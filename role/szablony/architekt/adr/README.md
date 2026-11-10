# ADR – rejestr decyzji architektonicznych produktu (agent architekt)

**Cel.** Każda decyzja, która kosztuje przy zmianie (baza, hosting, framework, model danych, granice modułów, interfejs agentowy,
migracje klasy B), ma krótki zapis: kontekst, decyzja, konsekwencje, źródło. Nowa sesja czyta ADR zamiast odtwarzać uzasadnienie
z dzienników. ADR organizacji (nie produktu) są w `docs/adr/` szablonu.

**Zasady.** Jeden plik `NNNN-<temat>.md`, numer kolejny, status `proponowany` → `przyjęty` (CEO albo decyzja właściciela, gdy dotyka
`uprawnienia.yaml` / kosztów ponad próg) → `zastąpiony przez NNNN` / `wycofany`. ADR nie zmienia się po przyjęciu – zastępuje go nowy.
Bez danych osobowych i sekretów (nazwy usług – tak, klucze i adresy – nie). **Aktualizuje:** architekt – przy każdej specyfikacji z etapu 8
procesu `procesy/10-budowa-produktu.md` i przy każdej migracji klasy B; recenzent sprawdza w PR-ze, że decyzja ma ADR.

| Nr | Tytuł | Status | Data | Zastępuje |
|---|---|---|---|---|

## Szablon

```markdown
# ADR NNNN · <tytuł> · status: proponowany · RRRR-MM-DD · autor: architekt

## Kontekst
Co wymusza decyzję (wymaganie, ograniczenie, pomiar, incydent). Liczby ze źródłem i datą.

## Rozważane opcje
1. … – zalety / wady / koszt
2. …

## Decyzja
Jedno zdanie. Kto zatwierdził (CEO wpis „[Decyzja CEO]” / D-…).

## Konsekwencje
Co zyskujemy, co tracimy, co trzeba zrobić (zlecenia, migracje, testy), kiedy przejrzeć ponownie.

## Źródła
Linki (dokumentacja, pomiar, specyfikacja `docs/…`, PR).
```
