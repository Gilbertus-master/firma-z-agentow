#!/usr/bin/env bash
# Test blokady przebiegów (scripts/przebieg.sh): gołe repo + dwa klony udające konta A i B.
# Uruchom: scripts/test-przebieg.sh   (bez sieci, wszystko w katalogu tymczasowym)
set -u
tu=$(cd "$(dirname "$0")" && pwd)
skrypt=$tu/przebieg.sh
tsv=$(dirname "$tu")/koordynacja-odstepy.tsv
zadania_plik=$(dirname "$tu")/flota/zadania.yaml
# Wersja z obciętą flotą (eksport publiczny) testuje na migawce pełnego harmonogramu i priorytetów: scripts/testdane/flota-pelna/.
if [ -f "$tu/testdane/flota-pelna/zadania.yaml" ]; then
  tsv=$tu/testdane/flota-pelna/koordynacja-odstepy.tsv; zadania_plik=$tu/testdane/flota-pelna/zadania.yaml
  export PRZEBIEG_ZADANIA=$zadania_plik
fi
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-przebieg.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
bledy=0

ok()  { echo "  ok   $1"; }
zle() { echo "  ŹLE  $1"; bledy=$((bledy + 1)); }

# epoka dla czasu strefy z org.yaml "RRRR-MM-DD GG:MM"
epoka() { TZ=Europe/Warsaw date -j -f '%Y-%m-%d %H:%M' "$1" +%s 2>/dev/null || TZ=Europe/Warsaw date -d "$1" +%s; }

git init -q --bare "$tmp/origin.git"
for k in A B; do
  git clone -q "$tmp/origin.git" "$tmp/$k" 2>/dev/null
  git -C "$tmp/$k" config user.email "test@example.invalid"
  git -C "$tmp/$k" config user.name "konto $k"
done
git -C "$tmp/A" commit -q --allow-empty -m start && git -C "$tmp/A" push -q origin HEAD 2>/dev/null
git -C "$tmp/B" pull -q 2>/dev/null

start() { # konto agent "czas" oczekiwany_kod opis
  PRZEBIEG_REPO="$tmp/$1" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "$3") \
    PRZEBIEG_LIMIT_PLIK="${LIMIT:-$tmp/brak-limitu.json}" "$skrypt" start "$2" "$1" >/dev/null 2>&1
  local kod=$?
  if [ "$kod" = "$4" ]; then ok "$5 → $kod"; else zle "$5 → $kod (oczekiwano $4)"; fi
}

echo "1. Blokada między kontami"
start A ceo "2026-11-09 07:34" 0  "A ceo pn 7:34"
start B ceo "2026-11-09 07:36" 10 "B ceo to samo okienko (7:36)"
start B ceo "2026-11-09 07:58" 10 "B ceo zaległy przebieg w tym samym okienku 1 h (7:58)"
start B ceo "2026-11-09 08:33" 0  "B ceo następne okienko 1 h (8:33)"
start B ceo "2026-11-10 07:33" 0  "B ceo kolejny dzień 7:33"
start A ceo "2026-11-10 07:50" 10 "A ceo zaległy po przełączeniu konta (okienko 7–8)"
start A obsluga "2026-11-09 08:47" 0  "A obsługa 8:45"
start B obsluga "2026-11-09 10:48" 0  "B obsługa 10:45 (kolejne okienko)"
start A obsluga "2026-11-09 11:20" 10 "A obsługa zaległa 10:00 odpalona o 11:20"
start B prawny  "2026-11-09 09:31" 0  "B prawny – inny agent niezależny"
start A nieznany "2026-11-09 09:31" 1 "nieznany agent"

echo "2. Brak sieci / złe origin → 1"
git -C "$tmp/B" remote set-url origin "$tmp/brak.git"
start B ceo "2026-11-11 07:31" 1 "B ceo bez dostępu do origin"
git -C "$tmp/B" remote set-url origin "$tmp/origin.git"

echo "3. Sprzątanie tagów starszych niż 14 dni"
start A sprzedaz "2026-10-20 11:01" 0 "A sprzedaż 20.10"
start A sprzedaz "2026-11-09 11:02" 0 "A sprzedaż 9.11"
if git -C "$tmp/A" ls-remote --tags origin | grep -q "przebieg/sprzedaz/$(PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-10-20 11:01") "$skrypt" okienko sprzedaz)\$"; then
  zle "stary tag sprzedaży z 20.10 nie usunięty"
else ok "stary tag sprzedaży z 20.10 usunięty"; fi
git -C "$tmp/A" ls-remote --tags origin | grep -q "przebieg/ceo/" && ok "tagi ceo z 9–10.11 zostały" || zle "zniknęły świeże tagi ceo"
git -C "$tmp/A" tag -l 'przebieg/*' | grep -q . && zle "lokalne tagi zostały w klonie" || ok "brak lokalnych tagów w klonie"

echo "4. Każda godzina harmonogramu w innym okienku (zima CET i lato CEST, +20 min opóźnienia aplikacji)"
# agent | godziny – wyliczone z koordynacja-odstepy.tsv (godziny „*” = każde okienko: początek + 30 min)
harm=$(awk -F'\t' '!/^#/ && NF>=5 {
  if ($5 == "*") { split($3, p, ":"); s = p[1]*60 + p[2] + 30; l = "";
    for (k = 0; k < 1440 / $2; k++) { m = (s + k*$2) % 1440; l = l (l ? "," : "") sprintf("%02d:%02d", int(m/60), m%60) } }
  else { n = split($5, g, ","); l = ""; for (i = 1; i <= n; i++) { split(g[i], q, ":"); l = l (l ? "," : "") sprintf("%02d:%s", q[1], q[2]) } }
  print $1, l }' "$tsv")
okn() { PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "$2") "$skrypt" okienko "$1"; }
for dni in "2026-11-09 2026-11-10" "2026-07-06 2026-07-07"; do
  set -- $dni
  while read -r a godziny; do
    lista=""; dobrze=1
    for d in "$1" "$2"; do
      for g in ${godziny//,/ }; do
        w=$(okn "$a" "$d $g")
        hh=${g%%:*}; mm=${g##*:}; t=$((10#$hh * 60 + 10#$mm + 20))
        p=$(printf '%02d:%02d' $(( (t / 60) % 24 )) $((t % 60)))
        dd=$d; [ $t -ge 1440 ] && dd=$2   # przejście przez północ – tylko gdy d to pierwszy dzień
        [ "$(okn "$a" "$dd $p")" = "$w" ] || dobrze=0
        lista="$lista $w"
      done
    done
    powt=$(echo $lista | tr ' ' '\n' | sort | uniq -d)
    if [ -z "$powt" ] && [ $dobrze = 1 ]; then ok "$a ($1)"; else zle "$a ($1): okienka$lista; opóźnienie ok=$dobrze"; fi
  done <<< "$harm"
done

echo "5. Budżet pojemności (limit konta z ~/.<prefiks>-limit-<konto>.json, priorytety z flota/zadania.yaml)"
prio() { awk -v a="$1" '/^- agent:/{k=""} /^  katalog:/{k=$2} /^  priorytet:/{if(k==a){print $2; exit}}' "$zadania_plik"; }
[ "$(prio ceo)" = P1 ] && [ "$(prio prawny)" = P2 ] && [ "$(prio podatkowy)" = P2 ] && [ "$(prio wywiad)" = P3 ] && ok "priorytety z manifestu: ceo P1, prawny i podatkowy P2, wywiad P3" || zle "priorytety z manifestu"
limit() { printf '{"sprawdzono": "2026-11-12T10:00:00Z", "procent": %s, "handoff": null}\n' "$1" > "$tmp/limit.json"; }
LIMIT=$tmp/limit.json
limit 84
start A wywiad    "2026-11-12 06:00" 0  "84%: P3 pracuje"
limit 85
start A wywiad    "2026-11-13 06:00" 10 "85%: P3 kończy kodem 10"
start A podatkowy "2026-11-12 13:05" 0  "85%: P2 (podatkowy) pracuje"
start A prawny    "2026-11-12 12:35" 0  "85%: P2 pracuje"
start A ceo       "2026-11-12 13:35" 0  "85%: P1 pracuje"
git -C "$tmp/A" ls-remote --tags origin | grep -q "przebieg/wywiad/$(PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-11-13 06:00") "$skrypt" okienko wywiad)\$" \
  && zle "budżet: tag P3 powstał mimo odmowy" || ok "budżet: odmowa bez tagu (okienko wolne na później)"
limit 94
start A prawny    "2026-11-12 15:35" 0  "94%: P2 pracuje"
limit 95
start A prawny    "2026-11-12 18:35" 10 "95%: P2 kończy kodem 10"
start A wywiad    "2026-11-14 06:00" 10 "95%: P3 kończy kodem 10"
start A podatkowy "2026-11-12 16:05" 10 "95%: P2 (podatkowy) kończy kodem 10"
start A ceo       "2026-11-12 16:35" 0  "95%: P1 pracuje"
limit 100
start A recenzent "2026-11-12 16:46" 0  "100%: P1 (recenzent) pracuje"
start A nieznany  "2026-11-12 16:46" 1  "100%: nieznany agent – błąd jak dotąd"
limit 50
start A wywiad    "2026-11-15 06:00" 0  "50%: P3 pracuje"
echo '{"sprawdzono": null}' > "$tmp/limit.json"
start A wywiad    "2026-11-16 06:00" 0  "plik limitu bez procentu: bez ograniczeń"
LIMIT=
limit 99
PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-11-17 06:00") PRZEBIEG_LIMIT_PLIK="$tmp/limit.json" \
  PRZEBIEG_ZADANIA="$tmp/brak.yaml" "$skrypt" start wywiad A >/dev/null 2>&1
[ $? = 0 ] && ok "brak manifestu: bez ograniczeń → 0" || zle "brak manifestu powinien dać 0"
if PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-11-18 06:00") PRZEBIEG_LIMIT_PLIK="$tmp/limit.json" \
  "$skrypt" start wywiad A 2>/dev/null | grep -q '^BUDŻET: limit konta A 99%'; then ok "komunikat BUDŻET"; else zle "komunikat BUDŻET"; fi


echo "6. Miękki budżet dzienny agenta (przebiegi/<agent>/koszty-<dziś>.jsonl)"
koszty=$(mktemp)
printf '{"agent":"ceo","koszt_usd":25.5}\n{"agent":"ceo","koszt_usd":15}\n' > "$koszty"
out=$(cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-01 09:35") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_BUDZETY=/nonexistent PRZEBIEG_KOSZTY="$koszty" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 0 ] && echo "$out" | grep -q "BUDŻET-AGENTA" && ok "40.5 ≥ 40 USD: ostrzeżenie BUDŻET-AGENTA, kod 0" || zle "budżet dzienny: kod $kod, wyjście: $out"
printf '{"agent":"ceo","koszt_usd":1.25}\n' > "$koszty"
out=$(cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-02 10:35") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_BUDZETY=/nonexistent PRZEBIEG_KOSZTY="$koszty" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 0 ] && ! echo "$out" | grep -q "BUDŻET-AGENTA" && ok "1.25 USD: bez ostrzeżenia" || zle "budżet dzienny (mały): $out"
rm -f "$koszty"

echo "7. Budżet miesięczny agenta i dead-letter"
kk=$(mktemp -d); mies=$(TZ=Europe/Warsaw date -j -f '%Y-%m-%d %H:%M' "2026-12-03 09:35" +%Y-%m 2>/dev/null || date -d "2026-12-03" +%Y-%m)
printf '{"agent":"ceo","koszt_usd":30}\n{"agent":"ceo","koszt_usd":25}\n' > "$kk/koszty-$mies-01.jsonl"
out=$(cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-03 09:35") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_BUDZETY=/nonexistent PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG="$kk" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 10 ] && echo "$out" | grep -q "BUDŻET-MIESIĄCA" && ok "55 ≥ 50 USD/mies.: kod 10 bez pracy" || zle "budżet miesięczny 100%: kod $kod, $out"
bt=$(mktemp); printf '# rozliczenie\tteam\nkatalog\twaga_usd_miesiac\tmiesiac_usd\tdzien_usd\nceo\t50\t2441.60\t244.16\n' > "$bt"
out=$(cd "$tmp/A" && PRZEBIEG_BUDZETY="$bt" PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-03 09:50") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG="$kk" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 0 ] && ! echo "$out" | grep -q "BUDŻET-MIESIĄCA" && ok "team: 55 z 2441.60 USD-ekw. udziału w pojemności konta floty – pracuje" || zle "team (duży udział): kod $kod, $out"
printf '# rozliczenie\tteam\nkatalog\twaga_usd_miesiac\tmiesiac_usd\tdzien_usd\nceo\t50\t50.00\t5.00\n' > "$bt"
out=$(cd "$tmp/A" && PRZEBIEG_BUDZETY="$bt" PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-03 09:55") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG="$kk" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 10 ] && echo "$out" | grep -q "pojemności konta floty" && ok "team: udział wyczerpany – kod 10 i wskazówka o wagach" || zle "team (udział wyczerpany): kod $kod, $out"
rm -f "$bt"
printf '{"agent":"ceo","koszt_usd":42}\n' > "$kk/koszty-$mies-01.jsonl"
out=$(cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-03 10:35") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_BUDZETY=/nonexistent PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG="$kk" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 0 ] && echo "$out" | grep -q "80 %" && ok "42 z 50 USD: ostrzeżenie 80 %, kod 0" || zle "budżet miesięczny 80%: kod $kod, $out"
dlf=$(mktemp); echo "powód: 3 błędy" > "$dlf"
out=$(cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "2026-12-03 11:35") PRZEBIEG_LIMIT_PLIK=/nonexistent PRZEBIEG_BUDZETY=/nonexistent PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG="$kk" PRZEBIEG_DEADLETTER="$dlf" "$skrypt" start ceo A 2>&1); kod=$?
[ $kod = 10 ] && echo "$out" | grep -q "WSTRZYMANY" && ok "dead-letter: kod 10 bez pracy" || zle "dead-letter: kod $kod, $out"
rm -rf "$kk" "$dlf"


echo "8. Regulator tempa (tryb zwolnij hamuje P3, a przy odchyleniu > 15 pp także P2; stary pomiar ignorowany)"
reg=$(mktemp)
iso_z() { python3 -c "import datetime as d,sys; print(d.datetime.fromtimestamp(int(sys.argv[1]), d.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$(epoka "$1")"; }
printf '{"procent": 40, "tryb": "zwolnij", "odchylenie": 8.0, "sprawdzono": "%s"}\n' "$(iso_z '2026-12-10 05:50')" > "$reg"
r() { (cd "$tmp/A" && PRZEBIEG_REPO="$tmp/A" PRZEBIEG_ODSTEPY="$tsv" PRZEBIEG_TERAZ=$(epoka "$2") PRZEBIEG_LIMIT_PLIK="$reg" PRZEBIEG_KOSZTY=/nonexistent PRZEBIEG_KOSZTY_KATALOG=/nonexistent "$skrypt" start "$1" A >/dev/null 2>&1; echo $?); }
[ "$(r wywiad '2026-12-10 06:00')" = 10 ] && ok "zwolnij +8 pp: P3 kończy kodem 10" || zle "regulator P3"
[ "$(r prawny '2026-12-10 06:35')" = 0 ] && ok "zwolnij +8 pp: P2 pracuje" || zle "regulator P2 przy +8"
printf '{"procent": 40, "tryb": "zwolnij", "odchylenie": 20.0, "sprawdzono": "%s"}\n' "$(iso_z '2026-12-10 09:00')" > "$reg"
[ "$(r prawny '2026-12-10 09:35')" = 10 ] && ok "zwolnij +20 pp: P2 kończy kodem 10" || zle "regulator P2 przy +20"
[ "$(r ceo '2026-12-10 09:35')" = 0 ] && ok "zwolnij +20 pp: P1 pracuje" || zle "regulator P1"
mkdir -p "$tmp/A/zlecenia"
printf '## [otwarte] 2026-12-10 08:00 · od: ceo · Termin blisko · Z-20261210-01\nTermin: 2026-12-10 10:30\n' > "$tmp/A/zlecenia/prawny.md"
[ "$(r prawny '2026-12-10 10:05')" = 0 ] && ok "zwolnij +20 pp: P2 z zleceniem ≤ 2 h pracuje" || zle "wyjątek regulatora dla terminu"
printf '## [zrobione] 2026-12-10 08:00 · od: ceo · Termin blisko · Z-20261210-01\nTermin: 2026-12-10 13:30\n' > "$tmp/A/zlecenia/prawny.md"
printf '{"procent": 40, "tryb": "zwolnij", "odchylenie": 20.0, "sprawdzono": "%s"}\n' "$(iso_z '2026-12-10 12:00')" > "$reg"
[ "$(r prawny '2026-12-10 12:05')" = 10 ] && ok "zwolnij +20 pp: zamknięte zlecenie nie zdejmuje hamulca" || zle "wyjątek regulatora – zamknięte"
printf '## [otwarte] 2026-12-10 08:00 · od: ceo · Termin blisko · Z-20261210-01\nTermin: 2026-12-10 13:30\n' > "$tmp/A/zlecenia/prawny.md"
[ "$(r prawny '2026-12-10 12:10')" = 0 ] && ok "to samo okienko po otwarciu zlecenia: pracuje" || zle "wyjątek regulatora – kontrola"
rm -rf "$tmp/A/zlecenia"
printf '{"procent": 40, "tryb": "zwolnij", "odchylenie": 20.0, "sprawdzono": "2020-01-01T00:00:00Z"}\n' > "$reg"
[ "$(r wywiad '2026-12-11 06:00')" = 0 ] && ok "stary pomiar (> 2 h): bez hamowania" || zle "regulator stary pomiar"
rm -f "$reg"

echo
if [ $bledy -eq 0 ]; then echo "WSZYSTKO OK"; exit 0; else echo "BŁĘDY: $bledy"; exit 1; fi
