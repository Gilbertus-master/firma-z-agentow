---
name: dyzur-pm
description: Dyżur blokad PM (kto na kogo czeka; > 6 h → zlecenie do CEO) i raport floty z kontraktu przebiegu (nieudane, NIEPEŁNE, F8 fałszywe ukończenie, F10 dead-letter) – procedura z poleceniami. Uruchamia agent PM w trybie DYŻUR / DZIENNY / PEŁNY, nie model z własnej inicjatywy.
disable-model-invocation: true
---
# Dyżur blokad i raport floty – kroki (pełna wersja: `role/pm.md`, `pm/dyzur.md`, `pm/szablony/raport-floty.md`)

Każda liczba z polecenia wykonanego **w tym dyżurze** i godzina z `date` – nic z pamięci ani z poprzedniego `pm/dyzur.md`.
Tylko odczyt źródeł + wpisy w swoich plikach. Niczego nie scalasz, nie budzisz agentów sam (robi to CEO), nie zamykasz cudzych zleceń.

0. Start: `date`; `scripts/przebieg.sh start pm <konto>` z kodem 0 (skill `/przebieg`); `git pull --rebase --quiet`. Repozytoria PR-ów: `org.yaml → repo.produkt` + `repo.github`.
1. **PR-y** – dla każdego repo: `gh pr list -R <repo> --state open --json number,title,headRefOid,isDraft,mergeable,statusCheckRollup,updatedAt` i `recenzent/stan.json → recenzje`
   (skrót: `bash recenzent/skrypty/uzgodnienie.sh` – tylko odczyt). Klasyfikacja: werdykt `OK`/`OK Z UWAGAMI` dla head + wszystkie checki SUCCESS + `MERGEABLE`
   = **gotowy niescalony** (od ilu h: `teraz − data werdyktu`); bez werdyktu dla head > 1 h = **kolejka recenzenta** (CEO budzi); `CONFLICTING` = **autor**.
2. **Zlecenia**: `python3 -I pm/narzedzia/backlog.py --sprawdz` (po terminie, duble, rozjazdy md ≠ Issue, zadania bez wiersza C);
   `grep -n "^## \[czeka\|^## \[w toku\|Pilne" zlecenia/*.md`; Issues: `gh issue list -R <org> --label stan:czeka --state open --json number,title,updatedAt`
   i `--label typ:blokada`. `[w toku]` starsze niż 6 h → sprawdź w `<adresat>/dziennik.md`, czy od tej godziny jest wpis; brak = blokuje adresat.
3. **Operator i właściciel**: `operator/kolejka.md` – pozycje starsze niż `org.yaml → ludzie.operator.sla_godziny`; `ceo/do-decyzji.md` – sprawy po „Ważne do” (wygasłe = domyślne „nie”).
4. **Flota (24 h)**: `python3 -I pm/narzedzia/przebieg-raport.py podsumuj 1`; `ls przebiegi/dead-letter/ 2>/dev/null`; agenci bez linii w swoim oknie
   (okienka z `koordynacja-odstepy.tsv`, tolerancja: okno + 30 min); `python3 -I pm/narzedzia/przebieg-raport.py sprawdz przebiegi/*/$(date +%F).jsonl`
   (linie odrzucone, wersja 1, brak `prompt_version`/`outcome_evidence`); F8 z kolumny „OK bez dowodu”.
5. **Sesje**: `python3 -I pm/narzedzia/sesje.py` (otwarte > 24 h, bez rodzica, duble, zamknięte bez wyniku) → linie dla CEO; nie zamykasz.
6. **Zapis**: nadpisz `pm/dyzur.md` wg szablonu (nagłówek z datą, godzinami i kontem; źródła z godziną; liczby; tabela „co · kto blokuje · kto czeka · od ilu h · co zrobić”).
   Blokada **> 6 h** (albo PR gotowy > 6 h, zlecenie po terminie, dead-letter) → wpis w `zlecenia/ceo.md`:
   `## [otwarte] RRRR-MM-DD GG:MM · od: pm · Dyżur blokad GG:MM · Z-RRRRMMDD-NN`, `Termin:` +3 h, `Zrobione gdy: CEO odpowiedział pod wpisem`, maks. 10 linii
   (do scalenia / do obudzenia / po terminie / do operatora). Blokującemu agentowi pod jego zleceniem: `**Pilne (dyżur PM GG:MM):** czeka na Ciebie <kto> – <co>`
   – najpierw `grep -n "Pilne (dyżur PM" zlecenia/<agent>.md` (raz na 6 h, nie częściej).
7. **Bez blokad**: zdanie „Dyżur: brak blokad.”, linia kontraktu w trybie `DYŻUR`, bez zmian w innych plikach.
8. **Piątek (PEŁNY)**: `python3 -I pm/narzedzia/przebieg-raport.py podsumuj 7` → `pm/raporty/RRRR-MM-DD-flota.md` (`pm/szablony/raport-floty.md`: pokrycie okienek, F1, F7–F10,
   koszt vs `budzet_floty_usd_miesiac`, koszt koordynacji); `pm/przeglady/RRRR-MM-DD.md` (`pm/szablony/przeglad-cyklicznych.md`, maks. 5 propozycji);
   `python3 -I scripts/decyzje-indeks.py --sprawdz`; wiersz w liczniku `ceo/do-decyzji.md`; poniedziałek: raporty pionów `<lider>/pion/<data>.md` (brak = wiersz w dyżurze).
9. **Koniec**: `pm/dziennik.md` (Dyżur · Flota · Rejestr sesji · Do CEO · **KPI:**), `pm/stan.json`, linia kontraktu v2 (`tryb: DYŻUR|DZIENNY|PEŁNY`; `zrodla`: `zlecenia/*.md`,
   `PR otwarte`, `przebiegi/`, `rejestr-sesji.md`, `operator/kolejka.md`, `ceo/do-decyzji.md` z liczbami z tego przebiegu; `outcome_evidence` = ścieżka `pm/dyzur.md`
   albo raportu), `git add pm/ backlog.md przebiegi/pm/ zlecenia/<tylko własne wpisy>` (z nazwy), commit `pm: dyżur RRRR-MM-DD GG:MM – <N blokad>`, `git pull --rebase` (do 3 prób), push.
