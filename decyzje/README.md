# Rejestr decyzji (katalog)

Jedna decyzja = jeden plik `D-RRRRMMDD-NN.md` z frontmatterem (`id`, `status`, `data`, `kto`, `scope`, `supersedes`,
`wazna_do`, `model_context`, `dotyczy`) i treścią (słowa właściciela, decyzja, skutek). `decyzje.md` w korzeniu to **indeks
generowany** (`python3 -I scripts/decyzje-indeks.py`, ≤ 200 linii) – jedyna warstwa wstrzykiwana agentom; nie edytować ręcznie.
Hook uprawnień sprawdza `DECYZJA=D-…` w tym katalogu (status `accepted`).
Kontrola spójności (`scripts/decyzje-indeks.py --sprawdz`, w CI): dwie decyzje `accepted` o tym samym `scope` bez `supersedes`
= sprzeczność; `supersedes` wskazujące na nieistniejącą decyzję = błąd; `wazna_do` w przeszłości = `expired`.
Archiwum: status `superseded`/`expired` starsze niż 90 dni przenosi `--archiwizuj` do `decyzje/archiwum/RRRR/`.
