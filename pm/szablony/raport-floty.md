# Raport floty – tydzień <RRRR-MM-DD>–<RRRR-MM-DD> (pt, PEŁNY PM)

Szablon: `pm/szablony/raport-floty.md`. Plik: `pm/raporty/RRRR-MM-DD-flota.md`. Pisze PM w piątkowym przebiegu PEŁNYM
(`role/pm.md`, Tygodniowo). Odbiorca: CEO (link w `zlecenia/ceo.md`), finansowy (koszt). Maks. 1 strona. Każda liczba z polecenia
i datą; bez danych osobowych. KPI: `ceo/kpi/kpi.md` F1, F7–F10.

**Źródła:** `python3 -I pm/narzedzia/przebieg-raport.py podsumuj 7` (GG:MM), `przebiegi/dead-letter/`, `koordynacja-odstepy.tsv`
(oczekiwane okienka), `flota/zadania.yaml` (budżety), `org.yaml → mandat.budzet_floty_usd_miesiac`, `ceo/straznik-zdarzenia.md`,
`bezpieczenstwo/blokady.jsonl`, `python3 -I pm/narzedzia/przebieg-raport.py sprawdz przebiegi/*/*.jsonl`.

## 1. Tabela floty (wklej wynik `podsumuj 7` bez zmian)

| Agent | Przebiegi (7 dni) | Tryby | Wyniki | Rozbieżności | Błędy | Koszt USD (n) | F7 koszt/OK | F8 OK bez dowodu | F9 p95 s | Ostatni |
|---|---|---|---|---|---|---|---|---|---|---|
| … | | | | | | | | | | |

Koszt floty razem (7 dni): N USD · tempo miesięczne: N USD z budżetu `budzet_floty_usd_miesiac` = N % (80 % = ostrzeżenie strażnika, 100 % = HALT).

## 2. Pokrycie harmonogramu (przebiegi nieudane)

| Agent | Oczekiwane okienka (tsv) | Z linią kontraktu | Bez linii (nieudane) | BŁĄD | NIEPEŁNY ×2 z rzędu | ROZBIEŻNOŚĆ bez działania |
|---|---|---|---|---|---|---|
| … | | | | | | |

Pokrycie floty: N / M okienek (N %). Cel F1 ≥ 95 % przebiegów z wynikiem OK.

## 3. Sygnały niezawodności

- **F8 fałszywe ukończenie** (OK bez `outcome_evidence`, poza CISZĄ): N % floty; agenci > 0 %: … → zlecenia do poprawy instrukcji (kto, link).
- **F10 dead-letter**: agenci w `przebiegi/dead-letter/`: … (od kiedy, czy operator ma w kolejce, numer pozycji).
- **Kontrakt**: linie odrzucone przez walidator N (agenci: …), linie wersji 1 / bez `prompt_version` N.
- **Strażnik**: rozbieżności z `ceo/straznik-zdarzenia.md` otwarte > 24 h: … · blokady hooka (`bezpieczenstwo/blokady.jsonl`) 7 dni: N (role: …).
- **F9 p95**: agenci powyżej własnego progu (budżet niezawodności) albo p95 > 2× mediany: …

## 4. Koszt koordynacji

- Przebiegi bez wyniku (CISZA + BŁĄD + NIEPEŁNY) / wszystkie: N % floty; agenci > 50 %: … (3 dni z rzędu → propozycja rytmu).
- Udział przebiegów liderów pionów na koordynację (z `<lider>/pion/<pn>.md` pkt 6): … (> 30 % przez 2 tyg. → sygnał dla CEO).
- Koszt przebiegów CISZA: N USD (N % kosztu floty) – kandydaci do trybu „na zdarzenie”: … (szczegóły w `pm/przeglady/RRRR-MM-DD.md`).

## 5. Wnioski i propozycje dla CEO (maks. 5, każda: co · dlaczego · skutek · ryzyko · koszt)

| # | Propozycja | Dlaczego (liczby z sekcji 1–4) | Skutek | Ryzyko | Zmiana wymaga (uprawnienia.yaml) |
|---|---|---|---|---|---|
| 1 | | | | | |

## 6. Porównanie z poprzednim tygodniem

| Miara | Poprzedni tydzień | Ten tydzień | Trend |
|---|---|---|---|
| F1 przebiegi OK | | | |
| pokrycie okienek | | | |
| F8 | | | |
| F10 | | | |
| koszt floty USD | | | |
| przebiegi bez wyniku % | | | |
