"""Testy pm/narzedzia/sesje.py na danych syntetycznych: python3 -m unittest discover pm/narzedzia"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

TU = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
import sesje  # noqa: E402

REJESTR = """# Rejestr sesji

Opis.

| Data | Id | Tytuł | Rodzic | Cel / zrobione gdy | Status | Wynik |
|---|---|---|---|---|---|---|
| 2026-11-08 10:00 | local_aaaa1111-0000 | Projekt eksportu | ceo (czat A) | PR | otwarta | – |
| 2026-11-10 08:30 | local_bbbb2222-0000 | Testy E2E | ceo (czat A) | testy | otwarta | – |
| 2026-11-09 | local_cccc3333-0000 | Audyt UX | – | audyt | otwarta | – |
| 2026-11-10 07:00 | local_dddd4444-0000 | Projekt Eksportu! | local_zzzz9999-0000 | PR | otwarta | – |
| 2026-11-09 12:00 | local_eeee5555-0000 | Zamknięta bez linku | ceo | plik | zamknięta | – |
| 2026-11-09 12:00 | local_ffff6666-0000 | Zamknięta dobrze | local_aaaa1111-0000 | plik | zamknięta | `pm/analizy/x.md` |
| 2026-11-09 13:00 | local_gggg7777-0000 | Porzucona bez powodu | ceo | plik | porzucona | – |
| 2026-11-09 13:00 | local_hhhh8888-0000 | Porzucona dobrze | ceo | plik | porzucona (dubel) | przejmuje: local_aaaa1111-0000 |
| 2026-11-09 13:00 | local_hhhh8888-0000 | Id powtórzony | ceo | plik | zamknięta | link |
| 2026-11-09 13:00 | local_iiii9999-0000 | Za mało | kolumn | otwarta | – |
| 2026-11-10 08:00 | local_jjjj0000-0000 | Status dziwny | ceo | plik | w toku | – |
"""

CZYSTY = """| Data | Id | Tytuł | Rodzic | Cel / zrobione gdy | Status | Wynik |
|---|---|---|---|---|---|---|
| 2026-11-10 08:30 | local_bbbb2222-0000 | Testy E2E | ceo (czat A) | testy | otwarta | – |
| 2026-11-09 12:00 | local_ffff6666-0000 | Zamknięta dobrze | local_bbbb2222-0000 | plik | zamknięta | `pm/analizy/x.md` |
"""


def uruchom(plik, *args):
    return subprocess.run([sys.executable, "-I", str(TU / "sesje.py"), "--plik", str(plik), "--teraz", "2026-11-10T09:00", *args],
                          capture_output=True, text=True)


class Sesje(unittest.TestCase):
    def test_uwagi(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "rejestr-sesji.md"
            p.write_text(REJESTR, encoding="utf-8")
            r = uruchom(p, "--json")
            self.assertEqual(r.returncode, 1, r.stderr)
            dane = json.loads(r.stdout)
            self.assertEqual(dane["wiersze"], 10)
            self.assertEqual(dane["otwarte"], 4)
            problemy = {(u["id"], u["problem"]) for u in dane["uwagi"]}
            self.assertIn(("local_aaaa1111-0000", "otwarta > 24 h"), problemy)
            self.assertNotIn(("local_bbbb2222-0000", "otwarta > 24 h"), problemy)
            self.assertIn(("local_cccc3333-0000", "bez rodzica"), problemy)
            self.assertNotIn(("local_cccc3333-0000", "otwarta > 24 h"), problemy, "sama data = koniec dnia 23:59 → 9 h, nie > 24")
            self.assertIn(("local_dddd4444-0000", "rodzic nieznany"), problemy)
            self.assertIn(("local_eeee5555-0000", "zamknięta bez wyniku"), problemy)
            self.assertNotIn(("local_ffff6666-0000", "zamknięta bez wyniku"), problemy)
            self.assertIn(("local_gggg7777-0000", "porzucona bez przejęcia"), problemy)
            self.assertNotIn(("local_hhhh8888-0000", "porzucona bez przejęcia"), problemy)
            self.assertIn(("local_hhhh8888-0000", "id powtórzony"), problemy)
            self.assertIn(("local_jjjj0000-0000", "status nieznany"), problemy)
            self.assertTrue(any(u["problem"] == "zła liczba kolumn" and u["linia"] == 16 for u in dane["uwagi"]))
            dublet = [u for u in dane["uwagi"] if u["problem"] == "dublet"]
            self.assertEqual(len(dublet), 1)
            self.assertIn("local_aaaa1111-0000", dublet[0]["id"])
            self.assertIn("local_dddd4444-0000", dublet[0]["id"])
            szczegol = next(u["szczegol"] for u in dane["uwagi"] if (u["id"], u["problem"]) == ("local_aaaa1111-0000", "otwarta > 24 h"))
            self.assertIn("47 h", szczegol)
            r = uruchom(p)
            self.assertEqual(r.returncode, 1)
            self.assertIn("| Linia | Id | Tytuł | Problem | Szczegół |", r.stdout)
            self.assertTrue(r.stdout.rstrip().endswith("sesje: 10 wierszy · otwarte 4 · uwagi %d" % len(dane["uwagi"])))

    def test_czysty_rejestr_i_prog(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "rejestr-sesji.md"
            p.write_text(CZYSTY, encoding="utf-8")
            r = uruchom(p)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("uwagi 0 · OK", r.stdout)
            r = uruchom(p, "--godziny", "0")
            self.assertEqual(r.returncode, 1)
            self.assertIn("otwarta > 0 h", r.stdout)

    def test_brak_pliku_i_zly_czas(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(uruchom(pathlib.Path(d) / "nie-ma.md").returncode, 2)
            p = pathlib.Path(d) / "r.md"
            p.write_text(CZYSTY, encoding="utf-8")
            r = subprocess.run([sys.executable, "-I", str(TU / "sesje.py"), "--plik", str(p), "--teraz", "dziś"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)

    def test_funkcje(self):
        self.assertEqual(sesje.status_norm("Zamknięta (link)"), "zamknięta")
        self.assertEqual(sesje.status_norm("porzucona (dubel)"), "porzucona")
        self.assertEqual(sesje.norm_tytul("Projekt Eksportu!"), sesje.norm_tytul("projekt eksportu"))
        self.assertEqual(sesje.parsuj_date("2026-11-09")[0].strftime("%H:%M"), "23:59")
        self.assertTrue(sesje.parsuj_date("2026-11-09 08:15")[1])


if __name__ == "__main__":
    unittest.main()
