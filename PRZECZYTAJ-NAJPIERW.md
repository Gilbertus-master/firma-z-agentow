# Przeczytaj najpierw – start sesji w organizacji agentycznej

Dla Claude, który zaczyna pracę w tej organizacji bez historii rozmów (nowe konto, nowa sesja, Routine).
Bez sekretów – klucze, hasła i tokeny nie są i nie mogą być zapisywane w plikach.

## Kto i co
- Dane firmy, ludzi, mandatu i runtime: `org.yaml`.
- **Właściciel** – mandat, budżet, granice; decyzje przez `ceo/do-decyzji.md` → `decyzje.md`.
- **Agent CEO** – zarządza organizacją; wszyscy agenci raportują do niego.
- **Operator** – „interfejs białkowy”: raportuje do CEO, wykonuje tylko to, czego agent nie może (`operator/`).
- Pracujesz po polsku, prostym językiem, krótko.

## Kolejność czytania
1. `zasady.md` – obowiązują zawsze; `uprawnienia.yaml` – co wolno bez pytania.
2. `README.md` – mapa repo i agentów.
3. `decyzje.md` (indeks; pliki w `decyzje/`), `ceo/do-decyzji.md`, `operator/kolejka.md`, `bezpieczenstwo/HALT` (jeśli istnieje – flota stoi).
4. Swoje zlecenia (Issues `agent:<ty>` albo `zlecenia/<ty>.md`) i `<ty>/agent.md`.

## Gdy jesteś czatem z człowiekiem
- Najpierw ustaw rolę sesji dla hooka uprawnień: `echo ceo > .agent-rola` (albo inna rola; plik jest w `.gitignore`).
  Bez tego hook blokuje wszystko poza czynnościami `sam`.
- Rozmawiasz z właścicielem albo operatorem – zapisujesz decyzje jako plik `decyzje/D-RRRRMMDD-NN.md` (frontmatter + dosłowny
  cytat) i odświeżasz indeks `python3 -I scripts/decyzje-indeks.py`. Czynność poziomu właściciel wykonujesz z tym ID: `DECYZJA=D-… <polecenie>`.
- Pracę wykonawczą zlecasz agentom albo sesjom (wpis w `rejestr-sesji.md`), nie robisz jej w czacie.
