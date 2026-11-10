"""Testy strażnika floty: python3 -m unittest discover moduly/straznik   (bez sieci; dane fikcyjne)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

TU = Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
sys.dont_write_bytecode = True
for _zmienna in [x for x in os.environ if x.startswith("STRAZNIK_")]:
    del os.environ[_zmienna]  # testy nie zależą od konfiguracji strażnika w środowisku uruchamiającego

import alerty as A  # noqa: E402
import kontrole as K  # noqa: E402
import straznik as S  # noqa: E402
import zrodla as Z  # noqa: E402

PRZEBIEG_SH = TU.parent.parent / "scripts" / "przebieg.sh"
TESTDANE = TU / "testdane"


def t(s):
    return K.parsuj_czas(s)[0]


def odstepy(*wiersze):
    """(agent, odstep, poczatek[, dni, godziny, od]) – jak kolumny koordynacja-odstepy.tsv."""
    wynik = []
    for w in wiersze:
        a, o, p, dni, godz, od = (tuple(w) + ("*", "*", None))[:6]
        wynik.append({"agent": a, "odstep": o, "poczatek": K.hhmm_na_min(p), "dni": Z.parsuj_dni(dni),
                      "godziny": None if godz == "*" else sorted(K.hhmm_na_min(g) for g in godz.split(",")),
                      "od": t(od) if od else None})
    return wynik


class ZgodnoscZPrzebiegSh(unittest.TestCase):
    """Numer okienka = scripts/przebieg.sh okienko <agent> (PRZEBIEG_TERAZ) – także przy zmianie czasu."""

    @unittest.skipUnless(PRZEBIEG_SH.exists(), "brak scripts/przebieg.sh")
    def test_okienka_jak_przebieg_sh(self):
        # plik z 6 kolumnami (przebieg.sh czyta 1–3) + wiersze 3-kolumnowe (kolumny 4–6 opcjonalne)
        tsv = TU / "testdane" / "repo" / "koordynacja-odstepy.tsv"
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        sciezka = str(d / "koordynacja-odstepy.tsv")
        Path(sciezka).write_text(tsv.read_text() + "inwestorzy\t1440\t12:00\tpt\t12:30\t2026-11-07 13:11\nmarketing\t180\t23:30\n")
        wiersze = {w["agent"]: w for w in Z.czytaj_odstepy(d)}
        self.assertEqual(len(wiersze), 5)
        chwile = ["2026-11-09T07:34:00+01:00", "2026-11-09T00:14:59+01:00", "2026-11-08T23:59:00+01:00",
                  "2026-03-29T01:59:00+01:00", "2026-03-29T03:01:00+02:00", "2026-10-25T02:30:00+02:00",
                  "2026-10-25T02:30:00+01:00", "2026-07-06T12:00:00+02:00", "2026-11-09T01:15:00+01:00"]
        for agent, w in wiersze.items():
            for c in chwile:
                teraz = t(c)
                env = dict(os.environ, PRZEBIEG_ODSTEPY=sciezka, PRZEBIEG_TERAZ=str(int(teraz.timestamp())),
                           PRZEBIEG_STREFA="Europe/Warsaw")
                out = subprocess.run(["bash", str(PRZEBIEG_SH), "okienko", agent], capture_output=True, text=True, env=env)
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertEqual(int(out.stdout.strip()), K.okienko(teraz, w["odstep"], w["poczatek"]), "%s %s" % (agent, c))

    @unittest.skipUnless((TU.parent.parent / "koordynacja-odstepy.tsv").exists(), "brak tsv repo")
    def test_tsv_repo_kompletny(self):
        """Każdy agent w koordynacja-odstepy.tsv ma 6 kolumn, datę „od”, a godziny z listy wpadają w różne okienka."""
        wiersze = Z.czytaj_odstepy(TU.parent.parent)
        for w in wiersze:
            self.assertIsNotNone(w["od"], w["agent"])
            h = K.harmonogram_z_wiersza(w)
            if h and w["godziny"]:
                dzien = t("2026-11-09T00:00:00+01:00")
                okna = [K.okienko(dzien + timedelta(minutes=g), w["odstep"], w["poczatek"]) for g in h["godziny"]]
                self.assertEqual(len(okna), len(set(okna)), w["agent"])


class Przebiegi(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def dane(self, tagi, stany=None, wiersze=(("ceo", 180, "01:00"),)):
        return {"odstepy": odstepy(*wiersze), "tagi": tagi,
                "stany": stany if stany is not None else {"ceo": {"ostatni_przebieg": "2026-11-09 10:40"}}}

    def nr(self, chwila, o=180, p="01:00"):
        return K.okienko(t(chwila), o, K.hhmm_na_min(p))

    def test_ok(self):
        w = K.kontrola_przebiegi(self.dane({"ceo": [self.nr("2026-11-09T10:40:00+01:00")]}), self.T)
        self.assertEqual(w["status"], K.OK, w)

    def test_brak_tagu_ostatniego_okienka(self):
        w = K.kontrola_przebiegi(self.dane({"ceo": [self.nr("2026-11-09T07:40:00+01:00")]}), self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo"]))

    def test_mniej_niz_10_min_po_koncu_okienka_sprawdza_poprzednie(self):
        # 13:05 – okienko 10:00–13:00 skończyło się 5 min temu → sprawdzane 7:00–10:00
        w = K.kontrola_przebiegi(self.dane({"ceo": [self.nr("2026-11-09T07:40:00+01:00")]}), t("2026-11-09T13:05:00+01:00"))
        self.assertEqual(w["status"], K.OK, w)

    def test_nieaktualny_stan_osobne_id(self):
        d = self.dane({"ceo": [self.nr("2026-11-09T10:40:00+01:00")]}, {"ceo": {"ostatni_przebieg": "2026-11-09T06:00:00+01:00"}})
        w = K.kontrola_przebiegi(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo:stan"]))

    def test_formaty_dat_stanu(self):
        for s, oczek in (("2026-11-09", K.OK), ("2026-11-09T11:25:00Z", K.OK), ("2026-11-09T10:40+01:00", K.OK),
                         ("2026-11-08 07:20", K.ROZ), ("wczoraj", K.OK), (None, K.OK)):
            d = self.dane({"ceo": [self.nr("2026-11-09T10:40:00+01:00")]}, {"ceo": {"ostatni_przebieg": s}})
            self.assertEqual(K.kontrola_przebiegi(d, self.T)["status"], oczek, s)

    def test_harmonogram_noc_obslugi(self):
        tag = self.nr("2026-11-08T20:58:00+01:00", 120, "08:15")
        d = self.dane({"obsluga": [tag]}, {}, (("obsluga", 120, "08:15", "*", "8:45,10:45,12:45,14:45,16:45,18:45,20:45"),))
        self.assertEqual(K.kontrola_przebiegi(d, t("2026-11-09T03:00:00+01:00"))["status"], K.OK)
        d["tagi"] = {"obsluga": [tag - 1]}
        self.assertEqual(K.kontrola_przebiegi(d, t("2026-11-09T03:00:00+01:00"))["id"], ["obsluga"])

    def test_okienka_30_min_spozniony_start(self):
        tag = self.nr("2026-11-09T11:20:00+01:00", 30, "01:15")  # przebieg 10:45 spóźniony o 35 min
        d = self.dane({"recenzent": [tag - 20, tag]}, {}, (("recenzent", 30, "01:15", "*", "1:45,4:45,7:45,10:45,13:45,16:45,19:45,22:45"),))
        self.assertEqual(K.kontrola_przebiegi(d, self.T)["status"], K.OK)
        d["tagi"] = {"recenzent": [tag - 20, tag + 5]}
        self.assertEqual(K.kontrola_przebiegi(d, self.T)["status"], K.ROZ)

    def test_harmonogram_tygodniowy(self):
        tag = self.nr("2026-11-06T12:31:00+01:00", 1440, "12:00")
        d = self.dane({"inwestorzy": [tag]}, {"inwestorzy": {"ostatni_przebieg": "2026-11-06"}}, (("inwestorzy", 1440, "12:00", "pt", "12:30"),))
        self.assertEqual(K.kontrola_przebiegi(d, self.T)["status"], K.OK)
        d["tagi"] = {"inwestorzy": [tag - 7]}
        self.assertEqual(K.kontrola_przebiegi(d, self.T)["id"], ["inwestorzy"])

    def test_od_daty_zmiany_harmonogramu(self):
        # inwestorzy: piątek 12:30 od 7.11 13:11 – brak przebiegu 6.11 nie jest rozbieżnością (także bez żadnego tagu)
        wiersz = ("inwestorzy", 1440, "12:00", "pt", "12:30", "2026-11-07 13:11")
        stan = {"inwestorzy": {"ostatni_przebieg": "2026-11-07"}}
        w = K.kontrola_przebiegi(self.dane({}, stan, (wiersz,)), self.T)
        self.assertEqual(w["status"], K.OK, w)
        self.assertTrue(any("brak oczekiwanego przebiegu od 2026-11-07 13:11" in u for u in w["uwagi"]))
        # okienko z piątkiem 13.11 (13.11 12:00 – 14.11 12:00) zakończone ≥ 10 min – już rozbieżność; wcześniej jeszcze nie
        self.assertEqual(K.kontrola_przebiegi(self.dane({}, stan, (wiersz,)), t("2026-11-14T12:05:00+01:00"))["status"], K.OK)
        w = K.kontrola_przebiegi(self.dane({}, stan, (wiersz,)), t("2026-11-14T12:15:00+01:00"))
        self.assertEqual(w["id"], ["inwestorzy"])
        # bez kolumny od – stare zachowanie (6.11 oczekiwany)
        self.assertEqual(K.kontrola_przebiegi(self.dane({}, stan, (wiersz[:5],)), self.T)["id"], ["inwestorzy"])

    def test_od_pierwszego_tagu_gdy_pozniejszy(self):
        # ceo: harmonogram od 1.11, pierwszy tag dopiero w okienku 13:00 – okienko 10:00 nie jest oczekiwane
        wiersz = ("ceo", 180, "01:00", "*", "*", "2026-11-01 00:00")
        teraz = t("2026-11-09T16:20:00+01:00")
        d = self.dane({"ceo": [self.nr("2026-11-09T13:40:00+01:00")]}, None, (wiersz,))
        self.assertEqual(K.kontrola_przebiegi(d, teraz)["status"], K.OK)
        d = self.dane({"ceo": [self.nr("2026-11-09T07:40:00+01:00")]}, None, (wiersz,))  # pierwszy tag wcześniej – 13:00 brak
        self.assertEqual(K.kontrola_przebiegi(d, teraz)["id"], ["ceo"])
        # od późniejsze niż pierwszy tag: harmonogram od 9.11 14:00 → okienko 13:00 nieoczekiwane
        d = self.dane({"ceo": [self.nr("2026-11-09T07:40:00+01:00")]}, None, (wiersz[:5] + ("2026-11-09 14:00",),))
        self.assertEqual(K.kontrola_przebiegi(d, teraz)["status"], K.OK)

    def test_blad_zrodla(self):
        w = K.kontrola_przebiegi(self.dane({"blad": "sieć"}), self.T)
        self.assertEqual(w["status"], K.BLAD)


# Jak testdane/repo/org.yaml: prefiks zadań „firma”, repo organizacji firma-agenci, repo produktu: produkt i strona.
POMIN_TYTUL_TEST = r"^\[wstrzymane"
ORG_TEST = {"organizacja": {"prefiks": "firma", "strefa": "Europe/Warsaw"}, "repo": {"github": "OWNER/firma-agenci",
            "produkt": ["OWNER/produkt", "OWNER/strona"]}, "runtime": {"glowny": "desktop-scheduled", "konta": ["B"]},
            "straznik": {"kontrole": list(Z.KONTROLE_WSZYSTKIE), "pomin_tytul": POMIN_TYTUL_TEST}}


class Org(unittest.TestCase):
    def test_czytaj_i_konfiguruj(self):
        org = Z.czytaj_org(TESTDANE / "repo")
        self.assertEqual(org["repo"]["produkt"], ["OWNER/produkt", "OWNER/strona"])
        self.assertEqual(org["straznik"]["pomin_tytul"], POMIN_TYTUL_TEST)
        self.assertEqual(org["ludzie"]["operator"]["kontakt_firmowy"], "operator@example.com")
        self.assertEqual(org["runtime"]["konta"], ["B"])
        Z.konfiguruj(org)
        self.assertEqual(Z.REPO_PR, ("produkt", "strona", "firma-agenci"))
        self.assertEqual(Z.REPO_PRODUKT, ("produkt", "strona"))
        self.assertEqual((Z.PREFIKS, Z.KONTA, K.REPO_BEZ_PREFIKSU), ("firma", ("B",), "produkt"))
        self.assertEqual((K.POMIN_TYTUL.pattern, K.POMIN_TYTUL_BLAD), (POMIN_TYTUL_TEST, None))
        self.assertEqual(Z.KONTROLE_AKTYWNE, Z.KONTROLE_WSZYSTKIE)

    def test_bez_org_i_rdzen(self):
        self.assertEqual(Z.czytaj_org(TESTDANE), {})
        Z.konfiguruj({"organizacja": {"prefiks": "x"}, "runtime": {"konta": ["A", "C"]}})
        self.assertEqual((Z.PREFIKS, Z.KONTA, Z.KONTROLE_AKTYWNE), ("x", ("A", "C"), Z.KONTROLE_RDZEN))
        Z.konfiguruj(ORG_TEST)

    def test_pominieta_konfiguracja_bez_katalogu_zadan(self):
        Z.konfiguruj({**ORG_TEST, "runtime": {"glowny": "claude-routines", "konta": ["A"]}})
        try:
            with tempfile.TemporaryDirectory() as d:
                shutil.copytree(TESTDANE / "repo", Path(d) / "repo")
                dane = Z.zloz(Path(d) / "repo", Path(d) / "brak-zadan", Z.zewnetrzne_z_pliku(TESTDANE))
                w = K.kontrola_konfiguracja(dane["konfiguracja"], t("2026-11-09T13:20:00+01:00"))
                self.assertEqual(w["status"], K.OK)
                self.assertIn("pominięta", w["opis"])
        finally:
            Z.konfiguruj(ORG_TEST)

    def test_uruchom_tylko_aktywne(self):
        w = K.uruchom_wszystkie({}, t("2026-11-09T13:20:00+01:00"), ("zlecenia",))
        self.assertEqual(list(w), ["zlecenia"])


class PrzebiegiNieutworzeni(unittest.TestCase):
    def test_role_bez_agent_md_pominiete(self):
        T = t("2026-11-09T13:20:00+01:00")
        d = {"odstepy": odstepy(("ceo", 60, "07:00"), ("marketing", 180, "23:30")), "tagi": {}, "stany": {},
             "utworzeni": ["ceo"]}
        w = K.kontrola_przebiegi(d, T)
        self.assertEqual((w["status"], w["id"], w["liczby"]["nieutworzeni"]), (K.ROZ, ["ceo"], 1))
        self.assertTrue(any("nieutworzonych" in u for u in w["uwagi"]))
        d["utworzeni"] = []
        self.assertEqual(K.kontrola_przebiegi(d, T)["status"], K.OK)


class BudzetyIMartwe(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def test_budzety(self):
        d = {"miesiac": "2026-11", "org_limit": 100.0, "agenci": {"ceo": {"wydano": 50.0, "limit": 50.0}, "pm": {"wydano": 20.0, "limit": 25.0},
                                                                   "x": {"wydano": 5.0, "limit": None}}}
        w = K.kontrola_budzety(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo:100"]))
        self.assertTrue(any(u.startswith("pm:") for u in w["uwagi"]))
        d["agenci"]["pm"]["wydano"] = 60.0  # razem 115 ≥ 100 → org:100
        self.assertIn("org:100", K.kontrola_budzety(d, self.T)["id"])
        self.assertEqual(K.kontrola_budzety({"miesiac": "2026-11", "org_limit": None, "agenci": {}}, self.T)["status"], K.OK)
        d["rozliczenie"] = "team"   # team: udział agenta pilnowany, cała flota bez HALT (nadwyżkę ogranicza limit u Anthropic)
        w = K.kontrola_budzety(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo:100", "pm:100"]))
        self.assertTrue(any(u.startswith("flota:") for u in w["uwagi"]))

    def test_martwe(self):
        d = {"k": 3, "wyniki": {"ceo": ["OK", "BŁĄD", "BŁĄD", "BŁĄD"], "pm": ["BŁĄD", "BŁĄD", "OK"], "obsluga": ["BŁĄD", "BŁĄD", "BŁĄD"]},
             "dead_letter": ["obsluga"]}
        w = K.kontrola_martwe(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo"]))
        self.assertTrue(any("obsluga" in u for u in w["uwagi"]))

    def test_zrodla_budzety_i_martwe_z_plikow(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "org.yaml").write_text('mandat:\n  budzet_floty_usd_miesiac: 10\n')
            (repo / "flota").mkdir(); (repo / "flota" / "zadania.yaml").write_text("budzet_usd_miesiac: 4\nzadania:\n- agent: ceo\n  katalog: ceo\n  budzet_usd_miesiac: 6\n- agent: pm\n  katalog: pm\n")
            for a in ("ceo", "pm"):
                (repo / "przebiegi" / a).mkdir(parents=True)
            (repo / "przebiegi" / "ceo" / "koszty-2026-11-09.jsonl").write_text('{"koszt_usd": 5.5}\n{"koszt_usd": 1}\n')
            (repo / "przebiegi" / "pm" / "2026-11-09.jsonl").write_text('{"wynik":"BŁĄD","koszt_usd":1.0}\n{"wynik":"BŁĄD"}\n{"wynik":"BŁĄD"}\n')
            b = Z.czytaj_budzety(repo, "2026-11")
            self.assertEqual((b["org_limit"], b["agenci"]["ceo"], b["agenci"]["pm"]), (10.0, {"wydano": 6.5, "limit": 6.0}, {"wydano": 1.0, "limit": 4.0}))
            m = Z.czytaj_martwe(repo)
            self.assertEqual(m["wyniki"]["pm"], ["BŁĄD", "BŁĄD", "BŁĄD"])
            self.assertEqual(K.kontrola_martwe(m, self.T)["id"], ["pm"])
            self.assertEqual(K.kontrola_budzety(b, self.T)["id"], ["ceo:100"])
            self.assertEqual(b["rozliczenie"], "api")   # brak pola w org.yaml = api (budżety obowiązują)
            (repo / "org.yaml").write_text('mandat:\n  budzet_floty_usd_miesiac: 10\nruntime:\n  rozliczenie: "team"\n')
            b = Z.czytaj_budzety(repo, "2026-11")
            self.assertEqual((b["rozliczenie"], K.kontrola_budzety(b, self.T)["id"]), ("team", ["ceo:100"]))
            (repo / "flota" / "budzety.tsv").write_text("# rozliczenie\tteam\n# flota_usd_miesiac\t31350.00\n"
                                                        "katalog\twaga_usd_miesiac\tmiesiac_usd\tdzien_usd\nceo\t6\t2441.60\t244.16\n")
            b = Z.czytaj_budzety(repo, "2026-11")
            self.assertEqual((b["org_limit"], b["agenci"]["ceo"]["limit"], b["agenci"]["pm"]["limit"]), (31350.0, 2441.6, 4.0))
            w = K.kontrola_budzety(b, self.T)
            self.assertEqual(w["id"], [])          # 6.5 z 2441.60 USD-ekw. – w normie; pm bez kosztów


class Pr(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    @classmethod
    def setUpClass(cls):
        Z.konfiguruj(ORG_TEST)

    def pr(self, nr, head, utw="2026-11-09T08:00:00Z", head_data="2026-11-09T08:00:00Z", **kw):
        d = {"number": nr, "title": kw.pop("title", "Przykład"), "isDraft": kw.pop("isDraft", False), "headRefOid": head,
             "createdAt": utw, "headDate": head_data}
        d.update(kw)
        return d

    def test_ok_werdykt_skrocony_sha(self):
        d = {"prs": {"produkt": [self.pr(1, "a" * 40)], "strona": [self.pr(5, "c" * 40)]},
             "recenzje": {"1": {"sha": "aaaaaaa"}, "strona#5": {"sha": "c" * 40}}}
        w = K.kontrola_pr(d, self.T)
        self.assertEqual((w["status"], w["liczby"]["z_werdyktem"]), (K.OK, 2))

    def test_repo_organizacji(self):
        self.assertIn("firma-agenci", Z.REPO_PR)
        d = {"prs": {"firma-agenci": [self.pr(1, "a" * 40), self.pr(2, "b" * 40)]},
             "recenzje": {"firma-agenci#1": {"sha": "aaaaaaa"}, "strona#2": {"sha": "bbbbbbb"}}}
        w = K.kontrola_pr(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["firma-agenci#2"]))

    def test_brak_werdyktu_ponad_60_min(self):
        d = {"prs": {"produkt": [self.pr(2, "b" * 40)], "strona": [self.pr(5, "c" * 40)]},
             "recenzje": {"2": {"sha": "0000000"}, "5": {"sha": "ccccccc"}}}  # „5” to produkt#5, nie strona#5
        w = K.kontrola_pr(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["produkt#2", "strona#5"]))

    def test_wiek_od_pozniejszej_daty_i_pominiete(self):
        # pominięte: szkic (#4) i tytuł pasujący do straznik.pomin_tytul z ORG_TEST (#6)
        d = {"prs": {"produkt": [self.pr(3, "b" * 40, head_data="2026-11-09T11:50:00Z"),
                                 self.pr(4, "d" * 40, isDraft=True), self.pr(6, "e" * 40, title="[wstrzymane] pakiet")]},
             "recenzje": {}}
        w = K.kontrola_pr(d, self.T)  # head 12:50 lokalnie → 30 min
        self.assertEqual((w["status"], w["liczby"]["pominiete"], w["liczby"]["bez_werdyktu"]), (K.OK, 2, 1))

    def test_blad_jednego_repo(self):
        w = K.kontrola_pr({"prs": {"produkt": {"blad": "gh"}, "strona": []}, "recenzje": {}}, self.T)
        self.assertEqual(w["status"], K.BLAD)
        w = K.kontrola_pr({"prs": {"produkt": {"blad": "gh"}, "strona": [self.pr(1, "f" * 40)]}, "recenzje": {}}, self.T)
        self.assertEqual(w["status"], K.ROZ)


class Testflight(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")
    REJ = "| 2026-11-09 | AXtest01 | … |\n| 2026-11-09 | AY-z_123 | … |"

    def test_ok(self):
        d = {"zrzuty": [{"id": "AXtest01-dlugie", "data": "x"}, {"id": "AY-z_1234567", "data": "y"}], "awarie": [], "rejestr": self.REJ}
        self.assertEqual(K.kontrola_testflight(d, self.T)["status"], K.OK)

    def test_brakujace_id(self):
        d = {"zrzuty": [{"id": "AXtest01x", "data": "a"}, {"id": "AZnowe00", "data": "b"}], "awarie": [{"id": "AWawaria1", "data": "c"}],
             "rejestr": self.REJ}
        w = K.kontrola_testflight(d, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["AZnowe00", "awaria:AWawaria"]))
        self.assertEqual(w["liczby"]["brak_w_rejestrze_awarie"], 1)

    def test_blad_asc(self):
        d = {"zrzuty": {"blad": "ASC HTTP 401"}, "awarie": {"blad": "ASC HTTP 401"}, "rejestr": self.REJ}
        self.assertEqual(K.kontrola_testflight(d, self.T)["status"], K.BLAD)


class Automaty(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def dane(self, **kw):
        d = {"cron_failed": [], "net5xx": 0, "build_stan": {"bledy": 0},
             "fly": {"conclusion": "success", "createdAt": "2026-11-09T07:00:00Z", "status": "completed"},
             "pages": {"produkt": {"status": "built", "created_at": "x"}, "strona": None}}
        d.update(kw)
        return d

    def test_ok(self):
        w = K.kontrola_automaty(self.dane(), self.T)
        self.assertEqual(w["status"], K.OK)
        self.assertTrue(any("strona" in u for u in w["uwagi"]))

    def test_rozbieznosci(self):
        przypadki = {
            "cron:produkt-przyklad": dict(cron_failed=[{"jobname": "produkt-przyklad", "n": 2}]),
            "net:5xx": dict(net5xx=4),
            "build_stan": dict(build_stan={"bledy": 3}),
            "fly:2026-11-09T07:00:00Z": dict(fly={"conclusion": "failure", "createdAt": "2026-11-09T07:00:00Z"}),
            "pages:produkt:x": dict(pages={"produkt": {"status": "errored", "created_at": "x"}}),
        }
        for ident, kw in przypadki.items():
            w = K.kontrola_automaty(self.dane(**kw), self.T)
            self.assertEqual((w["status"], w["id"]), (K.ROZ, [ident]), ident)
        self.assertEqual(K.kontrola_automaty(self.dane(build_stan={"bledy": 2}), self.T)["status"], K.OK)

    def test_blad_tokenu(self):
        b = {"blad": "brak tokenu w pęku"}
        w = K.kontrola_automaty(self.dane(cron_failed=b, net5xx=b, build_stan=b), self.T)
        self.assertEqual(w["status"], K.BLAD)


class Zlecenia(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def test_parser_terminow(self):
        p = K.najwczesniejszy_termin
        self.assertEqual(p("Termin: 2026-11-09 18:00"), t("2026-11-09T18:00:00+01:00"))
        self.assertEqual(p("Termin: 2026-11-09"), t("2026-11-09T23:59:00+01:00"))
        self.assertEqual(p("Termin: błędy – 2026-11-08 16:00; reszta – 2026-11-09 18:00"), t("2026-11-08T16:00:00+01:00"))
        self.assertEqual(p("Termin: 2026-11-06 20:45 (12 h – decyzja 6.11; wcześniej: 2026-11-02)"), t("2026-11-06T20:45:00+01:00"))
        self.assertEqual(p("Termin: 2026-11-06 22:00 → przesunięty przez CEO 7.11 na 2026-11-09 12:00"), t("2026-11-09T12:00:00+01:00"))
        self.assertIsNone(p("Termin: stałe"))
        self.assertIsNone(p("Termin: 12 h od Twojego najbliższego przebiegu"))

    def blok(self, status="[otwarte]", termin="2026-11-09 12:00", odp="Odpowiedź:", od="pm", dalej=""):
        return "# Zlecenia\n\n## %s 2026-11-09 · od: %s · Tytuł przykładowy\nTreść.\nTermin: %s\n%s\n%s\n" % (status, od, termin, odp, dalej)

    def test_ok(self):
        for tekst in (self.blok(odp="Odpowiedź: 2026-11-09 – zrobione"), self.blok(termin="2026-11-10 09:00"),
                      self.blok(status="[zrobione]"), self.blok(dalej="- dopisek w kolejnej linii"),
                      self.blok(od="straznik")):
            self.assertEqual(K.kontrola_zlecenia({"pliki": {"ceo.md": tekst}}, self.T)["status"], K.OK, tekst)

    def test_po_terminie_bez_odpowiedzi(self):
        w = K.kontrola_zlecenia({"pliki": {"ceo.md": self.blok(status="[w toku · konto B · 2026-11-09 09:00]")}}, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["ceo.md|2026-11-09|Tytuł przykładowy"]))


class Konfiguracja(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def skill(self, opis, konto=True):
        return "---\nname: x\ndescription: %s\n---\n\n%s\n" % (opis, "Konto: B" if konto else "")

    def test_ok(self):
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(("ceo", 180, "01:00"), ("pm", 120, "06:15", "*", "6:45,8:45,11:45,14:45,17:45,20:45"),
                                ("inwestorzy", 1440, "12:00", "pt", "12:30", "2026-11-07 13:11")),
             "zadania": {"ceo": self.skill("Co 3 h (1:30, 4:30 … 22:30), 7 dni"),
                         "inwestorzy": self.skill("Piątek 12:30 (od 7.11): przykład"),
                         "pm": self.skill("6:45 dziennie: backlog; 8:45–20:45 co 3 h: dyżur")}}
        w = K.kontrola_konfiguracja(d, self.T)
        self.assertEqual(w["status"], K.OK, w)

    def test_dwa_konta_i_pominieta(self):
        d = {"konta": ["A", "B"], "prefiks": "org", "odstepy": odstepy(("ceo", 180, "01:00")),
             "zadania": {"ceo": {"A": self.skill("Co 3 h (1:30, 4:30)").replace("Konto: B", "Konto: A"), "B": None}}}
        w = K.kontrola_konfiguracja(d, self.T)
        self.assertEqual(w["id"], ["ceo:brak-zadania:b"])
        self.assertIn("org-ceo-b", w["opis"])
        self.assertEqual(K.kontrola_konfiguracja({"pominieta": "runtime chmurowy"}, self.T)["status"], K.OK)

    def test_rozbieznosci(self):
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(("ceo", 180, "01:00"), ("prawny", 180, "00:00"), ("finansowy", 180, "01:10"), ("sprzedaz", 180, "01:30")),
             "zadania": {"ceo": self.skill("Co 3 h (1:30, 4:30)", konto=False), "prawny": self.skill("Co 3 h (0:45, 3:45)"),
                         "finansowy": self.skill("Co 2 h (1:40, 3:40)"), "sprzedaz": None}}
        w = K.kontrola_konfiguracja(d, self.T)
        self.assertEqual(w["id"], ["ceo:konto", "finansowy:godziny", "prawny:godzina", "prawny:godziny", "sprzedaz:brak-zadania"])

    def test_nieparsowalny_opis_to_uwaga(self):
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(("obsluga", 120, "08:15", "*", "8:45,10:45,12:45,14:45,16:45,18:45,20:45")),
             "zadania": {"obsluga": self.skill("Co 2 godziny 8–20: support@")}}
        w = K.kontrola_konfiguracja(d, self.T)
        self.assertEqual(w["status"], K.OK)
        self.assertTrue(w["uwagi"])

    def test_godziny_z_kolumny_tsv(self):
        # recenzent: okienko 30 min, ale godziny w tsv co 3 h – opis „co 3 h (1:45…” zgodny; „co 2 h” – rozbieżność
        wiersz = ("recenzent", 30, "01:15", "*", "1:45,4:45,7:45,10:45,13:45,16:45,19:45,22:45")
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(wiersz), "zadania": {"recenzent": self.skill("Na żądanie + co 3 h (1:45, 4:45…22:45)")}}
        self.assertEqual(K.kontrola_konfiguracja(d, self.T)["status"], K.OK)
        d["zadania"]["recenzent"] = self.skill("co 2 h (2:45, 4:45)")
        self.assertEqual(K.kontrola_konfiguracja(d, self.T)["id"], ["recenzent:godzina", "recenzent:godziny"])

    def test_odstep_okienka_nie_jest_porownywany(self):
        # odstęp w tsv to okienko blokady (recenzent 30 min, PM 120 min), nie rytm – zgodne godziny = OK
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(("recenzent", 30, "01:15", "*", "1:45,4:45,7:45,10:45,13:45,16:45,19:45,22:45"),
                                ("pm", 120, "06:15", "*", "6:45,8:45,11:45,14:45,17:45,20:45")),
             "zadania": {"recenzent": self.skill("co 3 h (1:45, 4:45…22:45) jako siatka"),
                         "pm": self.skill("6:45 dziennie; 8:45–20:45 co 3 h: dyżur")}}
        self.assertEqual(K.kontrola_konfiguracja(d, self.T)["status"], K.OK)

    def test_pelny_przeglad_w_siatce_ok_poza_siatka_rozbieznosc(self):
        d = {"konta": ["B"], "prefiks": "firma", "odstepy": odstepy(("aplikacje", 180, "00:50")),
             "zadania": {"aplikacje": self.skill("Co 3 h (1:20, 4:20 … 22:20); pełny przegląd w środę 13:20")}}
        self.assertEqual(K.kontrola_konfiguracja(d, self.T)["status"], K.OK)
        d["zadania"]["aplikacje"] = self.skill("Co 3 h (1:20, 4:20 … 22:20); pełny przegląd w środę 13:00")
        self.assertEqual(K.kontrola_konfiguracja(d, self.T)["id"], ["aplikacje:godziny"])


class Alerty(unittest.TestCase):
    T = t("2026-11-09T13:20:00+01:00")

    def w(self, status, ids=(), zrodla=()):
        return {"status": status, "liczby": {"n": len(ids)}, "id": list(ids), "opis": "opis",
                "uwagi": ["źródło niedostępne – " + z for z in zrodla], "zrodla_bledy": list(zrodla)}

    def seria(self, kroki):
        """[(minuty, {kontrola: wynik})] -> liczba alertów w każdym kroku (stan przenoszony jak w straznik.py)."""
        stan, wynik = {}, []
        for minuty, wyniki in kroki:
            czesc, zd, do = A.przetworz(stan, wyniki, self.T + timedelta(minutes=minuty))
            stan = dict(czesc, kontrole=wyniki)
            wynik.append(len(do))
        return wynik

    def test_trwala_rozbieznosc_przypomnienia_2_6_24_h(self):
        r = {"pr": self.w(K.ROZ, ["produkt#1"])}
        minuty = [0, 15, 119, 120, 479, 480, 1919, 1920, 3359, 3360]
        self.assertEqual(self.seria([(m, r) for m in minuty]), [1, 0, 0, 1, 0, 1, 0, 1, 0, 1])

    def test_stary_format_stanu_alertow(self):
        r = {"pr": self.w(K.ROZ, ["produkt#1"])}
        stan = {"kontrole": r, "alerty": {"pr:produkt#1": K.iso(self.T)}}  # starszy format stanu (sam czas)
        self.assertEqual(A.przetworz(stan, r, self.T + timedelta(minutes=60))[2], [])
        czesc, _, do = A.przetworz(stan, r, self.T + timedelta(minutes=120))
        self.assertEqual((len(do), czesc["alerty"]["pr:produkt#1"]["n"]), (1, 2))

    def test_zmiana_zbioru_id_od_razu(self):
        a, b = {"pr": self.w(K.ROZ, ["produkt#1"])}, {"pr": self.w(K.ROZ, ["produkt#1", "produkt#2"])}
        # A → B (nowe ID) → A (znów inny zbiór) – za każdym razem od razu, mimo alertu dla A 30 min wcześniej
        self.assertEqual(self.seria([(0, a), (15, b), (30, a), (45, a)]), [1, 1, 1, 0])
        # rozbieżność wraca po OK – nowy alert
        ok = {"pr": self.w(K.OK)}
        self.assertEqual(self.seria([(0, a), (15, ok), (30, a)]), [1, 0, 1])

    def test_zdarzenia_tylko_przy_zmianie(self):
        stan = {"kontrole": {"pr": self.w(K.OK)}, "alerty": {}}
        self.assertEqual(A.przetworz(stan, {"pr": self.w(K.OK)}, self.T)[1:], ([], []))
        self.assertEqual(A.przetworz({}, {"pr": self.w(K.OK)}, self.T)[1], [])
        stan = {"kontrole": {"pr": self.w(K.ROZ, ["produkt#1"])}, "alerty": {}}
        _, zd, do = A.przetworz(stan, {"pr": self.w(K.OK)}, self.T)
        self.assertEqual(len(zd), 1)
        self.assertIn("ROZBIEŻNOŚĆ → OK", zd[0])
        self.assertEqual(do, [])
        r = {"pr": self.w(K.ROZ, ["produkt#1"])}
        stan = dict(A.przetworz({}, r, self.T)[0], kontrole=r)
        self.assertEqual(A.przetworz(stan, r, self.T + timedelta(minutes=15))[1], [])

    def test_blad_zrodla_po_2_kolejnych(self):
        b = {"pr": self.w(K.BLAD, zrodla=["gh:pr:produkt"])}
        ok = {"pr": self.w(K.OK)}
        self.assertEqual(self.seria([(0, b), (15, b), (30, b), (45, b)]), [0, 1, 0, 0])
        # przerwa (OK) zeruje licznik
        self.assertEqual(self.seria([(0, b), (15, ok), (30, b), (45, ok)]), [0, 0, 0, 0])
        czesc, zd, do = A.przetworz({}, b, self.T)
        self.assertEqual(czesc["bledy_zrodel"], {"gh:pr:produkt": 1})
        self.assertIn("alert po 2 kolejnych", zd[-1])
        stan = dict(czesc, kontrole=b)
        _, _, do = A.przetworz(stan, b, self.T + timedelta(minutes=15))
        self.assertEqual(do[0][2], "pr:BLAD_ZRODLA:gh:pr:produkt")
        self.assertEqual(do[0][1]["id"], ["gh:pr:produkt"])
        # trwały błąd – przypomnienia jak przy rozbieżności (pierwsze 2 h po alercie z 15. min)
        self.assertEqual(self.seria([(0, b), (15, b), (134, b), (135, b)]), [0, 1, 0, 1])

    def test_blad_dwoch_zrodel_naraz_od_razu(self):
        b = {"pr": self.w(K.BLAD, zrodla=["gh:pr:produkt"]), "testflight": self.w(K.BLAD, zrodla=["asc:zrzuty"])}
        self.assertEqual(self.seria([(0, b)]), [2])
        b = {"automaty": self.w(K.BLAD, zrodla=["supabase:cron", "supabase:net"])}
        self.assertEqual(self.seria([(0, b)]), [1])

    WPIS = ("# Zlecenia\n\n## [zrobione] 2026-11-08 · od: straznik · Pilne (strażnik) · Przebiegi: bez przebiegu 1, nieaktualny stan 1\n"
            "Strażnik floty: opis.\nLiczby: agenci 16, bez_przebiegu 1. ID: inwestorzy, sprzedaz:stan.\n"
            "Stan: `ceo/straznik.json`. Klucz strażnika: `2c7a1e160a`.\nTermin: 2026-11-08 14:49\n"
            "Odpowiedź: 2026-11-08 13:55 (CEO) – sprzedaz:stan → zlecenie; inwestorzy – fałszywy alarm. %s\n\n"
            "## [otwarte] 2026-11-08 · od: pm · Inny wpis\nOdpowiedź: Wycisz do: 2026-12-31\n")

    def test_czytaj_wyciszenia_format_ceo(self):
        w = A.czytaj_wyciszenia(self.WPIS % "Wycisz do: 2026-11-13 (inwestorzy).")
        self.assertEqual(w, [{"kontrola": "przebiegi", "ids": ["inwestorzy"], "do": t("2026-11-13T23:59:59+01:00")}])
        w = A.czytaj_wyciszenia(self.WPIS % "Wycisz do: 2026-11-10 08:00")
        self.assertEqual(w[0]["ids"], ["inwestorzy", "sprzedaz:stan"])
        self.assertEqual(w[0]["do"], t("2026-11-10T08:00:00+01:00"))
        self.assertEqual(A.czytaj_wyciszenia(self.WPIS % ""), [])  # wpis pm z „Wycisz do:” nie liczy się

    def test_wyciszenie_id_do_daty(self):
        wycisz = A.czytaj_wyciszenia(self.WPIS % "Wycisz do: 2026-11-13 (inwestorzy).")
        r = {"przebiegi": self.w(K.ROZ, ["inwestorzy", "sprzedaz:stan"])}
        _, _, do = A.przetworz({}, r, self.T, wycisz)
        self.assertEqual(do[0][1]["id"], ["sprzedaz:stan"])  # alert tylko o niewyciszonym ID
        self.assertEqual(do[0][2], "przebiegi:sprzedaz:stan")
        tylko = {"przebiegi": self.w(K.ROZ, ["inwestorzy"])}
        _, zd, do = A.przetworz({}, tylko, self.T, wycisz)
        self.assertEqual(do, [])
        self.assertTrue(any("wyciszone" in z for z in zd))
        _, _, do = A.przetworz({}, tylko, t("2026-11-14T00:00:30+01:00"), wycisz)  # po dacie – alert
        self.assertEqual(len(do), 1)
        # sprzedaz:stan znika, inwestorzy wyciszeni – bez nowego alertu
        czesc, _, _ = A.przetworz({}, r, self.T, wycisz)
        _, _, do = A.przetworz(dict(czesc, kontrole=r), tylko, self.T + timedelta(minutes=15), wycisz)
        self.assertEqual(do, [])

    def test_cisza_nocna(self):
        for godz, oczek in (("22:59", False), ("23:00", True), ("03:00", True), ("06:59", True), ("07:00", False)):
            self.assertEqual(A.cisza_nocna(t("2026-11-09T%s:00+01:00" % godz)), oczek, godz)
        self.assertTrue(A.cisza_nocna(t("2026-07-06T21:30:00Z")))  # 23:30 CEST

    def test_build_stan_i_codemagic_od_razu(self):
        for z in ("supabase:build_stan", "codemagic:build"):
            self.assertEqual(self.seria([(0, {"automaty": self.w(K.BLAD, zrodla=[z])})]), [1], z)

    def test_rozbieznosc_z_bledem_czesci_zrodel(self):
        r = {"pr": self.w(K.ROZ, ["strona#1"], zrodla=["gh:pr:produkt"])}
        # rozbieżność od razu; błąd źródła (repo produkt) dopiero w drugim przebiegu (osobny alert)
        self.assertEqual(self.seria([(0, r), (15, r), (30, r)]), [1, 1, 0])

    def test_wpis_ceo_na_poczatku_listy_i_bez_duplikatu(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ceo.md"
            p.write_text("# Zlecenia dla: agent ceo\n\nNajnowsze na dole.\n\n## [otwarte] 2026-11-09 · od: pm · Stare\nTermin: x\nOdpowiedź:\n")
            w = self.w(K.ROZ, ["produkt#1"])
            k = A.klucz("pr", w)
            self.assertTrue(A.wstaw_wpis_ceo(p, A.wpis_ceo("pr", w, k, self.T), k))
            self.assertFalse(A.wstaw_wpis_ceo(p, A.wpis_ceo("pr", w, k, self.T), k))
            tekst = p.read_text()
            naglowki = [l for l in tekst.splitlines() if l.startswith("## ")]
            self.assertEqual(naglowki[0], "## [otwarte] 2026-11-09 · od: straznik · Pilne (strażnik) · PR-y: 1 PR bez werdyktu > 60 min")
            self.assertIn("Termin: 2026-11-09 15:20", tekst)
            self.assertEqual(len(naglowki), 2)


class ZrodlaOdpornosc(unittest.TestCase):
    def test_maskowanie_jwt_i_sekretow(self):
        jwt = "eyJhbGciOiJFUzI1NiIsImtpZCI6IlgifQ.eyJpc3MiOiJ4In0.c2lnbmF0dXJh"

        def zle():
            raise RuntimeError("ASC odrzucił Bearer %s oraz sbp_tajny" % jwt)
        b = Z.bezpiecznie(zle, maska=["sbp_tajny"])["blad"]
        self.assertNotIn("eyJ", b)
        self.assertNotIn("sbp_tajny", b)
        self.assertEqual(Z.maskuj("x eyJabcd y"), "x *** y")

    def test_ponowienie_przy_timeoucie(self):
        import socket
        proby = []

        def f():
            proby.append(1)
            if len(proby) == 1:
                raise socket.timeout("timed out")
            return "ok"
        self.assertEqual((Z.z_ponowieniem(f), len(proby)), ("ok", 2))

        def g():
            proby.append(1)
            raise ValueError("inny błąd")
        proby.clear()
        with self.assertRaises(ValueError):
            Z.z_ponowieniem(g)
        self.assertEqual(len(proby), 1)

    def test_uruchom_dwie_proby(self):
        stare, wywolania = Z.subprocess.run, []

        def run(*a, **kw):
            wywolania.append(1)
            raise subprocess.TimeoutExpired(a[0], kw.get("timeout"))
        Z.subprocess.run = run
        self.addCleanup(setattr, Z.subprocess, "run", stare)
        with self.assertRaises(Z.BladZrodla) as e:
            Z.uruchom(["gh", "pr", "list"], timeout=1)
        self.assertEqual(len(wywolania), 2)
        self.assertIn("2 próby", str(e.exception))


class ReadmeZgodnyZTsv(unittest.TestCase):
    """Tabela agentów w README.md (kolumna „Kiedy”) = harmonogram z koordynacja-odstepy.tsv (jedyne źródło)."""

    RE_DZIEN = {"poniedziałek": "pn", "wtorek": "wt", "środa": "sr", "czwartek": "cz", "piątek": "pt", "sobota": "so", "niedziela": "nd"}

    def z_readme(self, kiedy):
        """-> (dni, {(godz, min|None)})"""
        s = re.sub(r"\((pn|wt|śr|czw|pt|sob|nd)( \d{1,2}:\d\d)?\)", "", kiedy)
        dni = {K.DNI[v] for k, v in self.RE_DZIEN.items() if k in s} or set(range(7))
        czasy = set()
        for m in re.finditer(r"co (\d+) h :(\d\d) \((\d+)–(\d+)\)", s):
            czasy |= {(g, int(m.group(2))) for g in range(int(m.group(3)), int(m.group(4)) + 1, int(m.group(1)))}
        s = re.sub(r"co (\d+) h :(\d\d) \((\d+)–(\d+)\)", "", s)
        for m in re.finditer(r"co (\d+) h (\d{1,2}):(\d\d)–(\d{1,2}):(\d\d)", s):
            czasy |= {(g, int(m.group(3))) for g in range(int(m.group(2)), int(m.group(4)) + 1, int(m.group(1)))}
        s = re.sub(r"co (\d+) h (\d{1,2}):(\d\d)–(\d{1,2}):(\d\d)", "", s)
        for m in re.finditer(r"co (\d+) h (\d{1,2})–(\d{1,2})\b", s):
            czasy |= {(g, None) for g in range(int(m.group(2)), int(m.group(3)) + 1, int(m.group(1)))}
        s = re.sub(r"co (\d+) h (\d{1,2})–(\d{1,2})\b", "", s)
        czasy |= {(int(m.group(1)), int(m.group(2))) for m in re.finditer(r"(\d{1,2}):(\d\d)", s)}
        return dni, czasy

    def z_tsv(self, w):
        h = K.harmonogram_z_wiersza(w) or {"dni": set(range(7)), "godziny": sorted(
            {(w["poczatek"] + 30 + i * w["odstep"]) % 1440 for i in range(max(1, 1440 // w["odstep"]))})}
        return h["dni"], {(g // 60, g % 60) for g in h["godziny"]}

    @unittest.skip("w szablonie README nie ma tabeli harmonogramu – źródłem jest koordynacja-odstepy.tsv i flota/test_generuj.py")
    def test_readme_zgodny_z_tsv(self):
        readme = (TU.parent.parent / "README.md").read_text(encoding="utf-8")
        kiedy = {}
        for l in readme.splitlines():
            k = l.split("|")
            if len(k) > 5:
                m = re.match(r"\s*`([a-z-]+)/`", k[2])
                if m:
                    kiedy[m.group(1)] = k[4].strip()
        wiersze = Z.czytaj_odstepy(TU.parent.parent)
        self.assertEqual(len(wiersze), 21)
        for w in wiersze:
            self.assertIn(w["agent"], kiedy, w["agent"])
            dni_r, czasy_r = self.z_readme(kiedy[w["agent"]])
            dni_t, czasy_t = self.z_tsv(w)
            self.assertEqual(dni_r, dni_t, w["agent"])
            if all(m is None for _, m in czasy_r):  # README podaje tylko godziny (obsługa „co 2 h 8–20”)
                czasy_t = {(g, None) for g, _ in czasy_t}
            self.assertEqual(czasy_r, czasy_t, "%s: README %s" % (w["agent"], kiedy[w["agent"]]))


class Calosc(unittest.TestCase):
    """Przebieg na danych przykładowych: --sucho nic nie zapisuje; zwykły przebieg w kopii repo zapisuje stan, zdarzenia, wpis."""

    def test_sucho_i_przebieg(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            shutil.copytree(TESTDANE / "repo", repo)
            przed = sorted(str(p) for p in repo.rglob("*"))
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                S.main(["--dane", str(TESTDANE), "--repo", str(repo), "--sucho"])
            wynik = json.loads(buf.getvalue())
            self.assertEqual(sorted(str(p) for p in repo.rglob("*")), przed)
            self.assertEqual({n: w["status"] for n, w in wynik["kontrole"].items()},
                             {"przebiegi": K.ROZ, "pr": K.ROZ, "testflight": K.ROZ, "automaty": K.ROZ, "zlecenia": K.ROZ, "konfiguracja": K.OK,
                              "budzety": K.OK, "martwe": K.OK})
            with redirect_stdout(io.StringIO()):
                S.main(["--dane", str(TESTDANE), "--repo", str(repo)])
                S.main(["--dane", str(TESTDANE), "--repo", str(repo), "--teraz", "2026-11-09T13:35:00+01:00"])
            stan = json.loads((repo / "ceo" / "straznik.json").read_text())
            self.assertEqual(set(stan), {"czas", "czas_przebiegu_s", "kontrole", "alerty", "bledy_zrodel", "alert_zrodel",
                                         "aktywne_id", "wyciszenia", "ostatni_commit_zdarzen", "mail", "alerty_przebiegu", "uwagi"})
            self.assertEqual(len(stan["alerty"]), 5)
            self.assertEqual(stan["alerty_przebiegu"], [])  # drugi przebieg po 15 min – bez nowych alertów
            zd = (repo / "ceo" / "straznik-zdarzenia.md").read_text()
            self.assertEqual(zd.count("· alert ·"), 5)
            self.assertEqual(zd.count("brak stanu → ROZBIEŻNOŚĆ"), 5)
            ceo = (repo / "zlecenia" / "ceo.md").read_text()
            self.assertEqual(ceo.count("od: straznik · Pilne (strażnik)"), 5)
            self.assertLess(ceo.index("od: straznik"), ceo.index("od: pm"))


class GitIZdarzeniaCoGodzine(unittest.TestCase):
    """Prawdziwy przebieg (z git) na gołym repo tymczasowym; sieć, mail i powiadomienie podmienione."""

    def git(self, *a, cwd=None):
        return subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True, check=True).stdout

    def test_commit_alertu_od_razu_zdarzen_co_godzine(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.git("init", "-q", "--bare", str(d / "origin.git"))
            self.git("clone", "-q", str(d / "origin.git"), str(d / "klon"))
            klon = d / "klon"
            for k, v in (("user.email", "test@example.com"), ("user.name", "test")):
                self.git("config", k, v, cwd=klon)
            shutil.copytree(TESTDANE / "repo", klon, dirs_exist_ok=True)
            (klon / ".gitignore").write_text("ceo/straznik.json\n")
            self.git("add", "-A", cwd=klon)
            self.git("commit", "-q", "-m", "start", cwd=klon)
            self.git("push", "-q", "origin", "HEAD", cwd=klon)
            zewn = Z.zewnetrzne_z_pliku(TESTDANE)
            stare = (Z.pobierz_zewnetrzne, A.powiadom, A.wyslij_mail)
            Z.pobierz_zewnetrzne = lambda repo: zewn
            A.powiadom = lambda tekst: "powiadomienie (test)"
            A.wyslij_mail = lambda temat, tresc: A.MAIL_POMINIETY
            self.addCleanup(lambda: (setattr(Z, "pobierz_zewnetrzne", stare[0]), setattr(A, "powiadom", stare[1]),
                                     setattr(A, "wyslij_mail", stare[2])))
            import io
            from contextlib import redirect_stdout

            def przebieg(czas):
                with redirect_stdout(io.StringIO()):
                    S.main(["--repo", str(klon), "--zadania", str(TESTDANE / "zadania"), "--teraz", czas])
                return self.git("log", "--format=%s", "HEAD", cwd=d / "origin.git").splitlines()

            log = przebieg("2026-11-09T13:20:00+01:00")
            self.assertTrue(log[0].startswith("straznik: alert"), log)
            self.assertEqual(self.git("status", "--porcelain", cwd=klon), "")  # straznik.json w .gitignore
            stan = json.loads((klon / "ceo" / "straznik.json").read_text())
            self.assertEqual(stan["mail"], A.MAIL_POMINIETY)
            self.assertIn(A.MAIL_POMINIETY, (klon / "ceo" / "straznik-zdarzenia.md").read_text())
            # 13:50: PR-y wracają do OK → zdarzenie, ale bez commita (ostatni 30 min temu)
            zewn["prs"] = {"produkt": [], "strona": []}
            self.assertEqual(len(przebieg("2026-11-09T13:50:00+01:00")), len(log))
            self.assertIn("ceo/straznik-zdarzenia.md", self.git("status", "--porcelain", cwd=klon))
            # 14:25: minęła godzina → commit zdarzeń
            log2 = przebieg("2026-11-09T14:25:00+01:00")
            self.assertEqual(log2[0], "straznik: zdarzenia 2026-11-09 14:25")
            self.assertEqual(self.git("status", "--porcelain", cwd=klon), "")


class KlonWymagaUwagi(unittest.TestCase):
    """Konflikt przy pull w klonie strażnika: merge --abort, kontrole na migawce origin/main, alert „klon”, bez commitów;
    w nocy bez powiadomienia macOS."""

    def git(self, *a, cwd=None):
        return subprocess.run(["git"] + list(a), cwd=cwd, capture_output=True, text=True, check=True).stdout

    def klon(self, d, nazwa):
        self.git("clone", "-q", str(d / "origin.git"), str(d / nazwa))
        for k, v in (("user.email", "test@example.com"), ("user.name", nazwa)):
            self.git("config", k, v, cwd=d / nazwa)
        return d / nazwa

    def test_konflikt_pull(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.git("init", "-q", "--bare", str(d / "origin.git"))
            klon = self.klon(d, "klon")
            shutil.copytree(TESTDANE / "repo", klon, dirs_exist_ok=True)
            (klon / ".gitignore").write_text("ceo/straznik.json\n")
            self.git("add", "-A", cwd=klon)
            self.git("commit", "-q", "-m", "start", cwd=klon)
            self.git("push", "-q", "origin", "HEAD", cwd=klon)
            inny = self.klon(d, "inny")
            # inny autor: zmienia 1. linię ceo.md i dopisuje zlecenie po terminie w architekt.md
            p = inny / "zlecenia" / "ceo.md"
            p.write_text("# Zlecenia dla: agent ceo (zmiana innego autora)\n" + p.read_text().split("\n", 1)[1])
            a = inny / "zlecenia" / "architekt.md"
            a.write_text(a.read_text() + "\n## [otwarte] 2026-11-09 · od: pm · Tylko na origin\nTermin: 2026-11-09 08:00\nOdpowiedź:\n")
            self.git("commit", "-q", "-am", "inny", cwd=inny)
            self.git("push", "-q", "origin", "HEAD", cwd=inny)
            # klon strażnika: lokalny, niewypchnięty commit w tej samej linii
            p = klon / "zlecenia" / "ceo.md"
            p.write_text("# Zlecenia dla: agent ceo (lokalnie)\n" + p.read_text().split("\n", 1)[1])
            self.git("commit", "-q", "-am", "lokalny", cwd=klon)
            head = self.git("rev-parse", "HEAD", cwd=klon)
            origin_przed = self.git("rev-parse", "HEAD", cwd=d / "origin.git")

            zewn = Z.zewnetrzne_z_pliku(TESTDANE)
            powiadomienia = []
            stare = (Z.pobierz_zewnetrzne, A.powiadom, A.wyslij_mail)
            Z.pobierz_zewnetrzne = lambda repo: zewn
            A.powiadom = lambda tekst: powiadomienia.append(tekst) or "powiadomienie (test)"
            A.wyslij_mail = lambda temat, tresc: A.MAIL_POMINIETY
            self.addCleanup(lambda: (setattr(Z, "pobierz_zewnetrzne", stare[0]), setattr(A, "powiadom", stare[1]),
                                     setattr(A, "wyslij_mail", stare[2])))
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()):
                S.main(["--repo", str(klon), "--zadania", str(TESTDANE / "zadania"), "--teraz", "2026-11-09T23:40:00+01:00"])

            self.assertNotEqual(subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=klon).returncode, 0)
            self.assertEqual(self.git("rev-parse", "HEAD", cwd=klon), head)  # lokalny commit nietknięty
            # klon bez pusha; wpis Pilne trafia na origin przez tymczasowy worktree obok klonu
            self.assertNotEqual(self.git("rev-parse", "HEAD", cwd=d / "origin.git"), origin_przed)
            self.assertEqual(self.git("rev-parse", "HEAD~1", cwd=d / "origin.git"), origin_przed)
            ceo_origin = self.git("show", "HEAD:zlecenia/ceo.md", cwd=d / "origin.git")
            self.assertIn("od: straznik · Pilne (strażnik) · Klon strażnika", ceo_origin)
            self.assertIn("(zmiana innego autora)", ceo_origin)
            self.assertEqual(len(self.git("worktree", "list", cwd=klon).splitlines()), 1)
            self.assertFalse(list(Path(tempfile.gettempdir()).glob("straznik-wpis-*")))
            stan = json.loads((klon / "ceo" / "straznik.json").read_text())
            self.assertEqual(stan["kontrole"]["klon"]["status"], K.ROZ)
            self.assertIn("konflikt", stan["kontrole"]["klon"]["opis"])
            self.assertIn("architekt.md|2026-11-09|Tylko na origin", stan["kontrole"]["zlecenia"]["id"])  # migawka origin/main
            self.assertIn("klon", [x["kontrola"] for x in stan["alerty_przebiegu"]])
            zd = (klon / "ceo" / "straznik-zdarzenia.md").read_text()
            self.assertIn("wpis w zlecenia/ceo.md przez worktree obok klonu", zd)
            self.assertIn("powiadomienie pominięte (cisza nocna 23–7)", zd)
            self.assertEqual(powiadomienia, [])
            self.assertNotIn("od: straznik", (klon / "zlecenia" / "ceo.md").read_text())
            self.assertFalse(list(Path(tempfile.gettempdir()).glob("straznik-migawka-*")))
            self.assertTrue(any("obok zablokowanego klonu" in u for u in stan["uwagi"]), stan["uwagi"])

    def test_dwoch_pisarzy_zdarzen_nie_blokuje_klonu(self):
        """Inny pisarz (np. agent CEO) dopisał linię do ceo/straznik-zdarzenia.md w origin, a klon ma niezacommitowane
        zdarzenia – sam pull by odmówił. Commit przed pull + merge=union (.gitattributes): obie linie zostają, klon OK, push."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.git("init", "-q", "--bare", str(d / "origin.git"))
            klon = self.klon(d, "klon")
            shutil.copytree(TESTDANE / "repo", klon, dirs_exist_ok=True)
            (klon / ".gitignore").write_text("ceo/straznik.json\n")
            shutil.copy(Path(__file__).resolve().parents[2] / ".gitattributes", klon / ".gitattributes")
            zd = klon / "ceo" / "straznik-zdarzenia.md"
            zd.parent.mkdir(parents=True, exist_ok=True)
            zd.write_text(S.NAGLOWEK_ZDARZEN + "- 2026-11-09 10:00 · start\n")
            self.git("add", "-A", cwd=klon)
            self.git("commit", "-q", "-m", "start", cwd=klon)
            self.git("push", "-q", "origin", "HEAD", cwd=klon)
            inny = self.klon(d, "inny")
            z = inny / "ceo" / "straznik-zdarzenia.md"
            z.write_text(z.read_text() + "- 2026-11-09 10:05 · CEO (dopisek innego pisarza)\n")
            self.git("commit", "-q", "-am", "inny", cwd=inny)
            self.git("push", "-q", "origin", "HEAD", cwd=inny)
            zd.write_text(zd.read_text() + "- 2026-11-09 10:10 · zdarzenie strażnika niezacommitowane\n")

            stan, opis = S.aktualizuj_klon(klon)
            self.assertEqual((stan, opis), ("ok", ""))
            self.assertEqual(self.git("status", "--porcelain", cwd=klon), "")
            wynik = self.git("show", "HEAD:ceo/straznik-zdarzenia.md", cwd=d / "origin.git")
            self.assertIn("dopisek innego pisarza", wynik)
            self.assertIn("zdarzenie strażnika niezacommitowane", wynik)


def srodowisko(**zmienne):
    """Środowisko procesu bez zmiennych STRAZNIK_* poza podanymi (nazwy bez przedrostka STRAZNIK_)."""
    czyste = {k: v for k, v in os.environ.items() if not k.startswith("STRAZNIK_")}
    czyste.update({"STRAZNIK_" + k: v for k, v in zmienne.items()})
    return mock.patch.dict(os.environ, czyste, clear=True)


class OpcjeKonfiguracji(unittest.TestCase):
    """Opcje ustawiane zmiennymi STRAZNIK_* albo w org.yaml → straznik (wtyczki testflight i automaty, filtr tytułów PR).
    Bez sieci: gh, Supabase, Resend i moduł asc.py są podstawione."""
    T = t("2026-11-09T13:20:00+01:00")

    def setUp(self):
        Z.konfiguruj(ORG_TEST)
        self.addCleanup(Z.konfiguruj, ORG_TEST)

    def podstaw(self, obiekt, nazwa, wartosc):
        p = mock.patch.object(obiekt, nazwa, wartosc)
        p.start()
        self.addCleanup(p.stop)

    def gh(self, odpowiedz):
        """Podstawia Z.gh_json: zwraca listę argumentów kolejnych wywołań gh; odpowiedź-wyjątek jest zgłaszana."""
        wywolania = []

        def gh_json(args, timeout=15):
            wywolania.append(args)
            if isinstance(odpowiedz, Exception):
                raise odpowiedz
            return odpowiedz
        self.podstaw(Z, "gh_json", gh_json)
        return wywolania

    def supabase(self):
        """Podstawia projekt, token i Z.supabase_sql; zwraca listę wykonanych zapytań (licznik builda = 4)."""
        zapytania = []

        def sql(token, zapytanie):
            zapytania.append(zapytanie)
            return {Z.SQL_CRON: [], Z.SQL_NET: [{"n": 0}]}.get(zapytanie, [{"bledy": 4}])
        self.podstaw(Z, "SUPABASE_PROJEKT", "abc")
        self.podstaw(Z, "sekret", lambda usluga: "token-testowy")
        self.podstaw(Z, "supabase_sql", sql)
        return zapytania

    def pr(self, nr, tytul, szkic=False):
        # utworzony 13:00 czasu lokalnego, czyli 20 min przed T – poniżej progu 60 min
        return {"number": nr, "title": tytul, "isDraft": szkic, "headRefOid": "%040d" % nr,
                "createdAt": "2026-11-09T12:00:00Z", "headDate": "2026-11-09T12:00:00Z"}

    # --- wtyczka testflight: moduł asc.py wyłącznie z katalogu ze zmiennej STRAZNIK_ASC (bez katalogu domyślnego) ---

    def test_asc_bez_zmiennej_czytelny_blad(self):
        with srodowisko():
            b = Z.bezpiecznie(Z.pobierz_asc)
        self.assertIn("ustaw STRAZNIK_ASC", b["blad"])
        dane = Z.zloz(TESTDANE / "repo", TESTDANE / "zadania", {"tagi": {}, "asc": b})
        w = K.kontrola_testflight(dane["testflight"], self.T)
        self.assertEqual((w["status"], w["zrodla_bledy"]), (K.BLAD, ["asc:awarie", "asc:zrzuty"]))
        self.assertIn("ustaw STRAZNIK_ASC", w["opis"])

    def test_asc_katalog_bez_modulu_i_brak_pakietu(self):
        with tempfile.TemporaryDirectory() as d, srodowisko(ASC=d):
            self.assertIn("brak pliku asc.py", Z.bezpiecznie(Z.pobierz_asc)["blad"])
            (Path(d) / "asc.py").write_text("def call(metoda, sciezka):\n    return {'data': []}\n", encoding="utf-8")
            with mock.patch.object(Z, "ASC_BUNDLE", ""):
                self.assertIn("ustaw STRAZNIK_ASC_BUNDLE", Z.bezpiecznie(Z.pobierz_asc)["blad"])
            self.assertNotIn(d, sys.path)  # do importu modułu nie doszło

    def test_asc_modul_z_katalogu_ze_zmiennej(self):
        modul = ('def call(metoda, sciezka):\n'
                 '    if sciezka.startswith("/v1/apps?"):\n'
                 '        return {"data": [{"id": "APP1"}] if "com.example.app" in sciezka else []}\n'
                 '    if "betaFeedbackScreenshotSubmissions" in sciezka:\n'
                 '        return {"data": [{"id": "AXtest01-aaaa", "attributes": {"createdDate": "2026-11-09T08:00:00.000Z"}}]}\n'
                 '    return {"data": []}\n')
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "asc.py").write_text(modul, encoding="utf-8")
            self.addCleanup(sys.modules.pop, "asc", None)
            self.addCleanup(lambda: sys.path.remove(d) if d in sys.path else None)
            with srodowisko(ASC=d), mock.patch.object(Z, "ASC_BUNDLE", "com.example.app"):
                w = Z.pobierz_asc()
            self.assertEqual(w, {"zrzuty": [{"id": "AXtest01-aaaa", "data": "2026-11-09T08:00:00.000Z"}], "awarie": []})
            with srodowisko(ASC=d), mock.patch.object(Z, "ASC_BUNDLE", "com.example.inna"):
                self.assertIn("nie znaleziono aplikacji com.example.inna", Z.bezpiecznie(Z.pobierz_asc)["blad"])

    # --- nagłówek User-Agent zapytań HTTP (Supabase, Resend) ---

    def test_naglowek_user_agent_neutralny(self):
        zadania = []

        class Odpowiedz:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'[{"n": 0}]'

        def urlopen(req, timeout=None):
            zadania.append(req)
            return Odpowiedz()
        self.podstaw(Z.urllib.request, "urlopen", urlopen)  # ten sam moduł urllib.request co w alerty.py
        with mock.patch.object(Z, "SUPABASE_PROJEKT", "abc"):
            self.assertEqual(Z.supabase_sql("token-testowy", Z.SQL_NET), [{"n": 0}])
        with srodowisko(RESEND_KEY="klucz-testowy"):
            self.assertEqual(A.wyslij_mail("temat", "treść"), "mail wysłany (HTTP 200)")
        self.assertEqual([r.full_url for r in zadania],
                         ["https://api.supabase.com/v1/projects/abc/database/query", "https://api.resend.com/emails"])
        self.assertEqual([r.get_header("User-agent") for r in zadania], ["straznik-floty", "straznik-floty"])

    # --- wdrożenie (Fly): repo i nazwa workflow ---

    def test_fly_domyslnie_pierwsze_repo_produktu(self):
        wyw = self.gh([{"conclusion": "success", "createdAt": "2026-11-09T07:00:00Z", "status": "completed"}])
        with srodowisko():
            f = Z.pobierz_fly()
        self.assertEqual(wyw, [["run", "list", "-R", "OWNER/produkt", "--workflow", "Fly Deploy", "-L", "1",
                                "--json", "conclusion,createdAt,status"]])
        self.assertEqual((f["workflow"], f["conclusion"]), ("Fly Deploy", "success"))

    def test_fly_repo_i_workflow_ze_zmiennych(self):
        wyw = self.gh([{"conclusion": "failure", "createdAt": "2026-11-09T07:00:00Z", "status": "completed"}])
        with srodowisko(FLY_REPO="strona", FLY_WORKFLOW="Wdrożenie"):
            f = Z.pobierz_fly()
        with srodowisko(FLY_REPO="inny-wlasciciel/inne-repo"):
            Z.pobierz_fly()
        self.assertEqual([x[2:6] for x in wyw], [["-R", "OWNER/strona", "--workflow", "Wdrożenie"],
                                                 ["-R", "inny-wlasciciel/inne-repo", "--workflow", "Fly Deploy"]])
        w = K.kontrola_automaty({"cron_failed": [], "net5xx": 0, "build_stan": None, "fly": f, "pages": {}}, self.T)
        self.assertEqual((w["status"], w["id"]), (K.ROZ, ["fly:2026-11-09T07:00:00Z"]))
        self.assertEqual(w["opis"], "Wdrożenie 2026-11-09T07:00:00Z: failure")

    def test_fly_bez_repo_produktu_pominiete(self):
        Z.konfiguruj({**ORG_TEST, "repo": {"github": "OWNER/firma-agenci", "produkt": []}})
        wyw = self.gh([])
        with srodowisko():
            f = Z.pobierz_fly()
        self.assertEqual((wyw, list(f)), ([], ["pominieta"]))
        w = K.kontrola_automaty({"cron_failed": [], "net5xx": 0, "build_stan": {"bledy": 0}, "fly": f, "pages": {}}, self.T)
        self.assertEqual((w["status"], w["zrodla_bledy"]), (K.OK, []))
        self.assertTrue(any(u.startswith("Fly Deploy: pominięte") and "STRAZNIK_FLY_REPO" in u for u in w["uwagi"]), w["uwagi"])
        with srodowisko(FLY_REPO="strona"):  # zmienna wystarcza także bez repo.produkt
            self.assertIsNone(Z.pobierz_fly())
        self.assertEqual(wyw[0][3], "OWNER/strona")

    def test_fly_blad_gh_z_nazwa_workflow(self):
        self.gh(Z.BladZrodla("gh run: kod 1: HTTP 404"))
        with srodowisko(FLY_WORKFLOW="Wdrożenie"), mock.patch.object(Z, "SUPABASE_PROJEKT", ""):
            a = Z.pobierz_automaty()
        self.assertEqual(a["fly"], {"blad": "gh run: kod 1: HTTP 404", "workflow": "Wdrożenie"})
        w = K.kontrola_automaty(a, self.T)
        self.assertIn("gh:fly", w["zrodla_bledy"])
        self.assertIn("źródło niedostępne – Wdrożenie: gh run: kod 1: HTTP 404", w["uwagi"])

    # --- filtr tytułów PR: STRAZNIK_POMIN_TYTUL albo org.yaml → straznik.pomin_tytul ---

    def test_pomin_tytul_domyslnie_nic_nie_pomija(self):
        with srodowisko():
            Z.konfiguruj({**ORG_TEST, "straznik": {"kontrole": list(Z.KONTROLE_WSZYSTKIE)}})
        self.assertEqual((K.POMIN_TYTUL, K.POMIN_TYTUL_BLAD), (None, None))
        prs = [self.pr(1, "[wstrzymane] pakiet"), self.pr(2, "Szkic", szkic=True)]
        w = K.kontrola_pr({"prs": {"produkt": prs}, "recenzje": {}}, self.T)
        self.assertEqual((w["status"], w["liczby"]["pominiete"], w["liczby"]["otwarte"], w["uwagi"]), (K.OK, 1, 1, []))

    def test_pomin_tytul_z_org_yaml(self):
        # ORG_TEST: ^\[wstrzymane – dopasowanie przez re.search, kotwica ^ ogranicza je do początku tytułu
        self.assertTrue(K.pr_pominiety(self.pr(1, "[wstrzymane] pakiet")))
        self.assertFalse(K.pr_pominiety(self.pr(2, "pakiet [wstrzymane]")))
        prs = [self.pr(1, "[wstrzymane] pakiet"), self.pr(2, "pakiet [wstrzymane]")]
        w = K.kontrola_pr({"prs": {"produkt": prs}, "recenzje": {}}, self.T)
        self.assertEqual((w["liczby"]["pominiete"], w["liczby"]["otwarte"]), (1, 1))

    def test_pomin_tytul_zmienna_ma_pierwszenstwo(self):
        with srodowisko(POMIN_TYTUL="WIP"):
            Z.konfiguruj(ORG_TEST)
            self.assertEqual(K.POMIN_TYTUL.pattern, "WIP")
            self.assertTrue(K.pr_pominiety(self.pr(1, "Poprawka (WIP)")))
            self.assertFalse(K.pr_pominiety(self.pr(2, "[wstrzymane] pakiet")))
            Z.konfiguruj({})  # repo bez org.yaml – filtr ze zmiennej działa tak samo
            self.assertEqual(K.POMIN_TYTUL.pattern, "WIP")

    def test_pomin_tytul_nie_do_uzycia_wylacza_filtr(self):
        for zly in ("[niedomknięte", ["WIP"]):
            with srodowisko():
                Z.konfiguruj({**ORG_TEST, "straznik": {"kontrole": list(Z.KONTROLE_WSZYSTKIE), "pomin_tytul": zly}})
            self.assertIsNone(K.POMIN_TYTUL, zly)
            w = K.kontrola_pr({"prs": {"produkt": [self.pr(1, "[niedomknięte WIP")]}, "recenzje": {}}, self.T)
            self.assertEqual((w["status"], w["liczby"]["pominiete"], w["liczby"]["otwarte"]), (K.OK, 0, 1), zly)
            self.assertIn("filtr wyłączony", w["uwagi"][0])
        with srodowisko(POMIN_TYTUL="(niedomknięte"):
            Z.konfiguruj(ORG_TEST)
        self.assertIsNone(K.POMIN_TYTUL)
        self.assertIn("niepoprawne wyrażenie regularne", K.POMIN_TYTUL_BLAD)

    def test_pomin_tytul_w_pliku_org_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "org.yaml"
            p.write_text("straznik:\n  pomin_tytul: '^\\[wstrzymane|^WIP: '  # komentarz\n", encoding="utf-8")
            self.assertEqual(Z.czytaj_org(d)["straznik"]["pomin_tytul"], r"^\[wstrzymane|^WIP: ")
            p.write_text("straznik:\n  pomin_tytul: [WIP]\n", encoding="utf-8")  # bez cudzysłowu to lista, nie napis
            with srodowisko():
                Z.konfiguruj(Z.czytaj_org(d))
        self.assertIsNone(K.POMIN_TYTUL)
        self.assertIn("ujmij w cudzysłów", K.POMIN_TYTUL_BLAD)

    def test_pobierz_pr_bez_zapytania_o_date_dla_pominietych(self):
        lista = [self.pr(1, "Zwykły"), self.pr(2, "Szkic", szkic=True), self.pr(3, "[wstrzymane] pakiet")]
        for x in lista:
            del x["headDate"]
        wyw, zapytania = self.gh(lista), []

        def uruchom(cmd, timeout=15, cwd=None):
            zapytania.append(cmd)
            return "2026-11-09T12:00:00Z\n"
        self.podstaw(Z, "uruchom", uruchom)
        wynik = Z.pobierz_pr("produkt")
        self.assertEqual(wyw[0][:4], ["pr", "list", "-R", "OWNER/produkt"])
        self.assertEqual([z[:3] for z in zapytania], [["gh", "api", "repos/OWNER/produkt/commits/" + "%040d" % 1]])
        self.assertEqual([x.get("headDate") for x in wynik], ["2026-11-09T12:00:00Z", None, None])

    # --- wtyczka automaty: zapytanie o licznik błędów builda (STRAZNIK_SQL_BUILD), projekt i token Supabase ---

    def test_sql_build_bez_zmiennej_pominiete(self):
        zapytania = self.supabase()
        self.gh([])
        with srodowisko():
            a = Z.pobierz_automaty()
        self.assertEqual(zapytania, [Z.SQL_CRON, Z.SQL_NET])
        self.assertIn("ustaw STRAZNIK_SQL_BUILD", a["build_stan"]["pominieta"])
        w = K.kontrola_automaty(a, self.T)
        self.assertEqual((w["status"], w["zrodla_bledy"]), (K.OK, []))
        self.assertNotIn("build_bledy", w["liczby"])
        self.assertTrue(any(u.startswith("build_stan: pominięte – ustaw STRAZNIK_SQL_BUILD") for u in w["uwagi"]), w["uwagi"])

    def test_sql_build_ze_zmiennej(self):
        zapytania = self.supabase()
        self.gh([])
        with srodowisko(SQL_BUILD=" select 4 as bledy "):
            a = Z.pobierz_automaty()
        self.assertEqual(zapytania, [Z.SQL_CRON, Z.SQL_NET, "select 4 as bledy"])
        self.assertEqual(a["build_stan"], {"bledy": 4})
        w = K.kontrola_automaty(a, self.T)
        self.assertEqual((w["status"], w["id"], w["liczby"]["build_bledy"]), (K.ROZ, ["build_stan"], 4))

    def test_automaty_bez_projektu_i_bez_tokenu(self):
        self.gh([])
        siegniecia = []
        self.podstaw(Z, "sekret", lambda usluga: siegniecia.append(usluga))  # zwraca None = brak tokenu
        with srodowisko(SQL_BUILD="select 1 as bledy"):
            with mock.patch.object(Z, "SUPABASE_PROJEKT", ""):
                a = Z.pobierz_automaty()
            self.assertEqual(siegniecia, [])  # bez projektu strażnik nie sięga po token
            for pole in ("cron_failed", "net5xx", "build_stan"):
                self.assertIn("ustaw STRAZNIK_SUPABASE_PROJEKT", a[pole]["blad"])
            with mock.patch.object(Z, "SUPABASE_PROJEKT", "abc"):
                a = Z.pobierz_automaty()
        self.assertEqual(siegniecia, ["supabase-pat-straznik"])
        self.assertIn("brak tokenu Supabase", a["cron_failed"]["blad"])
        w = K.kontrola_automaty(a, self.T)
        self.assertEqual((w["status"], w["zrodla_bledy"]), (K.BLAD, ["supabase:build_stan", "supabase:cron", "supabase:net"]))
        with srodowisko(), mock.patch.object(Z, "SUPABASE_PROJEKT", ""):  # bez zapytania o build ta część jest tylko pomijana
            self.assertIn("pominieta", Z.pobierz_automaty()["build_stan"])

    # --- GitHub Pages: lista repo ze zmiennej STRAZNIK_PAGES ---

    def test_pages_lista_repo_ze_zmiennej(self):
        wyw = []

        def gh_json(args, timeout=15):
            wyw.append(args)
            if args[0] != "api":
                return []  # workflow wdrożenia bez przebiegów
            if "/strona/" in args[1]:
                raise Z.BladZrodla("gh api: kod 1: HTTP 404: Not Found")
            return {"status": "errored", "created_at": "x"}
        self.podstaw(Z, "gh_json", gh_json)
        self.podstaw(Z, "SUPABASE_PROJEKT", "")
        with srodowisko():
            self.assertEqual((Z.repo_pages(), Z.pobierz_automaty()["pages"]), ((), {}))
        self.assertEqual([x[0] for x in wyw], ["run"])
        with srodowisko(PAGES="produkt, strona,produkt"):
            self.assertEqual(Z.repo_pages(), ("produkt", "strona"))
            a = Z.pobierz_automaty()
        self.assertEqual(a["pages"], {"produkt": {"status": "errored", "created_at": "x"}, "strona": None})
        self.assertIn(["api", "repos/OWNER/produkt/pages/builds/latest"], wyw)
        w = K.kontrola_automaty(a, self.T)
        self.assertEqual(w["id"], ["pages:produkt:x"])
        self.assertIn("Pages strona: repo bez GitHub Pages – pominięte", w["uwagi"])

    # --- wtyczki wyłączone (domyślna konfiguracja szablonu): żadnych wywołań App Store Connect ani Supabase ---

    def test_wtyczki_wylaczone_bez_wywolan_zrodel(self):
        Z.konfiguruj({**ORG_TEST, "straznik": {"kontrole": list(Z.KONTROLE_RDZEN)}})
        self.assertEqual(Z.KONTROLE_AKTYWNE, Z.KONTROLE_RDZEN)
        siegniecia = []
        self.podstaw(Z, "pobierz_asc", lambda: siegniecia.append("asc"))
        self.podstaw(Z, "pobierz_automaty", lambda: siegniecia.append("automaty"))
        self.podstaw(Z, "pobierz_tagi", lambda repo: {})
        self.podstaw(Z, "pobierz_pr", lambda repo: [])
        z = Z.pobierz_zewnetrzne(TESTDANE / "repo")
        self.assertEqual(siegniecia, [])
        self.assertIn("wtyczka wyłączona", z["asc"]["blad"])
        self.assertIn("wtyczka wyłączona", z["automaty"]["blad"])
        self.assertEqual(z["prs"], {"produkt": [], "strona": [], "firma-agenci": []})
        dane = Z.zloz(TESTDANE / "repo", TESTDANE / "zadania", z)
        w = K.uruchom_wszystkie(dane, self.T, Z.KONTROLE_AKTYWNE)
        self.assertEqual(sorted(w), sorted(Z.KONTROLE_RDZEN))


if __name__ == "__main__":
    unittest.main()
