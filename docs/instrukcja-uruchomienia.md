# Instrukcja uruchomienia – nowa firma, konto floty i aktualizacje

Krok po kroku: jak z tego szablonu założyć organizację agentyczną, uruchomić flotę w wariancie dopuszczalnym według naszej interpretacji warunków Anthropic (stan na 10.11.2026; to nie porada prawna – za zgodność z aktualnymi warunkami odpowiadasz sam), mierzyć
jej koszt i utrzymywać ją na najnowszym wydaniu szablonu. W organizacji pracują dwie osoby: **właściciel** i **operator**.
Szczegóły: `ceo/handoff/konto-floty.md`, `flota/konto-start.md`, `procesy/00-nowa-organizacja.md`, `procesy/15-rozwoj-szablonu.md`.

## 0. Trzy rzeczy, których nie wolno pomylić
| Co | Do czego służy | Gdzie się to ustawia |
|---|---|---|
| **Konto floty** (jedno) | miejsce w planie Team operatora (albo klucz API), na którym działają wszystkie zadania agentów; należą do niego zadania zaplanowane, konektory i wtyczki | aplikacja Claude albo `claude` → `/login`; `org.yaml → runtime.konto` |
| **Konto GitHub** | dostęp do szablonu i repo firmy – przez `gh` na maszynie, niezależnie od konta Claude | `gh auth login` |
| **Repo firmy** | pamięć organizacji; kopia szablonu z aktualizacjami jako PR-y | kopia szablonu |

**Bez rotacji kont.** Flota nie przełącza się na konto innej osoby z wolnym limitem: plany Pro/Max/Ultra są do użytku
niekomercyjnego i nie wolno ich udostępniać, a na planie Team każde miejsce należy do jednej imiennej osoby i limitów nie wolno
przenosić ani dzielić (`ceo/handoff/konto-floty.md`).

## 1. Raz na maszynę
1. `git`, `gh` (`gh auth login`), Python 3 (CI używa 3.12), aplikacja Claude albo Claude Code CLI.
2. Konto GitHub z prawem tworzenia prywatnych repozytoriów (szablon jest publiczny).
3. Repo firmy leży w ścieżce z `org.yaml → repo.organizacja` – prompty zawierają tę ścieżkę. Inna ścieżka → popraw `org.yaml`
   i `python3 flota/generuj.py`.

## 2. Rozliczenie – wybierz jeden zgodny wariant (`org.yaml → runtime.rozliczenie`)
| Wariant | Co kupić | Ustawienia |
|---|---|---|
| `team` (domyślny) | plan Team: 2 miejsca (właściciel, operator – miejsce premium), włączone usage credits i limit wydatków w Organization settings | `konto: "A"`, `cena_planu_usd_miesiac`, `nadwyzka_usd_miesiac` = limit wydatków u Anthropic |
| `api` | klucz API z Claude Console; flota przez `scripts/przebieg-headless.sh` (Agent SDK) z własnym harmonogramem | `glowny: agent-sdk`, budżety USD w `flota/zadania.yaml`, `mandat.budzet_floty_usd_miesiac` (HALT) |
| Enterprise zużyciowy | większa firma, całość po stawkach API (warunki ustala Anthropic) | jak `api` |

Po wyczerpaniu tygodniowego limitu miejsca flota pracuje dalej tylko na płatnej nadwyżce; bez nadwyżki do resetu działa tylko P1.

## 3. Nowa firma – raz
```bash
gh repo create <OWNER>/<firma>-agenci --private --template Gilbertus-master/firma-z-agentow --clone
cd <firma>-agenci
scripts/init-org.sh --nazwa "Nowa Firma" --domena nowafirma.example --prefiks nf \
  --github <OWNER>/<firma>-agenci --operator operator@nowafirma.example --runtime claude-routines   # albo desktop-scheduled / agent-sdk
# org.yaml → runtime: rozliczenie, konto, cena_planu_usd_miesiac, nadwyzka_usd_miesiac; repo: szablon, skrzynka_propozycji
python3 flota/generuj.py        # prompty i budżety agentów (flota/budzety.tsv)
git add -A && git commit -m "start organizacji Nowa Firma" && git push
gh secret set STRAZNIK_TOKEN    # token fine-grained: odczyt PR-ów repo produktu, zapis repo organizacji
```
Wynik `init-org.sh`: `org.yaml`, decyzja startowa `D-<dziś>-01`, agenci rdzenia (ceo, pm, recenzent), etykiety Issues, prompty,
testy ✓ i lista zadań do założenia. Strażnik rusza sam w GitHub Actions co 15 min.

## 4. Flota na koncie floty
1. **Logowanie:** aplikacja Claude na koncie floty → Code → folder repo firmy; sesja z klawiatury tej maszyny (zadania zaplanowane
   zapamiętują tryb uprawnień). Bypass jest wyłączony (`.claude/settings.json`), granice trzyma hook.
2. **Konto:** konektory i wtyczki potrzebne rolom (`flota/konto-start.md`). Modele klas z `org.yaml → runtime.modele` muszą być
   dostępne na koncie; brak modelu → zmień mapowanie klasy i `python3 flota/generuj.py`.
3. **Pierwsza wiadomość:** prompt startowy (sekcja 5).
4. **Zadania rdzenia** (kolejność: `limit`, `scalanie`, `ceo`, `recenzent`, `pm`):
   - w aplikacji: `python3 flota/generuj.py --konto A --wyjscie ~/<prefiks>-prompty-a --tylko limit,scalanie,ceo,pm,recenzent`
     → linia JSON na zadanie; zakłada je CEO tej sesji;
   - w chmurze: `python3 flota/generuj.py --routines --konto A --wyjscie ~/<prefiks>-routines-a --tylko limit,scalanie,ceo,pm,recenzent`
     → plik na zadanie; zakładasz na claude.ai/code/routines albo `/schedule`.
5. **„Uruchom teraz”** każde zadanie raz – inaczej stanie na pytaniu o zgodę.
6. **Kontrola tego samego dnia:** linie w `przebiegi/<agent>/`, pliki `przebiegi/<agent>/koszty-*.jsonl`, strażnik bez „bez przebiegu”,
   brak `bezpieczenstwo/HALT`. Kolejne role dochodzą etapami (`procesy/00`, bramka 3 dni).

## 5. Prompt startowy – nowa firma
```text
Jesteś agentem CEO organizacji <NAZWA> na koncie floty A. Najpierw ustaw rolę sesji: echo ceo > .agent-rola.
Przeczytaj PRZECZYTAJ-NAJPIERW.md, zasady.md, uprawnienia.yaml, org.yaml, ceo/handoff/konto-floty.md i flota/konto-start.md.
Potem: python3 flota/generuj.py --konto A --wyjscie ~/<prefiks>-prompty-a --tylko limit,scalanie,ceo,pm,recenzent
i załóż zadania zaplanowane w kolejności z listy (najpierw limit, potem scalanie). Uruchom każde raz.
Commit, push. Na koniec napisz operatorowi krótko: co działa, co w toku, co wymaga człowieka.
```

## 6. Koszt floty – pomiar od pierwszego dnia
- Każdy przebieg zapisuje swój koszt: hook `SessionStart` zapamiętuje zapis sesji, a agent na końcu przebiegu (i hook `SessionEnd`)
  uruchamia `python3 -I scripts/koszt.py zapisz` – tokeny × `flota/ceny-modeli.yaml` → `przebiegi/<agent>/koszty-<data>.jsonl`.
- Raport: `python3 -I scripts/koszt.py raport --dni 14` – koszt na agenta i model, projekcja miesięczna w cenach API, porównanie
  z ceną miejsc i nadwyżką. Po 14 dniach wpisz zmierzoną pojemność miejsca (`runtime.pojemnosc_miejsca_usd_miesiac`) i uruchom
  `python3 flota/generuj.py` – budżety agentów staną się udziałami w pojemności konta floty.

## 7. Aktualizacje i rozwój szablonu (proces 15)
- **Co poniedziałek architekt** uruchamia `scripts/aktualizuj-z-szablonu.sh --pr`: najnowsze wydanie (`repo.szablon_kanal: stabilny`)
  na osobnej gałęzi, prompty, testy, PR → recenzent → kolejka scalania. Zmiany w `zasady.md` i `.claude/` czekają na decyzję właściciela.
- **Co poniedziałek architekt** zgłasza ulepszenia: `python3 -I scripts/propozycje.py zbierz` → `sprawdz` → `wyslij` – tylko zmiany
  mechanizmów i sprawdzone reguły, przez bramkę anonimizacji, do skrzynki firmy u wydawcy (`repo.skrzynka_propozycji`) albo – w darmowym rdzeniu – do publicznego repo szablonu, przy zgodzie
  `repo.dziel_sie_ulepszeniami: true` (wysyłka do wspólnego repo wymaga też decyzji właściciela w `repo.dziel_sie_decyzja`).

## 8. Na co dzień i gdy coś nie działa
| Sytuacja | Co zrobić |
|---|---|
| Właściciel – decyzje | `ceo/do-decyzji.md`: opcje, skutek, rekomendacja; zgoda = plik `decyzje/D-RRRRMMDD-NN.md` |
| Operator – zadania | `operator/kolejka.md`: gotowe kroki, termin, oczekiwany wynik |
| Rozmowa z CEO | czat w folderze repo: `echo ceo > .agent-rola`, zlecenia przez `zlecenia/ceo.md` |
| Limit konta floty wyczerpany | regulator dopisuje Pilne; z nadwyżką praca idzie dalej, bez niej do resetu tylko P1; stale za mało – decyzja właściciela (nadwyżka, miejsce, `api`) |
| Istnieje `bezpieczenstwo/HALT` | flota stoi; operator czyta powód i usuwa plik po przeglądzie |
| `przebiegi/dead-letter/<agent>.md` | 3 błędy z rzędu; przyczyna → poprawka → operator usuwa plik |
| Alert „bez przebiegu” | zadanie na koncie floty: włączone? model, tryb, konektory? |
| Zmiana manifestu (`flota/zadania.yaml`) | `python3 flota/generuj.py`, commit, zmiana zadań na koncie floty |
| PR aktualizacji z konfliktem | architekt scala ręcznie na gałęzi roboczej (`scripts/aktualizuj-z-szablonu.sh` bez `--pr`) i otwiera PR |
| Przeniesienie floty na inne konto (zmiana operatora albo planu) | `ceo/handoff/START-nowe-konto.md`; stare konto wyłącza zadania |
