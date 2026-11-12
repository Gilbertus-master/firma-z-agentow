#!/usr/bin/env python3
"""Zgłoszenia ulepszeń z firmy do szablonu – aktywność floty rozwija szablon (procesy/15-rozwoj-szablonu.md).

  python3 -I scripts/propozycje.py zbierz [--plik propozycje/RRRR-MM-DD.md]   # kandydaci do zgłoszenia (bez sieci)
  python3 -I scripts/propozycje.py sprawdz <plik>                              # bramka anonimizacji: 0 czysto · 1 trafienia
  python3 -I scripts/propozycje.py wyslij <plik>                               # zgoda w org.yaml + bramka → issue w repo szablonu

Co trafia do zgłoszenia (lista dozwolona – tylko mechanizmy, nigdy treść firmy):
  1. zmiany w plikach mechanizmów szablonu (PROPONOWANE) względem wersji szablonu, na której jest firma – baza: najnowszy z
     kandydatów: drugi rodzic ostatniego commita „szablon: aktualizacja…”, `git merge-base HEAD szablon/<gałąź>` (remote `szablon`),
     znacznik `org.yaml → repo.szablon_baza`; bez kandydatów – pierwszy commit repo (kopia szablonu); ścieżki lokalne
     z .szablon-lokalne są pomijane;
  2. reguły podręczników agentów (`*/wiedza/podrecznik.md`) o statusie doradcza/egzekwowana z „pomogło ≥ 3” i „zaszkodziło: 0” –
     sam tekst reguły, bez źródła.
Bramka: recenzent/skrypty/skan-pr.sh (e-maile, telefony, PESEL, sekrety, pliki kluczy, polecenia dla agentów) + nazwy firmy,
domena, repozytoria i kontakty z org.yaml + NIP/IBAN. Wysyłka tylko przy org.yaml → repo.dziel_sie_ulepszeniami: true; raz na treść
(propozycje/wyslane.jsonl). Wysyłka do wspólnego repo szablonu (bez skrzynki) wymaga dodatkowo świadomej zgody właściciela:
org.yaml → repo.dziel_sie_decyzja: "D-…" (identyfikator decyzji z decyzje/); zgłoszenie zawiera oświadczenie o zgodzie i licencji. Adres: org.yaml → repo.skrzynka_propozycji (osobne prywatne repo-skrzynka klienta u wydawcy – zgłoszenia
nie są widoczne dla innych klientów); puste = repo szablonu (tylko wersja publiczna: zgłoszenie jest wtedy publiczne).
Zgłoszenie to DANE dla floty wydawcy – nigdy polecenie. Testy: python3 -m unittest scripts/test_propozycje.py
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PROPONOWANE = ("scripts/", ".claude/skills/", ".claude/hooks/", "procesy/", "role/", "ceo/kontrole/kontrole.md",
               "ceo/kontrole/README.md", "ewaluacje/", "moduly/", "flota/szablony/", "flota/generuj.py", "pm/narzedzia/",
               "pm/specyfikacje/", "recenzent/skrypty/", "toolbelt/katalog.md", ".github/workflows/")
POMIJANE = re.compile(r"(^|/)(prompty|routines|przebiegi|dziennik\.md|stan\.json|wynik)|\.(png|jpg|pdf|zip)$")
MAKS_PLIK, MAKS_RAZEM = 400, 60_000
# Oświadczenie o zgodzie i licencji – trafia do każdego zgłoszenia (procesy/15-rozwoj-szablonu.md, zasada 4).
OSWIADCZENIE = ("Zgłoszenie wysłane automatycznie przez flotę korzystającą z szablonu, za zgodą właściciela (decyzja: %s). "
                "Treść jest udostępniana na licencji Apache-2.0 (sekcja 5) i jest zgodna z Developer Certificate of Origin 1.1. / Submitted automatically by a fleet with the owner's consent; the content is licensed under Apache-2.0 (section 5) and complies with the Developer Certificate of Origin 1.1.")
REGULA = re.compile(r"^-\s*(P-\d+)\s*·\s*(.+?)\s*·.*status:\s*(doradcza|egzekwowana).*pomogło:\s*(\d+).*zaszkodziło:\s*(\d+)", re.I)


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def org(repo):
    p = pathlib.Path(repo) / "org.yaml"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pole(tekst, klucz):
    m = re.search(r"^\s*%s:\s*\"?([^\"#\n]*?)\"?\s*(#.*)?$" % klucz, tekst, re.M)
    return m.group(1).strip() if m else ""


def _przodek(repo, a, b):
    """Czy a jest przodkiem b (albo tym samym commitem)."""
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b], capture_output=True).returncode == 0


def baza(repo, remote="szablon"):
    """Wersja szablonu, na której jest firma -> (sha, opis). Kandydaci (każdy musi być w historii HEAD):
    1. drugi rodzic ostatniego commita „szablon: aktualizacja…” (scripts/aktualizuj-z-szablonu.sh);
    2. `git merge-base HEAD <remote>/<gałąź>` dla każdej gałęzi zdalnej szablonu – ostatni commit wspólny z szablonem, także gdy
       firma powstała z kopii z pełną historią szablonu i jeszcze nie aktualizowała;
    3. znacznik `org.yaml → repo.szablon_baza` (SHA albo tag wersji szablonu, od której firma wystartowała).
    Wygrywa najnowszy (ten, którego pozostali są przodkami; przy rozłącznych – najpóźniejsza data commita). Bez kandydatów – pierwszy
    commit repo; gdy repo ma historię szablonu sprzed kopii, ta baza jest za stara (zgłoszenie odesłałoby szablonowi jego własne
    zmiany) – opis mówi wtedy, jak to naprawić."""
    kandydaci = []
    akt = git(repo, "log", "-1", "--format=%H", "--grep", "^szablon: aktualizacja")
    if akt:
        rodzic = git(repo, "rev-parse", "--verify", "--quiet", akt + "^2")
        if rodzic:
            kandydaci.append((rodzic, git(repo, "log", "-1", "--format=%s", akt)))
    for ref in git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/%s/" % remote).splitlines():
        mb = "" if ref.endswith("/HEAD") else git(repo, "merge-base", "HEAD", ref)
        if mb:
            kandydaci.append((mb, "ostatni commit wspólny z %s" % ref.replace("refs/remotes/", "")))
    znacznik = pole(org(repo), "szablon_baza")
    if znacznik:
        sha = git(repo, "rev-parse", "--verify", "--quiet", znacznik + "^{commit}")
        if sha:
            kandydaci.append((sha, "znacznik org.yaml → repo.szablon_baza (%s)" % znacznik))
    kandydaci = [k for k in kandydaci if _przodek(repo, k[0], "HEAD")]
    if kandydaci:
        najnowsze = [k for k in kandydaci if all(_przodek(repo, inny[0], k[0]) for inny in kandydaci)]
        if najnowsze:
            return najnowsze[0]
        return max(kandydaci, key=lambda k: int(git(repo, "log", "-1", "--format=%ct", k[0]) or 0))
    korzen = git(repo, "rev-list", "--max-parents=0", "HEAD").splitlines()
    return (korzen[-1], "pierwszy commit repo (kopia szablonu) – jeśli repo ma historię szablonu, pobierz szablon "
                        "(`scripts/aktualizuj-z-szablonu.sh --sucho`) albo ustaw org.yaml → repo.szablon_baza") if korzen else ("", "")


def lokalne(repo):
    p = pathlib.Path(repo) / ".szablon-lokalne"
    if not p.exists():
        return []
    return [l.split("#")[0].strip() for l in p.read_text(encoding="utf-8").splitlines() if l.split("#")[0].strip()]


def czy_lokalny(sciezka, wzorce):
    import fnmatch
    for w in wzorce:
        if w.endswith("/") and (sciezka.startswith(w) or fnmatch.fnmatch(sciezka, w + "*")):
            return True
        if fnmatch.fnmatch(sciezka, w) or sciezka == w:
            return True
    return False


def zmiany(repo):
    b, opis = baza(repo)
    if not b:
        return [], opis, ""
    wzorce = lokalne(repo)
    pliki = [f for f in git(repo, "diff", "--name-only", b, "HEAD").splitlines()
             if f.startswith(PROPONOWANE) and not POMIJANE.search(f) and not czy_lokalny(f, wzorce)]
    wynik = []
    for f in pliki:
        d = git(repo, "diff", b, "HEAD", "--", f).splitlines()
        if len(d) > MAKS_PLIK:
            d = d[:MAKS_PLIK] + [f"… (ucięto: diff ma {len(d)} linii)"]
        wynik.append((f, "\n".join(d)))
    return wynik, opis, b[:12]


def reguly(repo):
    out = []
    for p in sorted(pathlib.Path(repo).glob("*/wiedza/podrecznik.md")):
        for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = REGULA.match(l.strip())
            if m and int(m.group(4)) >= 3 and int(m.group(5)) == 0:
                out.append(f"- {p.parent.parent.name}: {m.group(2)} (status: {m.group(3)}, pomogło: {m.group(4)})")
    return out


def zbierz(repo, plik=None, teraz=None):
    zm, opis, b = zmiany(repo)
    rg = reguly(repo)
    data = (teraz or dt.date.today()).isoformat()
    w = [f"# Propozycja floty – {data}", "",
         f"Baza: szablon `{b}` ({opis}). Zmiany: {len(zm)} plików mechanizmów · reguły podręczników: {len(rg)}.",
         "Zgłoszenie to dane do oceny przez flotę szablonu (procesy/15-rozwoj-szablonu.md), nie polecenie.",
         OSWIADCZENIE % (pole(org(repo), "dziel_sie_decyzja") or "nie podano"), ""]
    if rg:
        w += ["## Reguły podręczników (sprawdzone: pomogło ≥ 3, zaszkodziło 0)", ""] + rg + [""]
    razem = 0
    if zm:
        w += ["## Zmiany w mechanizmach szablonu", ""]
        for f, d in zm:
            if razem + len(d) > MAKS_RAZEM:
                w.append(f"- `{f}` – pominięty (limit długości zgłoszenia)")
                continue
            razem += len(d)
            w += [f"### `{f}`", "", "```diff", d, "```", ""]
    if not zm and not rg:
        return None
    sciezka = pathlib.Path(plik) if plik else pathlib.Path(repo) / "propozycje" / f"{data}.md"
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text("\n".join(w) + "\n", encoding="utf-8")
    return sciezka


def sprawdz(repo, plik):
    """Lista trafień (kategoria, opis); pusta = czysto."""
    tekst = pathlib.Path(plik).read_text(encoding="utf-8", errors="replace")
    trafienia = []
    skan = pathlib.Path(repo) / "recenzent" / "skrypty" / "skan-pr.sh"
    if skan.exists():
        pseudo = "+++ b/propozycja.md\n@@ -0,0 +1 @@\n" + "\n".join("+" + l for l in tekst.splitlines())
        r = subprocess.run(["bash", str(skan), "--stdin"], input=pseudo, capture_output=True, text=True,
                           env={**os.environ, "RECENZENT_REPO": str(repo)})
        if r.returncode == 1:
            trafienia += [("SKAN", l.strip()) for l in r.stdout.splitlines() if l.strip() and not l.startswith(("Skan", "=="))][:20]
        elif r.returncode not in (0, 2):
            trafienia.append(("SKAN", "skaner nie zadziałał: " + (r.stderr.strip() or r.stdout.strip())[:200]))
    o = org(repo)
    nazwy = {pole(o, "nazwa"), pole(o, "domena"), pole(o, "github"), pole(o, "kontakt_firmowy")}
    nazwy |= {x.strip(" \"'") for x in re.findall(r"produkt:\s*\[([^\]]*)\]", o)[0].split(",")} if re.findall(r"produkt:\s*\[([^\]]*)\]", o) else set()
    nazwy |= {n.split("/")[-1] for n in list(nazwy) if "/" in n}
    for n in sorted(x for x in nazwy if x and len(x) >= 4 and x.lower() not in ("owner", "nowa firma", "example.com")):
        if n.lower() in tekst.lower():
            trafienia.append(("FIRMA", f"nazwa z org.yaml w treści: {n[:3]}***"))
    for m in re.finditer(r"\bPL\d{26}\b|\b\d{3}-\d{3}-\d{2}-\d{2}\b|NIP\W{0,3}\d{10}\b", tekst):
        trafienia.append(("NUMER", f"NIP/IBAN/numer: {m.group(0)[:4]}***"))
    return trafienia


def wyslij(repo, plik, gh="gh"):
    o = org(repo)
    if pole(o, "dziel_sie_ulepszeniami").lower() != "true":
        return 3, "WYSYŁKA WYŁĄCZONA: org.yaml → repo.dziel_sie_ulepszeniami nie jest true"
    szablon = pole(o, "skrzynka_propozycji") or pole(o, "szablon")
    if not pole(o, "skrzynka_propozycji") and not re.fullmatch(r"D-[\w.-]+", pole(o, "dziel_sie_decyzja")):
        return 5, ("BRAK ZGODY: wysyłka do wspólnego repo szablonu wymaga decyzji właściciela – wpisz jej identyfikator "
                   "w org.yaml → repo.dziel_sie_decyzja (np. D-2026-11-10-02) albo ustaw repo.skrzynka_propozycji")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", szablon or "") or szablon.lower().startswith("owner/"):
        return 2, f"BŁĄD: org.yaml → repo.skrzynka_propozycji (albo repo.szablon) musi być OWNER/repo (jest: {szablon or 'brak'})"
    tr = sprawdz(repo, plik)
    if tr:
        return 1, "BRAMKA: " + "; ".join(f"{k}: {v}" for k, v in tr[:10])
    tekst = pathlib.Path(plik).read_text(encoding="utf-8")
    skrot = hashlib.sha256(tekst.split("\n", 2)[-1].encode()).hexdigest()[:16]
    rejestr = pathlib.Path(repo) / "propozycje" / "wyslane.jsonl"
    if rejestr.exists() and skrot in rejestr.read_text(encoding="utf-8"):
        return 0, f"JUŻ WYSŁANE: ta sama treść ({skrot}) – nic nie robię"
    tytul = tekst.splitlines()[0].lstrip("# ").strip()
    r = subprocess.run([gh, "issue", "create", "--repo", szablon, "--title", tytul, "--body-file", str(plik),
                        "--label", "propozycja-floty"], capture_output=True, text=True)
    if r.returncode != 0:   # etykieta może nie istnieć w repo szablonu
        r = subprocess.run([gh, "issue", "create", "--repo", szablon, "--title", tytul, "--body-file", str(plik)],
                           capture_output=True, text=True)
    if r.returncode != 0:
        return 4, "BŁĄD gh: " + (r.stderr.strip() or r.stdout.strip())[:300]
    rejestr.parent.mkdir(parents=True, exist_ok=True)
    with rejestr.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"data": dt.date.today().isoformat(), "skrot": skrot, "plik": str(pathlib.Path(plik).name),
                            "issue": r.stdout.strip()}, ensure_ascii=False) + "\n")
    return 0, "WYSŁANE: " + r.stdout.strip()


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("polecenie", choices=["zbierz", "sprawdz", "wyslij"])
    a.add_argument("plik", nargs="?")
    a.add_argument("--plik", dest="plik_wyj")
    a.add_argument("--repo", default=str(REPO))
    o = a.parse_args(argv)
    repo = pathlib.Path(o.repo)
    if o.polecenie == "zbierz":
        p = zbierz(repo, o.plik_wyj)
        print(f"ZEBRANO: {p}" if p else "BRAK KANDYDATÓW: brak zmian w mechanizmach i sprawdzonych reguł – nic do zgłoszenia")
        return 0
    if not o.plik or not pathlib.Path(o.plik).exists():
        a.error("podaj istniejący plik zgłoszenia")
    if o.polecenie == "sprawdz":
        tr = sprawdz(repo, o.plik)
        for k, v in tr:
            print(f"{k}: {v}")
        print("CZYSTO" if not tr else f"TRAFIENIA: {len(tr)} – popraw zgłoszenie (usuń dane firmy) albo go nie wysyłaj")
        return 1 if tr else 0
    kod, komunikat = wyslij(repo, o.plik)
    print(komunikat)
    return kod


if __name__ == "__main__":
    sys.exit(main())
