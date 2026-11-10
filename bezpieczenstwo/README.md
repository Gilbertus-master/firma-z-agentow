# Bezpieczeństwo – pliki wspólne

- `audyt/RRRR-MM.jsonl` – rekord KAŻDEJ decyzji hooka uprawnień (pre: allow/deny, post: wykonane) z łańcuchem SHA-256 (`prev_hash` → `hash`); retencja ≥ 6 miesięcy (AI Act art. 26 – obowiązek podmiotów stosujących systemy wysokiego ryzyka; dla pozostałych dobra praktyka), `merge=union`.
- `blokady.jsonl` – same odmowy (skrót do przeglądu tygodniowego: CEO używa do decyzji o poluzowaniu `uprawnienia.yaml`).
- `HALT` – kill switch: gdy plik istnieje, hook zatrzymuje każdą sesję agenta przy pierwszym narzędziu innym niż odczyt. Zakłada strażnik (budżet floty ≥ 100 %) albo człowiek; usuwa operator po przeglądzie.
