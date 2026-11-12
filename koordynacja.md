# Koordynacja przebiegów

Każdy przebieg zaplanowany zaczyna od blokady okienka. Dzięki temu ta sama praca nie jest robiona dwa razy – także
przy kilku kontach Claude, zaległych przebiegach po uruchomieniu aplikacji i ręcznym „Uruchom teraz”.
Czaty z ludźmi (sesje ręczne) nie wykonują blokady.

## Konto
Konto bierzesz z linii „Konto: X” na początku promptu zadania (brak linii → `A`). Lista kont: `org.yaml → runtime.konta`.

## 1. Start – blokada okienka
```
cd <repo organizacji> && git pull --rebase --quiet
scripts/przebieg.sh start <agent> <konto>      # np. scripts/przebieg.sh start ceo A
```
- **kod 0** – przebieg Twój, pracuj dalej.
- **kod 10** – w tym okienku przebieg już był albo trwa. Kończysz jednym zdaniem, bez pracy i bez commita.
  Kod 10 z komunikatem `BUDŻET:` – limit konta jest wysoki, a agent ma niski priorytet (≥ 85% nie pracuje P3,
  ≥ 95% także P2).
- **inny kod** – kończysz bez pracy, raport z komunikatem skryptu.

Jak to działa: skrypt wypycha tag `przebieg/<agent>/<okienko>`. Tag może powstać tylko raz, więc wygrywa pierwszy.
Okienko = odstęp z `koordynacja-odstepy.tsv` w strefie z `org.yaml`. Tagi starsze niż 14 dni skrypt usuwa sam.
Test: `scripts/test-przebieg.sh`.

## 2. Praca dłuższa niż przebieg
Zlecenie, które może się nie zmieścić, oznaczasz **przed pracą**: `[w toku · konto X · RRRR-MM-DD GG:MM]`, commit
i push. Wpis młodszy niż 6 h zostawiasz; starszy uznajesz za porzucony – sprawdzasz, co zrobiono, oznaczasz swoim
i kończysz.

## 3. Koniec
Dziennik z kontem w nagłówku, `stan.json` z polem `konto`, linia w `przebiegi/`, commit tylko swoich plików.
Zapis wyłącznie skryptem: `scripts/przebieg.sh zapisz <agent> "<co>" <twoje ścieżki>` (= `scripts/zapisz.sh`): commit tylko
podanych ścieżek, `pull --rebase` (przy cudzych zmianach w kopii – merge), push do 5 prób z rosnącym odstępem i losowym
rozrzutem, nigdy `--force`. Kod 1 = konflikt we własnym pliku, znaczniki konfliktu albo push nieudany – commit zostaje
lokalnie, ślad na stderr; wpisujesz to do raportu i nie rozwiązujesz siłą (w CI z jednorazowym runnerem niewypchnięty
commit przepada razem z runnerem – stąd ponowienia). Test: `scripts/test-zapisz.sh` (wyścig dwóch zapisów).

## Sesje czatu
- Każdy PR otwarty przez sesję czatu ma w opisie linię `Sesja: <id sesji>` – po niej agent scalający i CEO powiadamiają
  autora o werdykcie (kontrola B-13).
- Po wysłaniu PR-a do recenzji sesja **sama pilnuje werdyktu**: co kilka minut (do 2 h) sprawdza `recenzent/stan.json`
  dla swoich PR-ów i od razu poprawia uwagi. Nie kończy pracy, dopóki jej łańcuch PR-ów nie jest scalony albo nie czeka
  wyłącznie na decyzję z datą. Łańcuchy PR-ów stoją najczęściej dlatego, że autor nie widzi werdyktu.
- Zasoby z numerami (np. migracje bazy) bierzesz z przydziału albo sprawdzasz na gałęzi głównej i w otwartych PR-ach,
  zanim nadasz numer – dwa PR-y z tym samym numerem kończą się konfliktem dopiero po scaleniu.

## Zmiana harmonogramu
W jednym commicie: wiersz w `koordynacja-odstepy.tsv` (wszystkie kolumny, `od` = chwila zmiany), wpis w
`flota/zadania.yaml` (cron), `python3 flota/generuj.py`, testy: `python3 -m unittest discover flota` i
`scripts/test-przebieg.sh`. Zmiana zadań zaplanowanych – według `uprawnienia.yaml`.
