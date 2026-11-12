"""Testy scripts/rejestry-git.py – rejestr wrażliwy: w gicie (pliki i historia) tylko nagłówki i wiersze bez danych."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("rejestry_git", pathlib.Path(__file__).resolve().parent / "rejestry-git.py")
RG = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RG)

KONF = "rej/*.tsv\tnaglowek:id,rodzaj,termin\nrej/*.tsv\tnaglowek:czas,id,wynik\nrej/**/*.jsonl\ttyp:zalozenie,test\n"
NAGLOWEK = "id\trodzaj\ttermin"
WPIS = "SP-20261110-01\tsprawa-poufna\t2026-11-13"
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class Repo(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp(prefix="rejestry-git-"))
        self.git("init", "-q")
        (self.d / "bezpieczenstwo").mkdir()
        (self.d / RG.KONFIGURACJA).write_text("# konfiguracja\n" + KONF, encoding="utf-8")
        (self.d / "rej" / "a").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def git(self, *a):
        subprocess.run(["git", "-C", str(self.d), "-c", "user.name=t", "-c", "user.email=t@example.com", *a], check=True,
                       capture_output=True, env=ENV)

    def zapisz(self, plik, tekst, msg="x"):
        (self.d / plik).write_text(tekst, encoding="utf-8")
        self.git("add", plik)
        self.git("commit", "-qm", msg)

    def uruchom(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            kod = RG.main(["--repo", str(self.d), *argv])
        return kod, out.getvalue()

    def test_naglowki_i_typy_dozwolone(self):
        self.zapisz("rej/sprawy.tsv", "# rejestr\n%s\n\nczas\tid\twynik\n" % NAGLOWEK)
        self.zapisz("rej/a/log.jsonl", json.dumps({"typ": "zalozenie"}) + "\n" + json.dumps({"typ": "test", "kanal": "mail"}) + "\n")
        self.zapisz("notatka.tsv", WPIS + "\n")                                   # plik spoza wzorców – nie dotyczy
        self.assertEqual(self.uruchom()[0], 0)

    def test_wiersz_danych_w_pliku_i_w_historii_bez_tresci(self):
        self.zapisz("rej/sprawy.tsv", NAGLOWEK + "\n" + WPIS + "\n", "wpis")
        kod, wynik = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertIn("rej/sprawy.tsv linia 2", wynik)
        self.assertNotIn("SP-20261110-01", wynik); self.assertNotIn("poufna", wynik)
        self.zapisz("rej/sprawy.tsv", NAGLOWEK + "\n", "usunięcie")                 # usunięty z pliku – zostaje w historii
        self.assertEqual(self.uruchom("--bez-historii")[0], 0)
        kod, wynik = self.uruchom()
        self.assertEqual(kod, 1); self.assertIn("commit ", wynik); self.assertNotIn("SP-20261110-01", wynik)

    def test_jsonl_typ_spoza_listy(self):
        self.zapisz("rej/a/log.jsonl", json.dumps({"typ": "alarm", "sprawa": "SP-20261110-01"}) + "\n{zly json\n")
        kod, wynik = self.uruchom("--bez-historii")
        self.assertEqual(kod, 1)
        self.assertIn("„alarm”", wynik); self.assertIn("nieczytelny JSON", wynik); self.assertNotIn("SP-20261110-01", wynik)

    def test_zla_konfiguracja_i_pusta(self):
        (self.d / RG.KONFIGURACJA).write_text("rej/*.tsv\tkolumny:a,b\n", encoding="utf-8")
        self.assertEqual(self.uruchom()[0], 2)
        (self.d / RG.KONFIGURACJA).write_text("# tylko komentarz\n", encoding="utf-8")
        self.zapisz("rej/sprawy.tsv", WPIS + "\n")
        self.assertEqual(self.uruchom()[0], 0)                                         # pusta konfiguracja = nic do sprawdzenia


if __name__ == "__main__":
    unittest.main()
