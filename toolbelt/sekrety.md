# Sekrety

Zasada: sekret (klucz API, token, hasło) **nigdy nie trafia do kontekstu modelu, do pliku ani do repo.**
Agent używa sekretu tylko wewnątrz polecenia, które go wstrzykuje.

## Wzorzec
- Menedżer sekretów: 1Password (konto usługowe, sejf „agenci-<org>”) albo Infisical (Machine Identity).
- Wywołanie: `op run --env-file=toolbelt/env/<usluga>.env -- <polecenie>`. Plik `.env` zawiera **odwołania**
  (`STRIPE_KEY=op://agenci/stripe-agent/credential`), nie wartości.
- Na jednym Macu w ostateczności: pęk kluczy `security find-generic-password -s <nazwa> -w` wewnątrz polecenia
  (wzorzec z organizacji źródłowej).

## Konfiguracja 1Password dla agentów (etap D)
1. **[operator]** Sejf `agenci-<org>` i **konto usługowe** 1Password z dostępem tylko do tego sejfu (Settings →
   Developer → Service accounts). Token konta usługowego trafia do: zmiennej `OP_SERVICE_ACCOUNT_TOKEN` na maszynie
   przebiegów (Mac: pęk kluczy, odczyt tylko w poleceniu; CI: sekret Actions). Nigdy do repo.
2. Pozycje w sejfie nazwane per rola i usługa: `github-pat-ceo`, `resend-obsluga`, `stripe-agent-finansowy`.
3. Plik roli `toolbelt/env/<rola>.env` z odwołaniami `op://…` (wzór: `toolbelt/env/przyklad.env`) – wolno go commitować.
4. Każde polecenie z sekretem: `op run --env-file=toolbelt/env/<rola>.env -- <polecenie>`. Wartość nie trafia do
   kontekstu modelu; `op run` maskuje ją też w wyjściu.
5. Kontrola: `toolbelt/sprawdz-dostepy.md` (`op whoami`, `op read op://agenci/<pozycja>/credential >/dev/null`).

## Zakresy
| Sekret | Zakres minimalny | Agent | Rotacja |
|---|---|---|---|
| Stripe | klucz restricted z tagiem „Agent”, tylko potrzebne zasoby | finansowy (odczyt) | 90 dni |
| GitHub | token per agent, tylko potrzebne repo | wg roli | 90 dni |
| Baza (Management API) | token z rolą tylko do odczytu dla agentów spoza Produktu | architekt | 90 dni |

## Zakazy
- Sekret wypisany w raporcie, dzienniku albo PR-ze → incydent: rotacja w ciągu 1 h (operator), wpis w
  `bezpieczenstwo/incydenty.md`.
- `pm/narzedzia/przebieg-raport.py` odrzuca linie przebiegu, które wyglądają na sekret.

## Sandbox i sekrety poza środowiskiem agenta (rek. 12, zadania operatora)
Ustawienia zarządzane (`managed settings` organizacji albo `~/.claude/settings.json` maszyny przebiegów – nie w repo,
bo repo może zmienić agent):
```json
{
  "sandbox": { "enabled": true, "failIfUnavailable": true, "allowUnsandboxedCommands": false,
               "network": { "allowedDomains": ["api.github.com", "github.com", "api.resend.com", "api.stripe.com"] },
               "credentials": { "mode": "mask" } },
  "disableBypassPermissionsMode": "disable",
  "allowManagedHooksOnly": true
}
```
- `allowedDomains` per typ agenta z `flota/zadania.yaml → domeny` (reader: tylko repo; actor: repo + usługi roli).
- `credentials.mode: mask` – polecenia dostają wartość-wartownik, prawdziwy sekret wstrzykiwany tylko do dozwolonych hostów.
- Domyślnie sandbox czyta `~/.ssh` i `~/.aws` – wyłączyć (`permissions.deny` w `.claude/settings.json` już to robi dla Read).
- Tożsamości: GitHub App (token 1 h) zamiast PAT; Stripe klucze z tagiem Agent per agent (przed 30.11.2026); role DB read-only.
- Kontrola: `toolbelt/sprawdz-dostepy.md` – wiersz „żaden sekret nie jest czytelny z sesji” (`printenv | grep -i key` ⇒ puste; `cat .env` ⇒ blokada hooka).
