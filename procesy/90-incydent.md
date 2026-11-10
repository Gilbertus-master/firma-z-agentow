# Proces 90 – incydent (bezpieczeństwo, niezawodność, koszty)

Uruchamia: agent bezpieczeństwa, CEO, strażnik (HALT automatyczny przy sufitach) albo operator. Skill `/incydent`.
Zasada: **najpierw zatrzymać, potem rozumieć.** Odpowiedzialność prawna spada na człowieka (zarząd), więc każdy krok ma ślad.

| Krok | Co | Kto | Dowód |
|---|---|---|---|
| 0 | HALT (`bezpieczenstwo/HALT`, powód, commit+push) | kto wykrył | commit |
| 1 | Zgłoszenie `incydenty/RRRR-MM-DD-<agent>.md` (szablon `incydenty/_szablon.md`) | kto wykrył | plik |
| 2 | Unieważnienie poświadczeń w zasięgu incydentu (GitHub App/PAT, Stripe, poczta, broker) | operator | wpis w kolejce |
| 3 | Migawka: `git tag incydent/<data>`, kopia audytu/dzienników/stanów poza repo | bezpieczeństwo | tag |
| 4 | Rollback kodu/konfiguracji/schematów MCP przez PR (nie reset --hard) | architekt/inżynier, recenzent | PR |
| 5 | Rotacja sekretów z okresem przejściowym; `toolbelt/sprawdz-dostepy.md` | operator | tabela |
| 6 | Przegląd pre/post z `bezpieczenstwo/audyt/`: co zawiodło w bezpiecznikach; klasa MAST; koszt | bezpieczeństwo, PM | sekcja w zgłoszeniu |
| 7 | Zmiany: prompt/polityka/strażnik/hook + **nowy scenariusz ewaluacji** | właściwy agent, recenzent | PR + plik w `ewaluacje/` |
| 8 | Raport właścicielowi; jeśli dotyczy – art. 26(5) AI Act / RODO (72 h) przez compliance | CEO, compliance | `ceo/do-decyzji.md` |
| 9 | Wznowienie: operator usuwa HALT; decyzja D-… z wnioskami | operator, właściciel | decyzja |

Test kill switcha: raz na kwartał operator zakłada HALT na 10 minut w godzinach pracy floty i sprawdza w audycie, że każda
sesja stanęła; wynik w `incydenty/testy-halt.md`.
