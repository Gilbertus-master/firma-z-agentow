#!/usr/bin/env bash
# Test zapisu końca przebiegu (scripts/zapisz.sh): gołe repo + dwa klony A i B, wyścig zapisów, konflikty, cudze pliki.
# Uruchom: bash scripts/test-zapisz.sh   (bez sieci, wszystko w katalogu tymczasowym)
set -u
tu=$(cd "$(dirname "$0")" && pwd)
skrypt=$tu/zapisz.sh
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-zapisz.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
bledy=0
ok()  { echo "  ok   $1"; }
zle() { echo "  ŹLE  $1"; bledy=$((bledy + 1)); }
sprawdz() { if eval "$1"; then ok "$2"; else zle "$2"; fi; }
export ZAPISZ_ODSTEP=0 ZAPISZ_ROZRZUT=1

git init -q --bare "$tmp/origin.git"
git -C "$tmp/origin.git" symbolic-ref HEAD refs/heads/main
for k in A B; do
  git clone -q "$tmp/origin.git" "$tmp/$k" 2>/dev/null
  git -C "$tmp/$k" config user.email "test@example.invalid"
  git -C "$tmp/$k" config user.name "agent $k"
  git -C "$tmp/$k" config commit.gpgsign false
done
( cd "$tmp/A" && git checkout -q -b main && mkdir -p a b && echo start > wspolny.md && echo x > cudzy.txt \
  && git add . && git commit -q -m start && git push -q origin main )
( cd "$tmp/B" && git fetch -q origin && git checkout -q -b main origin/main && mkdir -p b )
zapisz() { # klon, reszta = argumenty zapisz.sh
  local k=$1; shift
  ( cd "$tmp/$k" && "$skrypt" "$@" ) >"$tmp/wyj" 2>"$tmp/err"
}
na_origin() { git -C "$tmp/origin.git" show "main:$1" 2>/dev/null; }

echo "1. Złe wywołanie – nigdy „wszystko”"
for s in . ./ .. ../x a/../b /etc/x -A ":(glob)*" "*" "a/*"; do
  zapisz A "a: x" "$s"; kod=$?
  if [ $kod = 2 ]; then ok "odmowa ścieżki '$s' → 2"; else zle "ścieżka '$s' → $kod (oczekiwano 2)"; fi
done
zapisz A "a: x"; sprawdz '[ $? = 2 ]' "brak ścieżek → 2"

echo "2. Commit tylko własnych ścieżek; cudze zmiany zostają nietknięte"
( cd "$tmp/A" && echo 1 > a/wynik.md && echo obce > obcy.txt && git add obcy.txt && echo zmiana > cudzy.txt )
zapisz A "a: wynik" a/; kod=$?
sprawdz '[ $kod = 0 ]' "zapis a/ → 0"
sprawdz '[ "$(na_origin a/wynik.md)" = 1 ]' "a/wynik.md na origin"
sprawdz '! na_origin obcy.txt >/dev/null' "obcy.txt (w indeksie) nie trafił do commita"
sprawdz '[ "$(na_origin cudzy.txt)" = x ]' "cudzy.txt (zmieniony w kopii) nie trafił do commita"
sprawdz '[ "$(cat "$tmp/A/cudzy.txt")" = zmiana ] && git -C "$tmp/A" diff --cached --name-only | grep -qx obcy.txt' \
        "cudze zmiany w kopii i indeksie zostały"
( cd "$tmp/A" && git rm -q --cached obcy.txt && rm -f obcy.txt && git checkout -q -- cudzy.txt )

echo "3. Klon w tyle: rebase przy czystej kopii, merge przy cudzych zmianach w kopii"
( cd "$tmp/B" && echo 2 > b/wynik.md )
zapisz B "b: wynik" b/; kod=$?
sprawdz '[ $kod = 0 ] && [ "$(na_origin b/wynik.md)" = 2 ] && [ "$(na_origin a/wynik.md)" = 1 ]' "B w tyle (czysto) → rebase i push, oba wyniki na origin"
sprawdz '[ "$(git -C "$tmp/origin.git" rev-list --merges main | wc -l | tr -d " ")" = 0 ]' "rebase – historia liniowa"
( cd "$tmp/A" && echo 3 > a/wynik.md && echo lokalne > cudzy.txt )
zapisz A "a: wynik 2" a/; kod=$?
sprawdz '[ $kod = 0 ] && [ "$(na_origin a/wynik.md)" = 3 ] && [ "$(na_origin b/wynik.md)" = 2 ]' "A w tyle z cudzą zmianą w kopii → merge i push"
sprawdz '[ "$(cat "$tmp/A/cudzy.txt")" = lokalne ]' "cudza zmiana w kopii A przetrwała merge"
( cd "$tmp/A" && git checkout -q -- cudzy.txt )

echo "4. Wyścig dwóch zapisów (równoległe przebiegi, dwie grupy concurrency)"
for i in 1 2 3; do
  ( cd "$tmp/A" && echo "a$i" > "a/w$i.md" ); ( cd "$tmp/B" && echo "b$i" > "b/w$i.md" )
  ( cd "$tmp/A" && "$skrypt" "a: $i" a/ >/dev/null 2>"$tmp/errA$i" ) & pa=$!
  ( cd "$tmp/B" && "$skrypt" "b: $i" b/ >/dev/null 2>"$tmp/errB$i" ) & pb=$!
  wait $pa; ka=$?; wait $pb; kb=$?
  sprawdz '[ $ka = 0 ] && [ $kb = 0 ]' "runda $i: oba zapisy → 0 (A=$ka, B=$kb)"
  sprawdz '[ "$(na_origin a/w$i.md)" = "a$i" ] && [ "$(na_origin b/w$i.md)" = "b$i" ]' "runda $i: oba pliki na origin"
done

echo "5. Konflikt we własnym pliku: kod 1, ślad, bez rebase w toku, origin nietknięty"
( cd "$tmp/A" && echo "wersja A" > wspolny.md ); zapisz A "a: wspólny" wspolny.md
glowa=$(git -C "$tmp/origin.git" rev-parse main)
( cd "$tmp/B" && echo "wersja B" > wspolny.md )
ZAPISZ_SLAD="$tmp/slad.log" zapisz B "b: wspólny" wspolny.md; kod=$?
sprawdz '[ $kod = 1 ]' "konflikt → 1"
sprawdz 'grep -q "konflikt" "$tmp/err" && grep -q "wspolny.md" "$tmp/slad.log"' "ślad na stderr i w ZAPISZ_SLAD"
sprawdz '[ ! -d "$(git -C "$tmp/B" rev-parse --git-path rebase-merge)" ] && [ ! -d "$(git -C "$tmp/B" rev-parse --git-path rebase-apply)" ]' \
        "rebase przerwany (nie wisi)"
sprawdz '[ "$(git -C "$tmp/origin.git" rev-parse main)" = "$glowa" ] && [ "$(na_origin wspolny.md)" = "wersja A" ]' "origin bez zmian"
sprawdz '[ "$(git -C "$tmp/B" log -1 --format=%s)" = "b: wspólny" ]' "commit B zostaje lokalnie"
( cd "$tmp/B" && git reset -q --hard origin/main 2>/dev/null; git fetch -q origin && git reset -q --hard origin/main )

echo "6. Znaczniki konfliktu we własnym pliku – odmowa przed commitem"
lt=$(printf '%7s' '' | tr ' ' '<'); gt=$(printf '%7s' '' | tr ' ' '>')
( cd "$tmp/A" && git pull -q --rebase origin main 2>/dev/null; printf 'x\n%s HEAD\ny\n%s main\n' "$lt" "$gt" > a/zly.md )
przed=$(git -C "$tmp/A" rev-parse HEAD)
zapisz A "a: zły" a/; kod=$?
sprawdz '[ $kod = 1 ] && grep -q "znaczniki konfliktu" "$tmp/err" && [ "$(git -C "$tmp/A" rev-parse HEAD)" = "$przed" ]' "znaczniki → 1, bez commita"
( cd "$tmp/A" && printf '%s\n' "Nagłówek" "=======" "a $lt b" > a/zly.md )
zapisz A "a: dobry" a/; sprawdz '[ $? = 0 ]' "podkreślenie nagłówka i znaczniki w środku linii – nie są konfliktem"

echo "7. Nic do zapisania i push nieudany"
zapisz A "a: nic" a/; sprawdz '[ $? = 0 ] && grep -q "BEZ ZMIAN" "$tmp/wyj"' "brak zmian → 0, BEZ ZMIAN"
( cd "$tmp/A" && echo 9 > a/w9.md && git remote set-url origin "$tmp/nie-ma.git" )
ZAPISZ_PROBY=2 zapisz A "a: offline" a/; kod=$?
sprawdz '[ $kod = 1 ] && grep -q "po 2 próbach" "$tmp/err"' "push niemożliwy → 1 po 2 próbach"
git -C "$tmp/A" remote set-url origin "$tmp/origin.git"

echo "8. Skrypt nigdy nie używa --force, stash, reset"
sprawdz '! grep -v "^\s*#" "$skrypt" | grep -Eq -- "--force|push -f|git stash|reset --hard|git clean"' "brak siłowych poleceń"

echo "9. Wejście z kontraktu przebiegu: scripts/przebieg.sh zapisz <agent> \"<co>\" <ścieżki>"
( cd "$tmp/A" && git pull -q --rebase origin main 2>/dev/null; echo k > a/koniec.md )
( cd "$tmp/A" && "$tu/przebieg.sh" zapisz pm "koniec przebiegu" a/ ) >/dev/null 2>&1; kod=$?
sprawdz '[ $kod = 0 ] && [ "$(git -C "$tmp/origin.git" log -1 --format=%s main)" = "pm: koniec przebiegu" ]' "przebieg.sh zapisz → commit „pm: …” na origin"
( cd "$tmp/A" && "$tu/przebieg.sh" zapisz "Zły Agent" x a/ ) >/dev/null 2>&1; sprawdz '[ $? = 2 ]' "zła nazwa agenta → 2"
( cd "$tmp/A" && "$tu/przebieg.sh" zapisz pm x ) >/dev/null 2>&1; sprawdz '[ $? = 2 ]' "bez ścieżek → 2"

echo "---"
[ $bledy -eq 0 ] && { echo "test-zapisz: OK"; exit 0; }
echo "test-zapisz: $bledy błędów"; exit 1
