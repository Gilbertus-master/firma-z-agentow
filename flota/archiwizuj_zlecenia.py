#!/usr/bin/env python3
"""Archiwum zamkniętych zleceń (P0 architektury floty).

  python3 flota/archiwizuj_zlecenia.py [repo]                       # podgląd: liczby per plik, nic nie zapisuje
  python3 flota/archiwizuj_zlecenia.py [repo] zapisz [RRRR-MM]      # przenosi zamknięte wpisy do zlecenia/archiwum/RRRR-MM/

Zamknięte = nagłówek `## [zrobione…` / `## [zamknięte…`, albo `## [informacja…` z odpowiedzią w treści.
Treść wpisów bez zmian, kolejność zachowana; otwarte zostają. Wspólny checkout: przed – git pull --rebase,
po – git add zlecenia/ (tylko), commit, push od razu.
"""
import re, sys, pathlib, datetime
repo = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
zapis = len(sys.argv) > 2 and sys.argv[2] == "zapisz"
miesiac = sys.argv[3] if len(sys.argv) > 3 else datetime.date.today().strftime("%Y-%m")
def podziel(tekst):
    linie = tekst.splitlines(keepends=True)
    pre, wpisy, cur = [], [], None
    for l in linie:
        if l.startswith("## "):
            cur = [l]; wpisy.append(cur)
        elif cur is None: pre.append(l)
        else: cur.append(l)
    return pre, wpisy
def zamkniety(w):
    h = w[0]
    if re.match(r"## \[(zrobione|zamknięte)", h): return True
    if re.match(r"## \[informacja", h):
        body = "".join(w[1:])
        return bool(re.search(r"Odpowied[źz]|Potwierdz|przeczytane|zrobione", body, re.I))
    return False
suma = 0
for p in sorted((repo/"zlecenia").glob("*.md")):
    pre, wpisy = podziel(p.read_text())
    zam = [w for w in wpisy if zamkniety(w)]; otw = [w for w in wpisy if not zamkniety(w)]
    inf_bez = [w[0].strip()[:90] for w in wpisy if w[0].startswith("## [informacja") and not zamkniety(w)]
    nowe = "".join(pre) + "".join("".join(w) for w in otw)
    ln = nowe.count("\n") + (2 if zam else 0)
    print(f"{p.name:22} wpisy {len(wpisy):3} zamk {len(zam):3} otw {len(otw):3} linie {sum(1 for _ in p.read_text().splitlines()):5} -> {ln:4}", *inf_bez, sep="\n   " if inf_bez else " ")
    if zapis and zam:
        a = repo/"zlecenia/archiwum"/miesiac/p.name; a.parent.mkdir(parents=True, exist_ok=True)
        stary = a.read_text() if a.exists() else f"# Archiwum zleceń: {p.stem} ({miesiac})\n\nZamknięte wpisy przeniesione bez zmiany treści z [zlecenia/{p.name}](../../{p.name}) (P0 architektury floty, `ceo/analizy/2026-11-09-architektura-floty.md`). Najnowsze na dole.\n\n"
        a.write_text(stary + "".join("".join(w) for w in zam))
        link = f"Archiwum zamkniętych wpisów: [archiwum/{miesiac}/{p.name}](archiwum/{miesiac}/{p.name}).\n"
        pretxt = "".join(pre)
        if link not in pretxt:
            pretxt = pretxt.rstrip("\n") + "\n" + link + "\n"
        p.write_text(pretxt + "".join("".join(w) for w in otw))
