# Rejestr sesji

Każda sesja (czat, przebieg, sesja deweloperska, subagent na dłużej niż jedną turę) ma rodzica i raportuje do niego.
Łańcuch kończy się u CEO. Wpisuje ten, kto uruchamia; zamyka rodzic po sprawdzeniu wyniku u źródła. Najnowsze na dole.
Przed startem sprawdź, czy nikt nie robi tego samego. Przegląd: PM w każdym przebiegu (`python3 -I pm/narzedzia/sesje.py`:
otwarte > 24 h, bez rodzica, rodzic nieznany, zdublowane tytuły, zamknięte bez wyniku) zgłasza CEO; CEO zamyka albo przypisuje.

Kolumny: **Data** – `RRRR-MM-DD GG:MM` startu (bez godziny narzędzie liczy wiek od końca dnia); **Id** – `local_…` / id zadania / `sesja:<nazwa>`;
**Rodzic** – agent (`ceo`, `architekt (czat A)`) albo Id sesji z tego rejestru; **Cel / zrobione gdy** – sprawdzalne kryterium;
**Status**: otwarta · zamknięta (Wynik = link do wyniku) · porzucona (powód, `przejmuje: <kto>`); **Wynik** – ścieżka w repo albo URL.
Znak `|` w treści zastępuj „/” (tabela ma dokładnie 7 kolumn).

| Data | Id | Tytuł | Rodzic | Cel / zrobione gdy | Status | Wynik |
|---|---|---|---|---|---|---|
