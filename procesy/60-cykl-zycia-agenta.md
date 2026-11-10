# Proces 60 – cykl życia agenta

Cel: każdy agent powstaje, pracuje, zmienia się i kończy w ten sam sposób – z zapisem w rejestrach, bez porzuconych zadań, zleceń i dostępów.
Źródła prawdy: `role/<rola>.md` (biblioteka), `koordynacja-odstepy.tsv` + `flota/zadania.yaml` (flota), `<agent>/` (stan), `decyzje/`.
Uprawnienie: `nowy_agent_lub_zadanie_cykliczne` = poziom **ceo** (wiersz w `backlog.md`, koszt w manifeście); wygaszenie – decyzja CEO
z powiadomieniem właściciela; zmiana `zasady.md`/`uprawnienia.yaml` – właściciel.

## 1. Powołanie
1. **Potrzeba**: zlecenie albo wniosek (PM/CEO/dowolny agent) z EV ÷ koszt (`ceo/plan/portfel.md`) i wierszem w `backlog.md` (cykliczne);
   sprawdzenie, czy istniejąca rola nie pokrywa zakresu (duble ról = koszt); jeśli roli nie ma w `role/` – najpierw PR z nową rolą
   (format jak inne, `role/szablony/<rola>/` dla rejestrów), werdykt recenzenta.
2. **Decyzja**: wpis `[Decyzja CEO] powołanie agenta <rola>` (`decyzje/`) z modelem, rytmem, budżetem miesięcznym i typem (reader/actor/researcher).
3. **Utworzenie** w jednym PR-ze (gałąź `agent/<kto>-nowy-<rola>`):
   - `scripts/nowy-agent.sh <rola>` → katalog agenta (agent.md, dziennik, stan.json, backlog, podręcznik startowy, rejestry z `role/szablony/`),
     `przebiegi/<rola>/`, `zlecenia/<rola>.md`; dla ról z kontaktem zewnętrznym – `ewaluacje/<rola>/` (kontrola `ewaluacje/sprawdz.py`);
   - wiersz w `koordynacja-odstepy.tsv` (wszystkie kolumny, `od` = chwila planowanego startu) i wpis w `flota/zadania.yaml` (cron zgodny z tsv,
     `typ`, `wlasciciel_ludzki`, `domeny`, `autonomia: aprobata` – start zawsze ostrożny, budżety), etykieta `agent:<rola>` w `flota/etykiety.tsv`;
   - `python3 flota/generuj.py && python3 flota/generuj.py --routines`; testy: `python3 -m unittest discover flota`, `bash scripts/test-przebieg.sh`,
     `python3 -I ewaluacje/sprawdz.py`, `bash scripts/test-nowy-agent.sh`;
   - tabela źródeł agenta w `pm/specyfikacje/kontrakt-przebiegu.md` (sekcja 4) – co liczy, jaki rejestr, co jest rozbieżnością;
   - wiersz w `bezpieczenstwo/rejestr-ai.md` (gdy agent przetwarza dane osobowe) i w `ochrona-danych/rejestr-czynnosci.md` (nowe źródło danych);
   - KPI roli w `ceo/kpi/kpi.md` (z sekcji KPI roli).
4. **Werdykt recenzenta** dla PR-a (zmiany instrukcji merguje recenzent albo człowiek, nigdy autor) → scalenie.
5. **Zadanie zaplanowane** – **[operator]** według `ceo/handoff/routines/<rola>.md` (albo CEO w granicach uprawnień, gdy runtime na to pozwala):
   założenie, „Run now” raz ręcznie, kontrola linii w `przebiegi/<rola>/` i braku pytań o zgodę; etykieta Issues `agent:<rola>` w repo
   (`gh label create` z `flota/etykiety.tsv`); dostępy z zakresem minimalnym (`toolbelt/sprawdz-dostepy.md`, `bezpieczenstwo/dostepy.md`).

## 2. Bramka 3 dni
Agent jest „powołany”, gdy przez **3 kolejne dni**: przebiegi w każdym okienku harmonogramu (tagi `przebieg/<agent>/*`), każda linia kontraktu
przechodzi walidator (`outcome_evidence` przy OK), 0 alertów strażnika z jego udziałem, koszt ≤ budżet dzienny, 0 blokad hooka poza bramkami
kwotowymi, ewaluacje zielone. Niespełnione → CEO wydłuża bramkę o 3 dni z zleceniem naprawczym (maks. 2 razy), potem decyzja: zmiana roli
albo wygaszenie. Wynik bramki: linia w dzienniku CEO i status w `backlog.md` (`cykliczne → aktywne`).

## 3. Stały rytm
- Przebiegi według kontraktu; przegląd miesięczny (proces 50) → drabina autonomii; podręcznik ≤ 60 reguł z kuratorem (PM).
- Zmiana **rytmu**: w jednym commicie wiersz tsv (`od` = chwila zmiany) + cron w manifeście + `generuj.py` + testy; zadanie chmurowe
  zaktualizowane przez operatora/CEO (`/schedule update`); strażnik liczy okienka od `od`.
- Zmiana **modelu / budżetu**: manifest + decyzja CEO (budżet w górę ponad próg = właściciel).
- Zmiana **instrukcji** (`<agent>/agent.md`, `role/<rola>.md`, bloki promptów): PR, ewaluacje w CI zielone, werdykt recenzenta; `prompt_version`
  w linii kontraktu zmienia się automatycznie (hash commitu) – regresje da się przypisać do wersji; wdrożenie kanarkowe: nowa wersja na jednym
  zadaniu przez N przebiegów, gdy zmiana jest duża.
- **Pauza**: `przebiegi/dead-letter/<agent>.md` (powód) – `przebieg.sh` kończy kodem 10 bez pracy; zdejmuje CEO po naprawie; HALT dotyczy całej floty.

## 4. Zmiana roli
Gdy zakres się przesuwa (np. compliance oddaje RODO nowej roli ochrona-danych):
1. Decyzja CEO z mapą „co przechodzi, do kogo, od kiedy” (`decyzje/`), wpis w `backlog.md`.
2. PR: nowa/zmieniona rola w `role/`, aktualizacja `role/<rola>.md` obu stron (co 1:1 przeniesione – usunięte u dawcy), `opis` w manifeście,
   KPI w `kpi.md`, tabela źródeł w kontrakcie, rejestry: pliki przenoszone `git mv` (historia zostaje) albo nowe z `role/szablony/`.
3. Zlecenia otwarte w starym zakresie → przepisane do nowego adresata z adnotacją (nagłówek `[otwarte] … · przeniesione z <agent>`).
4. Ewaluacje: scenariusze dla nowej roli, gdy czyta niezaufane treści; rejestr AI i rejestr czynności zaktualizowane.
5. Werdykt recenzenta; po scaleniu 3 dni bramki jak przy powołaniu (dla roli, która zyskała zakres).

## 5. Wygaszenie
Kiedy: rola bez wartości (przegląd PM „koszt kontra wartość”, proces 50), zakres w całości przejęty przez inną rolę, koniec projektu, decyzja właściciela.
1. **Decyzja** `[Decyzja CEO] wygaszenie agenta <agent> od <data>` (z powiadomieniem właściciela w raporcie; gdy agent miał czynności `sam`
   w `uprawnienia.yaml` – także `D-…`, bo zmienia uprawnienia).
2. **Zamknięcie pracy**: zlecenia `[otwarte]`/`[w toku]` przeniesione do następcy albo zamknięte z powodem; PR-y agenta – przekazane (komentarz)
   albo zamknięte; `[w toku]` w cudzych rejestrach zdjęte.
3. **Zadanie zaplanowane usunięte** – **[operator]**/CEO (`/schedule delete` albo w aplikacji); dostępy i klucze agenta odebrane (operator;
   `bezpieczenstwo/dostepy.md` – wiersz `odebrane <data>`), etykieta Issues zostaje dla historii (opis „wygaszony <data>”).
4. **Flota** w jednym PR-ze: wiersz usunięty z `koordynacja-odstepy.tsv`, wpis z `flota/zadania.yaml`, etykieta z `flota/etykiety.tsv`
   (albo opis „wygaszony”), `python3 flota/generuj.py && python3 flota/generuj.py --routines` (prompt i instrukcja routine znikają), testy floty i
   `test-przebieg.sh`; tabela źródeł w kontrakcie – sekcja oznaczona `wygaszony`.
5. **Archiwizacja katalogu**: `git mv <agent> archiwum/<agent>-RRRR-MM` (historia zostaje; `archiwum/` ma własny README z tabelą: agent, od–do,
   powód, decyzja, następca); `przebiegi/<agent>/` **zostaje** (dowody kontraktu, retencja jak audyt ≥ 6 mies.); `zlecenia/<agent>.md` →
   `zlecenia/archiwum/`; `ewaluacje/<agent>/` → `archiwum/<agent>-RRRR-MM/ewaluacje/` (scenariusze z incydentów skopiowane do następcy).
6. **Rejestry**: `bezpieczenstwo/rejestr-ai.md` (status `wygaszony <data>`), `ochrona-danych/rejestr-czynnosci.md` (czynność zakończona, retencja
   danych agenta), `ceo/kpi/kpi.md` (KPI roli oznaczone `wygaszone`), `backlog.md` (cykliczne → `zakończone <data>`), `ryzyka.md`, jeśli agent
   był mitygacją któregoś ryzyka.
7. **Werdykt recenzenta** dla PR-a wygaszenia (lista kontrolna 2–6 w opisie PR-a z dowodami) → scalenie → strażnik przestaje oczekiwać przebiegów
   (agent zniknął z tsv) – sprawdzić brak alertu „brak przebiegu” w następnym cyklu.

## Lista kontrolna wygaszenia (do opisu PR-a)
- [ ] decyzja z datą (i `D-…`, gdy zmienia uprawnienia) · [ ] zlecenia i PR-y przekazane/zamknięte · [ ] zadanie zaplanowane usunięte ·
- [ ] dostępy odebrane · [ ] tsv / manifest / etykiety · [ ] `generuj.py` + testy zielone · [ ] `git mv` do `archiwum/` z README ·
- [ ] rejestry (AI, czynności, KPI, backlog, ryzyka) · [ ] werdykt recenzenta · [ ] brak alertu strażnika po scaleniu
