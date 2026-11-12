#!/usr/bin/env python3
"""Szkice odkryć procesu 16 z WŁASNEGO repo projektu – CEO projektu nie przegapia poprawek mechanizmów (procesy/16-wymiana-ceo.md).

  python3 -I scripts/odkrycia.py [--dni 1 | --od <rewizja>] [--do HEAD] [--katalog <wyjście>] [--json]

Bierze commity bez scaleń z okna (bez „szablon: aktualizacja…”), zostawia tylko pliki szkieletu-mechanizmów (hook, skill, skrypt,
strażnik, kontrola, próg, proces, instrukcja roli) poza ścieżkami lokalnymi (`.szablon-lokalne`, ta sama logika co zgodnosc.py)
i dla każdego takiego commita robi szkic rekordu `odkrycie` (scripts/wymiana.py): projekt, rodzaj, sciezki, wersja (sha7 commita),
`dowod` z nazwą zmienionego testu. Pola `objaw`, `przyczyna`, `zmiana` i ocena `ogolnosc`/`pilnosc` zostają do uzupełnienia przez CEO
– szkic celowo nie przechodzi `wymiana.py sprawdz`, dopóki ich nie wypełni. Nic nie wysyła i niczego nie zmienia w repo; temat
commita nie trafia do szkicu (może zawierać treść biznesową) – tylko liczby i ścieżki szkieletu. Bez sieci, biblioteka standardowa.
Kody: 0 – wynik (także pusty) · 2 – błąd (nie repo git, zła rewizja).
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wymiana as W  # noqa: E402
import zgodnosc as Z  # noqa: E402

# (wzorzec ścieżki, rodzaj odkrycia) – pierwsze dopasowanie wygrywa; ścieżki spoza mapy to praca operacyjna i odpadają.
MAPA = [
    (r"^\.claude/hooks/", "hook"), (r"^\.claude/skills/", "skill"), (r"^\.claude/", "inne"),
    (r"^moduly/straznik/", "straznik"), (r"^ceo/kontrole/progi\.yaml$", "prog"), (r"^ceo/kontrole/", "kontrola"),
    (r"^procesy/", "proces"), (r"^role/", "instrukcja"), (r"^flota/szablony/", "instrukcja"),
    (r"^(scripts|flota|pm/narzedzia|recenzent/skrypty|ceo/kpi|ewaluacje)/[^/]+\.(py|sh)$", "skrypt"),
]
TEST = re.compile(r"(^|/)test[_-][^/]+$")


def rodzaj(sciezka):
    return next((r for w, r in MAPA if re.search(w, sciezka)), None)


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git %s: %s" % (args[0], p.stderr.strip()[:200]))
    return p.stdout


def projekt(repo):
    try:
        m = re.search(r"^\s+prefiks:\s*\"?([a-z0-9][a-z0-9-]{1,40})\"?", (repo / "org.yaml").read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def szkice(repo, od=None, dni=1, do="HEAD"):
    zakres = ["%s..%s" % (od, do)] if od else ["--since=%d.days" % dni, do]
    lokalna = Z.dopasuj_lokalne(Z.lokalne(str(repo)))
    wynik = []
    for blok in git(repo, "log", "--no-merges", "--format=@@%H%x09%s", "--name-only", *zakres).split("@@")[1:]:
        naglowek, *pliki = [l for l in blok.splitlines() if l.strip()]
        sha, temat = naglowek.split("\t", 1)
        if temat.startswith("szablon: aktualizacja"):
            continue
        mech = [p for p in pliki if rodzaj(p) and not lokalna(p)]
        if not mech:
            continue
        rodzaje = [rodzaj(p) for p in mech if not TEST.search(p)] or [rodzaj(mech[0])]
        testy = [p for p in mech if TEST.search(p)]
        r = W.wzor("odkrycie")
        r.update({"projekt": projekt(repo), "rodzaj": max(sorted(set(rodzaje)), key=rodzaje.count), "wersja": sha[:7],
                  "sciezki": sorted(mech)[:W.MAX_LISTA],
                  "dowod": ("commit %s; test: %s" % (sha[:7], ", ".join(testy[:3]))) if testy else "", "objaw": "", "przyczyna": "",
                  "zmiana": "", "ogolnosc": "ogolne|domenowe", "pilnosc": "bezpieczenstwo|zwykle"})
        wynik.append(r)
    return wynik


def main(argv=None):
    ap = argparse.ArgumentParser(description="Szkice rekordów `odkrycie` z commitów mechanizmów własnego repo")
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parent.parent))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dni", type=int, default=1)
    g.add_argument("--od")
    ap.add_argument("--do", default="HEAD")
    ap.add_argument("--katalog", help="zapis szkiców jako odkrycie-<sha7>.json (domyślnie tylko lista na stdout)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    try:
        lista = szkice(repo, a.od, a.dni, a.do)
    except (RuntimeError, OSError) as e:
        print("BŁĄD: %s" % e, file=sys.stderr)
        return 2
    if a.katalog:
        kat = pathlib.Path(a.katalog)
        kat.mkdir(parents=True, exist_ok=True)
        for r in lista:
            (kat / ("odkrycie-%s.json" % r["wersja"])).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(lista, ensure_ascii=False, indent=1))
    else:
        for r in lista:
            print("%s  %-10s %s" % (r["wersja"], r["rodzaj"], ", ".join(r["sciezki"])))
        print("szkiców: %d – uzupełnij objaw, przyczyna, zmiana, dowod, ogolnosc, pilnosc → wymiana.py sprawdz → wyslij" % len(lista))
    return 0


if __name__ == "__main__":
    sys.exit(main())
