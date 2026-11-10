#!/usr/bin/env bash
# Blokada przebiegu agenta (jeden przebieg na okienko, także przy zaległym uruchomieniu albo przeniesieniu floty) – koordynacja.md.
#
#   scripts/przebieg.sh start <agent> <konto>   # konto floty: litera z org.yaml → runtime.konto
#   scripts/przebieg.sh okienko <agent>         # tylko wypisuje numer okienka (bez sieci; do testów)
#
# Kody wyjścia:
#   0  – przebieg Twój: tag przebieg/<agent>/<okienko> wypchnięty, rób pracę
#   10 – w tym okienku przebieg już był albo trwa (tag istnieje) – zakończ jednym zdaniem, bez pracy i bez commita;
#        także BUDŻET POJEMNOŚCI: limit konta ≥ 85% i agent P3 albo ≥ 95% i agent P2 (tag nie powstaje)
#   1  – błąd (sieć, brak agenta w koordynacja-odstepy.tsv itp.) – zakończ i zgłoś problem w raporcie
#   2  – złe wywołanie
#
# Okienko liczone w czasie lokalnym strefy z org.yaml (organizacja.strefa; jak harmonogramy zadań, więc zmiana czasu
# letni/zimowy nie przesuwa granic):  okienko = floor((minuty_lokalne_od_epoki - poczatek) / odstep).
# odstep i poczatek (HH:MM, granica okienka – 30 min przed pierwszą godziną harmonogramu) z koordynacja-odstepy.tsv.
# Przy okazji usuwa z origin tagi tego agenta starsze niż 14 dni.
#
# Budżet pojemności: przed blokadą czyta `procent` z ~/.<prefiks>-limit-<konto>.json (zapisuje go
# zadanie <prefiks>-limit-<konto>; prefiks z org.yaml) i priorytet agenta z flota/zadania.yaml (pole priorytet przy katalog: <agent>).
# Brak pliku limitu, brak procentu albo brak agenta w manifeście = brak ograniczenia (zachowanie jak dotąd).
#
# Do testów: PRZEBIEG_REPO (katalog repo), PRZEBIEG_ODSTEPY (plik tsv), PRZEBIEG_TERAZ (sekundy epoki),
#            PRZEBIEG_LIMIT_PLIK (plik limitu), PRZEBIEG_ZADANIA (manifest).

set -u

uzycie() { echo "Użycie: $0 start <agent> <konto A-Z>  |  $0 okienko <agent>" >&2; exit 2; }
tryb=${1:-}
case "$tryb $#" in
  "start 3") konto=$3; case "$konto" in [A-Z]) ;; *) uzycie ;; esac ;;
  "okienko 2") konto=- ;;
  *) uzycie ;;
esac
agent=$2
case "$agent" in *[!a-z0-9-]*|'') echo "Zła nazwa agenta: $agent" >&2; exit 2 ;; esac

katalog_skryptu=$(cd "$(dirname "$0")" && pwd)
repo=${PRZEBIEG_REPO:-$(dirname "$katalog_skryptu")}
odstepy=${PRZEBIEG_ODSTEPY:-$repo/koordynacja-odstepy.tsv}
teraz=${PRZEBIEG_TERAZ:-$(date +%s)}
# Strefa i prefiks z org.yaml (proste pola „klucz: "wartość"” – bez zależności od parsera YAML).
org_pole() { sed -n "s/^[[:space:]]*$1:[[:space:]]*\"\{0,1\}\([^\"#]*\)\"\{0,1\}.*/\1/p" "$repo/org.yaml" 2>/dev/null | head -n 1 | sed 's/[[:space:]]*$//'; }
STREFA=${PRZEBIEG_STREFA:-$(org_pole strefa)}; STREFA=${STREFA:-Europe/Warsaw}
PREFIKS=$(org_pole prefiks); PREFIKS=${PREFIKS:-org}

wiersz=$(awk -F'\t' -v a="$agent" '$1 == a { print $2 "\t" $3; exit }' "$odstepy" 2>/dev/null)
if [ -z "$wiersz" ]; then
  echo "BŁĄD: brak agenta '$agent' w $odstepy" >&2
  exit 1
fi
odstep=${wiersz%%$'\t'*}
poczatek=${wiersz#*$'\t'}
case "$odstep" in ''|*[!0-9]*) echo "BŁĄD: zły odstęp '$odstep' dla $agent" >&2; exit 1 ;; esac
case "$poczatek" in [0-2][0-9]:[0-5][0-9]) ;; *) echo "BŁĄD: zły początek '$poczatek' dla $agent" >&2; exit 1 ;; esac
[ "$odstep" -gt 0 ] || { echo "BŁĄD: odstęp 0" >&2; exit 1; }

# Przesunięcie strefy $STREFA w chwili $teraz (macOS: date -r, GNU: date -d @).
strefa=$(TZ=$STREFA date -r "$teraz" +%z 2>/dev/null || TZ=$STREFA date -d "@$teraz" +%z)
znak=${strefa:0:1}; gg=${strefa:1:2}; mm=${strefa:3:2}
przes=$(( 10#$gg * 60 + 10#$mm )); [ "$znak" = - ] && przes=$(( -przes ))
pocz_min=$(( 10#${poczatek%%:*} * 60 + 10#${poczatek##*:} ))
minuty=$(( teraz / 60 + przes ))
okienko=$(( (minuty - pocz_min) / odstep ))
czas=$(TZ=$STREFA date -r "$teraz" '+%Y-%m-%d %H:%M %Z' 2>/dev/null || TZ=$STREFA date -d "@$teraz" '+%Y-%m-%d %H:%M %Z')

[ "$tryb" = okienko ] && { echo "$okienko"; exit 0; }

# Budżet pojemności: przy wysokim zużyciu limitu konta pracują tylko ważniejsi agenci.
limit_plik=${PRZEBIEG_LIMIT_PLIK:-$HOME/.$PREFIKS-limit-$konto.json}
zadania=${PRZEBIEG_ZADANIA:-$(dirname "$katalog_skryptu")/flota/zadania.yaml}
procent=$(sed -n 's/.*"procent"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$limit_plik" 2>/dev/null | head -n 1)
priorytet=$(awk -v a="$agent" '
  /^- agent:/ { kat = "" }
  /^  katalog:/ { kat = $2 }
  /^  priorytet:/ { if (kat == a) { print $2; exit } }' "$zadania" 2>/dev/null)
if [ -n "$procent" ] && [ -n "$priorytet" ]; then
  prog=""
  case "$priorytet" in
    P3) prog=85 ;;
    P2) prog=95 ;;
  esac
  if [ -n "$prog" ] && [ "$procent" -ge "$prog" ]; then
    echo "BUDŻET: limit konta $konto $procent% ≥ $prog% – agent $agent ($priorytet) w tym okienku nie pracuje – koniec bez pracy."
    exit 10
  fi
fi

# Rola sesji dla hooka uprawnień (.claude/hooks/uprawnienia.py) – plik lokalny, w .gitignore.
printf '%s\n' "$agent" > "$repo/.agent-rola" 2>/dev/null || true

# Budżety efektywne z flota/budzety.tsv (generuje flota/generuj.py): przy rozliczeniu api – kwoty z manifestu; przy team –
# udział agenta w pojemności planu kont (wagi z manifestu × mnożnik). Brak pliku albo agenta → kwoty z manifestu (jak api).
budzety_tsv=${PRZEBIEG_BUDZETY:-$(dirname "$zadania")/budzety.tsv}
budzet_tsv() { awk -F'\t' -v a="$agent" -v k="$1" '$1 == a { print $k; exit }' "$budzety_tsv" 2>/dev/null; }
ROZLICZENIE=${PRZEBIEG_ROZLICZENIE:-$(sed -n 's/^# rozliczenie[[:space:]]*//p' "$budzety_tsv" 2>/dev/null | head -n 1)}
ROZLICZENIE=${ROZLICZENIE:-api}
[ "$ROZLICZENIE" = team ] && jedn="USD-ekw. (udział w pojemności konta floty)" || jedn="USD"

# Miękki budżet dzienny agenta z przebiegi/<agent>/koszty-<dziś>.jsonl (wrapper headless).
koszty_plik=${PRZEBIEG_KOSZTY:-$repo/przebiegi/$agent/koszty-$(TZ=$STREFA date -r "$teraz" +%Y-%m-%d 2>/dev/null || TZ=$STREFA date -d "@$teraz" +%Y-%m-%d).jsonl}
budzet_dzien=$(budzet_tsv 4)
[ -n "$budzet_dzien" ] || budzet_dzien=$(awk -v a="$agent" '
  /^- agent:/ { kat = "" }
  /^  katalog:/ { kat = $2 }
  /^  budzet_usd_dzien:/ { if (kat == a) { print $2; exit } }' "$zadania" 2>/dev/null)
[ -n "$budzet_dzien" ] || budzet_dzien=$(sed -n 's/^budzet_usd_dzien:[[:space:]]*//p' "$zadania" 2>/dev/null | head -n 1)
if [ -n "$budzet_dzien" ] && [ -f "$koszty_plik" ]; then
  wydano=$(sed -n 's/.*"koszt_usd":[[:space:]]*\([0-9.][0-9.]*\).*/\1/p' "$koszty_plik" | awk '{s+=$1} END {printf "%.2f", s}')
  if awk -v w="$wydano" -v b="$budzet_dzien" 'BEGIN { exit !(w+0 >= b+0) }'; then
    echo "BUDŻET-AGENTA: $agent wydał dziś $wydano ≥ $budzet_dzien $jedn – pracuj tylko w trybie ZDARZENIE (bez DZIENNY/PEŁNY)."
  fi
fi

# Dead-letter: przebiegi/dead-letter/<agent>.md (strażnik po K błędach z rzędu) – zadanie wstrzymane do przeglądu człowieka.
dl=${PRZEBIEG_DEADLETTER:-$repo/przebiegi/dead-letter/$agent.md}
if [ -f "$dl" ]; then
  echo "WSTRZYMANY: $agent jest w kolejce martwych przebiegów ($dl) – operator usuwa plik po przeglądzie. Koniec bez pracy."
  exit 10
fi

# Budżet miesięczny agenta (flota/zadania.yaml → budzet_usd_miesiac) z przebiegi/<agent>/koszty-<RRRR-MM>-*.jsonl: 80 % ostrzeżenie, 100 % koniec.
miesiac=$(TZ=$STREFA date -r "$teraz" +%Y-%m 2>/dev/null || TZ=$STREFA date -d "@$teraz" +%Y-%m)
budzet_mies=$(budzet_tsv 3)
[ -n "$budzet_mies" ] || budzet_mies=$(awk -v a="$agent" '
  /^- agent:/ { kat = "" }
  /^  katalog:/ { kat = $2 }
  /^  budzet_usd_miesiac:/ { if (kat == a) { print $2; exit } }' "$zadania" 2>/dev/null)
[ -n "$budzet_mies" ] || budzet_mies=$(sed -n 's/^budzet_usd_miesiac:[[:space:]]*//p' "$zadania" 2>/dev/null | head -n 1)
koszty_kat=${PRZEBIEG_KOSZTY_KATALOG:-$repo/przebiegi/$agent}
if [ -n "$budzet_mies" ] && ls "$koszty_kat"/koszty-"$miesiac"-*.jsonl >/dev/null 2>&1; then
  wydano_m=$(cat "$koszty_kat"/koszty-"$miesiac"-*.jsonl | sed -n 's/.*"koszt_usd":[[:space:]]*\([0-9.][0-9.]*\).*/\1/p' | awk '{s+=$1} END {printf "%.2f", s}')
  if awk -v w="$wydano_m" -v b="$budzet_mies" 'BEGIN { exit !(w+0 >= b+0) }'; then
    if [ "$ROZLICZENIE" = team ]; then dalej="większy udział = wyższa waga w flota/zadania.yaml (CEO, w granicach pojemności konta floty) albo wyższa nadwyżka (decyzja właściciela)"; else dalej="podniesienie budżetu = decyzja właściciela"; fi
    echo "BUDŻET-MIESIĄCA: $agent wydał w $miesiac $wydano_m ≥ $budzet_mies $jedn – koniec bez pracy (CISZA); $dalej."
    exit 10
  elif awk -v w="$wydano_m" -v b="$budzet_mies" 'BEGIN { exit !(w+0 >= 0.8*(b+0)) }'; then
    echo "BUDŻET-MIESIĄCA 80 %: $agent wydał w $miesiac $wydano_m z $budzet_mies $jedn – tylko tryb ZDARZENIE, bez prac opcjonalnych."
  fi
fi

# Regulator tempa (scripts/regulator.py): z pliku limitu `tryb` i `odchylenie` (pp względem celu równego zużycia okna).
# „zwolnij” → P3 nie pracuje; „zwolnij” i odchylenie > +15 pp → także P2. Tryb starszy niż 2 h (`sprawdzono`) jest pomijany.
tryb_reg=$(sed -n 's/.*"tryb"[[:space:]]*:[[:space:]]*"\([a-z]*\)".*/\1/p' "$limit_plik" 2>/dev/null | head -n 1)
odchylenie=$(sed -n 's/.*"odchylenie"[[:space:]]*:[[:space:]]*\(-\{0,1\}[0-9][0-9.]*\).*/\1/p' "$limit_plik" 2>/dev/null | head -n 1)
spr=$(sed -n 's/.*"sprawdzono"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$limit_plik" 2>/dev/null | head -n 1)
spr_epoka=""
[ -n "$spr" ] && spr_epoka=$(python3 -c "import sys,datetime as d; print(int(d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')).timestamp()))" "$spr" 2>/dev/null)
if [ "$tryb_reg" = zwolnij ] && [ -n "$priorytet" ] && [ -n "$spr_epoka" ] && [ $(( teraz - spr_epoka )) -le 7200 ]; then
  hamuj=0
  case "$priorytet" in
    P3) hamuj=1 ;;
    P2) awk -v o="${odchylenie:-0}" 'BEGIN { exit !(o > 15) }' && hamuj=1 ;;
  esac
  if [ "$hamuj" = 1 ]; then
    echo "BUDŻET: regulator tempa – konto $konto w trybie zwolnij (odchylenie +${odchylenie#+} pp od celu) – agent $agent ($priorytet) w tym okienku nie pracuje – koniec bez pracy."
    exit 10
  fi
fi

tag="przebieg/$agent/$okienko"
git -C "$repo" fetch --quiet --no-tags origin 2>/dev/null || { echo "BŁĄD: git fetch nie działa (sieć?)" >&2; exit 1; }

# Tag adnotowany tylko lokalnie na chwilę – źródłem prawdy jest origin.
git -C "$repo" tag -f -a "$tag" -m "przebieg $agent
konto: $konto
czas: $czas
odstep_min: $odstep" HEAD >/dev/null 2>&1 || { echo "BŁĄD: nie da się utworzyć tagu $tag" >&2; exit 1; }
wynik=$(LC_ALL=C git -C "$repo" push --porcelain origin "refs/tags/$tag:refs/tags/$tag" 2>&1)
kod=$?
git -C "$repo" tag -d "$tag" >/dev/null 2>&1

if [ $kod -ne 0 ]; then
  if printf '%s' "$wynik" | grep -qE 'already exists|\[rejected\]'; then
    echo "ZAJĘTE: przebieg $agent w tym okienku (od $poczatek co $odstep min) już był albo trwa – koniec bez pracy."
    exit 10
  fi
  echo "BŁĄD: push tagu $tag nie powiódł się:" >&2
  printf '%s\n' "$wynik" >&2
  exit 1
fi

echo "OK: przebieg $agent, konto $konto, okienko $okienko ($czas)."

# Sprzątanie: tagi tego agenta starsze niż 14 dni (błędy nie zmieniają wyniku).
granica=$(( okienko - 14 * 1440 / odstep ))
stare=$(git -C "$repo" ls-remote --tags origin 2>/dev/null | awk '{print $2}' |
  sed -n "s#^refs/tags/przebieg/$agent/\([0-9-]*\)\$#\1#p" | awk -v g="$granica" '$1 < g')
for s in $stare; do
  git -C "$repo" push --quiet origin --delete "refs/tags/przebieg/$agent/$s" >/dev/null 2>&1 || true
done
exit 0
