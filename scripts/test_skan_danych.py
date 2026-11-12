#!/usr/bin/env python3
"""Testy skanera danych osobowych (scripts/skan-danych.py). Bez sieci; repozytoria tymczasowe, dane fikcyjne.

  python3 -m unittest discover -s scripts -p 'test_skan_danych.py'
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location("skan_danych", pathlib.Path(__file__).resolve().parent / "skan-danych.py")
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

# Wartości fikcyjne składane w teście z sumą kontrolną liczoną na miejscu – żadna nie stoi w pliku jako całość, więc skaner repo
# (grupa „skan danych: repo”) nie zgłasza tego pliku i nie potrzebuje wyjątku.


def _pesel(baza):
    w = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    return baza + str((10 - sum(int(c) * k for c, k in zip(baza, w)) % 10) % 10)


def _nip(baza):
    return baza + str(sum(int(a) * b for a, b in zip(baza, (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11)


def _iban(kraj, bban):
    liczba = int("".join(str(int(z, 36)) for z in bban + kraj + "00"))
    return "%s%02d%s" % (kraj, 98 - liczba % 97, bban)


def _sep(*czesci, z="-"):
    return z.join(czesci)


PESEL_OK = _pesel("0207080362")
NIP_OK = _nip("123456321")
IBAN_OK = _iban("PL", "10901014" + "0" * 4 + "0712198" + "1287")
DOWOD_OK = "ABA" + "3" + "00000"                  # wzór urzędowy dowodu (suma kontrolna 3)
EMAIL_PRYW = "@".join(("jan.nowak", "poczta.pl"))
TEL = _sep("600", "700", "800")
DOMENA = "firma.example"


def kategorie(tekst):
    return [k for k, _ in sd.skanuj_linie(tekst, DOMENA)]


class Wzorce(unittest.TestCase):
    def test_pesel_z_suma_i_data(self):
        self.assertEqual(kategorie("klient %s pisze" % PESEL_OK), ["PESEL"])
        self.assertEqual(kategorie(PESEL_OK[:10] + str((int(PESEL_OK[10]) + 1) % 10)), [])   # zła suma
        self.assertEqual(kategorie(_pesel("0213080362")), [])            # miesiąc 13 – nie PESEL, nawet z sumą
        self.assertEqual(kategorie("x%sx" % PESEL_OK), [])               # część dłuższego identyfikatora

    def test_nip_suma_i_krs(self):
        self.assertEqual(kategorie("NIP " + _sep(NIP_OK[:3], NIP_OK[3:6], NIP_OK[6:8], NIP_OK[8:])), ["NIP"])
        self.assertEqual(kategorie(NIP_OK), ["NIP"])
        self.assertEqual(kategorie(NIP_OK[:9] + str((int(NIP_OK[9]) + 1) % 10)), [])   # zła suma
        self.assertEqual(kategorie("KRS 0000123456"), [])              # numer KRS zaczyna się od 0
        self.assertEqual(kategorie("1111111111"), [])

    def test_iban_mod_97(self):
        self.assertEqual(kategorie("konto " + IBAN_OK), ["IBAN"])
        self.assertEqual(kategorie("konto " + " ".join(IBAN_OK[i:i + 4] for i in range(0, len(IBAN_OK), 4))), ["IBAN"])
        self.assertEqual(kategorie(IBAN_OK[:2] + "%02d" % ((int(IBAN_OK[2:4]) + 1) % 100) + IBAN_OK[4:]), [])

    def test_email_wyjatki(self):
        self.assertEqual(kategorie("pisz do " + EMAIL_PRYW), ["EMAIL"])
        for ok in ("operator@firma.example", "ceo@agenci.firma.example", "jan@example.com", "a@b.invalid",
                   "kancelaria@mf.gov.pl", "123+bot@users.noreply.github.com"):
            self.assertEqual(kategorie(ok), [], ok)
        self.assertEqual(sd.skanuj_linie("@".join(("x", "firma.pl")), "firma.pl"), [])  # domena firmy z org.yaml

    def test_telefon_z_separatorami(self):
        for t in ("+48 " + _sep("600", "700", "800", z=" "), TEL, "+48" + TEL.replace("-", ""), _sep("600", "700", "800", z=" ")):
            self.assertEqual(kategorie("tel. " + t), ["TELEFON"], t)
        for t in ("600700800", "2026-11-12", "v1.600.700.800", "12:30:45"):
            self.assertEqual(kategorie(t), [], t)

    def test_dokument(self):
        self.assertEqual(kategorie("dowód " + DOWOD_OK), ["DOKUMENT"])
        self.assertEqual(kategorie(DOWOD_OK[:-1] + "1"), [])            # zła cyfra kontrolna
        self.assertEqual(kategorie("US 9910743"), [])                  # numer znaku towarowego ze spacją

    def test_maska_nie_zawiera_wartosci(self):
        for kat, w in (("PESEL", PESEL_OK), ("EMAIL", EMAIL_PRYW), ("IBAN", IBAN_OK)):
            m = sd.maska(kat, w)
            self.assertNotIn(w, m)
            self.assertNotIn("jan.nowak", m)


class Repo(unittest.TestCase):
    def setUp(self):
        self.kat = pathlib.Path(tempfile.mkdtemp(prefix="skan-danych-"))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        (self.kat / "org.yaml").write_text('organizacja:\n  domena: "%s"\n' % DOMENA, encoding="utf-8")
        (self.kat / "bezpieczenstwo").mkdir()

    def tearDown(self):
        shutil.rmtree(self.kat, ignore_errors=True)

    def git(self, *a):
        subprocess.run(["git", "-C", str(self.kat)] + list(a), check=True, capture_output=True)

    def uruchom(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            kod = sd.main(["--repo", str(self.kat)] + list(argv))
        return kod, out.getvalue()

    def test_sledzone_pliki_wyjatki_i_kody(self):
        (self.kat / "przebiegi").mkdir()
        (self.kat / "przebiegi/ceo.jsonl").write_text('{"uwaga": "klient %s"}\n' % PESEL_OK, encoding="utf-8")
        (self.kat / "obraz.png").write_bytes(b"\x89PNG\0" + PESEL_OK.encode())
        (self.kat / "nieśledzony.md").write_text(NIP_OK, encoding="utf-8")
        self.git("add", "org.yaml", "przebiegi/ceo.jsonl", "obraz.png")
        self.git("commit", "-qm", "x")
        kod, wynik = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertIn("PESEL    przebiegi/ceo.jsonl:1:", wynik)
        self.assertNotIn(PESEL_OK, wynik)                                 # wartość zamaskowana
        self.assertNotIn("obraz.png", wynik)                             # binarne pomijane
        self.assertNotIn("nieśledzony", wynik)                           # tylko pliki śledzone
        kod, wynik = self.uruchom("--json")
        self.assertEqual(json.loads(wynik)["trafienia"][0]["kategoria"], "PESEL")
        # wyjątek: skrót wartości, nie wartość
        (self.kat / sd.WYJATKI).write_text("# test\nprzebiegi/ceo.jsonl\tPESEL\t%s\tdane fikcyjne\n" % sd.skrot(PESEL_OK), encoding="utf-8")
        self.assertEqual(self.uruchom()[0], 0)
        (self.kat / sd.WYJATKI).write_text("przebiegi/ceo.jsonl\tPESEL\t%s\n" % sd.skrot(PESEL_OK), encoding="utf-8")   # bez powodu
        self.assertEqual(self.uruchom()[0], 2)
        (self.kat / sd.WYJATKI).write_text("inny.md\tPESEL\t%s\tpowód\n" % sd.skrot(PESEL_OK), encoding="utf-8")         # inny plik
        self.assertEqual(self.uruchom()[0], 1)

    def test_staged_tylko_linie_dodane(self):
        (self.kat / "a.md").write_text("stara linia %s\n" % NIP_OK, encoding="utf-8")
        self.git("add", "a.md")
        self.git("commit", "-qm", "x")
        (self.kat / "a.md").write_text("stara linia %s\nnowa linia tel. %s\n" % (NIP_OK, TEL), encoding="utf-8")
        self.git("add", "a.md")
        kod, wynik = self.uruchom("--staged")
        self.assertEqual(kod, 1)
        self.assertIn("TELEFON  a.md:2:", wynik)
        self.assertNotIn("NIP", wynik)                                    # stara linia nie jest w poczekalni
        self.git("commit", "-qm", "y")
        self.assertEqual(self.uruchom("--staged")[0], 0)

    def test_pliki_wskazane(self):
        (self.kat / "b.md").write_text("pisz: %s\n" % EMAIL_PRYW, encoding="utf-8")
        kod, wynik = self.uruchom("--pliki", "b.md")
        self.assertEqual(kod, 1)
        self.assertIn("j***@poczta.pl", wynik)


if __name__ == "__main__":
    unittest.main()
