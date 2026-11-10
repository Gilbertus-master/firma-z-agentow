> **W szablonie:** specyfikacja przeniesiona z organizacji źródłowej (8.11.2026). Pola linii JSON (sekcje 1–3), walidator
> `pm/narzedzia/przebieg-raport.py` i zasady są uniwersalne. Tabela źródeł per agent (sekcja 4) to **przykład z organizacji źródłowej**
> (np. repo produktu, sklep z aplikacjami, CI buildów mobilnych) – każda nowa organizacja wypełnia ją dla swoich agentów i usług z `toolbelt/katalog.md`.
> Wiersze ról dodanych w szablonie (inzynier, tester, lokalizacja, compliance, wywiad) są już uniwersalne – wynikają z sekcji
> „Źródła sprawdzane w każdym przebiegu” w `role/<rola>.md`; nowa rola = nowy wiersz tutaj w tym samym PR (`procesy/60-cykl-zycia-agenta.md`).
> **Pola dodane w szablonie (opcjonalne):** `model` (tekst); `koszt_usd` w linii kontraktu zostaje puste (`null`) – koszt przebiegu
> mierzy `python3 -I scripts/koszt.py zapisz --agent <agent>` (tokeny z zapisu sesji × `flota/ceny-modeli.yaml`) i zapisuje osobno
> w `przebiegi/<agent>/koszty-<data>.jsonl` (wrapper headless – z wyniku CLI); wpisanie kosztu także tutaj liczyłoby go podwójnie.
> `konto` to litera konta floty (org.yaml → runtime.konto); lista agentów = `koordynacja-odstepy.tsv` + `limit`.
> **Kontrakt v2 (`"wersja": 2`, zalecany od 10.11.2026 – research „Standardy 2026”, rek. 5):** dodatkowe pola
> `prompt_version` (hash commitu instrukcji: `git log -1 --format=%h -- <agent>/agent.md role/<agent>.md flota/szablony/`; wymagane),
> `outcome_evidence` (URL PR/commitu/pliku jako dowód spoza raportu; wymagane przy wyniku OK poza CISZĄ), `retries` (liczba ponowień
> kroków), `tool_calls` (liczba wywołań narzędzi), `escalation` (`operator|wlasciciel|ceo|brak`), `next_action` (jedno zdanie).
> Bez `prompt_version` nie da się wiązać regresji z wersją instrukcji ani robić wdrożeń kanarkowych; bez `outcome_evidence` „OK” to
> deklaracja, nie fakt (fałszywe ukończenie – MAST). Strażnik: K=3 przebiegi z rzędu z wynikiem BŁĄD → `przebiegi/dead-letter/<agent>.md`.

# Kontrakt przebiegu – specyfikacja raportu po każdym przebiegu (etap 1 niezawodności floty)

Autor: agent PM, 8.11.2026. Zlecenie: `zlecenia/pm.md` (właściciel przez CEO, „uruchom od razu”). Podstawa: `ceo/analizy/2026-11-08-niezawodnosc-floty.md`
sekcja 3 pkt 1–2 (przyczyny A i E: „przebieg zakończony” ≠ praca wykonana; CISZA bez śladu). Wdrożenie w instrukcjach agentów – CEO (blok w sekcji 7).
Spójne z równoległymi zleceniami z 8.11: strażnik floty (architekt – czyta te pliki, kontrola 1), uzgodnienia liczbowe recenzenta, aplikacji, recepcji i obsługi
(ich linie „N / M / K” to pola `nowe / obsluzone / otwarte` źródła).

## 1. Zasada

**Każdy przebieg każdego agenta kończy się jedną linią JSON** w `przebiegi/<agent>/<RRRR-MM-DD>.jsonl` – także w trybie **CISZA** (sygnał życia) i także wtedy,
gdy przebieg się nie udał (wtedy `wynik: "BŁĄD"`). Linia mówi, **co agent przeczytał (z liczbami), co z tym zrobił (z ID) i czego się nie zgadza**.
Przebieg bez linii, bez liczb albo z liczbami bez pokrycia w źródle = **przebieg nieudany**, niezależnie od statusu sesji w aplikacji Claude.
Raport nie zastępuje dziennika (`<agent>/dziennik.md` – dla ludzi i CEO) ani `stan.json` (pamięć agenta); jest dla maszyn: strażnika floty, PM-a i KPI.

Nie dotyczy: przebiegu zakończonego **kodem 10** protokołu `koordynacja.md` (drugie konto; ślad = tag `przebieg/<agent>/<okienko>` na origin – strażnik czyta tagi).
Czaty z właścicielem i sesje dev piszą linię tylko wtedy, gdy wykonują pracę agenta ze skrzynką (`tryb: "CZAT"`); PM w dyżurze – `tryb: "DYŻUR"`.

## 2. Plik

- Ścieżka: `przebiegi/<agent>/<RRRR-MM-DD>.jsonl` – `<agent>` = nazwa katalogu agenta (`ceo`, `ochrona-danych`, `marketing` …); data = **dzień startu** przebiegu
  w czasie Warszawy. Zadanie `org-sklepy-maile` pisze do `przebiegi/aplikacje/` z `zadanie: "org-sklepy-maile-a"`.
- Jedna linia = jeden przebieg, dopisywana na końcu (`>>`), UTF-8, bez łamania wiersza w środku, maks. 8 000 znaków (długie listy ID skracaj: pierwsze 20 + `"…+N"`).
- Dopisanie i walidacja jednym poleceniem (sekcja 6): `python3 -I pm/narzedzia/przebieg-raport.py dopisz <plik.json>` – odrzuca linię niezgodną z kontraktem
  (kod 1) i mówi dlaczego; agent poprawia i dopisuje ponownie. Bez narzędzia (brak Pythona): `printf '%s\n' '<json>' >> przebiegi/<agent>/<data>.jsonl`.
- Commit: razem z innymi plikami agenta; w CISZY **osobny commit tylko tego pliku**: `git add przebiegi/<agent>/ && git commit -m "<agent>: przebieg CISZA <data> <GG:MM>"`,
  potem `git pull --rebase` i push jak dotąd. Konflikt w `.jsonl` (dwa konta dopisały w tym samym pliku) rozwiązuje się **zachowaniem obu linii**; żeby git robił
  to sam, CEO dodaje do `.gitattributes` w katalogu głównym linię `przebiegi/**/*.jsonl merge=union` (propozycja PM – plik poza moim zakresem).
- Bez danych osobowych (żadnych adresów e-mail, nazwisk, telefonów – tylko ID wątków, liczby, role), bez sekretów, bez treści maili. Walidator odrzuca linię z adresem e-mail.
- Retencja: pliki dzienne zostają w repo; PM pierwszego dnia miesiąca scala poprzedni miesiąc do `przebiegi/<agent>/<RRRR-MM>.jsonl` (jedna operacja, bez zmiany treści linii).

## 3. Pola linii

| Pole | Typ | Obowiązkowe | Znaczenie |
|---|---|---|---|
| `wersja` | liczba | tak | Wersja kontraktu – dziś `1` (narzędzie dopisuje samo). |
| `agent` | tekst | tak | Nazwa katalogu agenta (w szablonie 21 ról z `role/`: ceo, pm, architekt, inzynier, recenzent, tester, aplikacje, lokalizacja, wywiad, marketing, sprzedaz, obsluga, recepcja, inwestorzy, finansowy, ksiegowy, podatkowy, prawny, compliance, ochrona-danych, bezpieczenstwo; organizacja ma tyle, ile ma w `koordynacja-odstepy.tsv`). |
| `zadanie` | tekst | nie | Id zadania zaplanowanego (`org-prawny-a`, `org-sklepy-maile-a`) albo `czat` / `sesja:<local_…>` / `dyzur`. |
| `konto` | `"A"`/`"B"` | tak | Z treści zadania („Konto: B”; brak = A) – jak w `koordynacja.md`. |
| `okienko` | liczba | nie | Wynik `scripts/przebieg.sh okienko <agent>` – spina linię z tagiem blokady `przebieg/<agent>/<okienko>`. |
| `start`, `koniec` | tekst ISO 8601 ze strefą | tak | `2026-11-08T13:04:00+01:00` (czas Warszawy; `date -Iseconds`). `koniec` uzupełnia narzędzie, gdy brak. |
| `tryb` | tekst | tak | Jak w instrukcji agenta: `CISZA`, `ZDARZENIE`, `DZIENNY`, `TYGODNIOWY`, `PEŁNY`, `PRACA` (architekt), `WYDANIE` (marketing), `CZAT`, `DYŻUR`, `BŁĄD` (przebieg przerwany przed wyborem trybu). |
| `zrodla` | lista obiektów | tak, niepusta (także CISZA) | Jedno na **każde obowiązkowe źródło pracy agenta** z sekcji 4 – nawet gdy wszystko = 0. Pola niżej. |
| `akcje` | lista obiektów | tak (może być `[]`) | Co agent zrobił, **po ID**: `{"typ": "zlecenie|pr|commit|plik|wpis|zlecenie_dla|sesja|przypomnienie|decyzja", "id": "…", "opis": "≤ 80 znaków"}`. |
| `rozbieznosci` | lista obiektów | tak (może być `[]`) | Każde źródło, w którym liczby się nie zgadzają (sekcja 5): `{"zrodlo", "opis", "liczby": {…}, "ids": […], "dzialanie"}`. |
| `bledy` | lista obiektów | tak (może być `[]`) | `{"gdzie": "Resend|gh|ASC|Supabase|git|skrypt <nazwa>|…", "komunikat": "≤ 200 znaków, bez sekretów", "skutek": "przebieg przerwany|źródło pominięte|akcja nieudana", "zrodlo": "<nazwa źródła, jeśli dotyczy>"}`. |
| `wynik` | tekst | tak | `OK` · `ROZBIEŻNOŚĆ` (lista `rozbieznosci` niepusta) · `NIEPEŁNY` (któreś źródło ma `przeczytane: null`) · `BŁĄD` (przebieg przerwany). Walidator wylicza i pilnuje zgodności. |
| `raport` | tekst | nie | Jedno zdanie dla człowieka (≤ 160 znaków) – to samo, co zdanie końcowe przebiegu. |
| `kpi` | tekst | nie | Treść linii `**KPI:**` z dziennika (procedura KPI pkt 1), żeby pomiar nie musiał czytać dziennika. |

### Obiekt źródła (`zrodla[]`)

| Pole | Znaczenie |
|---|---|
| `nazwa` | Stała nazwa z sekcji 4 (np. `kontakt@`, `zlecenia/prawny.md`, `PR otwarte produkt`, `ASC uwagi`). |
| `przeczytane` | Ile pozycji agent **faktycznie pobrał** ze źródła w tym przebiegu (cała lista, nie „od ostatniego razu”, gdy sekcja 4 mówi „wszystkie”). `null` = źródła nie udało się przeczytać → obowiązkowy wpis w `bledy` z tym `zrodlo`; **nigdy `0` zamiast `null`**. |
| `nowe` | Ile z nich jest nowych od ostatniego przebiegu albo **nie ma ich w rejestrze** (porównanie po ID, nie po dacie/statusie). |
| `obsluzone` | Ile z `nowe` agent obsłużył w tym przebiegu (wpis w rejestrze + akcja). `obsluzone ≤ nowe`. |
| `w_rejestrze` | Ile pozycji tego źródła ma rejestr agenta po przebiegu (dla uzgodnienia: `przeczytane` ↔ `w_rejestrze`). |
| `otwarte` (opcjonalne) | Pozycje czekające po przebiegu (np. zgłoszenia bez zamknięcia, PR bez werdyktu, zlecenia bez odpowiedzi). |
| `ids_bez_sladu` (opcjonalne) | ID pozycji nowych i nieobsłużonych (≤ 20) – to, co strażnik i PM mają sprawdzić. |
| `okres` (opcjonalne) | Od kiedy liczone `nowe`, gdy źródło czyta się przyrostowo (`"od": "2026-11-08T10:15:00+01:00"`). |

### Przykład – CISZA (recepcja)

```json
{"wersja":1,"agent":"recepcja","zadanie":"org-recepcja-a","konto":"B","okienko":4712,"start":"2026-11-08T13:15:10+01:00","koniec":"2026-11-08T13:17:02+01:00","tryb":"CISZA",
 "zrodla":[{"nazwa":"kontakt@","przeczytane":1,"nowe":0,"obsluzone":0,"w_rejestrze":1,"otwarte":0},
           {"nazwa":"zlecenia/recepcja.md","przeczytane":0,"nowe":0,"obsluzone":0,"w_rejestrze":0,"otwarte":0}],
 "akcje":[],"rozbieznosci":[],"bledy":[],"wynik":"OK","raport":"kontakt@: wątki nowe 0, obsłużone 0, otwarte 0 – brak nowych zleceń."}
```

### Przykład – ROZBIEŻNOŚĆ (recenzent)

```json
{"wersja":1,"agent":"recenzent","zadanie":"org-recenzent-a","konto":"B","start":"2026-11-08T10:45:20+01:00","koniec":"2026-11-08T11:40:00+01:00","tryb":"ZDARZENIE",
 "zrodla":[{"nazwa":"PR otwarte produkt","przeczytane":6,"nowe":2,"obsluzone":1,"w_rejestrze":5,"otwarte":1,"ids_bez_sladu":["produkt#214"]},
           {"nazwa":"zlecenia/recenzent.md","przeczytane":3,"nowe":1,"obsluzone":1,"w_rejestrze":3,"otwarte":2}],
 "akcje":[{"typ":"pr","id":"produkt#213","opis":"werdykt OK, klasa A, próba wycofana"},{"typ":"plik","id":"recenzent/recenzje/2026-11-08-pr-213.md","opis":"recenzja"},
          {"typ":"zlecenie_dla","id":"zlecenia/architekt.md › 2026-11-08 · produkt#213 uwaga 2","opis":"poprawka search_path"}],
 "rozbieznosci":[{"zrodlo":"PR otwarte produkt","opis":"PR bez werdyktu dla head SHA po przebiegu","liczby":{"otwarte":6,"z_werdyktem_dla_head":5},"ids":["produkt#214"],
                  "dzialanie":"nie zmieścił się w przebiegu – zapisany w stan.json → kolejka[0], wpis Pilne w zlecenia/ceo.md"}],
 "bledy":[],"wynik":"ROZBIEŻNOŚĆ","raport":"PR otwarte: 6, z werdyktem dla head: 5, bez: 1 (#214 – następny przebieg)."}
```

### Przykład – BŁĄD źródła (obsługa, Resend nie odpowiada)

```json
{"wersja":1,"agent":"obsluga","konto":"B","start":"2026-11-08T14:35:00+01:00","koniec":"2026-11-08T14:37:00+01:00","tryb":"ZDARZENIE",
 "zrodla":[{"nazwa":"support@","przeczytane":null,"nowe":null,"obsluzone":null,"w_rejestrze":3,"otwarte":1},
           {"nazwa":"zlecenia/obsluga.md","przeczytane":2,"nowe":0,"obsluzone":0,"w_rejestrze":2,"otwarte":2}],
 "akcje":[{"typ":"zlecenie_dla","id":"zlecenia/ceo.md › 2026-11-08 · Resend support@ – brak dostępu","opis":"zgłoszenie awarii narzędzia"}],
 "rozbieznosci":[],"bledy":[{"gdzie":"Resend list-inbox-threads","komunikat":"HTTP 503 po 3 próbach","skutek":"źródło pominięte","zrodlo":"support@"}],
 "wynik":"NIEPEŁNY","raport":"uzgodnienie skrzynki niewykonane: Resend 503 – zgłoszone CEO."}
```

## 4. Źródła pracy agentów – lista do uzgodnień po ID

Każdy agent ma **źródła obowiązkowe** (zawsze w `zrodla`, także w CISZY) i rejestr, z którym je uzgadnia. Porównanie zawsze **po identyfikatorze** (ID wątku Resend,
numer PR + head SHA, ID uwagi ASC, nagłówek zlecenia = plik + data + temat), nigdy po dacie, statusie ani „z pamięci” (`stan.json` to podpowiedź, nie źródło).
Wspólne dla wszystkich: (a) `zlecenia/<agent>.md` – `przeczytane` = nagłówki `[otwarte]`/`[w toku]`/`[czeka…]`, `nowe` = bez odpowiedzi od ostatniego przebiegu,
`obsluzone` = odpowiedziane/zmieniony status w tym przebiegu, `w_rejestrze` = nagłówki ze statusem i linią `Termin:`, `otwarte` = po przebiegu; (b) `decyzje.md` –
nowe wpisy od `stan.json → ostatni_przebieg` dotyczące agenta (`nowe`) i uwzględnione (`obsluzone`). Poniżej źródła dodatkowe.

| Agent | Źródło (`nazwa`) | Co liczyć (`przeczytane` / `nowe` / `obsluzone` / `w_rejestrze`) | Rejestr (po ID) | Rozbieżność = |
|---|---|---|---|---|
| **ceo** | `PR otwarte produkt` | `gh pr list --state open` w repo produktu (bez draftów, bez „[20.11”) / bez werdyktu dla head SHA / zgłoszone recenzentowi lub uruchomione zadanie / PR-y z werdyktem | `recenzent/stan.json → recenzje` (numer + sha) | PR bez werdyktu > 60 min od otwarcia/aktualizacji |
| | `zlecenia/ceo.md` | jak wspólne; dodatkowo `otwarte` = wpisy „Pilne” bez odpowiedzi | – | Pilne bez odpowiedzi po przebiegu |
| | `dzienniki agentów` | 16 dzienników / agenci z nowym wpisem od ostatniego przebiegu / przeczytane / – ; `ids_bez_sladu` = agenci bez wpisu i bez linii w `przebiegi/` od > 1 okienka | `przebiegi/<agent>/` | agent bez przebiegu w swoim oknie |
| | `rejestr-sesji.md` | sesje `otwarta` / nowe od ostatniego przebiegu / zamknięte lub porzucone w tym przebiegu / wiersze | `list_sessions` (id) | sesja > 24 h bez postępu, bez rodzica, w `list_sessions` a nie w rejestrze |
| | `straznik` (od wdrożenia) | rozbieżności w `ceo/straznik.json` / nowe od ostatniego przebiegu / obsłużone (zlecenie, decyzja) / – | `ceo/straznik-zdarzenia.md` | rozbieżność strażnika bez akcji > 1 przebieg |
| | `decyzje właściciela` | nowe wpisy w `decyzje.md` / – / przekazane agentom (zlecenie z odwołaniem) / sprawy w `ceo/do-decyzji.md` | `ceo/do-decyzji.md` (nr) | decyzja bez zlecenia; sprawa > 48 h |
| **architekt** | `zlecenia/architekt.md` | wspólne; `otwarte` = bez PR-a/pakietu po terminie | `stan.json → w_budowie` | zlecenie w toku bez etapu w rejestrze postępu > 1 okienko |
| | `PR własne otwarte` | PR-y architekta i sesji dev (`gh pr list --author`, etykieta/gałąź `claude/architekt-*`, pakiety `architekt/rownolegle/`) / nowe / z odpowiedzią na uwagi recenzenta / w `stan.json → w_budowie` | `stan.json`, `architekt/rownolegle/*.md` | PR z uwagami recenzenta bez odpowiedzi > 1 okienko; pakiet bez sesji > 24 h |
| | `sesje dev (rodzic: architekt)` | sesje w `rejestr-sesji.md` z rodzicem architekt / nowe raporty / odebrane (wynik sprawdzony, linia zamknięta) / wiersze | `rejestr-sesji.md` | raport sesji nieodebrany > 1 okienko |
| | `opinie TestFlight → pakiety` | zlecenia od aplikacji z ID uwagi ASC / nowe / ocenione (zgodne → pakiet/PR; wątpliwe → `zlecenia/ceo.md`) / wpisy w dzienniku `**TestFlight:**` | `aplikacje/opinie-testflight.md` (ID uwagi) | uwaga u architekta bez PR-a/pakietu/decyzji > 24 h |
| **recenzent** | `PR otwarte produkt` | `gh pr list --state open` (bez draftów, bez „[20.11”) **po numerze i head SHA** / bez werdyktu dla aktualnego SHA / zrecenzowane w przebiegu / wpisy `stan.json → recenzje` | `recenzent/stan.json → recenzje` | PR bez werdyktu dla head po przebiegu (`ids_bez_sladu`) |
| | `PR scalone 7 dni` (PEŁNY) | scalone / naprawcze (naprawa/fix/revert) po PR-ach z werdyktem OK / – / – | `recenzent/stan.json` | naprawczy po OK → wpis w podręczniku |
| **aplikacje** | `ASC uwagi` | `betaFeedbackScreenshotSubmissions` + `betaFeedbackCrashSubmissions` **wszystkie, po ID** / ID nie w rejestrze / zarejestrowane + zlecenie w przebiegu / wiersze rejestru | `aplikacje/opinie-testflight.md` | `przeczytane ≠ w_rejestrze` albo nowe > obsłużone |
| | `ASC buildy` | buildy z `externalBuildState`, grupy / nowe od `stan.json → ostatni_build` / zapisane / – | `aplikacje/stan.json` | build o stanie błędu; brak nowego buildu > 24 h po scaleniu w `main` (gdy Codemagic działa) |
| | `Codemagic` | ostatnie buildy (status) / nieudane od ostatniego przebiegu / zgłoszone / – | `aplikacje/stan.json` | `402`/`failed` bez zgłoszenia (incydent 2 z analizy) |
| | `apps@` | wątki Resend (wszystkie strony) po ID / nowe lub z nową wiadomością / streszczone + akcja / wiersze rejestru skrzynki | rejestr skrzynki w `aplikacje/` (wg `agent.md`) | wątek bez śladu |
| | `recenzja sklepów` | status wersji App Store Connect i Google Play / zmiana od `stan.json` / zapisana + zgłoszona CEO / – | `aplikacje/stan.json` | zmiana statusu bez wpisu |
| **aplikacje (zadanie `org-sklepy-maile-a`)** | `ASC uwagi`, `ASC buildy`, `recenzja sklepów` jak wyżej; `opinie/widziane.json` ↔ rejestr (ten sam ID) | | `aplikacje/opinie-testflight.md`, `opinie/widziane.json` | ID widziane, ale nie w rejestrze |
| **recepcja** | `kontakt@` | **wszystkie** wątki (inbox, archive, spam; stronicowanie) / ID nie w rejestrze lub nowa wiadomość w starym wątku / wiersz z przekazaniem lub oznaczeniem spam/test / wiersze rejestru | `recepcja/rejestr.md` (kolumna Id wątku) | `otwarte` > 0 po przebiegu (wdrożone 8.11 – `agent.md` pkt 2) |
| **obsluga** | `support@` | wątki z ostatnią wiadomością po `ostatni_przebieg_at` (wszystkie strony) / bez śladu w rejestrze / wiersz + szkic/zlecenie / wiersze; `otwarte` = zgłoszenia bez „zamknięte”/„wysłane” | `obsluga/zgloszenia.md` | wątek bez śladu (`agent.md` pkt 2a) |
| | `zgłoszenia otwarte` | wiersze otwarte / nowe / zamknięte w przebiegu / – ; `otwarte` = czekające na zgodę właściciela (szkic gotowy) | `obsluga/zgloszenia.md` | szkic czeka > 48 h bez przypomnienia |
| **prawny** | `legal@` | wątki Resend po ID / nowe / streszczone + akcja / wiersze rejestru skrzynki | rejestr skrzynki w `prawny/` | wątek bez śladu |
| | `PR-y dokumentów` | `gh pr list --state all --limit 30` z plikami regulaminu/polityki/`app/sklepy/teksty`/`lang` / nowe od `stan.json → ostatni_pr` / ocenione (wpis w rejestrze ryzyk albo „bez uwag” w dzienniku) / – | `prawny/stan.json`, `prawny/rejestr-ryzyk.md` | PR zmieniający dokument bez oceny > 24 h |
| | `rejestr ryzyk` | ryzyka otwarte / nowe / zaktualizowane / wiersze; `otwarte` = wysokie | `prawny/rejestr-ryzyk.md` | ryzyko wysokie bez działania z datą |
| | `kalendarz terminów prawnych` (po założeniu – KPI A-prawny-1) | terminy ≤ 30 dni / nowe / z przygotowaną czynnością / wiersze | `prawny/kalendarz.md` | termin < 14 dni bez przygotowania |
| **ochrona-danych** | `privacy@` | wątki po ID / nowe / zarejestrowane (żądanie → `rejestr-zadan.md` natychmiast) / wiersze | `ochrona-danych/rejestr-zadan.md` + rejestr skrzynki | żądanie osoby bez wpisu; termin art. 12 (30 dni) < 7 dni |
| | `naruszenia` | zgłoszenia naruszeń (skrzynka, zlecenia, dzienniki bezpieczeństwa) / nowe / ocenione (72 h) / wiersze | rejestr naruszeń (`stan.json → naruszenia_otwarte`) | naruszenie bez oceny > 24 h |
| | `PR-y z danymi osobowymi` | PR-y w `dom` zmieniające schemat `dom`/`anon`/eksport/usuwanie (`files` z `supabase/migrations`, `dom-konto-usun`) / nowe / z opinią / – | `ochrona-danych/analizy/` | migracja dotykająca danych osobowych bez opinii przed scaleniem |
| **bezpieczenstwo** | `security@` | wątki po ID / nowe / zarejestrowane + ocena CVSS / wiersze | `bezpieczenstwo/rejestr.md` | zgłoszenie bez oceny > 24 h |
| | `alerty GitHub` | `gh api repos/OWNER/produkt/dependabot/alerts?state=open` (+ code scanning, secret scanning) / nowe / ocenione / wiersze rejestru | `bezpieczenstwo/rejestr.md` | alert otwarty > 7 dni bez wpisu |
| | `Supabase advisors` | liczby ERROR / WARN / INFO (`get_advisors`) / nowe ERROR / zgłoszone architektowi / poprzedni pomiar w `stan.json` | `bezpieczenstwo/stan.json` | ERROR > 0; WARN wzrosło bez zlecenia |
| | `PR-y wrażliwe` | PR-y z plikami auth/RLS/sekretów/Edge Functions / nowe / przejrzane / – | `bezpieczenstwo/stan.json → ostatni_pr` | PR wrażliwy scalony bez przeglądu |
| **podatkowy** | `tax@` | wątki po ID / nowe / streszczone + akcja / wiersze | rejestr skrzynki w `podatkowy/` | wątek bez śladu |
| | `kalendarz terminów podatkowych` | terminy ≤ 30 dni / nowe / z przygotowaną deklaracją lub decyzją / wiersze | `podatkowy/kalendarz*.md` | termin < 7 dni bez statusu „przygotowane” |
| **ksiegowy** | `accounting@` | wątki po ID / nowe / zarejestrowane (załącznik → `~/org-spolka-dokumenty/`, w repo tylko nazwa) / wiersze | rejestr skrzynki w `ksiegowy/` | faktura w mailu bez wpisu |
| | `Stripe ↔ księgi` | transakcje Stripe miesiąca (agregat select z `ksiegowosc`) / nieuzgodnione / uzgodnione / – | `ksiegowy/miesiace/RRRR-MM.md` | nieuzgodnione > 0 po 5. dniu następnego miesiąca |
| | `paczka miesiąca` | pozycje listy zamknięcia / nowe dokumenty / odhaczone / – ; `otwarte` = brakujące | `ksiegowy/miesiace/RRRR-MM.md` | brak pozycji 3 dni przed terminem paczki |
| **finansowy** | `finance@` | wątki po ID / nowe / streszczone + akcja / wiersze | rejestr skrzynki w `finansowy/` | wątek bez śladu |
| | `alerty finansowe` | alerty z `system-raportowania.md` rozdz. 7 sprawdzone / aktywne / zgłoszone / – | `finansowy/kpi.md` | alert aktywny bez zgłoszenia |
| | `KPI tygodnia` (czwartek) | 1 wiersz tygodnia / brak = 1 nowe / dopisany / wiersze | `finansowy/kpi.md` | czwartek bez wiersza (KPI A-finansowy-1) |
| **sprzedaz** | `partnerships@` + `sales@` | wątki po ID (obie skrzynki) / nowe / firma w lejku zaktualizowana / wiersze lejka z ID wątku | `sprzedaz/lejek.md` | wątek bez firmy w lejku |
| | `lejek` | firmy / nowe / z aktualizacją statusu / wiersze; `otwarte` = „do kontaktu” z datą minioną lub czekające na „tak” właściciela | `sprzedaz/lejek.md` | firma „do kontaktu” po dacie bez akcji |
| **inwestorzy** | `investors@` | wątki po ID / nowe / streszczone + przekazane CEO (nic nie wysyła) / wiersze | rejestr skrzynki w `inwestorzy/` | wątek bez śladu > 1 okienko |
| | `investor update miesiąca` | 1 / brak w miesiącu / szkic gotowy / – | `inwestorzy/` (KPI A-inwestorzy-1) | brak szkicu po 5. dniu miesiąca |
| **marketing** | `marketing@` | wątki po ID / nowe / streszczone + akcja / wiersze | rejestr skrzynki w `dom/docs/marketing/` albo `marketing/` | wątek bez śladu |
| | `wydania i PR-y` | `app/package.json` na `origin/main`, App Store/Google Play wersja, PR-y > `stan.json → ostatni_pr` / nowe / opisane w komunikatach / – | `docs/marketing/stan.json` | wydanie bez aktualizacji komunikatów > 24 h |
| | `KPI lejka` (tydzień) | wiersz tygodnia / brak / dopisany / wiersze | `marketing/kpi.md` | tydzień bez wiersza (KPI A-marketing-3) |
| | `zadania planu` | pozycje W46 marketingu (T46.x) / nowe / z postępem w tym przebiegu / zlecenia z `Plan:` | `ceo/plan/tydzien-*.md`, `zlecenia/marketing.md` | pozycja planu bez zlecenia (PM zgłasza) |
| **inzynier** | `plany architekta` | plany w `architekt/plany/` przypisane inżynierowi / nowe od ostatniego przebiegu / z gałęzią `agent/inzynier-<temat>` lub PR-em / wpisy `stan.json → w_toku` | `inzynier/stan.json` | plan przypisany bez gałęzi > 1 okienko; praca poza planem (PR bez planu i zlecenia) |
| | `PR własne otwarte` | `gh pr list --author` + gałęzie `agent/inzynier-*` / z nową uwagą recenzenta lub czerwonym CI / z odpowiedzią (commit, komentarz) / wpisy `stan.json` | `inzynier/stan.json`, `recenzent/stan.json` (werdykt po head SHA) | uwaga recenzenta bez odpowiedzi > 1 okienko; PR otwarty > 3 dni bez ruchu |
| **tester** | `scalenia produktu` | `gh pr list --state merged` od ostatniego przebiegu, **po numerze** / bez wyniku testu / przetestowane (wynik zapisany) / wpisy `stan.json → przetestowane` | `tester/stan.json`, `tester/lista-reczna.md` | scalenie bez testu > 24 h; pozycja listy ręcznej przed wydaniem bez wyniku |
| | `błędy otwarte` | wiersze `T-…` otwarte / nowe w przebiegu / zamknięte po zweryfikowanej poprawce / wiersze; `otwarte` = krytyczne | `tester/bledy.md` (T-…) | błąd krytyczny bez zlecenia do autora w tym samym przebiegu; krytyczny otwarty > 48 h |
| **lokalizacja** | `scalenia produktu` | scalenia do gałęzi głównej od ostatniego przebiegu, po numerze PR / nie w `stan.json → sprawdzone` / skontrolowane (wynik liczbowy, „0 braków” też) / wpisy `sprawdzone` | `lokalizacja/stan.json`, `lokalizacja/rejestr.md` (L-RRRRMMDD-NN) | scalenie bez kontroli > 24 h; luka krytyczna otwarta > 6 h |
| | `Co nowego wersji w drodze` | wersje w drodze do sklepów (`aplikacje/stan.json`) / bez kompletu języków / uzupełnione / wiersze rejestru | `lokalizacja/rejestr.md` (`<wersja>@<sklep>`) | wersja przed wysyłką bez kompletu „Co nowego” |
| | `kraje dostępności` | kraje od agenta aplikacji / nowe względem rejestru / dopisane z językiem i językiem zapasowym / wiersze | `lokalizacja/kraje.md` | kraj dostępności bez języka ani języka zapasowego |
| **compliance** | `bramki wydań` | wersje w drodze do wydania (`aplikacje/stan.json`, zlecenia „bramka <wersja> <platforma>”) / bez bramki / z wykonaną bramką (przepuszczona albo zatrzymana, z listą luk) / wpisy `stan.json → bramki` | `compliance/bramka-wydania.md`, `compliance/stan.json` | wersja wysłana do sklepu lub na produkcję bez bramki |
| | `PR-y obszarów wrażliwych` | scalenia w obszarach wrażliwych od ostatniego przebiegu, po numerze PR / nieocenione / ocenione (wymóg, luka albo „bez wpływu”) / – | `compliance/rejestr-wymogow.md`, `compliance/luki.md` | scalenie wrażliwe bez oceny > 1 okienko; luka wysoka bez właściciela i terminu |
| | `kalendarz wymogów` | terminy ≤ 30 i ≤ 90 dni / nowe / z przygotowaną czynnością i właścicielem / wiersze | `compliance/kalendarz.md` | termin < 14 dni bez przygotowania |
| | `zmiany przepisów i wytycznych` | źródła z rejestru sprawdzone w przebiegu (akty, organy, sklepy) / zmiany nowe / ocenione (wymóg dopisany albo „nie dotyczy” z uzasadnieniem) / wiersze | `compliance/rejestr-wymogow.md` (źródło + data odczytu) | zmiana bez oceny > 7 dni; źródło nieczytane > 30 dni |
| **wywiad** | `źródła i konkurenci` | pozycje rejestru sprawdzone w przebiegu (`WebSearch`/`WebFetch`, URL + data odczytu) / znaleziska nowe / zapisane jako `WR-…` z EV i przekazane zleceniem / wiersze | `wywiad/rejestr.md` (WR-…) | znalezisko z EV bez zlecenia do CEO; źródło z rejestru nieczytane > 14 dni; liczba bez URL i daty |
| **pm** | `zlecenia/*.md (wszystkie)` | nagłówki otwarte we wszystkich skrzynkach / nowe od ostatniego przebiegu / ujęte w backlogu / wiersze J; `otwarte` = po terminie | `backlog.md` (J) | nagłówek bez wiersza J; J bez nagłówka; po terminie bez propozycji |
| | `zadania zaplanowane + crony` | zadania w aplikacji (lista) + `cron.job` / nowe lub zmieniony rytm / ujęte / wiersze C | `backlog.md` (C), `koordynacja-odstepy.tsv` | zadanie bez wiersza C; rytm ≠ tsv ≠ README |
| | `przebiegi/` (kontrakt) | linie z ostatnich 24 h / agenci bez linii w swoim oknie / zgłoszeni CEO / oczekiwane przebiegi z harmonogramu | `przebiegi/*/`, tagi `przebieg/*` | brak linii w oknie; `NIEPEŁNY`/`BŁĄD` bez reakcji; `rozbieznosci` otwarte > 1 okienko |
| | `rejestr-sesji.md` | sesje otwarte / nowe / zgłoszone (> 24 h, bez rodzica, dublet) / wiersze | `rejestr-sesji.md`, `list_sessions` | jak u CEO (jeden właściciel przeglądu – propozycja C-53) |

Agent, który nie ma jeszcze rejestru dla źródła (np. rejestr skrzynki, kalendarz), zakłada go przy pierwszym przebiegu po wdrożeniu (plik w swoim katalogu, kolumna z ID)
i do tego czasu podaje `w_rejestrze: 0` z rozbieżnością „brak rejestru – zakładam”. Źródło, którego agent nie może przeczytać z powodu braku narzędzia (np. Resend),
to `przeczytane: null` + `bledy`, **nie** `0`.

## 5. Reguły uzgodnień i wyniku

1. **Liczby zawsze z źródła, w tym przebiegu.** `stan.json`, poprzedni dziennik i pamięć z poprzedniego przebiegu nie są źródłem liczb (incydenty 1 i 8 z analizy).
2. **Rozbieżność** = którekolwiek: `przeczytane ≠ w_rejestrze` tam, gdzie rejestr ma zawierać wszystko (ASC uwagi, kontakt@, PR-y ↔ werdykty); `nowe > obsluzone`
   po przebiegu; pozycja z kolumny „Rozbieżność =” w sekcji 4. Każda rozbieżność ma `dzialanie` – obsłużona w tym przebiegu albo **wpis „Pilne” w `zlecenia/ceo.md`**
   (albo u właściwego agenta) **w tym samym przebiegu**; „zrobię następnym razem” jest dozwolone tylko z ID w `stan.json` i wpisem w `rozbieznosci`.
3. **CISZA jest dozwolona tylko, gdy wszystkie źródła mają `nowe = 0` i `rozbieznosci = []`.** W innym wypadku tryb to ZDARZENIE (nawet dla jednej pozycji).
4. `wynik` wylicza się z treści (walidator pilnuje): `BŁĄD` (przebieg przerwany) > `NIEPEŁNY` (źródło nieprzeczytane) > `ROZBIEŻNOŚĆ` > `OK`.
5. Linia powstaje **przed commitem końcowym**, także gdy przebieg kończy się błędem narzędzia – wtedy `tryb: "BŁĄD"` i to, co udało się ustalić.
6. **Przebieg nieudany** (dla strażnika, PM i KPI): brak linii w oknie harmonogramu (tolerancja: długość okna + 30 min), `wynik: "BŁĄD"`, `NIEPEŁNY` dwa przebiegi
   z rzędu dla tego samego źródła, albo rozbieżność bez `dzialanie`. Nieudany przebieg = linia w raporcie PM dla CEO (dziennie) i w przeglądzie piątkowym.
7. Nie dubluj: akcje opisujesz raz (w `akcje` po ID); dziennik może streszczać, nie musi powtarzać liczb.

## 6. Narzędzie `pm/narzedzia/przebieg-raport.py` (bez LLM, bez sieci)

- `python3 -I pm/narzedzia/przebieg-raport.py dopisz <plik.json | ->` – czyta obiekt JSON (plik albo stdin), uzupełnia `wersja` i `koniec`, **waliduje**
  (pola obowiązkowe, ISO 8601 ze strefą, tryb i wynik z listy, liczby całkowite albo `null` z wpisem w `bledy`, `obsluzone ≤ nowe`, zgodność `wynik` z treścią,
  brak adresów e-mail i sekretów, ≤ 8 000 znaków) i dopisuje linię do `przebiegi/<agent>/<data startu>.jsonl`. Kod 1 + lista powodów przy odrzuceniu – agent poprawia.
- `sprawdz <plik.jsonl>…` – walidacja istniejących plików (strażnik, PM). `podsumuj [dni]` – tabela per agent: przebiegi, tryby, wyniki, rozbieżności, błędy, ostatni
  (podstawa przeglądu piątkowego i wiersza KPI). Przetestowane 8.11 na przykładach z sekcji 3 (poprawna linia przyjęta, błędna odrzucona z 4 powodami).
- Zalecany wzorzec w przebiegu: zapisz JSON do pliku tymczasowego (`$TMPDIR/przebieg.json`), wywołaj `dopisz`, dopiero potem `git add`/commit.

## 7. Blok do wklejenia w `<agent>/agent.md` (wkleja CEO; `<agent>` i listę źródeł z sekcji 4 podstawia dla każdego agenta)

```markdown
### Kontrakt przebiegu – raport maszynowy po KAŻDYM przebiegu, także CISZA (od 9.11.2026, etap 1 niezawodności; spec: `pm/specyfikacje/2026-11-08-kontrakt-przebiegu.md`)

Na końcu przebiegu (przed commitem; w CISZY zamiast „nic nie zapisuję”) dopisz jedną linię JSON do `przebiegi/<agent>/<RRRR-MM-DD>.jsonl` poleceniem
`python3 -I pm/narzedzia/przebieg-raport.py dopisz <plik.json>` (odrzuci linię niezgodną z kontraktem – popraw i powtórz). Pola: `agent: "<agent>"`, `zadanie`
(id zadania albo `czat`), `konto` (A/B), `okienko` (`scripts/przebieg.sh okienko <agent>`), `start`, `koniec` (ISO 8601 ze strefą, `date -Iseconds`), `tryb`
(CISZA/ZDARZENIE/PEŁNY/… jak w pkt 2), `zrodla`, `akcje`, `rozbieznosci`, `bledy`, `wynik`, `raport` (zdanie końcowe), `kpi` (treść linii **KPI:**).

**Źródła obowiązkowe** (każde zawsze w `zrodla`, z liczbami z tego przebiegu – nigdy z pamięci ani ze `stan.json`): `zlecenia/<agent>.md`, `decyzje.md`
oraz: <LISTA ŹRÓDEŁ AGENTA Z SEKCJI 4 – nazwa · co liczyć · rejestr>. Dla każdego: `przeczytane` (ile pobrałeś – całą listę, gdy źródło tak każe), `nowe`
(nie ma w rejestrze albo nowe od ostatniego przebiegu – porównanie **po ID**), `obsluzone` (z nowych – załatwione teraz), `w_rejestrze` (wiersze rejestru po
przebiegu), opcjonalnie `otwarte`, `ids_bez_sladu`. Źródła nie dało się przeczytać → `przeczytane: null` + wpis w `bledy` (nigdy `0`).

**Rozbieżność** (`przeczytane ≠ w_rejestrze` tam, gdzie rejestr ma wszystko; `nowe > obsluzone`; przypadki z Twojej listy) = praca **w tym przebiegu** albo wpis
„Pilne” w `zlecenia/ceo.md` w tym przebiegu – zawsze z polem `dzialanie`. **CISZA tylko, gdy wszystkie źródła mają `nowe = 0` i nie ma rozbieżności.**
W CISZY commit samego pliku: `git add przebiegi/<agent>/ && git commit -m "<agent>: przebieg CISZA <data> <GG:MM>"`, potem `git pull --rebase` i push.
Konflikt w `.jsonl` → zachowaj obie linie. Bez danych osobowych (żadnych e-maili, nazwisk), bez sekretów, bez treści maili – tylko ID i liczby.
Brak linii, liczby bez źródła albo `0` zamiast `null` = przebieg nieudany (strażnik floty i PM liczą to jako awarię, nawet gdy sesja „zakończyła się sukcesem”).
```

Dla PM (`pm/agent.md`) CEO wkleja ten sam blok ze źródłami z wiersza **pm** w sekcji 4; PM dodatkowo w każdym przebiegu DZIENNYM czyta `przebiegi/*/` z ostatnich 24 h
(`podsumuj 1`) i wpisuje do raportu dla CEO: agenci bez linii w oknie, `BŁĄD`/`NIEPEŁNY`, rozbieżności bez działania.

## 8. Tygodniowy przegląd niezawodności (piątek, przebieg PEŁNY PM) – `pm/przeglady/RRRR-MM-DD.md`, sekcja „Niezawodność”

Źródła: `przebiegi/*/*.jsonl` (7 dni, `podsumuj 7`), tagi `przebieg/*` na origin, `ceo/straznik-zdarzenia.md` (od wdrożenia strażnika), `zlecenia/ceo.md` wpisy „Pilne”,
dzienniki agentów, `decyzje.md`. Tabela per agent i podsumowanie floty:

| Miernik | Definicja | Cel (analiza CEO, sekcja 4) |
|---|---|---|
| Pokrycie przebiegów | linie w `przebiegi/` ÷ przebiegi oczekiwane z harmonogramu (`koordynacja-odstepy.tsv`, 7 dni; kod 10 = oczekiwany spełniony przez drugie konto) | 100 % |
| Przebiegi bez raportu z liczbami | brak linii w oknie + `NIEPEŁNY` + `BŁĄD` | 0 % |
| Udział CISZY | linie `tryb = CISZA` ÷ wszystkie – za wysoki (> 90 % przy rytmie 3 h) = kandydat do rzadszego rytmu (przegląd cyklicznych) | – |
| Rozbieżności | liczba, per źródło; ile obsłużonych w tym samym przebiegu; ile otwartych > 1 okienko | pominięte pozycje w uzgodnieniach: 0 |
| Incydenty | zdarzenia strażnika + incydenty z dzienników/decyzji: początek, wykrycie, kto wykrył (strażnik / agent / PM / CEO / właściciel), klasa przyczyny A–H z analizy | wykryte przez właściciela: 0 |
| MTTD | mediana (wykrycie − początek) incydentów tygodnia; MTTR – mediana (usunięcie − wykrycie) | MTTD ≤ 30 min |
| PR bez werdyktu > 2 h | z rozbieżności recenzenta/CEO i strażnika (kontrola 2) | 0 |
| Zlecenia po terminie bez odpowiedzi | z backlogu (J po terminie) | 0 |

Wynik przeglądu: (1) tabela wyżej; (2) 3 największe przyczyny tygodnia (klasy A–H) z przykładami po ID; (3) **maks. 5 propozycji** do `zlecenia/ceo.md`
(nowa kontrola strażnika, niezmiennik do testów CI, zmiana rytmu, zmiana instrukcji agenta – co, dlaczego, skutek, ryzyko); (4) linia `**KPI:**` z miernikami
(propozycja nowego KPI organizacji `K9 – przebiegi bez raportu z liczbami (%)` i `K10 – MTTD awarii automatów` do `ceo/kpi/kpi.md`, pomiar z `podsumuj` i strażnika).
Mierniki trafiają na stronę planu w sekcji KPI po dodaniu do `kpi.md`/`pomiar.py` (CEO).

## 9. Wdrożenie (propozycja kolejności dla CEO) i ryzyka

1. 8.11: CEO dodaje `.gitattributes` (`przebiegi/**/*.jsonl merge=union`), wkleja blok z sekcji 7 do 16 × `agent.md` (+ instrukcja zadania `org-sklepy-maile-a`) –
   najpierw **recenzent, aplikacje, recepcja, obsługa** (mają już uzgodnienia z 8.11 – tylko format), potem CEO i architekt, potem reszta.
2. 9.11: pierwszy przebieg każdego agenta z linią; PM w przebiegu 6:45 i 9:45 sprawdza `podsumuj 1` i zgłasza agentów bez linii; strażnik (architekt) czyta
   `przebiegi/` w kontroli 1 zamiast świeżości `stan.json`.
3. 14.11 (piątek): pierwszy przegląd niezawodności (sekcja 8); kalibracja: które rozbieżności są szumem (np. `w_rejestrze` dla źródeł przyrostowych).
- **Koszt:** ok. 1 000 commitów CISZA/tydzień przy 17 zadaniach co 3 h (linia ~1 KB) – mało miejsca, dużo szumu w `git log`; jeśli przeszkadza, alternatywa: strażnik
  czyta pliki lokalnie (ten sam Mac), a CISZA commituje tylko raz na dobę (PM scala) – decyzja CEO po tygodniu.
- **Ryzyko:** agent wpisze liczby „z głowy” – dlatego rejestry po ID i strażnik liczy niezależnie (ASC, PR, skrzynki); rozjazd linii i strażnika = incydent klasy A.
- **Ryzyko:** konflikty `.jsonl` między kontami – `merge=union` + reguła „zachowaj obie linie”.
- **Poza zakresem (etap 2–3):** rejestr zgód z ID (`decyzja` w `akcje` odwołuje się dziś do `decyzje.md` datą i skrótem), GitHub Issues jako kolejka (wtedy `id` zlecenia = numer issue).
