#!/usr/bin/env bash
# Instalacja strażnika floty jako agenta launchd na Macu (org.agenci.straznik, co 15 min) – alternatywa dla GitHub Actions.
#
#   moduly/straznik/instaluj.sh                # klon strażnika (jeśli brak) + plist w ~/Library/LaunchAgents + start
#   moduly/straznik/instaluj.sh --odinstaluj   # zatrzymuje i usuwa agenta (klon zostaje)
#
# STRAZNIK_REPO – klon roboczy strażnika (domyślnie ~/projekty/organizacja-straznik; NIE wspólny checkout agentów).
# STRAZNIK_URL  – adres repo organizacji do sklonowania (domyślnie origin checkoutu, z którego uruchamiasz ten skrypt).
set -euo pipefail

ETYKIETA=org.agenci.straznik
REPO=${STRAZNIK_REPO:-$HOME/projekty/organizacja-straznik}
TU=$(cd "$(dirname "$0")" && pwd)
URL=${STRAZNIK_URL:-$(git -C "$TU" remote get-url origin 2>/dev/null || true)}
PLIST=$HOME/Library/LaunchAgents/$ETYKIETA.plist
LOG=$HOME/Library/Logs/straznik-floty.log
DOMENA=gui/$(id -u)

case "${1:-}" in
  --odinstaluj)
    launchctl bootout "$DOMENA/$ETYKIETA" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Strażnik odinstalowany ($PLIST usunięty). Klon $REPO i log $LOG zostały – usuń ręcznie, jeśli trzeba."
    exit 0 ;;
  "") ;;
  *) echo "Użycie: $0 [--odinstaluj]" >&2; exit 2 ;;
esac

if [ ! -d "$REPO/.git" ]; then
  [ -n "$URL" ] || { echo "BŁĄD: nie znam adresu repo organizacji – ustaw STRAZNIK_URL=https://github.com/<właściciel>/<repo>.git" >&2; exit 1; }
  echo "Klonuję $URL → $REPO"
  git clone -q "$URL" "$REPO"
else
  git -C "$REPO" pull --no-rebase -q
fi
SZABLON=$REPO/moduly/straznik/straznik.plist.szablon
[ -f "$SZABLON" ] || { echo "BŁĄD: brak $SZABLON w klonie – czy moduł strażnika jest na gałęzi głównej repo?" >&2; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s#__REPO__#$REPO#g" -e "s#__HOME__#$HOME#g" "$SZABLON" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

launchctl bootout "$DOMENA/$ETYKIETA" 2>/dev/null || true
launchctl bootstrap "$DOMENA" "$PLIST"

cat <<INFO
Strażnik zainstalowany: $PLIST (co 15 min, start od razu).
Sprawdź:
  launchctl print $DOMENA/$ETYKIETA | grep -E 'state|last exit'
  tail -f $LOG
  cat $REPO/ceo/straznik.json
Próba bez skutków:  /usr/bin/python3 $REPO/moduly/straznik/straznik.py --sucho
Wyłączenie:         $REPO/moduly/straznik/instaluj.sh --odinstaluj
INFO
