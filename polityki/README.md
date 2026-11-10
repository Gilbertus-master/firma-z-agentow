# Polityki biznesowe

Twarde reguły, których agent **nie negocjuje** (zasady.md pkt 11). Lekcja z Project Vend (Anthropic): agent
rozmawiający z ludźmi daje się namówić na rabaty, zwroty i wyjątki, jeśli reguły są tylko w prompcie.

Każda polityka ma wersję, datę i decyzję `D-…`, która ją zatwierdziła. Zmiana = decyzja według `uprawnienia.yaml`
(ceny → właściciel).

| Plik | Co | Kto stosuje |
|---|---|---|
| `cennik.md` | ceny, plany, waluty, okresy | sprzedaż, obsługa, marketing |
| `zwroty.md` | kiedy zwrot, ile, do jakiego progu CEO, powyżej – właściciel | obsługa (wniosek), CEO (decyzja) |
| `rabaty.md` | jakie rabaty istnieją; poza listą – nie ma | sprzedaż |
| `komunikacja.md` | ton, podpis, stopka AI, czego nie obiecujemy | wszyscy piszący na zewnątrz |
| `outbound.md`, `blacklista.tsv` | kontakt wychodzący: zgody (art. 398 PKE), kanały, limity | sprzedaż, marketing |
| `progi.yaml` | progi liczbowe czytane przez hook (zwroty, wydatki, outbound) | hook uprawnień |

Szablon polityki:
```
# <nazwa> · wersja 0.1 · RRRR-MM-DD · zatwierdzone: D-…
## Reguły
1. …
## Wyjątki
Brak. Prośba o wyjątek → zlecenie do CEO z rekomendacją; klient dostaje odpowiedź „sprawdzimy i odpowiemy do <termin>”.
```
