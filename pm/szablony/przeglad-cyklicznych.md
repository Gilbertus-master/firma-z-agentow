# Przegląd zadań cyklicznych – piątek RRRR-MM-DD (PEŁNY PM, konto X)

Szablon: `pm/szablony/przeglad-cyklicznych.md`. Plik: `pm/przeglady/RRRR-MM-DD.md`. Pisze PM co piątek (`role/pm.md`, Tygodniowo;
`backlog.md` C-01). Pytanie przeglądu: **czy każde zadanie cykliczne daje więcej, niż kosztuje – i kto czyta jego wynik?**
Propozycje idą do CEO (`zlecenia/ceo.md`); zmiany zadań zaplanowanych, cronów i rytmu wykonuje CEO wg `uprawnienia.yaml`
(`nowy_agent_lub_zadanie_cykliczne` – ceo), nie PM. Każda liczba z polecenia i godziną.

**Źródła:** `backlog.md` (sekcja Cykliczne), `flota/zadania.yaml` (cron, model, budżety), `koordynacja-odstepy.tsv`,
`python3 -I pm/narzedzia/przebieg-raport.py podsumuj 7` (GG:MM), `przebiegi/<agent>/*.jsonl` (pole `akcje` – co faktycznie powstało),
`ceo/kpi/kpi.md` (wartość = KPI, który zadanie karmi), `pm/raporty/RRRR-MM-DD-flota.md` (ten sam tydzień).

## 1. Tabela zadań cyklicznych (7 dni)

| Id | Zadanie (agent / cron / pętla) | Rytm | Przebiegi | CISZA | Z akcjami (ID) | BŁĄD + NIEPEŁNY | Koszt USD | Koszt / przebieg z akcją | Wartość (KPI) | Kto czyta wynik | Ocena |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C-01 | | | | | | | | | | | zostaw / rzadziej / na zdarzenie / połącz / skasuj / zmień model |

Legenda: **CISZA** = linie kontraktu `tryb: CISZA`; **Z akcjami** = linie z niepustym `akcje` (po ID – PR, commit, zlecenie, plik);
**Kto czyta wynik** = agent/człowiek, który w 7 dniach odwołał się do wyniku (zlecenie, dziennik, decyzja) – „nikt” = kandydat do skasowania.

## 2. Zadania bez wiersza w backlogu / rozjazdy manifestu

- Zadania z `flota/zadania.yaml` bez wiersza C-nn (`python3 -I pm/narzedzia/backlog.py --sprawdz`): …
- Rytm w `flota/zadania.yaml` ≠ `koordynacja-odstepy.tsv` (`python3 -m unittest discover flota`): …
- Zadania zgłoszone w `zlecenia/pm.md` jako nowe/zmienione w tym tygodniu: … (brak zgłoszenia przy zmianie = rozbieżność, kto).

## 3. Propozycje dla CEO (maks. 5)

| # | Zadanie | Propozycja (co zmienić) | Dlaczego (liczby z tabeli 1) | Skutek (koszt / wartość) | Ryzyko | Jak sprawdzimy po tygodniu |
|---|---|---|---|---|---|---|
| 1 | | | | | | |

Przykłady: agent z 7/7 CISZA → rzadszy rytm albo tryb „na zdarzenie” (budzenie przez CEO); dwa zadania o tym samym wyniku → połączyć;
zadanie bez odbiorcy wyniku → skasować; zadanie drogie z prostymi akcjami → słabszy model; agent z `BŁĄD` ≥ 3 → najpierw instrukcja,
nie rytm. Nie proponuj zmiany, której skutek nie jest mierzalny w następnym przeglądzie.

## 4. Co zmieniono po poprzednim przeglądzie i co to dało

| Propozycja z RRRR-MM-DD | Decyzja CEO (link) | Wdrożone (data) | Efekt po tygodniu (liczby) |
|---|---|---|---|

## 5. KPI PM-a
Zadania cykliczne odchudzone/skasowane w miesiącu: N (cel ≥ 1) · koszt floty / tydzień: N USD (poprzedni: N) · udział CISZA: N % (poprzedni: N %).
