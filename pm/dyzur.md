# Dyżur blokad PM – RRRR-MM-DD GG:MM (wykonany GG:MM–GG:MM, konto X)

Nadpisywany co dyżur (`role/pm.md`, Codziennie pkt 2; procedura: skill `/dyzur-pm`). Plik mówi, **kto na kogo czeka i od kiedy**.
Każda liczba i godzina ma źródło z tego dyżuru (polecenie + czas z `date`) – nigdy z pamięci ani z poprzedniego dyżuru.
Blokada > 6 h = zlecenie do CEO („Dyżur blokad GG:MM”). Bez blokad: nagłówek, źródła i zdanie „Dyżur: brak blokad.”

**Źródła:** `gh pr list` (repo z `org.yaml → repo.produkt` + organizacji) GG:MM · `recenzent/stan.json` · `zlecenia/*.md`
(`czeka:`, `Pilne`, `[w toku]`) · Issues `stan:czeka`/`typ:blokada` · `operator/kolejka.md` · `przebiegi/*/<dziś>.jsonl`
(`podsumuj 1`) · `przebiegi/dead-letter/` · `ceo/do-decyzji.md` · dzienniki adresatów (tylko nagłówki wpisów od chwili blokady).

**PR-y:** otwarte N (bez draftów) · gotowe niescalone (werdykt OK + CI zielone + MERGEABLE): #… (od N h) · bez werdyktu > 1 h: #… ·
z konfliktem (autor): #… · scalone od poprzedniego dyżuru: N.
**Zlecenia:** `czeka:` N · `Pilne` bez odpowiedzi N · `[w toku]` > 6 h bez śladu w dzienniku adresata N · po terminie N (`backlog.py --sprawdz`).
**Operator:** pozycji w kolejce N, po SLA (`org.yaml → sla_godziny`) N. **Do-decyzji:** spraw N, starszych niż 7 dni (wygasłe – domyślne „nie”) N.
**Flota (24 h):** bez linii w oknie: … · BŁĄD/NIEPEŁNY: … · dead-letter: … · F8 OK bez dowodu: N.
**Raporty pionów (pn):** N/M liderów złożyło `<lider>/pion/<data>.md`.

| # | Co | Kto blokuje | Kto czeka | Od ilu h | Co zrobić (kto) |
|---|---|---|---|---|---|
| 1 | <PR #N – temat; werdykt OK GG:MM, CI zielone> | <kto ma scalić wg uprawnienia.yaml> | <autor, sesje zależne> | N | <scalić w najbliższym przebiegu; jeśli > 6 h – CEO> |
| 2 | <zlecenie Z-… / #N – temat> | <adresat> | <zleceniodawca> | N | <przypomnienie Pilne dopisane GG:MM / obudzić (CEO)> |
| 3 | <czynność operatora #N> | operator | <agent> | N (SLA N h) | <CEO: eskalacja do operatora kanałem z org.yaml> |

**Pilne dopisane agentom (raz na 6 h):** `zlecenia/<agent>.md` – <lista albo „brak”>.
**Rozwiązane od poprzedniego dyżuru:** <co i czym – link do PR/commita/wpisu>.
**W terminie (bez Pilne):** <sprawy obserwowane, których termin jeszcze nie minął>.
**Stałe (powtarzają się ≥ 3 dyżury):** <lista z numerem sprawy w `ceo/do-decyzji.md` / `operator/kolejka.md`> – propozycja PM dla CEO: <…>.
**Własne PM:** <zaległości PM-a: DZIENNY nie wykonany, backlog nieprzeliczony, przegląd piątkowy>.
