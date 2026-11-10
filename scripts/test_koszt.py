"""Testy pomiaru kosztu przebiegu: python3 -m unittest discover -s scripts -p 'test_koszt.py'"""
import datetime as dt
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import koszt as K  # noqa: E402

REPO = K.REPO


def linia(req, model, we=0, wy=0, cr=0, c5=0, c1=0):
    return json.dumps({"type": "assistant", "requestId": req, "message": {"model": model, "usage": {
        "input_tokens": we, "output_tokens": wy, "cache_read_input_tokens": cr, "cache_creation_input_tokens": c5 + c1,
        "cache_creation": {"ephemeral_5m_input_tokens": c5, "ephemeral_1h_input_tokens": c1}}}})


class Koszt(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.d)
        (self.d / "flota").mkdir()
        shutil.copy(REPO / "flota" / "ceny-modeli.yaml", self.d / "flota" / "ceny-modeli.yaml")
        (self.d / "org.yaml").write_text('organizacja:\n  strefa: "Europe/Warsaw"\nruntime:\n  rozliczenie: "team"\n'
                                         '  cena_planu_usd_miesiac: 250\n  nadwyzka_usd_miesiac: 100\n')
        self.t = self.d / "sesja-1.jsonl"
        # ta sama odpowiedź w trzech liniach (bloki treści) liczona raz; podagent w <sesja>/subagents/
        self.t.write_text("\n".join([linia("r1", "claude-opus-5-5", we=1_000_000, wy=100_000)] * 3
                                    + [linia("r2", "claude-opus-5-5", cr=1_000_000, c1=500_000), '{"type":"user"}', "zepsuta linia"]) + "\n")
        sub = self.d / "sesja-1" / "subagents"; sub.mkdir(parents=True)
        (sub / "agent-x.jsonl").write_text(linia("r3", "claude-haiku-5-5", we=1_000_000, wy=1_000_000) + "\n")

    def test_ceny_z_pliku(self):
        c = K.ceny(REPO)
        self.assertIn("claude-opus-5-5", c["modele"])
        self.assertEqual((c["m5"], c["m1h"]), (1.25, 2.0))
        org = (REPO / "org.yaml").read_text()
        for model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
            self.assertIn(model, c["modele"])
        self.assertIn(c["domyslny"], c["modele"])
        self.assertTrue(all(m in c["modele"] for m in __import__("re").findall(r'(?m)^ {4}\w+: "(claude-[a-z0-9-]+)"', org)),
                        "każdy model z org.yaml → runtime.modele musi mieć cenę w flota/ceny-modeli.yaml")

    def test_zuzycie_deduplikacja_i_podagenci(self):
        z = K.zuzycie(self.t)
        self.assertEqual(z["claude-opus-5-5"]["zapytania"], 2)
        self.assertEqual(z["claude-opus-5-5"]["wejscie"], 1_000_000)
        self.assertEqual(z["claude-opus-5-5"]["cache_zapis_1h"], 500_000)
        self.assertEqual(z["claude-haiku-5-5"]["wyjscie"], 1_000_000)

    def test_koszt_wg_cennika(self):
        per, suma, obce = K.koszt(K.zuzycie(self.t), K.ceny(self.d))
        # opus: 1M×4 + 0,1M×20 + 1M×0,20 + 0,5M×4×2 = 4 + 2 + 0,2 + 4 = 10,2; haiku: 0,1 + 0,5 = 0,6
        self.assertAlmostEqual(per["claude-opus-5-5"], 10.2, places=3)
        self.assertAlmostEqual(per["claude-haiku-5-5"], 0.6, places=3)
        self.assertAlmostEqual(suma, 10.8, places=3)
        self.assertEqual(obce, [])
        per, _, obce = K.koszt({"claude-nieznany-9": dict.fromkeys(K.POLA, 0) | {"wejscie": 1_000_000}}, K.ceny(self.d))
        self.assertEqual(obce, ["claude-nieznany-9"])

    def test_zapis_idempotentny_i_raport(self):
        teraz = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
        K.zapisz_linie(self.d, "ceo", "s1", self.t, "przebieg", teraz)
        K.zapisz_linie(self.d, "ceo", "s1", self.t, "hook", teraz)       # ta sama sesja → zastąpiona
        K.zapisz_linie(self.d, "pm", "s2", self.t, "przebieg", teraz)
        plik = self.d / "przebiegi" / "ceo" / "koszty-2026-11-10.jsonl"
        linie = plik.read_text().splitlines()
        self.assertEqual(len(linie), 1)
        self.assertTrue(linie[0].rstrip().endswith('"koszt_usd": 10.8}'))   # przebieg.sh czyta ostatnie pole
        self.assertEqual(json.loads(linie[0])["zrodlo"], "hook")
        r = K.raport(self.d, 14, teraz)
        self.assertEqual((r["razem_usd"], r["dni_z_danymi"]), (21.6, 1))
        self.assertAlmostEqual(r["projekcja_usd_miesiac"], 648.0, places=1)
        self.assertEqual(list(r["agenci"]), ["ceo", "pm"])
        self.assertIsNone(K.zapisz_linie(self.d, "Zła/Nazwa", "s3", self.t, "przebieg", teraz))

    def test_hooki_sesja_i_zapisz(self):
        wej = json.dumps({"session_id": "s9", "transcript_path": str(self.t)})
        with mock.patch("sys.stdin", io.StringIO(wej)):
            self.assertEqual(K.main(["sesja", "--hook", "--repo", str(self.d)]), 0)
        self.assertEqual(json.loads((self.d / K.BIEZACA).read_text())["sesja"], "s9")
        (self.d / ".agent-rola").write_text("recenzent\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(K.main(["zapisz", "--repo", str(self.d)]), 0)   # agent z .agent-rola, sesja z pliku bieżącego
        self.assertIn("KOSZT: recenzent", buf.getvalue())
        self.assertTrue(list((self.d / "przebiegi" / "recenzent").glob("koszty-*.jsonl")))
        with mock.patch("sys.stdin", io.StringIO("to nie JSON")):
            self.assertEqual(K.main(["zapisz", "--hook", "--repo", str(self.d / "brak")]), 0)   # hook nigdy nie blokuje


if __name__ == "__main__":
    unittest.main()
