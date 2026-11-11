# Toolbelt – katalog zewnętrznych wtyczek

Zasada: **nie piszemy tego, co da się podłączyć.** Każdy obszar firmy obsługuje gotowa usługa sterowana przez agenta
(MCP, CLI albo API). Własny kod piszemy tylko tam, gdzie nie ma usługi albo gdzie jest przewaga konkurencyjna.

Pomysł z praktyki innych zespołów: agent ma z góry przygotowany pas narzędzi – usługi, w
których jest już zalogowany, z opisem użycia i gotowymi fragmentami kodu – i sam zakłada w nich projekt, zamiast
pisać integrację od zera.

Legenda statusu: **MCP-ofic.** – oficjalny serwer MCP dostawcy · **MCP-społ.** – serwer społeczności · **CLI** ·
**API** – tylko REST. „sprawdzone” – używane w organizacji źródłowej. „?” – niepotwierdzone w researchu 9.11.2026,
do sprawdzenia przed wyborem. Kolumna „Kto” – agent, który ma dostęp (zasada minimalnych uprawnień).

## Rdzeń (każda organizacja)

| Obszar | Wybór domyślny | Alternatywy | Status | Kto | Uwagi |
|---|---|---|---|---|---|
| Runtime agentów | Claude Code: Routines (chmura) | zadania zaplanowane w aplikacji desktop; Claude Agent SDK; Managed Agents | sprawdzone (desktop) | wszyscy | Routines nie wymagają włączonego laptopa; desktop tylko do GUI |
| Warstwa organizacji | to repo (pliki + Issues) | Paperclip (open source, MIT: schemat organizacyjny, budżety, zatwierdzenia, audyt) | sprawdzone | wszyscy | Paperclip do przetestowania jako panel nad Claude Code (etap 4 planu) |
| Repo i zlecenia | GitHub + `gh` CLI | Linear (MCP-ofic.) | sprawdzone | wszyscy | jedno konto techniczne na agenta = rozliczalność |
| Metodyka pracy | wtyczka superpowers (brainstorming, writing-plans, TDD, code review, verification) | – | sprawdzone | architekt, inżynier | specyfikacje i plany w repo produktu |
| Sekrety | 1Password CLI (`op run`) albo Infisical | pęk kluczy macOS (tylko pojedynczy Mac) | sprawdzone: pęk kluczy | wg zadania | `toolbelt/sekrety.md`; sekret nigdy w kontekście modelu |
| Obserwowalność agentów | OpenTelemetry z Claude Code → Langfuse (self-host w UE) | – | – | pm, ceo | koszt i wynik per agent i przebieg |
| Strażnik floty | `moduly/straznik` (Python bez LLM) w GitHub Actions co 15 min | launchd na Macu (`instaluj.sh`) | sprawdzone (launchd) | – | działa bez laptopa; sekret `STRAZNIK_TOKEN` |
| Powiadomienia do ludzi | PushNotification w aplikacji Claude + mail | – | sprawdzone | ceo | tylko operator i właściciel |

## Komunikacja

| Obszar | Wybór domyślny | Alternatywy | Status | Kto | Uwagi |
|---|---|---|---|---|---|
| Skrzynki agentów | Resend (skrzynki odbiorcze + wysyłka) | AgentMail (MCP-ofic., konektor Claude) | sprawdzone: Resend MCP-ofic. | recepcja, obsługa, agenci z adresem | każdy agent wysyła tylko ze swojego adresu |
| Domena i DNS | Cloudflare | OVH | sprawdzone: OVH | bezpieczeństwo (odczyt) | zmiany DNS → właściciel |
| Telefon / SMS | Twilio | Zadarma | API; MCP ? | obsługa | numer firmowy zakłada operator |
| Poczta właściciela | Gmail (konektor, odczyt i szkice) | – | sprawdzone | ceo | tylko odczyt; nic nie wysyłamy z prywatnej skrzynki |

## Wzrost i klienci

| Obszar | Wybór domyślny | Alternatywy | Status | Kto | Uwagi |
|---|---|---|---|---|---|
| CRM | Attio (MCP-ofic.) | HubSpot (MCP-ofic.) | research | sprzedaż | |
| Helpdesk | Plain (MCP-ofic.) | Intercom Fin (MCP-ofic.), Zendesk (MCP ?) | research | obsługa | reguła dwóch: obsługa nie zwraca pieniędzy |
| Social | Typefully (MCP-ofic.) | Buffer (?) | research | marketing | publikacja z kalendarza zatwierdzonego przez CEO |
| Analityka produktu | PostHog (MCP-ofic.) | – | research | marketing, architekt | |
| Strona | statyczna (GitHub Pages / Cloudflare Pages) | Fly.io, Vercel | sprawdzone: Pages, Fly | marketing, architekt | |
| Projekt graficzny | Claude Design / Stitch / generator z biblioteką komponentów | – | sprawdzone: Design | architekt, marketing | brzydkie makiety → kontrola zgodności ze specyfikacją → pełny projekt |

## Produkt i technologia

| Obszar | Wybór domyślny | Alternatywy | Status | Kto | Uwagi |
|---|---|---|---|---|---|
| Baza, logowanie, funkcje | Supabase (MCP-ofic., Management API) | WorkOS / Clerk (logowanie, ?) | sprawdzone | architekt, inżynier; reszta odczyt agregatów | migracje według `uprawnienia.yaml` |
| Hosting | Cloudflare / Fly.io | Vercel (MCP) | sprawdzone: Fly | architekt | |
| Błędy aplikacji | Sentry (MCP-ofic.) | – | research | tester, architekt, operacje | |
| Buildy mobilne | Codemagic | EAS (Expo) | sprawdzone | architekt | budżet minut! (wyczerpane minuty = błąd 402) |
| Sklepy z aplikacjami | App Store Connect API, Google Play API | – | sprawdzone | agent aplikacji | konta deweloperskie zakłada operator |
| Push | Firebase Cloud Messaging | – | sprawdzone | inżynier | |
| Subskrypcje mobilne | RevenueCat | – | do sprawdzenia | finansowy | sprawdzić Apple Small Business Program (15%) |
| Testy E2E | Playwright | – | sprawdzone | tester | |
| Dostępność (test automatyczny) | axe-core (CLI, też w Playwright) · Lighthouse (CLI) | – | ? | projektant, tester | |
| Analityka produktu | PostHog (MCP-ofic.?) · Plausible (API) | – | ? | analityk | |
| Monitoring dostępności usługi | monitor HTTP z alarmem (np. Better Stack, UptimeRobot) | – | ? | operacje | |
| Automatyzacje bez MCP | n8n (MCP Server Trigger, self-host) | Make | research | architekt | deterministyczna „rura” wywoływana przez agentów |

## Pieniądze, księgi, prawo

| Obszar | Wybór domyślny | Alternatywy | Status | Kto | Uwagi |
|---|---|---|---|---|---|
| Płatności | Stripe (MCP-ofic., Agent Toolkit) | – | sprawdzone: odczyt | finansowy (odczyt), CEO (zwroty wg polityki) | **od 12.2026 MCP przyjmuje tylko klucze z tagiem „Agent” – migracja do 30.11.2026** |
| Faktury PL + KSeF | Fakturownia (REST; MCP-ofic. tylko odczyt) | inFakt (REST, KSeF), wFirma (API ?) | sprawdzone: Fakturownia | księgowy | KSeF obsługuje program; faktury nie da się anulować |
| KSeF bezpośrednio | – | MCP-społ.: flippico/ksef-mcp, mcp-ksef-pl | research | księgowy | tylko gdy program fakturowy nie wystarcza |
| Bank | agregator PSD2 (odczyt) | Revolut Business API | research | finansowy, księgowy (odczyt) | przelewy wykonuje operator |
| Kursy walut | API NBP | – | sprawdzone | księgowy | |
| Podpis dokumentów | Docusign (MCP-ofic.) | Autenti (API ?) | research | prawny (przygotowanie) | podpis kwalifikowany składa operator |
| Kredyty chmurowe | Google for Startups, AWS Activate, programy AI | – | do sprawdzenia | finansowy | wnioski składa operator |

## Własne narzędzia szablonu (bez LLM)

To, czego nie dało się podłączyć: deterministyczny kod w repo. Biblioteka standardowa Pythona i bash, bez sieci (chyba
że zaznaczono), bez sekretów, każdy z testami w `bash scripts/testy.sh`. Agent **uruchamia** narzędzie i cytuje wynik –
nie liczy „w głowie”.

| Narzędzie | Polecenie | Kto | Co daje |
|---|---|---|---|
| Blokada przebiegu | `scripts/przebieg.sh start <agent> <konto>` | każdy agent | jeden przebieg na okienko przy wielu kontach (tag git), budżet pojemności P1–P3 |
| Regulator tempa | `python3 scripts/regulator.py --konto A --procent N --reset <ISO>` | zadanie `limit` | równe zużycie limitu konta, tryb przyspiesz/zwolnij, przekazanie pracy następnemu kontu |
| Przebieg bez aplikacji | `scripts/przebieg-headless.sh <agent>` | operator, serwer | `claude -p` z limitem kosztu i tur, koszt przebiegu w `przebiegi/` |
| Kontrakt przebiegu | `python3 -I pm/narzedzia/przebieg-raport.py dopisz\|sprawdz\|podsumuj` | każdy agent, pm | linia JSON na przebieg, walidacja, tabela 7 dni z kosztem |
| Backlog | `python3 -I pm/narzedzia/backlog.py [--sprawdz\|--json]` | pm | sekcja „Jednorazowe” ze zleceń i Issues; po terminie, duble, rozjazdy (sieć tylko przez `gh`) |
| Rejestr sesji | `python3 -I pm/narzedzia/sesje.py` | pm | sesje otwarte > 24 h, bez rodzica, dublety, zamknięte bez wyniku |
| Skan PR | `bash recenzent/skrypty/skan-pr.sh <nr>` | recenzent | dane osobowe, sekrety, prywatne adresy, polecenia dla agentów w dodanych liniach |
| Uzgodnienie recenzji | `bash recenzent/skrypty/uzgodnienie.sh [--json]` | recenzent | otwarte PR-y ↔ werdykty dla aktualnego head SHA (sieć: `gh`) |
| Model finansowy | `python3 finansowy/model/model.py [--zaklad cena=1.1,churn=0.9]` | finansowy, ceo | BEP, EBITDA, runway, scenariusze, ranking dźwigni; wariant „co jeśli” z Δ BEP i Δ EBITDA |
| Pomiar KPI | `python3 -I ceo/kpi/pomiar.py [--sprawdz\|--trend F4]` | ceo, pm | wartości, kolory i trend wskaźników z `zrodla.yaml` (`--z-siecia` dla źródeł z API) |
| Strona planu i KPI | `python3 ceo/plan/strona/zbuduj.py` | ceo | jeden plik HTML: plan, KPI, BEP, portfel, koszty, bezpieczniki; odmawia zapisu z danymi osobowymi |
| Indeks decyzji | `python3 -I scripts/decyzje-indeks.py [--sprawdz\|--archiwizuj]` | ceo | `decyzje.md` z plików `D-*.md`, sprzeczne decyzje = błąd |
| Flota | `python3 flota/generuj.py [--sprawdz\|--routines\|--lista]` | ceo, operator | prompty i zadania z jednego manifestu; rozjazd = błąd |
| Strażnik | `python3 moduly/straznik/straznik.py` | CI (cron) | cisza agentów, kolejki, budżety, HALT, dead-letter – alert bez LLM |
| Hook uprawnień | `.claude/hooks/uprawnienia.py` (uruchamia Claude Code) | – | egzekwuje `uprawnienia.yaml`, bramki z `polityki/progi.yaml`, łańcuch audytu |
| Ewaluacje | `python3 -I ewaluacje/uruchom.py [<agent>]` | recenzent, CI | scenariusze adwersaryjne przed zmianą instrukcji (jedyny runner z modelem) |
| Nowa firma / nowy agent | `scripts/init-org.sh`, `scripts/nowy-agent.sh <rola>` | operator, ceo | start organizacji jednym poleceniem; rola z rejestrami startowymi |
| Aktualizacja z szablonu | `scripts/aktualizuj-z-szablonu.sh [--sucho]` | ceo, operator | poprawki szablonu do spółki bez nadpisania jej plików |
| Suita testów | `bash scripts/testy.sh` | każdy, CI | testy powyższych narzędzi |

## Jak dodać usługę do toolbeltu
1. Agent proponuje usługę zleceniem do architekta: po co, alternatywy, koszt, czy ma MCP, jakie dane przetwarza.
2. Compliance: umowa powierzenia (DPA), transfer poza EOG, wpis w rejestrze czynności.
3. Bezpieczeństwo: zakres klucza (minimalny), gdzie leży sekret, kto ma dostęp.
4. Operator zakłada konto (KYC, 2FA) i wkłada sekret do menedżera sekretów.
5. Architekt dopisuje wiersz tutaj i opis użycia w `toolbelt/uslugi/<usluga>.md` (jak się zalogować z CLI,
   przykładowe wywołania, limity, koszty). Kontrola dostępów: `toolbelt/sprawdz-dostepy.md`.
6. Własne narzędzie (gdy usługi nie ma): skrypt z testem, wiersz w tabeli „Własne narzędzia” i w `scripts/testy.sh` – w jednym PR.
