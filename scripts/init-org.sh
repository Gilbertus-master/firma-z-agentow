#!/usr/bin/env bash
# Start nowej organizacji agentycznej jednym poleceniem (procesy/00-nowa-organizacja.md, etap 0 i 2).
#
#   scripts/init-org.sh --nazwa "Nowa Firma" --domena nowafirma.example --prefiks nf --github OWNER/nowafirma-agenci \
#                       --operator operator@nowafirma.example [--wlasciciel wlasciciel@nowafirma.example] [--strefa Europe/Warsaw] \
#                       [--runtime claude-routines|desktop-scheduled] [--bez-etykiet] [--tak]
#
# Bez argumentów pyta w terminalu. Co robi:
#   1. wypełnia org.yaml;  2. wpisuje decyzję startową D-<dziś>-01 w decyzje.md;  3. tworzy agentów rdzenia (ceo, pm, recenzent);
#   4. zakłada etykiety Issues w repo GitHub (gh, jeśli zalogowany i podano --github);  5. generuje prompty i uruchamia testy;
#   6. wypisuje listę zadań do założenia (limit, scalanie, ceo, pm, recenzent) i następne kroki dla operatora.
# Niczego nie wysyła, nie płaci, nie tworzy zadań zaplanowanych ani Routines – to robi operator według wydruku.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd); cd "$repo"

NAZWA=""; DOMENA=""; PREFIKS=""; GITHUB=""; OPERATOR=""; WLASCICIEL=""; STREFA="Europe/Warsaw"; RUNTIME="claude-routines"
ETYKIETY=1; TAK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --nazwa) NAZWA=$2; shift 2 ;;      --domena) DOMENA=$2; shift 2 ;;    --prefiks) PREFIKS=$2; shift 2 ;;
    --github) GITHUB=$2; shift 2 ;;    --operator) OPERATOR=$2; shift 2 ;; --wlasciciel) WLASCICIEL=$2; shift 2 ;;
    --strefa) STREFA=$2; shift 2 ;;    --runtime) RUNTIME=$2; shift 2 ;;   --bez-etykiet) ETYKIETY=0; shift ;;
    --tak) TAK=1; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Nieznany argument: $1" >&2; exit 2 ;;
  esac
done

pytaj() { # pytaj <zmienna> <pytanie> <domyślna>
  local v=$1 q=$2 d=$3
  if [ -z "${!v}" ]; then
    if [ -t 0 ]; then read -r -p "$q${d:+ [$d]}: " odp; eval "$v=\${odp:-\$d}"; else eval "$v=\$d"; fi
  fi
}
pytaj NAZWA "Nazwa firmy" "Nowa Firma"
pytaj DOMENA "Domena adresów funkcyjnych" "example.com"
pytaj PREFIKS "Prefiks zadań (krótki, małe litery)" "$(echo "$NAZWA" | tr '[:upper:] ' '[:lower:]-' | sed 's/[^a-z0-9-]//g' | cut -c1-12)"
pytaj GITHUB "Repo GitHub organizacji (OWNER/nazwa, puste = później)" ""
pytaj OPERATOR "Adres firmowy operatora" "operator@$DOMENA"
pytaj WLASCICIEL "Adres firmowy właściciela" "$OPERATOR"
case "$PREFIKS" in *[!a-z0-9-]*|'') echo "Zły prefiks: $PREFIKS (małe litery, cyfry, myślnik)" >&2; exit 2 ;; esac
case "$RUNTIME" in claude-routines|desktop-scheduled|agent-sdk) ;; *) echo "Zły runtime: $RUNTIME" >&2; exit 2 ;; esac

echo "== Organizacja: $NAZWA · $DOMENA · prefiks $PREFIKS · $GITHUB · operator $OPERATOR · $RUNTIME"
if [ $TAK = 0 ] && [ -t 0 ]; then read -r -p "Zapisać? [t/N] " o; case "$o" in t|T|tak) ;; *) echo "Przerwano."; exit 1 ;; esac; fi

# 1. org.yaml – podmiana wartości przy znanych kluczach (zachowuje komentarze).
ustaw() { # ustaw <klucz> <wartość> [<n-te wystąpienie>]
  python3 - "$1" "$2" "${3:-1}" <<'PY'
import re, sys, pathlib
klucz, wart, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
p = pathlib.Path("org.yaml"); s = p.read_text()
wzor = re.compile(r'^(\s*%s:\s*)"[^"]*"' % re.escape(klucz), re.M)
licz = [0]
def zam(m):
    licz[0] += 1
    return m.group(1) + '"' + wart + '"' if licz[0] == n else m.group(0)
s2 = wzor.sub(zam, s)
if licz[0] < n: sys.exit("brak klucza %s (#%d) w org.yaml" % (klucz, n))
p.write_text(s2)
PY
}
ustaw nazwa "$NAZWA"; ustaw podmiot "$NAZWA"; ustaw domena "$DOMENA"; ustaw strefa "$STREFA"; ustaw prefiks "$PREFIKS"
ustaw organizacja "$repo"; [ -n "$GITHUB" ] && ustaw github "$GITHUB"
ustaw kontakt_firmowy "$WLASCICIEL" 1; ustaw kontakt_firmowy "$OPERATOR" 2; ustaw glowny "$RUNTIME"
[ "$RUNTIME" = agent-sdk ] && ustaw rozliczenie "api"   # własny serwer = klucz API: budżety USD obowiązują; Routines i aplikacja = team (jedno miejsce + nadwyżka)
echo "✓ org.yaml"

# 2. Decyzja startowa.
DZIS=$(date +%Y%m%d); DATA=$(date +%Y-%m-%d)
if [ -f decyzje/D-RRRRMMDD-01.md ]; then
  sed -e "s/D-RRRRMMDD-01/D-$DZIS-01/g" -e "s/^data: RRRR-MM-DD/data: $DATA/" -e "s/Uruchomienie organizacji$/Uruchomienie organizacji ($NAZWA)/" \
      -e "s/Słowa właściciela:\*\* „…”/Słowa właściciela:** „uruchomienie przez scripts\/init-org.sh $DATA”/" decyzje/D-RRRRMMDD-01.md > "decyzje/D-$DZIS-01.md" \
  && rm -f decyzje/D-RRRRMMDD-01.md && python3 -I scripts/decyzje-indeks.py >/dev/null && echo "✓ decyzje/D-$DZIS-01.md + indeks decyzje.md"
fi

# 3. Agenci rdzenia.
for a in ceo pm recenzent; do
  [ -e "$a/agent.md" ] && { echo "· agent $a już jest"; continue; }
  scripts/nowy-agent.sh "$a" >/dev/null && echo "✓ agent $a"
done

# 4. Etykiety Issues.
if [ $ETYKIETY = 1 ] && [ -n "$GITHUB" ] && command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  n=0
  while IFS=$'\t' read -r nazwa kolor opis; do
    [ "$nazwa" = nazwa ] && continue
    gh label create "$nazwa" -R "$GITHUB" --color "$kolor" --description "$opis" --force >/dev/null 2>&1 && n=$((n+1)) || true
  done < flota/etykiety.tsv
  echo "✓ etykiety Issues w $GITHUB: $n"
elif [ $ETYKIETY = 0 ]; then
  echo "· etykiety Issues pominięte (--bez-etykiet)"
else
  echo "· etykiety Issues pominięte (brak --github, gh albo logowania; później: pętla gh label create po flota/etykiety.tsv)"
fi

# 4b. Strażnik w Actions: włącz harmonogram (w szablonie wyłączony).
if grep -q "# STRAZNIK-CRON " .github/workflows/straznik.yml; then
  sed -i.bak 's/^  # STRAZNIK-CRON //' .github/workflows/straznik.yml && rm -f .github/workflows/straznik.yml.bak
  echo "✓ strażnik floty: harmonogram co 15 min włączony (.github/workflows/straznik.yml)"
fi

# 5. Prompty i testy.
python3 flota/generuj.py >/dev/null && echo "✓ prompty zadań (ceo/handoff/prompty/)"
python3 -m unittest discover flota >/dev/null 2>&1 && echo "✓ testy floty" || { echo "✗ testy floty – uruchom: python3 -m unittest discover flota"; }
python3 -m unittest discover moduly/straznik >/dev/null 2>&1 && echo "✓ testy strażnika" || echo "✗ testy strażnika"
bash scripts/test-przebieg.sh >/dev/null 2>&1 && echo "✓ test blokady przebiegów" || echo "✗ test blokady przebiegów"

# 6. Następne kroki.
cat <<EOF

== Zadania do założenia na koncie A (kolejność ważna; prompt = plik):
EOF
python3 flota/generuj.py --lista --konto A --tylko limit,scalanie,ceo,pm,recenzent | sed -n '/^{/p'
if [ "$(sed -n 's/^ *dziel_sie_ulepszeniami: *\([a-z]*\).*/\1/p' org.yaml | head -1)" = "true" ]; then
  DZIEL_KOM="Dzielenie się ulepszeniami z wydawcą szablonu jest WŁĄCZONE (tylko mechanizmy i sprawdzone reguły, przez bramkę anonimizacji – README).
    Wysyłka do wspólnego repo szablonu wymaga decyzji właściciela (org.yaml → repo.dziel_sie_decyzja). Wyłączenie: repo.dziel_sie_ulepszeniami: false."
else
  DZIEL_KOM="Dzielenie się ulepszeniami z wydawcą szablonu jest WYŁĄCZONE – nic nie wychodzi. Włączenie (README, „Dzielenie się ulepszeniami”):
    decyzja właściciela w decyzje/, potem org.yaml → repo.dziel_sie_ulepszeniami: true i repo.dziel_sie_decyzja: \"D-…\"."
fi
cat <<EOF

== Następne kroki (operator) – procesy/00-nowa-organizacja.md, etapy 1–2:
 1. git add -A && git commit -m "start organizacji $NAZWA" && git push   (repo musi być PRYWATNE)
 2. Sekrety Actions w repo: STRAZNIK_TOKEN (odczyt PR-ów, zapis tego repo), STRAZNIK_RESEND_KEY (opcjonalnie) – strażnik rusza sam co 15 min.
 3. Załóż zadania/Routines z listy wyżej (pierwsze: limit, drugie: scalanie) i uruchom każde raz ręcznie, żeby nie stało na pytaniu o zgodę.
 4. Skrzynki funkcyjne @$DOMENA, menedżer sekretów, konektory MCP – toolbelt/katalog.md; kontrola: toolbelt/sprawdz-dostepy.md.
 5. Progi (polityki/progi.yaml) i cele organizacji – CEO poprosi o brakujące w pierwszym przebiegu.
 6. $DZIEL_KOM
EOF
