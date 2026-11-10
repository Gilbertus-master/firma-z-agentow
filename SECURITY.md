# Polityka bezpieczeństwa

**Nie zakładaj publicznego Issue dla podatności.** Użyj prywatnego zgłaszania podatności GitHuba w tym repozytorium
(Security → Report a vulnerability). Podaj: plik, którego dotyczy, sposób odtworzenia i skutek.

W zakresie: hook uprawnień (`.claude/hooks/uprawnienia.py`), dziennik audytu, HALT, kolejka scalania (`scripts/scalanie.py`),
bramka anonimizacji (`scripts/propozycje.py`, `recenzent/skrypty/skan-pr.sh`) i wszystko, co pozwala agentowi działać poza
`uprawnienia.yaml`.

Poza zakresem: zachowanie samego modelu oraz błędna konfiguracja własnego `org.yaml` / `uprawnienia.yaml`.

Staramy się potwierdzić zgłoszenie w ciągu 7 dni. Nie prowadzimy programu nagród.
