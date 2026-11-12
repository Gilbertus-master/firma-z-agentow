# Kolejka scalania

**Po co:** PR z werdyktem recenzenta „OK” dla bieżącego commita ma być scalony w kwadrans, a nie czekać na przebieg CEO.
Praca zatwierdzona i niescalona to zapas: nie daje wartości, starzeje się i wpycha kolejne PR-y w konflikt.

**Zasada nadrzędna:** fałszywe „nie scalaj” kosztuje kwadrans, fałszywe „scalaj” – produkcję. Każda wątpliwość kończy się
wpisem dla tego, kto ją usuwa, nigdy scaleniem.

## Kto co robi

| Kto | Co robi | Czego nie robi |
|---|---|---|
| Skrypt `scripts/scalanie.py` | liczy fakty i **klasę** każdego otwartego PR-a, pisze zlecenia, prowadzi stan i dziennik | nie scala, niczego nie zmienia w GitHubie |
| Agent scalający (zadanie `scalanie`, co 15 min) | wykonuje zamkniętą listę czynności z tabeli: scala `GOTOWY`, przepina bazę, ponawia CI, rozsyła zgłoszenia | nie zmienia klasy, nie dotyka kodu PR-a, nie rozwiązuje konfliktów |
| Recenzent | zapisuje werdykt z polami maszynowymi (`recenzent/stan.json`) | nie scala |
| CEO | decyduje o klasach `WARUNEK`, `DECYZJA`, `WYJATEK`, `MIGRACJA`; wstrzymuje i zwalnia; scala w zastępstwie tylko przy `REZERWA_CEO: TAK` | nie wpisuje pól werdyktu za recenzenta |
| Hook uprawnień | przed każdym `gh pr merge` pyta bramkę skryptu; scalenia przez API blokuje zawsze | – |
| Właściciel | decyzja `D-…` dla zasad, uprawnień, polityk i migracji klasy B | – |

Każda przeszkoda trafia od razu do tego, kto ją usuwa (autor, recenzent, CEO) – raz na commit i klasę. Nikt nie czeka na przegląd.

## Przebieg agenta (co 15 min)

1. `blokada scalanie-<konto>` → token i prywatny katalog roboczy (osobny worktree na świeżej gałęzi głównej; wspólnego katalogu agent nie brudzi).
2. `tabela` → wiersze z klasą, adresatem i gotowymi poleceniami.
3. Czynności: `GOTOWY` → polecenie z tabeli + `potwierdz`; `PRZEPNIJ` → `przepiecie`, `zapisz`, zmiana bazy, `odnotuj`; `BRAK_CI` → ponowienie CI + `odnotuj`; reszta → `zglos`.
4. `zapisz` (commit własnych plików kolejki na świeżej gałęzi głównej, do 3 prób, bez rebase i bez `--force`).
5. `odblokuj`. Raport najwyżej 8 linii.

Pełna treść zadania: `flota/szablony/tresc/scalanie.md` → `ceo/handoff/prompty/scalanie.md` (generuje `flota/generuj.py`).

## Klasy wierszy

| Klasa | Kiedy | Adresat |
|---|---|---|
| `GOTOWY` | werdykt `scalenie: tak` dla bieżącego commita, baza = gałąź główna, brak konfliktu, CI zielone, żadnych plików zastrzeżonych ani migracji, brak etykiety stop | agent scala |
| `PRZEPNIJ` | PR-rodzic scalony, baza PR-a wciąż wskazuje jego gałąź | agent zmienia bazę (po zapisie listy plików) |
| `BRAK_CI` | brak jakiegokolwiek checku | agent ponawia raz; po `brak_ci_eskalacja_min` → CEO |
| `KONFLIKT`, `CI_CZERWONE`, `KOLIZJA_MIGRACJI` | konflikt z gałęzią główną, czerwone testy, numer migracji zajęty | autor (z nazwy gałęzi) |
| `NOWY_HEAD`, `BRAK_WERDYKTU`, `NIEJASNY`, `PO_PRZEPIECIU` | werdykt dotyczy innego commita, brak werdyktu ponad `pr_bez_werdyktu_min`, werdykt bez pól maszynowych, po zmianie bazy inna lista plików | recenzent |
| `WARUNEK`, `DECYZJA`, `WYJATEK`, `MIGRACJA`, `DO_ZWOLNIENIA` | warunek w werdykcie, etykieta stop, pliki zastrzeżone albo niepełna lista plików, migracja bazy, wstrzymanie do sprawdzenia | CEO |
| `GLOWNA_CZERWONA`, `REJESTR` | czerwone CI gałęzi głównej („zatrzymaj linię”), nieczytelny rejestr wstrzymań | CEO, wpis **PILNE** |
| bez ruchu | `CZEKA_NA_RODZICA`, `ZALEZNOSC`, `CI_TRWA`, `NIE_SCALAC`, `WSTRZYMANY`, `SZKIC`, `SWIEZY`, `CZEKA_NA_GLOWNA`, `NIEZNANY` | nikt – czeka na zdarzenie |

Kolejność sprawdzeń jest stała i od najostrzejszych: stan PR-a → werdykt → baza → konflikt → CI → pliki → migracje → etykiety.

**CI = ostatni przebieg każdego checku.** `statusCheckRollup` zawiera wszystkie przebiegi checku na head, także czerwone sprzed
ponowienia; kolejka bierze dla klucza (workflow, nazwa checku albo kontekst statusu) tylko przebieg z najpóźniejszym czasem
startu (niezakończony – `0001-01-01` – jest najnowszy). Remis czasu albo brak czasu przy kilku przebiegach = najgorszy wynik
(czerwony). Ponowione i zielone CI zdejmuje więc `CI_CZERWONE` bez pustego commita.
Wstrzymanie CEO przykrywa każdą klasę. Tabela kończy się linią `REZERWA_CEO: TAK|NIE – <powód>`.

## Werdykt recenzenta – pola maszynowe

`recenzent/stan.json → recenzje["<klucz>"]` (klucz: numer PR-a w repozytorium produktu, `<nazwa-repo>#<numer>` w pozostałych):

| Pole | Wartość |
|---|---|
| `sha` | commit, którego dotyczy werdykt (co najmniej 7 znaków) |
| `wynik` | `OK` / `POPRAWKI` / … – proza dla ludzi |
| `scalenie` | `tak` · `nie` · `warunek` – **bez tego pola PR nie zostanie scalony** (`NIEJASNY`) |
| `warunki` | lista warunków, gdy `scalenie: warunek`; formy maszynowe (cały warunek, bez dopisków): `po #N` / `po <nazwa-repo>#N` (kolejka czeka na scalenie tamtego PR-a) i `zielony <check> na head` (nazwa ze spacjami w \`…\`, np. \`Testy / e2e\`; spełniony, gdy **ostatni** przebieg tego checku na bieżącym head ma `SUCCESS` – wtedy bez CEO; nieobecny, pominięty albo czerwony = `WARUNEK`). Każdy inny warunek idzie do CEO |
| `kroki` | czynności po scaleniu (wykonuje CEO albo właściwy agent, nie agent scalający) |
| `klasa_migracji` | `{"<plik migracji>": "A" \| "B"}` – każda migracja z PR-a; brak klasy = jak klasa B |
| `kiedy` | `RRRR-MM-DD GG:MM` – od tej chwili liczy się czas do scalenia |
| `po_przepieciu` | `true`, gdy recenzent obejrzał PR po zmianie bazy |

## Polecenia CEO

```
python3 -I scripts/scalanie.py                        # tabela + REZERWA_CEO
python3 -I scripts/scalanie.py wstrzymaj <klucz> "powód" [--head]
python3 -I scripts/scalanie.py zwolnij <klucz> "uzasadnienie"
python3 -I scripts/scalanie.py miary --dni 7          # mediana i p90 czasu werdykt → scalenie, trzy progi na żywo
python3 -I scripts/scalanie.py bramka "<polecenie>"   # czy to scalenie przejdzie przez hook
```

- **Warunek spoza werdyktu = `wstrzymaj`.** Notatka w czacie albo w pamięci nie zatrzyma agenta; rejestr `wstrzymane.json` – tak.
  Wstrzymanie jest domyślnie do odwołania (nowy commit go nie zdejmuje); `--head` wiąże je z bieżącym commitem.
- **CEO scala tylko pod blokadą** (`blokada ceo-czat` w rozmowie, `blokada ceo-przebieg` w przebiegu) i tylko gdy tabela mówi
  `REZERWA_CEO: TAK` albo wiersz ma klasę z własnej ścieżki CEO. Po pracy `odblokuj`.
- **Nieczytelny `wstrzymane.json` zatrzymuje wszystkie scalenia** – CEO naprawia plik, zanim zrobi cokolwiek innego.
- `BRAK_CI` po eskalacji: CEO sprawdza, czy repozytorium w ogóle ma testy PR; jeśli nie – dopisuje je do `bez_ci` w ustawieniach (PR-em). Nie scala „na słowo”.
- Po własnej zmianie w kolejce CEO sprawdza własną skrzynkę (`zlecenia/ceo.md`) i skrzynkę architekta – przebieg CEO mógł w tym czasie zlecić to samo.
- Przed rozwiązaniem konfliktu w cudzym PR: `git fetch` i sprawdzenie commita gałęzi – autor często robi to sam w ciągu minut.

## Bramka w hooku uprawnień

Każde `gh pr merge` przechodzi przez `bramka()` w skrypcie. Dozwolona jest jedna postać polecenia:
`gh pr merge <nr> --repo <właściciel/nazwa> --<metoda> --match-head-commit <pełny SHA>` – bez `--admin`, `--auto`, drugiego numeru, podstawień powłoki.

| Sytuacja | Kto może scalić | Warunki dodatkowe |
|---|---|---|
| klasa `GOTOWY` | każda rola | ważna blokada scalania; SHA = bieżący commit PR-a; metoda z ustawień |
| `WARUNEK`, `DECYZJA`, `WYJATEK`, `MIGRACJA` (klasa A), `GLOWNA_CZERWONA`, `CZEKA_NA_GLOWNA` | tylko CEO | blokada wzięta jako `ceo-czat` albo `ceo-przebieg`; żadnej twardej przeszkody (konflikt, czerwone CI, brak werdyktu dla commita, wstrzymanie) |
| pliki `zasady.md`, `uprawnienia.yaml`, `.claude/`, `polityki/` w repo organizacji; migracja klasy B albo bez klasy; niepełna lista plików | tylko CEO z decyzją właściciela | jak wyżej + prefiks `DECYZJA=D-RRRRMMDD-NN` przed poleceniem |
| każda inna klasa | nikt | najpierw usunięcie przeszkody |

Bramka czyta ustawienia, werdykty i wstrzymania z gałęzi głównej na serwerze (po `git fetch`), nie z lokalnego katalogu –
lokalna zmiana pliku niczego nie otwiera. Błąd albo brak czasu (40 s) = odmowa. Scalenia przez API (`gh api …`) hook blokuje bez pytania bramki.

**Zatrzymanie awaryjne:** plik `bezpieczenstwo/HALT` zatrzymuje też kolejkę – `blokada` kończy się kodem 14, bramka odmawia
każdego scalenia (także ze ścieżki CEO i z prywatnego katalogu roboczego). Plik usuwa operator.

## Pliki

| Plik | Kto pisze | Co zawiera |
|---|---|---|
| `ustawienia.yaml` | CEO przez PR | gałąź główna, metoda, listy `wyjatki`, `reguly`, `wlasciciel`, `migracje`, `etykiety_stop`, numer protokołu |
| `wstrzymane.json` | wyłącznie CEO (`wstrzymaj`/`zwolnij`) | wstrzymania z powodem |
| `stan.json` | skrypt (`zapisz`) | zgłoszenia już wysłane, zapisy sprzed zmiany bazy |
| `dziennik.jsonl` | skrypt (`potwierdz`) | jedna linia na scalenie: kto, kiedy, commit, minuty od werdyktu (łączenie `merge=union`) |
| `ceo/kontrole/progi.yaml` | CEO | progi kolejki: rezerwa CEO 45 min, blokada 30 min, eskalacja braku CI 30 min, pliki sporne od 3 PR-ów |

## Lekcje wbudowane w konstrukcję

- **Narzędzie scalające przechodzi recenzję przed włączeniem**, a nie po pierwszym błędnym scaleniu.
- **Treść zadania i skrypt podmienia się razem** – numer protokołu w obu; niezgodność = kod 13 i brak blokady (stare zadanie z nowym skryptem nie zostawi blokady na pół godziny).
- **Lista wyjątków jest wąska i jawna** – każdy wzorzec to ścieżka, której błędne scalenie boli; reszta idzie szybko.
- **Pliki sporne** (zmieniane przez ≥ 3 otwarte PR-y, linia `PLIKI SPORNE` w tabeli) są główną przyczyną konfliktów – architekt dzieli taki plik albo zamienia na generowany.
- **Limit konta zatrzymuje także agenta scalającego i rezerwę CEO** – po odnowieniu limitu operator uruchamia zadanie `scalanie` od razu („Uruchom teraz”). Przebieg zabity w połowie zostawia blokadę; następny przejmuje ją po 30 min.
- **„Zatrzymaj linię”**: przy czerwonej gałęzi głównej nie dokłada się zmian – najpierw naprawa.

## Granice, o których trzeba wiedzieć

- Blokada i znak życia agenta są plikami na jednej maszynie i opierają się na współpracy. Przy przebiegach z wielu maszyn wyłączność daje GitHub (scalenie z `--match-head-commit` udaje się raz), a stan w repo jest idempotentny.
- Bramka chroni przed pomyłką i przed poleceniem podsuniętym w treści PR-a, nie przed celowym obejściem (alias, skrypt, inna powłoka). **Prawdziwą granicą jest ochrona gałęzi w GitHubie** – operator ustawia ją przy starcie: wymagany PR, wymagane testy, zakaz wypychania z `--force`.
- Wszyscy agenci działają z jedną tożsamością GitHuba – „kto scalił” wynika z dziennika kolejki, nie z GitHuba. Scalenie bez wpisu w dzienniku jest możliwe; wykrywa je kontrola uzgodnienia B-11 (`ceo/kontrole/kontrole.md`).
- Stan CI gałęzi głównej sprawdzany jest w miarę możliwości: stan nieznany nie zatrzymuje kolejki (tabela wypisuje uwagę).
- GitHub oddaje najwyżej 100 plików na PR – większy PR dostaje klasę `WYJATEK` i idzie do CEO.
- Zlecenie **PILNE** nie budzi adresata – przeczyta je przy następnym przebiegu; pilność skraca termin, nie czas reakcji.
- W repo organizacji agenci wypychają zmiany wprost na gałąź główną, więc lista `reguly` działa tylko na PR-y; zmiany reguł wprost pilnuje hook uprawnień i recenzja następcza.
- Migracji bazy szablon nie automatyzuje: klasa A → scala i stosuje CEO, klasa B albo brak klasy → decyzja właściciela.
- Rola agenta (`AGENT_ROLA` albo plik `.agent-rola`) w prywatnym katalogu roboczym jest pusta – dlatego ścieżka `GOTOWY` nie zależy od roli, a ścieżka CEO wymaga i roli, i blokady wziętej jako `ceo-…`.

## Miary

`python3 -I scripts/scalanie.py miary` – mediana i p90 minut od werdyktu do scalenia, liczba PR-ów z werdyktem OK niescalonych
ponad 2 h (próg 3), PR-y w konflikcie (próg 3), minuty od ostatniego przebiegu agenta (próg 45). Przekroczenia czyta
przegląd tygodnia i kontrole CEO z grupy B.
