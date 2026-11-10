"""Testy hooka uprawnień: python3 -I .claude/hooks/test_uprawnienia.py  (bez sieci – `gh` podmieniony atrapą; repo tymczasowe
z własnym `origin`, bo bramka scalania czyta werdykty i ustawienia z gałęzi głównej)."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TU = Path(__file__).resolve().parent
REPO = TU.parent.parent
sys.path.insert(0, str(TU))
import uprawnienia as U  # noqa: E402

GH_ATRAPA = """#!/usr/bin/env python3
import json, sys, os
# atrapa `gh pr view <nr> --json ...`: stan z GH_ATRAPA_PLIK (JSON {nr: {...}})
d = json.load(open(os.environ["GH_ATRAPA_PLIK"]))
nr = sys.argv[3] if len(sys.argv) > 3 else ""
if nr not in d: sys.exit(1)
print(json.dumps(d[nr]))
"""
REPO_GH = "firma/org-agenci"


def sha(nr):
    return ("%02d" % nr) + "a" * 38


def pr(nr, pliki=("obsluga/notatki.md",), ci="SUCCESS", **inne):
    d = {"number": nr, "title": "Zmiana %d" % nr, "body": "", "baseRefName": "main", "headRefName": "agent/inzynier-zmiana-%d" % nr,
         "headRefOid": sha(nr), "mergeable": "MERGEABLE", "statusCheckRollup": [{"name": "testy", "conclusion": ci}],
         "files": [{"path": x} for x in pliki], "changedFiles": len(pliki), "isDraft": False,
         "createdAt": "2026-11-10T08:00:00Z", "labels": []}
    d.update(inne)
    return d


def scal(nr, sha_=None, repo=REPO_GH, metoda="--merge", inne=""):
    """Polecenie w postaci, którą wypisuje tabela kolejki."""
    return "gh pr merge %d --repo %s %s --match-head-commit %s%s" % (nr, repo, metoda, sha_ or sha(nr), inne)


class Hook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="hook-"))
        for f in ("uprawnienia.yaml", "decyzje.md"):
            shutil.copy(REPO / f, cls.tmp / f)
        (cls.tmp / "flota").mkdir()
        (cls.tmp / "flota" / "zadania.yaml").write_text("zadania:\n- agent: obsluga\n  katalog: obsluga\n  typ: reader\n- agent: finansowy\n  katalog: finansowy\n  typ: actor\n- agent: wywiad\n  katalog: wywiad\n  typ: researcher\n")
        (cls.tmp / "decyzje").mkdir()
        (cls.tmp / "decyzje" / "D-20261110-02.md").write_text("---\nid: D-20261110-02\nstatus: accepted\nscope: test/a\n---\n# D-20261110-02 · Zgoda z katalogu\n")
        (cls.tmp / "decyzje" / "D-20261110-03.md").write_text("---\nid: D-20261110-03\nstatus: superseded\nscope: test/b\n---\n# D-20261110-03 · Zastąpiona\n")
        (cls.tmp / "polityki").mkdir()
        shutil.copy(REPO / "polityki" / "progi.yaml", cls.tmp / "polityki" / "progi.yaml")
        with (cls.tmp / "decyzje.md").open("a") as f:
            f.write("\n### D-20261109-07 · Zgoda testowa\n- Decyzja: scalenie PR 12\n")
        cls.bin = cls.tmp / "bin"; cls.bin.mkdir()
        gh = cls.bin / "gh"; gh.write_text(GH_ATRAPA); gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        cls.gh_plik = cls.tmp / "gh.json"
        cls.gh_plik.write_text(json.dumps({
            "12": pr(12), "13": pr(13, ci="FAILURE"), "14": pr(14), "15": pr(15), "16": pr(16, pliki=("uprawnienia.yaml",)),
            "17": pr(17, statusCheckRollup=[]), "18": pr(18, mergeable="CONFLICTING")}))
        ok = {"wynik": "OK", "scalenie": "tak", "warunki": [], "kroki": []}
        (cls.tmp / "recenzent").mkdir()
        (cls.tmp / "recenzent" / "stan.json").write_text(json.dumps({"recenzje": {
            "12": dict(ok, sha=sha(12)), "13": dict(ok, sha=sha(13)), "14": dict(ok, sha="ffff000"),
            "15": dict(ok, sha=sha(15), scalenie="warunek", warunki=["sprawdzić ręcznie stronę cennika"]),
            "16": dict(ok, sha=sha(16)), "17": dict(ok, sha=sha(17)), "18": dict(ok, sha=sha(18))}}))
        for f in ("scripts/scalanie.py", "ceo/scalanie/ustawienia.yaml", "ceo/kontrole/progi.yaml"):
            (cls.tmp / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / f, cls.tmp / f)
        (cls.tmp / "org.yaml").write_text('organizacja:\n  prefiks: "test"\n  strefa: "Europe/Warsaw"\nrepo:\n  github: "%s"\n  produkt: []\n' % REPO_GH)
        # repo git z własnym origin – hermetycznie (bez konfiguracji użytkownika)
        (cls.tmp / "gitconfig").write_text("")
        cls.git_env = {"GIT_CONFIG_GLOBAL": str(cls.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                       "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
                       "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}
        cls.origin = Path(tempfile.mkdtemp(prefix="hook-origin-"))
        e = dict(os.environ, **cls.git_env)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(cls.origin)], check=True, capture_output=True, env=e)
        for a in (["init", "-q", "-b", "main"], ["remote", "add", "origin", str(cls.origin)],
                  ["add", "recenzent/stan.json", "ceo/scalanie/ustawienia.yaml", "org.yaml"],
                  ["commit", "-q", "-m", "stan"], ["push", "-q", "origin", "main"]):
            subprocess.run(["git", "-C", str(cls.tmp)] + a, check=True, capture_output=True, env=e)
        cls.blokada = cls.tmp / "blokada-agenta"            # ważna blokada scalania trzymana przez agenta scalającego
        cls.blokada_ceo = cls.tmp / "blokada-ceo"
        cls.blokada_stara = cls.tmp / "blokada-stara"
        for b, kto, od in ((cls.blokada, "scalanie-a", 0), (cls.blokada_ceo, "ceo-czat", 0), (cls.blokada_stara, "scalanie-a", 3600)):
            b.mkdir()
            (b / "kto").write_text(json.dumps({"kto": kto, "token": "0123456789abcdef", "od_s": time.time() - od, "protokol": 1}))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(cls.origin, ignore_errors=True)

    def hook(self, narzedzie, wejscie, rola=None, env=None, sesja="s1", faza="PreToolUse"):
        e = {k: v for k, v in os.environ.items() if k not in ("AGENT_ROLA", "DECYZJA")}
        e["PATH"] = str(self.bin) + os.pathsep + e.get("PATH", "")
        e["GH_ATRAPA_PLIK"] = str(self.gh_plik)
        e.update(self.git_env)
        e.update({"SCALANIE_BLOKADA": str(self.blokada), "SCALANIE_TETNO": str(self.tmp / "tetno"), "SCALANIE_KATALOG": str(self.tmp / "wt")})
        e.update(env or {})
        plik = self.tmp / ".agent-rola"
        if rola:
            plik.write_text(rola + "\n")
        elif plik.exists():
            plik.unlink()
        p = subprocess.run([sys.executable, "-I", str(TU / "uprawnienia.py")], input=json.dumps(
            {"hook_event_name": faza, "tool_name": narzedzie, "tool_input": wejscie, "cwd": str(self.tmp), "session_id": sesja,
             "tool_use_id": "t1", "permission_mode": "default"}), capture_output=True, text=True, env=e)
        return p.returncode, p.stderr.strip(), p.stdout.strip()

    def audyt(self):
        pliki = sorted((self.tmp / "bezpieczenstwo" / "audyt").glob("*.jsonl"))
        return [json.loads(l) for p in pliki for l in p.read_text().splitlines() if l.strip()]

    def test_zwykle_polecenia_wolno(self):
        for cmd in ("ls -la", "git status", "git add zlecenia/ceo.md && git commit -m x && git push", "gh pr list --state open",
                    "python3 -m unittest discover flota", "git push origin HEAD", "curl -s https://api.example.com/x"):
            self.assertEqual(self.hook("Bash", {"command": cmd}, "obsluga", sesja="s-" + str(hash(cmd)))[0], 0, cmd)

    def test_zakazy_git_bez_wyjatkow(self):
        for cmd in ("git reset --hard HEAD~1", "git stash", "git clean -fd", "git checkout -- .", "git push --force origin main",
                    "git push -f", "git add -A", "git add .", "git branch -D main", "rm -rf ~", "cat .env", "cat ~/.ssh/id_rsa"):
            kod, msg, _ = self.hook("Bash", {"command": cmd}, "ceo", {"DECYZJA": "D-20261109-07"})
            self.assertEqual(kod, 2, cmd)
            self.assertIn("zasady.md", msg)

    def scalenie(self, cmd, rola="inzynier", env=None):
        return self.hook("Bash", {"command": cmd}, rola, env, sesja="s-" + str(hash((cmd, rola, str(env)))))

    def test_scalenie_gotowy_dla_kazdej_roli(self):
        for rola in ("ceo", "inzynier", None):               # GOTOWY: bramka deterministyczna, rola bez znaczenia
            self.assertEqual(self.scalenie(scal(12), rola)[0], 0, rola)
        self.assertEqual(self.scalenie("cd /tmp && " + scal(12) + " 2>&1")[0], 0)
        rek = [r for r in self.audyt() if r.get("regula") == "pr_scalenie_bez_migracji:bramka"]
        self.assertTrue(rek)

    def test_scalenie_odmowy_z_faktow(self):
        for nr, slowo in ((13, "CI_CZERWONE"), (14, "NOWY_HEAD"), (17, "BRAK_CI"), (18, "KONFLIKT"), (99, "nie zwrócił")):
            kod, msg, _ = self.scalenie(scal(nr), "ceo", {"SCALANIE_BLOKADA": str(self.blokada_ceo)})
            self.assertEqual(kod, 2, nr)
            self.assertIn(slowo, msg)

    def test_scalenie_tylko_polecenie_z_tabeli(self):
        for cmd, slowo in (("gh pr merge 12 --squash", "brakuje"),
                           ("gh pr merge 12 --repo %s --merge" % REPO_GH, "--match-head-commit"),
                           (scal(12, sha_=sha(13)), "nie jest aktualnym commitem"),
                           (scal(12, metoda="--squash"), "wymagają --merge"),
                           (scal(12, inne=" --admin"), "niedozwolony"),
                           (scal(12, inne=" --auto"), "niedozwolony"),
                           (scal(12, inne=" --delete-branch"), "niedozwolony"),
                           (scal(12, repo="obca/firma"), "nie należy do organizacji"),
                           (scal(12) + " && " + scal(15), "jedno scalenie"),
                           ("gh pr -R %s merge 12 --merge --match-head-commit %s" % (REPO_GH, sha(12)), "flagi między"),
                           (scal(12, sha_="$(git rev-parse HEAD)"), "podstawienia")):
            kod, msg, _ = self.scalenie(cmd, "ceo")
            self.assertEqual(kod, 2, cmd)
            self.assertIn(slowo, msg, cmd)

    def test_scalenie_wymaga_waznej_blokady(self):
        for b in (self.tmp / "nie-ma-blokady", self.blokada_stara):
            kod, msg, _ = self.scalenie(scal(12), "ceo", {"SCALANIE_BLOKADA": str(b)})
            self.assertEqual(kod, 2)
            self.assertIn("blokady scalania", msg)

    def test_scalenie_poza_kolejka_zakazane(self):
        for cmd in ("gh api -X PUT repos/%s/pulls/12/merge" % REPO_GH,
                    "curl -X PUT https://api.github.com/repos/%s/pulls/12/merge" % REPO_GH,
                    "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'"):
            kod, msg, _ = self.scalenie(cmd, "ceo", {"DECYZJA": "D-20261110-02"})
            self.assertEqual(kod, 2, cmd)
            self.assertIn("poza kolejką", msg)

    def test_scalenie_sciezka_ceo(self):
        ceo = {"SCALANIE_BLOKADA": str(self.blokada_ceo)}
        kod, msg, _ = self.scalenie(scal(15), "inzynier", ceo)                  # WARUNEK: nie dla innych ról
        self.assertEqual(kod, 2); self.assertIn("WARUNEK", msg)
        kod, msg, _ = self.scalenie(scal(15), None, ceo)                        # brak roli to nie CEO
        self.assertEqual(kod, 2)
        kod, msg, _ = self.scalenie(scal(15), "ceo")                            # CEO, ale blokadę trzyma agent scalający
        self.assertEqual(kod, 2); self.assertIn("ceo-czat", msg)
        self.assertEqual(self.scalenie(scal(15), "ceo", ceo)[0], 0)             # CEO pod własną blokadą
        kod, msg, _ = self.scalenie(scal(16), "ceo", ceo)                       # zasady i uprawnienia: decyzja właściciela
        self.assertEqual(kod, 2); self.assertIn("decyzja właściciela", msg)
        self.assertEqual(self.scalenie("DECYZJA=D-20261110-03 " + scal(16), "ceo", ceo)[0], 2)   # decyzja zastąpiona nie liczy się
        self.assertEqual(self.scalenie("DECYZJA=D-20261110-02 " + scal(16), "ceo", ceo)[0], 0)
        self.assertEqual(self.scalenie("DECYZJA=D-20261110-02 " + scal(16), "inzynier", ceo)[0], 2)  # decyzja nie zastępuje roli

    def test_polecenie_zlozone_kazda_czynnosc_osobno(self):
        kod, msg, _ = self.scalenie("gh pr create --title x --body y && fly deploy", "inzynier")
        self.assertEqual(kod, 2); self.assertIn("polecenie złożone", msg)
        kod, msg, _ = self.scalenie(scal(12) + " && fly deploy", "ceo")
        self.assertEqual(kod, 2); self.assertIn("wdrozenie_produkcja", msg)
        self.assertEqual(self.scalenie("gh pr list --search merge; gh pr comment 12 --body 'do merge po poprawce'", "obsluga")[0], 0)

    def test_zwrot_bramka_kwotowa(self):
        self.assertEqual(self.hook("Bash", {"command": "stripe refunds create --amount 4500 --charge ch_1"}, "finansowy")[0], 0)   # 45 USD ≤ 50
        kod, msg, _ = self.hook("Bash", {"command": "stripe refunds create --amount 9900 --charge ch_1"}, "finansowy")
        self.assertEqual(kod, 2); self.assertIn("> próg", msg)
        self.assertEqual(self.hook("Bash", {"command": "stripe refunds create --amount 9900 --charge ch_1"}, "finansowy", {"DECYZJA": "D-20261109-07"})[0], 0)
        kod, msg, _ = self.hook("Bash", {"command": "stripe refunds create --charge ch_1"}, "finansowy")
        self.assertEqual(kod, 2); self.assertIn("kwoty", msg)

    def test_regula_dwoch_reader_nie_placi_ale_odpowiada(self):
        kod, msg, _ = self.hook("Bash", {"command": "stripe refunds create --amount 100 --charge ch_1"}, "obsluga")
        self.assertEqual(kod, 2); self.assertIn("reguła dwóch", msg)
        self.assertEqual(self.hook("mcp__abc__send-email", {"to": "x"}, "obsluga")[0], 0)   # odpowiedź wg szablonu: wyjątek dla readera z listy sam
        kod, msg, _ = self.hook("mcp__abc__send-email", {"to": "x"}, "wywiad")
        self.assertEqual(kod, 2); self.assertIn("researcher", msg)

    def test_decyzja_z_katalogu_tylko_accepted(self):
        cmd = "stripe prices update price_1 -d unit_amount=1900"
        self.assertEqual(self.hook("Bash", {"command": cmd}, "ceo", {"DECYZJA": "D-20261110-02"})[0], 0)
        self.assertEqual(self.hook("Bash", {"command": cmd}, "ceo", {"DECYZJA": "D-20261110-03"})[0], 2)
        kod, msg, _ = self.hook("Bash", {"command": "stripe refunds create --amount 100 --charge ch_1"}, "ceo")  # CEO nie jest bramką
        self.assertEqual(kod, 2); self.assertIn("wlasciciel", msg)

    def test_wydatek_prog_zero_blokuje(self):
        kod, msg, _ = self.hook("mcp__abc__stripe_api_write", {"amount": 500}, "ceo")  # zmiana_ustawien_uslugi: ceo → wolno
        self.assertEqual(kod, 0)

    def test_decyzja_wlasciciela_odblokowuje_jedna_czynnosc(self):
        cmd = "stripe prices update price_1 -d unit_amount=1900"
        self.assertEqual(self.hook("Bash", {"command": cmd}, "ceo")[0], 2)  # zmiana_cen: wlasciciel
        self.assertEqual(self.hook("Bash", {"command": cmd}, "ceo", {"DECYZJA": "D-20261109-07"})[0], 0)
        self.assertEqual(self.hook("Bash", {"command": "DECYZJA=D-20261109-07 " + cmd}, "ceo")[0], 0)
        self.assertEqual(self.hook("Bash", {"command": cmd}, "ceo", {"DECYZJA": "D-20261109-99"})[0], 2)

    def test_nigdy_operator_i_wdrozenie(self):
        kod, msg, _ = self.hook("Bash", {"command": "stripe transfers create --amount 100"}, "ceo", {"DECYZJA": "D-20261109-07"})
        self.assertEqual(kod, 2); self.assertIn("operator", msg)
        kod, msg, _ = self.hook("Bash", {"command": "fly deploy"}, "ceo", {"DECYZJA": "D-20261109-07"})
        self.assertEqual(kod, 2); self.assertIn("operator", msg)

    def test_mail_mcp_obsluga_tak_marketing_nie_bez_roli_nie(self):
        n = "mcp__abc123__send-email"
        self.assertEqual(self.hook(n, {"to": "x"}, "obsluga")[0], 0)
        kod, msg, _ = self.hook(n, {"to": "x"}, "marketing")
        self.assertEqual(kod, 2); self.assertIn("ceo", msg)
        self.assertEqual(self.hook(n, {"to": "x"}, None)[0], 2)
        self.assertEqual(self.hook("mcp__abc123__list-inbox-threads", {}, None)[0], 0)
        self.assertEqual(self.hook("mcp__abc123__send-broadcast", {}, "ceo")[0], 2)

    def test_rola_ze_srodowiska_i_sam_dla_wszystkich(self):
        self.assertEqual(self.hook("Bash", {"command": "gh pr create --title x"}, None, {"AGENT_ROLA": "inzynier"})[0], 0)
        self.assertEqual(self.hook("Bash", {"command": "gh pr create --title x"}, None)[0], 0)

    def test_migracje(self):
        self.assertEqual(self.hook("mcp__abc__apply_migration", {}, "ceo")[0], 0)
        self.assertEqual(self.hook("mcp__abc__apply_migration", {}, "architekt")[0], 2)
        self.assertEqual(self.hook("Bash", {"command": "psql $DB -c 'DROP TABLE x'"}, "ceo")[0], 2)
        self.assertEqual(self.hook("mcp__scheduled-tasks__create_scheduled_task", {}, "pm")[0], 2)

    def test_petla_identyczne_polecenie(self):
        s = "s-petla"
        for i in range(U.LIMIT_POWTORZEN - 1):
            self.assertEqual(self.hook("Bash", {"command": "npm install"}, "inzynier", sesja=s)[0], 0, i)
        kod, msg, _ = self.hook("Bash", {"command": "npm install"}, "inzynier", sesja=s)
        self.assertEqual(kod, 2); self.assertIn("pętla", msg)
        self.assertEqual(self.hook("Bash", {"command": "npm install"}, "inzynier", sesja="s-inna")[0], 0)  # inna sesja – od nowa
        self.assertEqual(self.hook("Bash", {"command": "npm test"}, "inzynier", sesja=s)[0], 0)          # inne polecenie przerywa serię

    def test_halt_zatrzymuje_sesje(self):
        h = self.tmp / "bezpieczenstwo" / "HALT"
        h.parent.mkdir(exist_ok=True)
        h.write_text("budżet organizacji 100%\n")
        try:
            kod, _, out = self.hook("Bash", {"command": "ls"}, "ceo")
            self.assertEqual(kod, 0)
            d = json.loads(out)
            self.assertIs(d["continue"], False)
            self.assertEqual(d["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(self.hook("Read", {"file_path": "x"}, "ceo")[0], 0)  # odczyt nadal wolno
        finally:
            h.unlink()

    def test_audyt_kazdej_decyzji_z_lancuchem(self):
        before = len(self.audyt())
        self.hook("Bash", {"command": "ls -1"}, "pm", sesja="s-audyt")
        self.hook("Bash", {"command": "gh pr merge 13"}, "pm", sesja="s-audyt")
        self.hook("Bash", {"command": "ls -1"}, "pm", sesja="s-audyt", faza="PostToolUse")
        a = self.audyt()[before:]
        self.assertEqual([r["decyzja"] for r in a], ["allow", "deny", "wykonane"])
        self.assertEqual([r["faza"] for r in a], ["pre", "pre", "post"])
        for i in range(1, len(a)):
            self.assertEqual(a[i]["prev_hash"], a[i - 1]["hash"])
        self.assertTrue(all(len(r["hash"]) == 64 for r in a))

    def test_blokada_zapisana(self):
        self.hook("Bash", {"command": "gh pr merge 13"}, "tester")
        log = (self.tmp / "bezpieczenstwo" / "blokady.jsonl").read_text().strip().splitlines()
        w = json.loads(log[-1])
        self.assertEqual((w["rola"], w["czynnosc"]), ("tester", "pr_scalenie_bez_migracji"))

    def test_parser_uprawnien(self):
        u = U.czytaj_uprawnienia(REPO)
        self.assertEqual(u["przelew"]["poziom"], "operator")
        self.assertEqual(u["zwrot_klientowi"]["bramka"], "kwota")
        self.assertEqual(u["pr_scalenie_bez_migracji"]["bramka"], "pr")
        self.assertEqual(u["wysylka_maila"]["sam"], ["obsluga"])
        for cz in {c for _, c in U.WZORCE_BASH} | {c for _, c in U.WZORCE_MCP}:
            self.assertIn(cz, u, "czynność z hooka bez wiersza w uprawnienia.yaml: " + cz)


if __name__ == "__main__":
    unittest.main()
