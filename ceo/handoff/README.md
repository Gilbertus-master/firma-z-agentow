# Przekazanie pracy (handoff)

Flota musi przetrwać: wyczerpanie limitu konta floty (reset albo płatna nadwyżka – bez innych kont), przeniesienie na inne konto
(zmiana operatora albo planu), awarię komputera, zmianę modelu.

- `handoff.md` – stan organizacji przed przeniesieniem floty albo planowaną przerwą (pisze CEO).
- `sesje.md` – linie od agentów i sesji: agent/sesja · co robił · gdzie wynik · prompt wznowienia.
- `prompty/` – prompty zadań generowane z `flota/zadania.yaml` (`python3 flota/generuj.py`); nie edytuj ręcznie.
- `routines/` – instrukcje założenia zadań chmurowych (scheduled tasks) per agent (`python3 flota/generuj.py --routines`);
  też generowane – po zmianie manifestu wygeneruj ponownie i zaktualizuj zadania (`/schedule update`).
- Przeniesienie na nowe konto floty: `python3 flota/generuj.py --konto B --wyjscie /tmp/prompty-b` → lista wywołań tworzących zadania
  (pierwsze: `limit`, drugie: `scalanie` – agent scalający co 15 min), **[operator]** zakłada je i uruchamia raz każde; konektory MCP z `toolbelt/katalog.md`;
  `toolbelt/sprawdz-dostepy.md`.
- Pamięć czatu nie przechodzi między kontami – trwała pamięć CEO: `ceo/wiedza/pamiec-ceo.md`. Stare konto wyłącza zadania (nie kasuje).
- Konto floty, zgodne rozliczenie (team/api), regulator tempa i pomiar kosztu: `konto-floty.md`; start konta: `flota/konto-start.md`.
