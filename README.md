# Organizacja agentyczna – darmowy rdzeń

[English edition → Gilbertus-master/company-of-agents](https://github.com/Gilbertus-master/company-of-agents) · Edycja polska jest źródłowa; angielska jest jej tłumaczeniem.
Warunki licencji określa wyłącznie angielski tekst w pliku `LICENSE` – opisy po polsku mają charakter informacyjny.

Repozytorium git, które prowadzi małą flotę agentów Claude Code jak organizację: agent CEO, kierownik projektów (PM),
recenzent, architekt, regulator limitu i agent scalający – z zabezpieczeniami, dzięki którym flota może pracować bez nadzoru.
W pętli zostają dwie osoby: **właściciel** (decyzje) i **operator** (konta, sekrety i wszystko, czego agentom nie wolno).

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
| Minimalny start: pięć zadań zaplanowanych (`limit`, `scalanie`, `ceo`, `recenzent`, `pm`); `architekt` – cotygodniowe aktualizacje i zgłoszenia – dochodzi jako następny | `flota/zadania.yaml` |

Poza rdzeniem (część pełnego szablonu): biblioteka kolejnych ról, kontrole menedżerskie i KPI, model rentowności,
polityki firmy i procesy biznesowe.

## Szybki start
```bash
gh repo create <ty>/<firma>-agenci --private --template Gilbertus-master/firma-z-agentow --clone
cd <firma>-agenci
scripts/init-org.sh --nazwa "Nowa Firma" --domena nowafirma.example --prefiks nf \
  --github <ty>/<firma>-agenci --operator operator@nowafirma.example --runtime claude-routines \
  --dziel-sie nie          # obowiązkowy, jawny wybór: tak albo nie – patrz „Dzielenie się ulepszeniami”
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

## Dzielenie się ulepszeniami – jawny wybór właściciela
Ten projekt może uczyć się od flot, które z niego korzystają – ale tylko wtedy, gdy właściciel firmy świadomie to włączy.
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

Innej telemetrii nie ma.

## Aktualizacje
W każdy poniedziałek architekt uruchamia `scripts/aktualizuj-z-szablonu.sh --pr`: najnowsze wydanie przychodzi jako PR, który
przechodzi przez recenzenta i kolejkę scalania. Zmiany w `zasady.md` i `.claude/` czekają na decyzję właściciela.

## Licencja i współtworzenie
Apache-2.0 (`LICENSE`, `NOTICE`). Wkład: `CONTRIBUTING.md` (podpis DCO, bez CLA). Podatności: `SECURITY.md`.
Zależności: Python 3 z biblioteką standardową i PyYAML (licencja MIT), `git`, `gh` – nie są częścią tego repozytorium.

> **Znaki towarowe i brak powiązania.** Ten projekt jest niezależny. Nie jest produktem Anthropic PBC, nie jest przez Anthropic
> sponsorowany, zatwierdzony ani wspierany i nie jest z Anthropic powiązany. Claude, Claude Code i Anthropic są znakami
> towarowymi Anthropic PBC. GitHub, Stripe i inne wymienione nazwy należą do ich właścicieli. Nazwy te służą wyłącznie do
> wskazania, z jakimi usługami szablon współpracuje.
