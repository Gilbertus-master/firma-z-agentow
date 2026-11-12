---
name: Wymiana – zgodność szkieletu (tylko przez narzędzie)
about: Rekordy procesu 16 tworzy wyłącznie scripts/zgodnosc.py + scripts/wymiana.py – zgłoszenie pisane ręcznie będzie „poza schematem”
title: "[zgodnosc] "
labels: ["wymiana", "typ:zgodnosc"]
---

<!-- Nie wypełniaj ręcznie. W repo projektu:
  python3 -I scripts/zgodnosc.py                                   # tabela: identyczne / zmienione / brakujące, obszary
  python3 -I scripts/zgodnosc.py --rekord <projekt> --plan "<co dalej, jedno zdanie>" --wyjscie zgodnosc.json
  python3 -I scripts/wymiana.py wyslij zgodnosc.json --zakazane "<nazwy firm i klientów>"
Rekord zawiera tylko liczby i ścieżki szkieletu wspólne z szablonem – bez treści plików i bez ścieżek istniejących tylko w projekcie.
Opis: procesy/16-wymiana-ceo.md, sekcja „Zbieżność struktury” -->
