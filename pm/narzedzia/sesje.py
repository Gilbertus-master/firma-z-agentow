#!/usr/bin/env python3
"""Przegląd rejestru sesji (rejestr-sesji.md) – role/pm.md, Codziennie pkt 5; zasady.md B „Hierarchia sesji”.

  python3 -I pm/narzedzia/sesje.py [--repo DIR | --plik rejestr-sesji.md] [--teraz ISO] [--godziny 24] [--json]

Czyta tabelę `| Data | Id | Tytuł | Rodzic | Cel / zrobione gdy | Status | Wynik |` i wypisuje uwagi:
  otwarta > N h        – status `otwarta`, a od kolumny Data (RRRR-MM-DD GG:MM; sama data = koniec dnia 23:59) minęło > N h (domyślnie 24)
  bez rodzica          – Rodzic pusty, „–”, „?”, „brak” (łańcuch musi kończyć się u CEO)
  rodzic nieznany      – Rodzic wskazuje Id sesji (`local_…`/`sesja:…`), którego nie ma w rejestrze
  dublet               – dwie i więcej otwartych sesji o tym samym tytule (bez wielkości liter i interpunkcji)
  zamknięta bez wyniku – status `zamknięta`, a Wynik pusty albo „–” (zamknięcie wymaga linku do wyniku sprawdzonego u źródła)
  porzucona bez przejęcia – status `porzucona` bez powodu / „przejmuje:”
  id powtórzony        – to samo Id w dwóch wierszach; zła liczba kolumn – wiersz tabeli bez 7 komórek
Wynik: tabela uwag + linia podsumowania `sesje: N wierszy · otwarte N · uwagi N`. Kod 0 bez uwag · 1 są uwagi · 2 złe wywołanie.
PM niczego tu nie zamyka – uwagi idą do CEO (zamyka albo przypisuje). Biblioteka standardowa, bez sieci."""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

DATA = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}):(\d{2}))?")
ID_SESJI = re.compile(r"(local_[\w-]{8,}|sesja:[\w-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
KOLUMNY = ["Data", "Id", "Tytuł", "Rodzic", "Cel", "Status", "Wynik"]
PUSTE = {"", "–", "-", "—", "?", "brak", "n/d"}


def parsuj_date(tekst):
    m = DATA.search(tekst or "")
    if not m:
        return None, False
    try:
        d = dt.datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None, False
    if m.group(2):
        return d.replace(hour=int(m.group(2)) % 24, minute=int(m.group(3))), True
    return d.replace(hour=23, minute=59), False


def status_norm(s):
    n = (s or "").strip().lower()
    for k in ("otwarta", "zamknięta", "zamknieta", "porzucona"):
        if n.startswith(k):
            return "zamknięta" if k == "zamknieta" else k
    return n.split()[0] if n else ""


def norm_tytul(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]+", " ", (t or "").lower())).strip()


def wczytaj(plik):
    """-> lista wierszy {nr_linii, komorki[...]} z tabeli (pomija nagłówek i separator) + lista błędów formatu."""
    wiersze, bledy = [], []
    for nr, l in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1):
        s = l.strip()
        if not s.startswith("|"):
            continue
        kom = [k.strip() for k in s.strip("|").split("|")]
        if kom and kom[0] == KOLUMNY[0]:
            continue
        if all(re.fullmatch(r":?-{3,}:?", k) for k in kom if k) and kom:
            continue
        if len(kom) != len(KOLUMNY):
            bledy.append({"linia": nr, "id": kom[1] if len(kom) > 1 else "", "tytul": kom[2] if len(kom) > 2 else "",
                          "problem": "zła liczba kolumn", "szczegol": "%d zamiast %d (znak | w treści – zastąp „/”)" % (len(kom), len(KOLUMNY))})
            continue
        wiersze.append({"linia": nr, **dict(zip(["data", "id", "tytul", "rodzic", "cel", "status", "wynik"], kom))})
    return wiersze, bledy


def sprawdz(wiersze, teraz, godziny=24):
    uwagi = []
    ids = {}
    for w in wiersze:
        ids.setdefault(w["id"], []).append(w["linia"])
    for i, linie in ids.items():
        if len(linie) > 1 and i not in PUSTE:
            uwagi.append({"linia": linie[0], "id": i, "tytul": "", "problem": "id powtórzony", "szczegol": "linie %s" % ", ".join(map(str, linie))})
    znane_id = {x.lower() for x in ids}
    otwarte_po_tytule = {}
    for w in wiersze:
        st = status_norm(w["status"])
        base = {"linia": w["linia"], "id": w["id"], "tytul": w["tytul"][:60]}
        if st == "otwarta":
            od, z_godzina = parsuj_date(w["data"])
            if od is None:
                uwagi.append({**base, "problem": "otwarta bez daty", "szczegol": "kolumna Data: %r" % w["data"]})
            elif teraz - od > dt.timedelta(hours=godziny):
                h = int((teraz - od).total_seconds() // 3600)
                uwagi.append({**base, "problem": "otwarta > %d h" % godziny,
                              "szczegol": "od %s (%d h)%s" % (od.strftime("%Y-%m-%d %H:%M"), h, "" if z_godzina else " – Data bez godziny, liczone od końca dnia")})
            otwarte_po_tytule.setdefault(norm_tytul(w["tytul"]), []).append(w["id"])
        elif st == "zamknięta":
            if w["wynik"].strip() in PUSTE:
                uwagi.append({**base, "problem": "zamknięta bez wyniku", "szczegol": "Wynik pusty – wpisz link do wyniku sprawdzonego u źródła"})
        elif st == "porzucona":
            if "przejm" not in (w["status"] + " " + w["wynik"]).lower() or w["wynik"].strip() in PUSTE and "(" not in w["status"]:
                uwagi.append({**base, "problem": "porzucona bez przejęcia", "szczegol": "status: %s" % w["status"][:80]})
        elif st:
            uwagi.append({**base, "problem": "status nieznany", "szczegol": "%r (dozwolone: otwarta · zamknięta · porzucona)" % w["status"][:40]})
        else:
            uwagi.append({**base, "problem": "bez statusu", "szczegol": ""})
        rodzic = w["rodzic"].strip()
        if rodzic.lower() in PUSTE:
            uwagi.append({**base, "problem": "bez rodzica", "szczegol": "każda sesja ma rodzica; łańcuch kończy się u CEO"})
        else:
            for m in ID_SESJI.finditer(rodzic):
                if m.group(1).lower() not in znane_id:
                    uwagi.append({**base, "problem": "rodzic nieznany", "szczegol": "Rodzic %s nie występuje w rejestrze" % m.group(1)})
    for t, lista in otwarte_po_tytule.items():
        if t and len(lista) > 1:
            uwagi.append({"linia": 0, "id": ", ".join(lista), "tytul": t[:60], "problem": "dublet", "szczegol": "%d otwarte sesje o tym samym tytule" % len(lista)})
    return uwagi


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[2]))
    a.add_argument("--plik", help="ścieżka rejestru (domyślnie <repo>/rejestr-sesji.md)")
    a.add_argument("--teraz", help="czas „teraz” ISO – do testów; domyślnie zegar")
    a.add_argument("--godziny", type=int, default=24, help="próg „otwarta > N h” (domyślnie 24)")
    a.add_argument("--json", action="store_true")
    o = a.parse_args(argv)
    plik = pathlib.Path(o.plik) if o.plik else pathlib.Path(o.repo) / "rejestr-sesji.md"
    if not plik.exists():
        print("BŁĄD: brak pliku %s" % plik, file=sys.stderr)
        return 2
    try:
        teraz = dt.datetime.fromisoformat(o.teraz) if o.teraz else dt.datetime.now().replace(second=0, microsecond=0)
    except ValueError:
        print("BŁĄD: --teraz musi być ISO, np. 2026-11-09T19:00", file=sys.stderr)
        return 2
    wiersze, bledy = wczytaj(plik)
    uwagi = bledy + sprawdz(wiersze, teraz, o.godziny)
    otwarte = sum(1 for w in wiersze if status_norm(w["status"]) == "otwarta")
    pods = "sesje: %d wierszy · otwarte %d · uwagi %d" % (len(wiersze), otwarte, len(uwagi))
    if o.json:
        print(json.dumps({"teraz": teraz.isoformat(), "wiersze": len(wiersze), "otwarte": otwarte, "uwagi": uwagi}, ensure_ascii=False, indent=1))
        return 1 if uwagi else 0
    if uwagi:
        print("| Linia | Id | Tytuł | Problem | Szczegół |\n|---|---|---|---|---|")
        for u in uwagi:
            print("| %s | %s | %s | %s | %s |" % (u["linia"] or "–", u["id"] or "–", u["tytul"].replace("|", "/") or "–", u["problem"], u["szczegol"].replace("|", "/")))
    print(pods + ("" if uwagi else " · OK"))
    return 1 if uwagi else 0


if __name__ == "__main__":
    sys.exit(main())
