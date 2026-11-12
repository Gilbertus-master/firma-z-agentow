# Współtworzenie

Dziękujemy za ulepszanie rdzenia. Są dwie drogi:

1. **Automatycznie, z działającej floty** – jeśli właściciel firmy włączył dzielenie się (README, „Dzielenie się
   ulepszeniami”; wybór właściciela przy `scripts/init-org.sh --dziel-sie tak|nie`). Wtedy w każdy poniedziałek architekt uruchamia `scripts/propozycje.py` i zakłada tutaj
   Issue ze zmianami mechanizmów i sprawdzonymi regułami. Zgłoszenie jest wkładem w rozumieniu sekcji 5 licencji Apache-2.0
   i zawiera oświadczenie o zgodzie właściciela oraz o zgodności z Developer Certificate of Origin 1.1.
2. **Ręcznie.** Załóż Issue (szablon „Propozycja ulepszenia”) albo pull request.

## Jak wysyłać uwagi i odkrycia do wydawcy
Kanałem jest to publiczne repozytorium. Trzy drogi, od najprostszej:
1. **Zgłoszenie** (Issue) – wzory „Propozycja ulepszenia”, „Wymiana – odkrycie”, „Zgłoś swój projekt”.
2. **Rekord procesu 16** jednym poleceniem: `python3 -I scripts/wymiana.py wyslij <rekord.json> --zakazane "<nazwy firm, klientów>"` –
   domyślnie do repo wydawcy tej edycji, po świadomym wyborze (`repo.dziel_sie_ulepszeniami: true` albo `--publicznie`); bez uprawnień w repo wydawcy – etykiety nadaje
   jego workflow `wymiana-etykiety.yml`.
3. **Pull request** z podpisem DCO (zasady niżej).

Zgłoszenia są **jawne** i przechodzą bramkę danych; nie wklejaj danych klientów, sekretów ani nazw firm. Każdego, kto korzysta
z kodu, prosimy o zgłoszenie „Zgłoś swój projekt” (zapisanie się jako kontrybutor) – to zasada współpracy, nie warunek licencji.

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
