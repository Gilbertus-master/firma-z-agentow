# Startowe rejestry ról

`role/szablony/<rola>/**` kopiuje `scripts/nowy-agent.sh <rola>` do katalogu agenta (rekurencyjnie, **bez nadpisywania** istniejących
plików; znaczniki `{{rola}}` i `{{org.nazwa}}` podmieniane). Agent zaczyna pracę z gotowymi rejestrami zamiast wymyślać format
w pierwszym przebiegu – a strażnik, PM i kontrakt przebiegu (`przeczytane` / `w_rejestrze`) mają stałe pliki do uzgodnień liczbowych.

Każdy rejestr ma nagłówek: **cel**, **kolumny**, zasadę **„bez danych osobowych”** (ID wątku / opinii / sprawy zamiast osób) i **kto i kiedy
aktualizuje**. Format i treść uogólnione z rejestrów floty źródłowej (listopad 2026).

| Rola | Pliki | Po co |
|---|---|---|
| aplikacje | `opinie.md`, `wydania.md` | opinie testerów po ID ze sklepu; wersje, buildy, bramki, wycofanie |
| architekt | `adr/README.md`, `tematy/README.md` | decyzje architektoniczne produktu; postęp tematów między sesjami |
| bezpieczenstwo | `alerty.md`, `dostepy.md` | alerty i podatności po ID; przegląd kwartalny tożsamości i kluczy |
| compliance | `rejestr-wymogow.md`, `kalendarz.md`, `luki.md`, `bramka-wydania.md` | wymogi per kraj (W-…), wejścia w życie, luki (C-…), bramka G1–G12 |
| inzynier | `README.md` | konwencja gałęzi, worktree, PR, zajęcia pracy |
| lokalizacja | `kraje.md`, `rejestr.md` | kraje → języki → karty; luki językowe (L-…) |
| ochrona-danych | `rejestr-czynnosci.md`, `dostawcy-dpa.md`, `zadania-osob.md`, `naruszenia.md`, `dpia-szablon.md` | art. 30, art. 28, art. 15–22, art. 33–34, art. 35 RODO |
| prawny | `umowy.md`, `terminy.md`, `wzory/README.md` | rejestr umów (U-…), terminy działań, wzory z wersją i decyzją |
| recepcja | `rejestr-poczty.md` | wpływy z adresów ogólnych po ID wątku, czas rozdzielenia |
| tester | `lista-reczna.md`, `bledy.md` | to, czego automat nie widzi; błędy (T-…) i ucieczki |
| wywiad | `rejestr.md` | źródła (S-…), konkurenci (K-…), znaleziska (WR-…) z EV |

Recenzent dostaje rubrykę z `role/_rubryka-recenzenta.md` (osobna ścieżka w skrypcie). Nowy rejestr dla roli: plik tutaj + wiersz
w tej tabeli + linia **Rejestry startowe** w `role/<rola>.md`; test `scripts/test-nowy-agent.sh` sprawdza, że każda rola z szablonami istnieje
w `role/` i że kopia się udaje.
