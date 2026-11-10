# Rejestr systemów AI organizacji (AI Act art. 26 – nadzór ludzki, logi ≥ 6 mies.: obowiązek przy systemach wysokiego ryzyka, tu dobra praktyka; ISO 42001 – wykaz systemów)

| System | Dostawca / model | Cel | Typ (reader/actor/researcher) | Osoba nadzoru (uprawniona do HALT i rotacji) | Dane osobowe | DPA / ZDR | Logi (gdzie, retencja) |
|---|---|---|---|---|---|---|---|
| Flota agentów (Claude Code) | Anthropic – klasy z `flota/zadania.yaml`, modele z `org.yaml → runtime.modele` | prowadzenie organizacji | wg manifestu | operator (org.yaml) | minimum (zasady A5) | plan komercyjny z DPA: ☐ · ZDR modeli: ☐ sprawdzone | `bezpieczenstwo/audyt/` (git, bezterminowo), `przebiegi/` |
| Strażnik floty | skrypt (bez LLM) | kontrole niezawodności | – | operator | nie | – | `ceo/straznik-zdarzenia.md` |
| (konektory/usługi z `toolbelt/katalog.md` przetwarzające dane osobowe) | | | | | | DPA ☐ | |

Zasady: wpis przed uruchomieniem systemu; przegląd kwartalny (compliance); pseudonimizacja PII w logach po 6 miesiącach;
decyzja właściciela o planie Claude (konsumencki nie ma DPA) i o dopuszczeniu modeli bez ZDR – `decyzje/`.
