#!/usr/bin/env bash
# Uzgodnienie liczbowe recenzenta (role/recenzent.md, „Przy każdym przebiegu” pkt 1; kontrakt przebiegu – źródło `PR otwarte`).
# Otwarte PR-y (bez draftów) we wszystkich repozytoriach z org.yaml → repo.produkt i w repo organizacji (repo.github), po numerze
# i head SHA, porównane z recenzent/stan.json → recenzje. Klucz werdyktu: goły numer dla PIERWSZEGO repo produktu (gdy repo.produkt
# jest puste – repo organizacji), `<nazwa-repo>#N` dla pozostałych (ten sam format czyta hook .claude/hooks/uprawnienia.py i strażnik;
# przyjmowane też `<repo>/N` i `<repo>-N`). Werdykt „jest” tylko wtedy, gdy `sha` (≥ 7 znaków) jest prefiksem aktualnego head.
#
#   bash recenzent/skrypty/uzgodnienie.sh          # „PR otwarte: N, z werdyktem dla head: M, bez: K (klucze)” + linie DO PRACY
#   bash recenzent/skrypty/uzgodnienie.sh --json   # {"otwarte","z_werdyktem","bez":[{klucz,repo,numer,head,w_stanie,powod,tytul}],"bledy":[…]}
#
# Kody: 0 – każdy otwarty PR ma werdykt dla head · 1 – są PR-y do pracy · 3 – któreś repo nie odpowiedziało (gh/sieć; w kontrakcie
# `przeczytane: null` + wpis w `bledy`) · 2 – złe wywołanie. Wymaga gh i python3 (biblioteka standardowa). Bez zapisu, bez commitów.
# Do testów: RECENZENT_REPO=<katalog repo z org.yaml i recenzent/stan.json>, atrapa `gh` w PATH. RECENZENT_POMIN_TYTUL=<regex> pomija
# PR-y o pasującym tytule (np. pakiet wstrzymany do daty), RECENZENT_LIMIT (domyślnie 100).
set -u
case "${1:-}" in
  ""|--json) ;;
  -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Użycie: $0 [--json]" >&2; exit 2 ;;
esac
A="${RECENZENT_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
[ -f "$A/org.yaml" ] || { echo "BŁĄD: brak $A/org.yaml" >&2; exit 2; }
command -v gh >/dev/null 2>&1 || { echo "BŁĄD: brak gh w PATH" >&2; exit 3; }

python3 -I - "$A" "${1:-}" <<'PY'
import json, os, pathlib, re, subprocess, sys

repo = pathlib.Path(sys.argv[1]); json_out = sys.argv[2] == "--json"
pomin = os.environ.get("RECENZENT_POMIN_TYTUL") or None
limit = os.environ.get("RECENZENT_LIMIT", "100")


def org_repo(p):
    """repo.github i repo.produkt z org.yaml bez PyYAML -> (github, [produkt…])."""
    github, produkt, w_repo = "", [], False
    for l in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^repo\s*:", l): w_repo = True; continue
        if w_repo and re.match(r"^\S", l): w_repo = False
        if not w_repo: continue
        m = re.match(r"^\s+(github|produkt)\s*:\s*(.*)$", l)
        if not m: continue
        v = m.group(2).split(" #", 1)[0].strip()
        if m.group(1) == "github":
            github = v.strip("\"'")
        else:
            v = v[:v.index("]") + 1] if v.startswith("[") and "]" in v else v
            produkt = [x.strip().strip("\"'") for x in v.strip("[]").split(",") if x.strip().strip("\"'")]
    return github, produkt


github, produkt = org_repo(repo / "org.yaml")
owner = github.split("/")[0] if "/" in github else ""
pelne = lambda r: r if "/" in r else (owner + "/" + r if owner else r)
repa = list(dict.fromkeys([pelne(r) for r in produkt] + ([github] if github else [])))
if not repa or any(r.startswith("OWNER/") for r in repa):
    print("BŁĄD: org.yaml → repo.github / repo.produkt niewypełnione (OWNER/…)", file=sys.stderr); sys.exit(2)
nazwa = lambda r: r.rstrip("/").split("/")[-1]
pierwsze = nazwa(repa[0])
try:
    recenzje = json.loads((repo / "recenzent" / "stan.json").read_text(encoding="utf-8")).get("recenzje") or {}
except (OSError, ValueError) as e:
    print("BŁĄD: recenzent/stan.json – %s" % e, file=sys.stderr); sys.exit(2)


def klucze(r, n):
    nz = nazwa(r)
    return [str(n)] if nz == pierwsze else ["%s#%s" % (nz, n), "%s/%s" % (nz, n), "%s-%s" % (nz, n)]


otwarte, ok, bez, bledy = 0, [], [], []
for r in repa:
    try:
        p = subprocess.run(["gh", "pr", "list", "-R", r, "--state", "open", "--limit", limit, "--json", "number,headRefOid,isDraft,title"],
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError((p.stderr.strip().splitlines() or ["kod %d" % p.returncode])[-1][:160])
        prs = json.loads(p.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as e:
        bledy.append({"repo": r, "komunikat": str(e)}); continue
    for pr in prs:
        tytul = pr.get("title") or ""
        if pr.get("isDraft") or (pomin and re.search(pomin, tytul)): continue
        otwarte += 1
        head = (pr.get("headRefOid") or "").lower()
        k = klucze(r, pr["number"])
        rec = next((recenzje[x] for x in k if isinstance(recenzje.get(x), dict)), None)
        sha = str((rec or {}).get("sha") or "").lower()
        wynik = str((rec or {}).get("wynik") or (rec or {}).get("werdykt") or "")
        if rec and len(sha) >= 7 and head.startswith(sha):
            ok.append((k[0], wynik)); continue
        bez.append({"klucz": k[0], "repo": r, "numer": pr["number"], "head": head[:7], "w_stanie": sha[:7] or "-",
                    "powod": "bez werdyktu" if not rec else "werdykt dla starego SHA %s (%s)" % (sha[:7] or "?", wynik or "?"), "tytul": tytul[:80]})

linia = "PR otwarte: %d, z werdyktem dla head: %d, bez: %d" % (otwarte, len(ok), len(bez)) + (" (" + ", ".join(b["klucz"] for b in bez) + ")" if bez else "")
if json_out:
    print(json.dumps({"linia": linia, "otwarte": otwarte, "z_werdyktem": len(ok), "zmiany_dla_head": [k for k, w in ok if w.upper() == "ZMIANY"],
                      "bez": bez, "bledy": bledy, "repozytoria": repa}, ensure_ascii=False, indent=1))
else:
    print(linia)
    for b in bez:
        print("  DO PRACY %s head %s (w stan.json: %s – %s) – %s" % (b["klucz"], b["head"], b["w_stanie"], b["powod"], b["tytul"]))
    for k, w in ok:
        if w.upper() == "ZMIANY": print("  CZEKA NA AUTORA %s – werdykt ZMIANY dla aktualnego head" % k)
    for e in bledy:
        print("  BŁĄD źródła %s: %s (w kontrakcie: przeczytane: null + bledy)" % (e["repo"], e["komunikat"]))
sys.exit(3 if bledy else 1 if bez else 0)
PY
