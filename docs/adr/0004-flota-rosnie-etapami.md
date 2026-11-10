# ADR 0004 · Flota rośnie etapami z bramką 3 dni · status: przyjęty · 2026-11-09

## Kontekst
Organizacja źródłowa powołała 21 agentów w ok. 4 dni. Mechanizmy niezawodności (kontrakt przebiegu, blokada okienek, strażnik, zajmowanie pracy, rejestry)
dopisywano **po** incydentach: duble PR-ów, zgubione opinie, przebiegi bez śladu, koszty bez budżetu, agenci bez podręcznika. Każdy nowy agent
to koszt stały (tokeny, limit konta, uwaga operatora) i nowa powierzchnia ryzyka (skrzynka, dostępy). MAST: 44 % awarii systemów wieloagentowych
to błędy projektu systemu, nie modelu.

## Decyzja
Flota startuje od **rdzenia** (`limit`, `ceo`, `pm`, `recenzent` – tworzy `scripts/init-org.sh`) i rośnie **etapami** (`procesy/00-nowa-organizacja.md`):
następny etap zaczyna się dopiero, gdy poprzedni przez **3 kolejne dni** ma przebiegi z wynikiem OK w każdym okienku, linie kontraktu z dowodem,
brak alertów strażnika i koszt w budżecie. Każdy nowy agent od pierwszego dnia ma: kontrakt przebiegu, wiersz w tsv i manifeście (test zgodności),
budżet miesięczny, podręcznik startowy, rejestry roli (`role/szablony/`), ewaluacje (gdy czyta niezaufane treści), typ reader/actor/researcher
i autonomię `aprobata`. Ten sam schemat obowiązuje przy każdym kolejnym powołaniu (`procesy/60-cykl-zycia-agenta.md`).

## Konsekwencje
- Start nowej organizacji trwa ok. 2 tygodnie zamiast 4 dni – świadomie; pierwsze tygodnie dają pomiar (F7–F9) do kalibracji budżetów.
- Niezawodność jest warunkiem wejścia, nie łatką: agent bez linii kontraktu albo bez wiersza w tsv nie przejdzie testów CI.
- Operator ma czas założyć konta i dostępy z zakresem minimalnym przed etapem, który ich potrzebuje; budżet floty rośnie liniowo z etapami.
- Koszt: wolniejsza ekspansja na nowe obszary; presja biznesowa („potrzebujemy sprzedaży dziś”) musi przejść przez decyzję właściciela
  z zapisem ryzyka (`ryzyka.md`), nie przez pominięcie bramki.
- Ten sam mechanizm działa w transformacji istniejącej firmy (`procesy/20`): tryb cienia i bramka przejęcia per obszar.

## Źródło
`docs/raport/2026-11-09-raport.md` rozdz. 0 („Niezawodność dopisywano po incydentach”), 1.4, 4.2 pkt 2–3 (niezawodność od dnia 1, flota rośnie
etapami), rozdz. 5 (plan wdrożenia); research „Standardy 2026” – MAST (arXiv 2503.13657), „Co zostawić bez zmian” (flota rosnąca etapami z bramką 3 dni).
