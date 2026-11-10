# Backlog organizacji

Prowadzi agent PM (`role/pm.md`). To spis z linkami, nie kopia zleceń. Każde zlecenie jednorazowe i każde zadanie cykliczne ma tu
wiersz z właścicielem, terminem i statusem. PM co piątek ocenia zasadność zadań cyklicznych (koszt kontra wartość;
`pm/szablony/przeglad-cyklicznych.md`) i zgłasza propozycje CEO.

Priorytet: **P1** termin prawny / produkcja / przychód · **P2** plan tygodnia (`Plan:` w zleceniu) · **P3** reszta.
Status: otwarte / w toku (kto) / czeka: kto / zrobione (data) / odłożone / informacja. `PO TERMINIE (+N d)` w kolumnie „Uwaga PM”
= termin minął, a odpowiedzi nie ma. Termin `(dom.)` = zlecenie bez linii `Termin:` (domyślnie 12 h od wpisu); `– (tekst)` = termin
zależny od zdarzenia (np. „po decyzji nr N”) – nie liczy się jako po terminie, ale musi mieć właściciela.

**Sekcję „Jednorazowe” generuje** `python3 -I pm/narzedzia/backlog.py` ze skrzynek `zlecenia/*.md` i Issues `typ:zlecenie`
(klucz wiersza: `Z-RRRRMMDD-NN`, `#N` Issue albo plik + temat). Kolumny **Właściciel, Temat, Źródło, Termin, Status** nadpisuje narzędzie;
**Id, P, Plan, Uwaga PM** są ręczne (PM wpisuje EV i koszt dla P1–P2) – narzędzie zachowuje je i dokłada tylko swoje znaczniki
(`PO TERMINIE`, `brak linii Termin:`, `odpowiedź jest – nagłówek otwarty (M-03)`, `status md ≠ Issue`, `źródło zniknęło`).
`python3 -I pm/narzedzia/backlog.py --sprawdz` wypisuje po terminie, duble i zadania z `flota/zadania.yaml` bez wiersza C.

## Jednorazowe

| Id | Właściciel | Temat | Źródło | P | Termin | Status | Plan | Uwaga PM |
|---|---|---|---|---|---|---|---|---|

## Cykliczne

Ręcznie (PM): każde zadanie z `flota/zadania.yaml`, każdy cron i pętla ma wiersz; Właściciel = katalog agenta (tak sprawdza `backlog.py --sprawdz`).
Koszt / tydzień z `przebieg-raport.py podsumuj 7` (USD, liczba przebiegów); Wartość = KPI z `ceo/kpi/kpi.md`, który zadanie karmi, i kto czyta wynik.

| Id | Właściciel | Zadanie | Rytm | Koszt / tydzień | Wartość (KPI) | Ostatni przegląd | Uwaga PM |
|---|---|---|---|---|---|---|---|
| C-01 | pm | Przegląd zasadności zadań cyklicznych (`pm/przeglady/`) | pt | – | koszt floty, F1 | – | – |
| C-02 | pm | Kontrola sprzeczności decyzji (`scripts/decyzje-indeks.py --sprawdz`) | pt | – | jakość decyzji | – | – |
| C-03 | pm | Raport floty z kontraktu (`pm/raporty/`): nieudane, F8, F10, koszt koordynacji | codziennie (24 h) · pt (7 dni) | – | F1, F8, F9, F10 | – | – |
| C-04 | pm | Dyżur blokad (`pm/dyzur.md`; > 6 h → CEO) | każde okienko | – | F4, czas do scalenia | – | – |
| C-05 | pm | Licznik do-decyzji (zadane / rozstrzygnięte / odrzucone / wygasłe) | pt | – | F5, F12 | – | – |
| C-06 | pm | Kurator podręczników (duplikaty, reguły bez efektu, stale guardrails) | 1. PEŁNY miesiąca | – | jakość instrukcji | – | – |
