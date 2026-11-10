#!/usr/bin/env python3
"""Indeks i kontrola rejestru decyzji (decyzje/D-*.md z frontmatterem).

  python3 -I scripts/decyzje-indeks.py              # generuje decyzje.md (indeks ≤ 200 linii)
  python3 -I scripts/decyzje-indeks.py --sprawdz    # kod 1: sprzeczne accepted o tym samym scope, złe supersedes, brak pól
  python3 -I scripts/decyzje-indeks.py --archiwizuj # superseded/expired > 90 dni → decyzje/archiwum/RRRR/
"""
import datetime, pathlib, re, shutil, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
KAT = REPO / "decyzje"
WYMAGANE = ("id", "status", "data", "kto", "scope")


def czytaj(p):
    t = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", t, re.S)
    fm = {}
    if m:
        for l in m.group(1).splitlines():
            k, _, v = l.partition(":")
            v = v.split("#", 1)[0].strip().strip("\"'")
            fm[k.strip()] = None if v in ("null", "") else v
    tytul = re.search(r"^# (.+)$", t, re.M)
    fm["_tytul"] = tytul.group(1).strip() if tytul else p.stem
    fm["_plik"] = p
    return fm


def wszystkie():
    return [czytaj(p) for p in sorted(KAT.glob("D-*.md"))]


def sprawdz(dec):
    b = []
    ids = {d.get("id") for d in dec}
    dzis = datetime.date.today().isoformat()
    for d in dec:
        for k in WYMAGANE:
            if not d.get(k):
                b.append("%s: brak pola %s" % (d["_plik"].name, k))
        if d.get("id") and d["id"] != d["_plik"].stem:
            b.append("%s: id ≠ nazwa pliku" % d["_plik"].name)
        if d.get("supersedes") and d["supersedes"] not in ids:
            b.append("%s: supersedes wskazuje nieistniejącą %s" % (d["_plik"].name, d["supersedes"]))
        if d.get("status") == "accepted" and d.get("wazna_do") and d["wazna_do"] < dzis and not d["wazna_do"].startswith("RRRR"):
            b.append("%s: accepted po terminie wazna_do %s – ustaw status expired" % (d["_plik"].name, d["wazna_do"]))
    zastapione = {d["supersedes"] for d in dec if d.get("supersedes")}
    for d in dec:
        if d.get("id") in zastapione and d.get("status") == "accepted":
            b.append("%s: zastąpiona przez inną decyzję, a nadal accepted" % d["_plik"].name)
    wg_scope = {}
    for d in dec:
        if d.get("status") == "accepted" and d.get("scope"):
            wg_scope.setdefault(d["scope"], []).append(d["id"])
    for sc, lista in wg_scope.items():
        if len(lista) > 1:
            b.append("sprzeczność: decyzje accepted o tym samym scope „%s” bez supersedes: %s" % (sc, ", ".join(lista)))
    return b


def indeks(dec):
    linie = ["# Rejestr decyzji – indeks (generowany: `python3 -I scripts/decyzje-indeks.py`; nie edytować ręcznie)", "",
             "Pliki: `decyzje/D-*.md` (format: `decyzje/README.md`). Zgoda na czynność = `DECYZJA=D-… <polecenie>` (hook sprawdza status accepted).", "",
             "| ID | Data | Status | Scope | Kto | Tytuł | Ważna do |", "|---|---|---|---|---|---|---|"]
    for d in sorted(dec, key=lambda x: x.get("id") or "", reverse=True):
        linie.append("| %s | %s | %s | %s | %s | %s | %s |" % (d.get("id"), d.get("data"), d.get("status"), d.get("scope"), d.get("kto"), d["_tytul"].split("·", 1)[-1].strip()[:70], d.get("wazna_do") or "–"))
    if len(linie) > 200:
        linie = linie[:198] + ["", "… starsze decyzje tylko w `decyzje/` (indeks ucięty do 200 linii – uruchom --archiwizuj)."]
    return "\n".join(linie) + "\n"


def archiwizuj(dec):
    n = 0
    granica = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    for d in dec:
        if d.get("status") in ("superseded", "expired") and d.get("data") and d["data"] < granica:
            cel = KAT / "archiwum" / d["data"][:4]
            cel.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d["_plik"]), str(cel / d["_plik"].name)); n += 1
    return n


def main(argv):
    dec = wszystkie()
    if "--sprawdz" in argv:
        b = sprawdz(dec)
        print("\n".join("BŁĄD: " + x for x in b) if b else "decyzje: OK (%d)" % len(dec))
        return 1 if b else 0
    if "--archiwizuj" in argv:
        print("zarchiwizowano:", archiwizuj(dec)); dec = wszystkie()
    (REPO / "decyzje.md").write_text(indeks(dec), encoding="utf-8")
    print("decyzje.md: %d decyzji" % len(dec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
