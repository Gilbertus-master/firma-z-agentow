# Konto floty, rozliczenie i regulator tempa

**Zasada (od 10.11.2026):** cała flota pracuje na **jednym koncie** – bez rotacji kont i bez przełączania floty na konto innej
osoby z wolnym limitem. Powód (nasza interpretacja, stan na 10.11.2026 – nie porada prawna; sprawdź aktualne brzmienie warunków): plany konsumenckie
(Free, Pro, Max, Ultra) podlegają Consumer Terms – zakaz udostępniania konta i użycie wyłącznie niekomercyjne (wersja dla
konsumentów z EOG, §11; w innych regionach sprawdź swoją wersję); na planie Team „Each seat is for one named individual”, a limitów „can't be transferred or shared
between team members”; Usage Policy zakazuje m.in. zakładania wielu kont w celu unikania wykrycia albo obchodzenia zabezpieczeń produktu
([Claude Code: Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance),
[Team plan](https://support.claude.com/en/articles/9266767-what-is-the-team-plan), [Usage Policy](https://www.anthropic.com/legal/aup)).
W organizacji pracują tylko dwie osoby: właściciel i operator.

## Warianty dopuszczalne według naszej interpretacji (`org.yaml → runtime.rozliczenie`)
| Wariant | Jak | Kiedy |
|---|---|---|
| `team` (domyślny) | plan Team (min. 2 miejsca: właściciel i operator); flota na miejscu premium operatora (`runtime.konto`); po wyczerpaniu limitu – płatna nadwyżka organizacji (usage credits) po stawkach API, z limitem wydatków ustawionym u Anthropic równym `runtime.nadwyzka_usd_miesiac` | zadania zaplanowane w chmurze (Routines) albo w aplikacji Claude |
| `api` | klucz API z Claude Console: `scripts/przebieg-headless.sh` (Agent SDK) z własnym harmonogramem; budżety USD z manifestu i pułap floty z HALT | własny serwer (`runtime.glowny: agent-sdk`) |
| Enterprise zużyciowy | bez limitów na miejsce, całość po stawkach API (warunki ustala Anthropic) | większa firma – ustaw `rozliczenie: api` |

Właściciel ma własne miejsce i własne użycie (czat, decyzje). Zadań floty nie zakłada się na jego miejscu.

## Regulator tempa – zadanie `<prefiks>-limit-<konto>` (co 30 min, pierwsze zadanie na koncie floty)
- Pomiar `get_usage` → `python3 scripts/regulator.py --konto <K> --procent N --reset <ISO> [--procent5h N --reset5h <ISO>]`.
- `cel_teraz` = 100 % × godziny od początku okna / `okno_celu_h` (domyślnie 168 h – równo przez cały tydzień);
  `odchylenie` = procent − cel.
- Tryby (plik `~/.<prefiks>-limit-<K>.json`, czyta `scripts/przebieg.sh`):

  | tryb | warunek | skutek |
  |---|---|---|
  | przyspiesz | odchylenie < −10 pp | wpis „Pilne: przyspiesz” w `zlecenia/ceo.md` (raz na 2 h); CEO dosypuje pracy; drugi dzień z rzędu → klasa `lekki` dostaje model klasy `mocny` (F-04) |
  | normalnie | −10 … +5 pp | bez zmian |
  | zwolnij | odchylenie > +5 pp (albo okno 5 h wyprzedzone o > 10 pp / ≥ 90 %) | P3 nie pracuje; przy > +15 pp także P2; P1 zawsze |
- Niezależnie: ≥ 85 % → P3 stop, ≥ 95 % → także P2 (budżet pojemności). Tryb starszy niż 2 h jest ignorowany.
- **Limit wyczerpany (≥ 98 %)**: jeden wpis Pilne na okno. Z płatną nadwyżką praca idzie dalej do limitu wydatków; bez niej do
  resetu pracuje tylko P1. Stałe wyczerpanie = decyzja właściciela (wyższe miejsce, nadwyżka albo rozliczenie `api`) – nie drugie konto.

## Pomiar kosztu (każdy przebieg)
Hook `SessionStart` zapisuje ścieżkę zapisu sesji; na końcu przebiegu `python3 -I scripts/koszt.py zapisz --agent <agent>` sumuje
tokeny z zapisu sesji według `flota/ceny-modeli.yaml` i dopisuje linię do `przebiegi/<agent>/koszty-<data>.jsonl` (hook `SessionEnd`
dopisuje to samo lokalnie, jeśli agent nie zdążył). Raport: `python3 -I scripts/koszt.py raport --dni 14` – koszt na agenta i model,
miesięczna projekcja w cenach API i porównanie z ceną miejsc i nadwyżką. Po 14 dniach wpisz zmierzoną pojemność miejsca
(`runtime.pojemnosc_miejsca_usd_miesiac`) i uruchom `python3 flota/generuj.py` – budżety agentów staną się udziałami w pojemności.

## Konto floty
| Konto | Osoba (miejsce) | Rozliczenie | Stan | Konektory podłączone |
|---|---|---|---|---|
| A | operator (miejsce premium Team) | team + nadwyżka | aktywne | ☐ |

Konektory, wtyczki i Artifacty są przypisane do konta Claude, nie do maszyny – lista: `flota/konto-start.md`.
Przeniesienie floty na inne konto (zmiana operatora albo planu, nie limit): `ceo/handoff/START-nowe-konto.md`.
