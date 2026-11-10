# Do decyzji właściciela – jedna lista

Prowadzi agent CEO. Tylko sprawy, których nie rozstrzyga `decyzje.md`, `zasady.md`, `uprawnienia.yaml` ani zakres
agenta. Najważniejsze na górze. Każda sprawa ma rekomendację i skutek zwłoki – właściciel odpowiada „tak / nie /
inaczej: …”. Po decyzji: wpis `D-…` w `decyzje.md`, usunięcie stąd, zlecenia do agentów.

**Jedno miejsce.** Żadna decyzja właściciela nie istnieje poza tą listą: pytanie do właściciela w raporcie, zleceniu,
opisie PR-a, mailu czy czacie bez wiersza tutaj jest błędem (kontrola A-12). Agent, który potrzebuje decyzji
właściciela, pisze do CEO; CEO najpierw sprawdza, czy może zdecydować sam (`uprawnienia.yaml`, `decyzje.md`), a jeśli
nie – dopisuje wiersz w tym samym przebiegu. Gdy właściciel woli stronę z przyciskami zamiast pliku (np. prywatna strona
Artifact z bazą odpowiedzi), ta lista zostaje źródłem, a strona jej lustrem: CEO w każdym przebiegu czyta odpowiedzi
ze strony, przenosi je tutaj i do `decyzje.md`, a każdy nowy wiersz dopisuje też na stronę.

Domyślna odpowiedź po upływie terminu to **„nie”** (bezpieczny wariant) – CEO planuje tak, żeby brak odpowiedzi
nie blokował organizacji.

| # | Pytanie | Opcje (maks. 4, każda ze skutkiem) | Migawka stanu (liczby, data) | Kto czeka, od kiedy | Rekomendacja CEO | Ważne do (7 dni) |
|---|---|---|---|---|---|---|

## Licznik (PM, co tydzień)
| Tydzień | Zadane | Rozstrzygnięte | Odrzucone | Wygasłe (domyślne „nie”) |
|---|---|---|---|---|
