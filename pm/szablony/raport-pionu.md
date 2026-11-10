# Raport pionu <Produkt | Wzrost | Ryzyko | Finanse> – <RRRR-MM-DD> (pn)

Szablon: `pm/szablony/raport-pionu.md` (prowadzi PM). Pisze lider pionu w pierwszym przebiegu w poniedziałek, przed przeglądem
CEO (`role/ceo.md`, Pełny przegląd). Plik: `<lider>/pion/RRRR-MM-DD.md`. Maks. 1 strona. Bez danych osobowych i sekretów.
Każda liczba ze źródłem i godziną. Brak raportu do pierwszego dyżuru PM po 7:30 = wiersz w `pm/dyzur.md` (blokuje: lider, czeka: CEO).
Piony i liderzy: `README.md → Agenci`.

**Lider:** <agent> · **Członkowie:** <agenci> · **Okres:** <pn poprzedni>–<nd> · **Źródła:** `ceo/kpi/pomiary/<data>.json`,
`python3 -I pm/narzedzia/przebieg-raport.py podsumuj 7`, `zlecenia/<członek>.md` / Issues `agent:<członek>`, `backlog.md`,
`ceo/plan/portfel.md`, `przebiegi/dead-letter/`.

## 1. KPI pionu

| KPI | Dziś | Tydzień temu | Cel | Stan (zielony/żółty/czerwony) | Właściciel |
|---|---|---|---|---|---|
| <id – nazwa z ceo/kpi/kpi.md> | | | | | |

Członkowie (kontrakt przebiegu, 7 dni, z `podsumuj 7` i `backlog.py --sprawdz`):

| Agent | Przebiegi z raportem / oczekiwane | NIEPEŁNY + BŁĄD | Rozbieżności otwarte | F8 OK bez dowodu | F10 dead-letter | Zlecenia otwarte / po terminie | Koszt USD (7 dni) |
|---|---|---|---|---|---|---|---|
| <agent> | N/M | N | N | N % (N/N) | tak/nie (od kiedy) | N / N | N |

**Koszt pionu (7 dni):** N USD = N % kosztu floty (`podsumuj 7`, suma kolumny Koszt dla członków) · koszt / udany przebieg (F7) pionu: N USD ·
usługi zewnętrzne pionu (faktury, `toolbelt/katalog.md`): N PLN. Budżet z `flota/zadania.yaml` (suma `budzet_usd_miesiac` członków): N USD/mies. → tempo N %.

## 2. Top 3 sprawy pionu

1. <sprawa> – stan, następny krok, właściciel, termin (link: zlecenie/PR/plik).
2. …
3. …

## 3. Blokady

| Co | Kto blokuje | Kto czeka | Od ilu h | Co zrobić (kto) |
|---|---|---|---|---|

Tylko blokady wewnątrz pionu, których lider nie rozwiązał sam, i blokady z innych pionów. Sprawy międzypionowe → także wpis w
`zlecenia/ceo.md`. Agent pionu w `przebiegi/dead-letter/` = blokada z właścicielem „operator” (przegląd) – zawsze w tej tabeli.

## 4. Granice i kolejność (rozstrzygnięcia lidera w tygodniu)

- Granice: <spór> → <kto robi>, dlaczego (link do wpisu pod zleceniem).
- Kolejność na ten tydzień: <członek>: 1. … 2. … 3. … (wg EV portfela i terminów; terminów P1 nie przesuwa się).

## 5. Propozycje dla CEO (maks. 3, z EV)

| Propozycja | EV (przychód/EBITDA × p) | Koszt (pojemność floty, pieniądze) | Czas do efektu | Ryzyko | Decyzja potrzebna od |
|---|---|---|---|---|---|

Zasada decyzji jak w portfelu: EV ÷ (koszt + zużycie pojemności floty). Liczby EV to hipotezy z podanym źródłem.

## 6. Koszt koordynacji

Przebiegi lidera w tygodniu: N, w tym na koordynację pionu (raport, rozstrzyganie granic, przypomnienia – bez pracy dziedzinowej): N (N %).
Przebiegi członków bez wyniku (CISZA + BŁĄD + NIEPEŁNY): N z M (N %). Próg: > 30 % koordynacji przez 2 tygodnie, > 50 % bez wyniku przez
3 dni albo raport > 1 strony → sygnał dla CEO (PM zbiera w `pm/raporty/RRRR-MM-DD-flota.md` pkt 4).

## 7. Nauka tygodnia

Reguły dodane do podręczników członków (Id, jedno zdanie) i pomyłki tygodnia (co zawiodło, czy stało się regułą) – maks. 5 linii.
