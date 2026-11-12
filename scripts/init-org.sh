#!/usr/bin/env bash
# Start nowej organizacji agentycznej jednym poleceniem (procesy/00-nowa-organizacja.md, etap 0 i 2).
#
#   scripts/init-org.sh --nazwa "Nowa Firma" --domena nowafirma.example --prefiks nf --github OWNER/nowafirma-agenci \
#                       --operator operator@nowafirma.example [--wlasciciel wlasciciel@nowafirma.example] [--strefa Europe/Warsaw] \
#                       --dziel-sie tak|nie [--runtime claude-routines|desktop-scheduled] [--bez-etykiet] [--bez-testow] [--tak]
#
# --dziel-sie jest OBOWIĄZKOWE i jest decyzją właściciela firmy (nie agenta): „tak” = flota zgłasza uogólnione ulepszenia
# mechanizmów do repozytorium szablonu (README, „Dzielenie się ulepszeniami”), „nie” = nic nie wychodzi. Wybór trafia do
# org.yaml i do decyzji startowej; można go zmienić później w org.yaml. Bez wyboru skrypt niczego nie zapisuje.
# Bez argumentów pyta w terminalu. Co robi:
#   1. wypełnia org.yaml;  2. wpisuje decyzję startową D-<dziś>-01 w decyzje.md;  3. tworzy agentów rdzenia (ceo, pm, recenzent);
#   4. zakłada etykiety Issues w repo GitHub (gh, jeśli zalogowany i podano --github);  5. generuje prompty i uruchamia testy;
#   6. wypisuje listę zadań do założenia (limit, scalanie, ceo, pm, recenzent) i następne kroki dla operatora.
# Niczego nie wysyła, nie płaci, nie tworzy zadań zaplanowanych ani Routines – to robi operator według wydruku.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd); cd "$repo"

NAZWA=""; DOMENA=""; PREFIKS=""; GITHUB=""; OPERATOR=""; WLASCICIEL=""; STREFA="Europe/Warsaw"; RUNTIME="claude-routines"
ETYKIETY=1; TAK=0; DZIEL=""; TESTY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --nazwa) NAZWA=$2; shift 2 ;;      --domena) DOMENA=$2; shift 2 ;;    --prefiks) PREFIKS=$2; shift 2 ;;
    --github) GITHUB=$2; shift 2 ;;    --operator) OPERATOR=$2; shift 2 ;; --wlasciciel) WLASCICIEL=$2; shift 2 ;;
    --strefa) STREFA=$2; shift 2 ;;    --runtime) RUNTIME=$2; shift 2 ;;   --bez-etykiet) ETYKIETY=0; shift ;;
    --tak) TAK=1; shift ;;         --dziel-sie) DZIEL=$2; shift 2 ;;
    --bez-testow) TESTY=0; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
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

# Dzielenie się ulepszeniami: jawny wybór właściciela, bez wartości domyślnej.
if [ -z "$DZIEL" ]; then
  if [ -t 0 ]; then
    cat <<'EOF'

== Dzielenie się ulepszeniami – decyzja właściciela firmy
 tak = flota co tydzień zgłasza do repozytorium szablonu uogólnione zmiany mechanizmów (skrypty, hooki, skille, procesy, role)
       i sprawdzone reguły, po przejściu bramki anonimizacji. Zgłoszenie jest Issue w repozytorium szablonu – jeśli jest ono
       publiczne, widzi je każdy, razem z nazwą konta GitHub. Wysłana treść jest udostępniana na licencji szablonu i nie da
       się tego cofnąć dla treści już wysłanej. Podgląd przed wysyłką: python3 -I scripts/propozycje.py zbierz
 nie = nic nie wychodzi z tego repozytorium.
 Wybór można zmienić później w org.yaml (repo.dziel_sie_ulepszeniami). Szczegóły: README, „Dzielenie się ulepszeniami”.
EOF
    read -r -p "Dzielić się ulepszeniami? [tak/nie]: " DZIEL
  else
    echo "Brak --dziel-sie tak|nie. To decyzja właściciela firmy – zapytaj go i podaj jego odpowiedź (opis: $0 --help)." >&2; exit 2
  fi
fi
case "$DZIEL" in tak|nie) ;; *) echo "Zła wartość --dziel-sie: „${DZIEL}” (dozwolone: tak, nie). Niczego nie zapisano." >&2; exit 2 ;; esac

echo "== Organizacja: $NAZWA · $DOMENA · prefiks $PREFIKS · $GITHUB · operator $OPERATOR · $RUNTIME · dzielenie się ulepszeniami: $DZIEL"
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
DZIS=$(date +%Y%m%d); DATA=$(date +%Y-%m-%d)
python3 - "$DZIEL" "D-$DZIS-01" <<'PY'
import re, sys, pathlib
dziel, decyzja = sys.argv[1] == "tak", sys.argv[2]
p = pathlib.Path("org.yaml"); s = p.read_text()
s, n1 = re.subn(r"^(\s*dziel_sie_ulepszeniami:\s*)((?:true|false) *)", lambda m: m.group(1) + ("true" if dziel else "false").ljust(len(m.group(2))), s, count=1, flags=re.M)
s, n2 = re.subn(r'^(\s*dziel_sie_decyzja:\s*)"[^"]*"', lambda m: m.group(1) + '"%s"' % decyzja, s, count=1, flags=re.M)
if n1 != 1 or n2 != 1: sys.exit("brak klucza repo.dziel_sie_ulepszeniami albo repo.dziel_sie_decyzja w org.yaml")
p.write_text(s)
PY
echo "✓ org.yaml (dzielenie się ulepszeniami: $DZIEL, decyzja D-$DZIS-01)"

# 2. Decyzja startowa.
[ "$DZIEL" = tak ] && DZIEL_DEC="**włączone** – właściciel zgadza się, żeby flota zgłaszała uogólnione ulepszenia mechanizmów do repozytorium szablonu na warunkach z README („Dzielenie się ulepszeniami”)" \
  || DZIEL_DEC="**wyłączone** – nic nie wychodzi z repozytorium"
if [ -f decyzje/D-RRRRMMDD-01.md ]; then
  sed -e "s/D-RRRRMMDD-01/D-$DZIS-01/g" -e "s/^data: RRRR-MM-DD/data: $DATA/" -e "s/Uruchomienie organizacji$/Uruchomienie organizacji ($NAZWA)/" \
      -e "s/Słowa właściciela:\*\* „…”/Słowa właściciela:** „uruchomienie przez scripts\/init-org.sh ${DATA}”/" decyzje/D-RRRRMMDD-01.md > "decyzje/D-$DZIS-01.md" \
  && printf -- '- **Dzielenie się ulepszeniami:** %s (wybór `--dziel-sie %s` w `scripts/init-org.sh`, %s).\n' "$DZIEL_DEC" "$DZIEL" "$DATA" >> "decyzje/D-$DZIS-01.md" \
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
if [ $TESTY -eq 1 ]; then
  python3 -m unittest discover flota >/dev/null 2>&1 && echo "✓ testy floty" || { echo "✗ testy floty – uruchom: python3 -m unittest discover flota"; }
  python3 -m unittest discover moduly/straznik >/dev/null 2>&1 && echo "✓ testy strażnika" || echo "✗ testy strażnika"
  bash scripts/test-przebieg.sh >/dev/null 2>&1 && echo "✓ test blokady przebiegów" || echo "✗ test blokady przebiegów"
else echo "· testy pominięte (--bez-testow) – uruchom: bash scripts/testy.sh"; fi

# 6. Następne kroki.
cat <<EOF

== Zadania do założenia na koncie A (kolejność ważna; prompt = plik):
EOF
python3 flota/generuj.py --lista --konto A --tylko limit,scalanie,ceo,pm,recenzent | sed -n '/^{/p'
if [ "$(sed -n 's/^ *dziel_sie_ulepszeniami: *\([a-z]*\).*/\1/p' org.yaml | head -1)" = "true" ]; then
  DZIEL_KOM="Dzielenie się ulepszeniami z wydawcą szablonu jest WŁĄCZONE (tylko mechanizmy i sprawdzone reguły, przez bramkę anonimizacji – README).
    Decyzja właściciela: D-$DZIS-01 (org.yaml → repo.dziel_sie_decyzja). Podgląd: python3 -I scripts/propozycje.py zbierz. Wyłączenie: repo.dziel_sie_ulepszeniami: false."
else
  DZIEL_KOM="Dzielenie się ulepszeniami z wydawcą szablonu jest WYŁĄCZONE – nic nie wychodzi. Włączenie (README, „Dzielenie się ulepszeniami”):
    nowa decyzja właściciela w decyzje/, potem org.yaml → repo.dziel_sie_ulepszeniami: true i repo.dziel_sie_decyzja: \"D-…\"."
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
# Edycja publiczna (eksport ustawia adres repo wydawcy): prośba o zgłoszenie projektu – zasada współpracy, nie warunek licencji.
ZGLOS_PROJEKT="Gilbertus-master/firma-z-agentow"
if [ -n "$ZGLOS_PROJEKT" ]; then
  cat <<EOF
 7. Zgłoś swój projekt wydawcy / Register your project (zasada współpracy, nie warunek licencji / a collaboration rule, not a licence term):
    https://github.com/$ZGLOS_PROJEKT/issues/new?template=zgloszenie-projektu.md
    Uwagi i odkrycia / feedback and discoveries: README, „Jak wysyłać uwagi i odkrycia do wydawcy” / "How to send feedback and discoveries".
EOF
fi
