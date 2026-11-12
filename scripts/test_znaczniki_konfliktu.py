"""Żaden śledzony plik tekstowy nie ma znaczników konfliktu git: python3 -m unittest discover -s scripts -p 'test_znaczniki_konfliktu.py'

Znacznik = linia zaczynająca się od 7 znaków <, > albo | (styl diff3), po nich spacja albo koniec linii. Samych 7 znaków „=”
nie liczymy (podkreślenie nagłówka Markdown). Wzorce składane z części, żeby test nie znalazł samego siebie.
Plik, który celowo cytuje znaczniki (np. instrukcja rozwiązywania konfliktów), wpisz do WYJATKI z powodem.
Ta sama kontrola działa w scripts/zapisz.sh przed commitem.
"""
import pathlib
import re
import subprocess
import unittest

KORZEN = pathlib.Path(__file__).resolve().parent.parent
ZN = [z * 7 for z in "<>|"]
ZNACZNIK = re.compile("^(?:" + "|".join(re.escape(z) for z in ZN) + ")(?: |$)")

# ścieżka -> powód (pliki, które celowo cytują znaczniki na początku linii)
WYJATKI = {}


def linie_ze_znacznikiem(tekst):
    return [i for i, linia in enumerate(tekst.split("\n"), 1) if ZNACZNIK.match(linia.rstrip("\r"))]


def sledzone(korzen=KORZEN):
    wynik = subprocess.run(["git", "ls-files", "-z"], cwd=korzen, capture_output=True, check=True).stdout
    return [n for n in wynik.decode("utf-8", "surrogateescape").split("\0") if n]


def znaczniki_w_repo(korzen=KORZEN, wyjatki=None):
    """[(ścieżka, [numery linii])] – pliki binarne (bajt zerowy) i nieczytelne pomijane."""
    wyjatki = WYJATKI if wyjatki is None else wyjatki
    out = []
    for n in sledzone(korzen):
        if n in wyjatki:
            continue
        p = korzen / n
        try:
            dane = p.read_bytes()
        except OSError:
            continue
        if b"\0" in dane[:8192]:
            continue
        linie = linie_ze_znacznikiem(dane.decode("utf-8", "replace"))
        if linie:
            out.append((n, linie[:5]))
    return out


class TestZnacznikiKonfliktu(unittest.TestCase):
    def test_wzorzec(self):
        lt, gt, kr = ZN
        for s in [lt + " HEAD", gt + " origin/main", lt, kr + " wspólny przodek", gt + " x\r"]:
            self.assertTrue(linie_ze_znacznikiem(s), "powinien złapać: %r" % s)
        for s in ["Nagłówek\n" + "=" * 7, "a " + lt + " b", "  " + gt + " wcięte", lt + "<", "<" * 6 + " sześć", "|| x"]:
            self.assertEqual(linie_ze_znacznikiem(s), [], "nie powinien złapać: %r" % s)

    def test_repo_tymczasowe(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            k = pathlib.Path(d)
            subprocess.run(["git", "init", "-q"], cwd=k, check=True)
            (k / "dobry.md").write_text("Tytuł\n=======\n")
            (k / "zly.md").write_text("a\n%s HEAD\nb\n=======\nc\n%s gałąź\n" % (ZN[0], ZN[1]))
            (k / "bin.dat").write_bytes(b"\0" + ZN[0].encode() + b" x\n")
            (k / "nieśledzony.md").write_text(ZN[0] + " x\n")
            subprocess.run(["git", "add", "dobry.md", "zly.md", "bin.dat"], cwd=k, check=True)
            self.assertEqual(znaczniki_w_repo(k, {}), [("zly.md", [2, 6])])
            self.assertEqual(znaczniki_w_repo(k, {"zly.md": "cytuje znaczniki"}), [])

    def test_wyjatki_istnieja_i_maja_powod(self):
        nazwy = set(sledzone())
        for n, powod in WYJATKI.items():
            self.assertIn(n, nazwy, "wyjątek dla nieśledzonego pliku: " + n)
            self.assertGreater(len(powod.strip()), 10, "wyjątek bez powodu: " + n)

    def test_repo_bez_znacznikow(self):
        nazwy = sledzone()
        self.assertGreater(len(nazwy), 50, "za mało plików – zły katalog?")
        bledy = znaczniki_w_repo()
        self.assertEqual(bledy, [], "znaczniki konfliktu w śledzonych plikach (ścieżka, linie): %s" % bledy)


if __name__ == "__main__":
    unittest.main()
