#!/usr/bin/env python3
"""Bramka skrótów zasad bezpieczeństwa – zasady nie mogą zniknąć ani zmienić się po cichu.

  python3 -I scripts/zasady_skroty.py sprawdz                         # kod 0 = zgodnie, 1 = rozbieżność (test CI)
  python3 -I scripts/zasady_skroty.py aktualizuj --decyzja D-RRRRMMDD-NN
                                                                       # świadoma zmiana zasad: nowe skróty z numerem decyzji
  python3 -I scripts/zasady_skroty.py aktualizuj --decyzja D-… --usun <klucz>
                                                                       # jawne usunięcie chronionego źródła (np. bloku)

Chronione źródła (klucze):
  zasady.md:A               sekcja A `zasady.md` (od „## A.” do następnego nagłówka „## ”),
  blok:<nazwa>              każdy plik `flota/szablony/bloki/zasady*.md` (skrót zasad wstawiany do promptów).
Skróty SHA-256 są w `bezpieczenstwo/zasady-skroty.json` razem z numerem decyzji, która je ustaliła. `sprawdz` sprawdza też:
  - każda treść zadania `flota/szablony/tresc/*.md` wstawia blok `{{blok:zasady-bezpieczenstwa}}` albo ma w pliku skrótów
    wiersz wyjątku z powodem (`wyjatki_tresci`);
  - każdy wygenerowany prompt (`flota/zadania.yaml → prompt`) z treści bez wyjątku zawiera dosłowny tekst bloku;
  - każda decyzja zapisana przy skrócie istnieje w `decyzje/<ID>.md` (albo `start` – skróty wydane z szablonem).
Zmiana zasad = ten sam PR zmienia źródło i plik skrótów poleceniem `aktualizuj` z numerem istniejącej decyzji właściciela.
Bez PyYAML (działa z `python3 -I`): manifest floty czytany prostym parserem pól `tresc:` i `prompt:`.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PLIK = "bezpieczenstwo/zasady-skroty.json"
BLOK = "zasady-bezpieczenstwa"
WSTAWKA = "{{blok:%s}}" % BLOK
RE_DECYZJA = re.compile(r"D-\d{8}-\d{2}")


def skrot(tekst):
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()


def sekcja_a(tekst):
    """Sekcja A zasad: od linii „## A.” do następnego nagłówka poziomu 2 (bez niego); None, gdy brak."""
    out, w = [], False
    for linia in tekst.splitlines():
        if linia.startswith("## A."):
            w = True
        elif w and linia.startswith("## "):
            break
        if w:
            out.append(linia)
    return "\n".join(out).rstrip() + "\n" if out else None


def zrodla(repo):
    """{klucz: tekst albo None (źródło zniknęło)} – wszystkie chronione źródła, które dziś istnieją lub powinny istnieć."""
    out = {}
    z = repo / "zasady.md"
    out["zasady.md:A"] = sekcja_a(z.read_text(encoding="utf-8")) if z.exists() else None
    for p in sorted((repo / "flota/szablony/bloki").glob("zasady*.md")):
        out["blok:" + p.stem] = p.read_text(encoding="utf-8")
    return out


def wczytaj(repo):
    p = repo / PLIK
    if not p.exists():
        return {"skroty": {}, "usuniete": {}, "wyjatki_tresci": {}}
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("skroty", "usuniete", "wyjatki_tresci"):
        d.setdefault(k, {})
    return d


def zapisz(repo, d):
    (repo / PLIK).write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def zadania(repo):
    """[(tresc, prompt)] z flota/zadania.yaml – prosty parser listy `- agent:` z polami `tresc:` i `prompt:`."""
    p = repo / "flota/zadania.yaml"
    if not p.exists():
        return []
    out, biez = [], None
    for linia in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^- agent:", linia):
            if biez:
                out.append(biez)
            biez = {}
        elif biez is not None:
            m = re.match(r"^\s+(tresc|prompt):\s*['\"]?([^'\"#\s]+)", linia)
            if m:
                biez[m.group(1)] = m.group(2)
    if biez:
        out.append(biez)
    return [(z.get("tresc"), z.get("prompt")) for z in out]


def decyzja_istnieje(repo, d):
    return d == "start" or (bool(RE_DECYZJA.fullmatch(d or "")) and (repo / "decyzje" / f"{d}.md").exists())


def sprawdz(repo=REPO):
    """Lista błędów (pusta = zgodnie)."""
    bledy = []
    d = wczytaj(repo)
    if not (repo / PLIK).exists():
        return [f"brak {PLIK} – zasady bez skrótów (python3 -I scripts/zasady_skroty.py aktualizuj --decyzja D-…)"]
    teraz = zrodla(repo)
    for klucz, wpis in sorted(d["skroty"].items()):
        tekst = teraz.get(klucz)
        if tekst is None:
            bledy.append(f"{klucz}: źródło zniknęło – usunięcie tylko jawnie: aktualizuj --decyzja D-… --usun {klucz}")
        elif skrot(tekst) != wpis.get("sha256"):
            bledy.append(f"{klucz}: treść zasad zmieniona bez decyzji (skrót różny od {PLIK}); świadoma zmiana: "
                         f"aktualizuj --decyzja D-… w tym samym PR")
        if not decyzja_istnieje(repo, str(wpis.get("decyzja") or "")):
            bledy.append(f"{klucz}: decyzja „{wpis.get('decyzja')}” nie istnieje w decyzje/")
    for klucz in sorted(set(teraz) - set(d["skroty"])):
        if teraz[klucz] is not None:
            bledy.append(f"{klucz}: nowe źródło zasad bez skrótu – aktualizuj --decyzja D-…")
    for klucz, dec in sorted(d["usuniete"].items()):
        if klucz in teraz and teraz[klucz] is not None and klucz not in d["skroty"]:
            bledy.append(f"{klucz}: oznaczone jako usunięte, a źródło istnieje")
        if not decyzja_istnieje(repo, str(dec or "")):
            bledy.append(f"{klucz}: usunięcie bez istniejącej decyzji („{dec}”)")

    tresci = sorted((repo / "flota/szablony/tresc").glob("*.md"))
    nazwy = {p.name for p in tresci}
    for nazwa, powod in sorted(d["wyjatki_tresci"].items()):
        if nazwa not in nazwy:
            bledy.append(f"wyjątek dla nieistniejącej treści {nazwa} – usuń wiersz")
        if len(str(powod or "").strip()) < 20:
            bledy.append(f"wyjątek {nazwa}: brak powodu (min. jedno zdanie)")
    for p in tresci:
        if WSTAWKA not in p.read_text(encoding="utf-8") and p.name not in d["wyjatki_tresci"]:
            bledy.append(f"flota/szablony/tresc/{p.name}: brak {WSTAWKA} i brak wyjątku z powodem w {PLIK}")

    blok = teraz.get("blok:" + BLOK)
    for tresc, prompt in zadania(repo):
        if not tresc or not prompt or pathlib.Path(tresc).name in d["wyjatki_tresci"]:
            continue
        pp = repo / prompt
        if blok is None or not pp.exists() or blok not in pp.read_text(encoding="utf-8"):
            bledy.append(f"{prompt}: prompt bez pełnego tekstu bloku zasad (python3 flota/generuj.py)")
    return bledy


def aktualizuj(repo, decyzja, usun=None):
    if not RE_DECYZJA.fullmatch(decyzja or ""):
        raise SystemExit(f"BŁĄD: numer decyzji w postaci D-RRRRMMDD-NN, nie „{decyzja}”")
    if not (repo / "decyzje" / f"{decyzja}.md").exists():
        raise SystemExit(f"BŁĄD: brak pliku decyzje/{decyzja}.md – zmiana zasad wymaga zapisanej decyzji właściciela")
    d = wczytaj(repo)
    teraz = zrodla(repo)
    if usun:
        if usun not in d["skroty"]:
            raise SystemExit(f"BŁĄD: klucza {usun} nie ma w {PLIK}")
        if teraz.get(usun) is not None:
            raise SystemExit(f"BŁĄD: źródło {usun} nadal istnieje – najpierw je usuń, potem --usun")
        del d["skroty"][usun]
        d["usuniete"][usun] = decyzja
        zapisz(repo, d)
        print(f"USUNIĘTO {usun} (decyzja {decyzja})")
        return 0
    zmiany = 0
    for klucz, tekst in teraz.items():
        if tekst is None:
            if klucz in d["skroty"]:
                print(f"POMIŃ {klucz}: źródło zniknęło – użyj --usun {klucz}")
            continue
        s = skrot(tekst)
        if (d["skroty"].get(klucz) or {}).get("sha256") != s:
            d["skroty"][klucz] = {"sha256": s, "decyzja": decyzja}
            d["usuniete"].pop(klucz, None)
            zmiany += 1
            print(f"ZAPISANO {klucz} (decyzja {decyzja})")
    zapisz(repo, d)
    if not zmiany:
        print("BEZ ZMIAN – skróty zgodne")
    return 0


def main(argv=None, repo=REPO):
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = a.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sprawdz")
    u = sub.add_parser("aktualizuj")
    u.add_argument("--decyzja", required=True)
    u.add_argument("--usun")
    o = a.parse_args(argv)
    if o.cmd == "sprawdz":
        bledy = sprawdz(repo)
        for b in bledy:
            print("BŁĄD:", b)
        print(f"zasady: {len(wczytaj(repo)['skroty'])} skrótów, błędów: {len(bledy)}")
        return 1 if bledy else 0
    return aktualizuj(repo, o.decyzja, o.usun)


if __name__ == "__main__":
    sys.exit(main())
