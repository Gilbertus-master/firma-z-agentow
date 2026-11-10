# Strażnik floty

Deterministyczny skrypt (bez LLM), który co 15 minut porównuje to, co flota agentów **miała zrobić**, z tym, co
**faktycznie widać** w repo organizacji i na GitHubie, i alarmuje przy każdej nowej rozbieżności: agent nie wystartował
w swoim okienku, PR czeka na werdykt, zlecenie minęło termin bez odpowiedzi, budżet się wyczerpał, przebiegi kończą się
błędem.

Strażnik nie ocenia jakości pracy i niczego nie naprawia. Zgłasza – operatorowi mailem i powiadomieniem, agentowi CEO
wpisem „Pilne” w `zlecenia/ceo.md` – a w dwóch przypadkach zaciąga hamulec: wstrzymuje agenta po serii błędów
i zatrzymuje flotę po wyczerpaniu budżetu organizacji. Dlaczego skrypt, a nie kolejny agent:
`docs/adr/0003-straznik-bez-llm.md`.

Ścieżki w tym dokumencie są podane względem katalogu głównego repo organizacji.

## W skrócie

| | |
|---|---|
| Kontrole | 6 w rdzeniu: `przebiegi`, `pr`, `zlecenia`, `konfiguracja`, `budzety`, `martwe`; 2 wtyczki domyślnie wyłączone: `testflight`, `automaty`; do tego kontrola własnego klonu (`klon`) |
| Rytm | co 15 min – GitHub Actions (zalecane) albo launchd na Macu |
| Konfiguracja | `org.yaml` w repo organizacji; zmienne środowiskowe `STRAZNIK_…` mają pierwszeństwo |
| Wymagania | Python 3.9+ (wyłącznie biblioteka standardowa, bez pip), `git`, `gh` |
| Kanały alertu | mail (Resend), powiadomienie macOS (tylko przy launchd), wpis „Pilne” w `zlecenia/ceo.md` |
| Sekrety | zmienne środowiskowe (CI) albo pęk kluczy macOS; nigdy w plikach, logach ani komunikatach błędów |

### Pliki modułu

| Plik | Rola |
|---|---|
| `straznik.py` | jeden przebieg: aktualizacja klonu, konfiguracja, kontrole, alerty, zapis stanu, commit własnych plików |
| `zrodla.py` | pobieranie danych (pliki repo, `git`, `gh`, źródła wtyczek), odczyt `org.yaml`, sekrety |
| `kontrole.py` | kontrole jako czyste funkcje `(dane, teraz) -> wynik` – bez sieci i bez zapisu |
| `alerty.py` | reguły alertów, wyciszenia, treść maila, powiadomienie, wpis w `zlecenia/ceo.md` |
| `instaluj.sh`, `straznik.plist.szablon` | instalacja i odinstalowanie agenta launchd (macOS) |
| `test_straznik.py`, `testdane/` | testy i fikcyjne dane przykładowe (bez sieci) |

### Wymagania

- Python 3.9 lub nowszy, tylko biblioteka standardowa (na Macu wystarcza systemowy `/usr/bin/python3`).
- `git` – tagi przebiegów w origin, aktualizacja klonu, commity własnych plików strażnika.
- `gh` (GitHub CLI), zalogowany albo z tokenem w zmiennej `GH_TOKEN` – otwarte PR-y i daty commitów.
- Tylko macOS, opcjonalnie: `security` (sekrety z pęku kluczy) i `osascript` (powiadomienie). Na innych systemach sekrety
  podaje się zmiennymi środowiskowymi, a powiadomienie jest pomijane.

## Szybki start

W katalogu głównym repo organizacji:

```bash
# 1. Dane przykładowe z modułu (fikcyjne): bez sieci i bez zapisu, wynik jako JSON na stdout
python3 moduly/straznik/straznik.py --dane moduly/straznik/testdane --sucho

# 2. Próba na prawdziwych źródłach: JSON na stdout, bez zapisu plików, maili, powiadomień i commitów
python3 moduly/straznik/straznik.py --sucho --repo .

# 3. Testy modułu (bez sieci)
python3 -m unittest discover moduly/straznik
```

Włączenie na stałe opisuje sekcja „Uruchamianie”.

## Jak działa jeden przebieg

1. **Aktualizacja klonu** – `git pull --no-rebase` w repo roboczym (tylko prawdziwy przebieg; szczegóły w sekcji
   „Klon wymaga uwagi”).
2. **Konfiguracja** – odczyt `org.yaml` z repo; zmienne `STRAZNIK_…` nadpisują wartości z pliku.
3. **Źródła** – pliki repo czytane lokalnie, źródła sieciowe (`git ls-remote`, `gh`, źródła wtyczek) pobierane
   równolegle. Źródło, które nie odpowiedziało, nie przerywa przebiegu – jego kontrola dostaje status błędu źródła.
4. **Kontrole** – każda aktywna kontrola liczona osobno; wyjątek w jednej nie zatrzymuje pozostałych.
5. **Alerty** – porównanie z poprzednim stanem (`ceo/straznik.json`) i z wyciszeniami z `zlecenia/ceo.md`; alert tylko
   wtedy, gdy coś się zmieniło albo przyszła pora przypomnienia.
6. **Skutki** – mail, powiadomienie, wpis „Pilne”, bezpieczniki (dead-letter, `HALT`), linie w dzienniku zdarzeń.
7. **Zapis** – commit i push wyłącznie własnych plików strażnika, nowy stan w `ceo/straznik.json`, jedna linia
   podsumowania na stdout: `<czas> <kontrola>=<STATUS>(<liczba ID>) … · alerty: N · X s`.

## Konfiguracja (`org.yaml`)

Strażnik czyta `org.yaml` z repo, które sprawdza. Klucze, z których korzysta:

| Klucz | Znaczenie dla strażnika | Gdy klucza nie ma |
|---|---|---|
| `organizacja.prefiks` | prefiks nazw zadań zaplanowanych `<prefiks>-<agent>-<konto>` (kontrola `konfiguracja`) | `org` |
| `organizacja.strefa` | strefa czasu: okienka harmonogramu, terminy zleceń, cisza nocna, daty w zdarzeniach i wpisach | `Europe/Warsaw` (także przy nieznanej nazwie strefy) |
| `organizacja.domena` | nadawca maili alertów: `Strażnik floty <straznik@<domena z org.yaml>>` | `alerty@example.com` – ustaw domenę albo `STRAZNIK_MAIL_OD` |
| `ludzie.operator.kontakt_firmowy` | adresat maili alertów | `ceo@example.com` – ustaw adres albo `STRAZNIK_MAIL_DO` |
| `repo.github` | `<właściciel>/<repo organizacji>`: właściciel wszystkich repo na GitHubie i repo organizacji w kontroli `pr` | nazwy zastępcze – kontrola `pr` zgłosi błąd źródła |
| `repo.produkt` | repo produktu – lista `[właściciel/nazwa, …]` albo jedna nazwa. Kontrola `pr` obejmuje je wszystkie i repo organizacji; pierwsze z listy to repo, którego werdykty mają klucz bez prefiksu | sprawdzane tylko repo organizacji |
| `runtime.glowny` | `desktop-scheduled` = flota działa jako zadania zaplanowane aplikacji desktopowej; przy każdej innej wartości kontrola `konfiguracja` jest pomijana | `desktop-scheduled` |
| `runtime.konta` | konta, dla których kontrola `konfiguracja` oczekuje osobnego zadania każdego agenta | `[A]` |
| `straznik.kontrole` | lista aktywnych kontroli; nieznane nazwy są ignorowane | 6 kontroli rdzenia |
| `straznik.pomin_tytul` | wyrażenie regularne tytułów PR pomijanych w kontroli `pr` (dopasowanie w dowolnym miejscu tytułu) | pomijane są tylko szkice |
| `mandat.budzet_floty_usd_miesiac` | miesięczny limit wydatków całej floty w USD (kontrola `budzety`) | bez limitu organizacji |

Przykład:

```yaml
organizacja:
  domena: "example.com"
  strefa: "Europe/Warsaw"
  prefiks: "firma"
ludzie:
  operator:
    kontakt_firmowy: "operator@example.com"
repo:
  github: "wlasciciel/firma-agenci"
  produkt: ["wlasciciel/produkt", "wlasciciel/strona"]
runtime:
  glowny: "desktop-scheduled"
  konta: ["A"]
mandat:
  budzet_floty_usd_miesiac: 300
straznik:
  kontrole: [przebiegi, pr, zlecenia, konfiguracja, budzety, martwe]
  pomin_tytul: '^\[wstrzymane'
```

Uwagi:

- **Uproszczony odczyt YAML.** Strażnik nie używa biblioteki YAML. Rozumie `klucz: wartość`, zagnieżdżenie wcięciami,
  komentarze `#` i listy zapisane w jednej linii (`[a, b]`). Lista blokowa (elementy `- …` w kolejnych liniach) nie jest
  czytana – klucz zachowuje się wtedy jak nieustawiony. Wartość w cudzysłowach jest brana dosłownie, bez sekwencji
  ucieczki; wyrażenie regularne zapisuj w pojedynczych cudzysłowach – tak samo odczyta je każdy inny parser YAML.
- **Repo bez `org.yaml`** (albo bez sekcji `organizacja` i `straznik`): wartości domyślne i wszystkie 8 kontroli,
  łącznie z wtyczkami.
- **`straznik.uruchamianie`** to informacja dla ludzi i agentów – kod strażnika jej nie czyta. O tym, gdzie strażnik
  działa, decyduje włączony harmonogram w GitHub Actions albo zainstalowany agent launchd.
- **Błędne wyrażenie w `pomin_tytul`** nie zatrzymuje kontroli: filtr jest wyłączany, a kontrola `pr` dostaje uwagę.
- Pozostałe ustawienia (repo robocze, katalog zadań, wtyczki) podaje się zmiennymi środowiskowymi – tabela w sekcji
  „Zmienne środowiskowe”.

## Czego strażnik oczekuje w repo

| Ścieżka | Kontrola | Uwagi |
|---|---|---|
| `koordynacja-odstepy.tsv` | `przebiegi`, `konfiguracja` | harmonogram floty; pusty albo nieczytelny plik = błąd źródła |
| tagi `przebieg/<agent>/<nr okienka>` w origin | `przebiegi` | wypycha je `scripts/przebieg.sh` na starcie każdego przebiegu agenta |
| `<agent>/agent.md` | `przebiegi` | znak, że rola jest uruchomiona; agent z harmonogramu bez tego pliku nie jest sprawdzany |
| `<agent>/stan.json` → `ostatni_przebieg` | `przebiegi` | brak pliku = uwaga, nie rozbieżność |
| `recenzent/stan.json` → `recenzje` | `pr` | plik musi istnieć (wystarczy `{}`); bez niego kontrola zgłasza błąd źródła – utwórz plik albo usuń `pr` z `straznik.kontrole` |
| `zlecenia/*.md` | `zlecenia` | format wpisów: `zlecenia/README.md`; wyciszenia alertów strażnik czyta z `zlecenia/ceo.md` |
| `przebiegi/<agent>/*.jsonl` | `budzety`, `martwe` | linie kontraktu przebiegu (`pm/specyfikacje/kontrakt-przebiegu.md`) i pliki kosztów |
| `flota/zadania.yaml` | `budzety` | limity miesięczne agentów (`budzet_usd_miesiac`) |
| katalog zadań zaplanowanych (poza repo) | `konfiguracja` | domyślnie `~/.claude/scheduled-tasks`; tylko przy `runtime.glowny: desktop-scheduled` |

## Kontrole

### Wynik kontroli

Każda kontrola zwraca:

- `status`: `OK`, `ROZBIEZNOSC` albo `BLAD_ZRODLA` (źródło nie odpowiedziało, więc nie da się nic stwierdzić);
- `liczby` – liczniki do szybkiej oceny skali;
- `id` – identyfikatory rozbieżności; ich zbiór decyduje o tym, czy alert jest „nowy”;
- `opis` i `uwagi` – tekst do alertu oraz spostrzeżenia, które same alertu nie wywołują;
- `zrodla_bledy` – źródła, które nie odpowiedziały. Kontrola może mieć jednocześnie rozbieżności i błąd części źródeł:
  status to wtedy `ROZBIEZNOSC`, a błąd źródła jest liczony osobno.

### Rdzeń

| Kontrola | Co sprawdza | Rozbieżność | ID |
|---|---|---|---|
| `przebiegi` | czy agent wystartował w ostatnim zakończonym okienku harmonogramu i czy jego `stan.json` jest świeży | brak tagu przebiegu; `ostatni_przebieg` starszy niż 2 × odstęp | `<agent>`, `<agent>:stan` |
| `pr` | czy każdy otwarty PR ma werdykt recenzenta dla aktualnego commita | brak werdyktu dłużej niż 60 min | `<repo>#<nr>` |
| `zlecenia` | czy otwarte zlecenia po terminie mają odpowiedź | termin minął, a odpowiedź jest pusta | plik, data wpisu i tytuł |
| `konfiguracja` | czy zadania zaplanowane agentów zgadzają się z harmonogramem | brak zadania, złe konto, inne godziny | `<agent>:brak-zadania`, `:konto`, `:godzina`, `:godziny` |
| `budzety` | wydatki miesiąca wobec limitów agentów i organizacji | wydatki ≥ 100 % limitu | `<agent>:100`, `org:100` |
| `martwe` | czy agent nie kończy przebiegów błędem raz za razem | 3 ostatnie wyniki to `BŁĄD` | `<agent>` |

#### `przebiegi`

Źródła: `koordynacja-odstepy.tsv`, tagi w origin (`git ls-remote --tags origin przebieg/*`), `<agent>/stan.json`.

- **Harmonogram.** Jeden wiersz tsv na agenta, kolumny rozdzielone tabulatorem: `agent`, `odstep_min` (długość okienka),
  `poczatek` (`GG:MM` – granica okienka) oraz opcjonalnie `dni` (`*` albo `pn,wt,sr,cz,pt,so,nd`), `godziny` (`*` –
  przebieg w każdym okienku – albo lista `G:MM`) i `od` (`RRRR-MM-DD GG:MM` – od kiedy harmonogram obowiązuje; `-` albo
  puste = bez ograniczenia). Linie zaczynające się od `#` to komentarze.
- **Okienko.** Numer okienka jest liczony tym samym wzorem co w `scripts/przebieg.sh`, w strefie organizacji. Sprawdzane
  jest ostatnie zakończone okienko, w którym harmonogram przewiduje przebieg; okienko uznaje się za zakończone 10 min
  po jego końcu. Przy okienkach krótszych niż 60 min tag może być też w następnych okienkach – do 60 min łącznie
  (spóźniony start).
- **Od kiedy.** Oczekiwane są tylko okienka od późniejszej z chwil: kolumna `od` albo pierwszy tag agenta; strażnik
  cofa się najwyżej o 8 dni. Gdy w tym zakresie nie ma okienka z przebiegiem, kontrola dopisuje uwagę, nie rozbieżność.
- **Role nieuruchomione.** Agent z harmonogramu bez pliku `<agent>/agent.md` jest pomijany (licznik `nieutworzeni`).
- **Stan.** `ostatni_przebieg` starszy niż 2 × `odstep_min` (gdy harmonogram ma wybrane dni lub godziny: 2 × najdłuższa
  przerwa między przebiegami) daje ID `<agent>:stan`. Brak pliku albo nieczytelna data to uwaga.

#### `pr`

Źródła: `gh pr list` dla każdego repo z `repo.produkt` i dla repo organizacji, data commita head z API GitHuba,
`recenzent/stan.json`.

- Pomijane są szkice (draft) i PR-y, których tytuł pasuje do `straznik.pomin_tytul` / `STRAZNIK_POMIN_TYTUL`.
- Werdykt to wpis w `recenzje` z polem `sha`. Klucz wpisu: sam numer PR dla pierwszego repo produktu (gdy nie ma repo
  produktu – dla repo organizacji); dla pozostałych `<repo>#<nr>` (akceptowane też `<repo>/<nr>` i `<repo>-<nr>`).
  `sha` może być skrócone – co najmniej 7 znaków, porównywane jako początek commita head.
- Wiek PR-a bez werdyktu liczy się od późniejszej z dat: utworzenie PR-a albo commit head. Powyżej 60 min – rozbieżność.
- Repo, którego `gh` nie zwrócił, to błąd źródła `gh:pr:<repo>`; pozostałe repo są sprawdzane normalnie.

#### `zlecenia`

Źródło: wszystkie pliki `zlecenia/*.md`.

- Sprawdzane są wpisy o nagłówku `## [otwarte…]` albo `## [w toku…]` z linią `Termin:` zawierającą datę. Liczy się
  najwcześniejsza data z tej linii; sama data oznacza koniec dnia (23:59). Po strzałce `→` liczy się tylko część za
  strzałką (termin przesunięty), a daty po słowie „wcześniej:” są pomijane.
- Rozbieżność: termin minął, a po `Odpowiedź:` nic nie ma – ani w tej samej linii, ani niżej w bloku. Wpis bez linii
  `Odpowiedź:` liczy się jak bez odpowiedzi.
- ID to trzy pola rozdzielone znakiem `|`: nazwa pliku, data z nagłówka wpisu i tytuł (do 60 znaków).
- Własne wpisy strażnika (`od: straznik`) są pomijane, żeby alert nie wywoływał kolejnego alertu.

#### `konfiguracja`

Źródła: `koordynacja-odstepy.tsv` i katalog zadań zaplanowanych aplikacji desktopowej (`STRAZNIK_ZADANIA`, domyślnie
`~/.claude/scheduled-tasks`). Dla każdego agenta z harmonogramu i każdego konta z `runtime.konta` strażnik sprawdza
zadanie `<prefiks>-<agent>-<konto małymi literami>/SKILL.md`:

| Warunek | ID przy niespełnieniu |
|---|---|
| plik zadania istnieje | `<agent>:brak-zadania` |
| zawiera linię `Konto: <KONTO>` | `<agent>:konto` |
| pierwsza godzina `GG:MM` w polu `description` (frontmatter) = pierwsza godzina harmonogramu: najwcześniejsza z kolumny `godziny`, a przy `*` – `poczatek` + 30 min | `<agent>:godzina` |
| każda godzina `GG:MM` z opisu należy do harmonogramu | `<agent>:godziny` |

- Przy więcej niż jednym koncie do ID dochodzi przyrostek konta, np. `<agent>:konto:b`.
- Opis bez godzin albo zadanie bez pola `description` to uwaga, nie rozbieżność. Uwagą są też zadania
  `<prefiks>-…-<konto>` spoza harmonogramu.
- Odstępu z opisu strażnik nie porównuje: `odstep_min` w tsv to długość okienka blokady przebiegu, a nie rytm zadania.
- Kontrola jest **pomijana** (status `OK` z opisem „pominięta”), gdy `runtime.glowny` ma wartość inną niż
  `desktop-scheduled`, a także gdy katalogu zadań nie ma i ustawiono `STRAZNIK_BEZ_ZADAN`. Przy `desktop-scheduled`
  brak katalogu zadań bez tej zmiennej to błąd źródła `zadania`.

#### `budzety`

Źródła: `org.yaml` (`mandat.budzet_floty_usd_miesiac`), `flota/zadania.yaml`, `przebiegi/<agent>/`.

- Limit agenta: `budzet_usd_miesiac` w jego bloku `- agent:` w `flota/zadania.yaml` (agent rozpoznawany po polu
  `katalog:`), a gdy go tam nie ma – wartość `budzet_usd_miesiac` z najwyższego poziomu pliku. Brak limitu = agent bez
  kontroli.
- Wydatki bieżącego miesiąca (w strefie organizacji): suma pól `koszt_usd` z plików
  `przebiegi/<agent>/koszty-<RRRR-MM>-*.jsonl` i `przebiegi/<agent>/<RRRR-MM>-*.jsonl`.
- Wydatki ≥ 100 % limitu agenta → `<agent>:100`; suma wydatków wszystkich agentów ≥ limit organizacji → `org:100`.
  Poziom ≥ 80 % to uwaga.
- **Bezpiecznik:** przy `org:100` strażnik zakłada plik `bezpieczenstwo/HALT` (kill switch floty opisany
  w `zasady.md`). Wznowienie: decyzja o budżecie i usunięcie pliku przez operatora.

#### `martwe`

Źródło: pole `wynik` z linii kontraktu w `przebiegi/<agent>/RRRR-MM-DD.jsonl` (trzy najnowsze pliki).

- Trzy ostatnie wyniki agenta równe `BŁĄD` → ID `<agent>`.
- **Bezpiecznik:** strażnik zakłada wtedy `przebiegi/dead-letter/<agent>.md`. Dopóki plik istnieje,
  `scripts/przebieg.sh` kończy przebieg tego agenta kodem 10, bez pracy. Wznowienie: przegląd przyczyny i usunięcie pliku
  przez operatora. Agent, który już ma plik dead-letter, jest tylko uwagą.

### Wtyczki (domyślnie wyłączone)

Wtyczka działa dopiero po dopisaniu jej nazwy do `straznik.kontrole`. Wyłączona nie wykonuje żadnych zapytań do swoich
źródeł. Wtyczki wymagają zmiennych środowiskowych i – częściowo – sekretów (sekcja „Sekrety”).

#### `testflight` – opinie testerów z App Store Connect

Porównuje identyfikatory opinii TestFlight (zrzuty ekranu z uwagami i zgłoszenia awarii) z rejestrem
`aplikacje/opinie-testflight.md`. Opinia jest „w rejestrze”, gdy pierwsze 8 znaków jej identyfikatora występuje
w tekście pliku. Pobierane są wyłącznie identyfikator i data – bez treści uwag i danych testerów.

| Zmienna | Znaczenie |
|---|---|
| `STRAZNIK_ASC` | katalog z modułem `asc.py` – klientem App Store Connect API organizacji, trzymanym poza repo |
| `STRAZNIK_ASC_BUNDLE` | identyfikator pakietu aplikacji (bundle ID) |

- Kontrakt modułu: funkcja `asc.call(metoda, sciezka)` zwraca odpowiedź API jako słownik (`data`, `links.next`) albo
  `{"blad": "<komunikat>"}`. Uwierzytelnienie jest sprawą tego modułu – strażnik nie zna kluczy App Store Connect.
- Bez którejkolwiek zmiennej kontrola zgłasza błąd źródła z komunikatem, co ustawić.
- ID: pierwsze 8 znaków identyfikatora opinii; awarie mają postać `awaria:<8 znaków>`.

#### `automaty` – automaty produktu

Pięć niezależnych części. Co się dzieje, gdy część nie jest skonfigurowana, opisują punkty pod tabelą.

| Część | Źródło | Rozbieżność | ID | Konfiguracja |
|---|---|---|---|---|
| zadania cron bazy | Supabase, `cron.job_run_details` | zadanie zakończone błędem w ostatniej godzinie | `cron:<nazwa zadania>` | `STRAZNIK_SUPABASE_PROJEKT` + token |
| wywołania HTTP z bazy | Supabase, `net._http_response` | odpowiedź 5xx w ostatniej godzinie | `net:5xx` | jak wyżej |
| licznik błędów builda | Supabase, własne zapytanie | wartość kolumny `bledy` ≥ 3 | `build_stan` | dodatkowo `STRAZNIK_SQL_BUILD` |
| workflow wdrożenia | GitHub Actions, ostatni przebieg | wynik `failure`, `timed_out` albo `startup_failure` | `fly:<data przebiegu>` | `STRAZNIK_FLY_REPO`, `STRAZNIK_FLY_WORKFLOW` |
| GitHub Pages | ostatni build Pages | status `errored` albo `failure` | `pages:<repo>:<data>` | `STRAZNIK_PAGES` |

- **Supabase.** Zapytania idą przez Management API w trybie tylko do odczytu (`read_only`). Potrzebny jest ref projektu
  (`STRAZNIK_SUPABASE_PROJEKT`) i token dostępu – usługa `supabase-pat-straznik` w pęku kluczy albo zmienna
  `STRAZNIK_SEKRET_SUPABASE_PAT_STRAZNIK`. Bez projektu albo tokenu części Supabase zgłaszają błąd źródła.
- **Licznik błędów builda.** `STRAZNIK_SQL_BUILD` to zapytanie SQL zależne od schematu bazy organizacji; strażnik bierze
  pierwszy wiersz wyniku i kolumnę `bledy`. Bez tej zmiennej część jest pomijana.
- **Workflow wdrożenia.** Repo: `STRAZNIK_FLY_REPO` (nazwa albo `właściciel/nazwa`), domyślnie pierwsze repo
  z `repo.produkt`; bez obu część jest pomijana. Nazwa workflow: `STRAZNIK_FLY_WORKFLOW`, domyślnie `Fly Deploy`.
- **Pages.** `STRAZNIK_PAGES` to nazwy repo po przecinku (bez właściciela); domyślnie żadne. Repo bez GitHub Pages
  jest pomijane z uwagą.

### Kontrola `klon`

W prawdziwym przebiegu strażnik dodaje jeszcze kontrolę własnego repo roboczego: `OK`, gdy `git pull` się udał; błąd
źródła `git:pull`, gdy nie działa ani pull, ani fetch (sieć); rozbieżność `klon:wymaga-uwagi`, gdy fetch działa, a pull
nie. Tej kontroli nie wpisuje się do `straznik.kontrole`. Co wtedy robić – sekcja „Klon wymaga uwagi”.

### Limity czasu

- Polecenia `git` i `gh` mają limit 10–20 s, zapytania do Supabase 15 s; po przekroczeniu czasu jest jedna ponowna
  próba w tym samym przebiegu. Limity zapytań do App Store Connect ustala moduł `asc.py`.
- Wszystkie źródła sieciowe razem mają 45 s. Źródło, które nie zdążyło, dostaje błąd „przekroczony czas”.

## Alerty

### Kiedy powstaje alert

- **Nowa rozbieżność** – od razu przy pierwszym wykryciu i przy każdej zmianie zbioru ID tej kontroli.
- **Trwała rozbieżność** – przypomnienia: po 2 h od alertu, kolejne po 6 h, następne co 24 h.
- **Błąd źródła** – dopiero gdy to samo źródło nie odpowiada 2 przebiegi z rzędu; pierwszy błąd to tylko linia
  w dzienniku zdarzeń. Od razu, gdy w jednym przebiegu nie odpowiadają co najmniej 2 źródła albo chodzi o licznik
  błędów builda (`build_stan`). Potem przypomnienia jak przy rozbieżności.
- **Powrót do `OK`** nie wysyła alertu – zostaje linia w dzienniku zdarzeń.

Klucz alertu to nazwa kontroli i posortowane ID, więc nowe ID oznacza nowy alert, a nie przypomnienie. Klucze
niewidziane od 3 dni są usuwane ze stanu.

### Wyciszanie

Znaną rozbieżność wycisza się w **odpowiedzi** na wpis strażnika w `zlecenia/ceo.md`, linią:

```
Wycisz do: RRRR-MM-DD[ GG:MM][ (ID, ID)]
```

- Do podanej chwili strażnik nie alarmuje o tych ID tej kontroli. Sama data oznacza koniec tego dnia.
- Bez nawiasu wyciszone są wszystkie ID z linii „Liczby: … ID: …” wpisu.
- Pozostałe ID alarmują dalej. Wyciszone ID są wymienione w uwagach alertu; gdy wyciszone są wszystkie, alert nie
  powstaje, a w dzienniku zdarzeń zostaje linia „bez alertu – wszystkie ID wyciszone”.
- Linia działa niezależnie od statusu wpisu (także po jego zamknięciu), dopóki data nie minie.

### Kanały

1. **Mail** przez Resend. Nadawca: `straznik@<domena z org.yaml>` (albo `STRAZNIK_MAIL_OD`), adresat:
   `ludzie.operator.kontakt_firmowy` (albo `STRAZNIK_MAIL_DO`). Temat: `[STRAŻNIK] <kontrola>: <krótko>`. Treść: status,
   liczby, ID (najwyżej 30, potem „… i N więcej”), opis i uwagi – bez danych osobowych i sekretów. Bez klucza Resend
   przebieg idzie dalej, a w stanie i zdarzeniach zostaje „mail pominięty – brak klucza Resend”.
2. **Powiadomienie macOS** „Strażnik floty” – tylko tam, gdzie jest `osascript`, czyli przy uruchamianiu przez launchd.
   W **ciszy nocnej 23:00–7:00** (strefa organizacji) powiadomienie jest pomijane; mail i wpis „Pilne” powstają jak
   zwykle.
3. **Wpis „Pilne”** w `zlecenia/ceo.md`:

   ```
   ## [otwarte] RRRR-MM-DD · od: straznik · Pilne (strażnik) · <kontrola>: <krótko>
   Strażnik floty (`moduly/straznik`, przebieg GG:MM): <opis>
   Liczby: <liczniki>. ID: <identyfikatory>.
   Stan: `ceo/straznik.json` (klon strażnika), historia: `ceo/straznik-zdarzenia.md`. Klucz strażnika: `<skrót>`.
   Termin: <chwila alertu + 2 h>
   Odpowiedź:
   ```

   Wpis trafia na początek listy zleceń (przed pierwszy nagłówek `## `), z dala od dopisków agentów na końcu pliku –
   mniej konfliktów scalania. Gdy pliku nie ma, strażnik go zakłada. Gdy otwarty wpis z tym samym kluczem już jest,
   strażnik go nie dubluje; mail i powiadomienie idą dalej według przypomnień.

## Pliki wynikowe

| Plik | Zawartość | W repo? |
|---|---|---|
| `ceo/straznik.json` | pełny stan ostatniego przebiegu: `czas`, `czas_przebiegu_s`, `kontrole`, `alerty`, `bledy_zrodel`, `alert_zrodel`, `aktywne_id`, `wyciszenia`, `ostatni_commit_zdarzen`, `mail`, `alerty_przebiegu`, `uwagi` | nie – w `.gitignore`; w GitHub Actions przenoszony między przebiegami w cache |
| `ceo/straznik-zdarzenia.md` | dziennik: linia tylko przy zmianie statusu albo zbioru ID kontroli, przy alercie i przy zadziałaniu bezpiecznika; najnowsze na dole | tak – commit najwyżej raz na godzinę, a przy alercie od razu |
| `zlecenia/ceo.md` | wpisy „Pilne” dla agenta CEO | tak – commit od razu |
| `przebiegi/dead-letter/<agent>.md` | wstrzymanie agenta po serii błędów (kontrola `martwe`) | tak – commit od razu |
| `bezpieczenstwo/HALT` | zatrzymanie floty po wyczerpaniu budżetu organizacji (kontrola `budzety`) | tak – commit od razu |

Strażnik commituje wyłącznie te pliki (`git commit -- <ścieżki>`) i wypycha je zwykłym `git push`; gdy push się nie uda,
robi `git pull --no-rebase` i próbuje jeszcze raz. Dziennik zdarzeń scala się regułą `merge=union` (`.gitattributes`),
więc dopiski innych piszących i linie strażnika zostają obie. Mimo to obsługę alertów lepiej zapisywać w odpowiedzi na
wpis w `zlecenia/ceo.md` niż w dzienniku zdarzeń.

## Uruchamianie

### GitHub Actions (zalecane)

Workflow `.github/workflows/straznik.yml` uruchamia strażnika co 15 minut na checkoucie repo organizacji – bez laptopa.

1. **Harmonogram.** W szablonie jest wyłączony (dwie linie oznaczone `# STRAZNIK-CRON`). Włącza go
   `scripts/init-org.sh` przy zakładaniu organizacji. Ręcznie – to samo polecenie, które usuwa znacznik z obu linii
   z zachowaniem wcięć:

   ```bash
   sed -i.bak 's/^  # STRAZNIK-CRON //' .github/workflows/straznik.yml && rm .github/workflows/straznik.yml.bak
   ```

   Pojedynczy przebieg można wywołać z zakładki Actions (`workflow_dispatch`).
2. **Sekrety repo** (Settings → Secrets and variables → Actions):

   | Sekret | Do czego | Bez niego |
   |---|---|---|
   | `STRAZNIK_TOKEN` | token GitHub z odczytem PR-ów repo produktu i zapisem do repo organizacji | używany jest token przebiegu Actions – działa tylko repo organizacji, PR-y repo produktu będą błędem źródła |
   | `STRAZNIK_RESEND_KEY` | klucz Resend do maili alertów | alert bez maila: wpis w `zlecenia/ceo.md` i dziennik zdarzeń |

3. **Stan** (`ceo/straznik.json`) jest przenoszony między przebiegami w cache Actions – nie trafia do repo.
4. **Wtyczki.** Ich zmienne (`STRAZNIK_ASC…`, `STRAZNIK_SUPABASE_PROJEKT`, `STRAZNIK_SEKRET_…` itd.) dopisz w sekcji
   `env:` kroku „Przebieg strażnika”, a wartości tajne przekaż z sekretów repo.
5. **Kontrola `konfiguracja` w chmurze.** Runner nie ma katalogu zadań aplikacji desktopowej. Przy `runtime.glowny`
   innym niż `desktop-scheduled` kontrola jest pomijana sama. Jeśli flota działa jako zadania desktopu, a strażnik
   w Actions – dopisz w `env:` zmienną `STRAZNIK_BEZ_ZADAN: "1"` albo usuń `konfiguracja` z `straznik.kontrole`; inaczej
   kontrola będzie stale zgłaszać błąd źródła.

### launchd na Macu (alternatywa)

Dla organizacji, której flota działa na jednym Macu: tylko tam strażnik ma dostęp do katalogu zadań zaplanowanych
(kontrola `konfiguracja`) i może wysłać powiadomienie macOS.
Strażnik pracuje we **własnym klonie** repo (domyślnie `~/projekty/organizacja-straznik`), nigdy we wspólnym checkoucie
agentów.

```bash
moduly/straznik/instaluj.sh                # klon (jeśli go nie ma), agent launchd org.agenci.straznik, start od razu
launchctl print gui/$(id -u)/org.agenci.straznik | grep -E 'state|last exit'
tail -f ~/Library/Logs/straznik-floty.log
moduly/straznik/instaluj.sh --odinstaluj   # zatrzymuje i usuwa agenta; klon i log zostają
```

- `STRAZNIK_REPO` – inne położenie klonu; `STRAZNIK_URL` – adres repo do sklonowania (domyślnie `origin` checkoutu,
  z którego uruchamiasz instalator).
- Instalator tworzy `~/Library/LaunchAgents/org.agenci.straznik.plist` z szablonu `straznik.plist.szablon`: przebieg co
  900 s i od razu po załadowaniu, interpreter `/usr/bin/python3`, log w `~/Library/Logs/straznik-floty.log`.
- Sekrety trzymaj w pęku kluczy (sekcja „Sekrety”). Jawne zmienne wtyczek dopisz do słownika `EnvironmentVariables`
  w szablonie plist i uruchom instalator ponownie – szablon jest brany z klonu strażnika, więc zmiana musi być na
  gałęzi głównej repo.
- Nie uruchamiaj jednocześnie launchd i harmonogramu w Actions: alerty i wpisy byłyby podwójne.

### Ręcznie i na sucho

| Opcja | Działanie |
|---|---|
| (bez opcji) | pełny przebieg ze skutkami: pull, kontrole, alerty, commit, zapis stanu |
| `--sucho` | prawdziwe źródła, wynik jako JSON na stdout (`czas`, `czas_przebiegu_s`, `repo`, `kontrole`); bez aktualizacji klonu, zapisu plików, maili, powiadomień i commitów |
| `--dane <katalog>` | zamiast sieci i prawdziwego repo: `<katalog>/zewnetrzne.json`, `<katalog>/repo/`, `<katalog>/zadania/`, `<katalog>/teraz.txt` |
| `--repo <ścieżka>` | repo robocze (domyślnie `STRAZNIK_REPO` albo `~/projekty/organizacja-straznik`) |
| `--zadania <ścieżka>` | katalog zadań zaplanowanych (domyślnie `STRAZNIK_ZADANIA` albo `~/.claude/scheduled-tasks`) |
| `--teraz <ISO>` | chwila przebiegu zamiast zegara, np. `RRRR-MM-DDTGG:MM` (bez strefy = czas organizacji); do testów i odtwarzania sytuacji |

`--dane` używaj razem z `--sucho`. Bez `--sucho` strażnik nie wysyła maili ani powiadomień i niczego nie commituje,
ale zapisuje stan, zdarzenia i wpisy „Pilne” w katalogu `repo/` z danymi.

## Klon wymaga uwagi

Każdy prawdziwy przebieg zaczyna się od `git pull --no-rebase` w repo roboczym. Strażnik nigdy nie używa `git stash`,
`git reset` ani wymuszonego pusha – cudzych zmian nie cofa.

**Zwykła kolizja.** Gdy pull odmawia, bo własne pliki strażnika (`ceo/straznik-zdarzenia.md`, `zlecenia/ceo.md`) mają
niezacommitowane zmiany, strażnik robi z nich lokalny commit, ponawia pull i wypycha wynik. Nie wymaga to niczyjej
uwagi.

**Gdy pull nadal się nie udaje** (konflikt, rozjechana historia), strażnik:

1. przerywa trwające scalanie (`git merge --abort`) – klon wraca do stanu sprzed pull;
2. robi `git fetch`; jeśli i to nie działa, jest to zwykły błąd źródła `git:pull` (alert po 2 przebiegach);
3. jeśli fetch działa – kontrola `klon` zgłasza rozbieżność `klon:wymaga-uwagi`, a strażnik pracuje w trybie awaryjnym:
   - pozostałe kontrole liczy na migawce gałęzi głównej origin (kopia tylko do odczytu w katalogu tymczasowym);
   - zdarzenia zapisuje lokalnie i niczego nie commituje w klonie;
   - nie zakłada plików dead-letter ani `HALT`;
   - wpisy „Pilne” – w tym alert o samym klonie – dopisuje do `zlecenia/ceo.md` przez tymczasowy worktree z gałęzi
     głównej origin (commit tylko tego pliku, zwykły push, worktree usuwany), żeby alert nie zginął.

**Naprawa (operator, ręcznie):**

```bash
git -C ~/projekty/organizacja-straznik status
git -C ~/projekty/organizacja-straznik log --oneline origin/main..HEAD
```

Lokalne commity strażnika dotyczą wyłącznie jego własnych plików. Najbezpieczniej odsunąć klon na bok i założyć nowy:

```bash
mv ~/projekty/organizacja-straznik ~/projekty/organizacja-straznik.stary
moduly/straznik/instaluj.sh    # nowy klon i restart agenta
```

Niewypchnięte wpisy i linie zdarzeń przenieś ręcznie ze starego klonu, potem go usuń. W GitHub Actions każdy przebieg
zaczyna od świeżego checkoutu, więc ta sytuacja w praktyce dotyczy tylko launchd.

## Sekrety

| Sekret | Do czego | Zmienna środowiskowa | Usługa w pęku kluczy macOS |
|---|---|---|---|
| klucz Resend | mail alertów | `STRAZNIK_RESEND_KEY` | `resend-api-key-straznik` |
| token Supabase | wtyczka `automaty` | `STRAZNIK_SEKRET_SUPABASE_PAT_STRAZNIK` | `supabase-pat-straznik` |
| token GitHub | `gh` (PR-y, workflow, Pages) | `GH_TOKEN` | – (albo logowanie `gh auth login`) |

- Zmienna środowiskowa ma pierwszeństwo przed pękiem kluczy. Ogólna reguła nazwy:
  `STRAZNIK_SEKRET_<NAZWA USŁUGI wielkimi literami, znaki inne niż litery i cyfry zamienione na _>`.
- Zapis do pęku kluczy (polecenie zapyta o wartość – nie wpisuj jej w wierszu poleceń):

  ```bash
  security add-generic-password -s resend-api-key-straznik -a straznik -w
  ```

- Klucz Resend powinien mieć wyłącznie uprawnienie wysyłania i być ograniczony do domeny organizacji. Tokenu Supabase
  strażnik używa wyłącznie do zapytań w trybie tylko do odczytu.
- Sekrety istnieją wyłącznie w pamięci procesu. W komunikatach błędów są maskowane, a każdy ciąg wyglądający jak JWT
  (`eyJ…`) jest zamieniany na `***`. Nie trafiają do `ceo/straznik.json`, zdarzeń, maili ani logów.

## Zmienne środowiskowe

| Zmienna | Znaczenie | Domyślnie |
|---|---|---|
| `STRAZNIK_REPO` | repo robocze strażnika (własny klon) | `~/projekty/organizacja-straznik` |
| `STRAZNIK_ZADANIA` | katalog zadań zaplanowanych aplikacji desktopowej | `~/.claude/scheduled-tasks` |
| `STRAZNIK_BEZ_ZADAN` | dowolna niepusta wartość: gdy katalogu zadań nie ma, kontrola `konfiguracja` jest pomijana zamiast zgłaszać błąd źródła | nieustawiona |
| `STRAZNIK_GH_ORG` | właściciel repo na GitHubie – nadpisuje właściciela z `repo.github` | z `org.yaml` |
| `GH_TOKEN` | token dla `gh` | logowanie `gh` |
| `STRAZNIK_MAIL_OD` | nadawca maili alertów | `Strażnik floty <straznik@<domena z org.yaml>>` |
| `STRAZNIK_MAIL_DO` | adresat maili alertów | `ludzie.operator.kontakt_firmowy` |
| `STRAZNIK_RESEND_KEY` | klucz Resend | pęk kluczy; bez klucza mail pomijany |
| `STRAZNIK_SEKRET_<USLUGA>` | sekret usługi zamiast pęku kluczy | pęk kluczy |
| `STRAZNIK_POMIN_TYTUL` | wyrażenie regularne tytułów PR pomijanych w kontroli `pr` – nadpisuje `straznik.pomin_tytul` | brak (nic nie jest pomijane) |
| `STRAZNIK_ASC` | wtyczka `testflight`: katalog z modułem `asc.py` | brak – błąd źródła „ustaw STRAZNIK_ASC” |
| `STRAZNIK_ASC_BUNDLE` | wtyczka `testflight`: identyfikator pakietu aplikacji | brak – błąd źródła |
| `STRAZNIK_SUPABASE_PROJEKT` | wtyczka `automaty`: ref projektu Supabase | brak – błąd źródła |
| `STRAZNIK_SQL_BUILD` | wtyczka `automaty`: zapytanie SQL o licznik błędów builda (kolumna `bledy`) | brak – część pomijana |
| `STRAZNIK_FLY_REPO` | wtyczka `automaty`: repo z workflow wdrożenia (nazwa albo `właściciel/nazwa`) | pierwsze repo z `repo.produkt`; bez niego część pomijana |
| `STRAZNIK_FLY_WORKFLOW` | wtyczka `automaty`: nazwa workflow wdrożenia | `Fly Deploy` |
| `STRAZNIK_PAGES` | wtyczka `automaty`: repo z GitHub Pages, nazwy po przecinku | brak – część nieaktywna |
| `STRAZNIK_URL` | tylko `instaluj.sh`: adres repo do sklonowania | `origin` checkoutu z instalatorem |

## Testy

```bash
python3 -m unittest discover moduly/straznik   # testy modułu
bash scripts/testy.sh                          # wszystkie grupy testów szkieletu, w tym strażnik
```

Testy nie korzystają z sieci, pęku kluczy ani prawdziwej konfiguracji: zmienne `STRAZNIK_…` z otoczenia są na czas
testów usuwane, a źródła zewnętrzne zastępują dane z `testdane/`. Dane są fikcyjne – organizacja o prefiksie `firma`,
repo `firma-agenci`, `produkt` i `strona`.

## Własna kontrola

1. **Funkcja** w `kontrole.py`: `kontrola_<nazwa>(dane, teraz)` zwracająca `wynik(status, liczby, ids, opis, uwagi,
   zrodla)`; gdy dane są nieczytelne – `zrodlo_niedostepne(komunikat, zrodlo)`. Bez sieci i bez zapisu: wszystko, czego
   kontrola potrzebuje, dostaje w `dane`. ID muszą być stabilne między przebiegami – od nich zależy, czy alert jest nowy.
2. **Rejestracja**: wiersz `("<nazwa>", "<etykieta>", kontrola_<nazwa>)` w liście `KONTROLE` w `kontrole.py` oraz nazwa
   w `KONTROLE_WSZYSTKIE` w `zrodla.py` (i w `KONTROLE_RDZEN`, jeśli ma działać domyślnie).
3. **Dane**: fragment pod kluczem `<nazwa>` w `zrodla.zloz` – pliki repo czytaj przez `bezpiecznie(...)`, żeby błąd
   odczytu stał się `{"blad": "…"}`, a nie wyjątkiem. Źródło sieciowe dodaj w `pobierz_zewnetrzne` (tylko gdy kontrola
   jest aktywna) i jego odpowiednik w `zewnetrzne_z_pliku` dla trybu `--dane`.
4. **Włączenie**: nazwa w `straznik.kontrole` w `org.yaml`.
5. **Tekst alertu** (opcjonalnie): krótki opis do tematu maila i nagłówka wpisu w słowniku w `alerty.krotko`.
6. **Testy**: przypadki `OK`, rozbieżność i błąd źródła w `test_straznik.py`; dane przykładowe w `testdane/`.

Konfigurację nowej kontroli podawaj tak jak istniejące: klucz w sekcji `straznik:` w `org.yaml` albo zmienna
`STRAZNIK_…`, zawsze z bezpieczną wartością domyślną i czytelnym komunikatem, gdy czegoś brakuje.

## Ograniczenia

- Strażnik widzi tylko to, co zapisano w repo i co zwracają `git` oraz `gh`. Nie wie, czy praca agenta była dobra –
  wie, czy się odbyła i czy zostawiła ślad.
- Rytm 15 minut i progi (60 min dla PR, 10 min zapasu po okienku, 2 przebiegi dla błędu źródła) są stałymi w kodzie
  (`kontrole.py`, `alerty.py`), nie ustawieniami w `org.yaml`.
- Kontrola `konfiguracja` czyta opisy zadań, nie ich faktyczne wyrażenia cron – te nie są dostępne poza aplikacją.
- Powiadomienia macOS i odczyt pęku kluczy działają tylko na Macu.
