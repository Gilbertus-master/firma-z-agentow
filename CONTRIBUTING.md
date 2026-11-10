# Współtworzenie

Dziękujemy za ulepszanie rdzenia. Są dwie drogi:

1. **Automatycznie, z działającej floty** – jeśli właściciel firmy włączył dzielenie się (README, „Dzielenie się
   ulepszeniami”; domyślnie wyłączone). Wtedy w każdy poniedziałek architekt uruchamia `scripts/propozycje.py` i zakłada tutaj
   Issue ze zmianami mechanizmów i sprawdzonymi regułami. Zgłoszenie jest wkładem w rozumieniu sekcji 5 licencji Apache-2.0
   i zawiera oświadczenie o zgodzie właściciela oraz o zgodności z Developer Certificate of Origin 1.1.
2. **Ręcznie.** Załóż Issue (szablon „Propozycja ulepszenia”) albo pull request.

## Zasady
- **Licencja.** Wkład przyjmujemy na licencji Apache-2.0, czyli licencji tego repozytorium (sekcja 5 licencji), bez
  dodatkowych warunków.
- **DCO, nie CLA.** Podpisuj każdy commit (`git commit -s`). Podpis potwierdza Developer Certificate of Origin 1.1
  (https://developercertificate.org): zmiana jest Twoja albo masz prawo zgłosić ją na licencji projektu.
- **Bez danych firmy.** Żadnych nazw, adresów e-mail, numerów NIP i kont, danych klientów, sekretów ani wewnętrznych
  ścieżek – w kodzie, testach, zgłoszeniach i logach. Odrzuca je bramka `scripts/propozycje.py sprawdz` i recenzenci.
- **Testy.** `bash scripts/testy.sh` ma być zielone; nowy mechanizm przychodzi z wierszem w tablicy `TESTY`.
- **Zakres.** Rdzeń to mechanizmy: hook uprawnień, audyt, HALT, strażnik, kolejka scalania, kontrakt przebiegu, pomiar
  kosztu, ewaluacje, zgłoszenia. Role i procesy trafiają do rdzenia tylko po uogólnieniu przez opiekunów (zgłoszenie z floty
  może je zawierać); polityki i dane konkretnej firmy tu nie trafiają.
- **Język.** Kod, identyfikatory i nazwy plików są po polsku w obu edycjach; zgłoszenia i PR-y mogą być po polsku albo
  po angielsku. Zmianę dokumentu zgłaszaj w tej edycji, w której pracujesz – drugą wersję językową uzupełnią opiekunowie.
