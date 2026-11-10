# Operator – interfejs białkowy

Operator to jedyny człowiek w codziennej pracy organizacji. **Raportuje do agenta CEO** i wykonuje czynności, których
agent wykonać nie może albo nie wolno mu (`uprawnienia.yaml`, poziom `operator`). Nie zarządza agentami, nie
priorytetyzuje pracy i nie decyduje o strategii – to robi CEO w granicach mandatu właściciela.

## Co robi operator (zamknięta lista)
| Kategoria | Przykłady | Dlaczego człowiek |
|---|---|---|
| Tożsamość i podpis | podpis kwalifikowany, profil zaufany (KRS, US, ZUS, KSeF – nadanie uprawnień), UPL-1 | prawo wymaga osoby fizycznej |
| Konta i KYC | założenie konta w usłudze, weryfikacja tożsamości (bank, Stripe, Apple, Google), 2FA | KYC, regulaminy, odpowiedzialność |
| Pieniądze | przelew przygotowany przez agenta, zasilenie salda, karta firmowa | zasady.md pkt 3 |
| Logowania w GUI | panel bez API (np. sklep z aplikacjami), CAPTCHA, odnowienie sesji | agent nie obchodzi zabezpieczeń |
| Świat fizyczny | odbiór poczty, wizyta w urzędzie, sprzęt | agent nie ma rąk |
| Kontakt wymagający człowieka | telefon, gdy rozmówca nie przyjmuje AI, spotkanie | wybór rozmówcy |

Wszystko spoza listy wraca do CEO z pytaniem „dlaczego to robi człowiek?”. Każde zadanie operatora powinno mieć plan
usunięcia człowieka z pętli (API, pełnomocnictwo, konto usługowe) – CEO śledzi to w KPI „minuty operatora / tydzień”.

## Jak pracuje
1. Raz albo dwa razy dziennie (albo po powiadomieniu) otwiera `operator/kolejka.md`.
2. Każde zadanie ma gotowe, numerowane kroki, linki i oczekiwany wynik. Operator nie musi niczego wymyślać.
3. Wynik wpisuje w kolumnie „Wynik” (bez sekretów: „konto założone, login w 1Password: pozycja X”).
4. Problem albo wątpliwość → wpis w kolumnie „Uwagi” i powiadomienie CEO (czat CEO).

## SLA
Czas reakcji z `org.yaml → ludzie.operator.sla_godziny`. Zadanie po terminie CEO eskaluje do właściciela
(`ceo/do-decyzji.md`), bo blokuje organizację.

## Właściciel a operator
Właściciel ustala mandat, budżet, granice i zatwierdza decyzje z `ceo/do-decyzji.md`. Może być tą samą osobą co
operator, ale role trzymamy osobno: decyzja (właściciel) i wykonanie (operator) zostawiają osobny ślad.
