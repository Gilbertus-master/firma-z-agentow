# ADR 0001 · Repozytorium git jako pamięć i szyna komunikatów organizacji · status: przyjęty · 2026-11-09

## Kontekst
Każdy przebieg agenta zaczyna się bez pamięci – stan musi być poza modelem. Rozważano: pamięć wektorową (Mem0, Zep), platformę
„firmy” nad Claude Code (Paperclip), własną bazę, pliki w repozytorium git z GitHub Issues jako zleceniami. Organizacja źródłowa przez 4 dni
i ok. 1400 commitów prowadziło całą organizację w plikach (dzienniki, `stan.json`, zlecenia, decyzje, rejestry) – działało, bolały rozmiar
plików zleceń (100 KB+), konflikty przy wspólnym zapisie i brak higieny pamięci. Benchmarki pamięci wektorowej są samoraportowane i sprzeczne;
Paperclip nie ma udokumentowanej działającej firmy, a pamięć i uczenie ma w planach.

## Decyzja
Pamięcią organizacji jest **prywatne repozytorium git**: pliki Markdown/JSON/YAML z jednym źródłem prawdy dla każdej rzeczy (`org.yaml`,
`uprawnienia.yaml`, `flota/zadania.yaml` + tsv, `decyzje/`, `<agent>/stan.json`, rejestry ról), **GitHub Issues** jako zlecenia (pliki
`zlecenia/` jako zapas), `merge=union` dla logów dopisywanych przez wielu pisarzy, limit 200 linii promptu z progressive disclosure
(skille), higiena pamięci jako osobny proces (kurator PM, statusy reguł, `supersedes` w decyzjach, indeks generowany).

## Konsekwencje
- Audytowalność i czytelność dla ludzi i wielu harnessów za darmo (historia, blame, PR z werdyktem recenzenta dla zmian instrukcji).
- Konflikty zapisu rozwiązuje dyscyplina git (commit tylko swoich plików, `pull --rebase`, nigdy reset/stash/force) i `merge=union`;
  każdy agent ma własne pliki, wspólne są tylko dopisywane.
- Koszt: brak wyszukiwania semantycznego – rejestry muszą mieć ID i stałe kolumny (`role/szablony/`), a prompt ładuje tylko to, co trzeba.
- Strażnik, hook i testy czytają te same pliki – kontrola deterministyczna bez dodatkowej infrastruktury.
- Zmiana na pamięć wektorową albo Paperclip – dopiero po v1.0, jako warstwa nad plikami, nie zamiast nich.

## Źródło
`docs/raport/2026-11-09-raport.md` (rozdz. 1.2, 1.4, 4.1–4.2); research „Standardy 2026” – sekcja „Wiedza i uczenie” oraz „Co zostawić bez zmian”
(repo git + Issues jako szyna, bez pamięci wektorowej, Paperclip tylko jako test panelu po v1.0); rek. 7 i 8.
