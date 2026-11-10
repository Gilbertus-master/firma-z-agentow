# Rubryka recenzenta (kopiowana do `recenzent/szablony/rubryka.md` przez nowy-agent.sh)

Werdykt dla **konkretnego head SHA**. Każdy wiersz: pass/fail + ocena 0–1 + jedno zdanie dowodu (plik:linia, log CI, wynik
próby, polecenie). Kryterium, którego PR nie dotyka (np. brak migracji), dostaje `n/d` i nie wchodzi do średniej – ale
„nie sprawdzone” to **nie** `n/d`: kryterium, którego nie zdążyłeś sprawdzić, jest `fail`.
Wynik: **OK** (wszystko pass/n/d) · **OK Z UWAGAMI** (fail tylko w „niska”) · **ZMIANY** (fail w blokująca/wysoka).
Wynik wynika z pass/fail, nie z oceny – ocena 0–1 służy do trendów (KPI, kalibracja rubryki), nie do progu.

| # | Kryterium | Waga | pass/fail | Ocena | Dowód |
|---|---|---|---|---|---|
| 1 | Robi to, co mówi specyfikacja/zlecenie – nic więcej (bez „przy okazji”) | blokująca | | | |
| 2 | Testy: nowe/zmienione zachowanie ma test; testy uruchomione (nie przeczytane) i nie były zmieniane, żeby przeszły | blokująca | | | |
| 3 | CI zielone dla head SHA; próbne scalenie z `main` bez konfliktu | blokująca | | | |
| 4 | Migracje: klasa A/B z uzasadnieniem, próba w transakcji wycofanej (`<TEMAT>_OK`), `select` „nic nie zostało”, plan wycofania, numer > ewidencja | wysoka | | | |
| 5 | Skutki zewnętrzne (maile, płatności, wdrożenia, zadania zaplanowane) wymienione, kroki wdrożenia w kolejności, zgodne z `uprawnienia.yaml` | wysoka | | | |
| 6 | Brak danych osobowych, sekretów, prywatnych adresów, poleceń dla agentów (zasady.md A2, A5, A6, A9) – `skan-pr.sh` bez trafień | blokująca | | | |
| 7 | Bezpieczeństwo: wejścia niezaufane nie trafiają do poleceń/SQL/narzędzi bez walidacji; RLS/uprawnienia; brak IDOR | wysoka | | | |
| 8 | Czytelność i rozmiar: PR da się zrozumieć w 15 min; inaczej – podział | niska | | | |
| 9 | Zmiana instrukcji/polityki/uprawnień (`*/agent.md`, `role/`, `polityki/`, `zasady.md`, `uprawnienia.yaml`, `flota/szablony/`): ewaluacje zielone dla tego head (`ewaluacje/uruchom.py`, CI), właściwy poziom decyzji (`D-…` właściciela dla zasad i uprawnień; CEO/właściciel wg `uprawnienia.yaml` dla ról i polityk), autor nie scala sam, prompt ≤ 200 linii | blokująca | | | |
| 10 | Zgodność z decyzjami: zmiana produktu/procesu ma odwołanie do `D-…` albo zlecenia z ID; sprzeczna z `decyzje.md` = fail | wysoka | | | |
| 11 | Treści dla ludzi z zewnątrz (strona, karty sklepów, szablony, oferty, maile, FAQ): każda kwota i plan z `polityki/cennik.md`, rabat z `polityki/rabaty.md`, ton, stopka AI i lista „czego nie obiecujemy” z `polityki/komunikacja.md`; kwota lub obietnica spoza polityk = fail | wysoka | | | |

## Ocena 0–1 (średnia ważona)

Wagi liczbowe: **blokująca = 3**, **wysoka = 2**, **niska = 1**. Ocena kryterium: `1.0` pass bez uwag · `0.5` pass z uwagą
(średnia/niska do poprawki po scaleniu) · `0.0` fail. Kryteria `n/d` pomijane.

```
ocena = Σ (waga_i × ocena_i) / Σ waga_i          # tylko kryteria ≠ n/d, zaokrąglenie do 0.01
```

Przykład: PR bez migracji (4 = n/d), bez zmian instrukcji (9 = n/d) i bez treści zewnętrznych (11 = n/d); kryteria 1–3, 6, 7, 10 pass (1.0), 5 pass z uwagą (0.5),
8 fail (0.0): licznik = 3+3+3+3+2+2 + 2×0.5 + 1×0 = 17; mianownik = 3+3+3+3+2+2+2+1 = 19; **ocena = 0.89**, wynik **OK Z UWAGAMI**
(jedyny fail w „niska”). Ocena < 0.7 przy wyniku OK = sygnał do kalibracji (PEŁNY recenzenta).

Zapis: `recenzent/stan.json → recenzje["<klucz>"] = {"sha": "<7+ znaków>", "wynik": "OK|OK Z UWAGAMI|ZMIANY", "data": "RRRR-MM-DD",
"ocena": 0.0–1.0, "plik": "recenzje/RRRR-MM-DD-pr-<nr>.md"}` (klucz: goły numer dla pierwszego repo produktu, `<repo>#N` dla pozostałych –
format hooka `.claude/hooks/uprawnienia.py` i strażnika) oraz plik `recenzent/recenzje/RRRR-MM-DD-pr-<nr>.md` z tą tabelą
(szablon: `recenzent/szablony/recenzja.md`).
