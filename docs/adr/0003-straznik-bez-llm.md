# ADR 0003 · Strażnik floty bez LLM · status: przyjęty · 2026-11-09

## Kontekst
W organizacji źródłowej flota 21 agentów gubiła pracę w sposób, którego żaden agent sam nie zauważał: 6 opinii testerów przez 12 godzin poza rejestrem
(zadanie je przeczytało, ale nie zapisało), przebiegi, które się nie odbyły po przełączeniu konta, PR-y bez werdyktu, zlecenia po terminie
bez odpowiedzi, duble PR-ów. Raporty agentów mówiły „succeeded”. Potrzebny był nadzorca, który (a) nie podziela ślepych punktów modelu,
(b) nie da się zmanipulować treścią, (c) kosztuje zero tokenów i działa, gdy limit konta jest wyczerpany, (d) sprawdza stan **u źródła**
(tagi w origin, API PR-ów, API sklepu, pliki rejestrów), nie w raportach.

## Decyzja
Strażnik floty (`moduly/straznik/`) to **deterministyczny skrypt Pythona ze standardowej biblioteki, bez LLM**, uruchamiany co 15 minut
(GitHub Actions – bez laptopa; alternatywnie launchd). Kontrole rdzenia: przebiegi (tag `przebieg/<agent>/<okienko>` 1:1 z `scripts/przebieg.sh`
i `koordynacja-odstepy.tsv`), PR-y bez werdyktu recenzenta > 60 min, zlecenia po terminie bez odpowiedzi, konfiguracja zadań, budżety
(80 % ostrzeżenie, 100 % HALT), martwe agenty. Wtyczki per organizacja (np. opinie testerów ze sklepu vs rejestr). Alert = mail do operatora,
wpis PILNE do CEO, bez dubli i z przypomnieniami; własny klon, nigdy stash/reset/force.

## Konsekwencje
- Kontrola niezależna od modelu: strażnik widzi tylko ID, liczby i daty – nie czyta treści, więc nie ma czego wstrzykiwać.
- Wymusza projekt: wszystko, co ma być pilnowane, **musi mieć ID i rejestr** (kontrakt przebiegu z uzgodnieniami `przeczytane`/`w_rejestrze`,
  rejestry startowe ról, tagi okienek). Czego nie da się policzyć, tego strażnik nie pilnuje – i to jest sygnał do poprawy rejestru.
- Zero tokenów, działa przy wyczerpanym limicie i wyłączonym laptopie; ma też prawo założyć HALT (budżet floty) – jedyny automat z tym prawem.
- Koszt: utrzymanie kontroli przy zmianie harmonogramu (test `test_straznik.py`, zgodność z `przebieg.sh`), sekrety w CI, fałszywe alarmy
  przy opóźnionych startach (okienka < 60 min dopuszczają tag w następnym okienku).

## Źródło
Organizacja źródłowa: analiza niezawodności floty (11.2026), `moduly/straznik/README.md`;
`docs/raport/2026-11-09-raport.md` rozdz. 1.2 i 4.2 pkt 4 („kontrola deterministyczna: skrypty, testy i hooki pilnują agentów, nie kolejny agent”);
research „Standardy 2026” – sekcja „Niezawodność: git + cron wystarcza…”, rek. 5 (dead-letter), „Co zostawić bez zmian” (strażnik bez LLM).
