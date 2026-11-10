#!/usr/bin/env bash
# Test scripts/nowy-agent.sh: kopia repo w katalogu tymczasowym, utworzenie agentów z rejestrami startowymi (role/szablony/),
# brak nadpisywania istniejących plików, podmiana {{rola}}, agent.md ≤ 200 linii. Uruchom: bash scripts/test-nowy-agent.sh
set -eu
tu=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-nowy-agent.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
bledy=0
ok()  { echo "  ok   $1"; }
zle() { echo "  ŹLE  $1"; bledy=$((bledy + 1)); }

# kopia tylko potrzebnych części repo (bez .git, bez katalogów agentów)
mkdir -p "$tmp/repo"
for p in role scripts org.yaml ewaluacje flota; do cp -R "$tu/$p" "$tmp/repo/"; done
cd "$tmp/repo"

echo "1. Rola z rejestrami w podkatalogach (architekt: adr/, tematy/, dlug.md)"
out=$(scripts/nowy-agent.sh architekt 2>&1) || { zle "nowy-agent.sh architekt: $out"; }
[ -f architekt/agent.md ] && ok "architekt/agent.md" || zle "brak architekt/agent.md"
[ -f architekt/adr/README.md ] && [ -f architekt/tematy/README.md ] && [ -f architekt/dlug.md ] && ok "rejestry adr/, tematy/ i dlug.md skopiowane" || zle "brak rejestrów architekta"
echo "$out" | grep -q "Rejestry startowe: 3 plików" && ok "komunikat o 3 plikach" || zle "komunikat: $out"
[ "$(wc -l < architekt/agent.md)" -le 200 ] && ok "agent.md ≤ 200 linii" || zle "agent.md > 200 linii"

echo "2. Bez nadpisywania istniejących plików"
if [ -d role/szablony/compliance ]; then
mkdir -p compliance && echo "moje" > compliance/luki.md
scripts/nowy-agent.sh compliance >/dev/null 2>&1 || zle "nowy-agent.sh compliance"
[ "$(cat compliance/luki.md)" = "moje" ] && ok "istniejący luki.md nietknięty" || zle "luki.md nadpisany"
for f in rejestr-wymogow.md kalendarz.md bramka-wydania.md; do [ -f "compliance/$f" ] && ok "compliance/$f" || zle "brak compliance/$f"; done
grep -q "G12" compliance/bramka-wydania.md && ok "bramka G1–G12" || zle "bramka bez G12"
else ok "pominięto – rola compliance spoza tej wersji"; fi

echo "3. Każda rola z role/szablony/ ma rolę w role/ i tworzy się bez błędu; brak {{rola}} po kopii"
for d in role/szablony/*/; do
  r=$(basename "$d")
  [ -f "role/$r.md" ] && ok "role/$r.md istnieje dla szablonów $r" || zle "role/szablony/$r bez role/$r.md"
  [ -e "$r/agent.md" ] || scripts/nowy-agent.sh "$r" >/dev/null 2>&1 || zle "nowy-agent.sh $r"
  if grep -rl "{{rola}}" "$r" >/dev/null 2>&1; then zle "$r: zostały znaczniki {{rola}}"; fi
done
n_szab=$(find role/szablony -mindepth 2 -type f | wc -l | tr -d ' ')
n_kopie=0
for d in role/szablony/*/; do r=$(basename "$d"); while IFS= read -r f; do [ -e "$r/${f#./}" ] && n_kopie=$((n_kopie + 1)); done < <(cd "$d" && find . -type f); done
[ "$n_szab" = "$n_kopie" ] && ok "wszystkie $n_szab pliki szablonów skopiowane" || zle "szablonów $n_szab, kopii $n_kopie"

echo "4. Nowe role w tsv i manifeście (aplikacje, lokalizacja, ochrona-danych)"
for r in aplikacje lokalizacja ochrona-danych; do
  [ -f "role/$r.md" ] || { ok "pominięto $r – rola spoza tej wersji"; continue; }
  grep -q "^$r	" "$tu/koordynacja-odstepy.tsv" && grep -q "^- agent: $r$" "$tu/flota/zadania.yaml" && ok "$r w tsv i manifeście" || zle "$r brak w tsv/manifeście"
done

echo
if [ $bledy -eq 0 ]; then echo "WSZYSTKO OK"; exit 0; else echo "BŁĘDY: $bledy"; exit 1; fi
