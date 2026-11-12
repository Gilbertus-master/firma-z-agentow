"""Strażnik floty – adresaci alertów i rdzeń rejestru alarmów (czyste funkcje; skutki w straznik.py).

Alert trafia do ADRESATA kontroli, nie do wszystkich naraz:
  - tabela kontrola → adresat (domyślnie TABELA, nadpisanie: org.yaml → straznik.adresaci):
      recenzent              – rola recenzenta (PR-y bez werdyktu),
      agent                  – agent z ID rozbieżności (przebiegi, martwe przebiegi),
      adresat_zlecenia       – agent, do którego skrzynki trafiło zlecenie po terminie (zlecenia/<agent>.md),
      ceo / wlasciciel / <nazwa agenta> – stały odbiorca (właściciel kontroli);
  - kopia do CEO dopiero przy 2. przypomnieniu (alert nr 3 tego samego zbioru ID – po 2 h i 6 h), o ile alarm
    nie został podjęty (wpis strażnika ma odpowiedź albo status „w toku”);
  - właściciel (founder) dostaje alert, gdy stoi sam CEO (ID „ceo” w przebiegach lub martwych przebiegach albo alarm,
    którego adresatem już był CEO, dochodzi do 2. przypomnienia) albo gdy kończy się budżet (kontrola budzety);
  - błąd źródła (BLAD_ZRODLA) – adresatem jest CEO (infrastruktura), eskalacja jak wyżej.

Rejestr alarmów (rdzeń #7, pełny rejestr typów z progami – później): jeden wpis na kontrolę z odpowiedzialnym, czasem
reakcji (termin = od + reakcja_min), stanem otwarty / podjęty / zamknięty, poziomem eskalacji i czasem usunięcia.
Alarm, który wraca w POWROT_MIN od zamknięcia, to to samo zdarzenie (czas liczy się dalej).
"""
import re
from datetime import timedelta

import kontrole as K

CEO, WLASCICIEL = "ceo", "wlasciciel"
TABELA = {   # kontrola -> (adresat, reakcja_min)
    "pr": ("recenzent", 60),
    "zlecenia": ("adresat_zlecenia", 120),
    "przebiegi": ("agent", 120),
    "martwe": ("agent", 120),
    "konfiguracja": (CEO, 240),
    "budzety": (CEO, 60),
    "testflight": (CEO, 240),
    "automaty": (CEO, 120),
    "klon": (CEO, 120),
}
DOMYSLNY = (CEO, 240)
ADRESACI_SPECJALNI = ("agent", "adresat_zlecenia")
NUMER_DO_CEO = 3          # alert nr 3 = drugie przypomnienie (alerty.PRZYPOMNIENIA_MIN: po 2 h, potem po 6 h)
POWROT_MIN = 30
PAMIEC_ZAMKNIETYCH_DNI = 3
RE_AGENT = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
STANY = ("otwarty", "podjety", "zamkniety")


def tabela(org=None):
    """Tabela adresatów: domyślna + org.yaml → straznik.adresaci ({kontrola: adresat} albo {kontrola: {adresat, reakcja_min}})."""
    t = dict(TABELA)
    nadpis = (((org or {}).get("straznik") or {}).get("adresaci")) or {}
    if isinstance(nadpis, dict):
        for k, v in nadpis.items():
            adr, reak = t.get(k, DOMYSLNY)
            if isinstance(v, dict):
                adr, reak = str(v.get("adresat") or adr), int(v.get("reakcja_min") or reak)
            elif v:
                adr = str(v)
            if adr in ADRESACI_SPECJALNI or RE_AGENT.match(adr):
                t[k] = (adr, reak)
    return t


def agent_z_id(i):
    """przebiegi: „obsluga” / „obsluga:stan”; martwe: „obsluga”; zlecenia: „inzynier.md|data|tytuł”."""
    s = str(i).split("|", 1)[0]
    if s.endswith(".md"):
        s = s[:-3]
    s = s.split(":", 1)[0]
    return s if RE_AGENT.match(s) else None


def adresaci_bazowi(nazwa, w, tab):
    """Odbiorcy pierwszego alertu (bez eskalacji) -> zbiór nazw (agenci, „ceo”, „wlasciciel”)."""
    if w.get("status") == K.BLAD:
        return {CEO}
    adr, _ = tab.get(nazwa, DOMYSLNY)
    if adr in ADRESACI_SPECJALNI:
        baza = {a for a in (agent_z_id(i) for i in w.get("id") or []) if a}
    else:
        baza = {adr}
    return baza or {CEO}


def odbiorcy(nazwa, w, n, tab, podjety=False):
    """-> (posortowana lista odbiorców, poziom: „adresat” | „ceo” | „wlasciciel”). n = numer alertu tego zbioru ID (1 = pierwszy)."""
    baza = adresaci_bazowi(nazwa, w, tab)
    wynik, poziom = set(baza), "adresat"
    stoi_ceo = nazwa in ("przebiegi", "martwe") and w.get("status") != K.BLAD and CEO in baza
    if stoi_ceo or (nazwa == "budzety" and w.get("status") != K.BLAD):
        wynik |= {CEO, WLASCICIEL}
        poziom = WLASCICIEL
    if n >= NUMER_DO_CEO and not podjety:
        if CEO in baza:
            wynik.add(WLASCICIEL)
            poziom = WLASCICIEL
        else:
            wynik.add(CEO)
            if poziom != WLASCICIEL:
                poziom = CEO
    return sorted(wynik), poziom


def podjete_kontrole(teksty):
    """teksty: {plik zleceń: tekst}. Kontrole, których wpis strażnika ma odpowiedź albo status „w toku” -> zbiór nazw."""
    nazwy = {v: k for k, v in K.NAZWY.items()}
    wynik = set()
    for tekst in teksty.values():
        for reszta, status, linie in K.bloki_zlecen(tekst):
            if "od: straznik" not in reszta or "Pilne (strażnik) · " not in reszta:
                continue
            nazwa = nazwy.get(reszta.split("Pilne (strażnik) · ", 1)[1].split(":", 1)[0].strip())
            if nazwa and (not str(status).startswith("otwarte") or not K.odpowiedz_pusta(linie)):
                wynik.add(nazwa)
    return wynik


def rejestr(poprzedni, wyniki, aktywne, teraz, tab, podjete=(), poziomy=None):
    """Rejestr alarmów -> nowy słownik {kontrola: wpis}. Czysta funkcja.

    aktywne: kontrole z alarmem w tym przebiegu (rozbieżność z niewyciszonymi ID albo błąd źródła po progu);
    poziomy: {kontrola: poziom eskalacji z ostatniego alertu}; podjete: kontrole z odpowiedzią na wpis strażnika.
    Wpis: kontrola, odpowiedzialny, reakcja_min, od, termin, stan, poziom, po_terminie, zamkniety_od, czas_usuniecia_min."""
    pop = dict(poprzedni or {})
    wynik = {}
    t = K.iso(teraz)
    for nazwa in sorted(set(pop) | set(aktywne)):
        p = pop.get(nazwa) if isinstance(pop.get(nazwa), dict) else None
        if nazwa in aktywne:
            w = wyniki.get(nazwa) or {}
            adr, reak = tab.get(nazwa, DOMYSLNY)
            odp = ",".join(sorted(adresaci_bazowi(nazwa, w, tab)))
            wraca = False
            if p and p.get("stan") == "zamkniety":
                zam, _ = K.parsuj_czas(p.get("zamkniety_od"))
                wraca = zam is not None and teraz - zam <= timedelta(minutes=POWROT_MIN)
            if p and (p.get("stan") != "zamkniety" or wraca):
                od, _ = K.parsuj_czas(p.get("od"))
                od = od or teraz
            else:
                od = teraz
            termin = od + timedelta(minutes=reak)
            stan = "podjety" if nazwa in podjete else "otwarty"
            wynik[nazwa] = {"kontrola": nazwa, "odpowiedzialny": odp, "reakcja_min": reak, "od": K.iso(od),
                            "termin": K.iso(termin), "stan": stan,
                            "poziom": (poziomy or {}).get(nazwa) or (p or {}).get("poziom") or "adresat",
                            "po_terminie": stan == "otwarty" and teraz > termin}
        elif p:
            if p.get("stan") == "zamkniety":
                zam, _ = K.parsuj_czas(p.get("zamkniety_od"))
                if zam is not None and teraz - zam <= timedelta(days=PAMIEC_ZAMKNIETYCH_DNI):
                    wynik[nazwa] = p
                continue
            od, _ = K.parsuj_czas(p.get("od"))
            wynik[nazwa] = dict(p, stan="zamkniety", zamkniety_od=t, po_terminie=False,
                                czas_usuniecia_min=int((teraz - od).total_seconds() // 60) if od else None)
    return wynik
