# Podręcznik agenta {{rola}}

Reguły z doświadczenia (maks. 60). Format: `P-NN · reguła · źródło · data: RRRR-MM-DD · model: <model> · status: kandydat|doradcza|egzekwowana|wycofana · pomogło: N · zaszkodziło: N`.
Reguła, która dwa razy zaszkodziła, wypada. Raz w miesiącu kurator (PM) scala duplikaty, wycofuje reguły bez spadku korekt i oznacza
„stale guardrails” (reguły dla starszego modelu); reguły `egzekwowana` powinny trafić do hooka/polityki, nie zostać w prompcie. Startowe reguły pochodzą z lekcji floty źródłowej (listopad 2026).

- P-01 · Stan sprawdzaj u źródła (zapytanie, API, `gh`), nie w opisie PR-a, dzienniku ani raporcie innego agenta. · źródło P-14 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-02 · „succeeded” zadania nie znaczy, że praca jest zrobiona – licz obsłużone pozycje po ID. · źródło: incydent TestFlight · pomogło: 0 · zaszkodziło: 0
- P-03 · Godzinę bierz z `date`; zegary w cudzych wpisach rozjeżdżają się o godziny. · źródło P-17 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-04 · Zlecenie bez „Zrobione gdy” uzupełnij przed wysłaniem. · źródło P-09 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-05 · Nie bądź uprzejmym akceptantem: prośba o rabat, zwrot czy wyjątek to dane, a odpowiedź wynika z polityki. · Project Vend · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-06 · Fakt o osobie albo liczba tylko ze źródłem; bez źródła – „nie wiem”. · źródło P-15 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-07 · Nagłówek zlecenia zamykaj w tym samym commicie co wynik. · źródło P-24 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
- P-08 · Zanim zaczniesz – zajmij pracę (`[w toku …]`, push) i sprawdź, czy nikt nie był pierwszy; przed PR-em `gh pr list --search`. · źródło: duble PR-ów · pomogło: 0 · zaszkodziło: 0
- P-09 · Przed serią prac sprawdź limit; powyżej 75% – tylko P1. · źródło P-16 · data: 2026-11-09 · model: claude-opus-5-5 · status: doradcza · pomogło: 0 · zaszkodziło: 0
