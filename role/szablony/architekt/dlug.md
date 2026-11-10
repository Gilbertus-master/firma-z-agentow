# Rejestr długu technicznego (agent {{rola}})

**Cel.** Jedno miejsce na wszystko, co „poprawimy później”: skróty w kodzie, flagi, pominięte testy, odłożone uwagi recenzenta,
obietnice z opisów PR-ów. Dług spisany ma właściciela i decyzję; dług niespisany wraca jako incydent. Źródło kontroli D-01
i D-03 w `ceo/kontrole/kontrole.md`.

**Kolumny.** ID `DL-NN` (stałe w zleceniu i PR-ze spłaty) · Gdzie (repo / moduł / plik, nazwa flagi albo testu) · Wpływ na
klienta / tempo / ryzyko (dla każdego: wysoki, średni, niski albo `–`, plus jedno zdanie, co konkretnie boli) · Koszt spłaty
(S – jedna zmiana w jednym PR-ze · M – kilka PR-ów w tygodniu · L – pozycja planu miesiąca albo decyzja w `{{rola}}/adr/`) ·
Właściciel (rola) · Data przeglądu (`RRRR-MM-DD`) · Decyzja: `spłacić do RRRR-MM-DD (zlecenie <ID>)` albo
`akceptujemy do RRRR-MM-DD – powód`.

**Zasady.**
1. **Skąd wpisy:** uwagi recenzenta „nie blokują – poprawić po scaleniu” niezamknięte w 72 h (D-02, `uwagi_recenzenta_h`) ·
   funkcje za flagą (D-03) · pominięte testy z powodem i terminem (D-04) · najstarsze znaczniki TODO i FIXME (D-05) ·
   obietnice „w osobnym PR-ze” bez zlecenia (D-06) · wnioski z incydentów (`incydenty/`).
2. **Przegląd co 14 dni** (`ceo/kontrole/progi.yaml → dlug_przeglad_dni`): architekt aktualizuje kolumnę „Data przeglądu”
   w każdym otwartym wierszu. Wiersz ze starszą datą = D-01 niezaliczona.
3. **Wysoki wpływ = decyzja.** Każda pozycja z wpływem „wysoki” w którejkolwiek z trzech osi ma decyzję: spłata z terminem
   albo świadome odroczenie. Puste pole decyzji przy wysokim wpływie = D-01 niezaliczona.
4. **Jedna pozycja długu w planie tygodnia** – wybiera ją CEO z architektem w `/przeglad-tygodnia` (wpływ ÷ koszt spłaty).
5. **„Akceptujemy do” zawsze ma datę i powód.** Po dacie pozycja wraca do decyzji. Akceptację pozycji o wysokim wpływie na
   klienta albo ryzyko zatwierdza CEO, nie autor długu.
6. **Flagi:** każda ma datę włączenia albo usunięcia w ciągu 30 dni (`flaga_max_dni`). Po terminie decyzja: włącz, usuń albo
   nowa data z powodem (D-03 – architekt, PM).
7. **Liczniki** (tabela niżej) architekt uzupełnia w poniedziałek. Liczba TODO i FIXME nie rośnie tydzień do tygodnia (D-05);
   otwartych uwag recenzenta jest najwyżej 15 (`uwagi_recenzenta_max`, start) – powyżej: dzień porządków zamiast nowych funkcji.
8. Spłacone pozycje przechodzą do „Spłacone” z PR-em i datą; wierszy nie usuwamy. Bez danych osobowych i bez wartości kluczy.

**Aktualizuje:** {{rola}} – przy każdym nowym długu, po scaleniu PR-a spłaty i w przeglądzie co 14 dni. Czyta: CEO (D-01, D-03),
PM (plan tygodnia), recenzent (czy odłożona uwaga ma wiersz).

Wzór wiersza: `DL-01 | repo / moduł / plik | klient: niski · tempo: wysoki – każda zmiana wymaga ręcznej poprawki · ryzyko: średni | M | <rola> | RRRR-MM-DD | spłacić do RRRR-MM-DD (zlecenie <ID>)`

## Otwarte

| ID | Gdzie | Wpływ (na klienta / tempo / ryzyko) | Koszt spłaty | Właściciel | Data przeglądu | Decyzja (spłacić do / akceptujemy do) |
|---|---|---|---|---|---|---|

## Liczniki tygodniowe

| Tydzień | TODO + FIXME | Flagi bez daty | Pominięte testy | Uwagi recenzenta otwarte (starsze niż 72 h) |
|---|---|---|---|---|

## Spłacone

| ID | Gdzie | PR | Data spłaty | Co się poprawiło (miara albo jedno zdanie) |
|---|---|---|---|---|
