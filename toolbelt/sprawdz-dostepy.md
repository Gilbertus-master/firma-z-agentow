# Kontrola dostępów (przed budową i raz w tygodniu)

Wzorzec z praktyki: zanim agent zacznie budować, sprawdza, że jest zalogowany we wszystkich usługach z planu.
Wzorzec z praktyki: konektor zniknął przy zmianie konta i agent przez pół dnia nie czytał skrzynki (wynik NIEPEŁNY).

Agent bezpieczeństwa w pełnym przeglądzie (i architekt przed każdym etapem budowy) wypełnia tabelę ze źródła –
najlżejsze wywołanie tylko do odczytu na każdą usługę:

| Usługa | Sprawdzenie (tylko odczyt) | Wynik | Data |
|---|---|---|---|
| GitHub | `gh auth status` i `gh repo view <repo>` | | |
| Skrzynki (Resend) | lista wątków skrzynki testowej | | |
| Baza | `select 1` przez Management API | | |
| Płatności | odczyt salda / listy produktów | | |
| Menedżer sekretów | `op whoami` | | |
| Konektory MCP konta Claude | lista narzędzi w sesji (ToolSearch) + odcisk w `toolbelt/mcp-odciski.tsv` zgodny | | |
| Sekrety poza sesją | `printenv \| grep -iE 'key\|token\|secret'` ⇒ pusto; `cat .env` ⇒ ZABLOKOWANE przez hook | | |
| Kill switch | `bezpieczenstwo/HALT` nie istnieje (albo istnieje świadomie – incydent otwarty) | | |

Brak dostępu → zlecenie do CEO z gotowymi krokami dla operatora (zalogowanie, odnowienie tokenu).
