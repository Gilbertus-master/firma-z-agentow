#!/usr/bin/env python3
"""Rejestry wrażliwe w gicie: w plikach rejestru – i w historii gita – wolno trzymać tylko nagłówki i wiersze bez danych
(komentarze, nagłówek kolumn, wpisy założenia rejestru). Prawdziwe wpisy żyją poza repo (baza, sejf, system dziedzinowy), bo
historii gita w praktyce nie da się wyczyścić, a repo czyta więcej osób i agentów niż rejestr.

  python3 -I scripts/rejestry-git.py                 # pliki śledzone + historia (wiersze dodane w dowolnym commicie)
  python3 -I scripts/rejestry-git.py --bez-historii

Konfiguracja: `bezpieczenstwo/rejestry-wrazliwe.tsv` – wiersz `wzorzec<TAB>reguła`; wzorzec jak git :(glob) (`*` w obrębie
katalogu, `**` – dowolnie głęboko); reguła:
  naglowek:<kol1>,<kol2>,…   plik tabelaryczny (TSV) – dozwolony pusty wiersz, komentarz `#…` i ten nagłówek (może być kilka reguł)
  typ:<a>,<b>,…              plik JSONL – dozwolony obiekt z polem `typ` z listy (np. założenie rejestru, test kanału bez danych)
Pusta konfiguracja = nic do sprawdzenia (kod 0). Wynik podaje tylko plik, linię albo commit i powód – NIGDY treści wiersza.
Kody: 0 – czysto · 1 – niedozwolony wiersz · 2 – błąd (konfiguracja, git, plik).
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

KONFIGURACJA = "bezpieczenstwo/rejestry-wrazliwe.tsv"


def _glob(wzor):
    r, i = "", 0
    while i < len(wzor):
        if wzor.startswith("**", i):
            r, i = r + ".*", i + 2
        elif wzor[i] == "*":
            r, i = r + "[^/]*", i + 1
        else:
            r, i = r + re.escape(wzor[i]), i + 1
    return re.compile(r + "$")


def wczytaj(repo):
    """-> [(wzorzec, regex, {"naglowek": set(...), "typ": set(...)})] w kolejności pliku."""
    p = repo / KONFIGURACJA
    reguly = {}
    if not p.exists():
        return []
    for nr, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not l.strip() or l.lstrip().startswith("#"):
            continue
        pola = l.split("\t")
        m = re.fullmatch(r"(naglowek|typ):(.+)", pola[1].strip()) if len(pola) == 2 else None
        if not m or not pola[0].strip():
            raise ValueError("%s linia %d: wymagane `wzorzec<TAB>naglowek:…|typ:…`" % (KONFIGURACJA, nr))
        r = reguly.setdefault(pola[0].strip(), {"naglowek": set(), "typ": set()})
        wart = [x.strip() for x in m.group(2).split(",")]
        if m.group(1) == "naglowek":
            r["naglowek"].add("\t".join(wart))
        else:
            r["typ"].update(wart)
    return [(w, _glob(w), r) for w, r in reguly.items()]


def regula(reguly, sciezka):
    return next((r for _, rx, r in reguly if rx.match(sciezka)), None)


def powod_wiersza(sciezka, linia, r):
    """None = wiersz dozwolony, inaczej krótki powód (bez treści wiersza)."""
    if not linia.strip() or linia.lstrip().startswith("#"):
        return None
    if not sciezka.endswith(".jsonl"):
        if "\t".join(k.strip() for k in linia.split("\t")) in r["naglowek"]:
            return None
        return "wiersz danych (dozwolone: komentarz, nagłówek z %s)" % KONFIGURACJA
    try:
        w = json.loads(linia)
    except ValueError:
        return "nieczytelny JSON"
    if isinstance(w, dict) and w.get("typ") in r["typ"]:
        return None
    return "wpis typu „%s” (dozwolone typy z %s)" % (w.get("typ") if isinstance(w, dict) and isinstance(w.get("typ"), str) else "?",
                                                    KONFIGURACJA)


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git %s: %s" % (args[0], p.stderr.strip()[:200]))
    return p.stdout


def sprawdz_pliki(repo, reguly):
    bledy = []
    for s in git(repo, "ls-files", "--", *(":(glob)" + w for w, _, _ in reguly)).splitlines():
        r = regula(reguly, s)
        for nr, linia in enumerate((repo / s).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            p = powod_wiersza(s, linia, r) if r else None
            if p:
                bledy.append("%s linia %d: %s" % (s, nr, p))
    return bledy


def sprawdz_historie(repo, reguly, wyjscie=None):
    """Wiersze dodane w historii (git log -p) – także później usunięte."""
    if wyjscie is None:
        wyjscie = git(repo, "log", "--all", "--no-renames", "--format=@@commit %h", "-p", "--", *(":(glob)" + w for w, _, _ in reguly))
    bledy, commit, plik = set(), "?", None
    for l in wyjscie.splitlines():
        if l.startswith("@@commit "):
            commit, plik = l.split(" ", 1)[1], None
        elif l.startswith("+++ "):
            plik = l[6:] if l.startswith("+++ b/") else None
        elif l.startswith("+") and plik and regula(reguly, plik):
            p = powod_wiersza(plik, l[1:], regula(reguly, plik))
            if p:
                bledy.add("commit %s, %s: %s" % (commit, plik, p))
    return sorted(bledy)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rejestry wrażliwe: w gicie tylko nagłówki i wiersze bez danych")
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parent.parent))
    ap.add_argument("--bez-historii", action="store_true")
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    try:
        reguly = wczytaj(repo)
        bledy = [] if not reguly else sprawdz_pliki(repo, reguly) + ([] if a.bez_historii else sprawdz_historie(repo, reguly))
    except (OSError, RuntimeError, ValueError) as e:
        print("BŁĄD: %s" % e, file=sys.stderr)
        return 2
    if bledy:
        print("NIEDOZWOLONE WIERSZE W REJESTRACH WRAŻLIWYCH W GICIE (zgłoś CEO jako incydent; treści nie kopiuj):")
        print("\n".join("  · " + b for b in bledy))
        return 1
    print("rejestry wrażliwe w gicie: %d reguł, tylko nagłówki i wiersze bez danych%s"
          % (len(reguly), "" if a.bez_historii else " (także w historii)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
