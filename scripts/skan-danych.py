#!/usr/bin/env python3
"""Skaner danych osobowych w plikach organizacji (dzienniki, rejestry, analizy, notatki) – egzekwuje `zasady.md` A.5
(„dane osobowe – minimum”). Bez sieci, bez LLM, biblioteka standardowa.

  python3 -I scripts/skan-danych.py                 # wszystkie pliki śledzone przez git (grupa w scripts/testy.sh)
  python3 -I scripts/skan-danych.py --staged        # tylko linie dodane w poczekalni gita (hook przed commitem – opcjonalny)
  python3 -I scripts/skan-danych.py --pliki A B …   # wskazane pliki (np. próbka kwartalna)
  python3 -I scripts/skan-danych.py --json          # wynik jako JSON (bez wartości – tylko kategoria, plik, linia, maska)

Kategorie (każda z kontrolą sumy albo formatu, żeby ograniczyć fałszywe trafienia):
  PESEL     11 cyfr z poprawną sumą kontrolną i miesiącem
  NIP       10 cyfr (także 3-3-2-2 / 3-2-2-3) z poprawną sumą kontrolną, nie od 0 (numery KRS)
  IBAN      kod kraju + 2 cyfry kontrolne + 11–30 znaków, poprawne mod 97 (ze spacjami albo bez)
  EMAIL     adres poza wyjątkami: domena firmy (org.yaml → organizacja.domena) z subdomenami, domeny przykładowe
            (example.*, *.example, *.invalid, *.test, *.localhost), users.noreply.github.com, gov.pl (adresy funkcyjne urzędów)
  TELEFON   numer z separatorami (+CC NNN NNN NNN, NNN-NNN-NNN, NNN NNN NNN) albo +CCNNNNNNNNN
  DOKUMENT  dowód osobisty (3 litery + 6 cyfr) albo paszport (2 litery + 7 cyfr) z cyfrą kontrolną – bez spacji
Wyjątki dla konkretnych trafień (dane fikcyjne w testach, adresy funkcyjne): `bezpieczenstwo/skan-danych-wyjatki.tsv` –
plik<TAB>kategoria<TAB>SHA-256 wartości (bez spacji, małymi literami; nigdy sama wartość)<TAB>powód. Wartości w wyniku są maskowane.

Kody: 0 – brak trafień · 1 – trafienia (usunąć z bieżących plików w 24 h; historia gita – tylko po decyzji właściciela) · 2 – błąd.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

sys.dont_write_bytecode = True
WYJATKI = "bezpieczenstwo/skan-danych-wyjatki.tsv"
POMIJANE_ROZSZERZENIA = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".pptx", ".docx", ".xlsx", ".woff",
                         ".woff2", ".ttf", ".otf", ".sqlite", ".db", ".pyc"}
MAKS_ROZMIAR = 2_000_000          # większe pliki tekstowe to zwykle zrzuty danych – do próbki ręcznej

PESEL = re.compile(r"(?<![\w-])\d{11}(?![\w-])")
NIP = re.compile(r"(?<![\w-])(\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3}|\d{10})(?![\w-])")
IBAN = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?)(?![A-Za-z0-9])")
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")
TELEFON = re.compile(r"(?<![\w.+/-])(?:\+\d{2}[ -]?\d{3}[ -]?\d{3}[ -]?\d{3}|\d{3}[ -]\d{3}[ -]\d{3})(?![\w./-])")
DOWOD = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3})(\d{6})(?![A-Za-z0-9])")      # bez spacji – „US 9910743” to np. numer znaku towarowego
PASZPORT = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2})(\d{7})(?![A-Za-z0-9])")
DOMENY_DOZWOLONE = re.compile(r"(^|\.)(example(\.(com|org|net|pl))?|[\w.-]+\.(invalid|test|localhost|example)|users\.noreply\.github\.com"
                              r"|gov\.pl)$", re.I)


def pesel_ok(s):
    w = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    if (10 - sum(int(c) * k for c, k in zip(s[:10], w)) % 10) % 10 != int(s[10]):
        return False
    return 1 <= int(s[2:4]) % 20 <= 12 and 1 <= int(s[4:6]) <= 31    # miesiąc z przesunięciem stulecia (+20, +40, +60, +80)


def nip_ok(s):
    c = re.sub(r"\D", "", s)
    if len(c) != 10 or len(set(c)) == 1 or c[0] == "0":
        return False
    k = sum(int(a) * b for a, b in zip(c[:9], (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11
    return k != 10 and k == int(c[9])


def iban_ok(s):
    c = s.replace(" ", "")
    if not 15 <= len(c) <= 34:
        return False
    return int("".join(str(int(z, 36)) for z in c[4:] + c[:4])) % 97 == 1


def _kontrolna_ok(litery, cyfry, wagi, poz):
    """Dokument (ICAO 9303: A=10 … Z=35): cyfra kontrolna na pozycji `poz`, suma ważona pozostałych znaków mod 10."""
    znaki = [ord(z) - 55 for z in litery] + [int(c) for c in cyfry]
    reszta, w = znaki[:poz] + znaki[poz + 1:], wagi[:poz] + wagi[poz + 1:]
    return sum(a * b for a, b in zip(reszta, w)) % 10 == znaki[poz]


def dowod_ok(litery, cyfry):
    return _kontrolna_ok(litery, cyfry, (7, 3, 1, 9, 7, 3, 1, 7, 3), 3)


def paszport_ok(litery, cyfry):
    return _kontrolna_ok(litery, cyfry, (7, 3, 9, 1, 7, 3, 1, 7, 3), 2)


def domena_firmy(repo):
    try:
        m = re.search(r"^\s+domena\s*:\s*[\"']?([A-Za-z0-9.-]+)", (repo / "org.yaml").read_text(encoding="utf-8"), re.M)
        return (m.group(1) if m else "").lower()
    except OSError:
        return ""


def maska(kat, s):
    if kat == "EMAIL":
        lok, dom = s.split("@", 1)
        return lok[:1] + "***@" + dom
    c = re.sub(r"\s", "", s)
    return c[:2] + "*" * max(len(c) - 4, 1) + c[-2:]


def skrot(s):
    return hashlib.sha256(re.sub(r"\s", "", s).lower().encode("utf-8")).hexdigest()


def skanuj_linie(t, domena):
    """-> [(kategoria, wartość)] dla jednej linii tekstu."""
    wynik = []
    for m in EMAIL.finditer(t):
        dom = m.group(1).lower()
        if DOMENY_DOZWOLONE.search(dom) or (domena and (dom == domena or dom.endswith("." + domena))):
            continue
        wynik.append(("EMAIL", m.group(0)))
    wynik += [("PESEL", m.group(0)) for m in PESEL.finditer(t) if pesel_ok(m.group(0))]
    pesele = {w for k, w in wynik if k == "PESEL"}
    wynik += [("NIP", m.group(0)) for m in NIP.finditer(t) if m.group(0) not in pesele and nip_ok(m.group(0))]
    wynik += [("IBAN", m.group(1)) for m in IBAN.finditer(t) if iban_ok(m.group(1))]
    wynik += [("TELEFON", m.group(0)) for m in TELEFON.finditer(t)]
    wynik += [("DOKUMENT", m.group(0)) for m in DOWOD.finditer(t) if dowod_ok(m.group(1), m.group(2))]
    wynik += [("DOKUMENT", m.group(0)) for m in PASZPORT.finditer(t) if paszport_ok(m.group(1), m.group(2))]
    return wynik


def wczytaj_wyjatki(repo):
    """-> {(plik, kategoria, sha256)}. Wiersz bez skrótu (64 hex) albo bez powodu = błąd (kod 2)."""
    p = repo / WYJATKI
    w = set()
    if not p.exists():
        return w
    for nr, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not l.strip() or l.startswith("#"):
            continue
        pola = l.split("\t")
        if len(pola) < 4 or not re.fullmatch(r"[0-9a-f]{64}", pola[2]) or not pola[3].strip():
            raise ValueError("%s linia %d: wymagane plik, kategoria, sha256 (64 znaki hex) i powód" % (WYJATKI, nr))
        w.add((pola[0], pola[1], pola[2]))
    return w


def pliki_sledzone(repo):
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def linie_staged(repo):
    """-> {plik: [(nr, tekst)]} – tylko linie dodane w poczekalni."""
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "-U0", "--no-color", "--no-ext-diff"],
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    wynik, plik, nr = {}, None, 0
    for l in diff.splitlines():
        if l.startswith("+++ "):
            plik = None if l[4:] == "/dev/null" else re.sub(r"^b/", "", l[4:]).strip()
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", l)
        if m:
            nr = int(m.group(1))
        elif l.startswith("+") and plik:
            wynik.setdefault(plik, []).append((nr, l[1:]))
            nr += 1
    return wynik


def linie_pliku(repo, rel):
    p = repo / rel
    if p.suffix.lower() in POMIJANE_ROZSZERZENIA or not p.is_file() or p.stat().st_size > MAKS_ROZMIAR:
        return []
    dane = p.read_bytes()
    if b"\0" in dane[:8192]:
        return []
    return list(enumerate(dane.decode("utf-8", "replace").splitlines(), 1))


def skanuj(repo, zrodlo):
    """zrodlo: {plik: [(nr, tekst)]} -> lista trafień po odjęciu wyjątków."""
    domena, wyjatki, trafienia = domena_firmy(repo), wczytaj_wyjatki(repo), []
    for plik in sorted(zrodlo):
        if plik == WYJATKI:
            continue
        for nr, t in zrodlo[plik]:
            for kat, wart in skanuj_linie(t, domena):
                if (plik, kat, skrot(wart)) not in wyjatki:
                    trafienia.append({"kategoria": kat, "plik": plik, "linia": nr, "maska": maska(kat, wart)})
    return trafienia


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skaner danych osobowych (PESEL, NIP, IBAN, e-mail, telefon, numer dokumentu).")
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parent.parent))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="tylko linie dodane w poczekalni (hook przed commitem)")
    g.add_argument("--pliki", nargs="+", help="wskazane pliki (ścieżki względem repo)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    repo = pathlib.Path(a.repo).resolve()
    try:
        zrodlo = linie_staged(repo) if a.staged else {p: linie_pliku(repo, p) for p in (a.pliki or pliki_sledzone(repo))}
        trafienia = skanuj(repo, zrodlo)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print("BŁĄD: %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"plikow": len(zrodlo), "trafienia": trafienia}, ensure_ascii=False, indent=1))
    elif trafienia:
        for t in trafienia:
            print("%-8s %s:%d: %s" % (t["kategoria"], t["plik"], t["linia"], t["maska"]))
        licz = {}
        for t in trafienia:
            licz[t["kategoria"]] = licz.get(t["kategoria"], 0) + 1
        print("TRAFIENIA: %d (%s) w %d plikach – usuń z bieżących plików w 24 h; fałszywe trafienie → wiersz w %s (sha256, powód)"
              % (len(trafienia), ", ".join("%s %d" % kv for kv in sorted(licz.items())), len({t["plik"] for t in trafienia}), WYJATKI))
    else:
        print("OK: brak danych osobowych w %d plikach" % len(zrodlo))
    return 1 if trafienia else 0


if __name__ == "__main__":
    sys.exit(main())
