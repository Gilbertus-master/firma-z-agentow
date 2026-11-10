---
name: przebieg
description: Kontrakt przebiegu agenta organizacji – start (blokada, budżet), tryby, zakończenie (dziennik, stan.json, linia JSON v2, commit), raport. Użyj na początku każdego przebiegu zaplanowanego.
---
# Przebieg agenta – procedura (pełna wersja: zasady.md sekcja B, pm/specyfikacje/kontrakt-przebiegu.md)

1. `cd <repo> && git pull --rebase --quiet`; `scripts/przebieg.sh start <agent> <konto>` – kod 10 = koniec jednym zdaniem,
   bez pracy i commita (okienko zajęte, budżet, dead-letter); inny ≠ 0 = koniec z opisem błędu. Czas z `date`.
2. Czytaj: `uprawnienia.yaml` (swoje wiersze), nowe `decyzje/` od `stan.json → ostatni_przebieg`, swoje zlecenia,
   `stan.json`, 3 ostatnie wpisy dziennika, `wiedza/podrecznik.md`.
3. Tryb: PEŁNY (raz w tygodniu, swój dzień, raz na dobę) · ZDARZENIE (nowe zlecenie/decyzja/termin ≤ 3 h) · DZIENNY
   (pierwszy przebieg dnia) · CISZA (nic nowego → jedno zdanie, linia JSON i osobny commit tylko pliku `przebiegi/<agent>/` – kontrakt przebiegu; innych plików nie commitujesz).
4. Praca w swoim zakresie; cudze obszary = zlecenie (zlecenia/README.md); sprawy dla człowieka → CEO.
   Stan sprawdzaj u źródła. Każdy wynik ma ścieżkę w repo albo URL.
5. Zakończenie: dziennik (nagłówek `## RRRR-MM-DD – TRYB (GG:MM, konto X)`, sekcje Co się zmieniło · Co zrobiłem ·
   Zlecenia · **KPI:** · Do decyzji · Dalej), `stan.json`, linia JSON **wersji 2** w `przebiegi/<agent>/<data>.jsonl`
   (`prompt_version` = `git log -1 --format=%h -- <agent>/agent.md role/<agent>.md flota/szablony/`, `outcome_evidence` = URL),
   `python3 -I pm/narzedzia/przebieg-raport.py sprawdz …`, koszt przebiegu `python3 -I scripts/koszt.py zapisz --agent <agent>`
   (`koszt_usd` w linii kontraktu zostaje `null`), `git add` tylko swoich plików (+ `przebiegi/<agent>/koszty-*.jsonl`, `bezpieczenstwo/audyt/`),
   commit, `git pull --rebase` (do 3 prób), push. Raport ≤ 12 linii dla zleceniodawcy.
6. Nauka: pierwszy przebieg po 18:00 – przegląd po działaniu → reguła w podręczniku (format z `role/_podrecznik-startowy.md`).
