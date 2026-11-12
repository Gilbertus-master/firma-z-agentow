"""Adresaci alertów strażnika i rdzeń rejestru alarmów: python3 -m unittest discover moduly/straznik"""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alerty as A  # noqa: E402
import eskalacja as E  # noqa: E402
import kontrole as K  # noqa: E402
import straznik as S  # noqa: E402

TESTDANE = Path(__file__).resolve().parent / "testdane"
T = K.parsuj_czas("2026-11-09T13:20:00+01:00")[0]


def roz(*ids):
    return {"status": K.ROZ, "id": list(ids), "liczby": {}, "opis": "x"}


class Adresaci(unittest.TestCase):
    def setUp(self):
        self.tab = E.tabela({})

    def odb(self, nazwa, w, n=1, podjety=False):
        return E.odbiorcy(nazwa, w, n, self.tab, podjety)

    def test_tabela_domyslna_i_nadpisanie(self):
        self.assertEqual(self.tab["pr"], ("recenzent", 60))
        t = E.tabela({"straznik": {"adresaci": {"pr": "inzynier", "konfiguracja": {"adresat": "pm", "reakcja_min": 30},
                                                 "zlecenia": "Zły Adresat; rm"}}})
        self.assertEqual(t["pr"], ("inzynier", 60))
        self.assertEqual(t["konfiguracja"], ("pm", 30))
        self.assertEqual(t["zlecenia"], E.TABELA["zlecenia"], "niepoprawna nazwa odbiorcy jest ignorowana")

    def test_pr_do_recenzenta_ceo_dopiero_przy_drugim_przypomnieniu(self):
        self.assertEqual(self.odb("pr", roz("produkt#5")), (["recenzent"], "adresat"))
        self.assertEqual(self.odb("pr", roz("produkt#5"), n=2), (["recenzent"], "adresat"))        # 1. przypomnienie
        self.assertEqual(self.odb("pr", roz("produkt#5"), n=3), (["ceo", "recenzent"], "ceo"))      # 2. przypomnienie
        self.assertEqual(self.odb("pr", roz("produkt#5"), n=3, podjety=True), (["recenzent"], "adresat"))

    def test_zlecenie_do_skrzynki_adresata(self):
        w = roz("inzynier.md|2026-11-09|Raport", "pm.md|2026-11-09|Plan")
        self.assertEqual(self.odb("zlecenia", w), (["inzynier", "pm"], "adresat"))

    def test_przebieg_do_agenta_a_stojacy_ceo_do_wlasciciela(self):
        self.assertEqual(self.odb("przebiegi", roz("obsluga", "pm:stan")), (["obsluga", "pm"], "adresat"))
        self.assertEqual(self.odb("przebiegi", roz("ceo")), (["ceo", "wlasciciel"], "wlasciciel"))
        self.assertEqual(self.odb("martwe", roz("ceo", "obsluga")), (["ceo", "obsluga", "wlasciciel"], "wlasciciel"))

    def test_alarm_ceo_po_drugim_przypomnieniu_do_wlasciciela(self):
        self.assertEqual(self.odb("konfiguracja", roz("pm:godzina")), (["ceo"], "adresat"))
        self.assertEqual(self.odb("konfiguracja", roz("pm:godzina"), n=3), (["ceo", "wlasciciel"], "wlasciciel"))
        self.assertEqual(self.odb("zlecenia", roz("ceo.md|2026-11-09|X"), n=3), (["ceo", "wlasciciel"], "wlasciciel"))

    def test_budzet_od_razu_do_wlasciciela(self):
        self.assertEqual(self.odb("budzety", roz("org:100")), (["ceo", "wlasciciel"], "wlasciciel"))

    def test_blad_zrodla_do_ceo(self):
        w = {"status": K.BLAD, "id": ["gh:pr"], "liczby": {}, "opis": "x"}
        self.assertEqual(self.odb("pr", w), (["ceo"], "adresat"))
        self.assertEqual(self.odb("pr", w, n=3), (["ceo", "wlasciciel"], "wlasciciel"))

    def test_adresy_maila_tylko_od_poziomu_ceo(self):
        stare = (A.MAIL_DO, A.MAIL_WLASCICIEL)
        self.addCleanup(lambda: (setattr(A, "MAIL_DO", stare[0]), setattr(A, "MAIL_WLASCICIEL", stare[1])))
        A.MAIL_DO, A.MAIL_WLASCICIEL = "operator@example.com", "wlasciciel@example.com"
        self.assertEqual(A.adresy_maila(["recenzent"], "adresat"), [])
        self.assertEqual(A.adresy_maila(["ceo", "recenzent"], "ceo"), ["operator@example.com"])
        self.assertEqual(A.adresy_maila(["ceo", "wlasciciel"], "wlasciciel"), ["wlasciciel@example.com", "operator@example.com"])
        A.MAIL_DO = ""                                                                  # flota foundera: bez operatora
        self.assertEqual(A.adresy_maila(["ceo", "wlasciciel"], "wlasciciel"), ["wlasciciel@example.com"])
        self.assertEqual(A.wyslij_mail("t", "x", do=[]), A.MAIL_BEZ_ADRESATA)


class Podjete(unittest.TestCase):
    def wpis(self, status="otwarte", odp=""):
        return ("# Zlecenia dla agenta recenzent\n\n## [%s] 2026-11-09 · od: straznik · Pilne (strażnik) · PR-y: 1 PR bez werdyktu\n"
                "Termin: 2026-11-09 15:20\nOdpowiedź:%s\n" % (status, (" " + odp) if odp else ""))

    def test_odpowiedz_albo_w_toku_to_podjety(self):
        self.assertEqual(E.podjete_kontrole({"recenzent.md": self.wpis()}), set())
        self.assertEqual(E.podjete_kontrole({"recenzent.md": self.wpis(odp="biorę, 14:00")}), {"pr"})
        self.assertEqual(E.podjete_kontrole({"recenzent.md": self.wpis(status="w toku · konto A · 2026-11-09 13:30")}), {"pr"})
        self.assertEqual(E.podjete_kontrole({"x.md": self.wpis().replace("od: straznik", "od: pm", 1) + "Odpowiedź: tak\n"}), set())


class Rejestr(unittest.TestCase):
    def setUp(self):
        self.tab = E.tabela({})
        self.w = {"pr": roz("produkt#5")}

    def test_otwarty_termin_i_po_terminie(self):
        r = E.rejestr({}, self.w, {"pr"}, T, self.tab)
        self.assertEqual((r["pr"]["stan"], r["pr"]["odpowiedzialny"], r["pr"]["reakcja_min"]), ("otwarty", "recenzent", 60))
        self.assertEqual(r["pr"]["termin"], K.iso(T + timedelta(minutes=60)))
        self.assertFalse(r["pr"]["po_terminie"])
        r2 = E.rejestr(r, self.w, {"pr"}, T + timedelta(minutes=75), self.tab, poziomy={"pr": "ceo"})
        self.assertEqual(r2["pr"]["od"], K.iso(T), "trwały alarm zachowuje czas otwarcia")
        self.assertTrue(r2["pr"]["po_terminie"])
        self.assertEqual(r2["pr"]["poziom"], "ceo")
        r3 = E.rejestr(r2, self.w, {"pr"}, T + timedelta(minutes=90), self.tab, podjete={"pr"})
        self.assertEqual((r3["pr"]["stan"], r3["pr"]["poziom"], r3["pr"]["po_terminie"]), ("podjety", "ceo", False))

    def test_zamkniecie_i_czas_usuniecia(self):
        r = E.rejestr({}, self.w, {"pr"}, T, self.tab)
        z = E.rejestr(r, {"pr": {"status": K.OK, "id": []}}, set(), T + timedelta(minutes=40), self.tab)
        self.assertEqual((z["pr"]["stan"], z["pr"]["czas_usuniecia_min"]), ("zamkniety", 40))

    def test_powrot_w_30_min_to_to_samo_zdarzenie(self):
        r = E.rejestr({}, self.w, {"pr"}, T, self.tab)
        z = E.rejestr(r, {}, set(), T + timedelta(minutes=40), self.tab)
        wraca = E.rejestr(z, self.w, {"pr"}, T + timedelta(minutes=60), self.tab)
        self.assertEqual((wraca["pr"]["stan"], wraca["pr"]["od"]), ("otwarty", K.iso(T)))
        nowy = E.rejestr(z, self.w, {"pr"}, T + timedelta(minutes=80), self.tab)
        self.assertEqual(nowy["pr"]["od"], K.iso(T + timedelta(minutes=80)))

    def test_zamkniete_znikaja_po_3_dniach(self):
        z = E.rejestr(E.rejestr({}, self.w, {"pr"}, T, self.tab), {}, set(), T + timedelta(minutes=10), self.tab)
        self.assertIn("pr", E.rejestr(z, {}, set(), T + timedelta(days=2), self.tab))
        self.assertNotIn("pr", E.rejestr(z, {}, set(), T + timedelta(days=4), self.tab))


class EskalacjaWPrzebiegu(unittest.TestCase):
    """Te same dane w trzech przebiegach: PR bez werdyktu trafia do recenzenta, a do CEO dopiero przy 2. przypomnieniu."""

    def test_pr_eskaluje_do_ceo_po_drugim_przypomnieniu(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            shutil.copytree(TESTDANE / "repo", repo)
            ceo, rec = repo / "zlecenia" / "ceo.md", repo / "zlecenia" / "recenzent.md"

            def przebieg(czas):
                with redirect_stdout(io.StringIO()):
                    S.main(["--dane", str(TESTDANE), "--repo", str(repo), "--teraz", czas])
                return json.loads((repo / "ceo" / "straznik.json").read_text())

            st = przebieg("2026-11-09T13:20:00+01:00")
            self.assertIn("PR-y", rec.read_text())
            self.assertNotIn("PR-y", ceo.read_text())
            st = przebieg("2026-11-09T15:25:00+01:00")                                  # 1. przypomnienie – nadal recenzent
            pr = [a for a in st["alerty_przebiegu"] if a["kontrola"] == "pr"]
            self.assertEqual([a["adresaci"] for a in pr], [["recenzent"]])
            self.assertNotIn("PR-y", ceo.read_text())
            st = przebieg("2026-11-09T21:30:00+01:00")                                  # 2. przypomnienie – kopia do CEO
            pr = [a for a in st["alerty_przebiegu"] if a["kontrola"] == "pr"]
            self.assertEqual([(a["adresaci"], a["poziom"]) for a in pr], [(["ceo", "recenzent"], "ceo")])
            self.assertIn("Pilne (strażnik) · PR-y", ceo.read_text())
            self.assertEqual(rec.read_text().count("Pilne (strażnik) · PR-y"), 1, "u recenzenta wpis już otwarty – bez dubla")
            self.assertEqual((st["alarmy"]["pr"]["stan"], st["alarmy"]["pr"]["poziom"]), ("otwarty", "ceo"))
            self.assertTrue(st["alarmy"]["pr"]["po_terminie"])


if __name__ == "__main__":
    unittest.main()
