"""Strażnik floty – stan, zdarzenia i alerty (mail Resend, powiadomienie macOS, wpis w zlecenia/ceo.md).

przetworz() jest czystą funkcją (testy); wyślij_mail / powiadom / wstaw_wpis_ceo mają skutki uboczne.
"""
import os
from pathlib import Path
import shutil
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from datetime import timedelta

import kontrole as K
from zrodla import sekret

PRZYPOMNIENIA_MIN = (120, 360, 1440)  # trwała rozbieżność: alert, potem przypomnienia po 2 h, 6 h, 24 h, dalej co 24 h
BLEDY_ZRODLA_PROG = 2       # błąd źródła: alert po 2 kolejnych błędach tego samego źródła …
ZRODLA_NATYCHMIAST = ("build_stan", "codemagic")  # … od razu: źródła builda (fragment nazwy źródła)
ZRODLA_NARAZ = 2            # … od razu: ≥ 2 źródła nie odpowiadają w jednym przebiegu
CISZA_NOCNA = (23, 7)       # bez powiadomień macOS 23:00–7:00 (mail i wpis „Pilne” bez zmian)
ALERTY_PAMIEC_DNI = 3       # klucze starsze – usuwane ze stanu
TERMIN_WPISU_MIN = 120      # „Termin:” wpisu w zlecenia/ceo.md = teraz + 2 h
RESEND_USLUGA = "resend-api-key-straznik"
MAIL_OD = os.environ.get("STRAZNIK_MAIL_OD", "Strażnik floty <alerty@example.com>")  # org.yaml → organizacja.domena
MAIL_DO = os.environ.get("STRAZNIK_MAIL_DO", "")            # operator (org.yaml → ludzie.operator.kontakt_firmowy); pusty = brak operatora
MAIL_WLASCICIEL = os.environ.get("STRAZNIK_MAIL_WLASCICIEL", "")  # właściciel/founder (org.yaml → ludzie.wlasciciel.kontakt_firmowy)
MAIL_POMINIETY = "mail pominięty – brak klucza Resend"
MAIL_BEZ_ADRESATA = "mail pominięty – poziom adresata (wpis w skrzynce wystarcza)"
MAX_ID = 30
STATUS_TEKST = {K.OK: "OK", K.ROZ: "ROZBIEŻNOŚĆ", K.BLAD: "BŁĄD ŹRÓDŁA"}


def klucz(nazwa, w):
    """Klucz rozbieżności = kontrola + posortowane ID."""
    return "%s:%s" % (nazwa, ",".join(sorted(w["id"])))


def klucz_zrodel(nazwa, zrodla):
    return "%s:BLAD_ZRODLA:%s" % (nazwa, ",".join(sorted(zrodla)))


def cisza_nocna(teraz):
    g = teraz.astimezone(K.WAW).hour
    od, do = CISZA_NOCNA
    return g >= od or g < do


RE_WYCISZ = re.compile(r"Wycisz do:\s*(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}):(\d{2}))?(?:\s*\(([^)]*)\))?")
RE_WIECEJ = re.compile(r"\s*… i \d+ więcej\s*$")


def czytaj_wyciszenia(tekst):
    """Wpisy strażnika w zlecenia/ceo.md (dowolny status) z „Wycisz do: RRRR-MM-DD[ GG:MM][ (ID, ID)]” w odpowiedzi
    -> [{"kontrola", "ids", "do"}]. Bez nawiasu wyciszone są wszystkie ID wpisu (linia „Liczby: … ID: …”);
    sama data = do końca tego dnia (czas lokalny organizacji)."""
    nazwy = {v: k for k, v in K.NAZWY.items()}
    wynik = []
    for blok in re.split(r"(?m)^(?=## )", tekst):
        linie = blok.splitlines()
        if not linie or " · od: straznik · " not in linie[0] or "Pilne (strażnik) · " not in linie[0]:
            continue
        nazwa = nazwy.get(linie[0].split("Pilne (strażnik) · ", 1)[1].split(":", 1)[0].strip())
        if not nazwa:
            continue
        ids, w_odpowiedzi = [], False
        for l in linie[1:]:
            if l.startswith("Liczby:") and "ID: " in l:
                surowe = RE_WIECEJ.sub("", l.split("ID: ", 1)[1].rstrip().rstrip("."))
                ids = [i.strip() for i in surowe.split(",") if i.strip() and i.strip() != "–"]
            if l.startswith("Odpowiedź"):
                w_odpowiedzi = True
            if not w_odpowiedzi:
                continue
            for m in RE_WYCISZ.finditer(l):
                r, mi, d = (int(x) for x in m.group(1).split("-"))
                g, mn, sek = (int(m.group(2)), int(m.group(3)), 0) if m.group(2) else (23, 59, 59)
                try:
                    do = K.datetime(r, mi, d, g, mn, sek, tzinfo=K.WAW)
                except ValueError:
                    continue
                lista = [i.strip() for i in m.group(4).split(",") if i.strip()] if m.group(4) else ids
                wynik.append({"kontrola": nazwa, "ids": lista, "do": do})
    return wynik


def wyciszone_id(wyciszenia, nazwa, teraz):
    return {i for x in wyciszenia or [] if x["kontrola"] == nazwa and x["do"] > teraz for i in x["ids"]}


def natychmiast(zrodlo):
    return any(x in zrodlo.lower() for x in ZRODLA_NATYCHMIAST)


def widok_bledu(w):
    """Wynik do treści alertu o błędzie źródła (także gdy kontrola jest ROZBIEŻNOŚĆ, a nie odpowiada tylko część źródeł)."""
    if w["status"] == K.BLAD:
        return dict(w, id=list(w.get("zrodla_bledy") or []))
    opis = "; ".join(u for u in w.get("uwagi") or [] if u.startswith("źródło niedostępne")) or "źródło niedostępne"
    return dict(w, status=K.BLAD, id=list(w.get("zrodla_bledy") or []), opis=opis)


def skrot_klucza(k):
    return hashlib.sha1(k.encode("utf-8")).hexdigest()[:10]


def liczby_tekst(liczby):
    return ", ".join("%s %s" % (k, v) for k, v in liczby.items())


def id_tekst(ids):
    if not ids:
        return "–"
    s = ", ".join(ids[:MAX_ID])
    return s + (" … i %d więcej" % (len(ids) - MAX_ID) if len(ids) > MAX_ID else "")


def krotko(nazwa, w):
    ids = w["id"]
    if w["status"] == K.BLAD:
        return "źródło niedostępne (%s)" % ", ".join(ids) if ids else "źródło niedostępne"
    if nazwa == "przebiegi":
        stan = sum(1 for i in ids if i.endswith(":stan"))
        return "bez przebiegu %d, nieaktualny stan %d" % (len(ids) - stan, stan)
    wzor = {
        "pr": "%d PR bez werdyktu > 60 min",
        "testflight": "%d opinii poza rejestrem",
        "automaty": "%d błędów automatów",
        "zlecenia": "%d zleceń po terminie bez odpowiedzi",
        "konfiguracja": "%d rozbieżności harmonogramu zadań",
        "klon": "klon strażnika wymaga uwagi (%d)",
    }.get(nazwa, "%d rozbieżności")
    return wzor % len(ids)


def stan_klucza(v):
    """Wpis alerty[k]: {"ostatni": ISO, "n": liczba alertów}; zgodność wstecz ze starym formatem (sam ISO)."""
    if isinstance(v, dict):
        return v
    return {"ostatni": v, "n": 1} if v else None


def przetworz(poprzedni, wyniki, teraz, wyciszenia=None):
    """-> (stan_alertow, linie_zdarzen, do_alertu[(nazwa, wynik_do_alertu, klucz)]). Czysta funkcja.

    Zdarzenie: tylko przy zmianie statusu albo zbioru ID.
    Rozbieżność: alert przy pierwszym wykryciu i przy każdej zmianie zbioru (niewyciszonych) ID; trwała – przypomnienia
    po 2 h, 6 h, 24 h, dalej co 24 h. ID wyciszone wpisem „Wycisz do:” w zlecenia/ceo.md – bez alertu do tej daty.
    Błąd źródła: alert, gdy to samo źródło nie odpowiada 2 przebiegi z rzędu; od razu, gdy w przebiegu nie odpowiadają
    ≥ 2 źródła albo chodzi o źródło builda (ZRODLA_NATYCHMIAST); potem jak rozbieżność.
    stan_alertow = {"alerty": {klucz: {"ostatni", "n"}}, "bledy_zrodel": {źródło: kolejne błędy},
                    "alert_zrodel": {kontrola: klucz}, "aktywne_id": {kontrola: [ID bez wyciszonych]}}."""
    pop = poprzedni or {}
    pk = pop.get("kontrole") or {}
    alerty = {k: stan_klucza(v) for k, v in (pop.get("alerty") or {}).items() if stan_klucza(v)}
    licz_pop = pop.get("bledy_zrodel") or {}
    alert_zrodel_pop = pop.get("alert_zrodel") or {}
    aktywne_pop = pop.get("aktywne_id") or {}
    licz, alert_zrodel, aktywne = {}, {}, {}
    for w in wyniki.values():
        for z in w.get("zrodla_bledy") or []:
            licz[z] = int(licz_pop.get(z, 0)) + 1
    naraz = len(licz) >= ZRODLA_NARAZ
    zdarzenia, do_alertu = [], []
    czas = teraz.astimezone(K.WAW).strftime("%Y-%m-%d %H:%M")

    def moze(k, nowy):
        st = alerty.get(k)
        if nowy or st is None:
            alerty[k] = {"ostatni": K.iso(teraz), "n": 1}
            return True
        ostatni, _ = K.parsuj_czas(st.get("ostatni"))
        n = int(st.get("n") or 1)
        przerwa = PRZYPOMNIENIA_MIN[min(n, len(PRZYPOMNIENIA_MIN)) - 1]
        if ostatni is None or teraz - ostatni >= timedelta(minutes=przerwa):
            alerty[k] = {"ostatni": K.iso(teraz), "n": n + 1}
            return True
        return False

    for nazwa, w in wyniki.items():
        p = pk.get(nazwa)
        p_status = p.get("status") if p else None
        p_id = sorted(p.get("id") or []) if p else None
        zmiana = (p_status != w["status"] or p_id != sorted(w["id"])) if p else w["status"] != K.OK
        if zmiana:
            zdarzenia.append("- %s · %s · %s → %s · %s · ID: %s" % (
                czas, nazwa, STATUS_TEKST.get(p_status, "brak stanu") if p else "brak stanu", STATUS_TEKST[w["status"]],
                liczby_tekst(w["liczby"]) or "–", id_tekst(w["id"])))
        if w["status"] == K.ROZ:
            cisza = wyciszone_id(wyciszenia, nazwa, teraz)
            akt = sorted(i for i in w["id"] if i not in cisza)
            if akt:
                aktywne[nazwa] = akt
                w_al = w if len(akt) == len(w["id"]) else dict(
                    w, id=akt, uwagi=list(w.get("uwagi") or []) + ["wyciszone (Wycisz do:): " + ", ".join(sorted(set(w["id"]) - set(akt)))])
                k = klucz(nazwa, w_al)
                poprz = aktywne_pop.get(nazwa, p_id if p_status == K.ROZ else None)
                if moze(k, p_status != K.ROZ or sorted(poprz or []) != akt):
                    do_alertu.append((nazwa, w_al, k))
            elif zmiana:
                zdarzenia.append("- %s · %s · bez alertu – wszystkie ID wyciszone (Wycisz do:)" % (czas, nazwa))
        zr = w.get("zrodla_bledy") or []
        if zr and (naraz or any(licz[z] >= BLEDY_ZRODLA_PROG or natychmiast(z) for z in zr)):
            k = klucz_zrodel(nazwa, zr)
            alert_zrodel[nazwa] = k
            if moze(k, alert_zrodel_pop.get(nazwa) != k):
                do_alertu.append((nazwa, widok_bledu(w), k))
        elif zr:
            zdarzenia.append("- %s · %s · błąd źródła %s (%s. z rzędu) – alert po %d kolejnych" % (
                czas, nazwa, ", ".join(zr), "/".join(str(licz[z]) for z in zr), BLEDY_ZRODLA_PROG))
    granica = teraz - timedelta(days=ALERTY_PAMIEC_DNI)
    alerty = {k: v for k, v in alerty.items() if (K.parsuj_czas(v.get("ostatni"))[0] or teraz) >= granica}
    return ({"alerty": alerty, "bledy_zrodel": licz, "alert_zrodel": alert_zrodel, "aktywne_id": aktywne},
            zdarzenia, do_alertu)


# ---------- treść alertu ----------

def temat(nazwa, w):
    return "[STRAŻNIK] %s: %s" % (K.NAZWY.get(nazwa, nazwa), krotko(nazwa, w))


def tresc(nazwa, w, teraz):
    linie = [
        "Strażnik floty – %s (%s)" % (K.NAZWY.get(nazwa, nazwa), teraz.astimezone(K.WAW).strftime("%Y-%m-%d %H:%M")),
        "Status: %s" % STATUS_TEKST[w["status"]],
        "Liczby: %s" % (liczby_tekst(w["liczby"]) or "–"),
        "ID: %s" % id_tekst(w["id"]),
        "",
        w["opis"][:3000],
    ]
    if w.get("uwagi"):
        linie += ["", "Uwagi:"] + ["- " + u for u in w["uwagi"][:20]]
    linie += ["", "Pełny stan: ceo/straznik.json (klon strażnika albo cache GitHub Actions); zdarzenia: ceo/straznik-zdarzenia.md.",
              "Przypomnienia o tej samej rozbieżności: po 2 h, 6 h, 24 h, dalej co 24 h; zmiana zbioru ID = nowy alert od razu.",
        "Wyciszenie: w zlecenia/ceo.md w odpowiedzi wpisu strażnika „Wycisz do: RRRR-MM-DD (ID)”."]
    return "\n".join(linie)


def wpis_ceo(nazwa, w, k, teraz, odbiorcy_=None):
    t = teraz.astimezone(K.WAW)
    termin = (t + timedelta(minutes=TERMIN_WPISU_MIN)).strftime("%Y-%m-%d %H:%M")
    opis = re.sub(r"\s+", " ", w["opis"])[:1500]
    return (
        "## [otwarte] %s · od: straznik · Pilne (strażnik) · %s: %s\n"
        "Strażnik floty (`moduly/straznik`, przebieg %s): %s\n"
        "Liczby: %s. ID: %s.\n"
        "Stan: `ceo/straznik.json` (klon strażnika), historia: `ceo/straznik-zdarzenia.md`. Klucz strażnika: `%s`.\n"
        "%s"
        "Termin: %s\n"
        "Odpowiedź:\n\n" % (t.strftime("%Y-%m-%d"), K.NAZWY.get(nazwa, nazwa), krotko(nazwa, w), t.strftime("%H:%M"), opis,
                            liczby_tekst(w["liczby"]) or "–", id_tekst(w["id"]), skrot_klucza(k),
                            ("Adresaci alertu: %s (odpowiedź „w toku” albo w polu Odpowiedź = alarm podjęty, bez eskalacji do CEO).\n"
                             % ", ".join(odbiorcy_)) if odbiorcy_ else "", termin))


def wstaw_wpis_ceo(sciezka, wpis, k):
    """Wstawia wpis przed pierwszym nagłówkiem „## ” (początek listy zleceń – z dala od dopisków agentów na końcu,
    mniej konfliktów scalania). Pomija, gdy otwarty wpis z tym samym kluczem już jest. -> True, gdy wstawiono."""
    sciezka = Path(sciezka)
    if not sciezka.exists():  # repo bez agenta CEO (np. świeży szablon) – strażnik zakłada skrzynkę
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        sciezka.write_text("# Zlecenia dla agenta %s\n\nFormat: zlecenia/README.md. Najnowsze na górze.\n" % sciezka.stem, encoding="utf-8")
    tekst = sciezka.read_text(encoding="utf-8")
    skrot = skrot_klucza(k)
    for reszta, status, linie in K.bloki_zlecen(tekst):
        if status == "otwarte" and any("Klucz strażnika: `%s`" % skrot in l for l in linie):
            return False
    m = re.search(r"^## ", tekst, re.M)
    i = m.start() if m else len(tekst)
    if not m and not tekst.endswith("\n\n"):
        wpis = ("\n" if tekst.endswith("\n") else "\n\n") + wpis
    sciezka.write_text(tekst[:i] + wpis + tekst[i:], encoding="utf-8")
    return True


# ---------- wysyłka ----------

def adresy_maila(odbiorcy_, poziom):
    """Mail tylko od poziomu CEO: właściciel, gdy jest wśród odbiorców; operator (jeśli jest) od poziomu CEO w górę."""
    do = []
    if "wlasciciel" in odbiorcy_ and MAIL_WLASCICIEL:
        do.append(MAIL_WLASCICIEL)
    if poziom in ("ceo", "wlasciciel") and MAIL_DO and MAIL_DO not in do:
        do.append(MAIL_DO)
    return do


def wyslij_mail(temat_, tresc_, do=None):
    """-> opis wyniku (do straznik.json i zdarzeń). Klucz Resend ze zmiennej STRAZNIK_RESEND_KEY albo z pęku kluczy,
    tylko w pamięci. do = lista adresów (domyślnie MAIL_DO); pusta – bez wysyłki."""
    do = [MAIL_DO] if do is None else list(do)
    do = [x for x in do if x]
    if not do:
        return MAIL_BEZ_ADRESATA
    klucz_api = os.environ.get("STRAZNIK_RESEND_KEY") or sekret(RESEND_USLUGA)
    if not klucz_api:
        return MAIL_POMINIETY
    req = urllib.request.Request(
        "https://api.resend.com/emails", method="POST",
        data=json.dumps({"from": MAIL_OD, "to": do, "subject": temat_, "text": tresc_}).encode(),
        headers={"Authorization": "Bearer " + klucz_api, "Content-Type": "application/json", "User-Agent": "straznik-floty"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return "mail wysłany (HTTP %d)" % r.status
    except urllib.error.HTTPError as e:
        return "mail nie wysłany: HTTP %d %s" % (e.code, e.read().decode(errors="replace")[:150].replace(klucz_api, "***"))
    except Exception as e:  # noqa: BLE001
        return "mail nie wysłany: %s" % (str(e)[:150].replace(klucz_api, "***"))


def powiadom(tekst):
    t = tekst.replace("\\", "").replace('"', "'")[:200]
    if not shutil.which("osascript"):
        return "powiadomienie pominięte (brak osascript – nie macOS)"
    try:
        subprocess.run(["osascript", "-e", 'display notification "%s" with title "Strażnik floty"' % t],
                       capture_output=True, timeout=15)
        return "powiadomienie"
    except Exception as e:  # noqa: BLE001
        return "powiadomienie nieudane: %s" % type(e).__name__
