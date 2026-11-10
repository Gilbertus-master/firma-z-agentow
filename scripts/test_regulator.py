"""Testy regulatora tempa: python3 -m unittest scripts/test_regulator.py (bez sieci, repo tymczasowe)."""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import regulator as R  # noqa: E402

RESET = "2026-11-16T08:00:00Z"  # okno od 2026-11-09 08:00 UTC


def h(godz):
    return R.iso(R.czas(RESET) - R.dt.timedelta(days=7) + R.dt.timedelta(hours=godz))


class Tempo(unittest.TestCase):
    def t(self, procent, godz, okno=60.0):
        return R.tempo(procent, R.czas(RESET), R.czas(h(godz)), okno)

    def test_cel_liniowy_i_tryby(self):
        self.assertEqual(self.t(50, 30)["cel_teraz"], 50.0)
        self.assertEqual(self.t(100, 90)["cel_teraz"], 100.0)
        self.assertEqual(self.t(10, 30)["tryb"], "przyspiesz")   # −40 pp
        self.assertEqual(self.t(52, 30)["tryb"], "normalnie")    # +2 pp
        self.assertEqual(self.t(60, 30)["tryb"], "zwolnij")      # +10 pp
        self.assertEqual(self.t(0, 10)["do_konca_h"], None)
        self.assertEqual(self.t(50, 30, okno=120)["cel_teraz"], 25.0)

    def test_5h_hamuje(self):
        r5 = R.czas("2026-11-10T13:00:00Z"); teraz = R.czas("2026-11-10T09:00:00Z")  # 1 h okna
        self.assertEqual(R.tempo5h(50, r5, teraz)["tryb_5h"], "zwolnij")    # cel 20, +30 pp
        self.assertEqual(R.tempo5h(25, r5, teraz)["tryb_5h"], "normalnie")
        self.assertEqual(R.tempo5h(95, r5, R.czas("2026-11-10T08:10:00Z"))["tryb_5h"], "zwolnij")


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        (self.d / "org.yaml").write_text('organizacja:\n  prefiks: "tst"\n  strefa: "Europe/Warsaw"\nruntime:\n  konto: "A"\n  okno_celu_h: 60\n')
        (self.d / "zlecenia").mkdir()
        (self.d / "zlecenia" / "ceo.md").write_text("# Zlecenia ceo\n")
        self.plik = self.d / ".tst-limit-A.json"

    def run_(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kod = R.main(["--repo", str(self.d), "--plik", str(self.plik)] + list(args))
        return kod, buf.getvalue()

    def test_przyspiesz_wpis_raz_na_2h(self):
        kod, out = self.run_("--konto", "A", "--procent", "10", "--reset", RESET, "--teraz", h(30))
        self.assertEqual(kod, 0); self.assertIn("PILNE: dopisane", out)
        self.assertIn("Pilne: przyspiesz", (self.d / "zlecenia" / "ceo.md").read_text())
        kod, out = self.run_("--konto", "A", "--procent", "11", "--reset", RESET, "--teraz", h(31))
        self.assertNotIn("PILNE", out)   # odstęp 2 h
        kod, out = self.run_("--konto", "A", "--procent", "12", "--reset", RESET, "--teraz", h(33))
        self.assertIn("PILNE", out)
        d = json.loads(self.plik.read_text())
        self.assertEqual((d["konto"], d["tryb"]), ("A", "przyspiesz"))

    def test_wyczerpany_bez_nadwyzki_tylko_p1(self):
        kod, out = self.run_("--konto", "A", "--procent", "98", "--reset", RESET, "--teraz", h(55))
        self.assertIn("LIMIT: wyczerpany", out); self.assertIn("tylko P1", out)
        self.assertIn("limit konta floty wyczerpany", (self.d / "zlecenia" / "ceo.md").read_text())
        kod, out = self.run_("--konto", "A", "--procent", "99", "--reset", RESET, "--teraz", h(57))
        self.assertIn("zgłoszony w tym oknie", out)
        self.assertNotIn("HANDOFF", out)   # bez rotacji kont

    def test_wyczerpany_z_nadwyzka(self):
        (self.d / "org.yaml").write_text('organizacja:\n  prefiks: "tst"\nruntime:\n  konto: "A"\n  nadwyzka_usd_miesiac: 500\n')
        kod, out = self.run_("--konto", "A", "--procent", "98", "--reset", RESET, "--teraz", h(55))
        self.assertIn("płatna nadwyżka", out)

    def test_5h_wygrywa(self):
        kod, out = self.run_("--konto", "A", "--procent", "10", "--reset", RESET, "--teraz", h(30),
                             "--procent5h", "95", "--reset5h", "2026-11-10T16:00:00Z")
        d = json.loads(self.plik.read_text())
        self.assertEqual(d["tryb"], "zwolnij"); self.assertNotIn("PILNE", out)


if __name__ == "__main__":
    unittest.main()
