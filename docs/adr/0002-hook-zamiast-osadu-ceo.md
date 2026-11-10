# ADR 0002 · Bramki deterministyczne w hooku zamiast osądu agenta-CEO · status: przyjęty · 2026-11-09

## Kontekst
Szablon v0.1 traktował zgodę agenta-CEO („[Decyzja CEO]”) jako bramkę dla pieniędzy, scaleń i wdrożeń. Project Vend 2 (Anthropic) pokazał,
że agent-nadzorca na tym samym modelu „podziela braki i ślepe punkty” podwładnego i zatwierdzał ulgi 8× częściej, niż odrzucał; literatura
o self-preference bias sędziów mówi to samo. W organizacji źródłowej tempo kusiło do trybu Bypass, a polityki żyły w promptach i decyzjach czatu.
Hook Claude Code może zablokować narzędzie przed wykonaniem i zapisać każdą decyzję.

## Decyzja
Polityki i progi są **w danych** (`uprawnienia.yaml`, `polityki/progi.yaml`, `polityki/*.md`), egzekucja jest **w hooku PreToolUse**
(`.claude/hooks/uprawnienia.py`, fail-closed, `matcher: "*"`, `onFailure: block`): bramka `kwota` (zwroty, wydatki do progu), bramka `pr`
(werdykt recenzenta OK dla head SHA + zielone CI), reguła dwóch (typ `reader`/`researcher` z manifestu nie wysyła, nie płaci, nie wdraża),
zgoda właściciela tylko jako `DECYZJA=D-…` istniejąca w `decyzje/`, kill switch `bezpieczenstwo/HALT`, audyt każdej decyzji z łańcuchem SHA
(≥ 6 miesięcy). Agent CEO decyduje o priorytetach, delegacji i kolejności – **nie o pojedynczych kwotach ani scaleniach**.

## Konsekwencje
- Agenta nie da się „przegadać”: manipulacja w mailu może zmienić jego zamiar, ale nie próg w pliku ani decyzję hooka.
- Hook zna tylko wzorce poleceń i narzędzi – zasada obowiązuje szerzej niż jej egzekucja (zasady A1); nowe narzędzia wysyłki/płatności
  wymagają wzorca w hooku i testu (`test_uprawnienia.py`).
- Każda zmiana uprawnień to decyzja właściciela z ID; luzowanie następuje z historią (przegląd miesięczny – `procesy/50`), nie z zaufaniem.
- Koszt: wolniejszy start (wszystko ostrożne), kilkanaście sekund na przebieg na hook, audyt rośnie (`merge=union`, archiwizacja).
- Recenzent odseparowany od autorów (inny model, świeży kontekst, rubryka) jest częścią tej samej decyzji – jego werdykt to dane dla hooka.

## Źródło
Research „Standardy 2026”: sekcja „Rada–CEO–liderzy” i „Bezpieczeństwo”, rek. 1 (hook fail-closed, audyt, HALT), 2 (bramki pieniężne poza
agentem-CEO), 3 (recenzent odseparowany), konkluzja; `docs/raport/2026-11-09-raport.md` rozdz. 0 (lekcje Project Vend), 3.2, 4.2 pkt 4 i 7.
