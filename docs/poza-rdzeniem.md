# Czego nie ma w rdzeniu

Rdzeń jest wydzielony z pełnego szablonu. Dokumenty rdzenia – zwłaszcza kontrakt przebiegu, katalog narzędzi, instrukcja CEO
i rejestr ryzyk – opisują organizację w pełnym kształcie, więc wspominają elementy, których tu nie ma. To nie błąd instalacji.
Agent, który trafi na takie odwołanie, pomija je i nie odtwarza brakującego pliku z pamięci (`CLAUDE.md`).

| Obszar pełnego szablonu | Ścieżki wspominane w rdzeniu | Co zrobić w rdzeniu |
|---|---|---|
| Biblioteka ról (inżynier, tester, obsługa, sprzedaż, marketing, finansowy, księgowy, podatkowy, prawny, compliance i inne) | `role/<rola>.md`, `role/szablony/<rola>/`, katalogi `obsluga/`, `sprzedaz/`, `marketing/`, `finansowy/`, `ksiegowy/`, `podatkowy/`, `inwestorzy/` | własną rolę dodajesz przez `scripts/nowy-agent.sh` i `procesy/60-cykl-zycia-agenta.md` |
| Kontrole menedżerskie CEO | `ceo/kontrole/kontrole.md`, `scripts/kontrole.py`, `procesy/55-…` | w rdzeniu zostaje tylko `ceo/kontrole/progi.yaml` – progi, z których korzysta kolejka scalania i hook |
| KPI, plan i portfel zakładów | `ceo/kpi/`, `ceo/plan/` | cel organizacji wpisujesz w `org.yaml`; plan prowadzisz w `backlog.md` |
| Program uczenia się i raporty CEO | `ceo/nauka/`, `ceo/raporty/` | reguły zbierasz w `ceo/wiedza/podrecznik.md` |
| Model rentowności (BEP, EBITDA) | `finansowy/model/` | koszt floty mierzy `scripts/koszt.py` |
| Polityki handlowe | `polityki/cennik.md`, `rabaty.md`, `zwroty.md`, `komunikacja.md`, `outbound.md` | w rdzeniu jest `polityki/progi.yaml`; własne polityki dodajesz jako pliki w `polityki/` |
| Procesy biznesowe | `procesy/10-…`, `20-…`, `30-…`, `40-…`, `50-…` | w rdzeniu: `00`, `05`, `15`, `60`, `90` |
| Skille okresowe | `/skrot-dnia`, `/przeglad-tygodnia`, `/przeglad-zarzadzania`, `/zamkniecie-miesiaca`, `/wydanie` | w rdzeniu: `/przebieg`, `/dyzur-pm`, `/recenzja`, `/incydent` |
| Raport i research źródłowy | `docs/raport/`, `docs/research/` | decyzje architektoniczne streszczają je w `docs/adr/` |

Dane testowe (`scripts/testdane/`, pliki `test_*`) celowo zawierają nazwy ról spoza rdzenia: testy sprawdzają zachowanie
mechanizmów dla pełnej floty.
