#!/usr/bin/env bash
# Zapis końca przebiegu: commit WYŁĄCZNIE podanych ścieżek, dociągnięcie zmian innych i push z ponowieniami.
#
#   scripts/zapisz.sh "<agent>: <co>" <ścieżka> [<ścieżka> …]
#
# Kody: 0 – zapisane i wypchnięte (albo nic do zapisania), 1 – nie zapisano (konflikt we własnych plikach, znaczniki
# konfliktu, push nieudany po wszystkich próbach; lokalny commit zostaje, ślad na stderr), 2 – złe wywołanie.
#
# Zasady (zasady.md, sekcja Git; koordynacja wielu zapisujących – np. flota w CI z jednorazowym runnerem i strażnik):
#  - ścieżki podane z nazwy: bez `.`, `..`, ścieżek bezwzględnych, opcji i magii pathspec – nigdy „wszystko”;
#  - commit z pathspec (`git commit -- <ścieżki>`): cudze zmiany w indeksie i kopii roboczej nie wchodzą do commita;
#  - przed commitem: brak plików w stanie konfliktu i brak znaczników konfliktu w podanych ścieżkach;
#  - dociągnięcie: `pull --rebase` przy czystej kopii roboczej, `pull --no-rebase` (merge) gdy leżą tam cudze zmiany;
#    konflikt = `rebase --abort` / `merge --abort`, kod 1 – nigdy rozwiązywanie „na siłę”;
#  - push bez `--force`, do ZAPISZ_PROBY prób (domyślnie 5), odstęp ZAPISZ_ODSTEP × nr próby + losowo 0..ZAPISZ_ROZRZUT s.
# Zmienne: ZAPISZ_GALAZ (gałąź docelowa; domyślnie bieżąca – przy odłączonym HEAD wymagana), ZAPISZ_ZDALNE (origin),
#          ZAPISZ_SLAD (plik, do którego dopisywany jest ślad nieudanego zapisu – poza stderr).
set -u

slad() {
  printf 'ZAPISZ: %s\n' "$*" >&2
  [ -n "${ZAPISZ_SLAD:-}" ] && printf '%s ZAPISZ: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$ZAPISZ_SLAD" 2>/dev/null
  return 0
}

[ $# -ge 2 ] || { echo "Użycie: $0 \"<agent>: <co>\" <ścieżka> [<ścieżka> …]" >&2; exit 2; }
wiadomosc=$1; shift
[ -n "${wiadomosc// /}" ] || { echo "BŁĄD: pusta wiadomość commita" >&2; exit 2; }
for s in "$@"; do
  case "$s" in
    ''|.|./|..|../*|*/../*|*/..|/*|-*|:*|'*'*|*'*'|*'?'*|*'['*)
      echo "BŁĄD: podaj własne pliki lub katalogi z nazwy, nie '$s'" >&2; exit 2 ;;
  esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "BŁĄD: to nie jest repozytorium git" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)" || exit 2
zdalne=${ZAPISZ_ZDALNE:-origin}
galaz=${ZAPISZ_GALAZ:-$(git symbolic-ref --quiet --short HEAD 2>/dev/null)}
[ -n "$galaz" ] || { echo "BŁĄD: odłączony HEAD – podaj ZAPISZ_GALAZ" >&2; exit 2; }
proby=${ZAPISZ_PROBY:-5}; odstep=${ZAPISZ_ODSTEP:-2}; rozrzut=${ZAPISZ_ROZRZUT:-3}

# 1. Stan repo: żadnego niedokończonego scalenia ani plików w konflikcie.
if [ -n "$(git diff --name-only --diff-filter=U)" ] || [ -e "$(git rev-parse --git-path MERGE_HEAD)" ] \
   || [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
  slad "NIE ZAPISANO: repozytorium w trakcie scalenia/rebase albo z plikami w konflikcie – nic nie zmieniam"
  exit 1
fi

# 2. Znaczniki konfliktu w podanych ścieżkach: linia zaczyna się od 7 znaków <, > albo | (diff3), potem spacja albo koniec.
wzorzec='^(<{7}|>{7}|[|]{7})( |$)'
znaczniki=""
while IFS= read -r f; do
  [ -n "$f" ] && [ -f "$f" ] || continue
  LC_ALL=C grep -Iq . "$f" 2>/dev/null || continue                      # pliki binarne i puste pomijamy
  if LC_ALL=C grep -Eq "$wzorzec" "$f" 2>/dev/null; then znaczniki="$znaczniki $f"; fi
done <<LISTA
$(git ls-files --cached --others --exclude-standard -- "$@" 2>/dev/null | sort -u)
LISTA
if [ -n "$znaczniki" ]; then
  slad "NIE ZAPISANO: znaczniki konfliktu w:$znaczniki"
  exit 1
fi

# 3. Commit tylko podanych ścieżek (nowe pliki, zmiany i usunięcia w tych ścieżkach).
git add -A -- "$@" 2>/dev/null || { slad "NIE ZAPISANO: git add podanych ścieżek nie powiódł się"; exit 1; }
if git diff --cached --quiet -- "$@"; then
  echo "BEZ ZMIAN: w podanych ścieżkach nie ma nic do zapisania"
else
  git -c commit.gpgsign=false commit -q -m "$wiadomosc" -- "$@" || { slad "NIE ZAPISANO: commit nie powiódł się"; exit 1; }
fi

# 4. Nic do wypchnięcia? (lokalne commity, których nie ma na zdalnej gałęzi)
git fetch -q "$zdalne" "$galaz" 2>/dev/null
if git rev-parse -q --verify "refs/remotes/$zdalne/$galaz" >/dev/null && \
   [ -z "$(git rev-list "refs/remotes/$zdalne/$galaz..HEAD" 2>/dev/null)" ]; then
  echo "ZAPISANO: nic do wypchnięcia"
  exit 0
fi

# 5. Push z ponowieniami: dociągnij cudze zmiany (rebase albo merge), wypchnij bez --force.
czysto() { git diff --quiet && git diff --cached --quiet; }
proba=1
while [ "$proba" -le "$proby" ]; do
  if git fetch -q "$zdalne" "$galaz" 2>/dev/null && git rev-parse -q --verify "refs/remotes/$zdalne/$galaz" >/dev/null; then
    if czysto; then
      if ! git rebase -q "refs/remotes/$zdalne/$galaz" >/dev/null 2>&1; then
        pliki=$(git diff --name-only --diff-filter=U | tr '\n' ' ')
        git rebase --abort >/dev/null 2>&1
        slad "NIE ZAPISANO: konflikt przy rebase z $zdalne/$galaz w: ${pliki:-?} – rebase przerwany, commit $(git rev-parse --short HEAD) zostaje lokalnie"
        exit 1
      fi
    else
      if ! git -c commit.gpgsign=false merge -q --no-edit "refs/remotes/$zdalne/$galaz" >/dev/null 2>&1; then
        pliki=$(git diff --name-only --diff-filter=U | tr '\n' ' ')
        [ -e "$(git rev-parse --git-path MERGE_HEAD)" ] && git merge --abort >/dev/null 2>&1
        slad "NIE ZAPISANO: scalenie z $zdalne/$galaz niemożliwe (konflikt albo cudze niezapisane zmiany w tych samych plikach): ${pliki:-?} – commit $(git rev-parse --short HEAD) zostaje lokalnie"
        exit 1
      fi
    fi
  fi
  if git push -q "$zdalne" "HEAD:refs/heads/$galaz" 2>/dev/null; then
    echo "ZAPISANO: $(git rev-parse --short HEAD) → $zdalne/$galaz (próba $proba)"
    exit 0
  fi
  [ "$proba" -lt "$proby" ] && sleep $(( odstep * proba + (rozrzut > 0 ? RANDOM % (rozrzut + 1) : 0) ))
  proba=$((proba + 1))
done
slad "NIE ZAPISANO: push na $zdalne/$galaz nieudany po $proby próbach – commit $(git rev-parse --short HEAD) zostaje lokalnie"
exit 1
