#!/usr/bin/env python3
"""Backlog organizacji – sekcja „Jednorazowe” w backlog.md generowana ze zleceń (role/pm.md, Codziennie pkt 1).

  python3 -I pm/narzedzia/backlog.py [--repo DIR] [--teraz ISO] [--bez-gh]   # aktualizuje sekcję „Jednorazowe”; wypisuje podsumowanie
  python3 -I pm/narzedzia/backlog.py --podglad                               # jak wyżej, ale nic nie zapisuje – wypisuje tabelę
  python3 -I pm/narzedzia/backlog.py --sprawdz                               # po terminie, duble, zadania manifestu bez wiersza C; kod 1, gdy coś jest
  python3 -I pm/narzedzia/backlog.py --json                                  # wiersze jako JSON (liczby do kontraktu przebiegu)

Źródła: `zlecenia/*.md` (nagłówki `## [status] RRRR-MM-DD GG:MM · od: X · temat · Z-RRRRMMDD-NN[ · issue #N]`, linie `Termin:`, `Plan:`,
`Odpowiedź:`, `Pilne`) oraz – gdy `gh` jest w PATH, a `org.yaml → repo.github` nie jest zaślepką – Issues z etykietą `typ:zlecenie`
(`gh issue list --json …`). Brak `gh` albo błąd sieci nie przerywa pracy: ostrzeżenie, Issues pominięte (w podsumowaniu `gh: brak|błąd`).

Wiersz `J-nn`: Id · Właściciel · Temat · Źródło (link, Z-id, Issue, od) · P · Termin · Status · Plan · Uwaga PM.
Generowane: Właściciel, Temat, Źródło, Termin, Status. **Ręczne (zachowywane po kluczu Z-id / #N / plik+temat):** Id, P, Plan, Uwaga PM –
z wyjątkiem znaczników narzędzia w „Uwaga PM”: `PO TERMINIE (+N d)`, `brak linii Termin: (domyślnie 12 h)`, `odpowiedź jest – nagłówek
otwarty (M-03)`, `status md ≠ Issue`, `źródło zniknęło`. Termin bez linii = data wpisu + 12 h (`(dom.)`); po „→” liczy się termin
przesunięty; daty po „wcześniej:” pomijane; sama data = 23:59. PO TERMINIE = status otwarty, termin minął, brak odpowiedzi.
Wiersze, których źródła już nie ma: zrobione/odłożone znikają (archiwum), otwarte zostają z uwagą.
Sekcja „Cykliczne” jest ręczna (PM); `--sprawdz` wypisuje zadania z `flota/zadania.yaml` bez wiersza C. Biblioteka standardowa, bez sieci
poza `gh`. Niczego nie commituje. Kody: 0 OK · 1 (`--sprawdz`) są pozycje po terminie/rozjazdy · 2 złe wywołanie / brak pliku."""
import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys

NAGLOWEK = re.compile(r"^## \[(?P<status>[^\]]*)\]\s*(?P<data>\d{4}-\d{2}-\d{2}(?: \d{1,2}:\d{2})?)?\s*(?P<reszta>.*?)\s*$")
DATA = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}):(\d{2}))?")
ZID = re.compile(r"\bZ-\d{8}-\d{2,}\b")
ISSUE = re.compile(r"\bissue\s*#(\d+)\b", re.I)
WIERSZ_J = re.compile(r"^\|\s*(J-\d+)\s*\|")
WIERSZ_C = re.compile(r"^\|\s*(C-\d+)\s*\|")
ZNACZNIKI = re.compile(r"(PO TERMINIE \(\+\d+ [dh]\)|brak linii Termin: \(domyślnie 12 h\)|odpowiedź jest – nagłówek otwarty \(M-03\)"
                       r"|status md ≠ Issue(?: \([^)]*\))?|źródło zniknęło[^·]*)")
KOLUMNY = ["Id", "Właściciel", "Temat", "Źródło", "P", "Termin", "Status", "Plan", "Uwaga PM"]
DOMYSLNY_TERMIN_H = 12
ZAMKNIETE = ("zrobione", "zamknięte", "zamkniete", "odłożone", "odlozone", "odrzucone")


# ---------- pomocnicze ----------

def parsuj_date(tekst):
    """'RRRR-MM-DD[ GG:MM]' -> datetime (sama data = 23:59) albo None."""
    m = DATA.search(tekst or "")
    if not m:
        return None
    try:
        d = dt.datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None
    if m.group(2):
        return d.replace(hour=int(m.group(2)) % 24, minute=int(m.group(3)))
    return d.replace(hour=23, minute=59)


def parsuj_termin(tekst):
    """Linia `Termin:` -> (datetime|None, tekst). Po „→” liczy się termin przesunięty, daty po „wcześniej:” pomijane."""
    t = (tekst or "").strip()
    if "→" in t:
        t = t.rsplit("→", 1)[1]
    t = re.split(r"wcześniej\s*:", t, maxsplit=1)[0]
    return parsuj_date(t), (tekst or "").strip()


def normalizuj_status(raw):
    s = raw.strip()
    n = s.lower()
    if n.startswith(("zrobione", "zamknięte", "zamkniete")):
        reszta = s[len(s.split()[0]):].strip(" –-·") if s.split() else ""
        return "zrobione" + (f" ({reszta})" if reszta else "")
    if n.startswith(("odłożone", "odlozone")):
        return "odłożone"
    if n.startswith("odrzucone"):
        return "odrzucone"
    if n.startswith("informacja"):
        return "informacja"
    if n.startswith("w toku"):
        kto = re.sub(r"^w toku\s*[–\-·:]?\s*", "", s, flags=re.I).strip()
        return "w toku" + (f" ({kto})" if kto else "")
    if n.startswith("czeka"):
        kto = re.sub(r"^czeka\s*(na|:)?\s*", "", s, flags=re.I).strip(" –-·")
        return "czeka: " + (kto or "?")
    if n.startswith("otwarte") or not n:
        return "otwarte"
    return f"otwarte ({s})"


def otwarty(status):
    return not status.startswith(ZAMKNIETE) and status != "informacja"


def norm_temat(t):
    return re.sub(r"[^a-z0-9ąćęłńóśźż ]+", " ", (t or "").lower()).strip()


def komorka(t):
    return str(t if t not in (None, "") else "–").replace("|", "\\|").replace("\n", " ")


# ---------- źródła ----------

def wpisy_z_pliku(plik, repo):
    """Nagłówki `## [status] …` z jednego pliku skrzynki -> lista słowników zlecenia."""
    linie = plik.read_text(encoding="utf-8").splitlines()
    wyn, cur = [], None
    for nr, l in enumerate(linie, 1):
        m = NAGLOWEK.match(l)
        if m:
            cur = {"plik": plik.relative_to(repo).as_posix(), "linia": nr, "wlasciciel": plik.stem, "status_raw": m.group("status"),
                   "data_wpisu": parsuj_date(m.group("data") or ""), "od": "", "temat": "", "zid": "", "issue": None,
                   "termin": None, "termin_tekst": "", "termin_domyslny": False, "odpowiedz": False, "plan": "", "pilne": False,
                   "tresc": []}
            reszta = m.group("reszta").strip().lstrip("·").strip()
            czesci = [c.strip() for c in re.split(r"\s·\s|\s\|\s", reszta) if c.strip()]
            temat = []
            for c in czesci:
                if re.match(r"^od\s*:", c, re.I):
                    cur["od"] = re.sub(r"^od\s*:\s*", "", c, flags=re.I)
                elif ZID.fullmatch(c):
                    cur["zid"] = c
                elif ISSUE.fullmatch(c):
                    cur["issue"] = int(ISSUE.fullmatch(c).group(1))
                else:
                    temat.append(c)
            cur["temat"] = " · ".join(temat)
            if not cur["zid"]:
                z = ZID.search(m.group("reszta"))
                cur["zid"] = z.group(0) if z else ""
            if cur["issue"] is None:
                i = ISSUE.search(m.group("reszta"))
                cur["issue"] = int(i.group(1)) if i else None
            cur["pilne"] = bool(re.search(r"\bpilne\b", m.group("reszta"), re.I))
            cur["status"] = normalizuj_status(cur["status_raw"])
            wyn.append(cur)
        elif cur is not None:
            cur["tresc"].append(l)
    for w in wyn:
        _pola_z_tresci(w)
    return wyn


def _pola_z_tresci(w):
    tresc = w.pop("tresc")
    for i, l in enumerate(tresc):
        s = l.strip().lstrip("*").strip()
        if re.match(r"^Termin\s*:", s, re.I):
            w["termin"], w["termin_tekst"] = parsuj_termin(re.sub(r"^Termin\s*:\s*", "", s, flags=re.I))
        elif re.match(r"^Plan(\s*/\s*zakład EV)?\s*:", s, re.I):
            w["plan"] = re.sub(r"^Plan[^:]*:\s*", "", s, flags=re.I).strip().strip("*").strip() or ""
            if re.fullmatch(r"[–\-]?|<[^>]*>", w["plan"]):
                w["plan"] = ""
        elif re.match(r"^Odpowied[źz]\s*:", s, re.I):
            po = re.sub(r"^Odpowied[źz]\s*:\s*", "", s, flags=re.I).strip()
            dalej = any(x.strip() and not x.strip().startswith("<") for x in tresc[i + 1:])
            w["odpowiedz"] = bool(po and not re.fullmatch(r"[–\-]|<[^>]*>", po)) or dalej
        elif re.match(r"^(\*\*)?PILNE\b", l.strip(), re.I) or re.match(r"^Pilne\s*:\s*tak", s, re.I):
            w["pilne"] = True
    if w["termin"] is None and not w["termin_tekst"] and otwarty(w["status"]) and w["data_wpisu"]:
        w["termin"] = w["data_wpisu"] + dt.timedelta(hours=DOMYSLNY_TERMIN_H)
        w["termin_domyslny"] = True


def wpisy_md(repo):
    kat = repo / "zlecenia"
    if not kat.is_dir():
        return []
    wyn = []
    for p in sorted(kat.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        wyn.extend(wpisy_z_pliku(p, repo))
    return wyn


def org_github(repo):
    """`repo.github` z org.yaml (bez PyYAML) albo ''."""
    p = repo / "org.yaml"
    if not p.exists():
        return ""
    w_repo = False
    for l in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^repo\s*:", l):
            w_repo = True
            continue
        if w_repo and re.match(r"^\S", l):
            w_repo = False
        m = re.match(r"^\s+github\s*:\s*[\"']?([^\"'#]+)", l) if w_repo else None
        if m:
            return m.group(1).strip()
    return ""


def issues_gh(repo, bez_gh=False):
    """Issues `typ:zlecenie` przez gh -> (lista, stan: 'ok'|'brak'|'pominięte'|'błąd: …')."""
    if bez_gh:
        return [], "pominięte"
    if not shutil.which("gh"):
        return [], "brak"
    gh_repo = org_github(repo)
    if not gh_repo or gh_repo.startswith("OWNER/"):
        return [], "pominięte (org.yaml → repo.github niewypełnione)"
    try:
        p = subprocess.run(["gh", "issue", "list", "-R", gh_repo, "--label", "typ:zlecenie", "--state", "all", "--limit", "200",
                            "--json", "number,title,labels,state,body,createdAt,closedAt,url"],
                           capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], f"błąd: {e.__class__.__name__}"
    if p.returncode != 0:
        return [], "błąd: " + (p.stderr.strip().splitlines() or ["gh zwrócił kod %d" % p.returncode])[-1][:120]
    try:
        dane = json.loads(p.stdout or "[]")
    except ValueError:
        return [], "błąd: gh nie zwrócił JSON"
    wyn = []
    for i in dane:
        ety = {(e.get("name") if isinstance(e, dict) else str(e)) for e in (i.get("labels") or [])}
        agent = next((e.split(":", 1)[1] for e in ety if e.startswith("agent:")), "")
        prio = next((e.split(":", 1)[1] for e in ety if e.startswith("prio:P")), "")
        body = i.get("body") or ""
        pole = lambda n: (re.search(r"\*\*%s[^:*]*:\*\*\s*(.*)" % n, body) or re.search(r"^%s[^:]*:\s*(.*)$" % n, body, re.M))
        termin_m = pole("Termin")
        termin, termin_tekst = parsuj_termin(termin_m.group(1)) if termin_m else (None, "")
        od_m, plan_m, do_m = pole("Od"), pole("Plan"), pole("Do")
        utw = parsuj_date((i.get("createdAt") or "")[:16].replace("T", " "))
        if i.get("state", "").upper() == "CLOSED":
            status = "zrobione (%s)" % ((i.get("closedAt") or "")[:10] or "Issue zamknięty")
        elif "stan:w-toku" in ety:
            status = "w toku"
        elif "stan:czeka" in ety:
            status = "czeka: ?"
        elif "stan:pr" in ety:
            status = "otwarte (PR)"
        else:
            status = "otwarte"
        w = {"plik": "", "linia": 0, "wlasciciel": agent or (do_m.group(1).strip() if do_m else "?"), "status_raw": i.get("state", ""),
             "data_wpisu": utw, "od": od_m.group(1).strip() if od_m else "", "temat": re.sub(r"^\[zlecenie\]\s*", "", i.get("title") or ""),
             "zid": "", "issue": int(i["number"]), "url": i.get("url") or "", "termin": termin, "termin_tekst": termin_tekst,
             "termin_domyslny": False, "odpowiedz": False, "plan": "" if plan_m and re.fullmatch(r"[–\-]?|<[^>]*>", plan_m.group(1).strip())
             else (plan_m.group(1).strip() if plan_m else ""), "pilne": "prio:pilne" in ety or bool(re.search(r"\*\*Pilne:\*\*\s*tak", body, re.I)),
             "prio": prio, "status": status}
        if w["termin"] is None and not w["termin_tekst"] and otwarty(status) and utw:
            w["termin"], w["termin_domyslny"] = utw + dt.timedelta(hours=DOMYSLNY_TERMIN_H), True
        wyn.append(w)
    return wyn, "ok"


# ---------- klucze i scalanie ----------

def klucz(w):
    if w.get("zid"):
        return w["zid"]
    if w.get("issue") is not None:
        return "#%d" % w["issue"]
    return "%s · %s" % (w.get("plik", ""), norm_temat(w.get("temat", "")))


def scal(md, issues):
    """Wpis md z ` · issue #N` i Issue #N to jedno zlecenie (md wygrywa; Issue dodaje URL i kontrolę statusu)."""
    po_issue = {w["issue"]: w for w in md if w.get("issue") is not None}
    wyn = list(md)
    for i in issues:
        m = po_issue.get(i["issue"])
        if m is None:
            wyn.append(i)
            continue
        m["url"] = i.get("url", "")
        if otwarty(m["status"]) != otwarty(i["status"]):
            m["rozjazd_issue"] = "md: %s, Issue: %s" % (m["status"], i["status"])
        if m["termin"] is None and i["termin"] is not None:
            m["termin"], m["termin_tekst"], m["termin_domyslny"] = i["termin"], i["termin_tekst"], False
    return wyn


# ---------- backlog.md ----------

def wczytaj_backlog(sciezka):
    """-> (przed, wiersze_sekcji_J (lista list komórek), po, istniala_sekcja, wiersze_C)."""
    tekst = sciezka.read_text(encoding="utf-8") if sciezka.exists() else "# Backlog organizacji\n\n## Jednorazowe\n\n## Cykliczne\n"
    linie = tekst.splitlines()
    start = next((i for i, l in enumerate(linie) if l.strip() == "## Jednorazowe"), None)
    if start is None:
        linie += ["", "## Jednorazowe", ""]
        start = len(linie) - 2
    koniec = next((i for i in range(start + 1, len(linie)) if linie[i].startswith("## ")), len(linie))
    wiersze = [[k.strip() for k in l.strip().strip("|").split("|")] for l in linie[start + 1:koniec] if WIERSZ_J.match(l.strip())]
    wiersze_c = [[k.strip() for k in l.strip().strip("|").split("|")] for l in linie if WIERSZ_C.match(l.strip())]
    return linie[:start], wiersze, linie[koniec:], wiersze_c


def klucz_wiersza(k):
    zrodlo = k[3] if len(k) > 3 else ""
    z = ZID.search(zrodlo)
    if z:
        return z.group(0)
    i = re.search(r"\[?#(\d+)\]?", zrodlo)
    if i:
        return "#" + i.group(1)
    plik = re.search(r"zlecenia/[\w.-]+\.md", zrodlo)
    return "%s · %s" % (plik.group(0) if plik else "", norm_temat(k[2] if len(k) > 2 else ""))


def zbuduj(repo, teraz, bez_gh=False):
    md = wpisy_md(repo)
    issues, stan_gh = issues_gh(repo, bez_gh)
    zlecenia = scal(md, issues)
    zlecenia.sort(key=lambda w: (w.get("plik") or "zzz", w.get("linia", 0), w.get("issue") or 0))
    przed, stare, po, wiersze_c = wczytaj_backlog(repo / "backlog.md")
    stare_po_kluczu = {klucz_wiersza(k): k for k in stare}
    numery = [int(k[0][2:]) for k in stare if re.fullmatch(r"J-\d+", k[0])]
    nastepny = max(numery, default=0) + 1
    kolejnosc = [klucz_wiersza(k) for k in stare]
    nowe, wiersze, stat = [], {}, {"otwarte": 0, "w toku": 0, "czeka": 0, "po_terminie": 0, "zrobione": 0, "nowe": 0, "bez_terminu": 0,
                                  "issues": len(issues), "gh": stan_gh, "po_terminie_lista": [], "duble": [], "rozjazdy": []}
    widziane_tematy = {}
    for w in zlecenia:
        k = klucz(w)
        stary = stare_po_kluczu.get(k)
        if stary is None:
            ident, p, plan, uwaga = "J-%02d" % nastepny, "", "", ""
            nastepny += 1
            stat["nowe"] += 1
            nowe.append(k)
        else:
            ident, p, plan, uwaga = stary[0], stary[4] if len(stary) > 4 else "", stary[7] if len(stary) > 7 else "", stary[8] if len(stary) > 8 else ""
        p = p if p not in ("", "–") else (w.get("prio") or ("P1" if w["pilne"] else "P2" if w.get("plan") else "P3"))
        plan = plan if plan not in ("", "–") else (w.get("plan") or "–")
        reczna = " · ".join(x.strip(" ·") for x in ZNACZNIKI.split(uwaga) if x and not ZNACZNIKI.fullmatch(x) and x.strip(" ·"))
        auto = []
        otw = otwarty(w["status"])
        if otw and w["termin"] and w["termin"] < teraz and not w["odpowiedz"]:
            delta = teraz - w["termin"]
            auto.append("PO TERMINIE (+%d d)" % (delta.days) if delta >= dt.timedelta(days=1) else "PO TERMINIE (+%d h)" % max(1, int(delta.total_seconds() // 3600)))
            stat["po_terminie"] += 1
            stat["po_terminie_lista"].append((ident, w))
        if otw and w["termin_domyslny"]:
            auto.append("brak linii Termin: (domyślnie 12 h)")
            stat["bez_terminu"] += 1
        if otw and w["odpowiedz"]:
            auto.append("odpowiedź jest – nagłówek otwarty (M-03)")
        if w.get("rozjazd_issue"):
            auto.append("status md ≠ Issue (%s)" % w["rozjazd_issue"])
            stat["rozjazdy"].append((ident, w["rozjazd_issue"]))
        if otw:
            stat["czeka" if w["status"].startswith("czeka") else "w toku" if w["status"].startswith("w toku") else "otwarte"] += 1
            nt = norm_temat(w["temat"])
            if nt and nt in widziane_tematy:
                stat["duble"].append((widziane_tematy[nt], ident, w["temat"]))
            widziane_tematy.setdefault(nt, ident)
        else:
            stat["zrobione"] += 1
        zrodlo = []
        if w.get("plik"):
            zrodlo.append("[%s:%d](%s)" % (w["plik"], w["linia"], w["plik"]))
        if w.get("zid"):
            zrodlo.append(w["zid"])
        if w.get("issue") is not None:
            zrodlo.append("issue [#%d](%s)" % (w["issue"], w["url"]) if w.get("url") else "issue #%d" % w["issue"])
        if w.get("od"):
            zrodlo.append("od: " + w["od"])
        termin = w["termin"].strftime("%Y-%m-%d %H:%M") + (" (dom.)" if w["termin_domyslny"] else "") if w["termin"] else \
            ("– (%s)" % w["termin_tekst"][:60] if w["termin_tekst"] else "–")
        temat = ("PILNE · " if w["pilne"] else "") + w["temat"][:110]
        wiersze[k] = [ident, w["wlasciciel"], komorka(temat), " · ".join(zrodlo), p, termin, komorka(w["status"]), komorka(plan),
                      komorka(" · ".join(auto + ([reczna] if reczna else [])))]
    # wiersze, których źródło zniknęło
    for k in kolejnosc:
        if k in wiersze:
            continue
        s = stare_po_kluczu[k]
        status = s[6] if len(s) > 6 else ""
        if status.lower().startswith(ZAMKNIETE):
            continue  # zrobione/odłożone poszło do archiwum
        uwaga = s[8] if len(s) > 8 else ""
        reczna = " · ".join(x.strip(" ·") for x in ZNACZNIKI.split(uwaga) if x and not ZNACZNIKI.fullmatch(x) and x.strip(" ·"))
        s = s + [""] * (9 - len(s))
        s[8] = komorka(" · ".join(["źródło zniknęło – sprawdź archiwum/Issue"] + ([reczna] if reczna else [])))
        wiersze[k] = s[:9]
    uporzadkowane = [wiersze[k] for k in kolejnosc if k in wiersze] + [wiersze[k] for k in nowe]
    return przed, uporzadkowane, po, stat, wiersze_c


def tabela(wiersze):
    return ["| " + " | ".join(KOLUMNY) + " |", "|" + "---|" * len(KOLUMNY)] + ["| " + " | ".join(w) + " |" for w in wiersze]


def podsumowanie(stat, teraz, z_nowymi=True):
    """Linia liczb do raportu/KPI; bez „nowe wiersze” do pliku (ta liczba dotyczy jednego uruchomienia, plik ma być idempotentny)."""
    return ("J: otwarte %d · w toku %d · czeka %d · po terminie %d · zrobione %d · %sbez linii Termin %d · Issues %d (gh: %s)"
            % (stat["otwarte"], stat["w toku"], stat["czeka"], stat["po_terminie"], stat["zrobione"],
               "nowe wiersze %d · " % stat["nowe"] if z_nowymi else "", stat["bez_terminu"], stat["issues"], stat["gh"]))


def zapisz(repo, przed, wiersze, po, stat, teraz):
    linia = "_Aktualizacja: %s · `python3 -I pm/narzedzia/backlog.py` · %s_" % (teraz.strftime("%Y-%m-%d %H:%M"), podsumowanie(stat, teraz, False))
    sekcja = ["## Jednorazowe", "", linia, ""] + tabela(wiersze) + [""]
    przed = [l for l in przed]
    while przed and not przed[-1].strip():
        przed.pop()
    tekst = "\n".join(przed + [""] + sekcja + po).rstrip("\n") + "\n"
    (repo / "backlog.md").write_text(tekst, encoding="utf-8")


# ---------- kontrola manifestu (sekcja Cykliczne) ----------

def agenci_manifestu(repo):
    p = repo / "flota" / "zadania.yaml"
    if not p.exists():
        return []
    wyn, agent = [], None
    for l in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- agent:\s*(\S+)", l)
        if m:
            agent = m.group(1)
            continue
        m = re.match(r"^\s+katalog:\s*(\S+)", l)
        if m and agent:
            if m.group(1) not in ("null", "~", "''", '""'):
                wyn.append(m.group(1))
            agent = None
    return wyn


def bez_wiersza_c(repo, wiersze_c):
    wlasciciele = {k[1] for k in wiersze_c if len(k) > 1}
    zadania = " ".join(k[2] for k in wiersze_c if len(k) > 2).lower()
    return [a for a in agenci_manifestu(repo) if a not in wlasciciele and not re.search(r"\b%s\b" % re.escape(a), zadania)]


# ---------- main ----------

def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[2]), help="katalog repo organizacji")
    a.add_argument("--teraz", help="czas „teraz” ISO (RRRR-MM-DDTGG:MM) – do testów; domyślnie zegar")
    a.add_argument("--bez-gh", action="store_true", help="nie pytaj gh o Issues")
    a.add_argument("--podglad", action="store_true", help="wypisz tabelę, nic nie zapisuj")
    a.add_argument("--sprawdz", action="store_true", help="po terminie, duble, zadania manifestu bez wiersza C; kod 1, gdy coś jest")
    a.add_argument("--json", action="store_true", help="wiersze i liczby jako JSON (nic nie zapisuje)")
    o = a.parse_args(argv)
    repo = pathlib.Path(o.repo).resolve()
    if not (repo / "zlecenia").is_dir() and not (repo / "backlog.md").exists():
        print("BŁĄD: %s nie wygląda na repo organizacji (brak zlecenia/ i backlog.md)" % repo, file=sys.stderr)
        return 2
    try:
        teraz = dt.datetime.fromisoformat(o.teraz) if o.teraz else dt.datetime.now().replace(second=0, microsecond=0)
    except ValueError:
        print("BŁĄD: --teraz musi być ISO, np. 2026-11-09T19:00", file=sys.stderr)
        return 2
    przed, wiersze, po, stat, wiersze_c = zbuduj(repo, teraz, o.bez_gh)
    if stat["gh"].startswith("błąd"):
        print("UWAGA: Issues pominięte – %s" % stat["gh"], file=sys.stderr)
    if o.json:
        print(json.dumps({"teraz": teraz.isoformat(), "liczby": {k: v for k, v in stat.items() if not isinstance(v, list)},
                          "po_terminie": [i for i, _ in stat["po_terminie_lista"]], "duble": [list(d) for d in stat["duble"]],
                          "bez_wiersza_c": bez_wiersza_c(repo, wiersze_c),
                          "wiersze": [dict(zip(KOLUMNY, w)) for w in wiersze]}, ensure_ascii=False, indent=1))
        return 0
    if o.sprawdz:
        kod = 0
        for ident, w in stat["po_terminie_lista"]:
            kod = 1
            print("PO TERMINIE · %s · %s · %s · termin %s · %s" % (ident, w["wlasciciel"], w["temat"][:70],
                  w["termin"].strftime("%Y-%m-%d %H:%M") + (" (dom.)" if w["termin_domyslny"] else ""),
                  "%s:%d" % (w["plik"], w["linia"]) if w.get("plik") else "issue #%s" % w.get("issue")))
        for a1, a2, temat in stat["duble"]:
            kod = 1
            print("DUBEL · %s i %s · %s" % (a1, a2, temat[:70]))
        for ident, opis in stat["rozjazdy"]:
            kod = 1
            print("ROZJAZD md ≠ Issue · %s · %s" % (ident, opis))
        for agent in bez_wiersza_c(repo, wiersze_c):
            kod = 1
            print("BRAK WIERSZA C · %s (flota/zadania.yaml) – dopisz do sekcji Cykliczne" % agent)
        print(podsumowanie(stat, teraz) + (" · OK" if kod == 0 else ""))
        return kod
    if o.podglad:
        print("\n".join(tabela(wiersze)))
        print(podsumowanie(stat, teraz))
        return 0
    zapisz(repo, przed, wiersze, po, stat, teraz)
    print("zapisano backlog.md (sekcja Jednorazowe: %d wierszy) · %s" % (len(wiersze), podsumowanie(stat, teraz)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
