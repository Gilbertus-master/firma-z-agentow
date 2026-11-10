"""Strażnik floty – kontrole niezawodności jako czyste funkcje (dane, teraz) -> wynik.

Wynik każdej kontroli:
    {"status": "OK" | "ROZBIEZNOSC" | "BLAD_ZRODLA", "liczby": {...}, "id": [...], "opis": "...", "uwagi": [...]}

Dane przygotowuje zrodla.py (sieć, pliki repo) – tu nie ma wejścia/wyjścia, więc testy nie potrzebują sieci.
Fragment danych, którego nie udało się pobrać, ma postać {"blad": "<komunikat>"}.
Czas lokalny: strefa organizacji (org.yaml → organizacja.strefa; domyślnie Europe/Warsaw). Python 3.9+ (biblioteka
standardowa).
"""
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    raise SystemExit("Potrzebny Python 3.9+ (zoneinfo)")

WAW = ZoneInfo("Europe/Warsaw")  # strefa organizacji; nadpisuje zrodla.konfiguruj z org.yaml → organizacja.strefa
REPO_BEZ_PREFIKSU = "produkt"    # repo, którego PR-y recenzent zapisuje gołym numerem (pierwsze repo produktu)
POMIN_TYTUL = None               # skompilowany regex tytułów PR pomijanych w kontroli (zrodla.konfiguruj); None = nic
POMIN_TYTUL_BLAD = None          # komunikat, gdy wzorca nie dało się użyć (uwaga w kontroli PR)
OK, ROZ, BLAD = "OK", "ROZBIEZNOSC", "BLAD_ZRODLA"

# Progi
PR_PROG_MIN = 60            # PR bez werdyktu dłużej niż 60 min
PRZEBIEG_ZAPAS_MIN = 10     # okienko uznane za zakończone 10 min po jego końcu
PRZEBIEG_MIN_POKRYCIE = 60  # przy okienkach < 60 min tag może być w kolejnym okienku (spóźniony start)
STAN_MNOZNIK = 2            # stan.json starszy niż 2 × odstęp = nieaktualny
BUILD_BLEDY_PROG = 3        # licznik błędów builda z rzędu (kolumna „bledy” zapytania STRAZNIK_SQL_BUILD) >= 3
DNI = {"pn": 0, "wt": 1, "sr": 2, "śr": 2, "cz": 3, "czw": 3, "pt": 4, "so": 5, "sb": 5, "nd": 6, "nie": 6}


def blad(dane):
    """Komunikat błędu źródła albo None."""
    return dane.get("blad") if isinstance(dane, dict) else None


def wynik(status, liczby=None, ids=None, opis="", uwagi=None, zrodla=None):
    """zrodla = identyfikatory źródeł, które nie odpowiedziały (alert po 2 kolejnych błędach – alerty.py)."""
    return {"status": status, "liczby": liczby or {}, "id": sorted(set(ids or [])), "opis": opis, "uwagi": uwagi or [],
            "zrodla_bledy": sorted(set(zrodla or []))}


def zrodlo_niedostepne(komunikat, zrodlo, uwagi=None):
    return wynik(BLAD, {}, [], "źródło niedostępne: " + komunikat, uwagi, [zrodlo])


def polacz_status(rozbieznosci, bledy_zrodel):
    if rozbieznosci:
        return ROZ
    if bledy_zrodel:
        return BLAD
    return OK


# ---------- czas ----------

def minuty_lokalne(teraz):
    """Minuty od epoki w czasie lokalnym organizacji – dokładnie jak scripts/przebieg.sh (teraz/60 + przesunięcie strefy)."""
    sek = int(teraz.timestamp())
    przes = int(teraz.astimezone(WAW).utcoffset().total_seconds() // 60)
    return sek // 60 + przes


def hhmm_na_min(s):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("zła godzina: %r" % s)
    return int(m.group(1)) * 60 + int(m.group(2))


def okienko(teraz, odstep, poczatek_min):
    """Numer okienka: floor((minuty_lokalne_od_epoki - poczatek) / odstep) – wzór 1:1 z przebieg.sh."""
    return (minuty_lokalne(teraz) - poczatek_min) // odstep


def lokalne_min_na_tekst(lm):
    return (datetime(1970, 1, 1) + timedelta(minutes=lm)).strftime("%Y-%m-%d %H:%M")


def parsuj_czas(s):
    """Data z stan.json / ASC / gh w różnych formatach -> (datetime z strefą, tylko_data) albo (None, None).
    Bez strefy = czas lokalny organizacji; sama data = koniec tego dnia (łagodnie)."""
    if not isinstance(s, str) or not s.strip():
        return None, None
    t = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        d = date.fromisoformat(t)
        return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=WAW), True
    t2 = t.replace("Z", "+00:00").replace(" ", "T", 1)
    t2 = re.sub(r"(\.\d{6})\d+", r"\1", t2)  # ASC: ułamki sekund
    try:
        dt = datetime.fromisoformat(t2)
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WAW)
    return dt, False


def iso(dt):
    return dt.astimezone(WAW).isoformat(timespec="seconds")


# ---------- harmonogram (kolumny 4–6 koordynacja-odstepy.tsv) ----------

def harmonogram_z_wiersza(w):
    """Wiersz tsv -> None (przebieg w każdym okienku: dni * i godziny *) albo {"dni": set, "godziny": [min]}.
    Godziny * przy wybranych dniach = początek każdego okienka + 30 min."""
    dni, godziny = w.get("dni") or set(range(7)), w.get("godziny")
    if godziny is None:
        if len(dni) == 7:
            return None
        godziny = sorted({(w["poczatek"] + 30 + i * w["odstep"]) % 1440 for i in range(max(1, 1440 // w["odstep"]))})
    return {"dni": set(dni), "godziny": sorted(godziny)}


def harmonogram_tydzien(h):
    """Lista minut tygodnia (pn 0:00 = 0) zaplanowanych przebiegów."""
    return sorted(d * 1440 + g for d in h["dni"] for g in h["godziny"])


def harmonogram_max_przerwa(h):
    t = harmonogram_tydzien(h)
    if len(t) < 2:
        return 7 * 1440
    przerwy = [b - a for a, b in zip(t, t[1:])] + [t[0] + 7 * 1440 - t[-1]]
    return max(przerwy)




def okienko_oczekiwane(k, odstep, pocz, h):
    """Czy w okienku k jest zaplanowany przebieg (h = None: każde okienko)."""
    if h is None:
        return True
    start, koniec = k * odstep + pocz, (k + 1) * odstep + pocz
    for dzien in range(start // 1440, (koniec - 1) // 1440 + 1):
        dow = (date(1970, 1, 1) + timedelta(days=dzien)).weekday()
        if dow not in h["dni"]:
            continue
        for g in h["godziny"]:
            if start <= dzien * 1440 + g < koniec:
                return True
    return False


def ostatnie_sprawdzane_okienko(teraz, odstep, pocz, h, start_lm=None):
    """(k, j): ostatnie zakończone (≥ 10 min po końcu) okienko z zaplanowanym przebiegiem; tag może być w k..k+j.
    Bez harmonogramu: okienko bieżące − 1 (albo − 2, gdy od końca − 1 minęło < 10 min).
    start_lm (minuty lokalne): okienka zaczynające się wcześniej nie są oczekiwane -> (None, j)."""
    M = minuty_lokalne(teraz)
    cur = (M - pocz) // odstep
    j = max(0, math.ceil(PRZEBIEG_MIN_POKRYCIE / odstep) - 1)
    k = cur - 1 - j
    if M - ((k + j + 1) * odstep + pocz) < PRZEBIEG_ZAPAS_MIN:
        k -= 1
    limit = 8 * 1440 // odstep + 2
    for _ in range(limit):
        if start_lm is not None and k * odstep + pocz < start_lm:
            return None, j
        if okienko_oczekiwane(k, odstep, pocz, h):
            return k, j
        k -= 1
    return None, j


# ---------- 1. Przebiegi ----------

def kontrola_przebiegi(dane, teraz):
    """dane: {"odstepy": [{"agent","odstep","poczatek","dni","godziny","od"}], "tagi": {agent: [nr okienka]} | {"blad"},
    "stany": {agent: {"ostatni_przebieg": str} | {"blad"}}}. Oczekiwane są tylko okienka od późniejszej z chwil:
    „od” (data obowiązywania harmonogramu z tsv) albo pierwszy tag agenta."""
    if blad(dane.get("odstepy")):
        return zrodlo_niedostepne("koordynacja-odstepy.tsv – " + blad(dane["odstepy"]), "repo:koordynacja-odstepy.tsv")
    if blad(dane.get("tagi")):
        return zrodlo_niedostepne("tagi przebieg/* w origin – " + blad(dane["tagi"]), "git:tagi")
    tagi, stany = dane["tagi"], dane.get("stany") or {}
    utworzeni = dane.get("utworzeni")  # None = brak informacji (stare dane) – sprawdzamy wszystkich z tsv
    ids, uwagi, bez, nieakt, opisy = [], [], [], [], []
    z_przebiegiem = pominiete_stany = nieutworzeni = 0
    for w in dane["odstepy"]:
        a, o, p = w["agent"], w["odstep"], w["poczatek"]
        if utworzeni is not None and a not in utworzeni:
            nieutworzeni += 1  # rola z harmonogramu jeszcze nieuruchomiona (procesy/00, etapy) – bez alertu
            continue
        h = harmonogram_z_wiersza(w)
        starty = []
        if w.get("od") is not None:
            starty.append(minuty_lokalne(w["od"]))
        if tagi.get(a):
            starty.append(min(tagi[a]) * o + p)
        start_lm = max(starty) if starty else None
        k, j = ostatnie_sprawdzane_okienko(teraz, o, p, h, start_lm)
        if k is None:
            uwagi.append("%s: brak oczekiwanego przebiegu od %s (harmonogram od / pierwszy tag)" % (
                a, lokalne_min_na_tekst(start_lm) if start_lm is not None else "8 dni"))
        else:
            if any(n in set(tagi.get(a, [])) for n in range(k, k + j + 1)):
                z_przebiegiem += 1
            else:
                bez.append(a)
                ids.append(a)
                opisy.append("%s bez tagu przebieg/%s/%d (okienko od %s)" % (a, a, k, lokalne_min_na_tekst(k * o + p)))
        st = stany.get(a)
        if st is None or blad(st):
            pominiete_stany += 1
            uwagi.append("%s: stan.json pominięty (%s)" % (a, blad(st) if st else "brak pliku"))
            continue
        surowy = st.get("ostatni_przebieg")
        dt, tylko_data = parsuj_czas(surowy)
        if dt is None:
            pominiete_stany += 1
            uwagi.append("%s: ostatni_przebieg nieparsowalny (%r) – pominięty" % (a, surowy))
            continue
        kadencja = harmonogram_max_przerwa(h) if h else o
        if teraz - dt > timedelta(minutes=STAN_MNOZNIK * kadencja):
            nieakt.append(a)
            ids.append(a + ":stan")
            opisy.append("%s: nieaktualny stan.json (ostatni_przebieg %s, próg %d min)" % (a, surowy, STAN_MNOZNIK * kadencja))
        if tylko_data:
            uwagi.append("%s: ostatni_przebieg bez godziny (%s) – liczony koniec dnia" % (a, surowy))
    liczby = {"agenci": len(dane["odstepy"]), "z_przebiegiem": z_przebiegiem, "bez_przebiegu": len(bez),
              "stan_nieaktualny": len(nieakt), "stan_pominiety": pominiete_stany, "nieutworzeni": nieutworzeni}
    if nieutworzeni:
        uwagi.append("%d ról z harmonogramu jeszcze nieutworzonych (brak <agent>/agent.md) – pominięte" % nieutworzeni)
    if not ids:
        return wynik(OK, liczby, [], "wszyscy utworzeni agenci z przebiegiem w ostatnim okienku", uwagi)
    krotko = []
    if bez:
        krotko.append("bez przebiegu: " + ", ".join(bez))
    if nieakt:
        krotko.append("nieaktualny stan.json: " + ", ".join(nieakt))
    return wynik(ROZ, liczby, ids, "; ".join(krotko) + ". " + "; ".join(opisy), uwagi)


# ---------- 2. PR-y bez werdyktu ----------

def klucze_recenzji(repo, nr):
    if repo == REPO_BEZ_PREFIKSU:
        return [str(nr)]
    return ["%s#%s" % (repo, nr), "%s/%s" % (repo, nr), "%s-%s" % (repo, nr)]


def pr_pominiety(pr):
    """PR poza kontrolą: szkic (draft) albo tytuł pasujący do POMIN_TYTUL (re.search; domyślnie brak wzorca)."""
    if pr.get("isDraft"):
        return True
    return bool(POMIN_TYTUL is not None and POMIN_TYTUL.search(pr.get("title") or ""))


def kontrola_pr(dane, teraz):
    """dane: {"prs": {repo: [ {number,title,isDraft,headRefOid,createdAt,headDate} ] | {"blad"}}, "recenzje": {...} | {"blad"}}"""
    if blad(dane.get("recenzje")):
        return zrodlo_niedostepne("recenzent/stan.json – " + blad(dane["recenzje"]), "repo:recenzent/stan.json")
    rec = dane["recenzje"]
    bledy, uwagi, ids, opisy = [], [], [], []
    otwarte = pominiete = z_werdyktem = bez_werdyktu = 0
    for repo, lista in sorted((dane.get("prs") or {}).items()):
        if blad(lista):
            bledy.append(("gh:pr:" + repo, "%s: %s" % (repo, blad(lista))))
            continue
        for pr in lista:
            if pr_pominiety(pr):
                pominiete += 1
                continue
            otwarte += 1
            head = (pr.get("headRefOid") or "").lower()
            r = next((rec[k] for k in klucze_recenzji(repo, pr["number"]) if isinstance(rec.get(k), dict)), None)
            sha = str((r or {}).get("sha") or "").lower()
            if r and len(sha) >= 7 and head.startswith(sha):
                z_werdyktem += 1
                continue
            bez_werdyktu += 1
            utw, _ = parsuj_czas(pr.get("createdAt"))
            com, _ = parsuj_czas(pr.get("headDate"))
            if com is None:
                uwagi.append("%s#%s: brak daty commita head – wiek od createdAt" % (repo, pr["number"]))
            od = max([d for d in (utw, com) if d is not None], default=None)
            if od is None:
                uwagi.append("%s#%s: brak dat – pominięty" % (repo, pr["number"]))
                continue
            wiek = int((teraz - od).total_seconds() // 60)
            if wiek > PR_PROG_MIN:
                ident = "%s#%s" % (repo, pr["number"])
                ids.append(ident)
                opisy.append("%s head %s bez werdyktu od %d min (w stan.json: %s)" % (ident, head[:7], wiek, sha[:7] or "-"))
    liczby = {"otwarte": otwarte, "pominiete": pominiete, "z_werdyktem": z_werdyktem,
              "bez_werdyktu": bez_werdyktu, "bez_werdyktu_ponad_60min": len(ids)}
    if POMIN_TYTUL_BLAD:
        uwagi.insert(0, POMIN_TYTUL_BLAD)
    status = polacz_status(ids, bledy)
    if bledy:
        uwagi = ["źródło niedostępne – " + b for _, b in bledy] + uwagi
    if status == OK:
        opis = "otwarte %d, z werdyktem dla head %d" % (otwarte, z_werdyktem)
    elif status == BLAD:
        opis = "źródło niedostępne: " + "; ".join(b for _, b in bledy)
    else:
        opis = "%d PR bez werdyktu > %d min: %s" % (len(ids), PR_PROG_MIN, "; ".join(opisy))
    return wynik(status, liczby, ids, opis, uwagi, [z for z, _ in bledy])


# ---------- 3. TestFlight ----------

def kontrola_testflight(dane, teraz):
    """dane: {"zrzuty": [{"id","data"}] | {"blad"}, "awarie": [...] | {"blad"}, "rejestr": str | {"blad"}}"""
    if blad(dane.get("rejestr")):
        return zrodlo_niedostepne("aplikacje/opinie-testflight.md – " + blad(dane["rejestr"]), "repo:opinie-testflight.md")
    rejestr = dane["rejestr"]
    bledy, ids, opisy, liczby = [], [], [], {}
    for rodzaj, etykieta in (("zrzuty", "opinie"), ("awarie", "awarie")):
        lista = dane.get(rodzaj)
        if lista is None or blad(lista):
            bledy.append(("asc:" + rodzaj, "%s: %s" % (rodzaj, blad(lista) if lista else "brak danych")))
            continue
        brak = [x for x in lista if x["id"][:8] not in rejestr]
        liczby["asc_" + etykieta] = len(lista)
        liczby["brak_w_rejestrze_" + etykieta] = len(brak)
        for x in sorted(brak, key=lambda x: x.get("data") or ""):
            ident = x["id"][:8] if rodzaj == "zrzuty" else "awaria:" + x["id"][:8]
            ids.append(ident)
            opisy.append("%s (%s)" % (ident, (x.get("data") or "?")[:16]))
    status = polacz_status(ids, bledy)
    uwagi = ["źródło niedostępne – " + b for _, b in bledy]
    if status == OK:
        opis = "każda opinia z App Store Connect jest w rejestrze"
    elif status == BLAD:
        opis = "źródło niedostępne: " + "; ".join(b for _, b in bledy)
    else:
        opis = "%d opinii z App Store Connect brak w rejestrze: %s" % (len(ids), ", ".join(opisy))
    return wynik(status, liczby, ids, opis, uwagi, [z for z, _ in bledy])


# ---------- 4. Automaty ----------

FLY_ZLE = {"failure", "timed_out", "startup_failure"}
FLY_WORKFLOW = "Fly Deploy"  # domyślna nazwa workflow wdrożenia (zrodla: STRAZNIK_FLY_WORKFLOW)
PAGES_ZLE = {"failure", "errored"}


def pominieta(dane):
    """Powód pominięcia części kontroli ({"pominieta": "<powód>"}) albo None."""
    return dane.get("pominieta") if isinstance(dane, dict) else None


def kontrola_automaty(dane, teraz):
    """dane: {"cron_failed": [{"jobname","n"}], "net5xx": int, "build_stan": {"bledy":..}|None,
    "fly": {"conclusion","createdAt","status"[,"workflow"]}|None, "pages": {repo: {"status","created_at"}|None}} – każde pole
    może być {"blad"}; build_stan i fly także {"pominieta": "<powód>"} (część kontroli nieskonfigurowana – tylko uwaga)."""
    bledy, ids, opisy, uwagi, liczby = [], [], [], [], {}
    c = dane.get("cron_failed")
    if blad(c) or c is None:
        bledy.append(("supabase:cron", "cron.job_run_details: " + (blad(c) or "brak danych")))
    else:
        liczby["cron_failed_1h"] = sum(int(x.get("n") or 0) for x in c)
        for x in c:
            ids.append("cron:%s" % x.get("jobname"))
            opisy.append("cron %s: %s× failed w ostatniej godzinie" % (x.get("jobname"), x.get("n")))
    n = dane.get("net5xx")
    if blad(n) or n is None:
        bledy.append(("supabase:net", "net._http_response: " + (blad(n) or "brak danych")))
    else:
        liczby["http_5xx_1h"] = int(n)
        if int(n) > 0:
            ids.append("net:5xx")
            opisy.append("net._http_response: %d odpowiedzi 5xx w ostatniej godzinie" % int(n))
    b = dane.get("build_stan")
    if blad(b):
        bledy.append(("supabase:build_stan", "build_stan: " + blad(b)))
    elif pominieta(b):
        uwagi.append("build_stan: pominięte – " + pominieta(b))
    elif b is None:
        uwagi.append("build_stan: brak danych licznika błędów builda")
    else:
        try:
            nb = int(b.get("bledy") or 0)
        except (TypeError, ValueError):
            nb = None
            uwagi.append("build_stan.bledy nieliczbowe: %r" % b.get("bledy"))
        if nb is not None:
            liczby["build_bledy"] = nb
            if nb >= BUILD_BLEDY_PROG:
                ids.append("build_stan")
                opisy.append("build: %d błędów z rzędu (próg %d)" % (nb, BUILD_BLEDY_PROG))
    f = dane.get("fly")
    wf = (f.get("workflow") if isinstance(f, dict) else None) or FLY_WORKFLOW  # nazwa workflow wdrożenia (do opisów)
    if blad(f):
        bledy.append(("gh:fly", "%s: %s" % (wf, blad(f))))
    elif pominieta(f):
        uwagi.append("%s: pominięte – %s" % (wf, pominieta(f)))
    elif f is None:
        uwagi.append("%s: brak przebiegów workflow" % wf)
    else:
        liczby["fly_ostatni"] = f.get("conclusion") or f.get("status")
        if (f.get("conclusion") or "") in FLY_ZLE:
            ids.append("fly:%s" % f.get("createdAt"))
            opisy.append("%s %s: %s" % (wf, f.get("createdAt"), f.get("conclusion")))
    for repo, p in sorted((dane.get("pages") or {}).items()):
        if blad(p):
            bledy.append(("gh:pages:" + repo, "Pages %s: %s" % (repo, blad(p))))
        elif p is None:
            uwagi.append("Pages %s: repo bez GitHub Pages – pominięte" % repo)
        else:
            liczby["pages_" + repo] = p.get("status")
            if (p.get("status") or "") in PAGES_ZLE:
                ids.append("pages:%s:%s" % (repo, p.get("created_at")))
                opisy.append("Pages %s %s: %s" % (repo, p.get("created_at"), p.get("status")))
    status = polacz_status(ids, bledy)
    uwagi = ["źródło niedostępne – " + x for _, x in bledy] + uwagi
    if status == OK:
        opis = "crony, Edge Functions, build, wdrożenie i Pages bez błędów"
    elif status == BLAD:
        opis = "źródło niedostępne: " + "; ".join(x for _, x in bledy)
    else:
        opis = "; ".join(opisy)
    return wynik(status, liczby, ids, opis, uwagi, [z for z, _ in bledy])


# ---------- 5. Zlecenia po terminie bez odpowiedzi ----------

RE_NAGLOWEK = re.compile(r"^## \[(otwarte|w toku)[^\]]*\]\s*(.*)$")
RE_DATA = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?")


def najwczesniejszy_termin(linia):
    """Najwcześniejsza data z linii „Termin: …” (czas lokalny organizacji; sama data = 23:59). Po „→” liczy się część za strzałką
    (termin przesunięty), daty po „wcześniej:” są pomijane (poprzedni termin)."""
    s = linia.split(":", 1)[1] if ":" in linia else linia
    if "→" in s:
        s = s.split("→")[-1]
    s = re.sub(r"wcześniej:[^);]*", "", s)
    daty = []
    for m in RE_DATA.finditer(s):
        r, mi, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        g, mn = (int(m.group(4)), int(m.group(5))) if m.group(4) else (23, 59)
        try:
            daty.append(datetime(r, mi, d, g, mn, tzinfo=WAW))
        except ValueError:
            continue
    return min(daty) if daty else None


def bloki_zlecen(tekst):
    """[(nagłówek_reszta, status, [linie bloku])] tylko dla [otwarte] / [w toku …]."""
    wynik_, biezacy = [], None
    for linia in tekst.splitlines():
        if linia.startswith("## "):
            m = RE_NAGLOWEK.match(linia)
            biezacy = [m.group(2), m.group(1), []] if m else None
            if biezacy:
                wynik_.append(biezacy)
        elif biezacy is not None:
            biezacy[2].append(linia)
    return [tuple(b) for b in wynik_]


def odpowiedz_pusta(linie):
    for i, l in enumerate(linie):
        if re.match(r"^Odpowiedź[^:]*:", l):
            reszta = l.split(":", 1)[1].strip()
            return reszta == "" and all(not x.strip() for x in linie[i + 1:])
    return True  # brak linii „Odpowiedź:” = brak odpowiedzi


def kontrola_zlecenia(dane, teraz):
    """dane: {"pliki": {"ceo.md": tekst, ...}} | {"blad"}"""
    if blad(dane):
        return zrodlo_niedostepne("zlecenia/*.md – " + blad(dane), "repo:zlecenia")
    ids, opisy, uwagi = [], [], []
    otwarte = z_terminem = bez_terminu_daty = wlasne = 0
    for plik, tekst in sorted(dane["pliki"].items()):
        for reszta, _status, linie in bloki_zlecen(tekst):
            czesci = [c.strip() for c in reszta.split(" · ")]
            if len(czesci) >= 2 and czesci[1] == "od: straznik":
                wlasne += 1  # własne wpisy alertów – już zgłoszone mailem i powiadomieniem (bez sprzężenia zwrotnego)
                continue
            otwarte += 1
            data = RE_DATA.search(czesci[0]).group(0)[:10] if czesci and RE_DATA.search(czesci[0]) else "?"
            if len(czesci) >= 3 and czesci[1].startswith("od:"):
                tytul = " · ".join(czesci[2:])
            else:
                tytul = " · ".join(czesci[1:]) or reszta
            linia_t = next((l for l in linie if l.startswith("Termin:")), None)
            termin = najwczesniejszy_termin(linia_t) if linia_t else None
            if termin is None:
                bez_terminu_daty += 1
                continue
            z_terminem += 1
            if termin < teraz and odpowiedz_pusta(linie):
                ident = "%s|%s|%s" % (plik, data, tytul[:60])
                ids.append(ident)
                opisy.append("%s (termin %s)" % (ident, termin.strftime("%Y-%m-%d %H:%M")))
    liczby = {"otwarte_i_w_toku": otwarte, "z_data_terminu": z_terminem, "bez_daty_terminu": bez_terminu_daty,
              "po_terminie_bez_odpowiedzi": len(ids), "wpisy_straznika": wlasne}
    if not ids:
        return wynik(OK, liczby, [], "brak zleceń po terminie bez odpowiedzi", uwagi)
    return wynik(ROZ, liczby, ids, "%d zleceń po terminie bez odpowiedzi: %s" % (len(ids), "; ".join(opisy)), uwagi)


# ---------- 6. Konfiguracja zadań ----------

def opis_frontmatter(tekst):
    m = re.match(r"^---\s*\n(.*?)\n---", tekst, re.S)
    if not m:
        return None
    d = re.search(r"^description:\s*(.*)$", m.group(1), re.M)
    return d.group(1).strip() if d else None




def godziny_z_opisu(opis):
    """Wszystkie godziny GG:MM z opisu zadania (minuty od północy)."""
    return [int(m.group(1)) * 60 + int(m.group(2)) for m in re.finditer(r"(?<![\d.])(\d{1,2}):(\d{2})(?!\d)", opis) if int(m.group(1)) <= 23]


def pierwsza_godzina_z_opisu(opis):
    m = re.search(r"(?<![\d.])(\d{1,2}):(\d{2})(?!\d)", opis)
    if not m or int(m.group(1)) > 23:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def kontrola_konfiguracja(dane, teraz):
    """dane: {"odstepy": [...], "zadania": {agent: {konto: tekst SKILL.md | None}}, "inne_zadania": [...],
    "konta": [...], "prefiks": str} albo {"pominieta": powód} (runtime bez katalogu zadań na tej maszynie)."""
    if dane.get("pominieta"):
        return wynik(OK, {"agenci": 0, "zadania_sprawdzone": 0, "rozbieznosci": 0}, [], "pominięta: " + str(dane["pominieta"]))
    if blad(dane.get("odstepy")):
        return zrodlo_niedostepne("koordynacja-odstepy.tsv – " + blad(dane["odstepy"]), "repo:koordynacja-odstepy.tsv")
    if blad(dane.get("zadania")):
        return zrodlo_niedostepne("katalog zadań – " + blad(dane["zadania"]), "zadania")
    ids, opisy, uwagi = [], [], []
    sprawdzone = 0
    konta = [str(k).upper() for k in (dane.get("konta") or ["A"])]
    prefiks = dane.get("prefiks") or "org"
    suf = (lambda k: "") if len(konta) == 1 else (lambda k: ":" + k.lower())
    for w in dane["odstepy"]:
      a, o, p = w["agent"], w["odstep"], w["poczatek"]
      z = dane["zadania"].get(a)
      if not isinstance(z, dict):
          z = {konta[0]: z}
      for konto in konta:
        tekst = z.get(konto)
        nazwa = "%s-%s-%s" % (prefiks, a, konto.lower())
        if tekst is None:
            ids.append(a + ":brak-zadania" + suf(konto))
            opisy.append("brak %s/SKILL.md" % nazwa)
            continue
        sprawdzone += 1
        if not re.search(r"^Konto: %s\s*$" % konto, tekst, re.M):
            ids.append(a + ":konto" + suf(konto))
            opisy.append("%s: brak linii „Konto: %s”" % (nazwa, konto))
        opis = opis_frontmatter(tekst)
        if opis is None:
            uwagi.append("%s: brak description we frontmatterze" % nazwa)
            continue
        h = harmonogram_z_wiersza(w) if w.get("godziny") is not None else None
        if h:
            godz_ocz = min(h["godziny"])
            zrodlo = "tsv (godziny)"
        else:
            godz_ocz = (p + 30) % 1440
            zrodlo = "tsv"
        # porównujemy godziny z opisu z kolumną „godziny” tsv, bez odstępu – odstęp w tsv to długość okienka blokady
        # (np. recenzent 30 min przy siatce co 3 h, PM 120 min przy przerwach), nie rytm zadania; cronExpression nie jest dostępny
        g = pierwsza_godzina_z_opisu(opis)
        if g is None:
            uwagi.append("%s: nie da się odczytać godzin z opisu" % a)
            continue
        if g != godz_ocz:
            ids.append(a + ":godzina" + suf(konto))
            opisy.append("%s: pierwsza godzina w opisie %d:%02d, %s %d:%02d" % (nazwa, g // 60, g % 60, zrodlo, godz_ocz // 60, godz_ocz % 60))
        dozwolone = set(h["godziny"]) if h else {(p + 30 + i * o) % 1440 for i in range(max(1, 1440 // o))}
        obce = sorted({x for x in godziny_z_opisu(opis) if x not in dozwolone})
        if obce:
            ids.append(a + ":godziny" + suf(konto))
            opisy.append("%s: godziny z opisu spoza harmonogramu %s: %s" % (nazwa, zrodlo, ", ".join("%d:%02d" % (x // 60, x % 60) for x in obce)))
    inne = dane.get("inne_zadania") or []
    if inne:
        uwagi.append("zadania %s-* spoza koordynacja-odstepy.tsv (bez kontroli): " % prefiks + ", ".join(sorted(inne)))
    liczby = {"agenci": len(dane["odstepy"]), "zadania_sprawdzone": sprawdzone, "rozbieznosci": len(ids)}
    if not ids:
        return wynik(OK, liczby, [], "zadania zgodne z koordynacja-odstepy.tsv (konta: %s)" % ", ".join(konta), uwagi)
    return wynik(ROZ, liczby, ids, "; ".join(opisy), uwagi)


def kontrola_budzety(dane, teraz):
    """dane: {"miesiac", "org_limit", "agenci": {agent: {"wydano", "limit"}}, "rozliczenie"}. ≥ 100 % = rozbieżność (agent:100,
    org:100 → HALT), ≥ 80 % = uwaga. Limit null = bez kontroli. Rozliczenie „team”: limity agentów to udziały w pojemności
    konta floty (flota/budzety.tsv) – przekroczenie udziału = rozbieżność, ale cała flota nie dostaje HALT (miejsce ogranicza
    plan, a płatną nadwyżkę – limit wydatków ustawiony u Anthropic); uwaga pokazuje wykorzystanie pojemności floty."""
    if blad(dane):
        return zrodlo_niedostepne("budżety – " + blad(dane), "repo:budzety")
    team = dane.get("rozliczenie") in ("team", "subskrypcja")
    ids, opisy, uwagi = [], [], []
    razem = 0.0
    for a, w in sorted((dane.get("agenci") or {}).items()):
        wyd, lim = float(w.get("wydano") or 0), w.get("limit")
        razem += wyd
        if lim in (None, 0):
            continue
        if wyd >= lim:
            ids.append(a + ":100"); opisy.append("%s: %.2f ≥ %.2f %s w %s (przebieg.sh kończy bez pracy)"
                                                  % (a, wyd, lim, "USD-ekw." if team else "USD", dane.get("miesiac")))
        elif wyd >= 0.8 * lim:
            uwagi.append("%s: %.2f z %.2f USD (≥ 80 %%)" % (a, wyd, lim))
    org = dane.get("org_limit")
    if team:
        if org:
            uwagi.append("flota: %.2f z %.2f USD-ekw. pojemności konta floty (%.0f %%) – niewykorzystany limit miejsca przepada (F-04)"
                         % (razem, org, 100 * razem / org))
    elif org:
        if razem >= org:
            ids.append("org:100"); opisy.append("organizacja: %.2f ≥ %.2f USD w %s → HALT" % (razem, org, dane.get("miesiac")))
        elif razem >= 0.8 * org:
            uwagi.append("organizacja: %.2f z %.2f USD (≥ 80 %%)" % (razem, org))
    liczby = {"agenci": len(dane.get("agenci") or {}), "razem_usd": round(razem, 2), "org_limit_usd": org, "przekroczenia": len(ids)}
    if not ids:
        return wynik(OK, liczby, [], "budżety w normie (%.2f USD w %s)" % (razem, dane.get("miesiac")), uwagi)
    return wynik(ROZ, liczby, ids, "; ".join(opisy), uwagi)


def kontrola_martwe(dane, teraz):
    """dane: {"k", "wyniki": {agent: [ostatnie wyniki]}, "dead_letter": [agenci]}. k wyników BŁĄD z rzędu → rozbieżność
    (straznik.py zakłada przebiegi/dead-letter/<agent>.md; przebieg.sh wstrzymuje zadanie). Agent już w dead-letter = uwaga."""
    if blad(dane):
        return zrodlo_niedostepne("martwe przebiegi – " + blad(dane), "repo:przebiegi")
    k = int(dane.get("k") or 3)
    ids, opisy, uwagi = [], [], []
    dl = set(dane.get("dead_letter") or [])
    for a, w in sorted((dane.get("wyniki") or {}).items()):
        if len(w) >= k and all(x == "BŁĄD" for x in w[-k:]):
            if a in dl:
                uwagi.append("%s: w dead-letter (czeka na przegląd operatora)" % a)
            else:
                ids.append(a); opisy.append("%s: %d przebiegi z rzędu z wynikiem BŁĄD" % (a, k))
    for a in sorted(dl):
        if a not in ids and not any(u.startswith(a + ":") for u in uwagi):
            uwagi.append("%s: w dead-letter" % a)
    liczby = {"agenci": len(dane.get("wyniki") or {}), "nowe_martwe": len(ids), "w_dead_letter": len(dl)}
    if not ids:
        return wynik(OK, liczby, [], "brak nowych martwych przebiegów", uwagi)
    return wynik(ROZ, liczby, ids, "; ".join(opisy), uwagi)


KONTROLE = [
    ("przebiegi", "Przebiegi", kontrola_przebiegi),
    ("pr", "PR-y", kontrola_pr),
    ("testflight", "TestFlight", kontrola_testflight),
    ("automaty", "Automaty", kontrola_automaty),
    ("zlecenia", "Zlecenia", kontrola_zlecenia),
    ("konfiguracja", "Konfiguracja zadań", kontrola_konfiguracja),
    ("budzety", "Budżety", kontrola_budzety),
    ("martwe", "Martwe przebiegi", kontrola_martwe),
]
NAZWY = {n: e for n, e, _ in KONTROLE}
NAZWY["klon"] = "Klon strażnika"  # stan własnego klonu repo (straznik.py, tylko prawdziwy przebieg)


def uruchom_wszystkie(dane, teraz, aktywne=None):
    """Każda kontrola osobno – wyjątek w jednej nie przerywa pozostałych (wynik BLAD_ZRODLA).
    aktywne: nazwy kontroli do uruchomienia (org.yaml → straznik.kontrole); None = wszystkie."""
    wyniki = {}
    for nazwa, _, f in KONTROLE:
        if aktywne is not None and nazwa not in aktywne:
            continue
        try:
            wyniki[nazwa] = f(dane.get(nazwa) or {"blad": "brak danych"}, teraz)
        except Exception as e:  # noqa: BLE001 – strażnik ma działać dalej
            wyniki[nazwa] = zrodlo_niedostepne("wyjątek w kontroli: %s: %s" % (type(e).__name__, str(e)[:300]), "wyjatek:" + nazwa)
    return wyniki


def utc_teraz():
    return datetime.now(timezone.utc)
