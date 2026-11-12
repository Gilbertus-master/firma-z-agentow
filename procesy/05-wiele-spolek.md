# Proces 05 – wiele spółek na jednym szablonie

Cel: właściciel prowadzi kilka organizacji agentycznych z jednego szablonu, a każda spółka jest **odizolowana** (limity, sekrety, dane,
odpowiedzialność) i jednocześnie **dostaje poprawki szablonu** bez ręcznego przepisywania. Decyzja z raportu (rozdz. 6, pkt 5): osobne
konta i organizacja GitHub per spółka.

## 1. Zasada: jedna spółka = jedna tożsamość

| Zasób | Per spółka | Dlaczego osobno |
|---|---|---|
| Konto Claude (plan z zadaniami chmurowymi, DPA) | tak | limity i koszty rozliczane na spółkę; umowa powierzenia danych wobec właściwego administratora (`bezpieczenstwo/rejestr-ai.md`) |
| Organizacja GitHub + prywatne repo organizacji `<spolka>-agenci` (+ repo produktu) | tak | role Read/Triage/Write i zespoły są tylko w organizacji; rozliczalność commitów |
| Domena i skrzynki funkcyjne, menedżer sekretów (osobny sejf), klucze płatności, konta usług z toolbeltu | tak | sekret jednej spółki nigdy nie leży obok sekretu drugiej; incydent nie przenosi się między spółkami |
| Konto techniczne agentów (GitHub App / konto usługowe) | tak | token spółki A nie otwiera repo spółki B |
| Operator i właściciel | mogą być ci sami ludzie | role zostają rozdzielone w każdej spółce (`org.yaml → ludzie`); KPI „minuty operatora” liczone per spółka |
| Szablon `agentyczna-organizacja` | wspólny (upstream) | jedno miejsce poprawek; spółki niczego nie współdzielą poza nim |

Nic nie jest współdzielone „na skróty” (jeden klucz, jedna skrzynka dla dwóch spółek) – to zawsze decyzja właściciela `D-…` z uzasadnieniem
i wpisem w rejestrze spółek.

## 2. Start spółki z szablonu

1. **[właściciel]** Wiersz w rejestrze spółek (sekcja 5) z nazwą, mandatem i budżetem floty.
2. **[operator]** Organizacja GitHub, repo `<spolka>-agenci` z szablonu (`gh repo create … --template` albo klon + `git remote rename origin szablon`),
   repo **prywatne**; konto Claude spółki; menedżer sekretów (sejf spółki).
3. `scripts/init-org.sh …` (proces 00, etap 0) – wypełnia `org.yaml`; w `org.yaml → repo.szablon` wpisać upstream (`Gilbertus-master/firma-z-agentow`
   albo pełny URL) – to źródło dla aktualizacji.
4. Dalej jak proces 00 (etapy 1–4). Każda spółka ma własne `decyzje/`, `polityki/`, `uprawnienia.yaml`, agentów i flotę.

## 3. Aktualizacja z szablonu

Skrypt: `scripts/aktualizuj-z-szablonu.sh [--sucho] [--url …] [--galaz main]` w repo spółki (test: `scripts/test-aktualizuj.sh`).
1. Dodaje/aktualizuje remote `szablon` (URL z argumentu albo `org.yaml → repo.szablon`), pobiera gałąź szablonu.
2. Pokazuje `git diff --stat` zmian szablonu **bez ścieżek lokalnych**; `--sucho` kończy tutaj.
3. Wymaga czystego drzewa roboczego; scala `git merge --no-commit`; dla ścieżek z `.szablon-lokalne` przywraca wersję spółki
   (`git checkout HEAD -- <plik>`), a **nowe pliki szablonu w ścieżkach lokalnych pomija i wypisuje** (operator kopiuje ręcznie, jeśli chce).
4. Konflikt poza ścieżkami lokalnymi → scalanie zostaje w toku, skrypt wypisuje pliki i instrukcję (rozwiąż → `git add` → `git commit`
   albo `git merge --abort`), kod 3. Bez konfliktów → commit `szablon: aktualizacja do <sha7>`.
5. Po scaleniu: `python3 flota/generuj.py && python3 flota/generuj.py --routines` (prompty i instrukcje zadań są lokalne – generowane
   z manifestu spółki), testy z `README.md`, PR do gałęzi głównej spółki → werdykt recenzenta spółki → scalenie przez kolejkę scalania spółki
   (`ceo/scalanie/README.md`): taki PR dotyka ścieżek wyłączonych (klasa WYJATEK), więc scala go CEO pod blokadą, a przy zmianie
   `zasady.md` / `uprawnienia.yaml` – dopiero z decyzją właściciela.

**Rytm:** raz w miesiącu (pierwszy PEŁNY przebieg CEO po przeglądzie agentów – proces 50) albo zdarzeniowo, gdy szablon ogłasza poprawkę
bezpieczeństwa (hook, strażnik). Wykonuje CEO spółki w PR-ze albo operator; aktualizacja nie jest czynnością zewnętrzną, scalenie PR-a – tak
(`pr_scalenie_bez_migracji`).
Po każdej aktualizacji (i co najmniej raz w tygodniu) CEO spółki mierzy zbieżność szkieletu `python3 -I scripts/zgodnosc.py` i wysyła
rekord `zgodnosc` (procesy/16-wymiana-ceo.md, sekcja 6); odstępstwo trwałe = wpis w `.szablon-lokalne` z powodem w komentarzu.

### Co wolno nadpisać lokalnie, a co płynie z szablonu

| Płynie z szablonu (merge; konflikt = pytanie do operatora) | Lokalne (`.szablon-lokalne` – szablon ich nie zmienia) |
|---|---|
| `zasady.md` – konstytucja (zmiana sekcji A w szablonie = właściciel **każdej** spółki potwierdza decyzją `D-…` przy scaleniu) | `org.yaml`, `uprawnienia.yaml`, `.szablon-lokalne` |
| `.claude/` (hook uprawnień, skille, ustawienia), `moduly/straznik/`, `scripts/`, `flota/generuj.py`, `flota/szablony/`, testy | `polityki/`, `decyzje/`, `decyzje.md`, `ryzyka.md` (treść spółki), `backlog.md`, `rejestr-sesji.md` |
| `role/*.md`, `role/szablony/`, `procesy/`, `docs/`, `toolbelt/*.md` (katalog, zasady), `ewaluacje/_startowe/`, `ewaluacje/*.py` | `koordynacja-odstepy.tsv`, `flota/zadania.yaml`, `flota/etykiety.tsv`, `ceo/handoff/prompty/`, `ceo/handoff/routines/` (generowane) |
| `pm/specyfikacje/`, `pm/narzedzia/`, `ceo/kpi/kpi.md` (szkielet F1–F12 – spółka dopisuje swoje O/K/A w osobnych sekcjach; konflikt możliwy) | katalogi agentów: `*/agent.md`, `*/dziennik.md`, `*/stan.json`, `*/backlog.md`, `*/wiedza/`, `*/analizy/`, `*/szkice/`, rejestry ról |
| `README.md`, `PRZECZYTAJ-NAJPIERW.md`, `CLAUDE.md` | `zlecenia/`, `przebiegi/`, `incydenty/`, `bezpieczenstwo/audyt/`, `bezpieczenstwo/blokady.jsonl`, `bezpieczenstwo/rejestr-ai.md`, `toolbelt/mcp-odciski.tsv`, `ewaluacje/<agent>/`, `operator/kolejka.md`, `ceo/do-decyzji.md`, `ceo/plan/`, `ceo/straznik-zdarzenia.md`, `ceo/scalanie/stan.json`, `ceo/scalanie/dziennik.jsonl`, `ceo/kontrole/wyniki.jsonl`, `recenzent/szablony/`, `.github/workflows/straznik.yml` (harmonogram włącza `init-org.sh`) |

Spółka może dopisać ścieżkę do `.szablon-lokalne` (np. własny proces `procesy/45-…` – i tak nie koliduje) albo ją usunąć (np. chce
przyjmować `uprawnienia.yaml` z szablonu) – to decyzja CEO spółki zapisana w dzienniku. Zmiana `role/<rola>.md` lokalnie jest dozwolona,
ale lepiej: uogólnić i wysłać do szablonu (sekcja 4), a lokalne doprecyzowania trzymać w `<agent>/agent.md` (lokalny).

## 4. Zmiany płynące w górę (spółka → szablon)

Lekcja spółki (incydent, reguła podręcznika, lepszy rejestr, nowa kontrola strażnika) trafia do szablonu PR-em **po uogólnieniu**:
bez nazwy spółki, ID projektów, adresów, osób, kwot – „właściciel”, „operator”, „repo produktu”. Autor: agent spółki (zlecenie od CEO) albo
operator; recenzent szablonu daje werdykt; testy szablonu zielone. Nigdy odwrotnie: dane spółki nie trafiają do szablonu, a szablon nie
dostaje sekretów ani plików z `.szablon-lokalne`.

## 5. Rejestr spółek u właściciela

Prowadzi właściciel **poza repozytoriami spółek** (każda spółka widzi tylko siebie): prywatne repo właściciela albo menedżer dokumentów.
Bez danych osobowych i sekretów – nazwy pozycji w menedżerze sekretów, nie loginy.

| Spółka | Repo organizacji | Organizacja GitHub | Konto Claude (pozycja w sejfie) | Operator (rola / SLA) | Wersja szablonu (sha7 / tag) | Ostatnia aktualizacja | Budżet floty USD/mies. | Uwagi |
|---|---|---|---|---|---|---|---|---|

Przegląd: raz w miesiącu właściciel (30 min, z raportami CEO spółek): spółki z wersją szablonu starszą niż 2 aktualizacje → zlecenie
aktualizacji; wspólne lekcje → PR do szablonu; nic nie jest współdzielone poza szablonem.
