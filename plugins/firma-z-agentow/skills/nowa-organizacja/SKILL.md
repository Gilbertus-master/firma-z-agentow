---
name: nowa-organizacja
description: Zakłada nową organizację agentyczną z tego szablonu – prywatne repo firmy, init-org.sh, prompty floty, testy i lista zadań zaplanowanych do założenia. Użyj, gdy użytkownik chce uruchomić flotę agentów dla swojej firmy.
disable-model-invocation: true
argument-hint: "<nazwa firmy> <domena> <prefiks>"
---
# Nowa organizacja agentyczna – kroki

Szablon: `Gilbertus-master/firma-z-agentow` (pełna instrukcja po sklonowaniu: `docs/instrukcja-uruchomienia.md`). Wymagane: `git`, `gh` (zalogowane),
Python 3. Zanim cokolwiek utworzysz, zapytaj użytkownika o: nazwę firmy, domenę, krótki prefiks (2–4 litery), właściciela
na GitHubie, adres operatora i sposób uruchamiania (`claude-routines`, `desktop-scheduled` albo `agent-sdk`).

1. Pokaż użytkownikowi polecenia z kroku 2 z podstawionymi wartościami i poczekaj na zgodę – tworzysz repozytorium na jego koncie.
2. Repo firmy (zawsze **prywatne**):
   ```bash
   gh repo create <owner>/<firma>-agenci --private --template Gilbertus-master/firma-z-agentow --clone
   cd <firma>-agenci
   scripts/init-org.sh --nazwa "<Nazwa>" --domena <domena> --prefiks <prefiks> \
     --github <owner>/<firma>-agenci --operator <adres operatora> --runtime <runtime>
   python3 flota/generuj.py
   bash scripts/testy.sh
   ```
3. Testy muszą być zielone. Czerwone → pokaż wynik i zatrzymaj się; nie poprawiaj testów, żeby przeszły.
4. Przeczytaj z użytkownikiem sekcję README „Dzielenie się ulepszeniami” – jest **domyślnie wyłączone**. Nie włączaj go sam:
   włącza je właściciel decyzją (`repo.dziel_sie_ulepszeniami: true` i `repo.dziel_sie_decyzja: "D-…"` w `org.yaml`).
5. Rozliczenie i konto floty: `org.yaml → runtime` według `docs/instrukcja-uruchomienia.md` (sekcja 2). Flota pracuje na
   **jednym** koncie; nie proponuj przełączania między kontami ani subskrypcjami innych osób.
6. Commit i push dopiero po zgodzie użytkownika. Sekretów (`STRAZNIK_TOKEN`) nie wpisujesz – podajesz polecenie
   `gh secret set STRAZNIK_TOKEN`, które użytkownik uruchamia sam.
7. Na koniec wypisz: co działa, jakie zadania zaplanowane trzeba założyć (kolejność: `limit`, `scalanie`, `ceo`, `recenzent`,
   `pm`) i co wymaga człowieka. Zadań zaplanowanych nie zakładasz bez osobnej zgody.

W repo firmy działają już skille projektu (`/przebieg`, `/dyzur-pm`, `/recenzja`, `/incydent`) i hook uprawnień – ta wtyczka
nie dodaje własnych hooków ani uprawnień.
