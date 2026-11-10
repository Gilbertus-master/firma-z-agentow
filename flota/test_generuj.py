"""Testy manifestu i generatora promptów: python3 -m unittest discover flota"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import generuj  # noqa: E402

REPO = generuj.REPO
DNI = {"nd": 0, "pn": 1, "wt": 2, "sr": 3, "cz": 4, "pt": 5, "so": 6}


def pole(s, maks):
    """Rozwija pole crona (liczba, lista, zakres, krok) do zbioru liczb."""
    if s == "*":
        return set(range(maks))
    wynik = set()
    for cz in s.split(","):
        krok = 1
        if "/" in cz:
            cz, k = cz.split("/")
            krok = int(k)
        if cz == "*":
            od, do = 0, maks - 1
        elif "-" in cz:
            od, do = map(int, cz.split("-"))
        else:
            od = do = int(cz)
        wynik |= set(range(od, do + 1, krok))
    return wynik


def godziny_crona(cron):
    m, h, dzien, mies, tyg = cron.split()
    assert dzien == "*" and mies == "*", cron
    return {f"{g}:{mm:02d}" for g in pole(h, 24) for mm in pole(m, 60)}, tyg


def tsv():
    w = {}
    for l in (REPO / "koordynacja-odstepy.tsv").read_text().splitlines():
        if l.startswith("#") or not l.strip():
            continue
        k = l.split("\t")
        w[k[0]] = k
    return w


class Manifest(unittest.TestCase):
    def setUp(self):
        self.dane = generuj.wczytaj()
        self.zad = self.dane["zadania"]

    def test_diff_zero(self):
        for z in self.zad:
            with self.subTest(z["agent"]):
                self.assertEqual(generuj.prompt(z), (REPO / z["prompt"]).read_text())

    def test_kazdy_prompt_w_manifescie(self):
        pliki = {p.relative_to(REPO).as_posix() for p in (REPO / "ceo/handoff/prompty").glob("*.md")}
        self.assertEqual(pliki, {z["prompt"] for z in self.zad})

    def test_pola_i_unikalnosc(self):
        self.assertEqual(len({z["agent"] for z in self.zad}), len(self.zad))
        for z in self.zad:
            self.assertIn(z["priorytet"], ("P1", "P2", "P3"), z["agent"])
            self.assertRegex(z["konto_w_prompcie"], r"^[A-Z]$", z["agent"])
            self.assertTrue(z["opis"], z["agent"])
        self.assertEqual(self.zad[0]["agent"], "limit", "limit tworzy się jako pierwsze")
        self.assertEqual(self.zad[1]["agent"], "scalanie", "agent scalający zaraz po regulatorze limitu")
        self.assertEqual(self.zad[1]["cron"], "*/15 * * * *")

    def test_agenci_tsv_w_manifescie(self):
        katalogi = {z["katalog"] for z in self.zad if z["katalog"]}
        self.assertEqual(katalogi, set(tsv()))

    def test_cron_zgodny_z_tsv(self):
        t = tsv()
        for z in self.zad:
            if not z["katalog"]:
                continue
            with self.subTest(z["agent"]):
                _, odstep, pocz, dni, godz = t[z["katalog"]][:5]
                if godz == "*":
                    p = int(pocz[:2]) * 60 + int(pocz[3:]) + 30
                    ocz = {f"{(p + k * int(odstep)) % 1440 // 60}:{(p + k * int(odstep)) % 60:02d}"
                           for k in range(1440 // int(odstep))}
                else:
                    ocz = {f"{int(g.split(':')[0])}:{g.split(':')[1]}" for g in godz.split(",")}
                cron, tyg = godziny_crona(z["cron"])
                self.assertEqual(cron, ocz)
                self.assertEqual(tyg, "*" if dni == "*" else ",".join(str(DNI[d]) for d in dni.split(",")))

    def test_prompt_i_szablon_agenta_do_200_linii(self):
        for z in self.zad:
            self.assertLessEqual(generuj.prompt(z).count("\n"), 200, z["agent"])
        self.assertLessEqual((REPO / "role/_szablon-agenta.md").read_text().count("\n"), 200)

    def test_bez_niewypelnionych_znacznikow(self):
        for z in self.zad:
            self.assertNotIn("{{", generuj.prompt(z), z["agent"])

    def test_konto_b_zmienia_tylko_linie_konta(self):
        for z in self.zad:
            a = generuj.prompt(z).split("\n")
            b = generuj.prompt(z, "B").split("\n")
            self.assertEqual(b[1], "Konto: B")
            self.assertEqual(a[:1] + a[2:], b[:1] + b[2:])

    def test_modele_tylko_jako_klasy(self):
        """Manifest podaje klasę modelu, a ID modeli są wyłącznie w org.yaml → runtime.modele (nowy model = jedna zmiana)."""
        o = generuj.org()
        modele = o["runtime"]["modele"]
        self.assertEqual(set(modele), set(generuj.KLASY_MODELI))
        self.assertTrue(all(str(v).startswith("claude-") for v in modele.values()))
        for z in [self.dane] + self.zad:
            if "model" in z:
                self.assertIn(z["model"], generuj.KLASY_MODELI, z.get("agent", "domyślny"))
        tekst = (REPO / "flota/zadania.yaml").read_text()
        kod = "\n".join(l.split("#")[0] for l in tekst.splitlines())
        self.assertNotIn("claude-", kod, "ID modelu wpisane w manifest – użyj klasy z org.yaml → runtime.modele")
        self.assertEqual({w["model"] for w in generuj.wywolania(self.dane, "A")} - set(modele.values()), set())
        self.assertEqual(generuj.model_id({"agent": "recenzent", "model": "sedzia"}, self.dane, o), modele["sedzia"])
        with self.assertRaises(SystemExit):
            generuj.model_id({"agent": "x", "model": "claude-opus-5-5"}, self.dane, o)
        self.assertIn(generuj.rozliczenie(o), ("team", "api"))

    def test_budzety_pojemnosc_planu(self):
        """Team: wagi z manifestu skalowane do (miejsce floty + nadwyżka) × cel; bez pomiaru miejsca – kwoty z manifestu;
        api: kwoty z manifestu i sufit z mandatu. Bez rotacji kont – jedno konto floty."""
        import copy
        o = copy.deepcopy(generuj.org())
        rt = o["runtime"]
        rt.update(rozliczenie="team", konto="a", pojemnosc_miejsca_usd_miesiac=None, nadwyzka_usd_miesiac=0, wykorzystanie_cel_proc=95)
        self.assertEqual(generuj.konto_floty(o), "A")
        self.assertNotIn("konta", rt)
        n = generuj.budzety(self.dane, o)
        self.assertEqual(n["mnoznik"], 1.0)            # pojemność niezmierzona → kwoty z manifestu
        rt.update(pojemnosc_miejsca_usd_miesiac=2000, nadwyzka_usd_miesiac=500)
        b = generuj.budzety(self.dane, o)
        self.assertAlmostEqual(b["flota_usd_miesiac"], 2500 * 0.95, places=2)
        suma = sum(m for m, _, _ in b["agenci"].values())
        self.assertAlmostEqual(suma, b["flota_usd_miesiac"], delta=0.01 * len(b["agenci"]))
        ceo = b["agenci"]["ceo"]
        self.assertAlmostEqual(ceo[0], ceo[2] * b["mnoznik"], delta=0.01)
        rt["rozliczenie"] = "api"
        a = generuj.budzety(self.dane, o)
        self.assertEqual(a["mnoznik"], 1.0)
        self.assertEqual(a["flota_usd_miesiac"], float(o["mandat"]["budzet_floty_usd_miesiac"]))
        self.assertTrue(all(m == w for m, _, w in a["agenci"].values()))
        tsv = generuj.budzety_tsv(self.dane, o)
        self.assertIn("# rozliczenie\tapi", tsv)
        self.assertEqual((REPO / generuj.BUDZETY).read_text(), generuj.budzety_tsv(self.dane), "python3 flota/generuj.py")

    def test_task_id(self):
        prefiks = generuj.org()["organizacja"]["prefiks"]
        self.assertEqual(generuj.task_id("ceo", "B"), f"{prefiks}-ceo-b")
        ids = [w["taskId"] for w in generuj.wywolania(self.dane, "C")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith(prefiks + "-") and i.endswith("-c") for i in ids))

    def test_cli_sprawdz_i_konto(self):
        r = subprocess.run([sys.executable, str(REPO / "flota/generuj.py"), "--sprawdz"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(REPO / "flota/generuj.py"), "--konto", "B", "--wyjscie", d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(list(pathlib.Path(d).glob("*.md"))), len(self.zad))
            self.assertIn(f'"taskId": "{generuj.org()["organizacja"]["prefiks"]}-ceo-b"', r.stdout)

    def test_routines(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(REPO / "flota/generuj.py"), "--routines", "--tylko", "ceo,limit", "--wyjscie", d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            pliki = sorted(p.name for p in pathlib.Path(d).glob("*.md"))
            self.assertEqual(pliki, ["ceo.md", "limit.md"])
            t = (pathlib.Path(d) / "ceo.md").read_text()
            self.assertIn("CRON_TZ=", t)
            self.assertIn("Konto: A", t)
            self.assertNotIn("{{", t)

    def test_sprawdz_wykrywa_roznice(self):
        z = self.zad[1]
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(REPO / "flota/generuj.py"), "--wyjscie", d], capture_output=True, check=True)
            p = pathlib.Path(d) / pathlib.Path(z["prompt"]).name
            p.write_text(p.read_text() + "zmiana\n")
            r = subprocess.run([sys.executable, str(REPO / "flota/generuj.py"), "--sprawdz", "--wyjscie", d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("różnic: 1", r.stdout)


if __name__ == "__main__":
    unittest.main()
