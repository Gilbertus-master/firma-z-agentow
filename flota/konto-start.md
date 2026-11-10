# Start floty na koncie Claude (nowa organizacja albo przeniesienie floty – bez rotacji kont)

Lista kontrolna. Źródło zadań: `flota/zadania.yaml` → `python3 flota/generuj.py --konto <K> --wyjscie ~/<prefiks>-prompty-<k>`
(zadania w aplikacji) albo `--routines` (zadania chmurowe). Wiadomość startowa CEO: `ceo/handoff/START-nowe-konto.md`.
Konto floty, zgodne rozliczenie (team/api), regulator i pomiar kosztu: `ceo/handoff/konto-floty.md`. Flota pracuje na JEDNYM koncie.
Instrukcja dla człowieka (krok po kroku): `docs/instrukcja-uruchomienia.md`.

## 1. Operator – przy aplikacji (ok. 10 min, raz na konto)
0. Plan Team (właściciel i operator; flota na miejscu premium operatora) z włączonymi usage credits i limitem wydatków równym
   `org.yaml → runtime.nadwyzka_usd_miesiac` (Organization settings) – albo klucz API przy rozliczeniu `api`.
1. Aplikacja Claude zalogowana na konto floty → Code → folder repo organizacji; model z manifestu; tryb uprawnień zgodny z
   `.claude/settings.json` (Bypass wyłączony – granice trzyma hook). Zadania zaplanowane zapisują tryb sesji, w której powstały –
   tworzyć z sesji założonej z klawiatury maszyny.
2. **Konektory** (Ustawienia → Konektory; przypisane do konta, nie do maszyny) – tylko te, które role potrzebują
   (`flota/zadania.yaml → konektory`, `toolbelt/katalog.md`):

   | Konektor | Po co | Zakres używany przez agentów |
   |---|---|---|
   | Poczta agentów (Resend / AgentMail) | skrzynki funkcyjne | odczyt; wysyłka wg `uprawnienia.yaml` (hook) |
   | Repo/zadania (GitHub) | PR-y, Issues | przez `gh` na maszynie – niezależne od konta |
   | Płatności (Stripe) | KPI, księgowość | tylko odczyt; klucz z tagiem Agent |
   | Baza (Supabase itp.) | KPI, produkt | agregaty; migracje wg uprawnień |
   | Gmail właściciela | tylko gdy decyzja D-… | odczyt |
3. **Wtyczki** potrzebne rolom (`toolbelt/wtyczki-claude.md`) – też per konto.
4. Na maszynie bez zmian: `gh`, menedżer sekretów, repo.

## 2. CEO konta floty – zadania
```bash
cd <repo> && git pull --rebase --quiet
python3 flota/generuj.py --sprawdz                                   # prompty = manifest
python3 flota/generuj.py --konto B --wyjscie ~/<prefiks>-prompty-b    # prompty „Konto: B” + lista wywołań
```
- Każda linia JSON = jedno zadanie (`taskId` `<prefiks>-<agent>-<konto>`, cron, description, prompt z pliku). **Kolejność z listy**
  (najpierw `<prefiks>-limit-<konto>` – regulator tempa).
- Po utworzeniu: „Uruchom teraz” dla recenzenta, obsługi i PM; sprawdź tryb każdego zadania.
- Przy przeniesieniu floty stare konto **wyłącza** zadania (nie kasuje); konto floty w `org.yaml → runtime.konto`.
- `scripts/przebieg.sh start <agent> <konto>` przyjmuje każdą literę A–Z; plik limitu `~/.<prefiks>-limit-<K>.json`.

## 3. Kontrola po starcie (CEO, ten sam dzień)
1. Plik limitu istnieje po pierwszym przebiegu regulatora i ma `procent`, `cel_teraz`, `odchylenie`, `tryb`.
2. Strażnik (`moduly/straznik`): brak „bez przebiegu” po pierwszym okienku każdego utworzonego agenta.
3. Kontrakt: w `przebiegi/<agent>/` brak błędów „brak narzędzi konektora” (konektory!).
4. `toolbelt/sprawdz-dostepy.md` wypełniona; `bezpieczenstwo/HALT` nie istnieje.
5. Wpis w `ceo/handoff/konto-floty.md` (tabela) i dzienniku CEO; po tygodniu pierwszy `python3 -I scripts/koszt.py raport`.

## Zmiana zadania
Manifest → `python3 flota/generuj.py` → `python3 -m unittest discover flota` → commit manifestu i promptów razem → zmiana
zadań na **wszystkich** kontach (poziom `nowy_agent_lub_zadanie_cykliczne` w `uprawnienia.yaml`).
