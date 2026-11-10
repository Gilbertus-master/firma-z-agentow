#!/usr/bin/env bash
# Test scripts/aktualizuj-z-szablonu.sh na dwóch repo tymczasowych (szablon + spółka), bez sieci.
# Sprawdza: --sucho nic nie zmienia; scalenie zachowuje pliki lokalne z .szablon-lokalne (także katalogi agentów i globy),
# przyjmuje zmiany szablonu, pomija nowe pliki szablonu w ścieżkach lokalnych, commituje; ponowne uruchomienie = „już aktualne”;
# konflikt poza ścieżkami lokalnymi → kod 3 i scalanie w toku; brudne drzewo → kod 2; brak URL → kod 2.
set -u
tu=$(cd "$(dirname "$0")" && pwd)
skrypt=$tu/aktualizuj-z-szablonu.sh
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-aktualizuj.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
bledy=0
ok()  { echo "  ok   $1"; }
zle() { echo "  ŹLE  $1"; bledy=$((bledy + 1)); }
g() { git -C "$1" -c user.email=test@example.invalid -c user.name="test" "${@:2}"; }

# --- szablon v1
S=$tmp/szablon; mkdir -p "$S"; git init -q -b main "$S"
mkdir -p "$S/scripts" "$S/polityki" "$S/ceo/wiedza" "$S/role" "$S/procesy" "$S/decyzje"
printf 'zasada 1\nzasada 2\nzasada 3\n' > "$S/zasady.md"
printf 'organizacja:\n  nazwa: "Nowa Firma"\nrepo:\n  szablon: "%s"\n' "$S" > "$S/org.yaml"
printf 'czynnosci: {}\n' > "$S/uprawnienia.yaml"
printf '#!/bin/sh\necho stary\n' > "$S/scripts/x.sh"
printf '# Polityki\nwersja szablonu\n' > "$S/polityki/README.md"
printf '# Agent ceo\nlinia szablonu\n' > "$S/ceo/agent.md"
printf 'reguła startowa\n' > "$S/ceo/wiedza/podrecznik.md"
printf '# Rola ceo v1\n' > "$S/role/ceo.md"
printf '# Proces 00 v1\n' > "$S/procesy/00.md"
printf '# D-RRRRMMDD-01 szablon\n' > "$S/decyzje/D-RRRRMMDD-01.md"
cat > "$S/.szablon-lokalne" <<'EOF'
# lokalne
org.yaml
uprawnienia.yaml
.szablon-lokalne
decyzje/
polityki/
*/agent.md
*/wiedza/
EOF
g "$S" add -A >/dev/null; g "$S" commit -q -m "szablon v1"

# --- spółka: klon + zmiany lokalne
P=$tmp/spolka; git clone -q "$S" "$P"; g "$P" branch -m main 2>/dev/null || true
sed -i.bak 's/Nowa Firma/Spółka Testowa/' "$P/org.yaml" && rm -f "$P/org.yaml.bak"
printf 'zasada 1\nzasada 2\nzasada 3 – doprecyzowanie spółki\n' > "$P/zasady.md"
printf '# Agent ceo\nlinia szablonu\nlokalna linia spółki\n' > "$P/ceo/agent.md"
printf 'reguła startowa\nreguła spółki\n' > "$P/ceo/wiedza/podrecznik.md"
printf '# Polityki\nwersja spółki\n' > "$P/polityki/README.md"
printf '# D-20260101-01 start spółki\n' > "$P/decyzje/D-20260101-01.md"; git -C "$P" rm -q decyzje/D-RRRRMMDD-01.md
g "$P" add -A >/dev/null; g "$P" commit -q -m "spółka: konfiguracja"
spolka_head=$(git -C "$P" rev-parse HEAD)

# --- szablon v2: zmiany wszędzie
printf 'zasada 1 – NOWA WERSJA\nzasada 2\nzasada 3\n' > "$S/zasady.md"
printf 'organizacja:\n  nazwa: "Nowa Firma"   # komentarz v2\nrepo:\n  szablon: "%s"\n' "$S" > "$S/org.yaml"
printf '#!/bin/sh\necho nowy\n' > "$S/scripts/nowy.sh"
printf '#!/bin/sh\necho stary v2\n' > "$S/scripts/x.sh"
printf '# Polityki\nwersja szablonu v2\n' > "$S/polityki/README.md"
printf 'nowa polityka\n' > "$S/polityki/nowa.md"
printf '# Agent ceo\nlinia szablonu v2\n' > "$S/ceo/agent.md"
printf 'reguła startowa v2\n' > "$S/ceo/wiedza/podrecznik.md"
printf 'nowy plik wiedzy\n' > "$S/ceo/wiedza/nowy.md"
printf '# Rola ceo v2\n' > "$S/role/ceo.md"
printf '# D-RRRRMMDD-01 szablon v2\n' > "$S/decyzje/D-RRRRMMDD-01.md"
git -C "$S" rm -q procesy/00.md
g "$S" add -A >/dev/null; g "$S" commit -q -m "szablon v2"
v2=$(git -C "$S" rev-parse --short main)

echo "1. --sucho: pokazuje zmiany, niczego nie scala"
out=$(cd "$P" && bash "$skrypt" --sucho 2>&1); kod=$?
[ $kod = 0 ] && ok "kod 0" || zle "kod $kod: $out"
echo "$out" | grep -q "zasady.md" && ok "diff zawiera zasady.md" || zle "brak zasady.md w diff"
echo "$out" | grep -q "role/ceo.md" && ok "diff zawiera role/ceo.md" || zle "brak role/ceo.md w diff"
echo "$out" | grep -q "org.yaml" && zle "diff pokazuje lokalny org.yaml" || ok "org.yaml (lokalny) poza diff"
echo "$out" | grep -q "ceo/agent.md" && zle "diff pokazuje lokalny ceo/agent.md" || ok "*/agent.md (glob) poza diff"
[ "$(git -C "$P" rev-parse HEAD)" = "$spolka_head" ] && ok "HEAD bez zmian" || zle "HEAD zmieniony przy --sucho"
[ -f "$P/.git/MERGE_HEAD" ] && zle "MERGE_HEAD po --sucho" || ok "brak scalania w toku"
git -C "$P" remote get-url szablon >/dev/null 2>&1 && ok "remote szablon dodany" || zle "brak remote szablon"

echo "2. Scalenie z zachowaniem plików lokalnych"
out=$(cd "$P" && bash "$skrypt" 2>&1); kod=$?
[ $kod = 0 ] && ok "kod 0" || zle "kod $kod: $out"
git -C "$P" log -1 --format=%s | grep -q "szablon: aktualizacja do main ($v2)" && ok "commit scalenia z wersją i sha $v2" || zle "zły tytuł commita: $(git -C "$P" log -1 --format=%s)"
[ -z "$(git -C "$P" status --porcelain)" ] && ok "drzewo czyste po scaleniu" || zle "drzewo brudne: $(git -C "$P" status --porcelain)"
grep -q "NOWA WERSJA" "$P/zasady.md" && grep -q "doprecyzowanie spółki" "$P/zasady.md" && ok "zasady.md: zmiana szablonu + zmiana spółki" || zle "zasady.md: $(cat "$P/zasady.md")"
grep -q "Spółka Testowa" "$P/org.yaml" && ! grep -q "komentarz v2" "$P/org.yaml" && ok "org.yaml lokalny zachowany" || zle "org.yaml nadpisany"
grep -q "lokalna linia spółki" "$P/ceo/agent.md" && ! grep -q "v2" "$P/ceo/agent.md" && ok "ceo/agent.md lokalny (glob */agent.md)" || zle "ceo/agent.md nadpisany"
grep -q "reguła spółki" "$P/ceo/wiedza/podrecznik.md" && ! grep -q "v2" "$P/ceo/wiedza/podrecznik.md" && ok "*/wiedza/ lokalne" || zle "podręcznik nadpisany"
[ -e "$P/ceo/wiedza/nowy.md" ] && zle "nowy plik szablonu w */wiedza/ nie pominięty" || ok "nowy plik w */wiedza/ pominięty"
grep -q "wersja spółki" "$P/polityki/README.md" && ok "polityki/README.md lokalny" || zle "polityki/README.md nadpisany"
[ -e "$P/polityki/nowa.md" ] && zle "polityki/nowa.md (nowy w ścieżce lokalnej) nie pominięty" || ok "polityki/nowa.md pominięty"
echo "$out" | grep -q "polityki/nowa.md" && ok "pominięty plik wypisany" || zle "brak informacji o pominiętym pliku"
[ -e "$P/decyzje/D-RRRRMMDD-01.md" ] && zle "placeholder decyzji z szablonu wrócił" || ok "decyzje/ lokalne (placeholder nie wrócił)"
[ -f "$P/decyzje/D-20260101-01.md" ] && ok "decyzja spółki zostaje" || zle "decyzja spółki zniknęła"
grep -q "Rola ceo v2" "$P/role/ceo.md" && ok "role/ceo.md z szablonu" || zle "role/ceo.md bez zmiany szablonu"
[ -f "$P/scripts/nowy.sh" ] && grep -q "stary v2" "$P/scripts/x.sh" && ok "scripts/ z szablonu (nowy + zmieniony)" || zle "scripts/ bez zmian szablonu"
[ -e "$P/procesy/00.md" ] && zle "plik usunięty w szablonie został" || ok "usunięcie z szablonu zastosowane"
git -C "$P" log -1 --format=%b | grep -q "przywrócone: " && ok "opis commita z liczbą przywróconych" || zle "opis commita bez liczby"

echo "3. Ponowne uruchomienie – już aktualne"
out=$(cd "$P" && bash "$skrypt" 2>&1); kod=$?
[ $kod = 0 ] && echo "$out" | grep -q "Już aktualne" && ok "już aktualne, kod 0" || zle "kod $kod: $out"

echo "4. Konflikt poza ścieżkami lokalnymi → kod 3, scalanie w toku"
printf 'zasada 1 – NOWA WERSJA\nzasada 2\nzasada 3 – wersja szablonu v3\n' > "$S/zasady.md"
g "$S" add -A >/dev/null; g "$S" commit -q -m "szablon v3"
out=$(cd "$P" && bash "$skrypt" 2>&1); kod=$?
[ $kod = 3 ] && ok "kod 3" || zle "kod $kod (oczekiwano 3): $out"
[ -f "$P/.git/MERGE_HEAD" ] && ok "MERGE_HEAD istnieje" || zle "brak scalania w toku"
grep -q "<<<<<<<" "$P/zasady.md" && ok "znaczniki konfliktu w zasady.md" || zle "brak znaczników konfliktu"
echo "$out" | grep -q "git merge --abort" && ok "instrukcja rozwiązania" || zle "brak instrukcji"
git -C "$P" merge --abort && [ -z "$(git -C "$P" status --porcelain)" ] && ok "merge --abort przywraca czyste drzewo" || zle "abort nie przywrócił"

echo "5. Brudne drzewo → kod 2"
echo "x" >> "$P/zasady.md"
out=$(cd "$P" && bash "$skrypt" 2>&1); kod=$?
[ $kod = 2 ] && echo "$out" | grep -q "nie jest czyste" && ok "odmowa przy brudnym drzewie" || zle "kod $kod: $out"
git -C "$P" checkout -q -- zasady.md

echo "6. Brak URL → kod 2; --url OWNER/repo → adres GitHub"
B=$tmp/bez; mkdir -p "$B"; git init -q -b main "$B"; printf 'a\n' > "$B/a.md"; g "$B" add -A >/dev/null; g "$B" commit -q -m a
out=$(cd "$B" && bash "$skrypt" --sucho 2>&1); kod=$?
[ $kod = 2 ] && echo "$out" | grep -q "brak URL" && ok "brak URL → kod 2" || zle "kod $kod: $out"
out=$(cd "$B" && bash "$skrypt" --sucho --url OWNER/agentyczna-organizacja 2>&1); kod=$?
[ "$(git -C "$B" remote get-url szablon 2>/dev/null)" = "https://github.com/OWNER/agentyczna-organizacja.git" ] && ok "OWNER/repo → https://github.com/…" || zle "URL GitHub: $(git -C "$B" remote get-url szablon 2>/dev/null)"
[ $kod != 0 ] && ok "fetch z fikcyjnego URL kończy błędem (kod $kod)" || zle "fetch fikcyjnego URL się udał?"

echo "7. Kanał stabilny i tryb --pr (zadanie aktualizacji floty)"
S2=$tmp/szablon2; mkdir -p "$S2"; git init -q -b main "$S2"
printf 'zasada 1\n' > "$S2/zasady.md"; printf 'repo:\n  szablon: "%s"\n' "$S2" > "$S2/org.yaml"; printf 'org.yaml\n' > "$S2/.szablon-lokalne"
g "$S2" add -A >/dev/null; g "$S2" commit -q -m v1.0; g "$S2" tag v1.0
printf 'nowy skrypt\n' > "$S2/narzedzie.sh"; g "$S2" add -A >/dev/null; g "$S2" commit -q -m v1.1-rc1; g "$S2" tag v1.1-rc1
printf 'poprawka\n' > "$S2/poprawka.md"; g "$S2" add -A >/dev/null; g "$S2" commit -q -m v1.1; g "$S2" tag v1.1; v11=$(git -C "$S2" rev-parse --short HEAD)
printf 'niewydane\n' > "$S2/niewydane.md"; g "$S2" add -A >/dev/null; g "$S2" commit -q -m "main po v1.1"
P2=$tmp/spolka2; git clone -q --branch v1.0 "$S2" "$P2" 2>/dev/null; g "$P2" checkout -q -b main
printf 'repo:\n  szablon: "%s"\n  nazwa: Spółka 2\n' "$S2" > "$P2/org.yaml"; g "$P2" add -A >/dev/null; g "$P2" commit -q -m "spółka 2"
out=$(cd "$P2" && bash "$skrypt" --kanal stabilny --sucho 2>&1); kod=$?
[ $kod = 0 ] && echo "$out" | grep -q "(v1.1)" && ok "kanał stabilny wybiera v1.1 (finalna > rc, bez niewydanego main)" || zle "kanał stabilny: kod $kod, $out"
glowa=$(git -C "$P2" rev-parse HEAD)
out=$(cd "$P2" && AKTUALIZUJ_BEZ_PUSH=1 AKTUALIZUJ_BEZ_TESTOW=1 bash "$skrypt" --kanal stabilny --pr 2>&1); kod=$?
[ $kod = 0 ] && ok "--pr: kod 0" || zle "--pr: kod $kod, $out"
[ "$(git -C "$P2" rev-parse --abbrev-ref HEAD)" = main ] && [ "$(git -C "$P2" rev-parse HEAD)" = "$glowa" ] && ok "--pr: powrót na main, main nietknięty" || zle "--pr: zmieniono main"
gal=$(git -C "$P2" branch --list 'agent/aktualizacje-v1.1-*' | tr -d ' *')
[ -n "$gal" ] && git -C "$P2" cat-file -e "$gal:poprawka.md" 2>/dev/null && ! git -C "$P2" cat-file -e "$gal:niewydane.md" 2>/dev/null \
  && ok "--pr: gałąź $gal z wydaniem v1.1 bez zmian niewydanych" || zle "--pr: gałąź '$gal' bez v1.1"
git -C "$P2" log -1 --format=%s "$gal" 2>/dev/null | grep -q "aktualizacja do v1.1 ($v11)" && ok "--pr: commit z wersją v1.1" || zle "--pr: tytuł $(git -C "$P2" log -1 --format=%s "$gal" 2>/dev/null)"
out=$(cd "$P2" && AKTUALIZUJ_BEZ_PUSH=1 AKTUALIZUJ_BEZ_TESTOW=1 bash "$skrypt" --kanal stabilny --pr 2>&1); kod=$?
[ $kod = 0 ] && echo "$out" | grep -q "już istnieje" && ok "--pr: drugi raz – PR w toku, nic nie robi" || zle "--pr powtórka: kod $kod, $out"
printf 'zasada 1 – wersja spółki\n' > "$P2/zasady.md"; g "$P2" add -A >/dev/null; g "$P2" commit -q -m "spółka: zasada"
printf 'zasada 1 – v1.2\n' > "$S2/zasady.md"; g "$S2" add -A >/dev/null; g "$S2" commit -q -m v1.2; g "$S2" tag v1.2
out=$(cd "$P2" && AKTUALIZUJ_BEZ_PUSH=1 AKTUALIZUJ_BEZ_TESTOW=1 bash "$skrypt" --kanal stabilny --pr 2>&1); kod=$?
[ $kod = 3 ] && [ ! -f "$P2/.git/MERGE_HEAD" ] && [ "$(git -C "$P2" rev-parse --abbrev-ref HEAD)" = main ] && [ -z "$(git -C "$P2" status --porcelain)" ] \
  && ok "--pr: konflikt → kod 3, scalanie przerwane, czysty main" || zle "--pr konflikt: kod $kod, $out"
[ -z "$(git -C "$P2" branch --list 'agent/aktualizacje-v1.2-*')" ] && ok "--pr: gałąź konfliktu usunięta" || zle "--pr: została gałąź konfliktu"

echo
if [ $bledy -eq 0 ]; then echo "WSZYSTKO OK"; exit 0; else echo "BŁĘDY: $bledy"; exit 1; fi
