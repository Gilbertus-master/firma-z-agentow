"""Testy scripts/odkrycia.py – szkice rekordów `odkrycie` z własnego repo (repo tymczasowe, bez sieci)."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
TU = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
_spec = importlib.util.spec_from_file_location("odkrycia", TU / "odkrycia.py")
O = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(O)
import wymiana as W  # noqa: E402

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


class Szkice(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp(prefix="odkrycia-"))
        self.git("init", "-q")
        self.commit({"org.yaml": 'organizacja:\n  prefiks: "firma-x"\n', ".szablon-lokalne": "org.yaml\n*/stan.json\nzlecenia/\n"}, "start")
        self.start = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.d), "-c", "user.name=t", "-c", "user.email=t@example.com", *a], check=True,
                              capture_output=True, text=True, env=ENV).stdout

    def commit(self, pliki, temat):
        for p, t in pliki.items():
            (self.d / p).parent.mkdir(parents=True, exist_ok=True)
            (self.d / p).write_text(t, encoding="utf-8")
        self.git("add", *pliki)
        self.git("commit", "-qm", temat)

    def test_tylko_mechanizmy_bez_tematu_i_lokalnych(self):
        self.commit({".claude/hooks/h.py": "x\n", ".claude/hooks/test_h.py": "t\n"}, "Klient ACME: poprawka bramki")
        self.commit({"zlecenia/ceo.md": "x\n", "ceo/stan.json": "{}\n", "marketing/plan.md": "x\n"}, "praca operacyjna")
        self.commit({"scripts/a.py": "x\n"}, "szablon: aktualizacja do abc1234")
        lista = O.szkice(self.d, od=self.start)
        self.assertEqual(len(lista), 1)
        r = lista[0]
        self.assertEqual((r["projekt"], r["rodzaj"]), ("firma-x", "hook"))
        self.assertEqual(r["sciezki"], [".claude/hooks/h.py", ".claude/hooks/test_h.py"])
        self.assertIn("test: .claude/hooks/test_h.py", r["dowod"])
        self.assertNotIn("ACME", json.dumps(r))                                  # temat commita nie trafia do szkicu
        self.assertTrue(any("brak pola: objaw" in b for b in W.bledy(r)))        # szkic nie przejdzie bez uzupełnienia
        r.update(objaw="o", przyczyna="p", zmiana="z", ogolnosc="ogolne", pilnosc="zwykle")
        self.assertEqual(W.bledy(r), [])                                          # po uzupełnieniu – poprawny rekord

    def test_zapis_do_katalogu_i_zla_rewizja(self):
        self.commit({"moduly/straznik/k.py": "x\n", "ceo/kontrole/progi.yaml": "a: 1\n"}, "strażnik")
        out = self.d.parent / (self.d.name + "-wynik")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(O.main(["--repo", str(self.d), "--od", self.start, "--katalog", str(out)]), 0)
            pliki = list(out.glob("odkrycie-*.json"))
            self.assertEqual(len(pliki), 1)
            self.assertIn(json.loads(pliki[0].read_text())["rodzaj"], ("straznik", "prog"))
        finally:
            shutil.rmtree(out, ignore_errors=True)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(O.main(["--repo", str(self.d), "--od", "nieistnieje"]), 2)


if __name__ == "__main__":
    unittest.main()
