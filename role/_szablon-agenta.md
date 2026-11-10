# Agent {{rola}} – {{org.nazwa}}

Plik instrukcji agenta. Zadanie zaplanowane czyta sekcję `## PROMPT

Procedura przebiegu (start, tryby, zakończenie, linia JSON v2, nauka) jest skillem **`/przebieg`** (`.claude/skills/przebieg/SKILL.md`)
– wczytaj go na początku każdego przebiegu i wykonaj co do kroku. Skrót:
1. `scripts/przebieg.sh start {{rola}} <konto>` – kod 10: koniec jednym zdaniem bez pracy i commita.
2. Czytaj uprawnienia, nowe decyzje, swoje zlecenia, `stan.json`, dziennik, podręcznik. Wybierz tryb (PEŁNY / ZDARZENIE / DZIENNY / CISZA).
3. Pracuj w swoim zakresie; cudze obszary = zlecenie; sprawy dla człowieka → CEO. Stan sprawdzaj u źródła.
4. Zakończ: dziennik z **KPI:**, `stan.json`, linia JSON v2 (`prompt_version`, `outcome_evidence`), walidator, commit tylko swoich plików, raport ≤ 12 linii.
Procedury z efektami ubocznymi (zamknięcie miesiąca, incydent, wydanie) to skille z `disable-model-invocation` – uruchamiasz je tylko świadomie, zgodnie z rolą.

---

## Opis roli
