# Tematy – rejestr postępu prac architekta

**Cel.** Każdy temat (funkcja, przebudowa, migracja) ma jeden plik `tematy/RRRR-MM-DD-<temat>.md`, który przenosi stan między
przebiegami i sesjami: rozpoznanie → projekt → plan → budowa → PR → zamknięcie. Dzięki temu nowa sesja nie powtarza rozpoznania,
a CEO widzi etap bez czytania dzienników. Limit: **jeden temat w budowie naraz** (kolejne – projektowane, budowa po otwarciu PR-a poprzedniego).

**Zasady.** Nagłówek pliku: zlecenie (ID, od kogo, data), worktree i gałąź (`agent/architekt-<temat>` od gałęzi głównej), etap
(`rozpoznanie` · `projekt` · `plan` · `budowa` · `PR #N` · `zamknięty <data>` · `przekazany inżynierowi <data>`). Etap też w
`stan.json → tematy`. Przed startem: zajęcie pracy (`[w toku …]`, push) i `gh pr list --search "<temat>"` – żeby nie dublować sesji.
Specyfikacje i plany w repo produktu (`docs/superpowers/specs/`, `docs/superpowers/plans/`); tu linki i decyzje, nie kopie.
**Bez danych osobowych** (agregaty z produkcji – tak, rekordy – nie) i bez sekretów. **Aktualizuje:** architekt – każdy przebieg, w którym
temat się zmienił; zamyka po scaleniu i potwierdzeniu testera.

| Plik | Temat | Zlecenie | Etap | PR | Ostatnia zmiana |
|---|---|---|---|---|---|

## Szablon pliku tematu

```markdown
# Temat: <nazwa> (<skrót>)

Zlecenie: <ID / od kogo / data>. Worktree: `<ścieżka>`, gałąź `agent/architekt-<temat>` (od gałęzi głównej <sha7>). Etap: rozpoznanie.

## Rozpoznanie (data, godzina)
- Co jest dziś (kod: plik:linia; stan produkcji – agregaty; otwarte PR-y w tym obszarze).
- Rozmiar: poprawka / projekt. Skutki prawne, dane osobowe, płatności → zlecenia do prawnego / ochrony danych / compliance.
- Pytania do CEO (z propozycją odpowiedzi).

## Projekt
- Specyfikacja: `docs/superpowers/specs/RRRR-MM-DD-<temat>-design.md` (link do PR). Decyzje architektoniczne → ADR NNNN.

## Plan
- `docs/superpowers/plans/RRRR-MM-DD-<temat>.md`; podział na PR-y (jeden PR = jeden krok), klasa migracji każdego kroku (A/B).

## Budowa
- Rejestr postępu (zadanie → PR → werdykt recenzenta → scalenie); przekazanie inżynierowi: wpis w jego zleceniach z linkami.

## Zamknięcie
- Co weszło na produkcję (sha), test testera (ID), co zostało do backlogu, lekcje → podręcznik.
```
