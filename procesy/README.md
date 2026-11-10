# Procesy organizacji agentycznej – indeks

Numeracja co 10 zostawia miejsce na procesy spółki (np. `45-…`). Każdy proces ma kroki z wykonawcą, bramką i dowodem; kroki człowieka
oznaczone **[operator]** / **[właściciel]**. Procedury z efektami ubocznymi mają też skill w `.claude/skills/` (`disable-model-invocation`).

| Nr | Proces | Jedno zdanie |
|---|---|---|
| [00](00-nowa-organizacja.md) | Nowa organizacja od zera | W ok. 2 tygodnie od decyzji właściciela działa CEO, rdzeń zarządczy i pierwsi agenci dziedzinowi; flota rośnie etapami z bramką 3 dni. |
| [05](05-wiele-spolek.md) | Wiele spółek na jednym szablonie | Jedna spółka = jedno konto Claude, jedna organizacja GitHub i jedno repo z szablonu jako upstream; aktualizacje przez `scripts/aktualizuj-z-szablonu.sh` z zachowaniem plików lokalnych. |
| [10](10-budowa-produktu.md) | Budowa produktu | Od pomysłu do działającej aplikacji w 17 etapach z bramkami CEO, kontrolą sprzeczności decyzji i kosztem każdego etapu. |
| [15](15-rozwoj-szablonu.md) | Rozwój szablonu przez floty klientów | Firmy co tydzień zgłaszają uogólnione ulepszenia (bez danych firmy) i dostają najnowsze wydanie szablonu jako PR – szablon uczy się z pracy wszystkich flot. |
| [20](20-transformacja-istniejacej.md) | Transformacja istniejącej organizacji | Audyt procesów i czasu ludzi → tryb cienia → bramki przejęcia per obszar, z integracjami do istniejących systemów, komunikacją z ludźmi i ryzykami prawnymi HR. |
| [30](30-zamkniecie-miesiaca.md) | Zamknięcie miesiąca | Do 10. dnia: faktury z KSeF, koszty, uzgodnienie bank ↔ płatności ↔ faktury, JPK przez osobę uprawnioną, koszt floty, raport (skill `/zamkniecie-miesiaca`). |
| [40](40-wydanie.md) | Wydanie wersji produktu | Zakres → testy → bramka zgodności G1–G12 → werdykt recenzenta → decyzja CEO → wysyłka przez rolę z uprawnień → monitoring 72 h i rollback (skill `/wydanie`). |
| [50](50-przeglad-agenta.md) | Miesięczny przegląd agenta | KPI, koszt, incydenty, blokady hooka i jakość linii kontraktu każdego agenta → decyzja o poziomie autonomii per typ zadania (drabina eskalacja → aprobata → auto). |
| [55](55-doskonalenie-zarzadzania.md) | Doskonalenie zarządzania | Sposób, w jaki CEO pilnuje floty, poprawia się w stałym rytmie: co tydzień trzy najczęściej niezaliczone kontrole i ucieczki, co miesiąc miary M1–M6, eksperymenty i kalibracja progów (skill `/przeglad-zarzadzania`), co kwartał samoocena dojrzałości i audyt recenzenta wprost do człowieka. |
| [60](60-cykl-zycia-agenta.md) | Cykl życia agenta | Powołanie (`nowy-agent.sh`) → 3 dni bramki → stały rytm → zmiana roli → wygaszenie z archiwizacją do `archiwum/` i decyzją D-…. |
| [90](90-incydent.md) | Incydent | Najpierw zatrzymać (HALT), potem rozumieć: unieważnienie poświadczeń, migawka, rollback, przegląd bezpieczników, nowy scenariusz ewaluacji, raport (skill `/incydent`). |

Powiązane rejestry: `ryzyka.md` (ryzyka organizacji, przegląd kwartalny), `decyzje/`, `incydenty/`, `ewaluacje/`. Decyzje architektoniczne
szablonu: `docs/adr/`.
