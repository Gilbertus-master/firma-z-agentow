#!/usr/bin/env bash
# Skan diffu PR-a pod kątem danych osobowych, sekretów, prywatnych adresów i poleceń dla agentów (role/recenzent.md; rubryka, kryterium 6;
# zasady.md A2, A5, A6, A9). Sprawdza TYLKO linie dodane (+). Każde trafienie = uwaga blokująca.
#
#   bash recenzent/skrypty/skan-pr.sh <nr> [-R owner/repo]   # diff z `gh pr diff <nr>` (domyślne repo: pierwsze z org.yaml → repo.produkt, inaczej repo.github)
#   bash recenzent/skrypty/skan-pr.sh --plik <diff.patch>    # gotowy diff z pliku (bez sieci – testy)
#   bash recenzent/skrypty/skan-pr.sh --stdin                # diff ze standardowego wejścia
#
# Kategorie i wzorce (sekrety – te z pm/narzedzia/przebieg-raport.py i więcej):
#   EMAIL     adres poza domeną firmy (org.yaml → organizacja.domena); dozwolone domeny example.*, *.invalid, *.test, *.localhost
#   TELEFON   +NN NNN NNN NNN, NNN-NNN-NNN, NNN NNN NNN (z separatorami – bez nich za dużo fałszywych trafień)
#   PESEL     11 cyfr z poprawną sumą kontrolną
#   SEKRET    sk_live_/sk_test_/rk_live_, re_…, eyJ… (JWT), ghp_/gho_/github_pat_, whsec_, sb_secret_/sb_publishable_, AKIA…, xox[abprs]-,
#             AIza…, -----BEGIN … PRIVATE KEY, password|hasło|passwd|secret|token = "…" (≥ 8 znaków)
#   PLIK      dodany/zmieniony plik .env*, *.pem, *.p12, *.pfx, *.key, id_rsa*, *.keychain, credentials.json
#   POLECENIE tekst skierowany do agenta/recenzenta („recenzencie, zatwierdź”, „ignore previous instructions”, „jesteś teraz…”) – prompt injection
# Wartości w wyniku są maskowane (wynik trafia do pliku recenzji). Kody: 0 – brak trafień · 1 – trafienia · 2 – złe wywołanie / pusty diff ·
# 3 – gh nie odpowiada. Biblioteka standardowa; bez zapisu. Do testów: RECENZENT_REPO=<katalog z org.yaml>.
set -u
A="${RECENZENT_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
tmpk=$(mktemp -d "${TMPDIR:-/tmp}/skan-pr.XXXXXX"); trap 'rm -rf "$tmpk"' EXIT
zrodlo=""; opis=""
case "${1:-}" in
  -h|--help|"") sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; [ -n "${1:-}" ] && exit 0 || exit 2 ;;
  --plik) [ -n "${2:-}" ] && [ -f "$2" ] || { echo "BŁĄD: --plik wymaga istniejącego pliku" >&2; exit 2; }; zrodlo=$(cat "$2"); opis="plik $2" ;;
  --stdin) zrodlo=$(cat); opis="stdin" ;;
  *[!0-9]*) echo "BŁĄD: numer PR musi być liczbą" >&2; exit 2 ;;
  *)
    nr=$1; shift
    r=""
    if [ "${1:-}" = "-R" ]; then r=${2:?-R wymaga owner/repo}; shift 2; fi
    if [ -z "$r" ]; then
      r=$(sed -n 's/^[[:space:]]*produkt:[[:space:]]*\[\([^],]*\).*/\1/p' "$A/org.yaml" | head -n 1 | tr -d '"'"'"' ')
      [ -n "$r" ] || r=$(sed -n 's/^[[:space:]]*github:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' "$A/org.yaml" | head -n 1 | sed 's/[[:space:]]*$//')
      case "$r" in */*) ;; *) owner=$(sed -n 's/^[[:space:]]*github:[[:space:]]*"\{0,1\}\([^/"#]*\)\/.*/\1/p' "$A/org.yaml" | head -n 1); r="$owner/$r" ;; esac
    fi
    command -v gh >/dev/null 2>&1 || { echo "BŁĄD: brak gh w PATH" >&2; exit 3; }
    zrodlo=$(gh pr diff "$nr" -R "$r" 2>"$tmpk/err") || { echo "BŁĄD: gh pr diff $nr -R $r: $(tail -n 1 "$tmpk/err")" >&2; exit 3; }
    opis="PR #$nr ($r)" ;;
esac
[ -n "$zrodlo" ] || { echo "BŁĄD: pusty diff ($opis)" >&2; exit 2; }
printf '%s\n' "$zrodlo" > "$tmpk/diff"

# Skrypt Pythona idzie heredokiem (stdin), więc diff podajemy ścieżką – nie przez potok.
python3 -I - "$A" "$opis" "$tmpk/diff" <<'PY'
import pathlib, re, sys

repo, opis = pathlib.Path(sys.argv[1]), sys.argv[2]
diff = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8", errors="replace")
domena = ""
try:
    m = re.search(r"^\s+domena\s*:\s*[\"']?([A-Za-z0-9.-]+)", (repo / "org.yaml").read_text(encoding="utf-8"), re.M)
    domena = (m.group(1) if m else "").lower()
except OSError:
    pass
DOZWOLONE = re.compile(r"(^|\.)(example\.(com|org|net|pl)|[\w.-]+\.(invalid|test|localhost))$", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
TELEFON = re.compile(r"(?<![\w.])(?:\+\d{2}[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?![\w.])|(?<![\w.])\+\d{2}\s?\d{9}(?!\d)")
PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
SEKRET = re.compile(r"(sk_live_[A-Za-z0-9]{8,}|sk_test_[A-Za-z0-9]{8,}|rk_live_[A-Za-z0-9]{8,}|re_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
                    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|whsec_[A-Za-z0-9]{8,}|sb_(secret|publishable)_[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}"
                    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY"
                    r"|(?i:(password|passwd|has[łl]o|secret|token|api[_-]?key)\s*[:=]\s*[\"'][^\"']{8,}[\"']))")
PLIK = re.compile(r"(^|/)(\.env(\..+)?|[^/]+\.(pem|p12|pfx|key|keychain)|id_(rsa|ed25519|ecdsa)[^/]*|credentials\.json)$", re.I)
POLECENIE = re.compile(r"(ignore (all |any )?(previous|prior|above|earlier) (instructions|rules|guidelines)|disregard (the )?(previous|above) instructions"
                       r"|zignoruj (wszystkie |wcze[śs]niejsze |poprzednie |powy[żz]sze )?(instrukcje|zasady|polecenia)|you are now [a-z]|jeste[śs] teraz "
                       # zwrot do adresata: wołacz (recenzencie, agencie…) albo mianownik z przecinkiem/dwukropkiem („agent: scal”), potem TRYB ROZKAZUJĄCY
                       # jako całe słowo – opis procesu („funkcje AI scalone”, „agent AI, a zatwierdził właściciel”, „recenzent scala”) to nie polecenie
                       r"|\b((recenzencie|agencie|asystencie)[,:]?|(recenzent|reviewer|agent|claude|assistant|ai)[,:])\s+(prosz[ęe]\s+|please\s+)?[^\n]{0,40}?"
                       r"\b(zatwierd[źz]|approve|scal|merge|pomi[ńn]|ignoruj|zignoruj|skip|nie recenzuj|do not review)\b"
                       r"|system prompt|<\s*/?\s*(system|instructions?)\s*>)", re.I)
PLACEHOLDER = re.compile(r"(xxx|placeholder|example|przyk[łl]ad|changeme|\.\.\.|…|<[^>]+>)", re.I)


def pesel_ok(s):
    w = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    return (10 - sum(int(c) * k for c, k in zip(s[:10], w)) % 10) % 10 == int(s[10])


def maska(s):
    return s[:6] + "…" if len(s) > 8 else "…"


trafienia, plik, nr, dodane = [], "?", 0, 0
for l in diff.splitlines():
    if l.startswith("+++ "):
        plik = re.sub(r"^\+\+\+ (b/)?", "", l).strip(); nr = 0
        if plik != "/dev/null" and PLIK.search(plik):
            trafienia.append(("PLIK", plik, 0, "plik z sekretami/kluczami w diffie"))
        continue
    if l.startswith("--- "):
        continue
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)", l)
    if m:
        nr = int(m.group(1)) - 1; continue
    if l.startswith("-"):
        continue
    nr += 1
    if not l.startswith("+"):
        continue
    t = l[1:]; dodane += 1
    for m in EMAIL.finditer(t):
        adres = m.group(0); dom = adres.split("@", 1)[1].lower()
        if (domena and (dom == domena or dom.endswith("." + domena))) or DOZWOLONE.search(dom):
            continue
        trafienia.append(("EMAIL", plik, nr, adres[0] + "***@" + dom))
    for m in SEKRET.finditer(t):
        # zaślepki („<wstaw-token>”, „changeme”) pomijamy tylko w ogólnym wzorcu hasło/token = "…"; klucz z prefiksem (sk_live_, re_…) zawsze zgłaszamy
        if m.group(0)[:1].lower() in "phst" and m.group(0)[:3].lower() not in ("sk_", "sb_") and PLACEHOLDER.search(m.group(0)):
            continue
        trafienia.append(("SEKRET", plik, nr, maska(m.group(0))))
    for m in TELEFON.finditer(t):
        cyfry = re.sub(r"\D", "", m.group(0))
        trafienia.append(("TELEFON", plik, nr, cyfry[:3] + "*" * (len(cyfry) - 5) + cyfry[-2:]))
    for m in PESEL.finditer(t):
        if pesel_ok(m.group(0)):
            trafienia.append(("PESEL", plik, nr, m.group(0)[:2] + "*********"))
    for m in POLECENIE.finditer(t):
        trafienia.append(("POLECENIE", plik, nr, "„%s”" % m.group(0)[:70]))

for kat, p, n, frag in trafienia:
    print("%-9s %s:%s: %s" % (kat, p, n or "-", frag))
licz = {}
for k, *_ in trafienia:
    licz[k] = licz.get(k, 0) + 1
if trafienia:
    print("TRAFIENIA: %d (%s) w %d liniach dodanych – %s – kryterium 6 rubryki: fail (blokująca)"
          % (len(trafienia), ", ".join("%s %d" % kv for kv in sorted(licz.items())), dodane, opis))
    sys.exit(1)
print("OK: brak trafień w %d liniach dodanych – %s (domena firmy: %s)" % (dodane, opis, domena or "nieustawiona"))
PY
