"""Test archiwum zleceń: python3 -m unittest discover flota"""
import pathlib, subprocess, sys, tempfile, unittest

SKRYPT = pathlib.Path(__file__).resolve().parent / "archiwizuj_zlecenia.py"
WEJ = """# Zlecenia dla: test

Najnowsze na dole.

## [zrobione] 2026-11-06 · od: ceo · A
treść A
## [otwarte] 2026-11-07 · od: ceo · B
treść B
## [informacja] 2026-11-07 · od: pm · C
Odpowiedź: przeczytane
## [informacja] 2026-11-08 · od: pm · D
bez reakcji
## [odłożone] 2026-11-08 · od: ceo · E
## [zamknięte – duplikat] 2026-11-08 · od: ceo · F
"""


class Archiwum(unittest.TestCase):
    def test_przenosi_zamkniete_bez_zmiany_tresci(self):
        with tempfile.TemporaryDirectory() as d:
            z = pathlib.Path(d) / "zlecenia"; z.mkdir(); (z / "test.md").write_text(WEJ)
            subprocess.run([sys.executable, str(SKRYPT), d, "zapisz", "2026-11"], check=True, capture_output=True)
            otw = (z / "test.md").read_text(); arch = (z / "archiwum/2026-11/test.md").read_text()
            self.assertEqual([l.split("]")[0][4:] for l in otw.splitlines() if l.startswith("## ")], ["otwarte", "informacja", "odłożone"])
            self.assertIn("## [zrobione] 2026-11-06 · od: ceo · A\ntreść A\n## [informacja] 2026-11-07 · od: pm · C\nOdpowiedź: przeczytane\n## [zamknięte", arch)
            self.assertIn("archiwum/2026-11/test.md", otw)
            # idempotentnie: drugi przebieg niczego nie dubluje
            subprocess.run([sys.executable, str(SKRYPT), d, "zapisz", "2026-11"], check=True, capture_output=True)
            self.assertEqual(arch, (z / "archiwum/2026-11/test.md").read_text())
            self.assertEqual(otw.count("Archiwum zamkniętych"), 1)


if __name__ == "__main__":
    unittest.main()
