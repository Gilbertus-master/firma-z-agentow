#!/usr/bin/env python3
"""Regulator tempa zużycia limitu JEDNEGO konta floty (zadanie <prefiks>-limit-<konto>; org.yaml → runtime.konto).

Flota pracuje na jednym koncie (miejsce Team operatora albo klucz API) – bez rotacji kont: na planach Team każde miejsce należy
do jednej imiennej osoby, a limitów nie wolno przenosić ani dzielić (ceo/handoff/konto-floty.md). Cel: tygodniowy limit konta
zużywany równo w `okno_celu_h` godzin od początku okna (org.yaml → runtime.okno_celu_h; domyślnie 168 h = cały tydzień).
Po wyczerpaniu limitu praca idzie dalej tylko na płatnej nadwyżce organizacji (usage credits, runtime.nadwyzka_usd_miesiac > 0),
w granicach limitu wydatków ustawionego u Anthropic; bez nadwyżki do resetu pracuje tylko P1.

  python3 scripts/regulator.py --konto A --procent 37 --reset 2026-11-12T08:00:00Z [--procent5h 40 --reset5h <ISO>]
      liczy tempo, zapisuje ~/.<prefiks>-limit-A.json (czyta go scripts/przebieg.sh), przy „przyspiesz” (raz na 2 h)
      dopisuje wpis Pilne w zlecenia/ceo.md; przy wyczerpaniu limitu (≥ 98 %) – jeden wpis Pilne na okno

Pola pliku: procent, cel_teraz (100 × h od początku okna / okno_celu_h, maks. 100), odchylenie (pp; ujemne = za wolno),
tryb (przyspiesz < −10 pp · normalnie · zwolnij > +5 pp), do_konca_h, do_resetu_h, pilne_przyspiesz, wyczerpany, resets_at.
Okno 5-godzinne (opcjonalne): cel_5h = 100 × h / 5; zwolnij gdy odchylenie_5h > +10 pp po 15 min okna albo procent_5h ≥ 90 –
wtedy tryb = zwolnij i bez wpisu „przyspiesz” (budżet 5 h ma starczyć do resetu).
scripts/przebieg.sh: tryb zwolnij → P3 nie pracuje; zwolnij i odchylenie > +15 pp → także P2 (P1 zawsze). Tryb starszy
niż 2 h jest ignorowany. Linie wyjścia czytane przez prompt: „PILNE: dopisane …”, „LIMIT: wyczerpany …”.
Bez sieci i bez git. Testy: python3 -m unittest scripts/test_regulator.py
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

PRZYSPIESZ_PP = -10
ZWOLNIJ_PP = 5
PILNE_CO_H = 2
WYCZERPANY_PROC = 98
OKNO_5H = 5
ZWOLNIJ_5H_PP = 10
TWARDY_5H_PROC = 90
REPO = pathlib.Path(__file__).resolve().parent.parent


def org(repo=REPO):
    """Minimalny odczyt org.yaml: prefiks, konto floty, okno_celu_h, nadwyżka, strefa (bez PyYAML)."""
    t = (pathlib.Path(repo) / "org.yaml").read_text(encoding="utf-8") if (pathlib.Path(repo) / "org.yaml").exists() else ""
    def pole(k, dom):
        m = re.search(r"^\s*%s:\s*\"?([^\"#\n]+?)\"?\s*(#.*)?$" % k, t, re.M)
        return m.group(1).strip() if m else dom
    try:
        nadwyzka = float(pole("nadwyzka_usd_miesiac", "0"))
    except ValueError:
        nadwyzka = 0.0
    return {"prefiks": pole("prefiks", "org"), "konto": pole("konto", "A").upper(), "okno_celu_h": float(pole("okno_celu_h", "168")),
            "nadwyzka": nadwyzka, "strefa": pole("strefa", "Europe/Warsaw")}


def czas(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wczytaj(plik):
    try:
        return json.loads(pathlib.Path(plik).read_text())
    except (OSError, ValueError):
        return {}


def zapisz(plik, dane):
    plik = pathlib.Path(plik)
    tmp = plik.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dane, ensure_ascii=False) + "\n")
    tmp.replace(plik)


def tempo(procent, reset, teraz, okno_celu_h=60.0):
    poczatek = reset - dt.timedelta(days=7)
    h = max(0.0, (teraz - poczatek).total_seconds() / 3600)
    cel = min(100.0, 100.0 * h / okno_celu_h)
    odch = procent - cel
    tryb = "przyspiesz" if odch < PRZYSPIESZ_PP else "zwolnij" if odch > ZWOLNIJ_PP else "normalnie"
    do_konca = round(max(0.0, 100 - procent) / (procent / h), 1) if procent > 0 and h > 0 else None
    return {"procent": int(procent), "cel_teraz": round(cel, 1), "odchylenie": round(odch, 1), "tryb": tryb,
            "do_konca_h": do_konca, "do_resetu_h": round(max(0.0, (reset - teraz).total_seconds() / 3600), 1),
            "okno_od": iso(poczatek), "godzin_okna": round(h, 1), "resets_at": iso(reset), "okno_celu_h": okno_celu_h}


def tempo5h(procent, reset, teraz):
    h = min(OKNO_5H, max(0.0, OKNO_5H - (reset - teraz).total_seconds() / 3600))
    cel = 100.0 * h / OKNO_5H
    odch = procent - cel
    zwolnij = procent >= TWARDY_5H_PROC or (h >= 0.25 and odch > ZWOLNIJ_5H_PP)
    return {"procent_5h": int(procent), "cel_5h": round(cel, 1), "odchylenie_5h": round(odch, 1),
            "tryb_5h": "zwolnij" if zwolnij else "normalnie", "reset_5h": iso(reset)}


def wpis_pilne(konto, d, teraz, strefa):
    lok = teraz.astimezone(ZoneInfo(strefa))
    do_konca = f"{d['do_konca_h']} h" if d["do_konca_h"] is not None else "– (0%)"
    return (f"\n## [otwarte] {lok:%Y-%m-%d %H:%M} · od: limit (regulator, konto {konto}) · Pilne: przyspiesz\n"
            f"Limit konta {konto}: **{d['procent']}%** przy celu {d['cel_teraz']}% (odchylenie {d['odchylenie']:+.1f} pp; "
            f"{d['godzin_okna']} h z {d['okno_celu_h']:.0f} h okna celu). Przy obecnym tempie 100% za {do_konca}, reset za {d['do_resetu_h']} h. "
            f"Dosyp pracy (role/ceo.md, sekcja „Regulator tempa”): Pilne do agentów z zapasem zleceń, przyspieszenie terminów, "
            f"praca równoległa subagentów – w granicach udziałów z flota/budzety.tsv. Niewykorzystany limit miejsca przepada: gdy "
            f"„przyspiesz” wraca następnego dnia, klasa „lekki” dostaje model klasy „mocny” (org.yaml → runtime.modele, kontrola F-04). "
            f"Kolejny taki wpis najwcześniej za {PILNE_CO_H} h. Termin: najbliższy przebieg CEO.\n")


def wpis_wyczerpany(konto, d, teraz, strefa, nadwyzka):
    lok = teraz.astimezone(ZoneInfo(strefa))
    dalej = (f"praca idzie dalej na płatnej nadwyżce organizacji (usage credits) do {nadwyzka:.0f} USD/mies. – sprawdź limit "
             f"wydatków u Anthropic i udziały w flota/budzety.tsv" if nadwyzka > 0 else
             "do resetu pracuje tylko P1 (bez nadwyżki); stałe wyczerpanie = decyzja właściciela: wyższe miejsce albo nadwyżka")
    return (f"\n## [otwarte] {lok:%Y-%m-%d %H:%M} · od: limit (regulator, konto {konto}) · Pilne: limit konta floty wyczerpany\n"
            f"Limit konta {konto}: **{d['procent']}%**, reset za {d['do_resetu_h']} h; {dalej}. Kontrola F-04. Termin: najbliższy przebieg CEO.\n")


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--konto", required=True)
    a.add_argument("--procent", type=float)
    a.add_argument("--reset", help="resetsAt z get_usage (ISO)")
    a.add_argument("--procent5h", type=float)
    a.add_argument("--reset5h")
    a.add_argument("--teraz", help="do testów (ISO)")
    a.add_argument("--plik", help="domyślnie ~/.<prefiks>-limit-<konto>.json")
    a.add_argument("--repo", default=str(REPO))
    o = a.parse_args(argv)
    konto = o.konto.upper()
    if not re.fullmatch(r"[A-Z]", konto):
        a.error("konto to jedna wielka litera")
    cfg = org(o.repo)
    teraz = czas(o.teraz) if o.teraz else dt.datetime.now(dt.timezone.utc)
    plik = pathlib.Path(o.plik) if o.plik else pathlib.Path.home() / f".{cfg['prefiks']}-limit-{konto}.json"
    stare = wczytaj(plik)

    if o.procent is None or not o.reset:
        a.error("potrzebne --procent i --reset")

    reset = czas(o.reset)
    d = tempo(o.procent, reset, teraz, cfg["okno_celu_h"])
    okno_od = reset - dt.timedelta(days=7)
    wyczerpany = stare.get("wyczerpany")
    if wyczerpany and czas(wyczerpany) < okno_od:
        wyczerpany = None
    pilne = stare.get("pilne_przyspiesz")
    if pilne and czas(pilne) < okno_od:
        pilne = None
    d.update({"konto": konto, "sprawdzono": iso(teraz), "wyczerpany": wyczerpany, "pilne_przyspiesz": pilne})
    if o.procent5h is not None and o.reset5h:
        d5 = tempo5h(o.procent5h, czas(o.reset5h), teraz)
        d.update(d5)
        if d5["tryb_5h"] == "zwolnij":
            d["tryb_tydz"], d["odchylenie_tydz"] = d["tryb"], d["odchylenie"]
            d["tryb"], d["odchylenie"] = "zwolnij", max(d["odchylenie"], d5["odchylenie_5h"])

    linie = [f"Regulator {konto}: {d['procent']}% / cel {d['cel_teraz']}% ({d.get('odchylenie_tydz', d['odchylenie']):+.1f} pp) – "
             f"{d.get('tryb_tydz', d['tryb'])}; reset za {d['do_resetu_h']} h"]
    if "tryb_5h" in d:
        linie[0] += f"; okno 5 h: {d['procent_5h']}% / cel {d['cel_5h']}% ({d['odchylenie_5h']:+.1f} pp) – {d['tryb_5h']} → tryb: {d['tryb']}"
    if d["tryb"] == "przyspiesz" and d["procent"] < WYCZERPANY_PROC and (not pilne or (teraz - czas(pilne)).total_seconds() >= PILNE_CO_H * 3600):
        zl = pathlib.Path(o.repo) / "zlecenia" / "ceo.md"
        zl.parent.mkdir(parents=True, exist_ok=True)
        with zl.open("a", encoding="utf-8") as f:
            f.write(wpis_pilne(konto, d, teraz, cfg["strefa"]))
        d["pilne_przyspiesz"] = iso(teraz)
        linie.append("PILNE: dopisane do zlecenia/ceo.md – commit i push")
    if d["procent"] >= WYCZERPANY_PROC and not wyczerpany:
        zl = pathlib.Path(o.repo) / "zlecenia" / "ceo.md"
        zl.parent.mkdir(parents=True, exist_ok=True)
        with zl.open("a", encoding="utf-8") as f:
            f.write(wpis_wyczerpany(konto, d, teraz, cfg["strefa"], cfg["nadwyzka"]))
        d["wyczerpany"] = iso(teraz)
        linie.append(f"LIMIT: wyczerpany (≥ {WYCZERPANY_PROC}%) – " + ("dalej płatna nadwyżka organizacji" if cfg["nadwyzka"] > 0
                     else "do resetu tylko P1") + "; Pilne dopisane do zlecenia/ceo.md – commit i push")
    elif d["procent"] >= WYCZERPANY_PROC:
        linie.append("LIMIT: wyczerpany – zgłoszony w tym oknie, pomijam")
    zapisz(plik, d)
    print("\n".join(linie))
    return 0


if __name__ == "__main__":
    sys.exit(main())
