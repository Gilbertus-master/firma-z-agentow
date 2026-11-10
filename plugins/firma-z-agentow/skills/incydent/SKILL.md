---
name: incydent
description: Runbook incydentu bezpieczeństwa lub niezawodności floty (HALT, unieważnienie tokenów, migawka, rollback, raport). Uruchamia agent bezpieczeństwa, CEO albo operator – nie model z własnej inicjatywy.
disable-model-invocation: true
---
# Incydent – kroki (pełna wersja: procesy/90-incydent.md)
1. **HALT**: `echo "<powód, data>" > bezpieczenstwo/HALT`, commit i push – wszystkie sesje agentów stają na pierwszym narzędziu.
2. Zgłoszenie: `incydenty/RRRR-MM-DD-<agent>.md` ze szablonu `incydenty/_szablon.md` (oś czasu z `bezpieczenstwo/audyt/`).
3. Unieważnienie poświadczeń, których mógł dotknąć incydent (operator): GitHub App/PAT, Stripe, poczta, broker sekretów.
4. Migawka: `git tag incydent/<data>`; kopia logów audytu, dzienników i stanu agentów poza repo roboczym.
5. Rollback: cofnięcie zmian w kodzie/konfiguracji/schematach MCP do ostatniego dobrego stanu (PR, nie reset --hard).
6. Rotacja sekretów z okresem przejściowym; kontrola `toolbelt/sprawdz-dostepy.md`.
7. Przegląd pre/post: co zawiodło w bezpiecznikach (hook, strażnik, polityki), klasa MAST, koszt.
8. Zmiany: prompt/polityka/strażnik + **nowy scenariusz w `ewaluacje/`**; raport wg AI Act art. 26(5), jeśli dotyczy.
9. Wznowienie: operator usuwa `bezpieczenstwo/HALT` po przeglądzie; wpis w `decyzje/`.
