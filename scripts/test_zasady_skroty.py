"""Testy bramki skrótów zasad: python3 -m unittest discover -s scripts -p 'test_zasady_skroty.py'"""
import io
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import zasady_skroty as zs  # noqa: E402

REPO = zs.REPO


class Repo(unittest.TestCase):
    """Mała kopia repo: zasady.md, bloki, treści, manifest, prompty, decyzje, plik skrótów."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        for p in ("zasady.md", "flota/zadania.yaml", zs.PLIK):
            (self.tmp / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / p, self.tmp / p)
        for d in ("flota/szablony/bloki", "flota/szablony/tresc", "ceo/handoff/prompty"):
            shutil.copytree(REPO / d, self.tmp / d)
        (self.tmp / "decyzje").mkdir()
        (self.tmp / "decyzje/D-20261112-01.md").write_text("# decyzja testowa\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def sprawdz(self):
        return zs.sprawdz(self.tmp)

    def cmd(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                kod = zs.main(list(argv), repo=self.tmp)
            except SystemExit as e:
                kod = e.code if isinstance(e.code, int) else 2
                buf.write(str(e.code))
        return kod, buf.getvalue()

    def test_kopia_zgodna(self):
        self.assertEqual(self.sprawdz(), [])

    def test_zmiana_bloku_bez_decyzji_czerwona(self):
        b = self.tmp / "flota/szablony/bloki/zasady-bezpieczenstwa.md"
        linie = b.read_text().rstrip("\n").split("\n")
        b.write_text("\n".join(linie[:-1]) + "\n")   # ostatnia zasada wycięta (bez literałów – działa też w tłumaczeniu)
        bledy = self.sprawdz()
        self.assertTrue(any("blok:zasady-bezpieczenstwa" in x and "bez decyzji" in x for x in bledy), bledy)

    def test_zmiana_sekcji_a_czerwona_sekcja_b_obojetna(self):
        z = self.tmp / "zasady.md"
        t = z.read_text()
        naglowek = lambda lit: next(l for l in t.splitlines() if l.startswith("## %s." % lit))  # noqa: E731
        z.write_text(t.replace(naglowek("B"), naglowek("B") + "\n\nDopisek w sekcji B.", 1))
        self.assertEqual(self.sprawdz(), [], "sekcja B nie jest chroniona skrótem")
        z.write_text(t.replace(naglowek("A") + "\n", naglowek("A") + "\n\nWyjątek: wolno.\n", 1))
        self.assertTrue(any(x.startswith("zasady.md:A") for x in self.sprawdz()))

    def test_aktualizuj_wymaga_istniejacej_decyzji(self):
        b = self.tmp / "flota/szablony/bloki/zasady-bezpieczenstwa.md"
        b.write_text(b.read_text() + "9. Nowa zasada.\n")
        self.assertEqual(self.cmd("aktualizuj", "--decyzja", "zgoda")[0] != 0, True)
        self.assertNotEqual(self.cmd("aktualizuj", "--decyzja", "D-20261112-07")[0], 0, "decyzji nie ma w decyzje/")
        self.assertTrue(self.sprawdz(), "po odmowie nadal czerwono")
        kod, out = self.cmd("aktualizuj", "--decyzja", "D-20261112-01")
        self.assertEqual(kod, 0, out)
        # prompty muszą zawierać nowy tekst bloku – stare prompty są teraz niezgodne
        self.assertTrue(all("prompt bez pełnego tekstu" in x for x in self.sprawdz()))
        self.assertEqual(zs.wczytaj(self.tmp)["skroty"]["blok:zasady-bezpieczenstwa"]["decyzja"], "D-20261112-01")

    def test_usuniecie_tylko_jawne(self):
        (self.tmp / "flota/szablony/bloki/zasady-bezpieczenstwa.md").unlink()
        self.assertTrue(any("źródło zniknęło" in x for x in self.sprawdz()))
        kod, _ = self.cmd("aktualizuj", "--decyzja", "D-20261112-01")
        self.assertTrue(any("źródło zniknęło" in x for x in self.sprawdz()), "aktualizuj nie usuwa po cichu")
        kod, out = self.cmd("aktualizuj", "--decyzja", "D-20261112-01", "--usun", "blok:zasady-bezpieczenstwa")
        self.assertEqual(kod, 0, out)
        self.assertIn("blok:zasady-bezpieczenstwa", zs.wczytaj(self.tmp)["usuniete"])
        self.assertFalse(any("źródło zniknęło" in x for x in self.sprawdz()))

    def test_usun_istniejacego_zrodla_odmowa(self):
        self.assertNotEqual(self.cmd("aktualizuj", "--decyzja", "D-20261112-01", "--usun", "blok:zasady-bezpieczenstwa")[0], 0)

    def test_nowy_blok_zasad_bez_skrotu(self):
        (self.tmp / "flota/szablony/bloki/zasady-dodatkowe.md").write_text("x\n")
        self.assertTrue(any("blok:zasady-dodatkowe" in x and "bez skrótu" in x for x in self.sprawdz()))

    def test_tresc_bez_bloku_wymaga_wyjatku(self):
        t = self.tmp / "flota/szablony/tresc/limit.md"
        t.write_text(t.read_text().replace(zs.WSTAWKA, ""))
        bledy = self.sprawdz()
        self.assertTrue(any("tresc/limit.md" in x and "brak" in x for x in bledy), bledy)
        d = zs.wczytaj(self.tmp)
        d["wyjatki_tresci"]["limit.md"] = ""
        zs.zapisz(self.tmp, d)
        self.assertTrue(any("wyjątek limit.md: brak powodu" in x for x in self.sprawdz()))
        d["wyjatki_tresci"]["limit.md"] = "zadanie mechaniczne bez dostępu do treści z zewnątrz – test"
        zs.zapisz(self.tmp, d)
        self.assertEqual(self.sprawdz(), [], "wyjątek z powodem zwalnia treść i jej prompt")

    def test_wyjatek_dla_nieistniejacej_tresci(self):
        d = zs.wczytaj(self.tmp)
        d["wyjatki_tresci"]["nie-ma.md"] = "powód dość długi, żeby przejść próg"
        zs.zapisz(self.tmp, d)
        self.assertTrue(any("nieistniejącej" in x for x in self.sprawdz()))

    def test_prompt_bez_bloku(self):
        p = self.tmp / "ceo/handoff/prompty/scalanie.md"
        blok = (self.tmp / "flota/szablony/bloki/zasady-bezpieczenstwa.md").read_text()
        linia = next(l for l in blok.splitlines() if len(l) > 40)
        self.assertIn(linia, p.read_text())
        p.write_text(p.read_text().replace(linia, linia[:20], 1))
        self.assertTrue(any("prompty/scalanie.md" in x for x in self.sprawdz()))

    def test_decyzja_przy_skrocie_musi_istniec(self):
        d = zs.wczytaj(self.tmp)
        d["skroty"]["zasady.md:A"]["decyzja"] = "D-20990101-01"
        zs.zapisz(self.tmp, d)
        self.assertTrue(any("nie istnieje" in x for x in self.sprawdz()))

    def test_brak_pliku_skrotow(self):
        (self.tmp / zs.PLIK).unlink()
        self.assertTrue(self.sprawdz())


class RepoSzablonu(unittest.TestCase):
    def test_repo_zgodne(self):
        self.assertEqual(zs.sprawdz(REPO), [])

    def test_kazda_tresc_ma_blok_albo_wyjatek(self):
        w = zs.wczytaj(REPO)["wyjatki_tresci"]
        for p in sorted((REPO / "flota/szablony/tresc").glob("*.md")):
            with self.subTest(p.name):
                self.assertTrue(zs.WSTAWKA in p.read_text() or p.name in w)

    def test_parser_manifestu(self):
        z = zs.zadania(REPO)
        self.assertGreater(len(z), 5)
        self.assertIn(("flota/szablony/tresc/scalanie.md", "ceo/handoff/prompty/scalanie.md"), z)


if __name__ == "__main__":
    unittest.main()
