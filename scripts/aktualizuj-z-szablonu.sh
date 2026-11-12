#!/usr/bin/env bash
# Aktualizacja repo spółki z szablonu organizacji agentycznej (procesy/05-wiele-spolek.md, sekcja 3).
#
#   scripts/aktualizuj-z-szablonu.sh [--sucho] [--url <URL | OWNER/repo>] [--galaz main] [--remote szablon] [--repo <katalog>]
#                                    [--kanal glowny|stabilny] [--pr]
#   --kanal stabilny – najnowsze wydanie szablonu (tag v*, wersja finalna wyżej niż -rc); glowny (domyślnie) – gałąź --galaz
#   --pr             – tryb agenta (zadanie aktualizacji, procesy/15-rozwoj-szablonu.md): gałąź agent/aktualizacje-<wersja>,
#                      scalenie, prompty z flota/generuj.py, testy, push i PR do gałęzi spółki (scala kolejka scalania po werdykcie
#                      recenzenta; pliki właściciela – zasady.md, .claude/ – tylko z DECYZJA). Konflikt → scalanie przerwane,
#                      powrót na gałąź spółki, kod 3 (zlecenie dla architekta). Zmienne testowe: AKTUALIZUJ_BEZ_PUSH, AKTUALIZUJ_BEZ_TESTOW.
#
# Co robi: 1. dodaje albo aktualizuje remote `szablon` (URL z --url albo z org.yaml → repo.szablon; `OWNER/repo` = GitHub);
#          2. pobiera gałąź szablonu i pokazuje `git diff --stat` zmian BEZ ścieżek lokalnych z `.szablon-lokalne`;  --sucho kończy tutaj;
#          3. wymaga czystego drzewa roboczego; `git merge --no-commit --no-ff`; dla ścieżek lokalnych przywraca wersję spółki
#             (`git checkout HEAD -- <plik>`), nowe pliki szablonu w ścieżkach lokalnych pomija i wypisuje;
#          4. bez konfliktów → commit „szablon: aktualizacja do <sha7>”; konflikt poza ścieżkami lokalnymi → scalanie zostaje w toku,
#             wypisuje pliki i instrukcję, kod 3.
# `.szablon-lokalne`: jedna ścieżka na linię (git pathspec); linia z `*` dostaje magię :(glob), `/` na końcu = cały katalog. Bez pliku – lista domyślna.
# Kody: 0 ok / już aktualne · 1 błąd git · 2 złe użycie, brak URL, brudne drzewo · 3 konflikty do rozwiązania. Nigdy stash, reset --hard, force.
# Test: scripts/test-aktualizuj.sh (dwa repo tymczasowe, bez sieci).
set -eu

SUCHO=0; URL=""; GALAZ="main"; REMOTE="szablon"; REPO=""; KANAL="glowny"; PR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sucho) SUCHO=1; shift ;;
    --url) URL=${2:?--url wymaga wartości}; shift 2 ;;
    --galaz) GALAZ=${2:?}; shift 2 ;;
    --remote) REMOTE=${2:?}; shift 2 ;;
    --repo) REPO=${2:?}; shift 2 ;;
    --kanal) KANAL=${2:?}; KANAL_Z_ARG=1; shift 2 ;;
    --pr) PR=1; shift ;;
    -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "Nieznany argument: $1" >&2; exit 2 ;;
  esac
done

blad() { echo "BŁĄD: $*" >&2; exit "${KOD:-1}"; }
[ -n "$REPO" ] && cd "$REPO"
repo=$(git rev-parse --show-toplevel 2>/dev/null) || KOD=2 blad "to nie jest repozytorium git (użyj --repo)"
cd "$repo"

# 1. URL szablonu
if [ -z "$URL" ] && [ -f org.yaml ]; then
  URL=$(sed -n 's/^[[:space:]]*szablon:[[:space:]]*"\{0,1\}\([^"#]*\)"\{0,1\}.*/\1/p' org.yaml | head -n 1 | sed 's/[[:space:]]*$//')
fi
[ -n "$URL" ] || KOD=2 blad "brak URL szablonu – podaj --url albo wpisz org.yaml → repo.szablon (OWNER/repo lub pełny URL)"
case "$URL" in
  *://*|git@*|/*|.*|~*) ;;
  */*) URL="https://github.com/$URL.git" ;;
  *) KOD=2 blad "niezrozumiały URL szablonu: $URL" ;;
esac
if git remote get-url "$REMOTE" >/dev/null 2>&1; then
  [ "$(git remote get-url "$REMOTE")" = "$URL" ] || git remote set-url "$REMOTE" "$URL"
else
  git remote add "$REMOTE" "$URL"
fi
if [ "$KANAL" = glowny ] && [ -z "${KANAL_Z_ARG:-}" ] && [ -f org.yaml ]; then   # domyślny kanał z org.yaml → repo.szablon_kanal
  k=$(sed -n 's/^[[:space:]]*szablon_kanal:[[:space:]]*"\{0,1\}\([a-z]*\)"\{0,1\}.*/\1/p' org.yaml | head -n 1); [ -n "$k" ] && KANAL=$k
fi
case "$KANAL" in glowny|stabilny) ;; *) KOD=2 blad "--kanal: glowny albo stabilny" ;; esac
if [ "$KANAL" = stabilny ]; then
  # najnowszy tag v* szablonu (bez importu tagów do repo spółki – spółka może mieć własne v1.0)
  wersja=$(git ls-remote --tags --refs "$REMOTE" 'v*' 2>/dev/null | awk '{sub("refs/tags/", "", $2); print $2}' | python3 -I -c '
import re, sys
def klucz(t):
    m = re.match(r"v(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-rc(\d+))?$", t)
    return None if not m else (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), 1 if m.group(4) is None else 0, int(m.group(4) or 0))
t = [x.strip() for x in sys.stdin if klucz(x.strip())]
print(max(t, key=klucz) if t else "")')
  [ -n "$wersja" ] || blad "kanał stabilny: szablon nie ma tagów v* ($URL)"
  git fetch --quiet "$REMOTE" "refs/tags/$wersja" || blad "nie udało się pobrać wydania $wersja z $URL"
  cel=$(git rev-parse FETCH_HEAD); cel_opis="$wersja"
else
  git fetch --quiet "$REMOTE" "$GALAZ" || blad "nie udało się pobrać $REMOTE/$GALAZ z $URL"
  cel="$REMOTE/$GALAZ"; cel_opis="$GALAZ"
fi

# 2. Ścieżki lokalne → pathspecs (do przywracania) i wykluczenia (do diff --stat)
lokalne=()
if [ -f .szablon-lokalne ]; then
  while IFS= read -r l; do
    l=${l%%#*}; l=$(printf '%s' "$l" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'); [ -n "$l" ] || continue
    lokalne+=("$l")
  done < .szablon-lokalne
else
  echo "UWAGA: brak .szablon-lokalne – używam listy domyślnej (org.yaml, uprawnienia.yaml, decyzje/, polityki/, zlecenia/, przebiegi/, katalogi agentów)." >&2
  lokalne=(org.yaml uprawnienia.yaml decyzje.md decyzje/ polityki/ zlecenia/ przebiegi/ koordynacja-odstepy.tsv flota/zadania.yaml
           '*/agent.md' '*/dziennik.md' '*/stan.json' '*/backlog.md' '*/wiedza/' '*/analizy/' '*/szkice/'
           ceo/scalanie/stan.json ceo/scalanie/dziennik.jsonl ceo/kontrole/wyniki.jsonl 'ewaluacje/[!_]*/' recenzent/szablony/
           .github/workflows/straznik.yml)
fi
pathspec() { # pathspec <ścieżka> [exclude]  → git pathspec z magią
  local p=$1 magia=""
  case "$p" in *\**) magia="glob"; case "$p" in */) p="${p}**" ;; esac ;; esac
  [ "${2:-}" = exclude ] && magia="${magia:+$magia,}exclude"
  if [ -n "$magia" ]; then printf ':(%s)%s' "$magia" "$p"; else printf '%s' "$p"; fi
}
spec=(); wyklucz=()
for l in "${lokalne[@]}"; do spec+=("$(pathspec "$l")"); wyklucz+=("$(pathspec "$l" exclude)"); done

# 3. Podgląd
if git merge-base --is-ancestor "$cel" HEAD 2>/dev/null; then
  echo "Już aktualne: $cel_opis ($(git rev-parse --short "$cel")) jest w historii HEAD."; exit 0
fi
baza=$(git merge-base HEAD "$cel" 2>/dev/null || true)
echo "== Szablon: $URL ($cel_opis) → $(git rev-parse --short "$cel")${baza:+, wspólna baza $(git rev-parse --short "$baza")}"
echo "== Zmiany szablonu względem HEAD (bez ścieżek lokalnych z .szablon-lokalne):"
stat=$(git diff --stat ${baza:-HEAD} "$cel" -- . "${wyklucz[@]}")
if [ -n "$stat" ]; then echo "$stat"; else echo "  (brak – szablon zmienia tylko ścieżki lokalne albo nic)"; fi
if [ $SUCHO = 1 ]; then echo "Na sucho (--sucho): nic nie scalono."; exit 0; fi

# 4. Scalanie
[ -z "$(git status --porcelain)" ] || KOD=2 blad "drzewo robocze nie jest czyste – commituj swoje zmiany (bez stash) i uruchom ponownie"
[ -f "$repo/.git/MERGE_HEAD" ] && KOD=2 blad "scalanie już w toku – dokończ (git commit) albo przerwij (git merge --abort)"
galaz_spolki=$(git rev-parse --abbrev-ref HEAD)
if [ $PR = 1 ]; then
  nowa="agent/aktualizacje-$(printf '%s' "$cel_opis" | tr -c 'A-Za-z0-9._-' '-')-$(git rev-parse --short "$cel")"
  if git show-ref --verify --quiet "refs/heads/$nowa" || git ls-remote --exit-code --heads origin "$nowa" >/dev/null 2>&1; then
    echo "Gałąź $nowa już istnieje – aktualizacja do $cel_opis jest w toku (PR); nic nie robię."; exit 0
  fi
  git checkout --quiet -b "$nowa"
fi
unrelated=""; [ -z "$baza" ] && unrelated="--allow-unrelated-histories" && echo "UWAGA: brak wspólnej historii – scalanie z --allow-unrelated-histories."
set +e
wyj=$(git merge --no-commit --no-ff $unrelated "$cel" 2>&1); kod=$?
set -e
if [ ! -f "$repo/.git/MERGE_HEAD" ]; then
  [ $kod = 0 ] && { echo "Nic do scalenia."; exit 0; }
  blad "scalanie nie wystartowało: $wyj"
fi

# 5. Ścieżki lokalne: przywróć wersję spółki; nowe pliki szablonu w tych ścieżkach pomiń
pominiete=(); przywrocone=0
if [ ${#spec[@]} -gt 0 ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if git cat-file -e "HEAD:$f" 2>/dev/null; then
      git checkout --quiet HEAD -- "$f"; przywrocone=$((przywrocone + 1))
    else
      git rm --quiet --cached -- "$f" >/dev/null 2>&1 || true; rm -f -- "$f"; pominiete+=("$f")
    fi
  done < <( { git diff --name-only --cached HEAD -- "${spec[@]}"; git diff --name-only --diff-filter=U -- "${spec[@]}"; } | LC_ALL=C sort -u)
fi

# 6. Konflikty poza ścieżkami lokalnymi?
konflikty=$(git diff --name-only --diff-filter=U)
sha7=$(git rev-parse --short "$cel")
if [ -n "$konflikty" ] && [ $PR = 1 ]; then
  echo "KONFLIKTY (poza ścieżkami lokalnymi) – tryb --pr przerywa scalanie i wraca na $galaz_spolki:"
  printf '  %s\n' $konflikty
  git merge --abort; git checkout --quiet "$galaz_spolki"; git branch -q -D "$nowa"
  echo "Dalej: zlecenie dla architekta – ręczna aktualizacja do $cel_opis (scripts/aktualizuj-z-szablonu.sh --kanal $KANAL bez --pr)."
  exit 3
fi
if [ -n "$konflikty" ]; then
  echo "KONFLIKTY (poza ścieżkami lokalnymi) – scalanie zostaje w toku:"
  printf '  %s\n' $konflikty
  cat <<EOF
Rozwiąż konflikty w plikach wyżej (zostaw to, co ma obowiązywać w spółce; zmiany szablonu w zasady.md sekcja A wymagają decyzji właściciela D-…),
potem:   git add <pliki> && git commit -m "szablon: aktualizacja do $sha7"
albo przerwij:   git merge --abort
Po commicie: python3 flota/generuj.py && python3 flota/generuj.py --routines && testy z README.md.
EOF
  exit 3
fi

# 7. Commit
opis="Źródło: $URL ($cel_opis). Ścieżki lokalne zachowane wg .szablon-lokalne (przywrócone: $przywrocone)."
if [ ${#pominiete[@]} -gt 0 ]; then opis="$opis Pominięte nowe pliki szablonu w ścieżkach lokalnych: ${pominiete[*]}"; fi
git commit --quiet -m "szablon: aktualizacja do $cel_opis ($sha7)" -m "$opis"
echo "✓ scalono $cel_opis ($sha7); przywrócone pliki lokalne: $przywrocone"
if [ ${#pominiete[@]} -gt 0 ]; then
  echo "· pominięte nowe pliki szablonu w ścieżkach lokalnych (skopiuj ręcznie, jeśli potrzebne: git show $cel:<plik>):"
  printf '    %s\n' "${pominiete[@]}"
fi
if [ $PR = 0 ]; then
  echo "Dalej: python3 flota/generuj.py && python3 flota/generuj.py --routines && testy z README.md; PR do gałęzi głównej spółki → werdykt recenzenta."
  exit 0
fi

# 8. Tryb --pr: prompty, testy, push, PR, powrót na gałąź spółki
if [ -f flota/generuj.py ]; then
  python3 flota/generuj.py >/dev/null 2>&1 && python3 flota/generuj.py --routines >/dev/null 2>&1 || true
  if [ -n "$(git status --porcelain)" ]; then git add -A && git commit --quiet -m "szablon: prompty i budżety po aktualizacji do $cel_opis"; fi
fi
testy="pominięte (AKTUALIZUJ_BEZ_TESTOW)"
if [ -z "${AKTUALIZUJ_BEZ_TESTOW:-}" ] && [ -f scripts/testy.sh ]; then
  testy=$(bash scripts/testy.sh 2>&1 | grep -E "^Testy:" | tail -n 1); testy=${testy:-"brak wyniku"}
fi
zmiany=$(git diff --stat "$galaz_spolki" HEAD -- . | tail -n 1)
if [ -z "${AKTUALIZUJ_BEZ_PUSH:-}" ] && git remote get-url origin >/dev/null 2>&1; then
  git push --quiet -u origin "$nowa" || { git checkout --quiet "$galaz_spolki"; blad "push gałęzi $nowa nie powiódł się"; }
  gh pr create --base "$galaz_spolki" --head "$nowa" --title "szablon: aktualizacja do $cel_opis" --body "$(printf '%s\n' \
    "Automatyczna aktualizacja z szablonu (kanał $KANAL, wydanie $cel_opis, $sha7) – procesy/15-rozwoj-szablonu.md." \
    "" "- Zmiany: $zmiany" "- Testy: $testy" "- Ścieżki lokalne spółki zachowane (.szablon-lokalne): $przywrocone" \
    "" "Scala kolejka scalania po werdykcie recenzenta; zmiany w zasady.md i .claude/ wymagają decyzji właściciela (DECYZJA=D-…).")" \
    || echo "UWAGA: gh pr create nie powiódł się – gałąź $nowa jest wypchnięta, PR załóż ręcznie"
fi
git checkout --quiet "$galaz_spolki"
echo "PR: $nowa → $galaz_spolki · $zmiany · testy: $testy"
