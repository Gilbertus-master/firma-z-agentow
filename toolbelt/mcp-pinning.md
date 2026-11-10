# Serwery MCP: zaufanie, pinning, screening (OWASP MCP Top 10 – MCP03 Tool Poisoning, MCP08 audyt)

1. **Źródło, nie nazwa.** Serwer trafia do toolbeltu tylko z oficjalnego adresu dostawcy (`toolbelt/katalog.md`, kolumna „Status”);
   lokalne serwery z `.mcp.json` tylko z podpisanego/pinowanego źródła. Hook widzi `mcp_server.source` – zaufanie wg źródła.
2. **Screening przed podłączeniem** (agent bezpieczeństwa, checklista): opisy narzędzi bez instrukcji dla modelu („ignore…”, „always…”),
   bez ukrytego Unicode, bez ścieżek do `~/.ssh`, `.env`; narzędzia zapisu wymienione i zmapowane na `uprawnienia.yaml`.
3. **Pinning odcisków.** `toolbelt/mcp-odciski.tsv`: serwer · wersja · SHA-256 listy narzędzi (nazwa+opis+schemat) · data · kto sprawdził.
   Odcisk liczy `python3 -I toolbelt/mcp-odcisk.py <plik-z-lista-narzedzi.json>` (listę narzędzi eksportuje sesja: `ToolSearch`/`/mcp`).
   Zmiana odcisku bez wpisu = alert strażnika (kontrola planowana) i zakaz użycia narzędzi zapisu do przeglądu.
4. **Minimalny zakres.** Konektor włączony tylko dla ról, które go potrzebują (kontrakt agenta w `flota/zadania.yaml → narzedzia`);
   narzędzia zapisu za `tool-approval`/hookiem. Zakaz token passthrough (spec MCP): serwer nie dostaje cudzych tokenów.
5. **Audyt.** Każde wywołanie MCP jest w `bezpieczenstwo/audyt/` (hook, pre i post).
