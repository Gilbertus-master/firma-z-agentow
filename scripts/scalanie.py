#!/usr/bin/env python3
"""Kolejka scalania – fakty i klasa dla każdego otwartego PR-a. Sama biblioteka standardowa (działa pod `python3 -I`).

Skrypt NIGDY nie scala i niczego nie zmienia w GitHubie. Liczy klasę wiersza, pisze zlecenia i własny stan; scala agent
(zadanie `scalanie`, co 15 min) – wyłącznie wiersze GOTOWY, wyłącznie poleceniem wypisanym w tabeli. Klasy agent nie zmienia.

  python3 -I scripts/scalanie.py [tabela] [--json] [--wszystko]   tabela otwartych PR-ów + ostatnia linia REZERWA_CEO
  python3 -I scripts/scalanie.py blokada <kto> [--protokol N]    blokada + prywatny katalog roboczy na świeżej gałęzi głównej
                                                                 -> „BLOKADA wzięta TOKEN=<token>” i „KATALOG=<ścieżka>”
  python3 -I scripts/scalanie.py odswiez <token>                 przed długą czynnością
  python3 -I scripts/scalanie.py odblokuj <token>                zawsze na końcu

Zapisy stanu – tylko z tokenem blokady i tylko z katalogu KATALOG (inaczej kod 2, 10 albo 11):
  … potwierdz <klucz> [--kto X] --token T      sprawdza stan MERGED i dopisuje linię do dziennika scaleń
  … przepiecie <klucz> --token T               zapis listy plików PRZED zmianą bazy PR-a na główną
  … odnotuj <klucz> <KLASA> --token T          własna czynność wykonana (PRZEPNIJ, BRAK_CI) – bez zlecenia
  … zglos --token T                            zlecenia dla wszystkich wierszy do zgłoszenia (raz na head i klasę)
  … zglos <klucz> <KLASA> --powod "…" --token T   własna czynność nieudana -> pilne zlecenie dla CEO
  … zapisz --token T                           commit własnych plików na świeżej gałęzi głównej + push (do 3 prób;
                                               bez rebase i bez --force: zapisy są odtwarzane z kolejki oczekujących)

Decyzje CEO i odczyt:
  python3 -I scripts/scalanie.py wstrzymaj <klucz> "powód" [--head]   tylko CEO; domyślnie do odwołania
  python3 -I scripts/scalanie.py zwolnij <klucz> "uzasadnienie"       tylko CEO
  python3 -I scripts/scalanie.py miary [--dni N]                      czas werdykt → scalenie, progi kolejki
  python3 -I scripts/scalanie.py bramka "<polecenie gh pr merge …>"   czy to scalenie wolno wykonać (to samo sprawdza hook)

Opcje wspólne: --repo DIR (domyślnie katalog nad scripts/), --teraz ISO (testy).
Kody: 0 dobrze · 1 błąd albo „nie scalony” · 2 złe wywołanie · 10 blokada zajęta / brak blokady · 11 blokada nie twoja ·
12 błąd systemu plików · 13 niezgodny protokół (podmień razem treść zadania i skrypt; blokady nie wzięto) ·
14 flota zatrzymana plikiem bezpieczenstwo/HALT (blokady nie wzięto; plik usuwa operator).
Zasada: fałszywe „nie scalaj” kosztuje kwadrans, fałszywe „scalaj” – produkcję. Wątpliwość = wpis dla recenzenta albo CEO.
Granice: blokada i tętno są lokalne dla maszyny. Przy przebiegach z wielu maszyn wyłączność daje GitHub (scalenie
z --match-head-commit udaje się raz), a stan w repo jest idempotentny (zgłoszenie raz na head i klasę).
Ustawienia: ceo/scalanie/ustawienia.yaml · progi: ceo/kontrole/progi.yaml · opis: ceo/scalanie/README.md.
"""
import datetime as dt
import fnmatch
import json
import os
import pathlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

PROTOKOL = 1   # wersja umowy między tym skryptem a treścią zadania `scalanie`; zmiana kroków = +1 tu, w ustawieniach i w treści
PROGI_DOMYSLNE = {"pr_bez_werdyktu_min": 60, "gotowy_rezerwa_ceo_min": 45, "blokada_scalania_min": 30, "brak_ci_eskalacja_min": 30,
                  "zlecenie_scalania_termin_h": 4, "pliki_sporne_min_pr": 3, "werdykt_ok_niescalony_h": 2,
                  "werdykt_ok_niescalony_max": 3, "pr_konflikty_max": 3}
UST_DOMYSLNE = {"protokol": 1, "galaz_glowna": "main", "metoda": "merge", "ci_wymagane": True, "stop_gdy_glowna_czerwona": True,
                "bez_ci": [], "wyjatki": [".github/"], "reguly": [], "migracje": ["migrations/", "*/migrations/*"], "etykiety_stop": [],
                "wlasciciel": ["zasady.md", "uprawnienia.yaml", ".claude/", "polityki/"]}   # w repo organizacji: scalenie tylko z decyzją właściciela
UST_TAK_NIE = ("ci_wymagane", "stop_gdy_glowna_czerwona")
POLA = "number,title,body,baseRefName,headRefName,headRefOid,mergeable,statusCheckRollup,files,changedFiles,isDraft,createdAt,labels"

SCALA = ("GOTOWY",)
WLASNE = ("PRZEPNIJ", "BRAK_CI")                                   # czynność agenta w GitHubie, bez zlecenia
ADRESAT = {"KONFLIKT": "autor", "CI_CZERWONE": "autor", "KOLIZJA_MIGRACJI": "autor",
           "NOWY_HEAD": "recenzent", "BRAK_WERDYKTU": "recenzent", "NIEJASNY": "recenzent", "PO_PRZEPIECIU": "recenzent",
           "WARUNEK": "ceo", "MIGRACJA": "ceo", "WYJATEK": "ceo", "DECYZJA": "ceo", "DO_ZWOLNIENIA": "ceo", "GLOWNA_CZERWONA": "ceo",
           "REJESTR": "ceo"}
DO_ZROBIENIA = SCALA + WLASNE + tuple(ADRESAT)
BEZ_RUCHU = ("CZEKA_NA_RODZICA", "ZALEZNOSC", "CI_TRWA", "NIE_SCALAC", "WSTRZYMANY", "SZKIC", "SWIEZY", "CZEKA_NA_GLOWNA", "NIEZNANY")
KLASY = DO_ZROBIENIA + BEZ_RUCHU
PILNE = ("GLOWNA_CZERWONA", "REJESTR")                             # wpis z dopiskiem PILNE: stoi cała kolejka (oraz każda nieudana czynność agenta)
WLASNE_PLIKI = ("ceo/scalanie/stan.json", "ceo/scalanie/dziennik.jsonl")   # + zlecenia/<adresat>.md – jedyne pliki, które skrypt zapisuje

CI_ZLE = ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE")
CI_DOBRE = ("SUCCESS", "NEUTRAL", "SKIPPED")
GLOWNA_ZLE = ("FAILURE", "ERROR", "TIMED_OUT", "STARTUP_FAILURE")  # anulowany bieg na głównej nie zatrzymuje kolejki
RE_KLUCZ = re.compile(r"^(?:([\w.-]+)#)?(\d+)$")
RE_TOKEN = re.compile(r"^[0-9a-f]{16}$")
RE_KTO = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
RE_PO = re.compile(r"^po\s+(?:([\w.-]+(?:/[\w.-]+)?)#|#)?(\d+)$", re.I)
# warunek maszynowy „zielony <check> na head” – cały warunek musi pasować (fullmatch); nazwa ze spacjami w `…`
RE_CHECK = re.compile(r"zielony\s+(?:`([^`\n]{1,100})`|([\w./:-]{1,100}))\s+na\s+head", re.I)
RE_STOP = re.compile(r"nie\s+scala[ćc]|do\s+not\s+merge|\bDNM\b|\bWIP\b|czeka\s+na\s+decyzj|wymaga\s+zgody|bez\s+zgody", re.I)
RE_STOP_TRESC = re.compile(r"nie\s+scala[ćc]|do\s+not\s+merge|czeka\s+na\s+decyzj", re.I)   # opis PR-a: tylko jednoznaczne zwroty
RE_BRAK_PR = re.compile(r"could not resolve|not found|no pull requests", re.I)
RE_CZLOWIEK = re.compile(r"nie\s+recenzowa[ćc]", re.I)
RE_AUTOR = re.compile(r"^agent/([a-z0-9]+)-")
RE_WERSJA = re.compile(r"^(\d{3,14})")

TEKSTY = {  # klasa -> (temat, „Zrobione gdy”, treść); {…} uzupełnia wpis_zlecenia()
    "KONFLIKT": ("rozwiąż konflikt z gałęzią główną", "PR ma stan MERGEABLE dla nowego head i zielone CI",
                 "PR ma konflikt z gałęzią główną. Kolejka scalania konfliktów nie rozwiązuje. Jeśli autor wypchnął już nowszy commit – pomiń."),
    "CI_CZERWONE": ("napraw czerwone CI", "wszystkie checki PR-a zielone dla nowego head",
                    "CI nie przechodzi dla head, który recenzent zatwierdził. Jeśli autor wypchnął już nowszy commit – pomiń."),
    "KOLIZJA_MIGRACJI": ("zmień numer migracji", "numer migracji w PR-ze jest wolny na gałęzi głównej i w starszych otwartych PR-ach",
                         "Numer migracji z tego PR-a jest już zajęty. Po zmianie numeru PR wraca do recenzji (nowy head)."),
    "NOWY_HEAD": ("zrecenzuj nowy head", "w recenzent/stan.json jest werdykt z polami maszynowymi dla aktualnego head",
                  "Werdykt dotyczy innego commita niż aktualny head PR-a (albo jego sha ma mniej niż 7 znaków)."),
    "BRAK_WERDYKTU": ("PR czeka na werdykt", "w recenzent/stan.json jest werdykt z polami maszynowymi dla aktualnego head",
                      "PR nie ma werdyktu dłużej, niż pozwala próg pr_bez_werdyktu_min."),
    "NIEJASNY": ("uzupełnij pola maszynowe werdyktu", "werdykt ma pola scalenie / warunki / kroki (i klasa_migracji przy migracjach) spójne z wynikiem",
                 "Kolejka nie umie odczytać z werdyktu, czy wolno scalić. Wystarczy dopisać pola – bez nowej recenzji, jeśli werdykt się nie zmienia."),
    "PO_PRZEPIECIU": ("potwierdź recenzję po zmianie bazy", "werdykt ma pole po_przepieciu: true albo jest nowy werdykt dla diffu względem gałęzi głównej",
                      "Po zmianie bazy na główną lista plików PR-a jest inna niż ta, którą widziała recenzja."),
    "WARUNEK": ("werdykt z warunkiem – decyzja", "PR scalony przez CEO pod blokadą, wstrzymany poleceniem wstrzymaj albo zamknięty",
                "Werdykt pozwala scalić tylko po spełnieniu warunku albo wykonaniu kroków. Agent scalający warunków nie ocenia."),
    "MIGRACJA": ("PR z migracją – scalenie i kroki", "migracja zastosowana według kroków z recenzji i PR scalony albo PR wstrzymany",
                 "PR zawiera migrację bazy. Scalenie i zastosowanie należą do CEO (uprawnienia.yaml: migracja_zgodna_wstecz); klasa B i brak klasy – decyzja właściciela."),
    "WYJATEK": ("PR dotyka ścieżek wyłączonych", "PR scalony przez CEO albo człowieka, wstrzymany albo zamknięty",
                "PR zmienia pliki z listy wyjątków albo pliki reguł organizacji. Agent scalający takich PR-ów nie scala."),
    "DECYZJA": ("PR oznaczony jako czekający na decyzję", "znacznik zdjęty i PR scalony albo PR wstrzymany poleceniem wstrzymaj",
                "PR ma werdykt pozwalający scalić, ale tytuł, opis albo etykieta mówią, żeby nie scalać."),
    "DO_ZWOLNIENIA": ("wstrzymany PR ma nowy head z werdyktem", "zwolnij z uzasadnieniem albo wstrzymaj ponownie dla nowego head",
                      "PR wstrzymany do odwołania dostał nowy commit z werdyktem pozwalającym scalić. Wstrzymanie zdejmuje tylko CEO."),
    "GOTOWY": ("scalenie odrzucone przez GitHub", "PR scalony albo przyczyna odmowy usunięta",
               "Polecenie scalenia z tabeli nie przeszło. Niczego nie wymuszono."),
    "PRZEPNIJ": ("zmiana bazy PR-a nie powiodła się", "PR ma bazę główną i uruchomione CI",
                 "Rodzic został scalony, ale zmiana bazy albo ponowne otwarcie PR-a nie powiodły się. Nie ponawiano."),
    "BRAK_CI": ("CI nie startuje", "PR ma komplet checków dla aktualnego head",
                "PR nie ma żadnego checku mimo jednego ponowienia (zamknięcie i otwarcie)."),
    "GLOWNA_CZERWONA": ("CI gałęzi głównej czerwone – kolejka scalania stoi", "ostatni commit gałęzi głównej ma zielone CI albo "
                        "stop_gdy_glowna_czerwona: nie w ceo/scalanie/ustawienia.yaml z wierszem w ceo/wiedza/zmiany-instrukcji.md",
                        "Ostatni commit gałęzi głównej ma czerwone CI. Kolejka nie dokłada zmian na zepsutą gałąź: gotowe PR-y tego "
                        "repozytorium czekają. Zleć naprawę autorowi ostatniego scalenia albo ponów CI, jeśli test jest niestabilny."),
    "REJESTR": ("rejestr wstrzymań nieczytelny – kolejka scalania stoi", "ceo/scalanie/wstrzymane.json na gałęzi głównej jest poprawnym "
                "JSON-em z kluczem wstrzymane (słownik)",
                "Kolejka nie umie odczytać rejestru wstrzymań CEO, więc nie wie, których PR-ów nie wolno scalić. Do naprawy pliku "
                "nie scala niczego. Napraw plik ręcznie (ostatnia dobra wersja: git log -- ceo/scalanie/wstrzymane.json)."),
}


# ---------- konfiguracja ----------

def org(repo):
    """org.yaml bez PyYAML -> strefa, prefiks, repo.github, repo.produkt (lista)."""
    wyn = {"strefa": "Europe/Warsaw", "prefiks": "org", "github": "", "produkt": []}
    p = repo / "org.yaml"
    if not p.exists():
        return wyn
    sekcja, w_produkt = "", False
    for l in p.read_text(encoding="utf-8").splitlines():
        bez = "" if l.lstrip().startswith("#") else re.split(r"\s+#", l, maxsplit=1)[0].rstrip()
        if not bez.strip():
            continue
        if re.match(r"^\S", bez):
            m = re.match(r"^(\w+)\s*:\s*$", bez)
            sekcja, w_produkt = (m.group(1) if m else ""), False
            continue
        if w_produkt:
            e = re.match(r"^\s+-\s*[\"']?([^\"'\s]+)", bez)
            if e:
                wyn["produkt"].append(e.group(1))
                continue
            w_produkt = False
        k = re.match(r"^\s{2}(\w+)\s*:\s*(.*)$", bez)
        if not k:
            continue
        klucz_, wart = k.group(1), k.group(2).strip()
        if sekcja == "organizacja" and klucz_ in ("strefa", "prefiks"):
            wyn[klucz_] = wart.strip("\"'") or wyn[klucz_]
        elif sekcja == "repo" and klucz_ == "github":
            wyn["github"] = wart.strip("\"'")
        elif sekcja == "repo" and klucz_ == "produkt":
            if wart.startswith("["):
                wyn["produkt"] = [x.strip().strip("\"'") for x in wart.strip("[]").split(",") if x.strip().strip("\"'")]
            elif not wart:
                w_produkt = True
    return wyn


def repozytoria(repo):
    """Repozytoria z PR-ami: repo.produkt, potem repo.github; bez placeholderów OWNER/…. Pierwsze ma klucz = goły numer."""
    o = org(repo)
    wyn = []
    for r in o["produkt"] + [o["github"]]:
        if r and "/" in r and not r.startswith("OWNER/") and r not in wyn:
            wyn.append(r)
    return wyn


def progi(repo):
    wyn = dict(PROGI_DOMYSLNE)
    p = repo / "ceo/kontrole/progi.yaml"
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([a-z_0-9]+)\s*:\s*(-?\d+(?:[.,]\d+)?)\s*(#.*)?$", l)
            if m:
                x = float(m.group(2).replace(",", "."))
                wyn[m.group(1)] = int(x) if x == int(x) else x
    return wyn


def _ustawienia_z(tekst):
    """Treść ustawień: `klucz: wartość` i `klucz:` + `  - "wzorzec"`; brak treści albo klucza = wartości domyślne."""
    wyn = {k: (list(v) if isinstance(v, list) else v) for k, v in UST_DOMYSLNE.items()}
    if tekst is None:
        return wyn
    lista = None
    for l in tekst.splitlines():
        bez = "" if l.lstrip().startswith("#") else re.split(r"\s+#", l, maxsplit=1)[0].rstrip()
        if not bez.strip():
            continue
        e = re.match(r"^\s+-\s*[\"']?(.*?)[\"']?\s*$", bez)
        if e and lista is not None:
            if e.group(1):
                wyn[lista].append(e.group(1))
            continue
        k = re.match(r"^(\w+)\s*:\s*(.*)$", bez)
        if not k:
            continue
        klucz_, wart = k.group(1), k.group(2).strip().strip("\"'")
        if not wart:
            lista = klucz_
            wyn[klucz_] = []
            continue
        lista = None
        if klucz_ == "protokol":
            wyn[klucz_] = int(wart) if wart.isdigit() else wart
        elif klucz_ in UST_TAK_NIE:
            wyn[klucz_] = wart.lower() in ("tak", "true", "1", "yes")
        else:
            wyn[klucz_] = wart
    for k, v in UST_DOMYSLNE.items():
        if isinstance(v, list) and not isinstance(wyn.get(k), list):
            wyn[k] = list(v)
    if wyn.get("metoda") not in ("merge", "squash", "rebase"):
        wyn["metoda"] = "merge"
    if not re.match(r"^[\w./-]+$", str(wyn.get("galaz_glowna", ""))):
        wyn["galaz_glowna"] = "main"
    return wyn


def ustawienia(repo):
    """ceo/scalanie/ustawienia.yaml z katalogu, w którym działa skrypt; brak albo nieczytelny plik = wartości domyślne."""
    try:
        return _ustawienia_z((pathlib.Path(repo) / "ceo/scalanie/ustawienia.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return _ustawienia_z(None)


def ustawienia_uzgodnione(repo):
    """Ustawienia z gałęzi głównej (wersja, którą przyjęła organizacja); dopiero gdy jej tam nie ma – z katalogu.
    Bramka scalania czyta właśnie te: lokalna, niewypchnięta zmiana listy wyjątków niczego nie otwiera."""
    lokalne = ustawienia(repo)
    tekst = z_glownej(repo, "ceo/scalanie/ustawienia.yaml", lokalne)
    return _ustawienia_z(tekst) if tekst is not None else lokalne


def teraz_org(repo, arg=None):
    """-> czas naiwny w strefie organizacji."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(org(repo)["strefa"])
    except Exception:
        tz = None
    if arg:
        t = dt.datetime.fromisoformat(arg.strip().replace("Z", "+00:00"))
        if t.tzinfo is not None:
            t = t.astimezone(tz) if tz else t.astimezone()
        return t.replace(tzinfo=None)
    return (dt.datetime.now(tz) if tz else dt.datetime.now()).replace(tzinfo=None, microsecond=0)


def czas_gh(s, repo):
    """Czas z GitHuba (UTC) -> naiwny w strefie organizacji; pusty albo nieczytelny -> None."""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return teraz_org(repo, s)
    except (ValueError, AttributeError, TypeError):
        return None


def czas_werdyktu(w):
    """`kiedy` (RRRR-MM-DD GG:MM) albo `data` (RRRR-MM-DD, liczona od 00:00) -> (czas, czy_dokladny)."""
    for pole, wzor, dokl in (("kiedy", "%Y-%m-%d %H:%M", True), ("data", "%Y-%m-%d", False)):
        try:
            return dt.datetime.strptime(str(w.get(pole, "")).strip()[:16 if dokl else 10], wzor), dokl
        except ValueError:
            continue
    return None, False


# ---------- git i gh ----------

TERMIN = None   # ustawia bramka scalania: chwila (time.monotonic), po której żadne polecenie już nie rusza


def uruchom(polecenie, cwd=None, timeout=60):
    if TERMIN is not None:
        zostalo = TERMIN - time.monotonic()
        if zostalo <= 0:
            return 1, "", "Termin"
        timeout = min(timeout, zostalo)
    try:
        p = subprocess.run(polecenie, capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", e.__class__.__name__
    return p.returncode, p.stdout, p.stderr


def gh(*a, timeout=60):
    return uruchom(["gh"] + list(a), timeout=timeout)


def git(repo, *a, timeout=60):
    return uruchom(["git", "-C", str(repo)] + list(a), timeout=timeout)


def json_z(tekst, domyslne):
    try:
        d = json.loads(tekst or "")
    except ValueError:
        return domyslne
    return d if isinstance(d, type(domyslne)) else domyslne


def z_glownej(repo, sciezka, ust):
    """Treść pliku z origin/<główna> (stan uzgodniony z flotą); brak -> None."""
    kod, out, _ = git(repo, "show", "origin/%s:%s" % (ust["galaz_glowna"], sciezka))
    return out if kod == 0 else None


def lokalny(repo, sciezka):
    try:
        return (repo / sciezka).read_text(encoding="utf-8")
    except OSError:
        return None


def werdykty(repo, ust):
    """recenzent/stan.json → recenzje: z origin/<główna>, a gdy brak – z pliku lokalnego. Brak pliku = brak werdyktów."""
    for tekst in (z_glownej(repo, "recenzent/stan.json", ust), lokalny(repo, "recenzent/stan.json")):
        if tekst:
            rec = json_z(tekst, {}).get("recenzje")
            if isinstance(rec, dict):
                return rec
    return {}


def stan(repo):
    d = json_z(lokalny(repo, "ceo/scalanie/stan.json"), {})
    return {"zgloszone": d.get("zgloszone") if isinstance(d.get("zgloszone"), dict) else {},
            "przepiete": d.get("przepiete") if isinstance(d.get("przepiete"), dict) else {}}


def wstrzymane(repo, ust):
    """Suma wstrzymań z pliku lokalnego i z origin/<główna> – wstrzymanie zapisane gdziekolwiek obowiązuje."""
    wyn = {}
    for tekst in (z_glownej(repo, "ceo/scalanie/wstrzymane.json", ust), lokalny(repo, "ceo/scalanie/wstrzymane.json")):
        w = json_z(tekst, {}).get("wstrzymane")
        if isinstance(w, dict):
            wyn.update({k: v for k, v in w.items() if isinstance(v, dict)})
    return wyn


def rejestr_nieczytelny(repo, ust):
    """True, gdy ceo/scalanie/wstrzymane.json istnieje (na origin/<główna> albo lokalnie), ale nie da się go odczytać.
    Brak pliku w obu miejscach to brak wstrzymań, nie błąd."""
    for tekst in (z_glownej(repo, "ceo/scalanie/wstrzymane.json", ust), lokalny(repo, "ceo/scalanie/wstrzymane.json")):
        if tekst is None:
            continue
        try:
            d = json.loads(tekst)
        except ValueError:
            return True
        if not isinstance(d, dict) or not isinstance(d.get("wstrzymane"), dict) \
                or any(not isinstance(v, dict) for v in d["wstrzymane"].values()):
            return True
    return False


def klucz(repo_gh, nr, repa):
    return str(nr) if repa and repo_gh == repa[0] else "%s#%s" % (repo_gh.split("/")[-1], nr)


def z_klucza(k, repa):
    """klucz -> (owner/repo, numer) albo None."""
    m = RE_KLUCZ.match(k or "")
    if not m or not repa:
        return None
    if not m.group(1):
        return repa[0], m.group(2)
    for r in repa[1:]:
        if r.split("/")[-1] == m.group(1):
            return r, m.group(2)
    return None


def stan_pr(repo_gh, nr):
    """-> OPEN | MERGED | CLOSED | BRAK (takiego PR-a nie ma) | None (GitHub nie odpowiedział – nie wiadomo)."""
    kod, out, err = gh("pr", "view", str(nr), "-R", repo_gh, "--json", "state")
    if kod != 0:
        return "BRAK" if RE_BRAK_PR.search(err or "") else None
    return json_z(out, {}).get("state") or None


def stan_galezi(repo_gh, galaz):
    """Stan PR-a, którego gałęzią źródłową jest `galaz`: OPEN | MERGED | CLOSED | BRAK | None (nie wiadomo)."""
    kod, out, _ = gh("pr", "list", "-R", repo_gh, "--state", "all", "--head", galaz, "--limit", "10", "--json", "state,number")
    if kod != 0 or not out.strip().startswith("["):
        return None
    stany = [p.get("state") for p in json_z(out, []) if isinstance(p, dict)]
    for s in ("OPEN", "MERGED", "CLOSED"):
        if s in stany:
            return s
    return "BRAK"


def glowna_ci(repo_gh, ust):
    """CI ostatniego commita gałęzi głównej -> (OK | CZERWONE | TRWA | BRAK, sha) albo (None, "") gdy GitHub nie odpowiedział."""
    g = ust["galaz_glowna"]
    kod, out, _ = gh("api", "repos/%s/commits/%s/check-runs?per_page=100" % (repo_gh, g))
    kod2, out2, _ = gh("api", "repos/%s/commits/%s/status" % (repo_gh, g))
    if kod != 0 or kod2 != 0:
        return None, ""
    biegi = [b for b in (json_z(out, {}).get("check_runs") or []) if isinstance(b, dict)]
    zb = json_z(out2, {})
    sha = str(zb.get("sha") or (biegi[0].get("head_sha") if biegi else "") or "").lower()
    stany = [str(b.get("conclusion") or b.get("status") or "").upper() for b in biegi]
    if zb.get("total_count"):
        stany.append({"success": "SUCCESS", "failure": "FAILURE", "error": "ERROR"}.get(str(zb.get("state")), "PENDING"))
    if any(s in GLOWNA_ZLE for s in stany):
        return "CZERWONE", sha
    if not stany:
        return "BRAK", sha
    return ("OK" if all(s in CI_DOBRE for s in stany) else "TRWA"), sha


def migracje_glownej(repo_gh, ust):
    """Ścieżki migracji na gałęzi głównej (jedno wywołanie API na repo); błąd -> None."""
    kod, out, _ = gh("api", "repos/%s/git/trees/%s?recursive=1" % (repo_gh, ust["galaz_glowna"]), "--jq", ".tree[].path", timeout=90)
    if kod != 0:
        return None
    return [p for p in out.splitlines() if pasuje(p, ust["migracje"])]


# ---------- klasyfikacja ----------

def czysc(s, n=80):
    """Tekst z GitHuba albo z cudzego pliku to dane: jedna linia, bez składni powłoki i Markdownu, przycięty."""
    t = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    t = re.sub(r"[^\w .,:;/#@()+=%–„”!?&'-]", "?", t)
    return t[:n] + ("…" if len(t) > n else "")


def czas_iso(s):
    try:
        return dt.datetime.strptime(str(s).strip()[:16], "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None


def min_od(t, teraz):
    return int((teraz - t).total_seconds() // 60) if t else None


def pasuje(sciezka, wzorce):
    """Wzorzec z „/” na końcu = katalog od początku ścieżki; z „/” w środku = glob po całej ścieżce; bez „/” = glob po nazwie pliku."""
    nazwa = sciezka.rsplit("/", 1)[-1]
    for wz in wzorce or []:
        if wz.endswith("/"):
            if sciezka.startswith(wz):
                return True
        elif "/" in wz:
            if fnmatch.fnmatchcase(sciezka, wz):
                return True
        elif fnmatch.fnmatchcase(nazwa, wz):
            return True
    return False


def pliki(pr):
    return sorted(str(f.get("path")) for f in (pr.get("files") or []) if isinstance(f, dict) and f.get("path"))


def wersje_migracji(sciezki_, ust):
    """-> {(katalog, numer): ścieżka} dla plików migracji z numerem na początku nazwy."""
    wyn = {}
    for p in sciezki_:
        if pasuje(p, ust["migracje"]):
            kat, _, nazwa = p.rpartition("/")
            m = RE_WERSJA.match(nazwa)
            if m:
                wyn[(kat, m.group(1))] = p
    return wyn


def _czas_checku(c):
    """Czas startu przebiegu checku do porównań: „9999” = niezakończony (GitHub podaje 0001-01-01 – jest najnowszy);
    "" = brak danych o czasie."""
    for p in ("startedAt", "createdAt", "completedAt"):
        v = str(c.get(p) or "")
        if v.startswith("0001-"):
            return "9999"
        if v:
            return v
    return ""


def _waga_wyniku(s):
    return 2 if s in CI_ZLE else 0 if s in CI_DOBRE else 1        # czerwony > w toku > zielony


def _wynik_checku(c):
    return str(c.get("conclusion") or c.get("state") or c.get("status") or "").upper()


def _klucz_checku(c):
    return (str(c.get("workflowName") or ""), str(c.get("name") or c.get("context") or "?"))


def ostatnie_checki(rollup):
    """Ostatni przebieg każdego checku (klucz: workflow + nazwa). `statusCheckRollup` zawiera WSZYSTKIE przebiegi na head,
    także czerwone sprzed ponowienia – liczy się tylko najnowszy wg czasu startu. Remis czasu albo brak czasu przy kilku
    przebiegach tego samego checku = nie da się ustalić kolejności → bierzemy najgorszy wynik (czerwony)."""
    grupy = {}
    for c in rollup or []:
        if isinstance(c, dict):
            grupy.setdefault(_klucz_checku(c), []).append(c)
    wynik = {}
    for kl, runy in grupy.items():
        if len(runy) == 1:
            wynik[kl] = runy[0]
            continue
        if any(not _czas_checku(c) for c in runy):
            kandydaci = runy                                        # brak danych o czasie – kolejność nieznana
        else:
            naj = max(_czas_checku(c) for c in runy)
            kandydaci = [c for c in runy if _czas_checku(c) == naj]
        wynik[kl] = max(kandydaci, key=lambda c: _waga_wyniku(_wynik_checku(c)))
    return wynik


def ci(pr, repo_gh, ust):
    """-> (OK | BRAK | CZERWONE | TRWA, nazwy czerwonych checków). Pusta lista checków to BRAK, nie zielone.
    Liczy się ostatni przebieg każdego checku (ostatnie_checki), nie każdy wpis rollupu."""
    stany, zle = [], []
    for c in ostatnie_checki(pr.get("statusCheckRollup")).values():
        s = _wynik_checku(c)
        stany.append(s)
        if s in CI_ZLE:
            zle.append(czysc(c.get("name") or c.get("context") or "?", 40))
    if zle:
        return "CZERWONE", zle
    if not stany:
        return ("BRAK" if ust["ci_wymagane"] and repo_gh not in ust["bez_ci"] else "OK"), []
    return ("OK" if all(s in CI_DOBRE for s in stany) else "TRWA"), []


def check_na_head(pr, nazwa):
    """Warunek „zielony <check> na head”: -> (True | False, opis). Nazwa = nazwa checku, kontekst statusu albo
    „<workflow> / <nazwa>”; zielony = ostatni przebieg ma SUCCESS (NEUTRAL i SKIPPED nie spełniają warunku)."""
    pasujace = [c for (wf, n), c in ostatnie_checki((pr or {}).get("statusCheckRollup")).items()
                if nazwa in (n, "%s / %s" % (wf, n))]
    if not pasujace:
        return False, "check %s nieobecny na head" % czysc(nazwa, 40)
    zle = [_wynik_checku(c) for c in pasujace if _wynik_checku(c) != "SUCCESS"]
    if zle:
        return False, "check %s na head: %s" % (czysc(nazwa, 40), zle[0] or "?")
    return True, ""


class Kontekst:
    """Wszystko, czego klasyfikacja potrzebuje poza samym PR-em. Testy podstawiają własne dane i funkcje."""

    def __init__(self, repo, teraz=None, repa=None, ust=None, prg=None, rec=None, st=None, wstrz=None, org_github=None,
                 agenci=None, teraz_s=None, tetno_s=None, f_stan_pr=stan_pr, f_stan_galezi=stan_galezi, f_migracje=migracje_glownej,
                 wstrz_blad=None):
        self.repo = pathlib.Path(repo)
        self.ust = ust if ust is not None else ustawienia(self.repo)
        self.prg = prg if prg is not None else progi(self.repo)
        self.repa = repa if repa is not None else repozytoria(self.repo)
        self.org_github = org_github if org_github is not None else org(self.repo)["github"]
        self.teraz = teraz or teraz_org(self.repo)
        self.teraz_s = teraz_s if teraz_s is not None else time.time()
        self.tetno_s = tetno_s
        self.rec = rec if rec is not None else werdykty(self.repo, self.ust)
        self.st = st if st is not None else stan(self.repo)
        self.wstrz = wstrz if wstrz is not None else wstrzymane(self.repo, self.ust)
        self.wstrz_blad = wstrz_blad if wstrz_blad is not None else (False if wstrz is not None else rejestr_nieczytelny(self.repo, self.ust))
        self.agenci = agenci
        self._f = (f_stan_pr, f_stan_galezi, f_migracje)
        self.otwarte = {}          # repo -> otwarte PR-y (uzupełnia tabela)
        self._pam = {}

    def _raz(self, kl, f):
        if kl not in self._pam:
            self._pam[kl] = f()
        return self._pam[kl]

    def stan_pr(self, repo_gh, nr):
        if any(str(p.get("number")) == str(nr) for p in self.otwarte.get(repo_gh, [])):
            return "OPEN"
        return self._raz(("pr", repo_gh, str(nr)), lambda: self._f[0](repo_gh, nr))

    def stan_galezi(self, repo_gh, galaz):
        if any(p.get("headRefName") == galaz for p in self.otwarte.get(repo_gh, [])):
            return "OPEN"
        return self._raz(("galaz", repo_gh, galaz), lambda: self._f[1](repo_gh, galaz))

    def autor(self, galaz):
        """Agent z nazwy gałęzi agent/<agent>-<temat>; nieznany albo bez roli -> ceo."""
        m = RE_AUTOR.match(str(galaz or ""))
        if not m:
            return "ceo"
        znany = m.group(1) in self.agenci if self.agenci is not None else (self.repo / "role" / (m.group(1) + ".md")).exists()
        return m.group(1) if znany else "ceo"

    def kolizja(self, repo_gh, nr, sc):
        """Ten sam (katalog, numer) migracji w innym pliku na głównej albo w starszym otwartym PR-ze -> opis; "" = brak; None = nie wiadomo."""
        moje = wersje_migracji(sc, self.ust)
        if not moje:
            return ""
        gl = self._raz(("migracje", repo_gh), lambda: self._f[2](repo_gh, self.ust))
        if gl is None:
            return None
        na_gl = wersje_migracji(gl, self.ust)
        for kw, p in sorted(moje.items()):
            if kw in na_gl and na_gl[kw] != p:
                return "numer %s zajęty na gałęzi głównej: %s" % (kw[1], czysc(na_gl[kw], 60))
        for inny in self.otwarte.get(repo_gh, []):
            if int(inny.get("number") or 0) < int(nr):
                for kw, p in wersje_migracji(pliki(inny), self.ust).items():
                    if kw in moje and moje[kw] != p:
                        return "numer %s ma też starszy PR %s" % (kw[1], klucz(repo_gh, inny.get("number"), self.repa))
        return ""


def werdykt_pol(w, repo_gh, k, pr=None):
    """Pola maszynowe werdyktu -> (TAK | NIE | WARUNEK | ZALEZNOSC | NIEJASNY, uwaga). Prozy werdyktu skrypt nie czyta.
    Formy maszynowe warunku: „po #N” / „po <repo>#N” (zależność) i „zielony <check> na head” (sprawdzany na `pr` – bez
    `pr` albo gdy niespełniony, zostaje warunkiem do oceny CEO). Każdy inny warunek, także forma z dopiskiem – WARUNEK."""
    wynik = str(w.get("wynik", "")).strip().upper()
    if wynik not in ("OK", "OK Z UWAGAMI", "ZMIANY"):
        return "NIEJASNY", "nieznany wynik werdyktu"
    sc = w.get("scalenie")
    if sc is None:
        return ("NIE", "werdykt ZMIANY") if wynik == "ZMIANY" else ("NIEJASNY", "brak pola „scalenie”")
    sc = str(sc).strip().lower()
    if sc == "nie":
        return "NIE", "scalenie: nie"
    if sc not in ("tak", "warunek"):
        return "NIEJASNY", "pole „scalenie” spoza tak / nie / warunek"
    if wynik == "ZMIANY":
        return "NIEJASNY", "wynik ZMIANY sprzeczny ze scalenie: %s" % sc
    warunki = w.get("warunki") if w.get("warunki") is not None else []
    kroki = w.get("kroki") if w.get("kroki") is not None else []
    if not isinstance(warunki, list) or not isinstance(kroki, list):
        return "NIEJASNY", "„warunki” i „kroki” muszą być listami"
    if sc == "warunek" and not warunki and not kroki:
        return "NIEJASNY", "scalenie: warunek bez warunków i kroków"
    inne, czeka, niespelnione = 0, [], []
    for wr in warunki:
        mc = RE_CHECK.fullmatch(str(wr).strip())
        if mc:
            ok, uw_ch = check_na_head(pr, mc.group(1) or mc.group(2)) if pr is not None else (False, "")
            if not ok:
                inne += 1
                if uw_ch:
                    niespelnione.append(uw_ch)
            continue
        m = RE_PO.match(str(wr).strip())
        if not m:
            inne += 1
            continue
        r = repo_gh
        if m.group(1):
            r = next((x for x in k.repa if m.group(1) in (x, x.split("/")[-1])), None)
            if r is None:
                return "NIEJASNY", "warunek wskazuje nieznane repozytorium: %s" % czysc(wr, 40)
        s, kz = k.stan_pr(r, m.group(2)), klucz(r, m.group(2), k.repa)
        if s == "OPEN":
            czeka.append(kz)
        elif s is None:
            czeka.append(kz + " (stan nieznany)")
        elif s != "MERGED":
            return "NIEJASNY", "zależność %s nie jest ani otwarta, ani scalona" % kz
    if inne or kroki:
        return "WARUNEK", "warunki do oceny: %d, kroki: %d%s%s" % (inne, len(kroki), ("; " + "; ".join(niespelnione[:2])) if niespelnione else "",
                                                                 ("; czeka też na " + ", ".join(czeka)) if czeka else "")
    if czeka:
        return "ZALEZNOSC", "czeka na " + ", ".join(czeka)
    return "TAK", ""


def _klasa(pr, repo_gh, k):
    """Kolejność ma znaczenie: najpierw to, co i tak wyklucza scalenie, na końcu to, co wymaga czyjejś decyzji."""
    ust, prg = k.ust, k.prg
    kk = klucz(repo_gh, pr.get("number"), k.repa)
    head = str(pr.get("headRefOid") or "").lower()
    tytul = str(pr.get("title") or "")
    if not re.match(r"^[0-9a-f]{40,64}$", head):
        return "NIEZNANY", "nieczytelny head"
    if pr.get("isDraft") or RE_CZLOWIEK.search(tytul):
        return "SZKIC", "szkic albo PR wyłączony z recenzji"
    w = k.rec.get(kk)
    if not isinstance(w, dict):
        wiek = min_od(czas_gh(pr.get("createdAt"), k.repo), k.teraz)
        if wiek is None or wiek > prg["pr_bez_werdyktu_min"]:
            return "BRAK_WERDYKTU", "bez werdyktu od %s min (próg %d)" % ("?" if wiek is None else wiek, prg["pr_bez_werdyktu_min"])
        return "SWIEZY", "czeka na recenzję %d min" % wiek
    sha = str(w.get("sha") or "").strip().lower()
    if len(sha) < 7 or not re.match(r"^[0-9a-f]+$", sha) or not head.startswith(sha):
        return "NOWY_HEAD", "werdykt dla %s, head %s" % (czysc(sha[:10], 10) or "–", head[:10])
    pol, uw_pol = werdykt_pol(w, repo_gh, k, pr)
    if pol == "NIE":
        return "NIE_SCALAC", uw_pol
    baza = str(pr.get("baseRefName") or "")
    if baza != ust["galaz_glowna"]:
        s = k.stan_galezi(repo_gh, baza)
        if s == "OPEN":
            return "CZEKA_NA_RODZICA", "baza %s – rodzic otwarty" % czysc(baza, 60)
        if s == "MERGED":
            return "PRZEPNIJ", "rodzic scalony – baza %s do zmiany na %s" % (czysc(baza, 60), ust["galaz_glowna"])
        if s is None:
            return "NIEZNANY", "stan rodzica nieznany (GitHub nie odpowiedział)"
        return "WARUNEK", "baza %s nie jest gałęzią główną, a jej PR nie jest ani otwarty, ani scalony" % czysc(baza, 60)
    scalalny = str(pr.get("mergeable") or "").upper()
    if scalalny == "CONFLICTING":
        return "KONFLIKT", "konflikt z %s" % ust["galaz_glowna"]
    stan_ci, zle = ci(pr, repo_gh, ust)
    if stan_ci == "BRAK":
        return "BRAK_CI", "brak checków dla head"
    if stan_ci == "CZERWONE":
        return "CI_CZERWONE", "czerwone: " + ", ".join(zle[:3])
    if stan_ci == "TRWA":
        return "CI_TRWA", "CI w toku"
    if scalalny != "MERGEABLE":
        return "CI_TRWA", "GitHub jeszcze liczy scalalność"
    sc = pliki(pr)
    prz = k.st["przepiete"].get(kk)
    if isinstance(prz, dict) and prz.get("sha") == head and w.get("po_przepieciu") is not True \
            and sorted(prz.get("pliki") or []) != sc:
        return "PO_PRZEPIECIU", "po zmianie bazy lista plików inna niż w recenzji"
    ile = pr.get("changedFiles")
    if not sc or (isinstance(ile, int) and ile != len(sc)) or len(sc) >= 100:
        return "WYJATEK", "lista plików pusta albo niepełna (%s z %s) – nie da się sprawdzić ścieżek" % (len(sc), ile if ile is not None else "?")
    wyj = [p for p in sc if pasuje(p, ust["wyjatki"])]
    if repo_gh == k.org_github:
        wyj += [p for p in sc if pasuje(p, ust["reguly"]) and p not in wyj]
    if wyj:
        return "WYJATEK", "ścieżki wyłączone: " + ", ".join(czysc(p, 50) for p in wyj[:3]) + (" i %d innych" % (len(wyj) - 3) if len(wyj) > 3 else "")
    if pol != "TAK":
        return pol, uw_pol
    km = w.get("klasa_migracji")
    if any(pasuje(p, ust["migracje"]) for p in sc) or km:
        kol = k.kolizja(repo_gh, pr.get("number"), sc)
        if kol is None:
            return "NIEZNANY", "nie udało się sprawdzić numerów migracji na gałęzi głównej"
        if kol:
            return "KOLIZJA_MIGRACJI", kol
        klasy = sorted(set(str(v).strip().upper() for v in km.values())) if isinstance(km, dict) and km else []
        return "MIGRACJA", ("klasa A – scalenie i zastosowanie: CEO" if klasy == ["A"] else "klasa B albo brak klasy – decyzja właściciela")
    etykiety = [str(e.get("name") or "").lower() for e in (pr.get("labels") or []) if isinstance(e, dict)]
    stop = [e for e in etykiety if e in [x.lower() for x in ust["etykiety_stop"]]]
    if stop:
        return "DECYZJA", "etykieta: " + czysc(stop[0], 40)
    if RE_STOP.search(tytul) or RE_STOP_TRESC.search(str(pr.get("body") or "")):
        return "DECYZJA", "znacznik „nie scalać” w tytule albo opisie"
    return "GOTOWY", ""


def klasa(pr, repo_gh, k):
    """-> (klasa, uwaga); nakłada wstrzymanie CEO na wiersze, które bez niego poszłyby do scalenia albo do CEO."""
    kl_, uw = _klasa(pr, repo_gh, k)
    h = k.wstrz.get(klucz(repo_gh, pr.get("number"), k.repa))
    if not isinstance(h, dict) or not (kl_ in SCALA or (ADRESAT.get(kl_) == "ceo" and kl_ != "DO_ZWOLNIENIA")):
        return kl_, uw
    head, hs = str(pr.get("headRefOid") or "").lower(), str(h.get("sha") or "").lower()
    if not hs or head.startswith(hs):
        return "WSTRZYMANY", "wstrzymany przez CEO: " + czysc(h.get("powod"), 60)
    if h.get("tryb") == "head":
        return kl_, uw                                      # wstrzymanie dotyczyło poprzedniego commita
    return ("DO_ZWOLNIENIA", "wstrzymany do odwołania, nowy head z werdyktem") if kl_ in SCALA else (kl_, uw)


def wiersz(pr, repo_gh, k):
    kl_, uw = klasa(pr, repo_gh, k)
    nr = int(pr.get("number") or 0)
    kk, head = klucz(repo_gh, nr, k.repa), str(pr.get("headRefOid") or "").lower()
    w = k.rec.get(kk) if isinstance(k.rec.get(kk), dict) else {}
    adr = "scal" if kl_ in SCALA else "własna" if kl_ in WLASNE else ADRESAT.get(kl_, "–")
    wyn = {"klucz": kk, "repo": repo_gh, "nr": nr, "klasa": kl_, "uwaga": uw, "head": head, "etap": 1, "klucz_zgl": kk, "sha_zgl": head,
           "galaz": czysc(pr.get("headRefName"), 80), "tytul": czysc(pr.get("title"), 80),
           "werdykt": czysc(w.get("wynik"), 20), "min_od_werdyktu": min_od(czas_werdyktu(w)[0], k.teraz),
           "adresat": k.autor(pr.get("headRefName")) if adr == "autor" else adr, "polecenia": []}
    zg = k.st["zgloszone"].get(kk)
    zgl = isinstance(zg, dict) and zg.get("sha") == head and zg.get("klasa") == kl_
    if kl_ == "BRAK_CI" and zgl and zg.get("etap") != 2:
        od = min_od(czas_iso(zg.get("kiedy")), k.teraz)
        if od is None or od > k.prg["brak_ci_eskalacja_min"]:     # ponowienie nie pomogło – drugi etap idzie do CEO
            zgl, wyn["etap"], wyn["adresat"], wyn["uwaga"] = False, 2, "ceo", "brak checków mimo ponowienia"
    if kl_ in SCALA + ("PRZEPNIJ",) and zgl:
        od = min_od(czas_iso(zg.get("kiedy")), k.teraz)
        if od is None or od > k.prg["zlecenie_scalania_termin_h"] * 60:
            zgl = False                                     # odmowa GitHuba zgłoszona dawno – jedna ponowna próba; zlecenie się nie dubluje
    wyn["zgloszony"] = bool(zgl)
    wyn["do_zrobienia"] = kl_ in DO_ZROBIENIA and not zgl
    if wyn["do_zrobienia"]:
        gdzie = "%d --repo %s" % (nr, repo_gh)
        if kl_ in SCALA:
            wyn["polecenia"] = ["gh pr merge %s --%s --match-head-commit %s" % (gdzie, k.ust["metoda"], head)]
        elif kl_ == "PRZEPNIJ":
            wyn["polecenia"] = ["gh pr edit %s --base %s" % (gdzie, k.ust["galaz_glowna"]), "gh pr close " + gdzie, "gh pr reopen " + gdzie]
        elif kl_ == "BRAK_CI" and wyn["etap"] == 1:
            wyn["polecenia"] = ["gh pr close " + gdzie, "gh pr reopen " + gdzie]
    return wyn


def otwarte_pr(repo_gh):
    kod, out, _ = gh("pr", "list", "-R", repo_gh, "--state", "open", "--limit", "200", "--json", POLA, timeout=120)
    return json_z(out, []) if kod == 0 and out.strip().startswith("[") else None


def jeden_pr(repo_gh, nr, pola=POLA):
    kod, out, _ = gh("pr", "view", str(nr), "-R", repo_gh, "--json", pola)
    return (json_z(out, {}) or None) if kod == 0 else None


def zatrzymaj_na_czerwonej(wiersze, k, f_glowna):
    """„Zatrzymaj linię”: przy czerwonym CI gałęzi głównej gotowe PR-y tego repozytorium nie są scalane.
    Pierwszy wiersz niesie jedno zgłoszenie do CEO (raz na czerwony commit), pozostałe czekają. -> uwagi do nagłówka."""
    uwagi = []
    if not k.ust.get("stop_gdy_glowna_czerwona"):
        return uwagi
    for r in k.repa:
        gotowe = [w for w in wiersze if w["repo"] == r and w["klasa"] in SCALA]
        if not gotowe:
            continue
        s, sha = f_glowna(r, k.ust)
        if s is None:
            uwagi.append("UWAGA: %s – stan CI gałęzi głównej nieznany, kolejka nie jest zatrzymana" % r)
            continue
        if s != "CZERWONE":
            continue
        kz = "glowna:" + r.split("/")[-1]
        zg = k.st["zgloszone"].get(kz)
        zgl = isinstance(zg, dict) and zg.get("sha") == sha and zg.get("klasa") == "GLOWNA_CZERWONA"
        for i, w in enumerate(gotowe):
            w["polecenia"] = []
            if i == 0:
                w.update(klasa="GLOWNA_CZERWONA", adresat="ceo", klucz_zgl=kz, sha_zgl=sha, zgloszony=bool(zgl), do_zrobienia=not zgl,
                         uwaga="CI gałęzi %s czerwone (%s) – gotowe PR-y w %s czekają: %d" % (k.ust["galaz_glowna"], sha[:10], r, len(gotowe)))
            else:
                w.update(klasa="CZEKA_NA_GLOWNA", adresat="–", zgloszony=False, do_zrobienia=False, uwaga="czeka na zieloną gałąź główną")
    return uwagi


def zatrzymaj_na_rejestrze(wiersze, k):
    """Nieczytelny rejestr wstrzymań CEO = nie wiadomo, czego nie wolno scalić: żaden gotowy PR nie jest scalany,
    a do CEO idzie jedno pilne zgłoszenie dziennie. -> uwagi do nagłówka."""
    if not k.wstrz_blad:
        return []
    gotowe = [w for w in wiersze if w["klasa"] in SCALA]
    dzien = k.teraz.strftime("%Y-%m-%d")
    zg = k.st["zgloszone"].get("rejestr:wstrzymane")
    zgl = isinstance(zg, dict) and zg.get("sha") == dzien and zg.get("klasa") == "REJESTR"
    for i, w in enumerate(gotowe):
        w["polecenia"] = []
        if i == 0:
            w.update(klasa="REJESTR", adresat="ceo", klucz_zgl="rejestr:wstrzymane", sha_zgl=dzien, zgloszony=bool(zgl),
                     do_zrobienia=not zgl, uwaga="rejestr wstrzymań nieczytelny – gotowe PR-y czekają: %d" % len(gotowe))
        else:
            w.update(klasa="WSTRZYMANY", adresat="–", zgloszony=False, do_zrobienia=False, uwaga="rejestr wstrzymań nieczytelny")
    return ["UWAGA: ceo/scalanie/wstrzymane.json nieczytelny – do naprawy pliku nic nie jest scalane"]


def pliki_sporne(k):
    """Ścieżki zmieniane przez co najmniej `pliki_sporne_min_pr` otwartych PR-ów -> [(repo, ścieżka, ile)], najczęstsze pierwsze.
    Po każdym scaleniu taki plik wpycha pozostałe PR-y w konflikt – architekt dzieli go albo zamienia na generowany."""
    prog, wyn = int(k.prg.get("pliki_sporne_min_pr", 3)), []
    for r in k.repa:
        ile = {}
        for p in k.otwarte.get(r, []):
            if not p.get("isDraft"):
                for s in set(pliki(p)):
                    ile[s] = ile.get(s, 0) + 1
        wyn += [(r, s, n) for s, n in ile.items() if n >= prog]
    return sorted(wyn, key=lambda x: (-x[2], x[0], x[1]))


def tabela(k, f_otwarte=otwarte_pr, f_pr=jeden_pr, spij=time.sleep, f_glowna=glowna_ci):
    """-> (wiersze, repozytoria z błędem gh); uwagi do nagłówka w k.uwagi, pliki sporne w k.sporne.
    Jedno ponowienie dla PR-ów, których scalalności GitHub jeszcze nie policzył."""
    bledy = []
    for r in k.repa:
        lista = f_otwarte(r)
        if lista is None:
            bledy.append(r)
        else:
            k.otwarte[r] = [p for p in lista if isinstance(p, dict)]
    niepewne = [(r, p) for r in k.repa for p in k.otwarte.get(r, [])
                if str(p.get("mergeable") or "").upper() not in ("MERGEABLE", "CONFLICTING") and not p.get("isDraft")]
    if niepewne:
        spij(2)
        for r, p in niepewne[:20]:
            nowy = f_pr(r, p.get("number"))
            if nowy:
                p.update(nowy)
    wiersze = [wiersz(p, r, k) for r in k.repa for p in sorted(k.otwarte.get(r, []), key=lambda x: int(x.get("number") or 0))]
    k.uwagi = zatrzymaj_na_rejestrze(wiersze, k)
    k.uwagi += zatrzymaj_na_czerwonej(wiersze, k, f_glowna)
    k.sporne = pliki_sporne(k)
    return wiersze, bledy


def rezerwa(wiersze, k):
    """-> (TAK | NIE, powód). Przebieg CEO scala w zastępstwie tylko przy TAK: gotowy PR czeka ponad próg, a agent nie daje znaku."""
    prog = k.prg["gotowy_rezerwa_ceo_min"]
    wieki = [w["min_od_werdyktu"] for w in wiersze if w["klasa"] in SCALA and w["do_zrobienia"]]
    if not wieki:
        return "NIE", "nic nie czeka na scalenie"
    znane = [x for x in wieki if x is not None]
    if not znane:
        return "NIE", "gotowe PR-y bez czasu werdyktu (pole kiedy albo data)"
    if max(znane) <= prog:
        return "NIE", "najstarszy gotowy PR czeka %d min (próg %d)" % (max(znane), prog)
    if k.tetno_s is not None and k.teraz_s - k.tetno_s <= prog * 60:
        return "NIE", "agent scalający działał %d min temu" % max(0, int((k.teraz_s - k.tetno_s) // 60))
    return "TAK", "gotowy PR czeka %d min, agent scalający bez śladu od ponad %d min" % (max(znane), prog)


def wypisz(wiersze, bledy, k, wszystko=False):
    rob = [w for w in wiersze if w["do_zrobienia"]]
    print("KOLEJKA SCALANIA %s – otwarte PR-y: %d, do zrobienia: %d" % (k.teraz.strftime("%Y-%m-%d %H:%M"), len(wiersze), len(rob)))
    for r in bledy:
        print("BŁĄD GH: %s – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu" % r)
    for u in getattr(k, "uwagi", []):
        print(u)
    sporne = getattr(k, "sporne", [])
    if sporne:
        print("PLIKI SPORNE: " + "; ".join("%s (%d PR-ów, %s)" % (czysc(s, 60), n, r.split("/")[-1]) for r, s, n in sporne[:5])
              + (" i %d innych" % (len(sporne) - 5) if len(sporne) > 5 else ""))
    for w in (wiersze if wszystko else rob):
        print("%-16s %-17s -> %-10s %s  %s" % (w["klucz"], w["klasa"] + ("*" if w["zgloszony"] else ""), w["adresat"], w["head"][:10], w["uwaga"]))
        for p in w["polecenia"]:
            print("    $ " + p)
    if not rob:
        print("NIC DO ZROBIENIA")
    if not wszystko:
        reszta = {}
        for w in wiersze:
            if not w["do_zrobienia"]:
                n = w["klasa"] + (" (zgłoszone)" if w["zgloszony"] else "")
                reszta[n] = reszta.get(n, 0) + 1
        if reszta:
            print("bez ruchu: " + ", ".join("%s %d" % x for x in sorted(reszta.items())))
    print("REZERWA_CEO: %s – %s" % rezerwa(wiersze, k))


# ---------- blokada, tętno, prywatny katalog roboczy ----------

def _prefiks(repo):
    return re.sub(r"[^a-z0-9-]", "", org(repo)["prefiks"].lower()) or "org"


def sciezki(repo):
    """Miejsca poza repozytorium (lokalne dla maszyny); zmienne SCALANIE_* podmieniają je w testach."""
    dom, pre = pathlib.Path.home(), _prefiks(repo)
    kat = pathlib.Path(os.environ.get("SCALANIE_KATALOG") or dom / (".%s-scalanie" % pre) / "wt")
    return {"blokada": pathlib.Path(os.environ.get("SCALANIE_BLOKADA") or dom / (".%s-scalanie.lock" % pre)),
            "tetno": pathlib.Path(os.environ.get("SCALANIE_TETNO") or dom / (".%s-scalanie.ostatni" % pre)),
            "katalog": kat, "oczekujace": kat.parent / "oczekujace.jsonl"}


def epoka(repo, arg=None):
    """--teraz -> sekundy epoki (w strefie organizacji); bez argumentu zegar systemowy."""
    if not arg:
        return time.time()
    t = teraz_org(repo, arg)
    try:
        from zoneinfo import ZoneInfo
        return t.replace(tzinfo=ZoneInfo(org(repo)["strefa"])).timestamp()
    except Exception:
        return time.mktime(t.timetuple())


def zapisz_plik(p, tekst):
    """Zapis przez plik tymczasowy i podmianę – czytelnik nigdy nie widzi połowy pliku."""
    p = pathlib.Path(p)
    tmp = p.with_name(p.name + ".tmp-" + secrets.token_hex(4))
    tmp.write_text(tekst, encoding="utf-8")
    os.replace(tmp, p)


def blokada_info(b):
    """-> {kto, token, od_s} albo None (blokady nie ma). Nieczytelny plik `kto` = blokada bez właściciela, wiek z katalogu."""
    if not b.is_dir():
        return None
    try:
        d = json.loads((b / "kto").read_text(encoding="utf-8"))
        return {"kto": str(d["kto"]), "token": str(d["token"]), "od_s": float(d["od_s"])}
    except (OSError, ValueError, KeyError, TypeError):
        try:
            return {"kto": "?", "token": "", "od_s": b.stat().st_mtime}
        except OSError:
            return None


def wez_blokade(repo, kto, teraz_s, prg):
    """-> (0, token) | (10, komunikat: zajęta) | (12, komunikat: błąd systemu plików).
    Blokada to katalog (mkdir jest atomowy). Martwą – bez znaku ponad próg – przejmuje się przez zmianę nazwy:
    z dwóch przebiegów, które zauważyły ją naraz, zmiana nazwy udaje się tylko jednemu."""
    b, prog_s = sciezki(repo)["blokada"], prg["blokada_scalania_min"] * 60
    for proba in (1, 2):
        try:
            os.mkdir(b)
        except FileExistsError:
            inf = blokada_info(b)
            if inf is None:
                continue                                    # zniknęła między próbą a odczytem
            wiek = teraz_s - inf["od_s"]
            if wiek <= prog_s or proba == 2:
                return 10, "BLOKADA zajęta: %s od %d min" % (czysc(inf["kto"], 40), max(0, int(wiek // 60)))
            stara = b.with_name(b.name + ".stara-" + secrets.token_hex(4))
            try:
                os.rename(b, stara)
            except OSError:
                return 10, "BLOKADA zajęta: właśnie przejmuje ją inny przebieg"
            po = blokada_info(stara)
            if po is None or po["token"] != inf["token"]:   # ktoś zdążył wziąć nową – oddaj mu ją
                try:
                    os.rename(stara, b)
                except OSError:
                    pass
                return 10, "BLOKADA zajęta: właśnie wziął ją inny przebieg"
            shutil.rmtree(stara, ignore_errors=True)
            print("BLOKADA przejęta po %s (bez znaku od %d min, próg %d)" % (czysc(inf["kto"], 40), int(wiek // 60), prg["blokada_scalania_min"]))
            continue
        except OSError as e:
            return 12, "BŁĄD SYSTEMU PLIKÓW: nie da się założyć blokady %s (%s)" % (b, e.__class__.__name__)
        token = secrets.token_hex(8)
        try:
            zapisz_plik(b / "kto", json.dumps({"kto": kto, "token": token, "od_s": teraz_s, "protokol": PROTOKOL}))
        except OSError as e:
            shutil.rmtree(b, ignore_errors=True)
            return 12, "BŁĄD SYSTEMU PLIKÓW: nie da się zapisać właściciela blokady (%s)" % e.__class__.__name__
        return 0, token
    return 10, "BLOKADA zajęta"


def sprawdz_token(repo, token):
    """-> (0, info) | (10, brak blokady) | (11, blokada nie twoja)."""
    inf = blokada_info(sciezki(repo)["blokada"])
    if inf is None:
        return 10, "BRAK BLOKADY: najpierw `scalanie.py blokada <kto>` – bez blokady niczego nie scalaj ani nie zapisuj"
    if not token or inf["token"] != token:
        return 11, "BLOKADA nie twoja: trzyma ją %s – niczego nie scalaj ani nie zapisuj" % czysc(inf["kto"], 40)
    return 0, inf


def odswiez(repo, token, teraz_s):
    kod, inf = sprawdz_token(repo, token)
    if kod != 0:
        return kod, inf
    try:
        zapisz_plik(sciezki(repo)["blokada"] / "kto", json.dumps({"kto": inf["kto"], "token": token, "od_s": teraz_s, "protokol": PROTOKOL}))
    except OSError as e:
        return 12, "BŁĄD SYSTEMU PLIKÓW: blokada nieodświeżona (%s)" % e.__class__.__name__
    return 0, "BLOKADA odświeżona"


def odblokuj(repo, token, teraz_s, z_tetnem=True):
    """Zdejmuje własną blokadę. Tętno („agent scalający skończył przebieg”) zapisuje tylko właściciel `scalanie…` –
    po nim przebieg CEO poznaje, czy ma scalać w zastępstwie."""
    s = sciezki(repo)
    inf = blokada_info(s["blokada"])
    if inf is None:
        return 0, "BLOKADY nie było"
    if not token or inf["token"] != token:
        return 11, "BLOKADA nie twoja: trzyma ją %s – zostaje" % czysc(inf["kto"], 40)
    if z_tetnem and inf["kto"].startswith("scalanie"):
        try:
            zapisz_plik(s["tetno"], json.dumps({"kto": inf["kto"], "kiedy_s": teraz_s}))
        except OSError:
            pass
    shutil.rmtree(s["blokada"], ignore_errors=True)
    return 0, "BLOKADA zwolniona"


def tetno(repo):
    """-> sekundy epoki ostatniego zakończonego przebiegu agenta scalającego albo None."""
    try:
        return float(json.loads(sciezki(repo)["tetno"].read_text(encoding="utf-8"))["kiedy_s"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _wlasny(rel):
    """Ścieżki, które wolno zapisać skryptowi: własny stan, dziennik i skrzynki zleceń (bez podkatalogów)."""
    return rel in WLASNE_PLIKI or bool(re.match(r"^zlecenia/[a-z0-9][a-z0-9-]*\.md$", rel))


def _brudne(wt):
    """-> [(znaki stanu, ścieżka)] z `git status` albo None przy błędzie."""
    kod, out, _ = git(wt, "status", "--porcelain", "-z", "--untracked-files=all")
    if kod != 0:
        return None
    wyn, czesci, i = [], out.split("\0"), 0
    while i < len(czesci):
        c = czesci[i]
        i += 1
        if len(c) < 4:
            continue
        wyn.append((c[:2], c[3:]))
        if "R" in c[:2] or "C" in c[:2]:
            i += 1                                          # druga ścieżka zmiany nazwy
    return wyn


def _na_swieza(wt, g):
    """Katalog roboczy -> odłączony HEAD na origin/<główna>; własne nieśledzone pliki znikają (odtworzy je kolejka oczekujących)."""
    for znaki, rel in _brudne(wt) or []:
        if znaki == "??" and _wlasny(rel):
            try:
                (wt / rel).unlink()
            except OSError:
                pass
    kod, _, err = git(wt, "checkout", "-q", "--detach", "-f", "origin/" + g)
    return kod == 0, czysc(err, 120)


def przygotuj_katalog(repo, ust, teraz):
    """Prywatny katalog roboczy (git worktree, odłączony HEAD na origin/<główna>). -> (0, ścieżka) | (1, komunikat).
    Wspólnego katalogu floty skrypt nie rusza – żadnego stash, clean ani reset; stąd osobny katalog. Obce zmiany znalezione
    w katalogu prywatnym są odkładane obok (łatka + nowe pliki), nigdy kasowane."""
    wt, g = sciezki(repo)["katalog"], ust["galaz_glowna"]
    kod, _, err = git(repo, "fetch", "-q", "origin", timeout=120)
    if kod != 0:
        return 1, "BŁĄD GIT: fetch nie przeszedł (%s)" % czysc(err, 120)
    try:
        wt.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return 1, "BŁĄD SYSTEMU PLIKÓW: %s (%s)" % (wt.parent, e.__class__.__name__)
    znacznik = teraz.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    if not ((wt / ".git").exists() and git(wt, "rev-parse", "HEAD")[0] == 0):
        if wt.exists():
            try:
                os.rename(wt, wt.parent / ("odlozone-" + znacznik))
            except OSError as e:
                return 1, "BŁĄD SYSTEMU PLIKÓW: %s nie jest katalogiem roboczym i nie da się go odłożyć (%s)" % (wt, e.__class__.__name__)
            print("UWAGA: %s nie był katalogiem roboczym git – odłożony jako odlozone-%s" % (wt, znacznik))
        git(repo, "worktree", "prune")
        kod, _, err = git(repo, "worktree", "add", "--detach", str(wt), "origin/" + g, timeout=120)
        if kod != 0:
            return 1, "BŁĄD GIT: nie da się utworzyć katalogu roboczego (%s)" % czysc(err, 120)
        return 0, str(wt)
    brudne = _brudne(wt)
    if brudne is None:
        return 1, "BŁĄD GIT: stan katalogu roboczego nieczytelny"
    obce = [(z, rel) for z, rel in brudne if not _wlasny(rel)]
    if obce:
        kosz = wt.parent / ("odlozone-" + znacznik)
        try:
            kosz.mkdir(parents=True)
            (kosz / "zmiany.patch").write_text(git(wt, "diff", "HEAD", "--binary")[1], encoding="utf-8")
            for z, rel in obce:
                if z == "??":
                    cel = kosz / "nowe" / rel
                    cel.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(wt / rel, cel)
        except OSError as e:
            return 1, "BŁĄD SYSTEMU PLIKÓW: obcych zmian z katalogu roboczego nie da się odłożyć (%s)" % e.__class__.__name__
        print("UWAGA: w katalogu roboczym były obce zmiany (%d plików) – odłożone do %s; kolejka ich nie używa" % (len(obce), kosz))
    ok, err = _na_swieza(wt, g)
    if not ok:
        return 1, "BŁĄD GIT: katalog roboczy nie przeszedł na origin/%s (%s)" % (g, err)
    return 0, str(wt)


# ---------- kolejka oczekujących zapisów (poza gitem) i ich nakładanie ----------

def oczekujace(repo):
    """Zapisy, których jeszcze nie ma na gałęzi głównej (plik poza repozytorium, obok katalogu roboczego)."""
    try:
        linie = sciezki(repo)["oczekujace"].read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    wyn = []
    for l in linie:
        d = json_z(l, {})
        if d.get("op"):
            wyn.append(d)
    return wyn


def dopisz_oczekujace(repo, ops):
    p = sciezki(repo)["oczekujace"]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for o in ops:
            f.write(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n")


def wyczysc_oczekujace(repo):
    try:
        sciezki(repo)["oczekujace"].unlink()
    except OSError:
        pass


def _nastepny_id(wt, dzien, liczniki):
    """Z-RRRRMMDD-NN: kolejny wolny numer dnia – liczony ze wszystkich skrzynek razem z archiwum, w chwili nakładania zapisu."""
    if dzien not in liczniki:
        naj, kat = 0, wt / "zlecenia"
        if kat.is_dir():
            for p in kat.rglob("*.md"):
                try:
                    tekst = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for m in re.finditer(r"\bZ-%s-(\d{2,})\b" % dzien, tekst):
                    naj = max(naj, int(m.group(1)))
        liczniki[dzien] = naj
    liczniki[dzien] += 1
    return "Z-%s-%02d" % (dzien, liczniki[dzien])


def zastosuj(wt, ops, teraz):
    """Nakłada zapisy na katalog roboczy. Idempotentne: drugie nałożenie tych samych zapisów niczego nie zmienia
    (zlecenie rozpoznaje po linii „Kolejka: …”, wpis dziennika po parze klucz + sha).
    -> (zmienione ścieżki względne, {klucz zgłoszenia: identyfikator zlecenia})."""
    wt = pathlib.Path(wt)
    p_stan, p_dz = wt / WLASNE_PLIKI[0], wt / WLASNE_PLIKI[1]
    st = stan(wt)
    przed = json.dumps(st, sort_keys=True)
    dz_tekst = lokalny(wt, WLASNE_PLIKI[1]) or ""
    znane = set()
    for l in dz_tekst.splitlines():
        d = json_z(l, {})
        znane.add((d.get("klucz"), d.get("sha")))
    nowe_linie, skrzynki, zmienione_skrzynki, idy, liczniki = [], {}, [], {}, {}
    for o in ops:
        op = o.get("op")
        if op == "stan_set" and o.get("sekcja") in st and isinstance(o.get("wartosc"), dict) and o.get("klucz"):
            st[o["sekcja"]][str(o["klucz"])] = o["wartosc"]
        elif op == "stan_del" and o.get("sekcja") in st:
            st[o["sekcja"]].pop(str(o.get("klucz")), None)
        elif op == "dziennik" and isinstance(o.get("linia"), dict):
            para = (o["linia"].get("klucz"), o["linia"].get("sha"))
            if para not in znane:
                znane.add(para)
                nowe_linie.append(json.dumps(o["linia"], ensure_ascii=False, sort_keys=True))
        elif op == "zlecenie":
            adr, dzien = str(o.get("adresat") or ""), str(o.get("dzien") or "")
            podpis, wpis = str(o.get("podpis") or "").strip(), str(o.get("wpis") or "").strip("\n")
            if not (RE_KTO.match(adr) and re.match(r"^\d{8}$", dzien) and podpis and wpis):
                continue
            if adr not in skrzynki:
                skrzynki[adr] = lokalny(wt, "zlecenia/%s.md" % adr)
            tekst = skrzynki[adr]
            if tekst is None:
                tekst = "# Zlecenia – %s\n\nFormat wpisu i zasady: `zlecenia/README.md`.\n" % adr
            if podpis in [l.strip() for l in tekst.splitlines()]:
                continue                                    # to zgłoszenie już jest w skrzynce
            nr = _nastepny_id(wt, dzien, liczniki)
            skrzynki[adr] = tekst.rstrip("\n") + "\n\n" + wpis.replace("{ID}", nr, 1) + "\n"
            if adr not in zmienione_skrzynki:
                zmienione_skrzynki.append(adr)
            if o.get("klucz"):
                idy[str(o["klucz"])] = nr
    for kk in [x for x, v in st["zgloszone"].items() if isinstance(v, dict)]:
        wiek = min_od(czas_iso(st["zgloszone"][kk].get("kiedy")), teraz)
        if wiek is not None and wiek > 14 * 24 * 60:        # stare zgłoszenie wygasa – sprawa, która trwa, wróci jako nowa
            del st["zgloszone"][kk]
    zmienione = []
    if json.dumps(st, sort_keys=True) != przed:
        p_stan.parent.mkdir(parents=True, exist_ok=True)
        zapisz_plik(p_stan, json.dumps(st, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        zmienione.append(WLASNE_PLIKI[0])
    if nowe_linie:
        p_dz.parent.mkdir(parents=True, exist_ok=True)
        zapisz_plik(p_dz, dz_tekst + ("" if not dz_tekst or dz_tekst.endswith("\n") else "\n") + "\n".join(nowe_linie) + "\n")
        zmienione.append(WLASNE_PLIKI[1])
    for adr in zmienione_skrzynki:
        (wt / "zlecenia").mkdir(parents=True, exist_ok=True)
        zapisz_plik(wt / "zlecenia" / (adr + ".md"), skrzynki[adr])
        zmienione.append("zlecenia/%s.md" % adr)
    return zmienione, idy


def protokol_skryptu(katalog):
    """Numer protokołu zapisany w skrypcie w podanym katalogu (bez uruchamiania go) albo None."""
    try:
        m = re.search(r"^PROTOKOL\s*=\s*(\d+)", (pathlib.Path(katalog) / "scripts" / "scalanie.py").read_text(encoding="utf-8"), re.M)
    except (OSError, UnicodeDecodeError):
        return None
    return int(m.group(1)) if m else None


def stop_awaryjny(repo):
    """-> powód zatrzymania floty (treść bezpieczenstwo/HALT) albo None. Sprawdza katalog, z którego skrypt działa, oraz wspólny
    katalog repozytorium: prywatny katalog roboczy to osobny worktree, więc lokalnego (jeszcze niewypchniętego) pliku HALT
    hook uprawnień by tam nie zobaczył. Nieczytelny plik HALT też zatrzymuje."""
    katalogi = [pathlib.Path(repo)]
    kod, wyj, _ = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=10)
    if kod == 0 and wyj.strip():
        wspolny = pathlib.Path(wyj.strip())
        if wspolny.name == ".git":
            katalogi.append(wspolny.parent)
    for kat in katalogi:
        plik = kat / "bezpieczenstwo" / "HALT"
        if plik.exists() or plik.is_symlink():
            try:
                return czysc(plik.read_text(encoding="utf-8"), 200) or "HALT"
            except (OSError, ValueError):
                return "HALT"
    return None


def cmd_blokada(repo, kto, protokol_arg, teraz, teraz_s):
    """Blokada + świeży katalog roboczy + zgodność protokołu. Cokolwiek zawiedzie – blokada wraca, bez śladu w tętnie."""
    stop = stop_awaryjny(repo)
    if stop:
        print("FLOTA ZATRZYMANA (bezpieczenstwo/HALT): %s – blokady nie wzięto; plik usuwa operator" % stop)
        return 14
    ust, prg = ustawienia(repo), progi(repo)
    kod, wyn = wez_blokade(repo, kto, teraz_s, prg)
    if kod != 0:
        print(wyn)
        return kod
    token = wyn

    def oddaj(komunikat, kod_):
        odblokuj(repo, token, teraz_s, z_tetnem=False)
        print(komunikat)
        return kod_

    kod, wt = przygotuj_katalog(repo, ust, teraz)
    if kod != 0:
        return oddaj(wt + " – blokady nie wzięto", 1)
    wersje = [("skrypt uruchomiony", PROTOKOL), ("skrypt na gałęzi głównej", protokol_skryptu(wt)),
              ("ustawienia na gałęzi głównej", ustawienia(pathlib.Path(wt)).get("protokol"))]
    if protokol_arg is not None:
        wersje.append(("treść zadania", protokol_arg))
    if len(set(w for _, w in wersje)) != 1:
        return oddaj("NIEZGODNY PROTOKÓŁ: " + ", ".join("%s %s" % (n, "brak" if w is None else w) for n, w in wersje)
                     + ". Podmień razem treść zadania i skrypt (python3 flota/generuj.py, treść zadania zaplanowanego, "
                       "git pull we wspólnym katalogu). Blokady nie wzięto.", 13)
    ops = oczekujace(repo)
    if ops:
        try:
            zastosuj(wt, ops, teraz)
        except OSError as e:
            return oddaj("BŁĄD SYSTEMU PLIKÓW: zapisów z poprzedniego przebiegu nie da się nałożyć (%s) – blokady nie wzięto" % e.__class__.__name__, 12)
        print("OCZEKUJĄCE: %d zapisów z poprzedniego przebiegu nałożone – wypchnie je `zapisz`" % len(ops))
    print("BLOKADA wzięta TOKEN=%s" % token)
    print("KATALOG=%s" % wt)
    return 0


# ---------- zapisy agenta (tylko z tokenem blokady i z katalogu roboczego) ----------

def wymagaj(repo, token):
    """-> (0, info o blokadzie) | (10 | 11, komunikat) | (2, komunikat: zły katalog)."""
    kod, inf = sprawdz_token(repo, token)
    if kod != 0:
        return kod, inf
    kat = sciezki(repo)["katalog"]
    try:
        ten_sam = pathlib.Path(repo).resolve() == kat.resolve()
    except OSError:
        ten_sam = False
    if not ten_sam:
        return 2, "ZŁE WYWOŁANIE: zapisy tylko z katalogu roboczego (%s) – wejdź do niego poleceniem cd i uruchom skrypt stamtąd" % kat
    return 0, inf


def _zapisz_ops(repo, ops, teraz):
    """Najpierw kolejka oczekujących (poza gitem), potem katalog roboczy – przerwany przebieg niczego nie gubi."""
    dopisz_oczekujace(repo, ops)
    return zastosuj(repo, ops, teraz)


def wiersz_prosty(pr, repo_gh, k, kl_, uwaga=""):
    """Wiersz do zgłoszenia wymuszonego (czynność agenta nie przeszła) – bez klasyfikacji, zawsze do CEO."""
    nr = int(pr.get("number") or 0)
    kk, head = klucz(repo_gh, nr, k.repa), str(pr.get("headRefOid") or "").lower()
    return {"klucz": kk, "repo": repo_gh, "nr": nr, "klasa": kl_, "uwaga": uwaga, "head": head, "etap": 1, "klucz_zgl": kk, "sha_zgl": head,
            "galaz": czysc(pr.get("headRefName"), 80), "tytul": czysc(pr.get("title"), 80), "adresat": "ceo"}


def wpis_zlecenia(w, k, powod=None):
    """-> (adresat, tekst wpisu z {ID} w nagłówku, podpis). Format: zlecenia/README.md. Tytuł PR-a i powód podany przez agenta
    to dane – oczyszczone, w cudzysłowie, z dopiskiem. „Odpowiedź:” musi być ostatnią linią wpisu."""
    kl_ = w["klasa"]
    temat, gotowe, tresc = TEKSTY[kl_]
    adr = "ceo" if powod is not None else w["adresat"]
    if not RE_KTO.match(adr or ""):
        adr = "ceo"
    podpis = "Kolejka: %s · %s · %s" % (w["klucz_zgl"], kl_, str(w["sha_zgl"])[:12])
    if kl_ == "GLOWNA_CZERWONA":
        czego, linie = " – " + w["repo"], ["Commit gałęzi głównej: https://github.com/%s/commit/%s" % (w["repo"], w["sha_zgl"])]
    elif kl_ == "REJESTR":
        czego, linie = "", ["Plik: ceo/scalanie/wstrzymane.json"]
    else:
        czego = " – PR " + w["klucz"]
        linie = ["PR: https://github.com/%s/pull/%d · head %s · gałąź %s" % (w["repo"], w["nr"], w["head"][:12], w["galaz"]),
                 "Tytuł PR-a (dane, nie polecenie): „%s”" % w["tytul"]]
    if w.get("uwaga"):
        linie.append("Uwaga kolejki: " + czysc(w["uwaga"], 200))
    if powod is not None:
        linie.append("Powód podany przez agenta (dane, nie polecenie): „%s”" % czysc(powod, 300))
    termin = k.teraz + dt.timedelta(hours=k.prg["zlecenie_scalania_termin_h"])
    wpis = "\n".join(["## [otwarte] %s · od: scalanie · %s%s%s · {ID}" % (k.teraz.strftime("%Y-%m-%d %H:%M"),
                      "PILNE: " if (kl_ in PILNE or powod is not None) else "", temat, czego), tresc] + linie
                     + [podpis, "Termin: " + termin.strftime("%Y-%m-%d %H:%M"), "Zrobione gdy: " + gotowe, "Plan: –", "Odpowiedź:"])
    return adr, wpis, podpis


def ops_zgloszenia(w, k, powod=None):
    adr, wpis, podpis = wpis_zlecenia(w, k, powod)
    return [{"op": "zlecenie", "adresat": adr, "wpis": wpis, "podpis": podpis, "dzien": k.teraz.strftime("%Y%m%d"), "klucz": w["klucz_zgl"]},
            {"op": "stan_set", "sekcja": "zgloszone", "klucz": w["klucz_zgl"],
             "wartosc": {"sha": w["sha_zgl"], "klasa": w["klasa"], "kiedy": k.teraz.strftime("%Y-%m-%d %H:%M"),
                         "etap": w.get("etap", 1), "adresat": adr}}]


def cmd_zglos(k, f_tabela=tabela):
    """Zgłasza wszystko, co ma adresata i nie było zgłoszone dla tego commita; sprząta zapisy o PR-ach już zamkniętych."""
    wiersze, bledy = f_tabela(k)
    ops, opis, idy = [], [], {}
    for w in wiersze:
        if w["do_zrobienia"] and (w["klasa"] in ADRESAT or (w["klasa"] == "BRAK_CI" and w["etap"] == 2)):
            o = ops_zgloszenia(w, k)
            ops += o
            opis.append((w["klucz_zgl"], w["klasa"], o[0]["adresat"]))
    otwarte = set(klucz(r, p.get("number"), k.repa) for r in k.otwarte for p in k.otwarte[r])
    for sekcja in ("zgloszone", "przepiete"):
        for kk in sorted(k.st[sekcja]):
            if ":" in kk:
                continue                                    # zgłoszenia o gałęzi głównej i rejestrze wygasają z wiekiem
            rn = z_klucza(kk, k.repa)
            if rn is None or (rn[0] not in bledy and kk not in otwarte):
                ops.append({"op": "stan_del", "sekcja": sekcja, "klucz": kk})
    if ops:
        idy = _zapisz_ops(k.repo, ops, k.teraz)[1]
    for r in bledy:
        print("BŁĄD GH: %s – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu" % r)
    for kz, kl_, adr in opis:
        print("ZGŁOSZONO: %s %s -> %s%s" % (kz, kl_, adr, " (%s)" % idy[kz] if kz in idy else " (wpis już był w skrzynce)"))
    if not opis:
        print("NIC DO ZGŁOSZENIA")
    return 1 if bledy and len(bledy) == len(k.repa) else 0


def _pr_klucza(k, kk, pola, f_pr):
    """-> (owner/repo, numer, klucz kanoniczny, PR) albo (None, komunikat, kod wyjścia, None)."""
    rn = z_klucza(kk, k.repa)
    if rn is None:
        return None, "ZŁE WYWOŁANIE: nieznany klucz PR-a „%s” (numer albo <nazwa-repo>#numer)" % czysc(kk, 40), 2, None
    pr = f_pr(rn[0], rn[1], pola)
    if not pr or not re.match(r"^[0-9a-f]{40,64}$", str(pr.get("headRefOid") or "").lower()):
        return None, "STAN NIEZNANY: GitHub nie zwrócił PR-a %s – niczego nie zapisano; spróbuj w następnym przebiegu" % kk, 1, None
    return rn[0], int(rn[1]), klucz(rn[0], int(rn[1]), k.repa), pr


def cmd_zglos_jeden(k, kk, kl_, powod, f_pr=jeden_pr):
    """Czynność agenta z tabeli nie przeszła: pilne zlecenie do CEO i zapis, żeby nie ponawiać jej co kwadrans."""
    r, nr, kan, pr = _pr_klucza(k, kk, "number,title,headRefName,headRefOid", f_pr)
    if r is None:
        print(nr)
        return kan
    w = wiersz_prosty(pr, r, k, kl_, "czynność agenta nie powiodła się")
    idy = _zapisz_ops(k.repo, ops_zgloszenia(w, k, powod=powod or "(bez opisu)"), k.teraz)[1]
    print("ZGŁOSZONO: %s %s -> ceo%s" % (kan, kl_, " (%s)" % idy[kan] if kan in idy else " (wpis już był w skrzynce)"))
    return 0


def cmd_odnotuj(k, kk, kl_, f_pr=jeden_pr):
    """Własna czynność wykonana (zmiana bazy, ponowienie CI) – zapis, żeby nie powtarzać jej dla tego samego commita."""
    r, nr, kan, pr = _pr_klucza(k, kk, "number,headRefOid", f_pr)
    if r is None:
        print(nr)
        return kan
    _zapisz_ops(k.repo, [{"op": "stan_set", "sekcja": "zgloszone", "klucz": kan,
                          "wartosc": {"sha": str(pr["headRefOid"]).lower(), "klasa": kl_, "kiedy": k.teraz.strftime("%Y-%m-%d %H:%M"),
                                      "etap": 1, "adresat": "własna"}}], k.teraz)
    print("ODNOTOWANO: %s %s" % (kan, kl_))
    return 0


def cmd_przepiecie(k, kk, f_pr=jeden_pr):
    """Przed zmianą bazy: lista plików, którą widziała recenzja. Zapis trafia do kolejki oczekujących (poza gitem), zanim
    agent dotknie PR-a – po zmianie bazy tej listy nie da się już odtworzyć."""
    r, nr, kan, pr = _pr_klucza(k, kk, "number,headRefOid,baseRefName,files,changedFiles", f_pr)
    if r is None:
        print(nr)
        return kan
    if str(pr.get("baseRefName") or "") == k.ust["galaz_glowna"]:
        print("POMIŃ: PR %s ma już bazę %s – niczego nie zapisano" % (kan, k.ust["galaz_glowna"]))
        return 1
    lista, ile = pliki(pr), pr.get("changedFiles")
    if not lista or (isinstance(ile, int) and ile != len(lista)) or len(lista) >= 100:
        print("LISTA PLIKÓW NIEPEŁNA: PR %s (%d z %s) – bazy nie zmieniaj; zgłoś: zglos %s PRZEPNIJ --powod \"lista plików niepełna\""
              % (kan, len(lista), ile if ile is not None else "?", kan))
        return 1
    _zapisz_ops(k.repo, [{"op": "stan_set", "sekcja": "przepiete", "klucz": kan,
                          "wartosc": {"sha": str(pr["headRefOid"]).lower(), "z_bazy": czysc(pr.get("baseRefName"), 80),
                                      "kiedy": k.teraz.strftime("%Y-%m-%d %H:%M"), "pliki": lista}}], k.teraz)
    print("ZAPISANO stan sprzed zmiany bazy: %s (%d plików) – teraz polecenia z tabeli" % (kan, len(lista)))
    return 0


def cmd_potwierdz(k, kk, kto, f_pr=jeden_pr):
    """Po `gh pr merge`: wiersz dziennika powstaje dopiero wtedy, gdy GitHub potwierdza scalenie – nie na słowo agenta."""
    r, nr, kan, pr = _pr_klucza(k, kk, "number,state,mergeCommit,headRefOid,mergedAt", f_pr)
    if r is None:
        print(nr)
        return kan
    if str(pr.get("state") or "").upper() != "MERGED":
        print("NIE SCALONY: PR %s ma stan %s – scalenia nie zapisano; odmowę GitHuba zgłoś: zglos %s GOTOWY --powod \"…\""
              % (kan, czysc(pr.get("state"), 20) or "nieznany", kan))
        return 1
    w = k.rec.get(kan) if isinstance(k.rec.get(kan), dict) else {}
    kiedy_w, dokladny = czas_werdyktu(w)
    scalono = czas_gh(pr.get("mergedAt"), k.repo) or k.teraz
    commit = pr["mergeCommit"].get("oid") if isinstance(pr.get("mergeCommit"), dict) else ""
    linia = {"kiedy": scalono.strftime("%Y-%m-%d %H:%M"), "klucz": kan, "repo": r, "nr": nr, "sha": str(pr["headRefOid"]).lower(),
             "commit": czysc(commit, 64), "kto": kto, "werdykt": czysc(w.get("wynik"), 20),
             "min_od_werdyktu": min_od(kiedy_w, scalono), "czas_dokladny": bool(dokladny)}
    _zapisz_ops(k.repo, [{"op": "dziennik", "linia": linia}, {"op": "stan_del", "sekcja": "zgloszone", "klucz": kan},
                         {"op": "stan_del", "sekcja": "przepiete", "klucz": kan}], k.teraz)
    print("POTWIERDZONO: %s scalony (%s)%s" % (kan, linia["commit"][:10] or "commit nieznany",
                                               "" if linia["min_od_werdyktu"] is None else ", %d min od werdyktu" % linia["min_od_werdyktu"]))
    return 0


def commit_i_push(wt, sciezki_, opis, g):
    """-> (True, skrót commita | "bez zmian") | (False, powód). Zwykły commit i zwykły push: bez rebase, bez --force."""
    kod, _, err = git(wt, "add", "--", *sciezki_)
    if kod != 0:
        return False, "git add: " + czysc(err, 120)
    if git(wt, "diff", "--cached", "--quiet")[0] == 0:
        return True, "bez zmian"
    kto = [] if git(wt, "config", "user.email")[1].strip() else ["-c", "user.name=scalanie", "-c", "user.email=scalanie@localhost"]
    kod, _, err = uruchom(["git", "-C", str(wt)] + kto + ["commit", "-q", "-m", opis, "--"] + list(sciezki_), timeout=120)
    if kod != 0:
        return False, "git commit: " + czysc(err, 120)
    kod, _, err = git(wt, "push", "-q", "origin", "HEAD:refs/heads/" + g, timeout=120)
    if kod != 0:
        return False, "git push: " + czysc(err, 120)
    return True, git(wt, "rev-parse", "--short=10", "HEAD")[1].strip() or "zapisane"


def cmd_zapisz(repo, ust, teraz):
    """Wypycha zapisy na gałąź główną. Zawsze od zera – świeża gałąź główna + kolejka oczekujących – więc cudzy push
    w międzyczasie nie wymaga rebase, a zapisy przerwanego przebiegu dokończy następny."""
    wt, g, powod = pathlib.Path(repo), ust["galaz_glowna"], ""
    ops = oczekujace(wt)
    if not ops:
        print("NIC DO ZAPISANIA")
        return 0
    for _ in range(3):
        kod, _, err = git(wt, "fetch", "-q", "origin", timeout=120)
        if kod != 0:
            powod = "git fetch: " + czysc(err, 120)
            continue
        ok, err = _na_swieza(wt, g)
        if not ok:
            powod = "git checkout: " + err
            continue
        try:
            zmienione = zastosuj(wt, ops, teraz)[0]
        except OSError as e:
            print("BŁĄD SYSTEMU PLIKÓW: zapisów nie da się nałożyć (%s) – czekają poza gitem" % e.__class__.__name__)
            return 12
        if not zmienione:
            wyczysc_oczekujace(wt)
            print("ZAPISANE: wszystko było już na gałęzi głównej")
            return 0
        ok, wyn = commit_i_push(wt, zmienione, "scalanie: stan kolejki %s" % teraz.strftime("%Y-%m-%d %H:%M"), g)
        if ok:
            wyczysc_oczekujace(wt)
            print("ZAPISANE: %s (%s)" % (wyn, ", ".join(zmienione)))
            return 0
        powod = wyn
    print("NIE ZAPISANO po 3 próbach (%s) – %d zapisów czeka poza gitem (%s); dokończy je następny przebieg"
          % (powod, len(ops), sciezki(wt)["oczekujace"]))
    return 1


# ---------- polecenia CEO: wstrzymaj, zwolnij ----------

def rola(repo):
    """Rola sesji tak, jak widzi ją hook uprawnień: AGENT_ROLA albo plik .agent-rola; brak = "" (człowiek przy klawiaturze)."""
    r = os.environ.get("AGENT_ROLA") or ""
    if not r:
        try:
            r = (pathlib.Path(repo) / ".agent-rola").read_text(encoding="utf-8").strip()
        except OSError:
            r = ""
    return re.sub(r"[^a-z0-9-]", "", r.lower())


def na_swiezej_glownej(repo, ust, zmiana, opis):
    """Zmiana wprost na świeżej gałęzi głównej, w jednorazowym katalogu roboczym – wspólny katalog floty zostaje nietknięty.
    zmiana(wt) -> lista ścieżek | [] (nic do zrobienia) | tekst błędu. -> (kod, komunikat)."""
    g, powod = ust["galaz_glowna"], ""
    for _ in range(3):
        kod, _, err = git(repo, "fetch", "-q", "origin", timeout=120)
        if kod != 0:
            powod = "git fetch: " + czysc(err, 120)
            continue
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="scalanie-"))
        wt = tmp / "wt"
        try:
            kod, _, err = git(repo, "worktree", "add", "--detach", str(wt), "origin/" + g, timeout=120)
            if kod != 0:
                powod = "git worktree: " + czysc(err, 120)
                continue
            try:
                wyn = zmiana(wt)
            except OSError as e:
                return 12, "BŁĄD SYSTEMU PLIKÓW: %s" % e.__class__.__name__
            if isinstance(wyn, str):
                return 1, wyn
            if not wyn:
                return 0, "bez zmian"
            ok, co = commit_i_push(wt, wyn, opis, g)
            if ok:
                return 0, co
            powod = co
        finally:
            git(repo, "worktree", "remove", "--force", str(wt))
            shutil.rmtree(tmp, ignore_errors=True)
            git(repo, "worktree", "prune")
    return 1, "nie udało się po 3 próbach (%s)" % powod


REJESTR = "ceo/scalanie/wstrzymane.json"


def _rejestr(wt):
    """-> (rejestr, None) | (None, komunikat). Nieczytelnego pliku skrypt nie nadpisuje – naprawia go CEO."""
    tekst = lokalny(wt, REJESTR)
    if tekst is None:
        return {"wstrzymane": {}, "zwolnione": []}, None
    try:
        d = json.loads(tekst)
    except ValueError:
        d = None
    if not isinstance(d, dict) or not isinstance(d.get("wstrzymane"), dict) or any(not isinstance(v, dict) for v in d["wstrzymane"].values()):
        return None, "BŁĄD REJESTRU: %s na gałęzi głównej jest nieczytelny – napraw plik ręcznie (do tego czasu nic nie jest scalane)" % REJESTR
    if not isinstance(d.get("zwolnione"), list):
        d["zwolnione"] = []
    return d, None


def _zapisz_rejestr(wt, d):
    (wt / REJESTR).parent.mkdir(parents=True, exist_ok=True)
    zapisz_plik(wt / REJESTR, json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return [REJESTR]


def _tylko_ceo(repo):
    r = rola(repo)
    if r in ("", "ceo"):
        return None
    return "ODMOWA: rejestr wstrzymań zapisuje tylko CEO (rola tej sesji: %s). Warunek do PR-a zgłoś w zlecenia/ceo.md." % r


def cmd_wstrzymaj(k, kk, powod, tylko_head, f_pr=jeden_pr, f_zmien=na_swiezej_glownej):
    """Warunek CEO spoza werdyktu recenzenta. Domyślnie do odwołania (nowy commit go nie zdejmuje); --head = tylko ten commit."""
    odmowa = _tylko_ceo(k.repo)
    if odmowa:
        print(odmowa)
        return 1
    r, nr, kan, pr = _pr_klucza(k, kk, "number,state,headRefOid", f_pr)
    if r is None:
        print(nr)
        return kan
    if str(pr.get("state") or "").upper() != "OPEN":
        print("PR %s nie jest otwarty – nie ma czego wstrzymywać" % kan)
        return 1
    wpis = {"sha": str(pr["headRefOid"]).lower(), "tryb": "head" if tylko_head else "do_odwolania", "powod": czysc(powod, 300),
            "kiedy": k.teraz.strftime("%Y-%m-%d %H:%M")}

    def zmiana(wt):
        d, blad = _rejestr(wt)
        if blad:
            return blad
        stary = d["wstrzymane"].get(kan) or {}
        if all(stary.get(p) == wpis[p] for p in ("sha", "tryb", "powod")):
            return []
        d["wstrzymane"][kan] = wpis
        return _zapisz_rejestr(wt, d)

    kod, kom = f_zmien(k.repo, k.ust, zmiana, "scalanie: wstrzymanie %s" % kan)
    if kod != 0:
        print(kom if kom.startswith("BŁĄD") else "NIE WSTRZYMANO: " + kom)
        return kod
    print("WSTRZYMANO: %s (%s) – %s. Kolejka czyta rejestr z gałęzi głównej; wspólny katalog odświeży `git pull`."
          % (kan, "tylko ten commit" if tylko_head else "do odwołania", kom))
    return 0


def cmd_zwolnij(k, kk, uzasadnienie, f_zmien=na_swiezej_glownej):
    odmowa = _tylko_ceo(k.repo)
    if odmowa:
        print(odmowa)
        return 1
    rn = z_klucza(kk, k.repa)
    if rn is None:
        print("ZŁE WYWOŁANIE: nieznany klucz PR-a „%s” (numer albo <nazwa-repo>#numer)" % czysc(kk, 40))
        return 2
    kan = klucz(rn[0], int(rn[1]), k.repa)

    def zmiana(wt):
        d, blad = _rejestr(wt)
        if blad:
            return blad
        h = d["wstrzymane"].pop(kan, None)
        if h is None:
            return "NIE WSTRZYMANY: %s nie ma wpisu w rejestrze na gałęzi głównej" % kan
        d["zwolnione"] = (d["zwolnione"] + [{"klucz": kan, "kiedy": k.teraz.strftime("%Y-%m-%d %H:%M"), "uzasadnienie": czysc(uzasadnienie, 300),
                                             "powod": h.get("powod"), "sha": h.get("sha")}])[-30:]
        return _zapisz_rejestr(wt, d)

    kod, kom = f_zmien(k.repo, k.ust, zmiana, "scalanie: zwolnienie %s" % kan)
    if kod != 0:
        print(kom if kom.startswith(("BŁĄD", "NIE WSTRZYMANY")) else "NIE ZWOLNIONO: " + kom)
        return kod
    print("ZWOLNIONO: %s – %s. We wspólnym katalogu wykonaj `git pull` – stara kopia rejestru dalej wstrzymuje (celowo)." % (kan, kom))
    return 0


# ---------- miary ----------

def _ranga(xs, p):
    """Percentyl metodą najbliższej rangi; pusta lista -> None."""
    xs = sorted(xs)
    return xs[max(1, -(-len(xs) * p // 100)) - 1] if xs else None


def cmd_miary(k, dni, jako_json, f_otwarte=otwarte_pr):
    """Czas od werdyktu do scalenia z dziennika (tylko wpisy z dokładnym czasem werdyktu) i trzy progi na żywo."""
    tekst = z_glownej(k.repo, WLASNE_PLIKI[1], k.ust)
    if tekst is None:
        tekst = lokalny(k.repo, WLASNE_PLIKI[1]) or ""
    od, wpisy, kto = k.teraz - dt.timedelta(days=dni), [], {}
    for l in tekst.splitlines():
        d = json_z(l, {})
        t = czas_iso(d.get("kiedy"))
        if t and t >= od:
            wpisy.append(d)
            n = czysc(d.get("kto"), 40) or "?"
            kto[n] = kto.get(n, 0) + 1
    czasy = [d["min_od_werdyktu"] for d in wpisy if d.get("czas_dokladny") is True
             and isinstance(d.get("min_od_werdyktu"), (int, float)) and d["min_od_werdyktu"] >= 0]
    stare, konflikty, bledy = 0, 0, []
    for r in k.repa:
        lista = f_otwarte(r)
        if lista is None:
            bledy.append(r)
            continue
        for p in [x for x in lista if isinstance(x, dict) and not x.get("isDraft")]:
            if str(p.get("mergeable") or "").upper() == "CONFLICTING":
                konflikty += 1
            w = k.rec.get(klucz(r, p.get("number"), k.repa))
            sha = str(w.get("sha") or "").lower() if isinstance(w, dict) else ""
            if len(sha) >= 7 and str(p.get("headRefOid") or "").lower().startswith(sha) and str(w.get("wynik") or "").upper().startswith("OK"):
                wiek = min_od(czas_werdyktu(w)[0], k.teraz)
                if wiek is not None and wiek > k.prg["werdykt_ok_niescalony_h"] * 60:
                    stare += 1
    tetno_min = None if k.tetno_s is None else max(0, int((k.teraz_s - k.tetno_s) // 60))
    progi_ = [("PR-y z werdyktem OK niescalone ponad %d h" % k.prg["werdykt_ok_niescalony_h"], None if bledy else stare, k.prg["werdykt_ok_niescalony_max"]),
              ("PR-y w konflikcie", None if bledy else konflikty, k.prg["pr_konflikty_max"]),
              ("minuty od ostatniego przebiegu agenta scalającego", tetno_min, k.prg["gotowy_rezerwa_ceo_min"])]
    wyn = {"okno_dni": dni, "scalone": len(wpisy), "kto": kto, "z_dokladnym_czasem": len(czasy), "mediana_min": _ranga(czasy, 50),
           "p90_min": _ranga(czasy, 90), "zgloszone": len(k.st["zgloszone"]), "wstrzymane": len(k.wstrz), "bledy_gh": bledy,
           "progi": [{"miara": n, "wartosc": v, "prog": p, "stan": "BRAK DANYCH" if v is None else "OK" if v <= p else "PRZEKROCZONY"}
                     for n, v, p in progi_]}
    if jako_json:
        print(json.dumps(wyn, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("MIARY SCALANIA %s – ostatnie %d dni" % (k.teraz.strftime("%Y-%m-%d %H:%M"), dni))
    print("scalone PR-y: %d%s" % (len(wpisy), " (" + ", ".join("%s %d" % x for x in sorted(kto.items())) + ")" if kto else ""))
    if czasy:
        print("czas od werdyktu do scalenia: mediana %d min, p90 %d min (z %d wpisów z dokładnym czasem werdyktu)"
              % (wyn["mediana_min"], wyn["p90_min"], len(czasy)))
    else:
        print("czas od werdyktu do scalenia: brak danych (werdykty bez pola `kiedy` albo brak scaleń w oknie)")
    print("otwarte zgłoszenia kolejki: %d · wstrzymania CEO: %d" % (wyn["zgloszone"], wyn["wstrzymane"]))
    for r in bledy:
        print("BŁĄD GH: %s – lista PR-ów nieczytelna, progi na żywo bez danych" % r)
    for p in wyn["progi"]:
        print("%s: %s (próg %s) – %s" % (p["miara"], "brak" if p["wartosc"] is None else p["wartosc"], p["prog"], p["stan"]))
    return 0


# ---------- bramka scalania (wywołuje ją hook .claude/hooks/uprawnienia.py przed każdym `gh pr merge`) ----------

BRAMKA_TERMIN_S = 40                    # łączny czas git + gh w bramce; hook ma na całość 60 s (.claude/settings.json)
CEO_SCALA = ("WARUNEK", "DECYZJA", "WYJATEK", "MIGRACJA", "GLOWNA_CZERWONA", "CZEKA_NA_GLOWNA")   # klasy, które CEO może scalić sam
_FLAGA_REPO = r"(?:\s+(?:-R|--repo)(?:\s+|=)\S+)*"
RE_SCAL = re.compile(r"\bgh\b" + _FLAGA_REPO + r"\s+pr\b" + _FLAGA_REPO + r"\s+merge\b", re.I)
RE_SCAL_SCISLE = re.compile(r"^gh pr merge$", re.I)
WZOR_SCALENIA = "gh pr merge <nr> --repo <właściciel/nazwa> --<metoda> --match-head-commit <pełny SHA>"


def rozbierz_scalenie(polecenie):
    """Polecenie powłoki -> ((repo_gh, nr, sha, metoda), "") albo (None, powód). Przechodzi tylko postać z tabeli kolejki:
    jedno scalenie na polecenie, numer, --repo, jedna metoda i --match-head-commit z pełnym SHA; każdy inny składnik = odmowa
    (--admin, --auto, --delete-branch, przekierowania, podstawienia powłoki)."""
    tekst = str(polecenie or "")
    wzor = "dozwolona postać: " + WZOR_SCALENIA
    trafienia = list(RE_SCAL.finditer(tekst))
    if len(trafienia) != 1:
        return None, "jedno scalenie na polecenie (znaleziono %d) – %s" % (len(trafienia), wzor)
    m = trafienia[0]
    if not RE_SCAL_SCISLE.match(re.sub(r"\s+", " ", m.group(0))):
        return None, "flagi między `gh pr` a `merge` – " + wzor
    ogon = re.sub(r"\s2>&1(?=\s|$)", " ", tekst[m.end():])
    ogon = re.split(r"[;\n|]|&&", ogon, maxsplit=1)[0]
    if re.search(r"[`$<>&(){}\\]", ogon):
        return None, "podstawienia i przekierowania powłoki w poleceniu scalenia – " + wzor
    try:
        zetony = shlex.split(ogon)
    except ValueError:
        return None, "nieczytelne cudzysłowy w poleceniu – " + wzor
    nr = repo_gh = sha = metoda = None
    i = 0
    while i < len(zetony):
        z = zetony[i]
        i += 1
        nazwa, znak, wart = z.partition("=")
        if nazwa in ("--repo", "--match-head-commit") or z == "-R":
            if not znak:
                if i >= len(zetony):
                    return None, "flaga %s bez wartości – %s" % (nazwa, wzor)
                wart = zetony[i]
                i += 1
            if nazwa == "--match-head-commit":
                if sha is not None:
                    return None, "--match-head-commit podane dwa razy – " + wzor
                sha = wart
            else:
                if repo_gh is not None:
                    return None, "--repo podane dwa razy – " + wzor
                repo_gh = wart
        elif z in ("--merge", "--squash", "--rebase"):
            if metoda is not None:
                return None, "więcej niż jedna metoda scalenia – " + wzor
            metoda = z[2:]
        elif re.match(r"^\d{1,9}$", z):
            if nr is not None:
                return None, "więcej niż jeden numer PR-a – " + wzor
            nr = int(z)
        else:
            return None, "niedozwolony składnik „%s” – %s" % (czysc(z, 40), wzor)
    braki = [n for n, v in (("numer PR-a", nr), ("--repo", repo_gh), ("metoda", metoda), ("--match-head-commit", sha)) if v is None]
    if braki:
        return None, "brakuje: %s – %s" % (", ".join(braki), wzor)
    if not re.match(r"^[\w.-]+/[\w.-]+$", repo_gh):
        return None, "--repo: oczekiwane właściciel/nazwa – " + wzor
    if not re.match(r"^[0-9a-fA-F]{40,64}$", sha):
        return None, "--match-head-commit: oczekiwany pełny SHA commita (40 znaków) – " + wzor
    return (repo_gh, nr, sha.lower(), metoda), ""


def przeszkody(pr, repo_gh, k):
    """Wszystkie fakty o PR-ze naraz – klasyfikacja kończy na pierwszej przeszkodzie, a ścieżka CEO musi znać każdą.
    -> (twarde, wlasciciel): `twarde` – nie scala nikt; `wlasciciel` – CEO scala tylko z przyjętą decyzją właściciela."""
    ust, twarde, wlasc = k.ust, [], []
    kk = klucz(repo_gh, pr.get("number"), k.repa)
    head = str(pr.get("headRefOid") or "").lower()
    if k.wstrz_blad:
        twarde.append("rejestr wstrzymań nieczytelny")
    h = k.wstrz.get(kk)
    if isinstance(h, dict):
        hs = str(h.get("sha") or "").lower()
        if not hs or head.startswith(hs) or h.get("tryb") != "head":
            twarde.append("wstrzymany przez CEO (%s) – najpierw `zwolnij`" % czysc(h.get("powod"), 60))
    if not re.match(r"^[0-9a-f]{40,64}$", head):
        twarde.append("nieczytelny head")
    if pr.get("isDraft") or RE_CZLOWIEK.search(str(pr.get("title") or "")):
        twarde.append("szkic albo PR wyłączony z recenzji")
    w = k.rec.get(kk)
    if not isinstance(w, dict):
        twarde.append("brak werdyktu recenzenta")
        w = {}
    else:
        sha = str(w.get("sha") or "").strip().lower()
        if len(sha) < 7 or not re.match(r"^[0-9a-f]+$", sha) or not head.startswith(sha):
            twarde.append("werdykt dotyczy innego commita")
        pol, uw = werdykt_pol(w, repo_gh, k, pr)
        if pol in ("NIE", "NIEJASNY", "ZALEZNOSC"):
            twarde.append("werdykt: %s%s" % (pol, (" – " + uw) if uw else ""))
    if str(pr.get("baseRefName") or "") != ust["galaz_glowna"]:
        twarde.append("baza PR-a nie jest gałęzią główną")
    if str(pr.get("mergeable") or "").upper() != "MERGEABLE":
        twarde.append("GitHub nie potwierdza scalalności (konflikt albo liczenie w toku)")
    stan_ci, zle = ci(pr, repo_gh, ust)
    if stan_ci != "OK":
        twarde.append("CI: %s%s" % (stan_ci, (" – " + ", ".join(zle[:3])) if zle else ""))
    sc = pliki(pr)
    prz = k.st["przepiete"].get(kk)
    if isinstance(prz, dict) and prz.get("sha") == head and w.get("po_przepieciu") is not True \
            and sorted(prz.get("pliki") or []) != sc:
        twarde.append("po zmianie bazy lista plików inna niż w recenzji")
    ile = pr.get("changedFiles")
    if not sc or (isinstance(ile, int) and ile != len(sc)) or len(sc) >= 100:
        wlasc.append("lista plików pusta albo niepełna – ścieżek nie da się sprawdzić")
    if repo_gh == k.org_github:
        chronione_wz = sorted(set(UST_DOMYSLNE["wlasciciel"]) | set(ust.get("wlasciciel") or []))   # plik może listę tylko wydłużyć
        chronione = [p for p in sc if pasuje(p, chronione_wz)]
        if chronione:
            wlasc.append("zasady i uprawnienia: " + ", ".join(czysc(p, 50) for p in chronione[:3]))
    km = w.get("klasa_migracji")
    if any(pasuje(p, ust["migracje"]) for p in sc) or km:
        kol = k.kolizja(repo_gh, pr.get("number"), sc)
        if kol is None:
            twarde.append("numerów migracji na gałęzi głównej nie udało się sprawdzić")
        elif kol:
            twarde.append(kol)
        klasy = sorted(set(str(v).strip().upper() for v in km.values())) if isinstance(km, dict) and km else []
        if klasy != ["A"]:
            wlasc.append("migracja klasy B albo bez klasy")
    return twarde, wlasc


def _bramka(repo, polecenie, rola_, decyzja, teraz, teraz_s, f_pr, f_glowna, f_otwarte, f_fetch):
    stop = stop_awaryjny(repo)
    if stop:
        return False, "flota zatrzymana (bezpieczenstwo/HALT): %s – niczego nie scalamy; plik usuwa operator" % stop
    rola_ = rola(repo) if rola_ is None else re.sub(r"[^a-z0-9-]", "", str(rola_ or "").lower())
    repa = repozytoria(repo)
    if not repa:
        return False, "BRAK REPOZYTORIÓW: uzupełnij repo.github / repo.produkt w org.yaml"
    wyn, powod = rozbierz_scalenie(polecenie)
    if wyn is None:
        return False, powod
    repo_gh, nr, sha, metoda = wyn
    zgodne = [r for r in repa if r.lower() == repo_gh.lower()]
    if not zgodne:
        return False, "repozytorium %s nie należy do organizacji (org.yaml)" % czysc(repo_gh, 60)
    repo_gh = zgodne[0]
    pobrane = f_fetch(repo) if f_fetch else git(repo, "fetch", "-q", "origin", timeout=30)[0] == 0
    if not pobrane:
        return False, "git fetch nie powiódł się – werdykty i wstrzymania mogły się zmienić; spróbuj ponownie"
    ust = ustawienia_uzgodnione(repo)
    if metoda != ust["metoda"]:
        return False, "metoda --%s, a ustawienia kolejki wymagają --%s" % (metoda, ust["metoda"])
    prg = progi(repo)
    teraz_s = epoka(repo) if teraz_s is None else teraz_s
    b = blokada_info(sciezki(repo)["blokada"])
    if b is None or teraz_s - b["od_s"] > prg["blokada_scalania_min"] * 60:
        return False, "brak ważnej blokady scalania – najpierw `python3 -I scripts/scalanie.py blokada <kto>`"
    k = _kontekst(repo, teraz or teraz_org(repo), teraz_s, ust=ust)
    pr = f_pr(repo_gh, nr)
    if not isinstance(pr, dict) or pr.get("number") != nr:
        return False, "GitHub nie zwrócił PR-a %s#%d" % (repo_gh, nr)
    head = str(pr.get("headRefOid") or "").lower()
    if head != sha:
        return False, ("--match-head-commit %s… nie jest aktualnym commitem PR-a (%s…) – weź polecenie ze świeżej tabeli"
                       % (sha[:10], head[:10] or "?"))
    werd = k.rec.get(klucz(repo_gh, nr, k.repa))
    if any(pasuje(p, ust["migracje"]) for p in pliki(pr)) or (isinstance(werd, dict) and werd.get("klasa_migracji")):
        inne = f_otwarte(repo_gh)
        if inne is None:
            return False, "lista otwartych PR-ów niedostępna – kolizji numerów migracji nie da się sprawdzić"
        k.otwarte[repo_gh] = inne
    w = wiersz(pr, repo_gh, k)
    zatrzymaj_na_rejestrze([w], k)
    zatrzymaj_na_czerwonej([w], k, f_glowna)
    kl_, opis = w["klasa"], "%s#%d %s" % (repo_gh, nr, head[:10])
    if kl_ in SCALA:
        return True, "GOTOWY " + opis
    if rola_ != "ceo" or kl_ not in CEO_SCALA:
        return False, "%s ma klasę %s%s – adresat: %s; bez decyzji CEO scala się tylko klasę GOTOWY" % (
            opis, kl_, (" (%s)" % w["uwaga"]) if w["uwaga"] else "", w["adresat"])
    if not str(b.get("kto") or "").startswith("ceo"):
        return False, ("%s, klasa %s – ścieżka CEO wymaga blokady wziętej jako ceo-czat albo ceo-przebieg (teraz trzyma ją „%s”)"
                       % (opis, kl_, czysc(b.get("kto"), 30)))
    twarde, wlasc = przeszkody(pr, repo_gh, k)
    if twarde:
        return False, "%s, klasa %s – przeszkody, których nie usuwa decyzja CEO: %s" % (opis, kl_, "; ".join(twarde[:4]))
    if wlasc and not decyzja:
        return False, "%s, klasa %s – potrzebna decyzja właściciela (prefiks DECYZJA=D-RRRRMMDD-NN przed poleceniem): %s" % (
            opis, kl_, "; ".join(wlasc[:3]))
    return True, "%s %s – ścieżka CEO%s" % (kl_, opis, " z decyzją właściciela" if wlasc else "")


def bramka(repo, polecenie, rola_=None, decyzja=False, teraz=None, teraz_s=None,
           f_pr=jeden_pr, f_glowna=glowna_ci, f_otwarte=otwarte_pr, f_fetch=None):
    """Czy to polecenie `gh pr merge` wolno wykonać -> (True, opis) | (False, powód). Wątpliwość, błąd i brak czasu = odmowa.
    GOTOWY przechodzi niezależnie od roli (agent scalający pracuje w prywatnym katalogu, bez pliku roli); pozostałe klasy
    z listy CEO_SCALA tylko dla roli `ceo`, po ponownym sprawdzeniu wszystkich faktów, a część tylko z decyzją właściciela."""
    global TERMIN
    TERMIN = time.monotonic() + BRAMKA_TERMIN_S
    try:
        wolno, opis = _bramka(pathlib.Path(repo), polecenie, rola_, decyzja, teraz, teraz_s, f_pr, f_glowna, f_otwarte, f_fetch)
        if wolno and time.monotonic() >= TERMIN:
            return False, "bramka nie zdążyła sprawdzić faktów w %d s – spróbuj ponownie" % BRAMKA_TERMIN_S
        return wolno, opis
    except Exception as e:                                  # bramka nie ma prawa przepuścić przez własny błąd
        return False, "błąd bramki scalania (%s) – zgłoś CEO" % e.__class__.__name__
    finally:
        TERMIN = None


# ---------- wywołanie ----------

OPCJE_WARTOSC = ("--repo", "--teraz", "--protokol", "--kto", "--powod", "--dni", "--token")
OPCJE_FLAGA = ("--json", "--wszystko", "--head")


def _opcje(a):
    """-> (argumenty pozycyjne, {opcja: wartość}) albo None przy złym wywołaniu."""
    poz, opc, i = [], {}, 0
    while i < len(a):
        x = a[i]
        if x in OPCJE_WARTOSC:
            if i + 1 >= len(a):
                return None
            opc[x[2:]] = a[i + 1]
            i += 2
        elif x in OPCJE_FLAGA:
            opc[x[2:]] = True
            i += 1
        elif x.startswith("--"):
            return None
        else:
            poz.append(x)
            i += 1
    return poz, opc


def _zle(powod=""):
    if powod:
        print("ZŁE WYWOŁANIE: " + powod, file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


def _stan_z(tekst):
    d = json_z(tekst, {})
    return {"zgloszone": d.get("zgloszone") if isinstance(d.get("zgloszone"), dict) else {},
            "przepiete": d.get("przepiete") if isinstance(d.get("przepiete"), dict) else {}}


def _kontekst(repo, teraz, teraz_s, ust=None):
    """Poza katalogiem roboczym stan kolejki pochodzi z gałęzi głównej – kopia we wspólnym katalogu bywa nieświeża."""
    ust, st = (ust if ust is not None else ustawienia(repo)), None
    try:
        w_katalogu = repo.resolve() == sciezki(repo)["katalog"].resolve()
    except OSError:
        w_katalogu = False
    if not w_katalogu:
        tekst = z_glownej(repo, WLASNE_PLIKI[0], ust)
        if tekst is not None:
            st = _stan_z(tekst)
    return Kontekst(repo, teraz=teraz, teraz_s=teraz_s, tetno_s=tetno(repo), ust=ust, st=st)


def main(a):
    wyn = _opcje(a)
    if wyn is None:
        return _zle()
    poz, opc = wyn
    repo = pathlib.Path(opc.get("repo") or pathlib.Path(__file__).resolve().parent.parent).resolve()
    polecenie, arg = (poz[0] if poz else "tabela"), poz[1:]
    try:
        teraz, teraz_s = teraz_org(repo, opc.get("teraz")), epoka(repo, opc.get("teraz"))
    except ValueError:
        return _zle("--teraz: oczekiwany czas ISO, np. 2026-01-31T12:00")
    token = opc.get("token")
    if token is not None and not RE_TOKEN.match(token):
        return _zle("--token: oczekiwany token z polecenia `blokada`")

    if polecenie == "blokada":
        if len(arg) != 1 or not RE_KTO.match(arg[0]) or not re.match(r"^\d{1,6}$", opc.get("protokol") or "0"):
            return _zle("blokada <kto> [--protokol N]; <kto> np. scalanie-a, ceo-czat, ceo-przebieg")
        return cmd_blokada(repo, arg[0], int(opc["protokol"]) if opc.get("protokol") else None, teraz, teraz_s)
    if polecenie in ("odswiez", "odblokuj"):
        if len(arg) != 1 or not RE_TOKEN.match(arg[0]):
            return _zle("%s <token>" % polecenie)
        kod, kom = (odswiez if polecenie == "odswiez" else odblokuj)(repo, arg[0], teraz_s)
        print(kom)
        return kod

    if polecenie == "bramka":
        if len(arg) != 1:
            return _zle('bramka "<polecenie gh pr merge …>" – całe polecenie w jednym cudzysłowie')
        wolno, opis = bramka(repo, arg[0], teraz=teraz, teraz_s=teraz_s)
        print(("WOLNO: " if wolno else "ZABLOKOWANE: ") + opis)
        return 0 if wolno else 1

    if polecenie not in ("tabela", "miary", "zglos", "potwierdz", "przepiecie", "odnotuj", "zapisz", "wstrzymaj", "zwolnij"):
        return _zle("nieznane polecenie „%s”" % czysc(polecenie, 30))
    if len(arg) >= 1 and not RE_KLUCZ.match(arg[0]):
        return _zle("klucz PR-a: numer albo <nazwa-repo>#numer")
    pisze = polecenie in ("zglos", "potwierdz", "przepiecie", "odnotuj", "zapisz")
    if pisze:
        if token is None:
            return _zle("%s wymaga --token <token z polecenia blokada>" % polecenie)
        kod, inf = wymagaj(repo, token)
        if kod != 0:
            print(inf)
            return kod
        odswiez(repo, token, teraz_s)                       # każdy zapis przedłuża blokadę – długi przebieg nie zostanie przejęty
    if polecenie == "zapisz":
        return cmd_zapisz(repo, ustawienia(repo), teraz) if not arg else _zle("zapisz --token T")
    if not repozytoria(repo):
        print("BRAK REPOZYTORIÓW: uzupełnij repo.github / repo.produkt w org.yaml")
        return 1
    if polecenie in ("tabela", "miary", "zglos") and not arg:
        git(repo, "fetch", "-q", "origin", timeout=120)     # na ile się da; bez sieci liczy się stan ostatnio pobrany
    k = _kontekst(repo, teraz, teraz_s)

    if polecenie == "tabela":
        if arg:
            return _zle("tabela nie przyjmuje argumentów")
        wiersze, bledy = tabela(k)
        if opc.get("json"):
            print(json.dumps({"teraz": k.teraz.strftime("%Y-%m-%d %H:%M"), "wiersze": wiersze, "bledy": bledy, "uwagi": k.uwagi,
                              "pliki_sporne": [{"repo": r, "plik": s, "pr": n} for r, s, n in k.sporne],
                              "rezerwa": dict(zip(("stan", "powod"), rezerwa(wiersze, k)))}, ensure_ascii=False, indent=2))
        else:
            wypisz(wiersze, bledy, k, wszystko=bool(opc.get("wszystko")))
        return 1 if bledy and len(bledy) == len(k.repa) else 0
    if polecenie == "miary":
        if arg or not re.match(r"^\d{1,3}$", opc.get("dni") or "7") or int(opc.get("dni") or 7) < 1:
            return _zle("miary [--dni N] [--json]")
        return cmd_miary(k, int(opc.get("dni") or 7), bool(opc.get("json")))
    if polecenie == "zglos":
        if not arg:
            return cmd_zglos(k)
        if len(arg) != 2 or arg[1] not in SCALA + WLASNE or not (opc.get("powod") or "").strip():
            return _zle("zglos <klucz> <%s> --powod \"co odpowiedział GitHub\" --token T" % "|".join(SCALA + WLASNE))
        return cmd_zglos_jeden(k, arg[0], arg[1], opc["powod"])
    if polecenie == "potwierdz":
        kto = opc.get("kto") or inf["kto"]
        if len(arg) != 1 or not RE_KTO.match(kto):
            return _zle("potwierdz <klucz> [--kto X] --token T")
        return cmd_potwierdz(k, arg[0], kto)
    if polecenie == "przepiecie":
        return cmd_przepiecie(k, arg[0]) if len(arg) == 1 else _zle("przepiecie <klucz> --token T")
    if polecenie == "odnotuj":
        if len(arg) != 2 or arg[1] not in WLASNE:
            return _zle("odnotuj <klucz> <%s> --token T" % "|".join(WLASNE))
        return cmd_odnotuj(k, arg[0], arg[1])
    if len(arg) != 2 or not arg[1].strip():
        return _zle("%s <klucz> \"%s\"%s" % (polecenie, "powód" if polecenie == "wstrzymaj" else "uzasadnienie",
                                              " [--head]" if polecenie == "wstrzymaj" else ""))
    return cmd_wstrzymaj(k, arg[0], arg[1], bool(opc.get("head"))) if polecenie == "wstrzymaj" else cmd_zwolnij(k, arg[0], arg[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
