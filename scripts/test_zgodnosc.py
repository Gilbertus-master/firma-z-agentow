"""Testy scripts/zgodnosc.py – bez sieci: szablon i projekt w katalogach tymczasowych."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wymiana as W  # noqa: E402
import zgodnosc as Z  # noqa: E402

SZABLON = {
    "scripts/a.py": "print('a')\n",
    "scripts/b.py": "print('b')\n",
    "scripts/c.py": "print('c')\n",
    ".claude/hooks/h.py": "h = 1\n",
    "procesy/01.md": "# Proces\n",
    "README.md": "szablon\n",
    "org.yaml": "firma: wzor\n",               # ścieżka lokalna (lista domyślna i .szablon-lokalne)
    "ceo/agent.md": "wzor\n",                  # lokalna przez */agent.md
    "ceo/wiedza/x.md": "wzor\n",               # lokalna przez */wiedza/
    "publiczne/zamiany.tsv": "a\tb\n",         # narzędzie wydawcy – poza pomiarem
}
PROJEKT = {
    "scripts/a.py": "print('a')\n",            # identyczny
    "scripts/b.py": "print('B zmienione')\n",  # zmieniony
    ".claude/hooks/h.py": "h = 1\n",           # identyczny
    "README.md": "projekt\n",                  # zmieniony
    "org.yaml": "firma: projekt-a\n",          # lokalny – pominięty mimo różnicy
    "ceo/agent.md": "projekt\n",
    "scripts/wlasny-tajny.py": "x = 1\n",      # tylko w projekcie, katalog szkieletu
    "sprzedaz/klienci.md": "treść\n",          # tylko w projekcie, katalog spoza szkieletu
    ".szablon-lokalne": "org.yaml\n*/agent.md\n*/wiedza/\n",
}


def zapisz(katalog, pliki):
    for sciezka, tresc in pliki.items():
        p = os.path.join(katalog, sciezka)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(tresc)


def repo_git(katalog, wiadomosc):
    for cmd in (["init", "-q", "-b", "main"], ["add", "."],
                ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                 "commit", "-q", "-m", wiadomosc]):
        subprocess.run(["git", "-C", katalog] + cmd, check=True, capture_output=True)


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.szablon = os.path.join(self.tmp.name, "szablon")
        self.projekt = os.path.join(self.tmp.name, "projekt")
        zapisz(self.szablon, SZABLON)
        zapisz(self.projekt, PROJEKT)

    def tearDown(self):
        self.tmp.cleanup()

    def uruchom(self, *argv):
        out = io.StringIO()
        kod = Z.main(["--repo", self.projekt, "--szablon", self.szablon] + list(argv), wyjscie=out)
        return kod, out.getvalue()


class TestPomiar(Baza):
    def test_liczby_i_pominiete(self):
        w, blad = Z.zmierz(self.projekt, self.szablon)
        self.assertIsNone(blad)
        self.assertEqual((w["identyczne"], w["zmienione"], w["brakujace"]), (2, 2, 2))
        self.assertEqual(w["procent"], 33.3)
        self.assertEqual(w["pominiete_lokalne"], 4)             # org.yaml, ceo/agent.md, ceo/wiedza/x.md, publiczne/
        self.assertEqual(w["top_brakujace"], ["scripts/c.py", "procesy/01.md"])   # mechanizmy przed procesami
        self.assertEqual(w["top_zmienione"], ["scripts/b.py", "README.md"])
        self.assertEqual(w["obszary"]["scripts"], {"identyczne": 1, "zmienione": 1, "brakujace": 1})
        self.assertEqual(w["tylko_w_projekcie"], 1)             # scripts/wlasny-tajny.py; sprzedaz/ poza szkieletem

    def test_sciezki_tylko_w_projekcie_nie_wychodza(self):
        kod, out = self.uruchom("--json")
        self.assertEqual(kod, 0)
        self.assertNotIn("wlasny-tajny", out)
        self.assertNotIn("klienci", out)
        self.assertNotIn(self.tmp.name, out)

    def test_bez_pliku_lokalnych_lista_domyslna(self):
        os.remove(os.path.join(self.projekt, ".szablon-lokalne"))
        w, _ = Z.zmierz(self.projekt, self.szablon)
        self.assertEqual(w["pominiete_lokalne"], 4)

    def test_dopasowanie_jak_pathspec(self):
        m = Z.dopasuj_lokalne(["polityki/", "flota/zadania.yaml", "*/agent.md", "*/wiedza/", "*/rejestr*.md"])
        for tak in ("polityki/x/y.md", "flota/zadania.yaml", "ceo/agent.md", "pm/wiedza/a/b.md", "pm/rejestr-x.md"):
            self.assertTrue(m(tak), tak)
        for nie in ("flota/zadania.yaml.bak", "a/b/agent.md", "flota/generuj.py", "politykiX/a", "pm/sub/rejestr.md"):
            self.assertFalse(m(nie), nie)

    def test_listy_domyslne_identyczne_i_w_pliku_szablonu(self):
        """Lista domyślna w aktualizuj-z-szablonu.sh = LOKALNE_DOMYSLNE; obie zawarte w .szablon-lokalne szablonu."""
        import re as _re
        import shlex
        katalog = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sh = open(os.path.join(katalog, "scripts", "aktualizuj-z-szablonu.sh"), encoding="utf-8").read()
        blok = _re.search(r"^\s*lokalne=\(([^)]+)\)", sh, _re.M).group(1)   # niepusta lista = domyślna
        self.assertEqual(shlex.split(blok), Z.LOKALNE_DOMYSLNE)
        self.assertLessEqual(set(Z.LOKALNE_DOMYSLNE), set(Z.lokalne(katalog)))

    def test_wzorce_zgodne_z_git_pathspec(self):
        """Ten sam wynik co git (:(glob) dla linii z `*`): stan instancji głębiej niż jeden poziom, scenariusze agentów bez
        _startowe, klasa znaków [!_]."""
        pliki = ["ceo/scalanie/stan.json", "ceo/scalanie/README.md", "ceo/scalanie/dziennik.jsonl", "ceo/kontrole/wyniki.jsonl",
                 "ceo/kontrole/kontrole.md", "ewaluacje/marketing/s1.yaml", "ewaluacje/_startowe/s.yaml", "ewaluacje/sprawdz.py",
                 "recenzent/szablony/rubryka.md", "recenzent/skrypty/skan.sh", "recenzent/stan.json", ".github/workflows/straznik.yml",
                 ".github/workflows/testy.yml", "a/b/stan.json"]
        with tempfile.TemporaryDirectory() as d:
            for f in pliki:
                os.makedirs(os.path.join(d, os.path.dirname(f)), exist_ok=True)
                open(os.path.join(d, f), "w").write("x\n")
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            subprocess.run(["git", "init", "-q", d], check=True, env=env)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True, env=env)
            spec = [(":(glob)" + (w + "**" if w.endswith("/") else w)) if "*" in w else w for w in Z.LOKALNE_DOMYSLNE]
            git = set(subprocess.run(["git", "-C", d, "ls-files", "--"] + spec, capture_output=True, text=True, check=True,
                                     env=env).stdout.split())
        m = Z.dopasuj_lokalne(Z.LOKALNE_DOMYSLNE)
        self.assertEqual({f for f in pliki if m(f)}, git)
        self.assertEqual(git, {"ceo/scalanie/stan.json", "ceo/scalanie/dziennik.jsonl", "ceo/kontrole/wyniki.jsonl",
                               "ewaluacje/marketing/s1.yaml", "recenzent/szablony/rubryka.md", "recenzent/stan.json",
                               ".github/workflows/straznik.yml"})

    LOGI_DOPISYWANE = ("przebiegi/ceo/2026-11-12.jsonl", "przebiegi/ceo/koszty-2026-11-12.jsonl", "bezpieczenstwo/audyt/2026-11.jsonl",
                       "bezpieczenstwo/blokady.jsonl", "ceo/scalanie/dziennik.jsonl", "ceo/kontrole/wyniki.jsonl",
                       "ewaluacje/wyniki/2026-11-12.jsonl", "propozycje/wyslane.jsonl", "ceo/straznik-zdarzenia.md")

    def test_logi_dopisywane_merge_union(self):
        """Każdy log tylko-dopisywany szkieletu ma merge=union (.gitattributes) – także każdy śledzony *.jsonl."""
        katalog = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sledzone = subprocess.run(["git", "-C", katalog, "ls-files", "*.jsonl"], capture_output=True, text=True).stdout.split()
        out = subprocess.run(["git", "-C", katalog, "check-attr", "merge", "--", *self.LOGI_DOPISYWANE, *sledzone],
                             capture_output=True, text=True, check=True).stdout
        bez = [l.split(":")[0] for l in out.splitlines() if not l.endswith(": union")]
        self.assertEqual(bez, [], "logi bez merge=union w .gitattributes")

    def test_projekt_bez_wspolnej_historii(self):
        repo_git(self.szablon, "szablon")
        repo_git(self.projekt, "projekt – osobna historia")
        w, blad = Z.zmierz(self.projekt, self.szablon)
        self.assertIsNone(blad)
        self.assertEqual((w["identyczne"], w["zmienione"], w["brakujace"]), (2, 2, 2))
        sha = subprocess.run(["git", "-C", self.szablon, "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True)
        self.assertEqual(w["wersja_szablonu"], sha.stdout.strip())
        # ten sam szablon jako ref zdalnego `szablon` w projekcie (bez wspólnej bazy z HEAD projektu)
        subprocess.run(["git", "-C", self.projekt, "remote", "add", "szablon", self.szablon], check=True)
        subprocess.run(["git", "-C", self.projekt, "fetch", "-q", "szablon", "main"], check=True)
        subprocess.run(["git", "-C", self.szablon, "tag", "v1.2"], check=True)
        subprocess.run(["git", "-C", self.projekt, "fetch", "-q", "--tags", "szablon"], check=True)
        w2, blad = Z.zmierz(self.projekt, None, pobierz=False)
        self.assertIsNone(blad)
        self.assertEqual((w2["identyczne"], w2["zmienione"], w2["brakujace"]), (2, 2, 2))
        self.assertEqual(w2["wersja_szablonu"], "v1.2")

    def test_brak_szablonu(self):
        out = io.StringIO()
        self.assertEqual(Z.main(["--repo", self.projekt, "--bez-pobierania"], wyjscie=out), 2)
        self.assertIn("nie znam szablonu", out.getvalue())

    def test_tabela(self):
        kod, out = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertIn("zgodność 33.3 %", out)
        self.assertIn("scripts/c.py", out)


class TestRekord(Baza):
    def test_rekord_przechodzi_bramke(self):
        repo_git(self.szablon, "szablon")
        cel = os.path.join(self.tmp.name, "rekord.json")
        kod, out = self.uruchom("--rekord", "projekt-a", "--plan", "Partia 1: scripts/ w PR z testami.", "--wyjscie", cel)
        self.assertEqual(kod, 0, out)
        with open(cel, encoding="utf-8") as f:
            r = json.load(f)
        self.assertEqual(W.bledy(r), [])
        self.assertEqual(r["typ"], "zgodnosc")
        self.assertEqual((r["identyczne"], r["zmienione"], r["brakujace"], r["procent"]), (2, 2, 2, 33.3))
        self.assertIn("scripts: 1/3", r["obszary"])
        tekst = json.dumps(r)
        self.assertNotIn("print(", tekst)              # bez treści plików
        self.assertNotIn("wlasny-tajny", tekst)        # bez ścieżek tylko z projektu
        self.assertEqual(W.etykiety(r), ["wymiana", "typ:zgodnosc", "od:projekt-a"])

    def test_rekord_bez_wersji_odrzucony(self):
        kod, out = self.uruchom("--rekord", "projekt-a", "--wyjscie", os.path.join(self.tmp.name, "r.json"))
        self.assertEqual(kod, 2)
        self.assertIn("wersja_szablonu", out)
        kod, _ = self.uruchom("--rekord", "projekt-a", "--wersja", "v2.0", "--wyjscie", os.path.join(self.tmp.name, "r.json"))
        self.assertEqual(kod, 0)


if __name__ == "__main__":
    unittest.main()
