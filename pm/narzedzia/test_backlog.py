"""Testy pm/narzedzia/backlog.py na danych syntetycznych (bez sieci): python3 -m unittest discover pm/narzedzia"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

TU = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
import backlog  # noqa: E402

TERAZ = "2026-11-10T09:00"

ARCHITEKT = """# Zlecenia dla agenta architekt

## [otwarte] 2026-11-08 10:00 · od: ceo · Projekt eksportu danych · Z-20261108-01
Opis zadania.
Termin: 2026-11-09 12:00
Zrobione gdy: PR z werdyktem OK
Plan: Q1
Odpowiedź:

## [w toku – sesja-dev, 14:10] 2026-11-09 14:00 · od: ceo · Migracja ról · Z-20261109-02 · issue #12
Termin: 2026-11-10 18:00
Zrobione gdy: migracja w PR
Plan: Q2

## [zrobione 9.11 19:50] 2026-11-07 09:00 · od: pm · Porządek w skrzynce · Z-20261107-03
Termin: 2026-11-08 09:00
Odpowiedź: zrobione, link architekt/analizy/x.md

## [otwarte] 2026-11-09 20:00 · od: tester · Błąd T-01 w formularzu
Opis bez linii Termin.
Zrobione gdy: PR naprawczy

## [czeka na operatora] 2026-11-08 08:00 · od: ceo · Dostęp do konsoli · Z-20261108-05
Termin: 2026-11-08 12:00 → po decyzji operatora (nr 3); wcześniej: 2026-11-08 12:00
Odpowiedź: czekamy

## [otwarte] 2026-11-08 11:00 · od: marketing · Projekt eksportu danych · Z-20261108-07
Termin: 2026-11-12 12:00
"""

CEO = """# Zlecenia dla agenta ceo

## [otwarte] 2026-11-09 07:00 · od: pm · Dyżur blokad 06:45 · Z-20261109-04
Termin: 2026-11-09 19:00
Odpowiedź: przyjęte, scalone #40

## [informacja] 2026-11-09 08:00 · od: prawny · Nowy regulamin obowiązuje
Treść informacji.
"""

BACKLOG = """# Backlog organizacji

Wstęp.

## Jednorazowe

| Id | Właściciel | Temat | Źródło | P | Termin | Status | Plan | Uwaga PM |
|---|---|---|---|---|---|---|---|---|
| J-03 | architekt | Projekt eksportu danych | [zlecenia/architekt.md:3](zlecenia/architekt.md) · Z-20261108-01 · od: ceo | P1 | 2026-11-09 12:00 | otwarte | Q1-ręczny | PO TERMINIE (+0 d) · EV 5k, koszt 2 przebiegi |
| J-07 | ksiegowy | Stare zlecenie bez źródła | [zlecenia/ksiegowy.md:9](zlecenia/ksiegowy.md) · Z-20261101-09 · od: ceo | P3 | 2026-11-02 12:00 | otwarte | – | notatka |
| J-08 | ksiegowy | Zrobione i zarchiwizowane | [zlecenia/ksiegowy.md:20](zlecenia/ksiegowy.md) · Z-20261101-10 · od: ceo | P3 | 2026-11-02 12:00 | zrobione (3.11) | – | – |

## Cykliczne

| Id | Właściciel | Zadanie | Rytm | Koszt / tydzień | Wartość (KPI) | Ostatni przegląd | Uwaga PM |
|---|---|---|---|---|---|---|---|
| C-01 | pm | Przegląd zasadności zadań cyklicznych | pt | – | koszt floty | – | – |
| C-02 | ceo | Przebiegi CEO co godzinę | 7:30–21:30 | – | plan | – | – |
"""

ZADANIA = """model: x
zadania:
- agent: limit
  katalog: null
  priorytet: P1
- agent: ceo
  katalog: ceo
  priorytet: P1
- agent: pm
  katalog: pm
  priorytet: P1
- agent: architekt
  katalog: architekt
  priorytet: P1
"""

ISSUES_JSON = json.dumps([
    {"number": 12, "title": "[zlecenie] Migracja ról", "state": "CLOSED", "closedAt": "2026-11-10T07:00:00Z", "createdAt": "2026-11-09T13:00:00Z",
     "url": "https://example.invalid/issues/12", "labels": [{"name": "typ:zlecenie"}, {"name": "agent:architekt"}, {"name": "prio:P1"}],
     "body": "**Od:** ceo\n**Do:** architekt\n**Termin:** 2026-11-10 18:00\n**Plan / zakład EV:** Q2\n**Pilne:** nie\n"},
    {"number": 15, "title": "[zlecenie] Raport kosztów", "state": "OPEN", "closedAt": None, "createdAt": "2026-11-09T06:00:00Z",
     "url": "https://example.invalid/issues/15", "labels": [{"name": "typ:zlecenie"}, {"name": "agent:finansowy"}, {"name": "prio:pilne"}, {"name": "stan:w-toku"}],
     "body": "**Od:** ceo\n**Do:** finansowy\n**Termin:** 2026-11-09 20:00\n**Zrobione gdy:** plik\n**Plan / zakład EV:** –\n**Pilne:** tak\n"},
])


def repo_tmp(d, github="OWNER/nowa-firma-agenci"):
    d = pathlib.Path(d)
    (d / "zlecenia").mkdir()
    (d / "flota").mkdir()
    (d / "zlecenia" / "architekt.md").write_text(ARCHITEKT, encoding="utf-8")
    (d / "zlecenia" / "ceo.md").write_text(CEO, encoding="utf-8")
    (d / "zlecenia" / "README.md").write_text("# README\n## [otwarte] to nie jest zlecenie\n", encoding="utf-8")
    (d / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    (d / "flota" / "zadania.yaml").write_text(ZADANIA, encoding="utf-8")
    (d / "org.yaml").write_text('organizacja:\n  nazwa: "X"\nrepo:\n  organizacja: "~/x"\n  github: "%s"\n  produkt: []\n' % github, encoding="utf-8")
    return d


def uruchom(*args):
    return subprocess.run([sys.executable, "-I", str(TU / "backlog.py"), *args], capture_output=True, text=True)


def wiersze_j(d):
    return {k[0]: k for k in backlog.wczytaj_backlog(pathlib.Path(d) / "backlog.md")[1]}


class Parsowanie(unittest.TestCase):
    def test_termin(self):
        self.assertEqual(backlog.parsuj_termin("2026-11-09 12:00")[0].strftime("%Y-%m-%d %H:%M"), "2026-11-09 12:00")
        self.assertEqual(backlog.parsuj_termin("2026-11-09")[0].strftime("%H:%M"), "23:59")
        self.assertEqual(backlog.parsuj_termin("2026-11-08 12:00 → 2026-11-12 09:00")[0].day, 12)
        self.assertIsNone(backlog.parsuj_termin("2026-11-08 12:00 → po decyzji (nr 3); wcześniej: 2026-11-08 12:00")[0])
        self.assertIsNone(backlog.parsuj_termin("12 h od najbliższego przebiegu")[0])

    def test_status(self):
        self.assertEqual(backlog.normalizuj_status("otwarte"), "otwarte")
        self.assertEqual(backlog.normalizuj_status("w toku – sesja-dev, 14:10"), "w toku (sesja-dev, 14:10)")
        self.assertEqual(backlog.normalizuj_status("w toku · konto A · 2026-11-09 10:00"), "w toku (konto A · 2026-11-09 10:00)")
        self.assertEqual(backlog.normalizuj_status("czeka na operatora"), "czeka: operatora")
        self.assertEqual(backlog.normalizuj_status("zrobione 9.11 19:50"), "zrobione (9.11 19:50)")
        self.assertEqual(backlog.normalizuj_status("PR #40 – do recenzji"), "otwarte (PR #40 – do recenzji)")
        self.assertTrue(backlog.otwarty("czeka: ceo"))
        self.assertFalse(backlog.otwarty("zrobione (x)"))
        self.assertFalse(backlog.otwarty("informacja"))

    def test_naglowek(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d)
            w = backlog.wpisy_z_pliku(repo / "zlecenia" / "architekt.md", repo)
            self.assertEqual(len(w), 6)
            self.assertEqual(w[0]["zid"], "Z-20261108-01")
            self.assertEqual(w[0]["od"], "ceo")
            self.assertEqual(w[0]["temat"], "Projekt eksportu danych")
            self.assertEqual(w[0]["plan"], "Q1")
            self.assertFalse(w[0]["odpowiedz"], "pusta linia Odpowiedź: to brak odpowiedzi")
            self.assertEqual(w[1]["issue"], 12)
            self.assertTrue(w[2]["odpowiedz"])
            self.assertTrue(w[3]["termin_domyslny"])
            self.assertEqual(w[3]["termin"].strftime("%Y-%m-%d %H:%M"), "2026-11-10 08:00")
            self.assertIsNone(w[4]["termin"])
            self.assertTrue(w[4]["termin_tekst"].startswith("2026-11-08"))


class Generowanie(unittest.TestCase):
    def test_aktualizacja_zachowuje_reczne_i_liczy_po_terminie(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d)
            r = uruchom("--repo", str(repo), "--teraz", TERAZ, "--bez-gh")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("po terminie 2", r.stdout)
            w = wiersze_j(repo)
            # istniejący wiersz: Id, P, Plan i ręczna uwaga zachowane; znacznik PO TERMINIE odświeżony
            j3 = w["J-03"]
            self.assertEqual((j3[4], j3[7]), ("P1", "Q1-ręczny"))
            self.assertIn("PO TERMINIE (+21 h)", j3[8])
            self.assertIn("EV 5k, koszt 2 przebiegi", j3[8])
            self.assertNotIn("+0 d", j3[8])
            # wiersz bez źródła, otwarty – zostaje z uwagą; zrobiony bez źródła – znika
            self.assertIn("źródło zniknęło", w["J-07"][8])
            self.assertIn("notatka", w["J-07"][8])
            self.assertNotIn("J-08", w)
            # nowe Id od maks.+1; kolejność nowych wg pliku i linii
            nowe = [k for k in w if int(k[2:]) > 8]
            self.assertEqual(nowe, ["J-09", "J-10", "J-11", "J-12", "J-13", "J-14", "J-15"])
            po_kluczu = {backlog.klucz_wiersza(k): k for k in w.values()}
            bez_terminu = po_kluczu["zlecenia/architekt.md · błąd t 01 w formularzu"]
            self.assertIn("brak linii Termin: (domyślnie 12 h)", bez_terminu[8])
            self.assertIn("PO TERMINIE (+1 h)", bez_terminu[8])
            self.assertIn("(dom.)", bez_terminu[5])
            czeka = po_kluczu["Z-20261108-05"]
            self.assertTrue(czeka[6].startswith("czeka: operatora"))
            self.assertTrue(czeka[5].startswith("– (2026-11-08"), "termin przesunięty na decyzję – bez daty")
            self.assertNotIn("PO TERMINIE", czeka[8])
            zrob = po_kluczu["Z-20261107-03"]
            self.assertTrue(zrob[6].startswith("zrobione"))
            self.assertEqual(zrob[8], "–")
            dyzur = po_kluczu["Z-20261109-04"]
            self.assertIn("odpowiedź jest – nagłówek otwarty (M-03)", dyzur[8])
            self.assertNotIn("PO TERMINIE", dyzur[8], "po terminie liczy się tylko bez odpowiedzi")
            self.assertEqual(po_kluczu["Z-20261109-02"][4], "P2", "Plan: → P2 domyślnie")
            self.assertIn("issue #12", po_kluczu["Z-20261109-02"][3])
            informacja = po_kluczu["zlecenia/ceo.md · nowy regulamin obowiązuje"]
            self.assertEqual(informacja[6], "informacja")
            tekst = (repo / "backlog.md").read_text(encoding="utf-8")
            self.assertIn("## Cykliczne", tekst)
            self.assertIn("| C-02 | ceo |", tekst)
            self.assertIn("Wstęp.", tekst)
            self.assertIn("_Aktualizacja: 2026-11-10 09:00", tekst)
            # README w zlecenia/ pominięty
            self.assertNotIn("to nie jest zlecenie", tekst)
            # idempotencja
            r2 = uruchom("--repo", str(repo), "--teraz", TERAZ, "--bez-gh")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertEqual(tekst, (repo / "backlog.md").read_text(encoding="utf-8"))

    def test_sprawdz(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d)
            r = uruchom("--repo", str(repo), "--teraz", TERAZ, "--bez-gh", "--sprawdz")
            self.assertEqual(r.returncode, 1)
            self.assertIn("PO TERMINIE · J-03 · architekt · Projekt eksportu danych", r.stdout)
            self.assertIn("DUBEL · J-03 i J-", r.stdout)
            self.assertIn("BRAK WIERSZA C · architekt", r.stdout)
            self.assertNotIn("BRAK WIERSZA C · ceo", r.stdout)
            self.assertNotIn("BRAK WIERSZA C · pm", r.stdout)
            self.assertNotIn("BRAK WIERSZA C · limit", r.stdout, "katalog: null = poza blokadą, bez wiersza C")
            self.assertEqual((repo / "backlog.md").read_text(encoding="utf-8"), BACKLOG, "--sprawdz nic nie zapisuje")

    def test_json_i_podglad(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d)
            r = uruchom("--repo", str(repo), "--teraz", TERAZ, "--bez-gh", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            dane = json.loads(r.stdout)
            self.assertEqual(dane["liczby"]["po_terminie"], 2)
            self.assertEqual(dane["liczby"]["gh"], "pominięte")
            self.assertIn("architekt", dane["bez_wiersza_c"])
            self.assertEqual(len(dane["wiersze"]), 9, "8 zleceń + 1 otwarty wiersz bez źródła")
            r = uruchom("--repo", str(repo), "--teraz", TERAZ, "--bez-gh", "--podglad")
            self.assertEqual(r.returncode, 0)
            self.assertIn("| J-03 |", r.stdout)
            self.assertEqual((repo / "backlog.md").read_text(encoding="utf-8"), BACKLOG)

    def test_zle_wywolanie(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(uruchom("--repo", d).returncode, 2)
            repo_tmp(d)
            self.assertEqual(uruchom("--repo", d, "--teraz", "wczoraj").returncode, 2)


class Issues(unittest.TestCase):
    def _gh(self, d, tresc):
        kat = pathlib.Path(d) / "bin"
        kat.mkdir()
        gh = kat / "gh"
        gh.write_text("#!/bin/sh\n" + tresc, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        env = dict(os.environ)
        env["PATH"] = str(kat) + os.pathsep + env.get("PATH", "")
        return env

    def test_issues_scalone_z_md(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d, github="firma/firma-agenci")
            env = self._gh(d, "cat <<'EOF'\n%s\nEOF\n" % ISSUES_JSON)
            r = subprocess.run([sys.executable, "-I", str(TU / "backlog.py"), "--repo", str(repo), "--teraz", TERAZ],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Issues 2 (gh: ok)", r.stdout)
            w = {backlog.klucz_wiersza(k): k for k in wiersze_j(repo).values()}
            migracja = w["Z-20261109-02"]
            self.assertIn("[#12](https://example.invalid/issues/12)", migracja[3])
            self.assertIn("status md ≠ Issue", migracja[8], "md w toku, Issue zamknięty = rozjazd")
            raport = w["#15"]
            self.assertEqual(raport[1], "finansowy")
            self.assertTrue(raport[2].startswith("PILNE · Raport kosztów"))
            self.assertEqual(raport[4], "P1")
            self.assertEqual(raport[6], "w toku")
            self.assertIn("PO TERMINIE (+13 h)", raport[8])
            r = subprocess.run([sys.executable, "-I", str(TU / "backlog.py"), "--repo", str(repo), "--teraz", TERAZ, "--sprawdz"],
                               capture_output=True, text=True, env=env)
            self.assertIn("ROZJAZD md ≠ Issue", r.stdout)

    def test_gh_pada(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d, github="firma/firma-agenci")
            env = self._gh(d, "echo 'HTTP 401: Bad credentials' >&2\nexit 1\n")
            r = subprocess.run([sys.executable, "-I", str(TU / "backlog.py"), "--repo", str(repo), "--teraz", TERAZ],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, "błąd gh nie przerywa pracy")
            self.assertIn("gh: błąd: HTTP 401", r.stdout)
            self.assertIn("UWAGA: Issues pominięte", r.stderr)
            self.assertEqual(len(wiersze_j(repo)), 9)

    def test_zaslepka_owner_pomija_gh(self):
        with tempfile.TemporaryDirectory() as d:
            repo = repo_tmp(d)
            env = self._gh(d, "echo 'gh nie powinien być wywołany' >&2\nexit 7\n")
            r = subprocess.run([sys.executable, "-I", str(TU / "backlog.py"), "--repo", str(repo), "--teraz", TERAZ],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0)
            self.assertIn("gh: pominięte (org.yaml", r.stdout)


if __name__ == "__main__":
    unittest.main()
