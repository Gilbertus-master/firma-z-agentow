"""Testy scripts/wymiana.py – bez sieci (gh podmieniony)."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wymiana as W  # noqa: E402

ODK = {"typ": "odkrycie", "projekt": "projekt-a", "rodzaj": "skrypt", "objaw": "Dwa agenty nadpisały sobie commit.",
       "przyczyna": "git add + commit nie jest atomowe przy wspólnym indeksie.", "zmiana": "Commit przez pathspec.",
       "dowod": "Test regresji test_zapisz.sh; 0 wymieszanych commitów od 12.11.", "ogolnosc": "ogolne", "pilnosc": "zwykle",
       "sciezki": ["scripts/zapisz.sh"]}
WYD = {"typ": "wydanie", "co": "Commit tylko przez pathspec.", "dlaczego": "Wyścig indeksu przy wielu agentach.",
       "priorytet": "zalecane", "jak_wdrozyc": "scripts/aktualizuj-z-szablonu.sh --pr", "decyzja_wlasciciela": "nie",
       "do": ["wszyscy"], "zrodla": ["#2"]}
ZGO = {"typ": "zgodnosc", "projekt": "projekt-a", "wersja_szablonu": "54f1aba", "identyczne": 80, "zmienione": 15,
       "brakujace": 5, "procent": 80.0, "obszary": ["scripts: 20/24", "procesy: 10/13"], "top_brakujace": ["scripts/zgodnosc.py"],
       "top_zmienione": ["scripts/przebieg.sh"], "plan": "Partia 1: scripts/ w jednym PR z testami."}


class Gh:
    def __init__(self, wynik=""):
        self.wywolania, self.wynik = [], wynik

    def __call__(self, cmd, **kw):
        self.wywolania.append(cmd)
        return type("P", (), {"returncode": 0, "stdout": self.wynik, "stderr": ""})()


def plik(rekord):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(rekord, f, ensure_ascii=False)
    f.close()
    return f.name


class TestSchemat(unittest.TestCase):
    def test_poprawne(self):
        self.assertEqual(W.bledy(ODK), [])
        self.assertEqual(W.bledy(WYD), [])

    def test_braki_i_wartosci(self):
        r = dict(ODK, pilnosc="bardzo", rodzaj="cos")
        r.pop("dowod")
        b = W.bledy(r)
        self.assertIn("brak pola: dowod", b)
        self.assertTrue(any(x.startswith("pilnosc:") for x in b))
        self.assertTrue(any(x.startswith("rodzaj:") for x in b))

    def test_zwiezlosc(self):
        self.assertTrue(W.bledy(dict(ODK, objaw="x" * 301)))
        self.assertTrue(W.bledy(dict(ODK, objaw="dwie\nlinie")))
        self.assertTrue(W.bledy(dict(ODK, sciezki=["a"] * 11)))
        self.assertTrue(W.bledy(dict(ODK, kod="\n" * 50)))
        self.assertTrue(W.bledy(dict(ODK, nadmiar="x")))

    def test_bramka_danych(self):
        for zle in ("jan.kowalski" + "@poczta-domowa.pl", "600 700 800", "90010112345", "ghp_abcdefghijklmnop", "PL61 1090 1014 0000 0712 1981 2874"):
            self.assertTrue(any("bramka" in x for x in W.bledy(dict(ODK, objaw="Zgłosił " + zle))), zle)
        self.assertEqual(W.bledy(dict(ODK, objaw="Adres operator@firma.example działa.")), [])
        self.assertTrue(W.bledy(ODK, ["Dwa agenty"]))

    def test_zgodnosc(self):
        self.assertEqual(W.bledy(ZGO), [])
        self.assertEqual(W.bledy(dict(ZGO, wersja_szablonu="v1.2")), [])
        for zle in ({"wersja_szablonu": "main"}, {"identyczne": -1}, {"identyczne": "80"}, {"procent": 120},
                    {"procent": 50.0}, {"obszary": ["scripts 20 z 24"]}, {"obszary": ["a: 1/1"] * 11},
                    {"top_brakujace": ["x"] * 11}, {"plan": "x" * 301}, {"tresc": "plik"}):
            self.assertTrue(W.bledy(dict(ZGO, **zle)), zle)
        r = dict(ZGO)
        r.pop("procent")
        self.assertIn("brak pola: procent", W.bledy(r))
        self.assertTrue(any("bramka" in x for x in W.bledy(dict(ZGO, plan="Pytania: tel. 600 700 800."))))
        self.assertEqual(W.bledy(dict(ZGO, identyczne=0, zmienione=0, brakujace=0, procent=0)), [])
        self.assertEqual(W.wzor("zgodnosc")["identyczne"], 0)

    def test_do_wydania(self):
        self.assertTrue(W.bledy(dict(WYD, do=["Projekt A"])))


class TestTresc(unittest.TestCase):
    def test_tresc_w_obie_strony(self):
        self.assertEqual(W.odczytaj(W.tresc(ODK)), ODK)
        self.assertIsNone(W.odczytaj("zwykły opis bez znacznika"))

    def test_etykiety(self):
        self.assertEqual(W.etykiety(ODK), ["wymiana", "typ:odkrycie", "od:projekt-a"])
        self.assertIn("pilne", W.etykiety(dict(ODK, pilnosc="bezpieczenstwo")))
        self.assertEqual(W.etykiety(WYD), ["wymiana", "typ:wydanie", "do:wszyscy"])
        self.assertEqual(W.etykiety(ZGO), ["wymiana", "typ:zgodnosc", "od:projekt-a"])
        self.assertIn("80.0%", W.tytul(ZGO))
        self.assertEqual(W.odczytaj(W.tresc(ZGO)), ZGO)


class TestEdycjaPubliczna(unittest.TestCase):
    """Edycja publiczna: domyślny cel = publiczne repo wydawcy z org.yaml; zapis tylko po świadomym wyborze."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.stary = os.getcwd()
        os.chdir(self.d)
        self.env, self.flaga = os.environ.pop("WYMIANA_REPO", None), W.EDYCJA_PUBLICZNA
        self.rekord = plik(ODK)

    def tearDown(self):
        os.chdir(self.stary)
        setattr(W, "EDYCJA_PUBLICZNA", self.flaga)
        if self.env is not None:
            os.environ["WYMIANA_REPO"] = self.env

    def org(self, dziel):
        with open("org.yaml", "w", encoding="utf-8") as f:
            f.write('repo:\n  szablon: "wydawca/szablon"\n  dziel_sie_ulepszeniami: %s\n' % dziel)

    def wyslij(self, *extra):
        out, g = io.StringIO(), Gh("https://github.com/wydawca/szablon/issues/1")
        kod = W.main(["wyslij", self.rekord, "--repo", W.repo_domyslne()] + list(extra), uruchom=g, wyjscie=out)
        return kod, out.getvalue(), g

    def test_cel_domyslny_z_org_yaml(self):
        self.org("false")
        self.assertEqual(W.repo_domyslne(), "wydawca/szablon")

    def test_szablon_prywatny_bez_bramki(self):
        setattr(W, "EDYCJA_PUBLICZNA", False)
        self.org("false")
        kod, _, g = self.wyslij()
        self.assertEqual(kod, 0)
        self.assertEqual(len(g.wywolania), 1)

    def test_publiczna_bez_zgody_nic_nie_wychodzi(self):
        setattr(W, "EDYCJA_PUBLICZNA", True)
        self.org("false")
        kod, out, g = self.wyslij()
        self.assertEqual(kod, 3)
        self.assertIn("PUBLICZNE", out)
        self.assertEqual(g.wywolania, [])
        self.assertEqual(self.wyslij("--na-sucho")[0], 0, "podgląd bez zgody wolno")

    def test_publiczna_ze_zgoda(self):
        setattr(W, "EDYCJA_PUBLICZNA", True)
        self.org("false")
        kod, _, g = self.wyslij("--publicznie")
        self.assertEqual((kod, len(g.wywolania)), (0, 1))
        self.org("true")
        kod, _, g = self.wyslij()
        self.assertEqual((kod, len(g.wywolania)), (0, 1))

    def test_publiczna_inne_repo_jawnie(self):
        setattr(W, "EDYCJA_PUBLICZNA", True)
        self.org("false")
        out, g = io.StringIO(), Gh("ok")
        self.assertEqual(W.main(["wyslij", self.rekord, "--repo", "ja/prywatne"], uruchom=g, wyjscie=out), 0)


class TestPolecenia(unittest.TestCase):
    def uruchom(self, argv, gh=None):
        out, g = io.StringIO(), gh or Gh()
        if argv[0] in ("wyslij", "status", "lista") and "--repo" not in argv:
            argv = argv + ["--repo", "wydawca/szablon"]
        kod = W.main(argv, uruchom=g, wyjscie=out)
        return kod, out.getvalue(), g

    def test_sprawdz_i_odrzucenie(self):
        self.assertEqual(self.uruchom(["sprawdz", plik(ODK)])[0], 0)
        kod, out, _ = self.uruchom(["sprawdz", plik(dict(ODK, objaw="tel. 600 700 800"))])
        self.assertEqual(kod, 2)
        self.assertIn("ODRZUCONE", out)

    def test_wyslij_wola_gh_z_etykietami(self):
        kod, out, g = self.uruchom(["wyslij", plik(ODK)], Gh("https://github.com/x/y/issues/7\n"))
        self.assertEqual(kod, 0)
        cmd = g.wywolania[0]
        self.assertEqual(cmd[:3], ["gh", "issue", "create"])
        self.assertIn("od:projekt-a", cmd)
        self.assertEqual(W.odczytaj(cmd[cmd.index("--body") + 1]), ODK)

    def test_na_sucho_bez_gh(self):
        kod, _, g = self.uruchom(["wyslij", plik(WYD), "--na-sucho"])
        self.assertEqual((kod, g.wywolania), (0, []))

    def test_status(self):
        kod, _, g = self.uruchom(["status", "7", "odrzucone", "Dotyczy tylko jednej domeny."])
        self.assertEqual(kod, 0)
        self.assertEqual([c[2] for c in g.wywolania], ["comment", "edit", "close"])
        self.assertEqual(self.uruchom(["status", "7", "zle", "x"])[0], 2)

    def test_lista(self):
        dane = [{"number": 7, "title": "t", "body": W.tresc(ODK), "createdAt": "2026-11-12T10:00:00Z", "state": "OPEN",
                 "labels": [{"name": "wymiana"}, {"name": "od:projekt-a"}, {"name": "status:przyjete"}]},
                {"number": 1, "title": "stare", "body": "bez schematu", "createdAt": "2026-11-12T09:00:00Z", "state": "OPEN",
                 "labels": [{"name": "wymiana"}, {"name": "do:inny"}]}]
        kod, out, _ = self.uruchom(["lista", "--json"], Gh(json.dumps(dane)))
        w = json.loads(out)
        self.assertEqual([(x["nr"], x["status"], x["rekord"]) for x in w], [(7, "przyjete", True), (1, "nowe", False)])
        kod, out, _ = self.uruchom(["lista", "--projekt", "projekt-a", "--json"], Gh(json.dumps(dane)))
        self.assertEqual([x["nr"] for x in json.loads(out)], [7])

    def test_lista_zgodnosc_ostatni_na_projekt(self):
        def zg(nr, projekt, procent, chwila):
            r = dict(ZGO, projekt=projekt, identyczne=int(procent), zmienione=100 - int(procent), brakujace=0, procent=float(procent))
            return {"number": nr, "title": "t", "body": W.tresc(r), "createdAt": chwila, "state": "OPEN",
                    "labels": [{"name": "wymiana"}, {"name": "typ:zgodnosc"}, {"name": "od:%s" % projekt}]}
        dane = [zg(9, "projekt-a", 90, "2026-11-19T10:00:00Z"), zg(8, "projekt-b", 40, "2026-11-18T10:00:00Z"),
                zg(5, "projekt-a", 70, "2026-11-12T10:00:00Z")]
        kod, out, g = self.uruchom(["lista", "--typ", "zgodnosc", "--json"], Gh(json.dumps(dane)))
        w = json.loads(out)
        self.assertEqual([(x["nr"], x["projekt"], x["procent"]) for x in w], [(9, "projekt-a", 90.0), (8, "projekt-b", 40.0)])
        self.assertIn("typ:zgodnosc", g.wywolania[0])
        # kolejność odpowiedzi bez znaczenia – liczy się data
        kod, out, _ = self.uruchom(["lista", "--typ", "zgodnosc", "--json"], Gh(json.dumps(dane[::-1])))
        self.assertEqual(sorted(x["nr"] for x in json.loads(out)), [8, 9])
        kod, out, _ = self.uruchom(["lista", "--typ", "zgodnosc", "--wszystkie", "--json"], Gh(json.dumps(dane)))
        self.assertEqual(len(json.loads(out)), 3)
        kod, out, _ = self.uruchom(["lista", "--typ", "zgodnosc"], Gh(json.dumps(dane)))
        self.assertIn("projekt-a 90.0%", out)



class GhSekwencja:
    """Atrapa gh: odpowiedzi po kolei (kod, stdout, stderr) albo funkcja(cmd) -> (kod, stdout, stderr)."""

    def __init__(self, odpowiedzi):
        self.odp, self.wywolania = odpowiedzi, []

    def __call__(self, cmd, **kw):
        self.wywolania.append(cmd)
        kod, out, err = self.odp(cmd) if callable(self.odp) else self.odp[len(self.wywolania) - 1]
        return type("P", (), {"returncode": kod, "stdout": out, "stderr": err})()


def odpowiedz_api(zgloszenie, etykiety_repo=()):
    def f(cmd):
        if cmd[1] == "api":
            return 0, json.dumps(zgloszenie), ""
        if cmd[1:3] == ["label", "list"]:
            return 0, json.dumps([{"name": n} for n in etykiety_repo]), ""
        return 0, "", ""
    return f


class TestBezUprawnien(unittest.TestCase):
    def wyslij(self, g):
        out = io.StringIO()
        return W.main(["wyslij", plik(ODK), "--repo", "wydawca/szablon"], uruchom=g, wyjscie=out), out.getvalue()

    def test_ponowienie_bez_etykiet(self):
        g = GhSekwencja([(1, "", "could not add label: 'od:projekt-a' not found"), (0, "https://github.com/w/s/issues/3\n", "")])
        kod, out = self.wyslij(g)
        self.assertEqual(kod, 0)
        self.assertEqual(len(g.wywolania), 2, "dokładnie jedno ponowienie")
        self.assertIn("--label", g.wywolania[0])
        self.assertNotIn("--label", g.wywolania[1])
        self.assertFalse(any(x.startswith(("od:", "typ:")) or x == "wymiana" for x in g.wywolania[1]))
        self.assertEqual(W.odczytaj(g.wywolania[1][g.wywolania[1].index("--body") + 1]), ODK)
        self.assertIn("ETYKIETY", out)
        self.assertIn("issues/3", out)

    def test_bez_petli_i_inny_blad_bez_ponowienia(self):
        g = GhSekwencja([(1, "", "HTTP 403: Resource not accessible by integration (label)"), (1, "", "HTTP 403: forbidden")])
        with self.assertRaises(SystemExit):
            self.wyslij(g)
        self.assertEqual(len(g.wywolania), 2)
        g = GhSekwencja([(1, "", "HTTP 502: bad gateway")])
        with self.assertRaises(SystemExit):
            self.wyslij(g)
        self.assertEqual(len(g.wywolania), 1)


class TestEtykietuj(unittest.TestCase):
    def uruchom(self, zgl, repo_et=()):
        g, out = GhSekwencja(odpowiedz_api(zgl, repo_et)), io.StringIO()
        kod = W.main(["etykietuj", "5", "--repo", "wydawca/szablon"], uruchom=g, wyjscie=out)
        return kod, out.getvalue(), g

    def edycje(self, g):
        return [c for c in g.wywolania if c[1:3] in (["issue", "edit"], ["issue", "comment"], ["label", "create"])]

    def test_poprawny_rekord(self):
        kod, out, g = self.uruchom({"body": W.tresc(ODK), "labels": [], "author_association": "NONE"}, ["wymiana"])
        self.assertEqual(kod, 0)
        utworzone = [c[3] for c in g.wywolania if c[1:3] == ["label", "create"]]
        self.assertEqual(utworzone, ["typ:odkrycie", "od:projekt-a"])
        edit = [c for c in g.wywolania if c[1:3] == ["issue", "edit"]][0]
        self.assertEqual(edit[edit.index("--add-label") + 1], "wymiana,typ:odkrycie,od:projekt-a")

    def test_bez_znacznika_bez_akcji(self):
        kod, out, g = self.uruchom({"body": "Zwykłe zgłoszenie", "labels": [], "author_association": "NONE"})
        self.assertEqual((kod, self.edycje(g)), (0, []))
        self.assertIn("BEZ AKCJI", out)

    def test_bramka_danych_poza_schematem_bez_tresci(self):
        zly = dict(ODK, dowod="Pisz na jan.kowalski" + "@poczta-domowa.pl po szczegóły.")   # składane – bez literału adresu w pliku
        kod, out, g = self.uruchom({"body": W.tresc(zly), "labels": [], "author_association": "NONE"})
        self.assertIn("POZA SCHEMATEM", out)
        kom = [c for c in g.wywolania if c[1:3] == ["issue", "comment"]][0]
        tekst = kom[kom.index("--body") + 1]
        self.assertIn("bramka danych", tekst)
        self.assertNotIn("kowalski", tekst)
        self.assertTrue(any(W.POZA_SCHEMATEM in c for c in g.wywolania if c[1:3] == ["issue", "edit"]))
        # ponowna edycja tego samego zgłoszenia – bez drugiego komentarza
        kod, out, g = self.uruchom({"body": W.tresc(zly), "labels": [{"name": W.POZA_SCHEMATEM}], "author_association": "NONE"})
        self.assertEqual(self.edycje(g), [])

    def test_poprawka_zdejmuje_poza_schematem(self):
        kod, out, g = self.uruchom({"body": W.tresc(ODK), "labels": [{"name": W.POZA_SCHEMATEM}], "author_association": "NONE"},
                                   ["wymiana", "typ:odkrycie", "od:projekt-a", W.POZA_SCHEMATEM])
        self.assertTrue(any("--remove-label" in c for c in g.wywolania))

    def test_wydanie_tylko_od_wydawcy(self):
        kod, out, g = self.uruchom({"body": W.tresc(WYD), "labels": [], "author_association": "NONE"})
        self.assertIn("POZA SCHEMATEM", out)
        kod, out, g = self.uruchom({"body": W.tresc(WYD), "labels": [], "author_association": "OWNER"}, ["wymiana", "typ:wydanie"])
        self.assertIn("ETYKIETY", out)

    def test_zepsuty_json(self):
        kod, out, g = self.uruchom({"body": W.ZNACZNIK + "\n```json\n{zle\n```\n", "labels": [], "author_association": "NONE"})
        self.assertIn("POZA SCHEMATEM", out)


class TestListaBezEtykiet(unittest.TestCase):
    def test_zgloszenie_bez_etykiet_widoczne(self):
        bez = {"number": 11, "title": "t", "body": W.tresc(ODK), "createdAt": "2026-11-12T11:00:00Z", "state": "OPEN", "labels": []}
        wyd = {"number": 12, "title": "t", "body": W.tresc(WYD), "createdAt": "2026-11-12T11:00:00Z", "state": "OPEN", "labels": []}
        g = GhSekwencja(lambda cmd: (0, json.dumps([bez, wyd] if "--search" in cmd else []), ""))
        out = io.StringIO()
        W.main(["lista", "--projekt", "projekt-a", "--json", "--repo", "w/s"], uruchom=g, wyjscie=out)
        self.assertEqual([x["nr"] for x in json.loads(out.getvalue())], [11])
        out = io.StringIO()
        W.main(["lista", "--typ", "wydanie", "--json", "--repo", "w/s"], uruchom=g, wyjscie=out)
        self.assertEqual(json.loads(out.getvalue()), [], "wydanie bez etykiet nie pochodzi od wydawcy")

if __name__ == "__main__":
    unittest.main()
