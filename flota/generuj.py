#!/usr/bin/env python3
"""Generator promptów zadań zaplanowanych floty z manifestu flota/zadania.yaml.

  python3 flota/generuj.py                  # zapisuje ceo/handoff/prompty/*.md (konto z manifestu – stan dzisiejszy)
  python3 flota/generuj.py --sprawdz        # nic nie zapisuje; kod 1, gdy którykolwiek prompt różni się od pliku (diff = 0)
  python3 flota/generuj.py --konto B --wyjscie /tmp/prompty-b
                                            # prompty dla konta B do katalogu + lista wywołań tworzących zadania
  python3 flota/generuj.py --lista --konto C  # tylko lista wywołań (kolejność z manifestu)
  python3 flota/generuj.py --routines [--tylko ceo,pm]
                                            # ceo/handoff/routines/<agent>.md – instrukcja założenia zadania chmurowego
                                            # (Claude Code scheduled task / routine): /schedule, cron z CRON_TZ, model, effort, repo, konektory, prompt

Szablon: flota/szablony/zadanie.md.tmpl ({naglowek}, {konto}, {tresc}); treść: flota/szablony/tresc/<agent>.md
z blokami {{blok:nazwa}} (flota/szablony/bloki/nazwa.md) i {{katalog}}. Generator niczego nie tworzy w aplikacji Claude –
zadania zakłada operator albo CEO w granicach uprawnienia.yaml. Dane firmy (nazwa, repo, prefiks) z org.yaml:
znaczniki {{org.nazwa}}, {{org.repo}}, {{org.github}}, {{org.prefiks}}.
"""
import argparse
import json
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
STD = "Prompt zadania zaplanowanego (generowany z flota/zadania.yaml). description: "


def wczytaj(repo=REPO):
    return yaml.safe_load((repo / "flota/zadania.yaml").read_text())


def org(repo=REPO):
    return yaml.safe_load((repo / "org.yaml").read_text())


KLASY_MODELI = ("sedzia", "mocny", "lekki", "mechaniczny")


def model_id(z, dane, o=None):
    """Klasa modelu z manifestu → identyfikator z org.yaml → runtime.modele (jedyne miejsce z ID modeli)."""
    klasa = str(z.get("model") or dane.get("model") or "mocny")
    modele = ((o if o is not None else org()).get("runtime") or {}).get("modele") or {}
    if klasa not in modele:
        raise SystemExit(f"BŁĄD: model „{klasa}” ({z.get('agent', '?')}) nie jest klasą z org.yaml → runtime.modele "
                         f"({', '.join(sorted(modele)) or 'brak klas'}) – manifest podaje klasę, nie ID modelu")
    return str(modele[klasa])


def rozliczenie(o=None):
    return str(((o if o is not None else org()).get("runtime") or {}).get("rozliczenie") or "team")


def konto_floty(o=None):
    rt = (o if o is not None else org()).get("runtime") or {}
    return str(rt.get("konto") or (rt.get("konta") or ["A"])[0]).upper()


BUDZETY = "flota/budzety.tsv"


def budzety(dane, o=None):
    """Budżety efektywne agentów (USD/mies. i USD/dzień). api: wartości z manifestu, sufit floty z mandatu (HALT).
    team: wartości z manifestu są wagami – skalowane do pojemności floty = (pojemność miejsca floty + płatna nadwyżka)
    × wykorzystanie_cel_proc; bez zmierzonej pojemności miejsca (null) – kwoty z manifestu, a nadwyżka dokłada się wagami."""
    o = o if o is not None else org()
    rt = o.get("runtime") or {}
    rozl = rozliczenie(o)
    dom_m, dom_d = float(dane.get("budzet_usd_miesiac") or 0), float(dane.get("budzet_usd_dzien") or 0)
    wiersze = [(z.get("katalog") or z["agent"], float(z.get("budzet_usd_miesiac", dom_m) or 0),
                float(z.get("budzet_usd_dzien", dom_d) or 0)) for z in dane["zadania"]]
    suma_wag = sum(m for _, m, _ in wiersze)
    if rozl == "team":
        cel = float(rt.get("wykorzystanie_cel_proc", 95))
        nadwyzka = float(rt.get("nadwyzka_usd_miesiac") or 0)
        miejsce = rt.get("pojemnosc_miejsca_usd_miesiac")
        if miejsce in (None, "", "null"):
            flota = round(suma_wag + nadwyzka * cel / 100, 2)
            opis = (f"konto {konto_floty(o)}: pojemność miejsca niezmierzona – kwoty z manifestu ({suma_wag:g} USD-ekw.)"
                    f" + nadwyżka {nadwyzka:g} USD × {cel:.0f} %; zmierz: python3 -I scripts/koszt.py raport --dni 14")
        else:
            flota = round((float(miejsce) + nadwyzka) * cel / 100, 2)
            opis = (f"konto {konto_floty(o)}: (miejsce {float(miejsce):g} USD-ekw. + nadwyżka {nadwyzka:g} USD) × {cel:.0f} %")
        mnoznik = flota / suma_wag if suma_wag else 0.0
        opis += f"; wagi z manifestu × {mnoznik:.2f}"
    else:
        flota = float(((o.get("mandat") or {}).get("budzet_floty_usd_miesiac")) or 0)
        mnoznik, opis = 1.0, "kwoty z manifestu; sufit floty z mandatu (100 % → HALT)"
    agenci = {k: (round(m * mnoznik, 2), round(d * mnoznik, 2), m) for k, m, d in wiersze}
    return {"rozliczenie": rozl, "flota_usd_miesiac": flota, "mnoznik": round(mnoznik, 4), "opis": opis, "agenci": agenci}


def budzety_tsv(dane, o=None):
    b = budzety(dane, o)
    w = ["# Budżety efektywne agentów – GENEROWANE (python3 flota/generuj.py z flota/zadania.yaml i org.yaml), nie edytuj.",
         "# Czytają: scripts/przebieg.sh (budżet dzienny i miesięczny), moduly/straznik (kontrola budzety).",
         f"# rozliczenie\t{b['rozliczenie']}",
         f"# flota_usd_miesiac\t{b['flota_usd_miesiac']:.2f}",
         f"# opis\t{b['opis']}",
         "katalog\twaga_usd_miesiac\tmiesiac_usd\tdzien_usd"]
    w += [f"{k}\t{waga:g}\t{m:.2f}\t{d:.2f}" for k, (m, d, waga) in b["agenci"].items()]
    return "\n".join(w) + "\n"


def task_id(agent, konto, repo=REPO):
    return f"{org(repo)['organizacja']['prefiks']}-{agent}-{konto.lower()}"


def tresc(z, repo=REPO):
    t = (repo / z["tresc"]).read_text()

    def blok(m):
        p = repo / "flota/szablony/bloki" / f"{m.group(1)}.md"
        if not p.exists():
            raise SystemExit(f"BŁĄD: brak bloku {m.group(1)} ({z['agent']})")
        return p.read_text()

    t = re.sub(r"\{\{blok:([a-z0-9-]+)\}\}", blok, t)
    t = t.replace("{{katalog}}", z.get("katalog") or z["agent"])
    o = org(repo)
    for k, v in {"nazwa": o["organizacja"]["nazwa"], "repo": o["repo"]["organizacja"],
                 "github": o["repo"]["github"], "prefiks": o["organizacja"]["prefiks"]}.items():
        t = t.replace("{{org.%s}}" % k, str(v))
    if "{{" in t:
        raise SystemExit(f"BŁĄD: nieznany znacznik w treści {z['agent']}: {re.search(r'{{[^}]*}}', t).group(0)}")
    return t


def prompt(z, konto=None, repo=REPO):
    szablon = (repo / "flota/szablony/zadanie.md.tmpl").read_text()
    naglowek = z.get("naglowek") or STD + z["opis"]
    return (szablon.replace("{naglowek}", naglowek)
                   .replace("{konto}", konto or z["konto_w_prompcie"])
                   .replace("{tresc}", tresc(z, repo)))


def wywolania(dane, konto, katalog=None, tylko=None):
    nazwa = org()["organizacja"]["nazwa"]
    for z in dane["zadania"]:
        if tylko and z["agent"] not in tylko:
            continue
        yield {
            "narzedzie": "mcp__scheduled-tasks__create_scheduled_task",
            "taskId": task_id(z["agent"], konto),
            "title": f"{nazwa}: {z['agent']} (konto {konto})",
            "cronExpression": z["cron"],
            "description": z["opis"],
            "prompt_z_pliku": str(pathlib.Path(katalog) / pathlib.Path(z["prompt"]).name) if katalog else z["prompt"],
            "priorytet": z["priorytet"],
            "model": model_id(z, dane),
            "klasa_modelu": z.get("model") or dane.get("model") or "mocny",
            "tryb": "Auto",
        }


def routine_md(z, dane, o, konto):
    """Instrukcja założenia zadania chmurowego (scheduled task) dla agenta – do wklejenia w /schedule albo w formularz web."""
    strefa = o["organizacja"].get("strefa", "Europe/Warsaw")
    model = model_id(z, dane, o)
    klasa = z.get("model") or dane.get("model") or "mocny"
    mies, dzien, _ = budzety(dane, o)["agenci"].get(z.get("katalog") or z["agent"], (0, 0, 0))
    if rozliczenie(o) == "api":
        budzet = (f"przebieg ≈ {z.get('budzet_usd_przebieg', dane.get('budzet_usd_przebieg', 2))} USD, dzień ≤ {dzien:g} USD "
                  f"(miękko: przebieg.sh wypisze BUDŻET-AGENTA), miesiąc ≤ {mies:g} USD")
    else:
        budzet = (f"team – udział w pojemności konta floty: {mies:g} USD-ekw./mies., {dzien:g} USD-ekw./dzień (`flota/budzety.tsv`); "
                  f"tempo limitu pilnuje regulator (`{task_id('limit', konto)}`), priorytet {z['priorytet']}; po limicie – tylko płatna nadwyżka")
    konektory = z.get("konektory") or ["(żadne – tylko repo i gh)"]
    return f"""# Zadanie chmurowe: {o['organizacja']['nazwa']} – {z['agent']} (konto {konto})

Zakłada operator (claude.ai/code/routines → New, albo w Claude Code: `/schedule`). Źródło: `flota/zadania.yaml`; po zmianie
manifestu wygeneruj ponownie (`python3 flota/generuj.py --routines`) i zaktualizuj zadanie (`/schedule update`).

| Pole | Wartość |
|---|---|
| Nazwa | `{task_id(z['agent'], konto)}` |
| Harmonogram (cron, strefa {strefa}) | `CRON_TZ={strefa} {z['cron']}` |
| Model | `{model}` (klasa `{klasa}` z `org.yaml → runtime.modele`) · effort: `{z.get('efekt', 'medium')}` |
| Repozytorium | `{o['repo']['github']}` (gałąź główna; agent commituje tylko swoje pliki wg zasady.md) |
| Konektory (tylko te!) | {', '.join('`%s`' % k for k in konektory)} |
| Środowisko chmurowe | dostęp sieciowy: domyślny + domeny z `toolbelt/katalog.md` potrzebne tej roli; zmienne: `AGENT_ROLA={z['agent']}`, `KONTO={konto}` |
| Budżet | {budzet} |
| Limity platformy | 100 uruchomień/h na konto, 30/h „Run now” per zadanie; sesja startuje w trybie auto |

## Prompt (wklej w całości)

```
{prompt(z, konto).rstrip()}
```

## Po założeniu
1. „Run now” raz ręcznie; sprawdź w repo linię w `przebiegi/{z.get('katalog') or z['agent']}/` i brak pytań o zgodę w transkrypcie.
2. Wpis w `backlog.md` (cykliczne) i w `rejestr-sesji.md` nie jest potrzebny – zadanie jest w manifeście.
3. Strażnik: kontrola konfiguracji zadań desktopu jest pominięta (runtime chmurowy); kontrola przebiegów (tagi) działa bez zmian.
"""


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--sprawdz", action="store_true")
    a.add_argument("--konto", help="A, B, C… – podmienia linię „Konto:” (domyślnie stan z manifestu)")
    a.add_argument("--wyjscie", help="katalog na prompty (domyślnie ceo/handoff/prompty w repo)")
    a.add_argument("--lista", action="store_true", help="tylko lista wywołań tworzących zadania")
    a.add_argument("--tylko", help="lista agentów po przecinku – start floty etapami (procesy/00-nowa-organizacja.md)")
    a.add_argument("--routines", action="store_true", help="zapisuje ceo/handoff/routines/<agent>.md – instrukcje zadań chmurowych")
    o = a.parse_args(argv)
    if o.konto and not re.fullmatch(r"[A-Z]", o.konto):
        a.error("konto to jedna wielka litera (A, B, C…)")
    dane = wczytaj()

    if o.routines:
        org_ = org()
        konto = o.konto or konto_floty(org_)
        tylko = set(o.tylko.split(",")) if o.tylko else None
        cel = pathlib.Path(o.wyjscie) if o.wyjscie else REPO / "ceo/handoff/routines"
        cel.mkdir(parents=True, exist_ok=True)
        n = 0
        for z in dane["zadania"]:
            if tylko and z["agent"] not in tylko:
                continue
            (cel / f"{z['agent']}.md").write_text(routine_md(z, dane, org_, konto))
            n += 1
        print(f"zapisano {n} instrukcji zadań chmurowych → {cel}")
        return 0

    if o.lista:
        if not o.konto:
            a.error("--lista wymaga --konto")
    else:
        rozne = 0
        cel = pathlib.Path(o.wyjscie) if o.wyjscie else REPO
        for z in dane["zadania"]:
            tekst = prompt(z, o.konto)
            plik = (cel / pathlib.Path(z["prompt"]).name) if o.wyjscie else REPO / z["prompt"]
            if o.sprawdz:
                if not plik.exists() or plik.read_text() != tekst:
                    rozne += 1
                    print(f"RÓŻNICA: {plik.relative_to(REPO) if plik.is_relative_to(REPO) else plik}")
            else:
                plik.parent.mkdir(parents=True, exist_ok=True)
                plik.write_text(tekst)
        if not o.wyjscie:
            tsv, plik_b = budzety_tsv(dane), REPO / BUDZETY
            if o.sprawdz:
                if not plik_b.exists() or plik_b.read_text() != tsv:
                    rozne += 1
                    print(f"RÓŻNICA: {BUDZETY} (python3 flota/generuj.py)")
            else:
                plik_b.write_text(tsv)
        if o.sprawdz:
            print(f"{len(dane['zadania'])} promptów i budżety, różnic: {rozne}")
            return 1 if rozne else 0
        print(f"zapisano {len(dane['zadania'])} promptów → {cel}; budżety → {BUDZETY}")

    if o.konto:
        print(f"\n# Zadania do utworzenia na koncie {o.konto} (kolejność ważna; prompt = treść pliku po generacji):")
        tylko = set(o.tylko.split(",")) if o.tylko else None
        for w in wywolania(dane, o.konto, o.wyjscie, tylko):
            print(json.dumps(w, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
