#!/usr/bin/env bash
# Tworzy katalog agenta z biblioteki ról:  scripts/nowy-agent.sh <rola> [<nazwa-katalogu>]
# Wynik: <katalog>/agent.md (szablon + opis roli), dziennik.md, stan.json, backlog.md, wiedza/podrecznik.md,
#        analizy/, szkice/, przebiegi/<katalog>/, zlecenia/<katalog>.md oraz startowe rejestry roli z role/szablony/<rola>/
#        (kopiowane rekurencyjnie, bez nadpisywania istniejących plików; znacznik {{rola}} → nazwa katalogu). Test: scripts/test-nowy-agent.sh.
# Nie tworzy zadania zaplanowanego – to robi CEO/operator (flota/generuj.py --lista --konto A --tylko <agent>).
set -eu
rola=${1:?Użycie: $0 <rola> [katalog]}; kat=${2:-$rola}
repo=$(cd "$(dirname "$0")/.." && pwd); cd "$repo"
[ -f "role/$rola.md" ] || { echo "Brak roli role/$rola.md (dostępne: $(ls role | grep -v '^_' | sed 's/\.md$//' | tr '\n' ' '))" >&2; exit 2; }
[ -e "$kat/agent.md" ] && { echo "Agent $kat już istnieje" >&2; exit 1; }
nazwa=$(sed -n 's/^[[:space:]]*nazwa:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' org.yaml | head -n 1 | sed 's/[[:space:]]*$//')
dzien=$(sed -n 's/.*\*\*Pełny przegląd:\*\* \([a-z]*\).*/\1/p' "role/$rola.md")
mkdir -p "$kat/wiedza" "$kat/analizy" "$kat/szkice" "przebiegi/$kat" zlecenia
{ sed -e "s/{{rola}}/$kat/g" -e "s/{{org.nazwa}}/$nazwa/g" role/_szablon-agenta.md; echo; sed '1d' "role/$rola.md"; } > "$kat/agent.md"
sed "s/{{rola}}/$kat/g" role/_podrecznik-startowy.md > "$kat/wiedza/podrecznik.md"
printf '# Dziennik agenta %s\n\nNajnowsze na górze.\n' "$kat" > "$kat/dziennik.md"
printf '# Backlog pomysłów agenta %s\n\n| Pomysł | EV / uzasadnienie | Stan |\n|---|---|---|\n' "$kat" > "$kat/backlog.md"
extra=""; [ "$rola" = recenzent ] && extra=',\n  "recenzje": {}'   # strażnik czyta recenzent/stan.json → recenzje
printf '{\n  "ostatni_przebieg": null,\n  "ostatni_pelny": null,\n  "dzien_pelny": "%s",\n  "konto": null,\n  "kursory": {}%b\n}\n' "${dzien:-pn}" "$extra" > "$kat/stan.json"
[ -f "zlecenia/$kat.md" ] || printf '# Zlecenia dla agenta %s\n\nFormat: zlecenia/README.md. Najnowsze na górze.\n' "$kat" > "zlecenia/$kat.md"
touch "przebiegi/$kat/.gitkeep" "$kat/analizy/.gitkeep" "$kat/szkice/.gitkeep"
# Startowe rejestry roli (role/szablony/<rola>/**): kopia bez nadpisywania, z podmianą {{rola}} i {{org.nazwa}}.
if [ -d "role/szablony/$rola" ]; then
  n=0
  while IFS= read -r f; do
    cel="$kat/${f#./}"
    [ -e "$cel" ] && continue
    mkdir -p "$(dirname "$cel")"
    sed -e "s/{{rola}}/$kat/g" -e "s/{{org.nazwa}}/$nazwa/g" "role/szablony/$rola/${f#./}" > "$cel"
    n=$((n + 1))
  done < <(cd "role/szablony/$rola" && find . -type f | LC_ALL=C sort)
  echo "Rejestry startowe: $n plików z role/szablony/$rola/ → $kat/"
fi
[ "$rola" = recenzent ] && { mkdir -p "$kat/szablony" "$kat/recenzje" && cp -n role/_rubryka-recenzenta.md "$kat/szablony/rubryka.md"; }
case "$rola" in obsluga|recepcja|sprzedaz|marketing|inwestorzy|aplikacje|ochrona-danych)   # kontakt zewnętrzny / skrzynka: scenariusze ewaluacji od startu
  mkdir -p "ewaluacje/$kat" && cp -n ewaluacje/_startowe/*.md "ewaluacje/$kat/" && echo "Ewaluacje: ewaluacje/$kat/ (kontrola: python3 -I ewaluacje/sprawdz.py)" ;;
esac
echo "Utworzono agenta $kat z roli $rola. Dalej: wiersz w koordynacja-odstepy.tsv i flota/zadania.yaml, python3 flota/generuj.py."
