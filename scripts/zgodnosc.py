#!/usr/bin/env python3
"""Zgodność szkieletu projektu z szablonem (procesy/16-wymiana-ceo.md, „Zbieżność struktury”). Uruchamiany W PROJEKCIE;
sama biblioteka standardowa – plik można skopiować do projektu o innej strukturze bez zmian.

  python3 -I scripts/zgodnosc.py [--szablon <katalog klonu | ref git>] [--repo <katalog projektu>]      tabela dla człowieka
  python3 -I scripts/zgodnosc.py … --json                                                              pełny wynik (JSON)
  python3 -I scripts/zgodnosc.py … --rekord <projekt> [--plan "<jedno zdanie>"] [--wyjscie <plik>]     rekord `zgodnosc` procesu 16

Domyślny szablon: ref `szablon/main` (remote jak w scripts/aktualizuj-z-szablonu.sh; najpierw `git fetch`, chyba że
--bez-pobierania). Porównanie idzie PO ŚCIEŻKACH i skrótach treści (blob git), nie po historii – działa też w projekcie bez
wspólnej historii z szablonem. Projekt: drzewo HEAD (repo git) albo pliki katalogu; szablon: drzewo ref-a, HEAD klonu albo pliki.
Ścieżki lokalne (`.szablon-lokalne` projektu, bez pliku – lista domyślna jak w aktualizuj-z-szablonu.sh) i narzędzia samego
wydawcy (TYLKO_WYDAWCA) są pomijane.

Wynik: identyczne / zmienione / brakujace (ścieżki szablonu) + procent = identyczne / wszystkie, podział na obszary, do 10
ścieżek brakujących i zmienionych. Ścieżki istniejące tylko w projekcie NIE są wypisywane (mogą być treścią biznesową) – tylko
ich liczba w katalogach szkieletu. Rekord nie zawiera treści plików. Kody: 0 ok · 2 złe użycie, brak szablonu, rekord odrzucony.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

LOKALNE_DOMYSLNE = ["org.yaml", "uprawnienia.yaml", "decyzje.md", "decyzje/", "polityki/", "zlecenia/", "przebiegi/",
                    "koordynacja-odstepy.tsv", "flota/zadania.yaml", "*/agent.md", "*/dziennik.md", "*/stan.json",
                    "*/backlog.md", "*/wiedza/", "*/analizy/", "*/szkice/",
                    "ceo/scalanie/stan.json", "ceo/scalanie/dziennik.jsonl", "ceo/kontrole/wyniki.jsonl", "ewaluacje/[!_]*/",
                    "recenzent/szablony/", ".github/workflows/straznik.yml"]
OBSZARY = (".claude", "scripts", "moduly", "flota", "procesy", "role", "ceo", "pm", "docs")   # kolejność = waga w top 10
# Narzędzia samego wydawcy (eksport wersji publicznej) – nie są szkieletem projektu, więc nie wchodzą do pomiaru.
TYLKO_WYDAWCA = ["publiczne/", "scripts/eksport-publiczny.py"]
POZOSTALE = "pozostale"
POMIJANE = re.compile(r"(^|/)(__pycache__/|\.DS_Store$)|\.pyc$")
TOP = 10


def git(katalog, *args):
    p = subprocess.run(["git", "-C", katalog] + list(args), capture_output=True)
    return p.stdout.decode("utf-8", "surrogateescape") if p.returncode == 0 else None


def blob(dane):
    return hashlib.sha1(b"blob %d\0" % len(dane) + dane).hexdigest()


def drzewo_git(katalog, ref):
    """{ścieżka: sha bloba} z drzewa ref-a (bez submodułów)."""
    wyj = git(katalog, "ls-tree", "-r", "-z", "--full-tree", ref)
    if wyj is None:
        return None
    out = {}
    for wpis in wyj.split("\0"):
        if not wpis:
            continue
        meta, sciezka = wpis.split("\t", 1)
        _, typ, sha = meta.split()
        if typ == "blob" and not POMIJANE.search(sciezka):
            out[sciezka] = sha
    return out


def drzewo_katalogu(katalog):
    """{ścieżka: sha bloba} z plików katalogu (bez .git) – ten sam skrót co git, więc porównywalny z drzewem ref-a."""
    out = {}
    for korzen, katalogi, pliki in os.walk(katalog):
        katalogi[:] = [k for k in katalogi if k != ".git"]
        for nazwa in pliki:
            pelna = os.path.join(korzen, nazwa)
            sciezka = os.path.relpath(pelna, katalog).replace(os.sep, "/")
            if POMIJANE.search(sciezka):
                continue
            if os.path.islink(pelna):
                out[sciezka] = blob(os.readlink(pelna).encode("utf-8", "surrogateescape"))
            else:
                with open(pelna, "rb") as f:
                    out[sciezka] = blob(f.read())
    return out


def wersja(katalog, ref):
    tagi = [t for t in (git(katalog, "tag", "--points-at", ref) or "").split() if re.match(r"^v\d", t)]
    if tagi:
        return sorted(tagi)[-1]
    sha = git(katalog, "rev-parse", "--short=7", ref)
    return sha.strip() if sha else None


def lokalne(projekt):
    sciezka = os.path.join(projekt, ".szablon-lokalne")
    if not os.path.isfile(sciezka):
        return list(LOKALNE_DOMYSLNE)
    out = []
    with open(sciezka, encoding="utf-8") as f:
        for linia in f:
            linia = linia.split("#", 1)[0].strip()
            if linia:
                out.append(linia)
    return out


def _glob(wzor):
    """Wzorzec :(glob) gita → regex: `**` = cokolwiek, `*`, `?` i `[…]` nie przechodzą przez `/`."""
    r, i = "", 0
    while i < len(wzor):
        if wzor.startswith("**", i):
            r, i = r + ".*", i + 2
        elif wzor[i] == "*":
            r, i = r + "[^/]*", i + 1
        elif wzor[i] == "?":
            r, i = r + "[^/]", i + 1
        elif wzor[i] == "[" and "]" in wzor[i + 2:]:            # klasa znaków: [abc], [!_] / [^_] = zaprzeczenie
            k = wzor.index("]", i + 2)
            klasa = wzor[i + 1:k]
            neg = klasa[:1] in ("!", "^")
            r, i = r + "[" + ("^/" if neg else "") + re.escape(klasa[1:] if neg else klasa) + "]", k + 1
        else:
            r, i = r + re.escape(wzor[i]), i + 1
    return re.compile(r + r"(/.*)?$")


def dopasuj_lokalne(wzorce):
    """Ta sama logika co aktualizuj-z-szablonu.sh: linia z `*` = :(glob) (`/` na końcu = cały katalog), inaczej ścieżka
    dosłowna – plik albo katalog z całą zawartością."""
    regexy, doslowne = [], []
    for w in wzorce:
        if "*" in w:
            regexy.append(_glob(w + "**" if w.endswith("/") else w))
        else:
            doslowne.append(w.rstrip("/"))
    return lambda s: any(s == d or s.startswith(d + "/") for d in doslowne) or any(r.match(s) for r in regexy)


def obszar(sciezka):
    pierwszy = sciezka.split("/", 1)[0]
    return pierwszy if "/" in sciezka and pierwszy in OBSZARY else POZOSTALE


def waga(sciezka):
    o = obszar(sciezka)
    return (OBSZARY.index(o) if o in OBSZARY else len(OBSZARY), sciezka.count("/"), sciezka)


def porownaj(szablon, projekt, czy_lokalna):
    """szablon, projekt: {ścieżka: sha}. → wynik pomiaru (bez treści plików, bez ścieżek spoza szablonu)."""
    ident, zmien, brak, pominiete = [], [], [], 0
    for s, sha in szablon.items():
        if czy_lokalna(s):
            pominiete += 1
        elif s not in projekt:
            brak.append(s)
        elif projekt[s] == sha:
            ident.append(s)
        else:
            zmien.append(s)
    katalogi = {s.split("/", 1)[0] for s in szablon if "/" in s}
    tylko = sum(1 for s in projekt if s not in szablon and not czy_lokalna(s) and "/" in s and s.split("/", 1)[0] in katalogi)
    obszary = {}
    for nazwa, lista in (("identyczne", ident), ("zmienione", zmien), ("brakujace", brak)):
        for s in lista:
            obszary.setdefault(obszar(s), {"identyczne": 0, "zmienione": 0, "brakujace": 0})[nazwa] += 1
    razem = len(ident) + len(zmien) + len(brak)
    return {
        "identyczne": len(ident), "zmienione": len(zmien), "brakujace": len(brak),
        "procent": round(100.0 * len(ident) / razem, 1) if razem else 0.0,
        "obszary": {o: obszary[o] for o in list(OBSZARY) + [POZOSTALE] if o in obszary},
        "top_brakujace": sorted(brak, key=waga)[:TOP], "top_zmienione": sorted(zmien, key=waga)[:TOP],
        "tylko_w_projekcie": tylko, "pominiete_lokalne": pominiete,
    }


def obszary_rekordu(wynik):
    return ["%s: %d/%d" % (o, v["identyczne"], sum(v.values())) for o, v in wynik["obszary"].items()][:TOP]


def rekord(wynik, projekt, plan=""):
    r = {"typ": "zgodnosc", "projekt": projekt, "wersja_szablonu": wynik["wersja_szablonu"],
         "identyczne": wynik["identyczne"], "zmienione": wynik["zmienione"], "brakujace": wynik["brakujace"],
         "procent": wynik["procent"], "obszary": obszary_rekordu(wynik)}
    for k in ("top_brakujace", "top_zmienione"):
        if wynik[k]:
            r[k] = wynik[k]
    if plan:
        r["plan"] = plan
    return r


def tabela(w):
    linie = ["Zgodność szkieletu z szablonem %s (%s)" % (w["wersja_szablonu"], w["zrodlo"]),
             "  identyczne %d · zmienione %d · brakujące %d · zgodność %.1f %%" % (
                 w["identyczne"], w["zmienione"], w["brakujace"], w["procent"]),
             "", "  %-12s %6s %6s %6s %6s %7s" % ("obszar", "ident", "zmien", "brak", "razem", "%")]
    for o, v in w["obszary"].items():
        razem = sum(v.values())
        linie.append("  %-12s %6d %6d %6d %6d %6.1f" % (o, v["identyczne"], v["zmienione"], v["brakujace"], razem,
                                                       100.0 * v["identyczne"] / razem))
    linie += ["", "  pominięte ścieżki lokalne (.szablon-lokalne): %d · pliki tylko w projekcie (katalogi szkieletu): %d" % (
        w["pominiete_lokalne"], w["tylko_w_projekcie"])]
    for tytul, k in (("Brakujące", "top_brakujace"), ("Zmienione", "top_zmienione")):
        if w[k]:
            linie += ["", "  %s (do %d):" % (tytul, TOP)] + ["    " + s for s in w[k]]
    return "\n".join(linie)


def zmierz(projekt, szablon=None, remote="szablon", galaz="main", pobierz=True):
    """→ (wynik, None) albo (None, komunikat błędu)."""
    if git(projekt, "rev-parse", "--show-toplevel"):
        projekt = git(projekt, "rev-parse", "--show-toplevel").strip()
        p = drzewo_git(projekt, "HEAD")
        if p is None:
            p = drzewo_katalogu(projekt)
    else:
        p = drzewo_katalogu(projekt)
    if szablon and os.path.isdir(szablon):
        if git(szablon, "rev-parse", "--show-toplevel") and git(szablon, "rev-parse", "--verify", "-q", "HEAD"):
            s, wer, zrodlo = drzewo_git(szablon, "HEAD"), wersja(szablon, "HEAD"), "katalog klonu"
        else:
            s, wer, zrodlo = drzewo_katalogu(szablon), None, "katalog"
    else:
        ref = szablon or "%s/%s" % (remote, galaz)
        if pobierz and not szablon and git(projekt, "remote", "get-url", remote):
            if git(projekt, "fetch", "--quiet", remote, galaz) is None:
                print("UWAGA: git fetch %s %s nie powiódł się – porównuję z ostatnio pobranym %s" % (remote, galaz, ref),
                      file=sys.stderr)
        s, wer, zrodlo = drzewo_git(projekt, ref), wersja(projekt, ref), "ref %s" % ref
        if s is None:
            return None, "nie znam szablonu %s – podaj --szablon <katalog klonu | ref> albo dodaj remote '%s'" % (ref, remote)
    wynik = porownaj(s, p, dopasuj_lokalne(lokalne(projekt) + TYLKO_WYDAWCA))
    wynik.update(wersja_szablonu=wer or "nieznana", zrodlo=zrodlo)
    return wynik, None


def main(argv=None, wyjscie=sys.stdout):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--szablon", help="katalog klonu szablonu albo ref git (domyślnie <remote>/<galaz>)")
    a.add_argument("--repo", default=".", help="katalog projektu (domyślnie bieżący)")
    a.add_argument("--remote", default="szablon")
    a.add_argument("--galaz", default="main")
    a.add_argument("--bez-pobierania", action="store_true", help="nie rób git fetch remote-a szablonu")
    a.add_argument("--wersja", help="nadpisz wersję szablonu (sha7 albo tag) – np. dla katalogu bez gita")
    a.add_argument("--json", action="store_true")
    a.add_argument("--rekord", metavar="PROJEKT", help="zapisz rekord `zgodnosc` procesu 16 dla projektu (slug)")
    a.add_argument("--plan", default="", help="rekord: jedno zdanie – co projekt zrobi dalej")
    a.add_argument("--wyjscie", help="rekord: plik wyjściowy (domyślnie zgodnosc-<projekt>.json w katalogu tymczasowym)")
    o = a.parse_args(argv)
    pisz = lambda s: print(s, file=wyjscie)  # noqa: E731

    wynik, blad = zmierz(o.repo, o.szablon, o.remote, o.galaz, not o.bez_pobierania)
    if blad:
        pisz("BŁĄD: " + blad)
        return 2
    if o.wersja:
        wynik["wersja_szablonu"] = o.wersja
    if o.rekord:
        r = rekord(wynik, o.rekord, o.plan)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import wymiana
            b = wymiana.bledy(r)
        except ImportError:
            b = []
            pisz("UWAGA: brak scripts/wymiana.py obok – rekord nie został sprawdzony (sprawdź: wymiana.py sprawdz)")
        if b:
            pisz("ODRZUCONE:\n- " + "\n- ".join(b))
            return 2
        cel = o.wyjscie or os.path.join(tempfile.gettempdir(), "zgodnosc-%s.json" % o.rekord)
        with open(cel, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
            f.write("\n")
        pisz("REKORD: %s (%s %% zgodności, szablon %s)" % (cel, r["procent"], r["wersja_szablonu"]))
        pisz("Dalej: python3 -I scripts/wymiana.py wyslij %s --zakazane \"<nazwy firm i klientów>\"" % cel)
        return 0
    pisz(json.dumps(wynik, ensure_ascii=False, indent=1) if o.json else tabela(wynik))
    return 0


if __name__ == "__main__":
    sys.exit(main())
