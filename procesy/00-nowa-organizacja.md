# Proces 00 – nowa organizacja agentyczna od zera

Cel: w ok. 2 tygodnie od decyzji właściciela organizacja działa z CEO, rdzeniem zarządczym i pierwszymi agentami
dziedzinowymi. Człowiek wykonuje tylko kroki oznaczone **[operator]** albo **[właściciel]**.

Zasada startu: **flota rośnie etapami.** Każdy etap ma bramkę – następny startuje dopiero, gdy poprzedni przez
3 dni ma przebiegi z wynikiem OK (`przebiegi/`) i nie ma otwartych alertów strażnika. W organizacji źródłowej 21 agentów
powstało w kilka dni, a mechanizmy niezawodności (kontrakt przebiegu, strażnik, zajmowanie pracy) dopisywano po
incydentach. Tu są od pierwszego dnia.

## Etap 0 – decyzja i konfiguracja (dzień 0, właściciel + Claude w czacie)
1. **[właściciel]** Teza biznesowa na 1 stronę: co, dla kogo, model przychodu, czego nie robimy.
2. Skopiuj szablon: `gh repo create OWNER/<firma>-agenci --private --template Gilbertus-master/firma-z-agentow`
   i sklonuj do `~/projekty/<firma>-agenci`.
3. **Jedno polecenie:** `scripts/init-org.sh --nazwa "…" --domena … --prefiks … --github OWNER/<firma>-agenci --operator …`
   – wypełnia `org.yaml`, wpisuje decyzję startową `D-…-01`, tworzy agentów rdzenia (ceo, pm, recenzent), zakłada
   etykiety Issues, generuje prompty, uruchamia testy i wypisuje listę zadań do założenia oraz kroki dla operatora.
   Ręcznie dopisz w `org.yaml` mandat, budżet i próg zgody.
4. Przejrzyj `uprawnienia.yaml` – startowo ostrożnie.
5. Wypełnij `polityki/` (cennik, zwroty, rabaty, ton komunikacji) – choćby wersje 0.1.
6. `git push` (repo prywatne) i sekrety Actions `STRAZNIK_TOKEN` (+ opcjonalnie `STRAZNIK_RESEND_KEY`) – strażnik
   floty (`.github/workflows/straznik.yml`) rusza sam co 15 min, bez laptopa.

## Etap 1 – tożsamość prawna i konta (dni 1–5, operator)
Kroki przygotowuje agent CEO (po etapie 2 – do tego czasu Claude w czacie), operator wykonuje:
1. **[operator]** Spółka (np. sp. z o.o. przez S24): zarząd i beneficjent rzeczywisty (CRBR) to osoby fizyczne.
2. **[operator]** Konto firmowe w banku (KYC), dostęp do odczytu przez agregator PSD2.
3. **[operator]** Domena, poczta: adresy funkcyjne (kontakt@, support@, legal@, privacy@, security@, accounting@,
   tax@, sales@, investors@) przez Resend/AgentMail.
4. **[operator]** Menedżer sekretów (1Password / Infisical) z kontem usługowym dla agentów.
5. **[operator]** Konta usług z `toolbelt/katalog.md` potrzebne w etapach 2–3 (GitHub, Stripe, program
   fakturowy, KSeF – nadanie uprawnień profilem zaufanym).
6. **[operator]** Konto Claude (plan z Routines) i konektory MCP z toolbeltu.

## Etap 2 – rdzeń zarządczy (dni 3–7)
1. Agenci rdzenia są z etapu 0 (`init-org.sh`); uzupełnij `ceo/kpi/kpi.md` (O1–O3) i `ceo/plan/` (rok, kwartał,
   pierwszy tydzień).
2. Sprawdź w zakładce Actions, że strażnik floty ma zielone przebiegi (alerty: `zlecenia/ceo.md`, `ceo/straznik-zdarzenia.md`,
   mail do operatora, gdy jest klucz Resend).
3. Zadania agentów rdzenia – zależnie od `org.yaml → runtime.glowny`:
   - **`claude-routines` (zalecane, bez laptopa):** `python3 flota/generuj.py --routines --tylko limit,scalanie,ceo,pm,recenzent`
     → `ceo/handoff/routines/<agent>.md` z gotowymi polami (cron `CRON_TZ=…`, model, effort, repo, konektory, prompt);
     **[operator]** zakłada każde na claude.ai/code/routines albo przez `/schedule` i klika „Run now”;
   - **`desktop-scheduled`:** `python3 flota/generuj.py --lista --konto A --tylko …` → zadania w aplikacji Claude;
   - **`agent-sdk` (własny serwer):** cron wywołuje `scripts/przebieg-headless.sh <agent>` – twardy limit kosztu
     i zapis kosztu do `przebiegi/<agent>/koszty-*.jsonl`.
   Każde zadanie uruchom raz ręcznie, żeby nie stało na pytaniu o zgodę.
4. Telemetria kosztów (`toolbelt/obserwowalnosc.md`): **[operator]** włącza OTel w `~/.claude/settings.json` maszyny
   przebiegów albo w zmiennych cloud environment; bez tego koszt widać tylko z wrappera headless i limitu konta.
5. Bramka: 3 dni przebiegów CEO i PM z wynikiem OK; CEO prowadzi `operator/kolejka.md` i `ceo/do-decyzji.md`.

## Etap 3 – pierwsza linia przychodu i ryzyka (tydzień 2)
1. Wybór według tezy: zwykle `marketing`, `sprzedaz` albo `obsluga` + `recepcja`, oraz `prawny`, `compliance`, `ochrona-danych` (gdy są dane osobowe – od startu),
   `ksiegowy`, `finansowy`.
2. Każdy agent: `scripts/nowy-agent.sh <rola>`, wiersz w `koordynacja-odstepy.tsv` i `flota/zadania.yaml`,
   tabela źródeł w `pm/specyfikacje/kontrakt-przebiegu.md` (sekcja 4), `python3 -m unittest discover flota`.
3. Agenci czytający niezaufane treści (obsługa, recepcja) – zestaw testów wstrzyknięć w `ewaluacje/` przed startem.
4. Bramka: 3 dni bez alertów, zgłoszenia obsłużone w SLA.

## Etap 4 – produkt i pełna flota (tydzień 3+)
1. `architekt`, `inzynier`, `tester` – proces `procesy/10-budowa-produktu.md`; przy aplikacjach w sklepach i wielu językach także `aplikacje` i `lokalizacja` (wydania: `procesy/40-wydanie.md`).
2. `bezpieczenstwo`, `podatkowy`, `wywiad`, `inwestorzy` – gdy jest czego pilnować. Każde powołanie według `procesy/60-cykl-zycia-agenta.md` (bramka 3 dni), przeglądy miesięczne według `procesy/50-przeglad-agenta.md`.
3. Piony z liderami i raporty pionów (od 4 agentów dziedzinowych w pionie).

## Ciągłe
- Co tydzień CEO: KPI „minuty operatora”, propozycje poluzowania `uprawnienia.yaml` i usunięcia człowieka z pętli.
- Co tydzień PM: koszt floty, zasadność zadań cyklicznych, sprzeczności decyzji.
- Co miesiąc właściciel: przegląd mandatu, budżetu i uprawnień (30 min, na podstawie raportu CEO).
