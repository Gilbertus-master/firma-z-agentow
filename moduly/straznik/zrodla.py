"""Strażnik floty – pobieranie danych dla kontroli (pliki repo, git, gh, App Store Connect, Supabase).

Każde źródło zwraca dane albo {"blad": "<komunikat>"} – nigdy wyjątek do góry. Sekrety (token Supabase) tylko w pamięci
procesu, ze środowiska albo z pęku kluczy macOS; w komunikatach błędów są maskowane.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import kontrole as K

# Konfiguracja organizacji – ustawia konfiguruj(czytaj_org(repo)) na starcie przebiegu (org.yaml). Poniżej wartości
# domyślne (repo bez org.yaml) i nadpisania ze środowiska (STRAZNIK_*). Zmienne wtyczek czytane przy każdym wywołaniu
# źródła: STRAZNIK_ASC, STRAZNIK_SQL_BUILD, STRAZNIK_FLY_REPO, STRAZNIK_FLY_WORKFLOW, STRAZNIK_PAGES.
GH_ORG = os.environ.get("STRAZNIK_GH_ORG", "OWNER")          # org.yaml → repo.github (właściciel)
REPO_PR = ("produkt", "organizacja")                          # repo produktu + repo organizacji (nazwy bez właściciela)
REPO_PRODUKT = ()                                             # org.yaml → repo.produkt (nazwy bez właściciela)
PREFIKS = "org"                                               # org.yaml → organizacja.prefiks (zadania <prefiks>-<agent>-<konto>)
KONTA = ("A",)                                                # org.yaml → runtime.konta
RUNTIME = "desktop-scheduled"                                 # org.yaml → runtime.glowny
KONTROLE_WSZYSTKIE = ("przebiegi", "pr", "testflight", "automaty", "zlecenia", "konfiguracja", "budzety", "martwe")
KONTROLE_RDZEN = ("przebiegi", "pr", "zlecenia", "konfiguracja", "budzety", "martwe")
KONTROLE_AKTYWNE = KONTROLE_WSZYSTKIE                         # org.yaml → straznik.kontrole (wtyczki: testflight, automaty)
SUPABASE_PROJEKT = os.environ.get("STRAZNIK_SUPABASE_PROJEKT", "")  # wtyczka automaty (Supabase)
SUPABASE_PAT_USLUGA = "supabase-pat-straznik"
ASC_BUNDLE = os.environ.get("STRAZNIK_ASC_BUNDLE", "")        # wtyczka testflight (App Store)
LIMIT_ZRODLA_S = 45
RE_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{4,}(?:\.[A-Za-z0-9_-]*){0,2}")


class BladZrodla(Exception):
    pass


def maskuj(tekst, sekrety=()):
    """Sekrety z pęku -> ***, a także wszystko, co wygląda jak JWT (eyJ…) – np. błędy modułu asc z katalogu kluczy."""
    for m in sekrety or ():
        if m:
            tekst = tekst.replace(m, "***")
    return RE_JWT.sub("***", tekst)


def jest_timeout(e):
    if isinstance(e, (socket.timeout, TimeoutError, subprocess.TimeoutExpired)):
        return True
    if isinstance(e, urllib.error.URLError) and isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
        return True
    return "timed out" in str(e).lower()


def z_ponowieniem(f, *a):
    """Jedna ponowna próba, gdy źródło przekroczyło czas; inne błędy od razu."""
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001
        if not jest_timeout(e):
            raise
    return f(*a)


def uruchom(cmd, timeout=15, cwd=None):
    p = None
    for _ in range(2):  # 1 ponowienie przy przekroczeniu czasu
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
            break
        except FileNotFoundError:
            raise BladZrodla("brak programu %s" % cmd[0])
        except subprocess.TimeoutExpired:
            continue
    if p is None:
        raise BladZrodla("%s: przekroczony czas %d s (2 próby)" % (cmd[0], timeout))
    if p.returncode != 0:
        raise BladZrodla("%s %s: kod %d: %s" % (cmd[0], cmd[1] if len(cmd) > 1 else "", p.returncode, (p.stderr or p.stdout).strip()[:300]))
    return p.stdout


def sekret(usluga):
    """Sekret ze środowiska (STRAZNIK_SEKRET_<USLUGA>, np. w CI) albo z pęku kluczy macOS (security); None gdy brak.
    Wartość tylko w pamięci."""
    ze_srodowiska = os.environ.get("STRAZNIK_SEKRET_" + re.sub(r"[^A-Za-z0-9]", "_", usluga).upper())
    if ze_srodowiska:
        return ze_srodowiska
    try:
        p = subprocess.run(["security", "find-generic-password", "-s", usluga, "-w"], capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    v = p.stdout.strip()
    return v if p.returncode == 0 and v else None


# ---------- org.yaml ----------

def _wartosc(v):
    v = v.strip()
    if v.startswith("[") and "]" in v:
        v = v[:v.index("]") + 1]  # komentarz po liście
    if v.startswith("[") and v.endswith("]"):
        return [_wartosc(x) for x in v[1:-1].split(",") if x.strip()]
    if v[:1] in ("'", '"'):
        return v[1:].split(v[0], 1)[0]
    return v.split(" #", 1)[0].strip()


def czytaj_org(repo):
    """Minimalny odczyt org.yaml (klucz: wartość, zagnieżdżenie wcięciami, listy [a, b]) – bez PyYAML. Brak pliku -> {}."""
    p = Path(repo) / "org.yaml"
    if not p.exists():
        return {}
    org, stos = {}, [(-1, None)]
    for linia in p.read_text(encoding="utf-8").splitlines():
        if not linia.strip() or linia.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$", linia)
        if not m:
            continue
        wciecie, klucz, reszta = len(m.group(1)), m.group(2), m.group(3)
        while stos and stos[-1][0] >= wciecie:
            stos.pop()
        rodzic = stos[-1][1] if stos and stos[-1][1] is not None else org
        if reszta.strip() == "" or reszta.lstrip().startswith("#"):
            rodzic[klucz] = {}
            stos.append((wciecie, rodzic[klucz]))
        else:
            rodzic[klucz] = _wartosc(reszta)
    return org


def _nazwa_repo(pelna):
    return str(pelna).rstrip("/").split("/")[-1]


def ustaw_pomin_tytul(z_org=None):
    """Filtr tytułów PR poza kontrolą: wyrażenie regularne (re.search) ze zmiennej STRAZNIK_POMIN_TYTUL albo z org.yaml →
    straznik.pomin_tytul; domyślnie brak (nic nie jest pomijane poza szkicami). Wzorzec nie do użycia = filtr wyłączony
    i uwaga w kontroli PR."""
    wzor = os.environ.get("STRAZNIK_POMIN_TYTUL") or z_org
    K.POMIN_TYTUL, K.POMIN_TYTUL_BLAD = None, None
    if not wzor:
        return
    if not isinstance(wzor, str):
        K.POMIN_TYTUL_BLAD = "straznik.pomin_tytul: wartość nie jest napisem (wyrażenie ujmij w cudzysłów) – filtr wyłączony"
        return
    try:
        K.POMIN_TYTUL = re.compile(wzor)
    except re.error as e:
        K.POMIN_TYTUL_BLAD = "filtr tytułów PR: niepoprawne wyrażenie regularne (%s) – filtr wyłączony" % e


def konfiguruj(org):
    """Ustawia globalne wartości modułów (zrodla, kontrole) z org.yaml. Zmienne STRAZNIK_* mają pierwszeństwo."""
    global GH_ORG, REPO_PR, REPO_PRODUKT, PREFIKS, KONTA, RUNTIME, KONTROLE_AKTYWNE
    st = (org or {}).get("straznik")
    ustaw_pomin_tytul(st.get("pomin_tytul") if isinstance(st, dict) else None)
    if not org:
        return org
    o, r, rt, st = org.get("organizacja", {}), org.get("repo", {}), org.get("runtime", {}), org.get("straznik", {})
    github = str(r.get("github", ""))
    if "/" in github and "STRAZNIK_GH_ORG" not in os.environ:
        GH_ORG = github.split("/")[0]
    produkt = r.get("produkt") or []
    if isinstance(produkt, str):
        produkt = [produkt] if produkt else []
    REPO_PRODUKT = tuple(dict.fromkeys(_nazwa_repo(x) for x in produkt))
    repa = list(REPO_PRODUKT) + ([_nazwa_repo(github)] if github else [])
    if repa:
        REPO_PR = tuple(dict.fromkeys(repa))
        K.REPO_BEZ_PREFIKSU = REPO_PR[0]
    PREFIKS = str(o.get("prefiks") or PREFIKS)
    konta = rt.get("konta") or ([rt["konto"]] if rt.get("konto") else [])
    if isinstance(konta, str):
        konta = [konta]
    if konta:
        KONTA = tuple(str(k).upper() for k in konta)
    RUNTIME = str(rt.get("glowny") or RUNTIME)
    kontrole = st.get("kontrole")
    if isinstance(kontrole, list) and kontrole:
        KONTROLE_AKTYWNE = tuple(k for k in KONTROLE_WSZYSTKIE if k in kontrole)
    elif "straznik" in org or "organizacja" in org:
        KONTROLE_AKTYWNE = KONTROLE_RDZEN
    strefa = o.get("strefa")
    if strefa:
        try:
            K.WAW = K.ZoneInfo(str(strefa))
        except Exception:  # noqa: BLE001 – zła strefa: zostaje domyślna
            pass
    return org


def bezpiecznie(f, *a, maska=None):
    try:
        return f(*a)
    except Exception as e:  # noqa: BLE001
        msg = "%s" % e if isinstance(e, BladZrodla) else "%s: %s" % (type(e).__name__, e)
        return {"blad": maskuj(msg, maska)[:400]}


# ---------- pliki repo ----------

def parsuj_dni(t):
    t = (t or "*").strip()
    if t == "*":
        return set(range(7))
    return {K.DNI[d.strip().lower()] for d in t.split(",")}


def czytaj_odstepy(repo):
    """koordynacja-odstepy.tsv: agent, odstep_min, poczatek, [dni, godziny, od]. Kolumny 4–6 opcjonalne:
    dni (* albo pn,wt,sr,cz,pt,so,nd), godziny (* = każde okienko, albo lista 8:45,10:45), od (RRRR-MM-DD GG:MM – od kiedy
    obowiązuje harmonogram; - = brak)."""
    wiersze = []
    for linia in (Path(repo) / "koordynacja-odstepy.tsv").read_text(encoding="utf-8").splitlines():
        if not linia.strip() or linia.startswith("#"):
            continue
        k = [x.strip() for x in linia.split("\t")] + ["", "", ""]
        godz = k[4] if k[4] not in ("", "*") else None
        od = K.parsuj_czas(k[5])[0] if k[5] not in ("", "-") else None
        if k[5] not in ("", "-") and od is None:
            raise BladZrodla("zła data od %r dla %s" % (k[5], k[0]))
        wiersze.append({"agent": k[0], "odstep": int(k[1]), "poczatek": K.hhmm_na_min(k[2]), "dni": parsuj_dni(k[3]),
                        "godziny": sorted(K.hhmm_na_min(g) for g in godz.split(",")) if godz else None, "od": od})
    if not wiersze:
        raise BladZrodla("pusty koordynacja-odstepy.tsv")
    return wiersze


def czytaj_stany(repo, agenci):
    stany = {}
    for a in agenci:
        p = Path(repo) / a / "stan.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            stany[a] = {"ostatni_przebieg": d.get("ostatni_przebieg") if isinstance(d, dict) else None}
        except (ValueError, OSError) as e:
            stany[a] = {"blad": "stan.json nieczytelny: %s" % type(e).__name__}
    return stany


def czytaj_recenzje(repo):
    d = json.loads((Path(repo) / "recenzent" / "stan.json").read_text(encoding="utf-8"))
    r = d.get("recenzje")
    if r is None:
        return {}  # świeży agent recenzent bez werdyktów
    if not isinstance(r, dict):
        raise BladZrodla("pole recenzje nie jest słownikiem")
    return r


def czytaj_zlecenia(repo):
    pliki = {p.name: p.read_text(encoding="utf-8") for p in sorted((Path(repo) / "zlecenia").glob("*.md"))}
    if not pliki:
        raise BladZrodla("brak plików zlecenia/*.md")
    return {"pliki": pliki}


def czytaj_rejestr(repo):
    return (Path(repo) / "aplikacje" / "opinie-testflight.md").read_text(encoding="utf-8")


def czytaj_zadania(katalog, agenci):
    """-> ({agent: {konto: tekst SKILL.md | None}}, [inne zadania <prefiks>-*-<konto> spoza tsv])."""
    k = Path(katalog)
    if not k.is_dir():
        raise BladZrodla("brak katalogu %s" % katalog)
    zadania = {}
    for a in agenci:
        zadania[a] = {}
        for konto in KONTA:
            p = k / ("%s-%s-%s" % (PREFIKS, a, konto.lower())) / "SKILL.md"
            zadania[a][konto] = p.read_text(encoding="utf-8") if p.exists() else None
    wzor = re.compile(r"%s-(.+)-(%s)" % (re.escape(PREFIKS), "|".join(re.escape(x.lower()) for x in KONTA)))
    inne = sorted(d.name for d in k.iterdir() if d.is_dir() and wzor.fullmatch(d.name) and wzor.fullmatch(d.name).group(1) not in agenci)
    return zadania, inne


# ---------- źródła zewnętrzne ----------

def parsuj_tagi(linie):
    tagi = {}
    for l in linie:
        ref = l.split()[-1] if l.strip() else ""
        m = re.fullmatch(r"(?:refs/tags/)?przebieg/([a-z0-9-]+)/(-?\d+)", ref)
        if m:
            tagi.setdefault(m.group(1), []).append(int(m.group(2)))
    return {a: sorted(set(v)) for a, v in tagi.items()}


def pobierz_tagi(repo):
    out = uruchom(["git", "-C", str(repo), "ls-remote", "--tags", "origin", "przebieg/*"], timeout=20)
    return parsuj_tagi(out.splitlines())


def gh_json(args, timeout=15):
    out = uruchom(["gh"] + args, timeout=timeout)
    return json.loads(out) if out.strip() else None


def pobierz_pr(repo):
    lista = gh_json(["pr", "list", "-R", "%s/%s" % (GH_ORG, repo), "--state", "open", "--limit", "100",
                     "--json", "number,title,isDraft,headRefOid,createdAt"])
    for pr in lista:
        if K.pr_pominiety(pr):  # szkic albo tytuł z filtra – bez dodatkowego zapytania o datę commita
            continue
        try:
            pr["headDate"] = uruchom(["gh", "api", "repos/%s/%s/commits/%s" % (GH_ORG, repo, pr["headRefOid"]),
                                      "--jq", ".commit.committer.date"], timeout=10).strip() or None
        except BladZrodla:
            pr["headDate"] = None
    return lista


def pobierz_asc():
    """Wtyczka testflight: ID i daty opinii (zrzuty, awarie) z App Store Connect przez własny moduł asc.py organizacji
    (poza repo; funkcja asc.call(metoda, sciezka) -> odpowiedź JSON API albo {"blad": ...}). Katalog modułu: STRAZNIK_ASC."""
    katalog = os.environ.get("STRAZNIK_ASC", "").strip()
    if not katalog:
        raise BladZrodla("ustaw STRAZNIK_ASC – katalog z modułem asc.py (klient App Store Connect API, poza repo)")
    katalog = os.path.expanduser(katalog)
    if not (Path(katalog) / "asc.py").is_file():
        raise BladZrodla("STRAZNIK_ASC: brak pliku asc.py w katalogu %s" % katalog)
    if not ASC_BUNDLE:
        raise BladZrodla("ustaw STRAZNIK_ASC_BUNDLE – identyfikator pakietu aplikacji (bundle ID)")
    sys.dont_write_bytecode = True
    if katalog not in sys.path:
        sys.path.insert(0, katalog)
    import asc  # noqa: E402 – moduł z katalogu kluczy (nie w repo)

    def wszystkie(sciezka):
        dane, url = [], sciezka
        for _ in range(50):
            r = z_ponowieniem(asc.call, "GET", url)
            if "blad" in r:
                raise BladZrodla(maskuj("ASC HTTP %s" % r["blad"]))
            dane += r.get("data", [])
            url = (r.get("links") or {}).get("next")
            if not url:
                return dane
        raise BladZrodla("ASC: za dużo stron")

    apps = z_ponowieniem(asc.call, "GET", "/v1/apps?filter[bundleId]=%s&fields[apps]=bundleId" % ASC_BUNDLE)
    if "blad" in apps or not apps.get("data"):
        raise BladZrodla("ASC: nie znaleziono aplikacji %s" % ASC_BUNDLE)
    app = apps["data"][0]["id"]
    wynik = {}
    for rodzaj, typ in (("zrzuty", "betaFeedbackScreenshotSubmissions"), ("awarie", "betaFeedbackCrashSubmissions")):
        # tylko ID i data – bez treści uwag i danych testerów
        wynik[rodzaj] = bezpiecznie(lambda t=typ: [{"id": x["id"], "data": (x.get("attributes") or {}).get("createdDate")}
                                                   for x in wszystkie("/v1/apps/%s/%s?limit=200&fields[%s]=createdDate" % (app, t, t))])
    return wynik


def supabase_sql(token, sql):
    return z_ponowieniem(_supabase_sql, token, sql)


def _supabase_sql(token, sql):
    req = urllib.request.Request(
        "https://api.supabase.com/v1/projects/%s/database/query" % SUPABASE_PROJEKT,
        data=json.dumps({"query": sql, "read_only": True}).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "straznik-floty"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        tresc = e.read().decode(errors="replace")[:200].replace(token, "***")
        raise BladZrodla("Supabase HTTP %d: %s" % (e.code, tresc))
    except urllib.error.URLError as e:
        if jest_timeout(e):
            raise
        raise BladZrodla("Supabase: %s" % e.reason)


SQL_CRON = ("select j.jobname, count(*)::int as n from cron.job_run_details d join cron.job j using (jobid) "
            "where d.status = 'failed' and d.start_time > now() - interval '1 hour' group by 1 order by 1")
SQL_NET = "select count(*)::int as n from net._http_response where status_code >= 500 and created > now() - interval '1 hour'"


def sql_build():
    """Zapytanie o licznik błędów builda z rzędu (STRAZNIK_SQL_BUILD): pierwszy wiersz wyniku, kolumna „bledy”.
    Zależy od schematu bazy organizacji, dlatego nie ma wartości domyślnej; "" = ta część kontroli jest pomijana."""
    return os.environ.get("STRAZNIK_SQL_BUILD", "").strip()


def repo_fly():
    """Repo z workflow wdrożenia: STRAZNIK_FLY_REPO (nazwa albo właściciel/nazwa), inaczej pierwsze repo produktu
    z org.yaml (repo.produkt). None = brak repo (część kontroli pomijana)."""
    r = os.environ.get("STRAZNIK_FLY_REPO", "").strip() or (REPO_PRODUKT[0] if REPO_PRODUKT else "")
    if not r:
        return None
    return r if "/" in r else "%s/%s" % (GH_ORG, r)


def workflow_fly():
    """Nazwa workflow wdrożenia w GitHub Actions (STRAZNIK_FLY_WORKFLOW; domyślnie „Fly Deploy”)."""
    return os.environ.get("STRAZNIK_FLY_WORKFLOW", "").strip() or K.FLY_WORKFLOW


def pobierz_fly():
    """Ostatni przebieg workflow wdrożenia: {"conclusion", "createdAt", "status", "workflow"} | None (brak przebiegów)
    | {"pominieta": ...} (brak repo)."""
    repo = repo_fly()
    if not repo:
        return {"pominieta": "brak repo produktu w org.yaml (repo.produkt) – ustaw STRAZNIK_FLY_REPO"}
    r = gh_json(["run", "list", "-R", repo, "--workflow", workflow_fly(), "-L", "1", "--json", "conclusion,createdAt,status"])
    return dict(r[0], workflow=workflow_fly()) if r else None


def repo_pages():
    """Repo z GitHub Pages do sprawdzenia: STRAZNIK_PAGES (nazwy po przecinku, bez właściciela); domyślnie żadne."""
    return tuple(dict.fromkeys(x.strip() for x in os.environ.get("STRAZNIK_PAGES", "").split(",") if x.strip()))


def pobierz_pages(repo):
    try:
        return gh_json(["api", "repos/%s/%s/pages/builds/latest" % (GH_ORG, repo)])
    except BladZrodla as e:
        if "404" in str(e):
            return None
        raise


def pobierz_automaty():
    wynik = {}
    sql = sql_build()
    bez_sql = {"pominieta": "ustaw STRAZNIK_SQL_BUILD (zapytanie o licznik błędów builda, kolumna „bledy”)"}
    token = sekret(SUPABASE_PAT_USLUGA) if SUPABASE_PROJEKT else None
    if not token:
        brak = {"blad": ("brak tokenu Supabase (pozycja %s w pęku kluczy albo zmienna STRAZNIK_SEKRET_SUPABASE_PAT_STRAZNIK)"
                         % SUPABASE_PAT_USLUGA) if SUPABASE_PROJEKT else "ustaw STRAZNIK_SUPABASE_PROJEKT (ref projektu Supabase)"}
        wynik.update(cron_failed=brak, net5xx=brak, build_stan=brak if sql else bez_sql)
    else:
        m = [token]
        wynik["cron_failed"] = bezpiecznie(lambda: supabase_sql(token, SQL_CRON), maska=m)
        wynik["net5xx"] = bezpiecznie(lambda: int(supabase_sql(token, SQL_NET)[0]["n"]), maska=m)
        wynik["build_stan"] = bezpiecznie(lambda: (supabase_sql(token, sql) or [None])[0], maska=m) if sql else bez_sql
    wynik["fly"] = bezpiecznie(pobierz_fly)
    if K.blad(wynik["fly"]):
        wynik["fly"]["workflow"] = workflow_fly()
    wynik["pages"] = {r: bezpiecznie(pobierz_pages, r) for r in repo_pages()}
    return wynik


def rownolegle(zadania, limit_s=LIMIT_ZRODLA_S):
    """{nazwa: funkcja} -> {nazwa: wynik}; wątki demonowe, żeby zawieszone źródło nie blokowało końca przebiegu."""
    wyniki = {}

    def cel(n, f):
        wyniki[n] = bezpiecznie(f)
    watki = []
    for n, f in zadania.items():
        t = threading.Thread(target=cel, args=(n, f), daemon=True)
        t.start()
        watki.append((n, t))
    import time
    koniec = time.monotonic() + limit_s
    for n, t in watki:
        t.join(max(0.0, koniec - time.monotonic()))
    return {n: wyniki.get(n, {"blad": "przekroczony czas %d s" % limit_s}) for n in zadania}


def pobierz_zewnetrzne(repo):
    """Źródła sieciowe tylko dla aktywnych kontroli (wtyczki testflight/automaty wyłączone = bez wywołań ASC i Supabase)."""
    z = {"tagi": lambda: pobierz_tagi(repo)}
    if "testflight" in KONTROLE_AKTYWNE:
        z["asc"] = pobierz_asc
    if "automaty" in KONTROLE_AKTYWNE:
        z["automaty"] = pobierz_automaty
    for r in REPO_PR:
        z["pr:" + r] = (lambda rr=r: pobierz_pr(rr))
    w = rownolegle(z)
    wyl = {"blad": "wtyczka wyłączona (org.yaml → straznik.kontrole)"}
    return {"tagi": w["tagi"], "prs": {r: w["pr:" + r] for r in REPO_PR}, "asc": w.get("asc", wyl), "automaty": w.get("automaty", wyl)}


def zewnetrzne_z_pliku(katalog):
    """Tryb --dane: źródła zewnętrzne z <katalog>/zewnetrzne.json (tagi jako lista refów)."""
    d = json.loads((Path(katalog) / "zewnetrzne.json").read_text(encoding="utf-8"))
    tagi = d.get("tagi")
    if isinstance(tagi, list):
        tagi = parsuj_tagi(tagi)
    return {"tagi": tagi, "prs": d.get("prs") or {}, "asc": d.get("asc") or {"blad": "brak"}, "automaty": d.get("automaty") or {}}


# ---------- złożenie danych dla kontroli ----------

def czytaj_budzety(repo, teraz_miesiac):
    """Budżety miesięczne (org.yaml → mandat.budzet_floty_usd_miesiac; flota/zadania.yaml → budzet_usd_miesiac per agent/domyślny)
    i wydatki miesiąca z przebiegi/<agent>/koszty-<RRRR-MM>-*.jsonl oraz pola koszt_usd linii kontraktu <RRRR-MM>-*.jsonl."""
    repo = Path(repo)
    org = czytaj_org(repo)
    org_limit = (org.get("mandat") or {}).get("budzet_floty_usd_miesiac")
    try:
        org_limit = float(org_limit) if org_limit not in (None, "") else None
    except ValueError:
        org_limit = None
    rozl = str((org.get("runtime") or {}).get("rozliczenie") or "api")
    tsv = repo / "flota" / "budzety.tsv"   # budżety efektywne z flota/generuj.py (team: udziały w pojemności konta floty)
    if tsv.exists():
        limity_t, flota_t = {}, None
        for linia in tsv.read_text(encoding="utf-8").splitlines():
            pola = linia.split("\t")
            if linia.startswith("# rozliczenie") and len(pola) > 1:
                rozl = pola[1].strip()
            elif linia.startswith("# flota_usd_miesiac") and len(pola) > 1:
                try:
                    flota_t = float(pola[1])
                except ValueError:
                    pass
            elif not linia.startswith("#") and len(pola) >= 3 and pola[0] != "katalog":
                try:
                    limity_t[pola[0]] = float(pola[2])
                except ValueError:
                    pass
        if limity_t:
            org_limit = flota_t if flota_t else org_limit
    else:
        limity_t = None
    man = (repo / "flota" / "zadania.yaml").read_text(encoding="utf-8") if (repo / "flota" / "zadania.yaml").exists() else ""
    wspolny = re.search(r"^budzet_usd_miesiac:\s*([0-9.]+)", man, re.M)
    domyslny = float(wspolny.group(1)) if wspolny else None
    limity = {}
    for blok in re.split(r"^- agent:", man, flags=re.M)[1:]:
        kat = re.search(r"^\s*katalog:\s*([a-z0-9-]+)", blok, re.M)
        b = re.search(r"^\s*budzet_usd_miesiac:\s*([0-9.]+)", blok, re.M)
        if kat and kat.group(1) != "null":
            limity[kat.group(1)] = float(b.group(1)) if b else domyslny
    agenci = {}
    kat_przeb = repo / "przebiegi"
    if kat_przeb.is_dir():
        for d in sorted(x for x in kat_przeb.iterdir() if x.is_dir() and x.name != "dead-letter"):
            wydano = 0.0
            for pl in list(d.glob("koszty-%s-*.jsonl" % teraz_miesiac)) + list(d.glob("%s-*.jsonl" % teraz_miesiac)):
                for linia in pl.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        k = json.loads(linia).get("koszt_usd")
                    except ValueError:
                        continue
                    if isinstance(k, (int, float)):
                        wydano += float(k)
            lim = limity_t.get(d.name) if limity_t else None
            agenci[d.name] = {"wydano": round(wydano, 2), "limit": lim if lim is not None else limity.get(d.name, domyslny)}
    return {"miesiac": teraz_miesiac, "org_limit": org_limit, "agenci": agenci, "rozliczenie": rozl}


def czytaj_martwe(repo, k=3):
    """Ostatnie k wyników kontraktu per agent (po dacie pliku i kolejności linii) + agenci już w przebiegi/dead-letter/."""
    repo = Path(repo)
    wyniki, dl = {}, set()
    kat = repo / "przebiegi"
    if (kat / "dead-letter").is_dir():
        dl = {p.stem for p in (kat / "dead-letter").glob("*.md")}
    if kat.is_dir():
        for d in sorted(x for x in kat.iterdir() if x.is_dir() and x.name != "dead-letter"):
            ostatnie = []
            for pl in sorted(d.glob("????-??-??.jsonl"))[-3:]:
                for linia in pl.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        w = json.loads(linia).get("wynik")
                    except ValueError:
                        continue
                    if w:
                        ostatnie.append(str(w))
            wyniki[d.name] = ostatnie[-k:]
    return {"k": k, "wyniki": wyniki, "dead_letter": sorted(dl)}


def zloz(repo, zadania_katalog, zewn):
    odstepy = bezpiecznie(czytaj_odstepy, repo)
    agenci = [w["agent"] for w in odstepy] if isinstance(odstepy, list) else []
    stany = bezpiecznie(czytaj_stany, repo, agenci)
    if RUNTIME != "desktop-scheduled" or (not Path(zadania_katalog).is_dir() and os.environ.get("STRAZNIK_BEZ_ZADAN")):
        konfiguracja = {"pominieta": "runtime %s – zadania zaplanowane desktopu nie dotyczą tej floty" % RUNTIME}
    elif not Path(zadania_katalog).is_dir():
        konfiguracja = {"odstepy": odstepy, "zadania": {"blad": "brak katalogu %s" % zadania_katalog}, "inne_zadania": [],
                        "konta": list(KONTA), "prefiks": PREFIKS}
    else:
        zad = bezpiecznie(czytaj_zadania, zadania_katalog, agenci)
        zadania, inne = (zad if isinstance(zad, tuple) else (zad, []))
        konfiguracja = {"odstepy": odstepy, "zadania": zadania, "inne_zadania": inne, "konta": list(KONTA), "prefiks": PREFIKS}
    asc_d = zewn.get("asc") or {}
    if K.blad(asc_d):
        asc_d = {"zrzuty": asc_d, "awarie": asc_d}
    automaty = zewn.get("automaty") or {}
    if K.blad(automaty):
        automaty = {k: automaty for k in ("cron_failed", "net5xx", "fly")}
    return {
        "przebiegi": {"odstepy": odstepy, "tagi": zewn["tagi"] if zewn.get("tagi") is not None else {"blad": "brak danych"},
                      "utworzeni": sorted(a for a in agenci if (Path(repo) / a / "agent.md").exists()),  # flota rośnie etapami
                      "stany": stany if isinstance(stany, dict) else {}},
        "pr": {"prs": zewn.get("prs") or {}, "recenzje": bezpiecznie(czytaj_recenzje, repo)},
        "testflight": {"zrzuty": asc_d.get("zrzuty"), "awarie": asc_d.get("awarie"), "rejestr": bezpiecznie(czytaj_rejestr, repo)},
        "automaty": automaty,
        "zlecenia": bezpiecznie(czytaj_zlecenia, repo),
        "konfiguracja": konfiguracja,
        "budzety": bezpiecznie(czytaj_budzety, repo, zewn.get("miesiac") or K.utc_teraz().astimezone(K.WAW).strftime("%Y-%m")),
        "martwe": bezpiecznie(czytaj_martwe, repo),
    }
