# Wtyczki (pluginy) Claude dla floty – mapa rola → wtyczka

Wtyczki działają na koncie Claude, na którym są włączone (konto floty – `flota/konto-start.md`). Instaluje operator.
Zasady (z organizacji źródłowej, 7.11.2026, uogólnione):
1. Skille z wtyczek to **sposób pracy** (listy kontrolne, szablony) – nie zmieniają `zasady.md` ani `uprawnienia.yaml`:
   czynności zewnętrzne nadal przez hook i decyzje.
2. Wtyczki z serwerami MCP firm trzecich – tylko po wpisie w `toolbelt/katalog.md`, opinii ochrony danych (DPA) i screeningu
   (`toolbelt/mcp-pinning.md`).
3. Pierwszeństwo: wtyczki Anthropic i oficjalnych partnerów; społecznościowe – tylko lokalne, po przeglądzie bezpieczeństwa.
4. Agent zapisuje w dzienniku, którego skilla użył; PM co miesiąc usuwa nieużywane z mapy.

## Rekomendowane – poziom 1 (Anthropic / partner oficjalny)
| Wtyczka | Role | Najważniejsze skille |
|---|---|---|
| superpowers | architekt, inżynier, CEO | brainstorming, writing-plans, test-driven-development, code review, verification |
| Legal / commercial-legal / ip-legal | prawny, sprzedaż | review-contract, compliance-check, NDA i umowy, renewal-tracker, oss-review |
| privacy-legal / ai-governance-legal | ochrona danych, compliance | dpa-review, dsar-response, DPIA, ai-inventory, vendor-ai-review |
| Finance / Data | finansowy, księgowy, CEO | close-management, reconciliation, variance-analysis, sql-queries, dashboard |
| Marketing / Product Marketing | marketing | kampanie, brand voice, pozycjonowanie, persony |
| Sales | sprzedaż | account-research, call-prep, draft-outreach (tylko ze zgodą – `polityki/outbound.md`), pipeline-review |
| Customer Support | obsługa, recepcja | ticket-triage, draft-response, kb-article, escalation |
| Product Management / Operations | architekt, PM, CEO | write-spec, roadmap, capacity-plan, runbook, risk-assessment, status-report |
| Design | marketing, architekt, aplikacje | design-critique, UX copy, dostępność |
| oficjalne wtyczki dostawców ze stosu (np. Supabase) | architekt, bezpieczeństwo | najlepsze praktyki bazy, RLS, auth |

## Poziom 2 (społecznościowe, lokalne – po przeglądzie bezpieczeństwa)
| Wtyczka | Role | Do czego |
|---|---|---|
| audyt bezpieczeństwa (OWASP, threat model) | bezpieczeństwo, architekt | OWASP Top 10 / LLM, ship-check |
| kontrola zależności (CVE, licencje) | bezpieczeństwo | alerty zależności |
| projekt aplikacji mobilnych | aplikacje, architekt | konwencje platform |

## Nie teraz
Płatne integracje wymagające kont – dopiero przy potrzebie i budżecie (decyzja D-…). Brak gotowych wtyczek dla KSeF i polskiego
prawa – zostają własne procesy agentów (`procesy/30-zamkniecie-miesiaca.md`, rola prawnego).
