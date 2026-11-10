#!/usr/bin/env bash
# Test: scripts/init-org.sh wymaga jawnego wyboru --dziel-sie tak|nie i zapisuje go w org.yaml oraz w decyzji startowej.
# Pracuje na kopii repozytorium w katalogu tymczasowym; bez sieci (--bez-etykiet), bez LLM.
set -u
cd "$(dirname "$0")/.." || exit 2
T=$(mktemp -d "${TMPDIR:-/tmp}/init-org.XXXXXX"); trap 'rm -rf "$T"' EXIT
zle=0
blad() { echo "✗ $*"; zle=1; }
kopia() {  # kopia plików śledzonych i nowych (bez ignorowanych) jako świeże repo
  mkdir -p "$1"
  if [ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$PWD" ]; then
    git ls-files -co --exclude-standard -z | tar --null -T - -cf - 2>/dev/null | tar -xf - -C "$1"
  else tar --exclude .git -cf - . | tar -xf - -C "$1"; fi   # katalog bez repozytorium (np. świeży eksport)
  (cd "$1" && git init -q . && git add -A && git -c user.name=test -c user.email=test@firma-testowa.example commit -qm start)
}
ARG=(--nazwa "Firma Testowa" --domena firma-testowa.example --prefiks ft --github ktos/ft-agenci
     --operator operator@firma-testowa.example --bez-etykiet --bez-testow --tak)

kopia "$T/a"
(cd "$T/a" && bash scripts/init-org.sh "${ARG[@]}" </dev/null >/dev/null 2>"$T/err"); kod=$?
[ $kod -eq 2 ] || blad "brak --dziel-sie: kod $kod zamiast 2"
grep -q -- "--dziel-sie" "$T/err" || blad "brak --dziel-sie: komunikat nie wskazuje opcji"
[ -z "$(cd "$T/a" && git status --porcelain)" ] || blad "brak --dziel-sie: skrypt coś zapisał"
(cd "$T/a" && bash scripts/init-org.sh "${ARG[@]}" --dziel-sie moze </dev/null >/dev/null 2>&1); kod=$?
[ $kod -eq 2 ] || blad "zła wartość --dziel-sie: kod $kod zamiast 2"
[ -z "$(cd "$T/a" && git status --porcelain)" ] || blad "zła wartość --dziel-sie: skrypt coś zapisał"

for wybor in nie tak; do
  (cd "$T/a" && git reset -q --hard && git clean -fdq) && rm -rf "$T/$wybor" && mv "$T/a" "$T/$wybor"
  (cd "$T/$wybor" && bash scripts/init-org.sh "${ARG[@]}" --dziel-sie "$wybor" </dev/null >"$T/out" 2>&1) || { blad "--dziel-sie $wybor: skrypt zakończył się błędem"; tail -5 "$T/out"; continue; }
  [ "$wybor" = tak ] && wart=true slowo=włączone || wart=false slowo=wyłączone
  grep -Eq "^ +dziel_sie_ulepszeniami: $wart +#" "$T/$wybor/org.yaml" || blad "--dziel-sie $wybor: org.yaml nie ma dziel_sie_ulepszeniami: $wart"
  dec=$(ls "$T/$wybor"/decyzje/D-[0-9]*-01.md 2>/dev/null | head -1)
  [ -n "$dec" ] || { blad "--dziel-sie $wybor: brak decyzji startowej"; continue; }
  id=$(basename "$dec" .md)
  grep -q "dziel_sie_decyzja: \"$id\"" "$T/$wybor/org.yaml" || blad "--dziel-sie $wybor: org.yaml nie wskazuje decyzji $id"
  grep -q "Dzielenie się ulepszeniami:\*\* \*\*$slowo\*\*" "$dec" || blad "--dziel-sie $wybor: decyzja startowa nie zapisuje wyboru"
  mv "$T/$wybor" "$T/a"
done
[ $zle -eq 0 ] && echo "OK: init-org wymaga i zapisuje wybór dzielenia się ulepszeniami"
exit $zle
