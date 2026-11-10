#!/usr/bin/env bash
# Pełna suita testów szablonu – jedno polecenie dla człowieka, agenta i CI (.github/workflows/testy.yml).
#
#   bash scripts/testy.sh            # wszystko; kod 0 = zielono, 1 = co najmniej jeden test czerwony
#   bash scripts/testy.sh --lista    # wypisz testy i zakończ
#   bash scripts/testy.sh kpi model  # tylko testy, których nazwa zawiera podane słowo
#
# Nowy test = nowy wiersz w tablicy TESTY (nazwa|polecenie). Bez sieci, bez LLM, bez sekretów; repozytoria tymczasowe
# tworzą same testy. Wymaga: bash, git, python3 (biblioteka standardowa; PyYAML tylko tam, gdzie test sam go szuka).
set -u
cd "$(dirname "$0")/.." || exit 2

TESTY=(
  "flota: prompty zgodne z manifestem|python3 flota/generuj.py --sprawdz"
  "flota: manifest, generator, archiwizacja|python3 -m unittest discover flota"
  "straznik: kontrole bez LLM|python3 -m unittest discover moduly/straznik"
  "przebieg: blokada, okienka, CISZA|bash scripts/test-przebieg.sh"
  "propozycje: zgłoszenia ulepszeń do szablonu|python3 -m unittest discover -s scripts -p 'test_propozycje.py'"
  "koszt: pomiar kosztu przebiegu|python3 -m unittest discover -s scripts -p 'test_koszt.py'"
  "regulator: tempo i limit konta floty|python3 -m unittest discover -s scripts -p 'test_regulator.py'"
  "nowy-agent: rola z rejestrami startowymi|bash scripts/test-nowy-agent.sh"
  "aktualizuj: spółka z szablonu|bash scripts/test-aktualizuj.sh"
  "hook: uprawnienia, bramki, audyt|python3 -I .claude/hooks/test_uprawnienia.py"
  "scalanie: kolejka, blokada, bramka|python3 -m unittest discover -s scripts -p 'test_scalanie.py'"
  "decyzje: spójność rejestru|python3 -I scripts/decyzje-indeks.py --sprawdz"
  "ewaluacje: scenariusze ról|python3 -I ewaluacje/sprawdz.py"
  "ewaluacje: runner (bez modelu)|python3 -I ewaluacje/uruchom.py --tylko-sprawdz"
  "pm: backlog i rejestr sesji|python3 -m unittest discover pm/narzedzia"
  "recenzent: skan PR|bash recenzent/skrypty/test_skan.sh"
)

if [ "${1:-}" = "--lista" ]; then
  for t in "${TESTY[@]}"; do printf '%s\n    %s\n' "${t%%|*}" "${t#*|}"; done
  exit 0
fi

dziennik=$(mktemp "${TMPDIR:-/tmp}/testy.XXXXXX"); trap 'rm -f "$dziennik"' EXIT
ok=0; zle=0; pominiete=0; czerwone=()
for t in "${TESTY[@]}"; do
  nazwa="${t%%|*}"; polecenie="${t#*|}"
  if [ $# -gt 0 ]; then
    pasuje=0; for slowo in "$@"; do case "$nazwa" in *"$slowo"*) pasuje=1 ;; esac; done
    [ $pasuje -eq 1 ] || { pominiete=$((pominiete + 1)); continue; }
  fi
  start=$(date +%s)
  if bash -c "$polecenie" >"$dziennik" 2>&1; then
    ok=$((ok + 1)); printf 'OK    %-45s %3ss\n' "$nazwa" "$(( $(date +%s) - start ))"
  else
    zle=$((zle + 1)); czerwone+=("$nazwa"); printf 'BŁĄD  %-45s %3ss\n' "$nazwa" "$(( $(date +%s) - start ))"
    echo "      polecenie: $polecenie"; tail -n 40 "$dziennik" | sed 's/^/      | /'
  fi
done

echo "---"
echo "Testy: $ok OK, $zle BŁĄD$([ $pominiete -gt 0 ] && echo ", $pominiete pominiętych")"
[ $zle -eq 0 ] || { printf 'Czerwone: %s\n' "${czerwone[@]}"; exit 1; }
[ $ok -gt 0 ] || { echo "Żaden test nie pasuje do: $*" >&2; exit 2; }
