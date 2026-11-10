# Wtyczka Claude Code – firma-z-agentow

Skille organizacji agentycznej dostępne w każdym folderze, bez klonowania szablonu.

```
/plugin marketplace add Gilbertus-master/firma-z-agentow
/plugin install firma-z-agentow@firma-z-agentow
```

| Skill | Do czego |
|---|---|
| `/firma-z-agentow:nowa-organizacja` | zakłada prywatne repo firmy z szablonu i prowadzi przez pierwsze uruchomienie |
| `/firma-z-agentow:przebieg` | kontrakt przebiegu agenta (start, tryby, zakończenie, raport) |
| `/firma-z-agentow:dyzur-pm` | dyżur blokad PM i raport floty |
| `/firma-z-agentow:recenzja` | recenzja PR-a krok po kroku |
| `/firma-z-agentow:incydent` | runbook incydentu (HALT, migawka, raport) |

Skille `przebieg`, `dyzur-pm`, `recenzja` i `incydent` zakładają, że pracujesz w repo firmy utworzonym z szablonu
(te same skille są tam w `.claude/skills/`). Wtyczka nie zawiera hooków ani reguł uprawnień – zabezpieczenia floty
działają tylko w repo firmy (`.claude/settings.json`, `.claude/hooks/uprawnienia.py`).

Katalog jest generowany przy wydaniu z `.claude/skills/` – zmiany zgłaszaj tam. Licencja: Apache-2.0.
