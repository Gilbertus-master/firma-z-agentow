# Organizacja agentyczna – darmowy rdzeń

[English edition → Gilbertus-master/company-of-agents](https://github.com/Gilbertus-master/company-of-agents) · Edycja polska jest źródłowa; angielska jest jej tłumaczeniem.
Warunki licencji określa wyłącznie angielski tekst w pliku `LICENSE` – opisy po polsku mają charakter informacyjny.

Repozytorium git, które prowadzi małą flotę agentów Claude Code jak organizację: agent CEO, kierownik projektów (PM),
recenzent, architekt, regulator limitu i agent scalający – z zabezpieczeniami, dzięki którym flota może pracować bez nadzoru.
W pętli zostają dwie osoby: **właściciel** (decyzje) i **operator** (konta, sekrety i wszystko, czego agentom nie wolno).

> **Wymóg projektu: dziel się ulepszeniami.** To open source – chodzi o to, żeby razem rozwinąć ten szablon w lepsze
> rozwiązanie. Od każdego, kto z niego korzysta, wymagamy, żeby ulepszenia mechanizmów wracały tutaj: przez `--dziel-sie tak`
> przy zakładaniu firmy albo przez pull request. To zasada współpracy w tym projekcie, a nie warunek licencji – Apache-2.0
> jej nie wymusza. Co dokładnie wychodzi z Twojego repozytorium: sekcja „Dzielenie się ulepszeniami”. Prosimy też każdego,
> kto korzysta z kodu, o zgłoszenie „Zgłoś swój projekt” – sekcja „Jak wysyłać uwagi i odkrycia do wydawcy”.

> **Stan.** Rdzeń jest wydzielony z prywatnego szablonu, na którym pracuje prawdziwa flota. Przechodzi własne testy
> (`bash scripts/testy.sh`, bez sieci i bez LLM). Nikt spoza autorów nie uruchomił go jeszcze od początku do końca –
> spodziewaj się nierówności. Część plików wspomina elementy pełnego szablonu, których tu nie ma: `docs/poza-rdzeniem.md`.

> **Odpowiedzialność.** Szablon dostarczamy „tak jak jest” (Apache-2.0, sekcje 7–8). Nie jest poradą prawną, podatkową,
> finansową ani z zakresu ochrony danych. Agenci AI popełniają błędy. Uruchamiając flotę, stajesz się dostawcą lub podmiotem
> stosującym system AI i sam odpowiadasz za nadzór człowieka, za działania agentów (płatności, zwroty, wiadomości do klientów,
> publikacje) i za zgodność z prawem (m.in. AI Act – art. 50: osoby muszą wiedzieć, że rozmawiają z AI; RODO) oraz z warunkami
> dostawców (Anthropic, GitHub i innych). Decyzje prawne, podatkowe, kredytowe, kadrowe i inne obszary wysokiego ryzyka z Usage
> Policy Anthropic wymagają przeglądu przez kwalifikowaną osobę przed użyciem. Przed włączeniem czynności zewnętrznych
> skonsultuj konfigurację z prawnikiem. Opisy warunków Anthropic w tym repozytorium to nasza interpretacja ze stanu na
> 10.11.2026 – sprawdź aktualne brzmienie.

## Co jest w rdzeniu
| Mechanizm | Gdzie |
|---|---|
| Hook uprawnień działający „domyślnie odmawiam” – każdą czynność zewnętrzną sprawdza `uprawnienia.yaml`, a nie osąd agenta | `.claude/hooks/uprawnienia.py` |
| Dziennik audytu odporny na podmianę (łańcuch SHA-256) i plik HALT, który zatrzymuje flotę | `bezpieczenstwo/` |
| Strażnik bez LLM – pominięte przebiegi, zastój, zlecenia bez odpowiedzi; działa w GitHub Actions co 15 minut | `moduly/straznik/` |
| Kolejka scalania – skrypt liczy fakty, agent scalający scala, hook egzekwuje werdykt recenzenta | `scripts/scalanie.py`, `ceo/scalanie/` |
| Kontrakt przebiegu – każdy przebieg kończy się jedną linią JSON: wynik, obsłużone pozycje, co zostało | `pm/specyfikacje/kontrakt-przebiegu.md` |
| Pomiar kosztu – tokeny × cennik dla każdego przebiegu, z projekcją miesięczną | `scripts/koszt.py` |
| Ewaluacje ról, w tym scenariusze adwersaryjne | `ewaluacje/` |
| Aktualizacje szablonu jako cotygodniowy PR i zgłoszenia ulepszeń z powrotem do tego repozytorium | `scripts/aktualizuj-z-szablonu.sh`, `scripts/propozycje.py` |
| Wymiana odkryć i wydań między CEO projektów a wydawcą szablonu (jeden rekord = jedno zgłoszenie) i pomiar zbieżności szkieletu z szablonem | `procesy/16-wymiana-ceo.md`, `scripts/wymiana.py`, `scripts/odkrycia.py`, `scripts/zgodnosc.py` |
| Skaner danych osobowych w repo, rejestry wrażliwe bez danych w gicie, bramka skrótów zasad bezpieczeństwa | `scripts/skan-danych.py`, `scripts/rejestry-git.py`, `scripts/zasady_skroty.py` |
| Minimalny start: pięć zadań zaplanowanych (`limit`, `scalanie`, `ceo`, `recenzent`, `pm`); `architekt` – cotygodniowe aktualizacje i zgłoszenia – dochodzi jako następny | `flota/zadania.yaml` |

Poza rdzeniem (część pełnego szablonu): biblioteka kolejnych ról, kontrole menedżerskie i KPI, model rentowności,
polityki firmy i procesy biznesowe.

## Szybki start
```bash
gh repo create <ty>/<firma>-agenci --private --template Gilbertus-master/firma-z-agentow --clone
cd <firma>-agenci
scripts/init-org.sh --nazwa "Nowa Firma" --domena nowafirma.example --prefiks nf \
  --github <ty>/<firma>-agenci --operator operator@nowafirma.example --runtime claude-routines \
  --dziel-sie tak          # obowiązkowy, jawny wybór; projekt wymaga „tak” – patrz „Dzielenie się ulepszeniami”
python3 flota/generuj.py
bash scripts/testy.sh
```
Dalej według `docs/instrukcja-uruchomienia.md`: konto floty, rozliczenie (`team` albo `api`), zadania zaplanowane, pomiar
kosztu. Flota pracuje na **jednym** koncie; nie przełączaj jej między prywatnymi subskrypcjami.

## Wtyczka Claude Code
Skille rdzenia są też paczką wtyczki (`plugins/`, opis: `plugins/<nazwa>/README.md`) – to repozytorium jest jej katalogiem:
```
/plugin marketplace add Gilbertus-master/firma-z-agentow
/plugin install <nazwa>@<nazwa>
```
gdzie `<nazwa>` to nazwa tego repozytorium. Skill `nowa-organizacja` zakłada repo firmy i prowadzi przez pierwsze uruchomienie.
Wtyczka nie zawiera hooków ani uprawnień – zabezpieczenia floty działają w repo firmy.

## Jak wysyłać uwagi i odkrycia do wydawcy
Kanałem uwag i odkryć jest **to repozytorium** – zgłoszenia (Issues) i propozycje zmian (pull requesty). Trzy drogi, od najprostszej:

1. **Zgłoszenie w tym repozytorium** – wzory: „Propozycja ulepszenia”, „Wymiana – odkrycie” i „Zgłoś swój projekt”.
2. **Rekord procesu 16 jednym poleceniem** z repo Twojej firmy: `python3 -I scripts/wymiana.py wyslij <rekord.json> --zakazane "<nazwy firm, klientów>"`
   (rekord: `wymiana.py wzor odkrycie`, opis: `procesy/16-wymiana-ceo.md`). Domyślnym celem jest repo wydawcy tej edycji
   (`org.yaml → repo.szablon`), ale narzędzie wysyła dopiero po świadomym wyborze: `repo.dziel_sie_ulepszeniami: true`
   (`scripts/init-org.sh --dziel-sie tak`) albo `--publicznie` przy poleceniu. Bez tego kończy się kodem 3 i nic nie wychodzi;
   podgląd: `--na-sucho`. Nie potrzebujesz żadnych uprawnień w repo wydawcy: gdy repo nie przyjmie etykiet, narzędzie wysyła
   zgłoszenie bez nich, a etykiety (albo `poza-schematem` z powodem) nadaje workflow wydawcy `wymiana-etykiety.yml`.
3. **Propozycja zmiany** – pull request z podpisem DCO (`git commit -s`), zasady: `CONTRIBUTING.md`.

**Zgłoszenia są JAWNE** – widzi je każdy, razem z nazwą konta GitHub, z którego wyszły. Rekordy procesu 16 i propozycje z
`scripts/propozycje.py` przechodzą bramkę danych (e-maile, telefony, PESEL, NIP, IBAN, sekrety, nazwy z `--zakazane`), ale bramka
działa na wzorcach: nie wklejaj danych klientów, sekretów ani nazw firm.

**Zgłoś swój projekt.** Prosimy każdego, kto korzysta z tego kodu, o zapisanie się jako kontrybutor: zgłoszenie „Zgłoś swój
projekt” (skrót projektu, wersja szablonu, język, czy chcesz dostawać wydania). To zasada współpracy w tym projekcie, a nie
warunek licencji – Apache-2.0 jej nie wymusza. Przypomina o tym też komunikat końcowy `scripts/init-org.sh`.

## Dzielenie się ulepszeniami – jawny wybór właściciela
Projekt jest otwarty po to, żeby rozwijać go razem: wymagamy, żeby floty, które z niego korzystają, oddawały swoje
ulepszenia – wybierz `--dziel-sie tak`. Technicznie nic nie wychodzi bez świadomego włączenia przez właściciela firmy.
`scripts/init-org.sh` nie ma tu wartości domyślnej: wymaga `--dziel-sie tak` albo `--dziel-sie nie` (w terminalu pyta) i
zapisuje wybór w `org.yaml` oraz w decyzji startowej. Przy „nie” – i w repozytorium, w którym nie uruchomiono jeszcze
`init-org.sh` – nic nie wychodzi z Twojego repozytorium.

| | |
|---|---|
| **Włączenie** | Przy zakładaniu firmy: `scripts/init-org.sh … --dziel-sie tak` (wybór trafia do decyzji startowej `D-…-01` i do `org.yaml`). Później: decyzja właściciela zapisana w `decyzje/`, potem w `org.yaml`: `repo.dziel_sie_ulepszeniami: true` i `repo.dziel_sie_decyzja: "D-…"` (identyfikator tej decyzji). Bez identyfikatora decyzji skrypt nie wyśle niczego do tego repozytorium. |
| **Co może zostać wysłane** | Twoje zmiany w plikach *mechanizmów* względem wersji szablonu: `scripts/`, `.claude/skills/`, `.claude/hooks/`, `procesy/`, `role/`, `ewaluacje/`, `moduly/`, `flota/szablony/`, `flota/generuj.py`, `pm/narzedzia/`, `pm/specyfikacje/`, `recenzent/skrypty/`, `toolbelt/katalog.md`, `.github/workflows/` – oraz reguły z podręczników agentów, które pomogły co najmniej 3 razy i ani razu nie zaszkodziły (sam tekst reguły). |
| **Czego mechanizm nie zbiera** | Plików spoza powyższej listy: `org.yaml`, polityk, decyzji, zleceń, dzienników przebiegów, danych klientów i finansowych. Jeśli jednak taka treść znajdzie się w pliku z listy (na przykład w skrypcie albo w opisie roli), zostanie zebrana – dlatego jest bramka i podgląd. |
| **Bramka** | Przed wysyłką `scripts/propozycje.py sprawdz` odrzuca zgłoszenie, w którym znajdzie nazwę firmy, domenę, właściciela na GitHubie, adres kontaktowy, adresy e-mail, numery telefonów, PESEL, NIP, numer konta albo sekret. Bramka działa na wzorcach i nie rozpozna każdej poufnej treści. |
| **Kiedy i dokąd** | W poniedziałki, w przebiegu architekta (czyli nic nie wychodzi, dopóki nie dodasz tego agenta), jako **Issue w tym repozytorium – które jest publiczne**: zgłoszenie widzi każdy, razem z nazwą konta GitHub, z którego wyszło. Żeby wysyłać do własnego prywatnego repozytorium, ustaw `repo.skrzynka_propozycji`. |
| **Licencja** | Wysłana treść jest wkładem (Contribution) w rozumieniu sekcji 5 licencji Apache-2.0: udzielasz na nią licencji na warunkach Apache-2.0, w tym licencji patentowej z sekcji 3. Dla treści już wysłanej tej licencji nie da się cofnąć. Każde zgłoszenie zawiera oświadczenie o zgodzie właściciela i zgodności z Developer Certificate of Origin 1.1. Wysyłaj tylko to, do czego masz prawa. |
| **Co robi wydawca** | Zgłoszenia ocenia flota AI wydawcy pod nadzorem człowieka. Przyjęte ulepszenia trafiają do tego repozytorium na Apache-2.0; wydawca może je wykorzystać także w płatnych wersjach szablonu. Informacja o przetwarzaniu danych: `PRYWATNOSC.md`. |
| **Podgląd** | `python3 -I scripts/propozycje.py zbierz` pokazuje, co zostałoby wysłane; `propozycje/wyslane.jsonl` – co wysłano. |
| **Wyłączenie** | `org.yaml` → `repo.dziel_sie_ulepszeniami: false`. Od tej chwili nic nie wychodzi; to, co już opublikowano, pozostaje publiczne. |

Innej telemetrii nie ma. Rekordy procesu 16 (`scripts/wymiana.py`) idą do tego repozytorium tylko po tym samym świadomym
wyborze albo z `--publicznie` – sekcja „Jak wysyłać uwagi i odkrycia do wydawcy”.

## Aktualizacje
W każdy poniedziałek architekt uruchamia `scripts/aktualizuj-z-szablonu.sh --pr`: najnowsze wydanie przychodzi jako PR, który
przechodzi przez recenzenta i kolejkę scalania. Zmiany w `zasady.md` i `.claude/` czekają na decyzję właściciela.

## Zmiany
**0.2.0 (12.11.2026)**
- Proces 16 – wymiana odkryć i wydań między CEO projektów a wydawcą szablonu: `scripts/wymiana.py` (jeden rekord = jedno
  zgłoszenie, jeden schemat JSON, bramka danych przed wysyłką), `scripts/odkrycia.py` (szkice odkryć z commitów mechanizmów
  własnego repo), `scripts/zgodnosc.py` (zbieżność szkieletu z szablonem po ścieżkach i skrótach, bez historii git), wzory
  zgłoszeń, workflow etykiet po stronie wydawcy (`wymiana-etykiety.yml`, wysyłka bez uprawnień w repo wydawcy). W tej edycji kanałem jest publiczne repo wydawcy; wysyłka wymaga świadomego wyboru (`--dziel-sie tak` albo `--publicznie`).
- Skaner danych osobowych `scripts/skan-danych.py` (PESEL, NIP, IBAN, dokumenty z sumą kontrolną, e-maile spoza domeny firmy,
  telefony; wyjątki po SHA-256; `--staged` przed commitem) i `scripts/rejestry-git.py` (rejestry wrażliwe w gicie tylko z nagłówkami).
- Bramka skrótów zasad `scripts/zasady_skroty.py`: sekcja A `zasady.md` i blok zasad w treściach zadań nie zmienią się ani nie
  znikną bez decyzji właściciela; blok zasad także w treściach `limit` i `scalanie`.
- `scripts/zapisz.sh` (`scripts/przebieg.sh zapisz`): zapis końca przebiegu – commit tylko podanych ścieżek, rebase albo merge,
  push z ponowieniami i rozrzutem, nigdy `--force`; test wyścigu dwóch zapisów.
- Kolejka scalania: CI z ostatniego przebiegu każdego checku; warunek maszynowy `zielony <check> na head`; powiadamianie autora
  PR-a o werdykcie raz na SHA.
- Strażnik: alert do adresata kontroli (`zlecenia/<adresat>.md`), eskalacja do CEO i właściciela, rejestr alarmów
  (`moduly/straznik/eskalacja.py`); adresy maili alertów tylko w plist launchd.
- Hook uprawnień: nota kredytowa i zwrot przez MCP operatora płatności pod tym samym progiem kwotowym; odmowa przy więcej niż
  jednym zwrocie w poleceniu.
- Ścieżki lokalne przy aktualizacji z szablonu (stan kolejki scalania, wyniki ewaluacji, szablony recenzenta, workflow strażnika),
  `merge=union` dla każdego logu tylko-dopisywanego, test: żaden śledzony plik bez znaczników konfliktu.
- Kanał uwag i odkryć w publicznym repo wydawcy (sekcja „Jak wysyłać uwagi i odkrycia do wydawcy”) i wzór zgłoszenia
  „Zgłoś swój projekt”; prośba o zgłoszenie także w komunikacie końcowym `scripts/init-org.sh`.
- `scripts/propozycje.py`: baza zmian = najnowsza wspólna wersja z szablonem (`repo.szablon_baza`); `scripts/koszt.py`: ceny
  modeli z 11.11.2026 i progi cen dla długich promptów; `ceo/do-decyzji.md` – jedyne miejsce decyzji właściciela.

## Licencja i współtworzenie
Apache-2.0 (`LICENSE`, `NOTICE`). Wkład: `CONTRIBUTING.md` (podpis DCO, bez CLA). Podatności: `SECURITY.md`.
Zależności: Python 3 z biblioteką standardową i PyYAML (licencja MIT), `git`, `gh` – nie są częścią tego repozytorium.

> **Znaki towarowe i brak powiązania.** Ten projekt jest niezależny. Nie jest produktem Anthropic PBC, nie jest przez Anthropic
> sponsorowany, zatwierdzony ani wspierany i nie jest z Anthropic powiązany. Claude, Claude Code i Anthropic są znakami
> towarowymi Anthropic PBC. GitHub, Stripe i inne wymienione nazwy należą do ich właścicieli. Nazwy te służą wyłącznie do
> wskazania, z jakimi usługami szablon współpracuje.
