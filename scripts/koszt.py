#!/usr/bin/env python3
"""Pomiar kosztu każdego przebiegu agenta – bez LLM, z zapisu sesji Claude Code (ceo/handoff/konto-floty.md).

  python3 -I scripts/koszt.py sesja --hook             # hook SessionStart: zapamiętuje ścieżkę zapisu sesji (.claude/sesja-biezaca.json)
  python3 -I scripts/koszt.py zapisz --agent <agent>   # koniec przebiegu: tokeny × flota/ceny-modeli.yaml → przebiegi/<agent>/koszty-<data>.jsonl
  python3 -I scripts/koszt.py zapisz --hook            # hook SessionEnd: to samo lokalnie (agent z .agent-rola); bez agenta – nic
  python3 -I scripts/koszt.py raport [--dni 14] [--json]   # koszt na agenta i model, projekcja miesięczna, porównanie z rozliczeniem

Zapis sesji (JSONL) ma przy każdej odpowiedzi modelu pole message.usage; jedna odpowiedź zajmuje kilka linii z tym samym
requestId – liczymy ją raz. Sesje podagentów leżą w <katalog zapisu>/<sesja>/subagents/*.jsonl i wchodzą do kosztu przebiegu.
Linia kosztu jest idempotentna (ta sama sesja → linia zastąpiona), pole `koszt_usd` jest ostatnie (czyta je przebieg.sh i strażnik).
Koszt to ekwiwalent cen API: przy rozliczeniu `team` mierzy zużycie miejsca floty, przy `api` – faktyczny wydatek.
Hook nigdy nie blokuje sesji (kod 0 także przy błędzie). Testy: python3 -m unittest scripts/test_koszt.py
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

REPO = pathlib.Path(__file__).resolve().parent.parent
BIEZACA = ".claude/sesja-biezaca.json"
POLA = ("wejscie", "wyjscie", "cache_odczyt", "cache_zapis_5m", "cache_zapis_1h")


# ---------- konfiguracja (bez PyYAML) ----------

def ceny(repo=REPO):
    """flota/ceny-modeli.yaml → {"modele": {id: {wejscie, wyjscie, cache_odczyt}}, "m5", "m1h", "domyslny"}."""
    t = (pathlib.Path(repo) / "flota" / "ceny-modeli.yaml").read_text(encoding="utf-8")
    modele = {}
    for m in re.finditer(r"^\s+([a-z0-9.-]+):\s*\{([^}]*)\}", t, re.M):
        pola = dict(re.findall(r"(\w+):\s*([0-9.]+)", m.group(2)))
        modele[m.group(1)] = {k: float(v) for k, v in pola.items()}
    def liczba(k, dom):
        r = re.search(r"^%s:\s*([0-9.]+)" % k, t, re.M)
        return float(r.group(1)) if r else dom
    dom = re.search(r"^domyslny:\s*([a-z0-9.-]+)", t, re.M)
    return {"modele": modele, "m5": liczba("mnoznik_cache_5m", 1.25), "m1h": liczba("mnoznik_cache_1h", 2.0),
            "domyslny": dom.group(1) if dom else next(iter(modele), "")}


def org_pole(repo, klucz, dom=None):
    p = pathlib.Path(repo) / "org.yaml"
    t = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r"^\s*%s:\s*\"?([^\"#\n]*?)\"?\s*(#.*)?$" % klucz, t, re.M)
    return m.group(1).strip() if m and m.group(1).strip() not in ("", "null") else dom


# ---------- zużycie i koszt ----------

def pliki_sesji(transcript):
    p = pathlib.Path(transcript)
    pliki = [p] if p.exists() else []
    sub = p.with_suffix("") / "subagents"
    if sub.is_dir():
        pliki += sorted(sub.glob("*.jsonl"))
    return pliki


def zuzycie(transcript):
    """{model: {wejscie, wyjscie, cache_odczyt, cache_zapis_5m, cache_zapis_1h, zapytania}} z zapisu sesji i podagentów."""
    wynik = {}
    for plik in pliki_sesji(transcript):
        odp = {}
        for linia in plik.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(linia)
            except ValueError:
                continue
            msg = d.get("message") if isinstance(d, dict) else None
            if d.get("type") != "assistant" or not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                continue
            odp[d.get("requestId") or d.get("uuid") or len(odp)] = (msg.get("model") or "?", msg["usage"])
        for model, u in odp.values():
            w = wynik.setdefault(model, dict.fromkeys(POLA, 0) | {"zapytania": 0})
            cz = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
            z1h = int(cz.get("ephemeral_1h_input_tokens") or 0)
            z5m = int(cz.get("ephemeral_5m_input_tokens") or 0)
            if not cz:
                z5m = int(u.get("cache_creation_input_tokens") or 0)
            w["wejscie"] += int(u.get("input_tokens") or 0)
            w["wyjscie"] += int(u.get("output_tokens") or 0)
            w["cache_odczyt"] += int(u.get("cache_read_input_tokens") or 0)
            w["cache_zapis_5m"] += z5m
            w["cache_zapis_1h"] += z1h
            w["zapytania"] += 1
    return wynik


def koszt(zuz, cn):
    """{model: usd}, suma, lista modeli spoza cennika (liczone po stawce domyślnej)."""
    per, obce = {}, []
    for model, w in zuz.items():
        c = cn["modele"].get(model)
        if c is None:
            obce.append(model)
            c = cn["modele"].get(cn["domyslny"], {"wejscie": 0, "wyjscie": 0, "cache_odczyt": 0})
        we = c.get("wejscie", 0)
        usd = (w["wejscie"] * we + w["wyjscie"] * c.get("wyjscie", 0) + w["cache_odczyt"] * c.get("cache_odczyt", we * 0.1)
               + w["cache_zapis_5m"] * we * cn["m5"] + w["cache_zapis_1h"] * we * cn["m1h"]) / 1_000_000
        per[model] = round(usd, 4)
    return per, round(sum(per.values()), 4), obce


# ---------- zapis ----------

def dzis(repo, teraz=None):
    strefa = org_pole(repo, "strefa", "Europe/Warsaw")
    return (teraz or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(strefa))


def zapisz_linie(repo, agent, sesja, transcript, zrodlo, teraz=None):
    if not re.fullmatch(r"[a-z0-9-]+", agent or ""):
        return None
    zuz = zuzycie(transcript)
    if not zuz:
        return None
    per, suma, obce = koszt(zuz, ceny(repo))
    lok = dzis(repo, teraz)
    linia = {"czas": lok.isoformat(timespec="seconds"), "agent": agent, "sesja": sesja, "zrodlo": zrodlo,
             "rozliczenie": org_pole(repo, "rozliczenie", "team"),
             "modele": {m: {**{k: v for k, v in w.items()}, "usd": per[m]} for m, w in zuz.items()},
             "spoza_cennika": obce, "koszt_usd": suma}
    kat = pathlib.Path(repo) / "przebiegi" / agent
    kat.mkdir(parents=True, exist_ok=True)
    plik = kat / f"koszty-{lok:%Y-%m-%d}.jsonl"
    stare = plik.read_text(encoding="utf-8").splitlines() if plik.exists() else []
    nowe = [l for l in stare if not (sesja and f'"sesja": "{sesja}"' in l)] + [json.dumps(linia, ensure_ascii=False)]
    tmp = plik.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(nowe) + "\n", encoding="utf-8")
    tmp.replace(plik)
    return linia


def wejscie_hooka():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}


# ---------- raport ----------

def raport(repo, dni=14, teraz=None):
    koniec = dzis(repo, teraz).date()
    od = koniec - dt.timedelta(days=dni - 1)
    agenci, modele, dni_z_danymi = {}, {}, set()
    for plik in sorted((pathlib.Path(repo) / "przebiegi").glob("*/koszty-*.jsonl")):
        m = re.search(r"koszty-(\d{4}-\d{2}-\d{2})", plik.name)
        if not m:
            continue
        data = dt.date.fromisoformat(m.group(1))
        if not od <= data <= koniec:
            continue
        for linia in plik.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(linia)
            except ValueError:
                continue
            usd = d.get("koszt_usd")
            if not isinstance(usd, (int, float)):
                continue
            dni_z_danymi.add(data)
            a = agenci.setdefault(plik.parent.name, {"usd": 0.0, "przebiegi": 0})
            a["usd"] += usd; a["przebiegi"] += 1
            for mod, w in (d.get("modele") or {}).items():
                modele[mod] = modele.get(mod, 0.0) + float(w.get("usd") or 0)
    razem = sum(a["usd"] for a in agenci.values())
    n = max(1, len(dni_z_danymi))
    mies = razem / n * 30
    rozl = org_pole(repo, "rozliczenie", "team")
    cena = float(org_pole(repo, "cena_planu_usd_miesiac", "0") or 0)
    nadwyzka = float(org_pole(repo, "nadwyzka_usd_miesiac", "0") or 0)
    return {"od": od.isoformat(), "do": koniec.isoformat(), "dni_z_danymi": len(dni_z_danymi), "rozliczenie": rozl,
            "razem_usd": round(razem, 2), "projekcja_usd_miesiac": round(mies, 2),
            "agenci": {k: {"usd": round(v["usd"], 2), "przebiegi": v["przebiegi"]} for k, v in sorted(agenci.items(), key=lambda kv: -kv[1]["usd"])},
            "modele": {k: round(v, 2) for k, v in sorted(modele.items(), key=lambda kv: -kv[1])},
            "cena_planu_usd_miesiac": cena, "nadwyzka_usd_miesiac": nadwyzka}


def drukuj_raport(r):
    print(f"Koszt floty {r['od']} – {r['do']} (dni z danymi: {r['dni_z_danymi']}, rozliczenie: {r['rozliczenie']})")
    print(f"Razem: {r['razem_usd']:.2f} USD ekwiwalentu API · projekcja: {r['projekcja_usd_miesiac']:.2f} USD/mies.")
    if r["rozliczenie"] == "team":
        print(f"Team: miejsca planu {r['cena_planu_usd_miesiac']:.0f} USD + nadwyżka do {r['nadwyzka_usd_miesiac']:.0f} USD/mies. "
              f"Jeśli w tym okresie limit miejsca nie był wyczerpany, projekcja jest dolną granicą jego pojemności – wpisz ją do "
              f"org.yaml → runtime.pojemnosc_miejsca_usd_miesiac i uruchom python3 flota/generuj.py.")
    for k, v in r["agenci"].items():
        print(f"  {k:<16} {v['usd']:>9.2f} USD  ({v['przebiegi']} przebiegów)")
    if r["modele"]:
        print("  modele: " + " · ".join(f"{k} {v:.2f}" for k, v in r["modele"].items()))


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("polecenie", choices=["sesja", "zapisz", "raport"])
    a.add_argument("--hook", action="store_true", help="dane z wejścia hooka (stdin JSON); nigdy nie blokuje")
    a.add_argument("--agent")
    a.add_argument("--transcript")
    a.add_argument("--sesja")
    a.add_argument("--dni", type=int, default=14)
    a.add_argument("--json", action="store_true")
    a.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR") or str(REPO))
    o = a.parse_args(argv)
    repo = pathlib.Path(o.repo)
    try:
        if o.polecenie == "sesja":
            d = wejscie_hooka() if o.hook else {"session_id": o.sesja, "transcript_path": o.transcript}
            if d.get("transcript_path"):
                p = repo / BIEZACA
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"sesja": d.get("session_id"), "transcript": d["transcript_path"]}) + "\n", encoding="utf-8")
            return 0
        if o.polecenie == "zapisz":
            if os.environ.get("PRZEBIEG_HEADLESS"):   # scripts/przebieg-headless.sh zapisuje koszt z wyniku CLI
                return 0
            d = wejscie_hooka() if o.hook else {}
            if not d:
                try:
                    b = json.loads((repo / BIEZACA).read_text(encoding="utf-8"))
                    d = {"session_id": b.get("sesja"), "transcript_path": b.get("transcript")}
                except (OSError, ValueError):
                    d = {}
            transcript = o.transcript or d.get("transcript_path")
            agent = o.agent
            if not agent:
                rola = repo / ".agent-rola"
                agent = rola.read_text(encoding="utf-8").strip() if rola.exists() else None
            if not transcript or not agent:
                if not o.hook:
                    print("KOSZT: brak zapisu sesji albo agenta (hook SessionStart w .claude/settings.json; --transcript, --agent)")
                return 0 if o.hook else 1
            linia = zapisz_linie(repo, agent, o.sesja or d.get("session_id"), transcript, "hook" if o.hook else "przebieg")
            if linia and not o.hook:
                modele = " · ".join(f"{m} {w['usd']:.2f}" for m, w in linia["modele"].items())
                print(f"KOSZT: {agent} {linia['koszt_usd']:.2f} USD ({modele}) → przebiegi/{agent}/koszty-*.jsonl")
            return 0
        r = raport(repo, o.dni)
        print(json.dumps(r, ensure_ascii=False, indent=1)) if o.json else drukuj_raport(r)
        return 0
    except Exception as e:  # hook nie może przerwać sesji
        if o.hook:
            return 0
        print(f"KOSZT: błąd {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
