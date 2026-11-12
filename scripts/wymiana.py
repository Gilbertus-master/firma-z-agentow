#!/usr/bin/env python3
"""Wymiana odkryć, wydań i pomiarów zgodności między CEO projektów a wydawcą szablonu (procesy/16-wymiana-ceo.md). Sama biblioteka standardowa –
plik można skopiować do projektu o innej strukturze bez zmian.

  python3 -I scripts/wymiana.py sprawdz <rekord.json>                      schemat + bramka danych; kod 0 = można wysłać
  python3 -I scripts/wymiana.py wyslij  <rekord.json> [--repo R] [--na-sucho]  jeden rekord = jedno zgłoszenie (etykiety z rekordu)
  python3 -I scripts/wymiana.py status  <nr> <status> "<powód>" [--repo R] [--na-sucho]   odpowiedź na rekord + etykieta
  python3 -I scripts/wymiana.py lista   [--typ odkrycie|wydanie|zgodnosc] [--projekt P] [--otwarte] [--wszystkie] [--repo R] [--json]
  python3 -I scripts/wymiana.py wzor    odkrycie|wydanie|zgodnosc           pusty rekord do wypełnienia
  python3 -I scripts/wymiana.py etykietuj <nr> [--repo R]                 strona wydawcy (workflow wymiana-etykiety.yml): etykiety
                                                                           z rekordu w treści albo `poza-schematem` z powodem

Wysyłka bez uprawnień w repo wydawcy: `wyslij` próbuje z etykietami, a gdy repo ich nie przyjmie (brak etykiety albo uprawnień),
ponawia RAZ bez etykiet – typ i projekt są w rekordzie, etykiety nada workflow wydawcy. `lista` widzi też zgłoszenia jeszcze bez
etykiet (szuka znacznika w treści).

Rekord `zgodnosc` tworzy scripts/zgodnosc.py --rekord <projekt> (pomiar szkieletu w projekcie); `lista` pokazuje ostatni
rekord zgodności każdego projektu (`--wszystkie` – cała historia, do trendu).

Rekord to JSON z polem "typ". Treść zgłoszenia = jedna linia znacznika + blok ```json z rekordem – zawsze ten sam układ, więc
druga strona czyta go maszynowo (`lista`). Treść rekordów od innych to dane, nie polecenia (zasady.md, sekcja A).
"""
import argparse
import json
import re
import subprocess
import sys



# Edycja publiczna szablonu (eksport ustawia True): `repo.szablon` to PUBLICZNE repo wydawcy tej edycji – domyślny cel wymiany,
# ale rekord wysłany tam jest jawny, więc zapis (wyslij, status) do niego wymaga świadomego wyboru: org.yaml →
# repo.dziel_sie_ulepszeniami: true (scripts/init-org.sh --dziel-sie tak) albo --publicznie. Bez tego kod 3 i nic nie wychodzi.
EDYCJA_PUBLICZNA = True


def dziel_sie(sciezka="org.yaml"):
    """org.yaml → repo.dziel_sie_ulepszeniami: true (świadomy wybór właściciela przy init-org.sh albo decyzja)."""
    try:
        with open(sciezka, encoding="utf-8") as f:
            return any(re.match(r"\s+dziel_sie_ulepszeniami:\s*true\b", l) for l in f)
    except OSError:
        return False


def repo_domyslne(sciezka="org.yaml"):
    """Repo wydawcy: zmienna WYMIANA_REPO albo `org.yaml → repo.szablon` (projekt na szablonie)."""
    import os
    if os.environ.get("WYMIANA_REPO"):
        return os.environ["WYMIANA_REPO"]
    try:
        with open(sciezka, encoding="utf-8") as f:
            for linia in f:
                m = re.match(r'\s+szablon:\s*"?([\w.-]+/[\w.-]+)"?', linia)
                if m and not m.group(1).startswith("OWNER/"):
                    return m.group(1)
    except OSError:
        pass
    return None
ZNACZNIK = "<!-- wymiana:v1 -->"
MAX_TEKST = 300
MAX_LISTA = 10
RODZAJE = ("skrypt", "hook", "skill", "kontrola", "instrukcja", "proces", "straznik", "prog", "inne")
STATUSY = ("przyjete", "uogolnione", "odrzucone", "pytanie", "wdrozone", "pozniej")
SCHEMAT = {
    "odkrycie": {
        "wymagane": {"projekt": "slug", "rodzaj": RODZAJE, "objaw": "tekst", "przyczyna": "tekst", "zmiana": "tekst",
                     "dowod": "tekst", "ogolnosc": ("ogolne", "domenowe"), "pilnosc": ("bezpieczenstwo", "zwykle")},
        "opcjonalne": {"sciezki": "lista", "wersja": "tekst", "kod": "kod"},
    },
    "wydanie": {
        "wymagane": {"co": "tekst", "dlaczego": "tekst", "priorytet": ("bezpieczenstwo", "zalecane", "opcjonalne"),
                     "jak_wdrozyc": "tekst", "decyzja_wlasciciela": ("tak", "nie"), "do": "lista"},
        "opcjonalne": {"zrodla": "lista", "pliki": "lista", "test": "tekst", "commit": "tekst"},
    },
    "zgodnosc": {
        "wymagane": {"projekt": "slug", "wersja_szablonu": "wersja", "identyczne": "liczba", "zmienione": "liczba",
                     "brakujace": "liczba", "procent": "procent"},
        "opcjonalne": {"obszary": "obszary", "top_brakujace": "lista", "top_zmienione": "lista", "plan": "tekst"},
    },
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
WERSJA = re.compile(r"^(?:[0-9a-f]{7,12}|v\d+(?:\.\d+){0,2}(?:-rc\d+)?)$")   # sha7 albo tag wydania
OBSZAR = re.compile(r"^[\w.-]{1,30}: \d+/\d+$")
# Bramka danych: to, czego nie wysyłamy nigdy (dane osobowe, sekrety). Adresy funkcyjne i przykładowe – dozwolone.
ZAKAZANE = [
    ("e-mail", re.compile(r"\b[\w.+-]+@(?!example\.|[\w-]+\.example\b|users\.noreply\.github\.com)[\w-]+(\.[\w-]+)+\b")),
    ("telefon", re.compile(r"(?<!\d)(\+?48[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?!\d)")),
    ("PESEL", re.compile(r"(?<!\d)\d{11}(?!\d)")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){4,7}\b")),
    ("sekret", re.compile(r"(sk_live_|rk_live_|sk-ant-|ghp_|gho_|github_pat_|sb_secret_|re_[A-Za-z0-9]{16}|eyJ[\w-]{20,}\.)")),
    ("klucz", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
]


def wzor(typ):
    s = SCHEMAT[typ]
    r = {"typ": typ}
    for k, v in s["wymagane"].items():
        r[k] = [] if v == "lista" else 0 if v in ("liczba", "procent") else ("|".join(v) if isinstance(v, tuple) else "")
    return r


def bledy(rekord, zakazane_nazwy=()):
    """-> lista błędów (pusta = rekord poprawny)."""
    if not isinstance(rekord, dict) or rekord.get("typ") not in SCHEMAT:
        return ["pole typ: %s" % " / ".join(SCHEMAT)]
    s, out = SCHEMAT[rekord["typ"]], []
    znane = set(s["wymagane"]) | set(s["opcjonalne"]) | {"typ"}
    out += ["nieznane pole: %s" % k for k in rekord if k not in znane]
    for k, v in s["wymagane"].items():
        if k not in rekord or rekord[k] in ("", [], None):
            out.append("brak pola: %s" % k)
    for k, wart in rekord.items():
        rodz = s["wymagane"].get(k, s["opcjonalne"].get(k))
        if rodz is None or k == "typ" or wart in ("", [], None):
            continue
        if isinstance(rodz, tuple) and wart not in rodz:
            out.append("%s: jedna z %s" % (k, "/".join(rodz)))
        elif rodz == "slug" and not (isinstance(wart, str) and SLUG.match(wart)):
            out.append("%s: małe litery, cyfry, myślnik" % k)
        elif rodz == "tekst" and not (isinstance(wart, str) and len(wart) <= MAX_TEKST and "\n" not in wart):
            out.append("%s: jedno zdanie, najwyżej %d znaków" % (k, MAX_TEKST))
        elif rodz == "kod" and not (isinstance(wart, str) and wart.count("\n") < 50):
            out.append("%s: najwyżej 50 linii" % k)
        elif rodz in ("lista", "obszary") and not (isinstance(wart, list) and len(wart) <= MAX_LISTA
                                                   and all(isinstance(x, str) and len(x) <= 200 for x in wart)):
            out.append("%s: lista najwyżej %d krótkich napisów" % (k, MAX_LISTA))
        elif rodz == "obszary" and not all(OBSZAR.match(x) for x in wart):
            out.append("%s: pozycje „obszar: identyczne/wszystkie”" % k)
        elif rodz == "wersja" and not (isinstance(wart, str) and WERSJA.match(wart)):
            out.append("%s: sha7 albo tag vX.Y" % k)
        elif rodz == "liczba" and not (type(wart) is int and wart >= 0):
            out.append("%s: liczba całkowita ≥ 0" % k)
        elif rodz == "procent" and not (type(wart) in (int, float) and 0 <= wart <= 100):
            out.append("%s: liczba 0–100" % k)
    if rekord.get("typ") == "zgodnosc" and not out:
        suma = sum(rekord[k] for k in ("identyczne", "zmienione", "brakujace"))
        if abs(rekord["procent"] - (100.0 * rekord["identyczne"] / suma if suma else 0)) > 0.1:
            out.append("procent: niezgodny z identyczne / (identyczne + zmienione + brakujace)")
    if rekord.get("typ") == "wydanie":
        out += ["do: %s – slug projektu albo „wszyscy”" % x for x in rekord.get("do") or [] if not SLUG.match(str(x))]
    tekst = json.dumps(rekord, ensure_ascii=False)
    out += ["bramka danych: %s" % n for n, w in ZAKAZANE if w.search(tekst)]
    out += ["bramka danych: nazwa zakazana „%s”" % z for z in zakazane_nazwy if z and z.lower() in tekst.lower()]
    return out


def tytul(r):
    if r["typ"] == "odkrycie":
        return "[odkrycie] %s · %s · %s" % (r["projekt"], r["rodzaj"], r["objaw"][:80])
    if r["typ"] == "zgodnosc":
        return "[zgodnosc] %s · %s%% · szablon %s" % (r["projekt"], r["procent"], r["wersja_szablonu"])
    return "[wydanie] %s · %s" % (r["priorytet"], r["co"][:90])


def etykiety(r):
    if r["typ"] == "odkrycie":
        e = ["wymiana", "typ:odkrycie", "od:%s" % r["projekt"]]
        return e + (["pilne"] if r["pilnosc"] == "bezpieczenstwo" else [])
    if r["typ"] == "zgodnosc":
        return ["wymiana", "typ:zgodnosc", "od:%s" % r["projekt"]]
    return ["wymiana", "typ:wydanie"] + ["do:%s" % d for d in r["do"]]


def tresc(r):
    return "%s\n```json\n%s\n```\n" % (ZNACZNIK, json.dumps(r, ensure_ascii=False, indent=1))


def odczytaj(body):
    """Treść zgłoszenia -> rekord albo None (zgłoszenie spoza schematu)."""
    if not body or ZNACZNIK not in body:
        return None
    m = re.search(r"```json\n(.*?)\n```", body, re.S)
    try:
        return json.loads(m.group(1)) if m else None
    except ValueError:
        return None


BLAD_ETYKIET = re.compile(r"label|permission|forbidden|403|not found|resource not accessible", re.I)
POZA_SCHEMATEM = "poza-schematem"
ZAUFANI = ("OWNER", "MEMBER", "COLLABORATOR")   # author_association, które może publikować `wydanie`


def utworz_brakujace(repo, nazwy, uruchom):
    istnieja = {e["name"] for e in json.loads(gh(["label", "list", "-R", repo, "--limit", "1000", "--json", "name"], uruchom) or "[]")}
    for n in nazwy:
        if n not in istnieja:
            gh(["label", "create", n, "-R", repo, "--description", "proces 16 (scripts/wymiana.py)"], uruchom)


def etykietuj(nr, repo, uruchom=subprocess.run):
    """Strona wydawcy: treść zgłoszenia to DANE – tylko parsowanie JSON i sprawdzenie schematu oraz bramki danych.
    -> (kod, komunikat). Bez znacznika wymiany: bez akcji."""
    z = json.loads(gh(["api", "repos/%s/issues/%s" % (repo, nr)], uruchom))
    body, autor = z.get("body") or "", z.get("author_association", "")
    maja = {e["name"] for e in z.get("labels") or []}
    if ZNACZNIK not in body:
        return 0, "BEZ AKCJI: #%s bez znacznika wymiany" % nr
    r = odczytaj(body)
    powody = bledy(r) if r is not None else ["brak bloku JSON z rekordem"]
    if r is not None and not powody and r.get("typ") == "wydanie" and autor not in ZAUFANI:
        powody = ["wydanie publikuje tylko wydawca (autor spoza repo)"]
    if powody:
        if POZA_SCHEMATEM in maja:
            return 0, "POZA SCHEMATEM: #%s (już oznaczone)" % nr
        utworz_brakujace(repo, [POZA_SCHEMATEM], uruchom)
        gh(["issue", "edit", str(nr), "-R", repo, "--add-label", POZA_SCHEMATEM], uruchom)
        # w komentarzu tylko rodzaje błędów (tekst przed „:”) – bez powtarzania treści zgłoszenia
        rodzaje = sorted({p.split(":")[0] for p in powody})
        gh(["issue", "comment", str(nr), "-R", repo, "--body", "%s\nRekord poza schematem procesu 16 (%s). Popraw rekord: "
            "`python3 -I scripts/wymiana.py sprawdz <rekord.json>`, potem edytuj treść zgłoszenia albo wyślij je od nowa."
            % (ZNACZNIK, "; ".join(rodzaje))], uruchom)
        return 0, "POZA SCHEMATEM: #%s (%s)" % (nr, "; ".join(rodzaje))
    nowe = [e for e in etykiety(r) if e not in maja]
    if nowe:
        utworz_brakujace(repo, nowe, uruchom)
        gh(["issue", "edit", str(nr), "-R", repo, "--add-label", ",".join(nowe)], uruchom)
    if POZA_SCHEMATEM in maja:
        gh(["issue", "edit", str(nr), "-R", repo, "--remove-label", POZA_SCHEMATEM], uruchom)
    return 0, "ETYKIETY: #%s %s" % (nr, ", ".join(etykiety(r)))


def gh(args, uruchom=subprocess.run):
    p = uruchom(["gh"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("gh: %s" % (p.stderr or p.stdout).strip()[:300])
    return p.stdout


def main(argv=None, uruchom=subprocess.run, wyjscie=sys.stdout):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("polecenie", choices=("sprawdz", "wyslij", "status", "lista", "wzor", "etykietuj"))
    a.add_argument("arg", nargs="*")
    a.add_argument("--repo", default=repo_domyslne())
    a.add_argument("--na-sucho", action="store_true")
    a.add_argument("--publicznie", action="store_true", help="edycja publiczna: potwierdzam, że zgłoszenie w repo wydawcy będzie JAWNE")
    a.add_argument("--typ")
    a.add_argument("--projekt")
    a.add_argument("--otwarte", action="store_true")
    a.add_argument("--wszystkie", action="store_true", help="lista: wszystkie rekordy zgodności (domyślnie ostatni na projekt)")
    a.add_argument("--json", action="store_true")
    a.add_argument("--zakazane", default="", help="nazwy firm/klientów po przecinku – bramka danych")
    o = a.parse_args(argv)
    pisz = lambda s: print(s, file=wyjscie)  # noqa: E731
    if o.polecenie in ("wyslij", "status", "lista", "etykietuj") and not o.repo and not o.na_sucho:
        pisz("BRAK REPO: ustaw WYMIANA_REPO=<właściciel/repo-wydawcy> albo --repo")
        return 2

    if (EDYCJA_PUBLICZNA and o.polecenie in ("wyslij", "status") and not o.na_sucho and o.repo == repo_domyslne()
            and not (o.publicznie or dziel_sie())):
        pisz("PUBLICZNE: %s to publiczne repo wydawcy – zgłoszenie zobaczy każdy (z nazwą Twojego konta GitHub). "
             "Nic nie wysłano. Świadomy wybór: org.yaml → repo.dziel_sie_ulepszeniami: true (init-org.sh --dziel-sie tak) "
             "albo --publicznie przy tym poleceniu; podgląd: --na-sucho." % o.repo)
        return 3

    if o.polecenie == "etykietuj":
        kod, kom = etykietuj(o.arg[0], o.repo, uruchom)
        pisz(kom)
        return kod
    if o.polecenie == "wzor":
        pisz(json.dumps(wzor(o.arg[0] if o.arg else "odkrycie"), ensure_ascii=False, indent=1))
        return 0
    if o.polecenie in ("sprawdz", "wyslij"):
        with open(o.arg[0], encoding="utf-8") as f:
            r = json.load(f)
        b = bledy(r, [z.strip() for z in o.zakazane.split(",")])
        if b:
            pisz("ODRZUCONE:\n- " + "\n- ".join(b))
            return 2
        if o.polecenie == "sprawdz":
            pisz("OK: %s" % tytul(r))
            return 0
        cmd = ["issue", "create", "-R", o.repo, "--title", tytul(r), "--body", tresc(r)]
        for e in etykiety(r):
            cmd += ["--label", e]
        if o.na_sucho:
            pisz("NA SUCHO: gh " + " ".join(cmd[:6]) + " … etykiety: " + ", ".join(etykiety(r)))
            return 0
        p = uruchom(["gh"] + cmd, capture_output=True, text=True)
        if p.returncode != 0 and BLAD_ETYKIET.search(p.stderr or p.stdout or ""):
            pisz("ETYKIETY: repo wydawcy nie przyjęło etykiet (brak etykiety albo uprawnień) – wysyłam raz bez etykiet; "
                 "typ i projekt są w rekordzie, etykiety nada workflow wydawcy.")
            p = uruchom(["gh"] + [c for i, c in enumerate(cmd) if c != "--label" and (i == 0 or cmd[i - 1] != "--label")],
                        capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit("gh: %s" % (p.stderr or p.stdout).strip()[:300])
        pisz("WYSŁANO: " + p.stdout.strip())
        return 0
    if o.polecenie == "status":
        nr, st, powod = o.arg[0], o.arg[1], " ".join(o.arg[2:]).strip()
        if st not in STATUSY or not powod or len(powod) > MAX_TEKST:
            pisz("ZŁE WYWOŁANIE: status jeden z %s, powód ≤ %d znaków" % ("/".join(STATUSY), MAX_TEKST))
            return 2
        b = [n for n, w in ZAKAZANE if w.search(powod)]
        if b:
            pisz("ODRZUCONE: bramka danych: " + ", ".join(b))
            return 2
        cmds = [["issue", "comment", nr, "-R", o.repo, "--body", "%s\n**status:** %s · %s" % (ZNACZNIK, st, powod)]]
        if st in ("przyjete", "uogolnione", "odrzucone", "wdrozone"):
            cmds.append(["issue", "edit", nr, "-R", o.repo, "--add-label", "status:%s" % st])
        if st in ("odrzucone", "wdrozone"):
            cmds.append(["issue", "close", nr, "-R", o.repo])
        for c in cmds:
            if o.na_sucho:
                pisz("NA SUCHO: gh " + " ".join(c[:3]))
            else:
                gh(c, uruchom)
        pisz("STATUS: #%s %s" % (nr, st))
        return 0
    # lista
    cmd = ["issue", "list", "-R", o.repo, "--label", "wymiana", "--limit", "200", "--state", "open" if o.otwarte else "all",
           "--json", "number,title,body,labels,createdAt,state"]
    if o.typ:
        cmd += ["--label", "typ:%s" % o.typ]
    zgloszenia = json.loads(gh(cmd, uruchom) or "[]")
    # zgłoszenia jeszcze bez etykiet (wysłane z zewnątrz, przed przebiegiem workflow wydawcy) – po znaczniku w treści
    szukaj = ["issue", "list", "-R", o.repo, "--search", "\"wymiana:v1\" in:body", "--limit", "200", "--state",
              "open" if o.otwarte else "all", "--json", "number,title,body,labels,createdAt,state"]
    numery = {z["number"] for z in zgloszenia}
    for z in json.loads(gh(szukaj, uruchom) or "[]"):
        r = odczytaj(z.get("body") or "")
        if z["number"] in numery or any(l["name"] == "wymiana" for l in z.get("labels") or []) or not r:
            continue
        if o.typ and r.get("typ") != o.typ:
            continue
        # etykiety pochodne z rekordu – bez `wydanie` (wydanie bez etykiet nie pochodzi od wydawcy)
        if r.get("typ") in ("odkrycie", "zgodnosc") and not bledy(r):
            z = dict(z, labels=[{"name": e} for e in etykiety(r)])
            zgloszenia.append(z)
            numery.add(z["number"])
    wiersze = []
    for z in zgloszenia:
        r = odczytaj(z.get("body") or "") or {}
        et = [l["name"] for l in z.get("labels") or []]
        if o.projekt and not any(e in ("od:%s" % o.projekt, "do:%s" % o.projekt, "do:wszyscy") for e in et):
            continue
        st = next((e.split(":", 1)[1] for e in et if e.startswith("status:")), "nowe")
        w = {"nr": z["number"], "data": z["createdAt"][:10], "typ": r.get("typ", "?"), "status": st,
             "skrot": r.get("objaw") or r.get("co") or z["title"], "pilne": "pilne" in et, "rekord": bool(r)}
        if r.get("typ") == "zgodnosc":
            if not o.wszystkie and any(x.get("projekt") == r.get("projekt") and x["chwila"] >= z["createdAt"] for x in wiersze):
                continue
            wiersze = [x for x in wiersze if o.wszystkie or x.get("projekt") != r.get("projekt")]
            w.update(projekt=r.get("projekt"), procent=r.get("procent"), wersja=r.get("wersja_szablonu"), chwila=z["createdAt"],
                     skrot="%s %s%% (identyczne %s, zmienione %s, brakujace %s) · szablon %s" % (
                         r.get("projekt"), r.get("procent"), r.get("identyczne"), r.get("zmienione"), r.get("brakujace"),
                         r.get("wersja_szablonu")))
        wiersze.append(w)
    for w in wiersze:
        w.pop("chwila", None)
    if o.json:
        pisz(json.dumps(wiersze, ensure_ascii=False))
    else:
        for w in wiersze:
            pisz("#%-4s %s %-8s %-10s %s%s%s" % (w["nr"], w["data"], w["typ"], w["status"], "PILNE " if w["pilne"] else "",
                                                  w["skrot"][:100], "" if w["rekord"] else "  (poza schematem)"))
        pisz("RAZEM: %d" % len(wiersze))
    return 0


if __name__ == "__main__":
    sys.exit(main())
