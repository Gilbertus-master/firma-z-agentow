# Obserwowalność floty: koszt i wynik per agent

Trzy źródła, od najprostszego:

| Źródło | Co daje | Gdzie |
|---|---|---|
| **Linia kontraktu przebiegu** (agent) | tryb, źródła, akcje, wynik OK/ROZBIEŻNOŚĆ, opcjonalnie `model` i `koszt_usd` | `przebiegi/<agent>/<data>.jsonl` |
| **Wrapper headless** (`scripts/przebieg-headless.sh`) | `total_cost_usd`, czas, tury, błąd – z wyniku JSON `claude -p` (szacunek kliencki) | `przebiegi/<agent>/koszty-<data>.jsonl` |
| **OpenTelemetry z Claude Code** | metryki `claude_code.cost.usage`, `claude_code.token.usage` (input/output/cacheRead/cacheCreation), `claude_code.session.count`, `claude_code.active_time.total`, `claude_code.commit.count`, `claude_code.pull_request.count`; zdarzenia `claude_code.tool_result`, `claude_code.api_error` | kolektor OTLP → Langfuse (self-host, UE) albo Prometheus/Grafana |

Raport tygodniowy: `python3 -I pm/narzedzia/przebieg-raport.py podsumuj 7` sumuje koszt z obu plików per agent.
KPI F2 „koszt floty / przychód” (`ceo/kpi/kpi.md`) – finansowy bierze liczbę z tego raportu albo z Langfuse.

## Włączenie telemetrii (operator, raz na maszynę przebiegów)
Zmienne OTEL w `.claude/settings.json` repo są **ignorowane** – muszą być w `~/.claude/settings.json` maszyny
(albo w ustawieniach zarządzanych organizacji; w chmurowych scheduled tasks – w zmiennych środowiska cloud environment):
```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.<domena-firmy>",
    "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic <token z 1Password, nie wpisywać na stałe – otelHeadersHelper>",
    "OTEL_RESOURCE_ATTRIBUTES": "org.prefiks=<prefiks>,deployment.environment=flota",
    "OTEL_METRIC_EXPORT_INTERVAL": "30000"
  },
  "otelHeadersHelper": "/usr/local/bin/otel-naglowki.sh"
}
```
- `otelHeadersHelper` – skrypt wypisujący nagłówki (token z `op read`), żeby sekret nie leżał w pliku.
- Rola agenta: wrapper headless dodaje `agent.role=<agent>` do `OTEL_RESOURCE_ATTRIBUTES` (zmienna środowiska per
  uruchomienie). W aplikacji desktop i w chmurze jedna sesja = jeden agent, więc rola jest atrybutem sesji; metryki
  subagentów mają własne `agent.name`.
- **Nie włączać** `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_RAW_API_BODIES` – treści promptów i
  narzędzi zawierają dane osobowe i sekrety; metryki i zdarzenia bez treści wystarczą do kosztów.

## Langfuse (self-host w UE)
- Docker Compose na VPS firmy (Postgres + ClickHouse + Redis + Langfuse); domena `langfuse.<domena>`; dostęp tylko
  dla operatora, CEO (odczyt przez API) i agenta finansowego (odczyt).
- Kolektor OTel (otel-collector-contrib) przyjmuje OTLP z Claude Code i eksportuje do Langfuse (endpoint
  `/api/public/otel`) – konfiguracja w `toolbelt/uslugi/langfuse.md` po pierwszym wdrożeniu (etap E).
- Alternatywa bez własnego serwera: Prometheus + Grafana Cloud (darmowy limit) tylko na metryki kosztów.

## Budżety
- `flota/zadania.yaml`: `budzet_usd_przebieg` (twardy limit `--max-budget-usd` w headless) i `budzet_usd_dzien`
  (miękki: `scripts/przebieg.sh` wypisuje `BUDŻET-AGENTA`, agent pracuje tylko w trybie ZDARZENIE).
- Budżet całej floty: limit konta (zadanie `limit`) i próg pojemności (P3 ≥ 85%, P2 ≥ 95%).
- PM w piątek: koszt per zadanie cykliczne kontra wartość (`backlog.md`, sekcja „Cykliczne”).
