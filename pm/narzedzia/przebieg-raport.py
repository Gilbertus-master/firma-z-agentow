#!/usr/bin/env python3
"""Kontrakt przebiegu (pm/specyfikacje/kontrakt-przebiegu.md) – dopisanie, sprawdzenie i podsumowanie raportów.

  python3 -I pm/narzedzia/przebieg-raport.py dopisz <plik.json | ->      # dopisuje 1 linię do przebiegi/<agent>/<data>.jsonl (data i agent z JSON)
  python3 -I pm/narzedzia/przebieg-raport.py sprawdz <plik.jsonl> [...]   # sprawdza każdą linię; kod 1 przy błędzie
  python3 -I pm/narzedzia/przebieg-raport.py podsumuj [dni=7]              # tabela: agent · przebiegi · tryby · wynik · rozbieżności · błędy · koszt USD
                                                                           # (koszt z pola koszt_usd linii kontraktu + przebiegi/<agent>/koszty-*.jsonl wrappera headless)

Bez tokenów modelu, bez sieci. Niczego nie commituje. Zwraca kod 0 (OK) / 1 (błąd walidacji) / 2 (złe wywołanie)."""
import json, pathlib, re, sys, datetime, collections

REPO = pathlib.Path(__file__).resolve().parents[2]


def _agenci():
    """Agenci z koordynacja-odstepy.tsv (źródło prawdy harmonogramu) – nie lista na sztywno."""
    w = set()
    try:
        for l in (REPO / "koordynacja-odstepy.tsv").read_text(encoding="utf-8").splitlines():
            if l.strip() and not l.startswith("#"):
                w.add(l.split("\t")[0].strip())
    except OSError:
        pass
    return w | {"limit"}


AGENCI = _agenci()
TRYBY = {"CISZA", "ZDARZENIE", "DZIENNY", "TYGODNIOWY", "PEŁNY", "PRACA", "WYDANIE", "CZAT", "DYŻUR", "BŁĄD"}
WYNIKI = {"OK", "ROZBIEŻNOŚĆ", "NIEPEŁNY", "BŁĄD"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?[+-]\d{2}:\d{2}$")
WYMAGANE = ("wersja", "agent", "konto", "start", "koniec", "tryb", "zrodla", "akcje", "rozbieznosci", "bledy", "wynik")
LICZBY = ("przeczytane", "nowe", "obsluzone", "w_rejestrze")


def bledy_linii(d):
    b = []
    if not isinstance(d, dict):
        return ["linia nie jest obiektem JSON"]
    for k in WYMAGANE:
        if k not in d:
            b.append(f"brak pola `{k}`")
    if b:
        return b
    if d["agent"] not in AGENCI: b.append(f"nieznany agent `{d['agent']}`")
    if not re.fullmatch(r"[A-Z]", str(d["konto"])): b.append("konto musi być jedną wielką literą (org.yaml → runtime.konta)")
    if "koszt_usd" in d and d["koszt_usd"] is not None and not isinstance(d["koszt_usd"], (int, float)): b.append("`koszt_usd` musi być liczbą albo null")
    if int(d.get("wersja") or 1) >= 2:  # kontrakt v2 (standard 2026): wersja instrukcji i zewnętrzny dowód wyniku
        if not re.fullmatch(r"[0-9a-f]{7,40}", str(d.get("prompt_version") or "")): b.append("v2: `prompt_version` = hash commitu instrukcji agenta (git log -1 --format=%h -- <agent>/agent.md role/)")
        if d["tryb"] != "CISZA" and d["wynik"] == "OK" and not str(d.get("outcome_evidence") or "").strip(): b.append("v2: wynik OK wymaga `outcome_evidence` (URL PR/commitu/pliku – dowód spoza raportu)")
        for k in ("retries", "tool_calls"):
            if k in d and d[k] is not None and not isinstance(d[k], int): b.append(f"v2: `{k}` musi być liczbą całkowitą")
        if "escalation" in d and d["escalation"] not in (None, "operator", "wlasciciel", "ceo", "brak"): b.append("v2: `escalation` ∈ operator|wlasciciel|ceo|brak|null")
        if "next_action" in d and d["next_action"] is not None and not isinstance(d["next_action"], str): b.append("v2: `next_action` tekst")
    if "model" in d and not isinstance(d["model"], str): b.append("`model` musi być tekstem")
    for k in ("start", "koniec"):
        if not ISO.match(str(d[k])): b.append(f"`{k}` nie jest datą ISO 8601 ze strefą (np. 2026-11-08T13:04:00+01:00)")
    if d["tryb"] not in TRYBY: b.append(f"tryb `{d['tryb']}` spoza listy {sorted(TRYBY)}")
    if d["wynik"] not in WYNIKI: b.append(f"wynik `{d['wynik']}` spoza listy {sorted(WYNIKI)}")
    if not isinstance(d["zrodla"], list) or (d["tryb"] != "BŁĄD" and not d["zrodla"]):
        b.append("`zrodla` musi być niepustą listą (także w CISZY)")
    for z in d["zrodla"] if isinstance(d["zrodla"], list) else []:
        if not isinstance(z, dict) or not z.get("nazwa"):
            b.append("źródło bez `nazwa`"); continue
        for k in LICZBY:
            if k not in z: b.append(f"źródło `{z['nazwa']}`: brak `{k}`")
            elif z[k] is not None and not isinstance(z[k], int): b.append(f"źródło `{z['nazwa']}`: `{k}` musi być liczbą całkowitą albo null")
        if z.get("przeczytane") is None and not any(e.get("zrodlo") == z["nazwa"] for e in d["bledy"] if isinstance(e, dict)):
            b.append(f"źródło `{z['nazwa']}`: `przeczytane` = null wymaga wpisu w `bledy` z tym samym `zrodlo`")
        if isinstance(z.get("nowe"), int) and isinstance(z.get("obsluzone"), int) and z["obsluzone"] > z["nowe"]:
            b.append(f"źródło `{z['nazwa']}`: obsłużone > nowe")
    for a in d["akcje"] if isinstance(d["akcje"], list) else [None]:
        if not isinstance(a, dict) or not a.get("typ") or not a.get("id"): b.append("akcja bez `typ`/`id`")
    for r in d["rozbieznosci"] if isinstance(d["rozbieznosci"], list) else [None]:
        if not isinstance(r, dict) or not r.get("zrodlo") or not r.get("opis") or not r.get("dzialanie"): b.append("rozbieżność bez `zrodlo`/`opis`/`dzialanie`")
    for e in d["bledy"] if isinstance(d["bledy"], list) else [None]:
        if not isinstance(e, dict) or not e.get("gdzie") or not e.get("komunikat"): b.append("błąd bez `gdzie`/`komunikat`")
    tekst = json.dumps(d, ensure_ascii=False)
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", tekst): b.append("w raporcie jest adres e-mail – dane osobowe zabronione")
    if re.search(r"(sk_live|re_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}\.|ghp_[A-Za-z0-9]{20,}|whsec_)", tekst): b.append("w raporcie jest coś, co wygląda na sekret")
    if len(tekst) > 8000: b.append(f"linia ma {len(tekst)} znaków (limit 8000) – skróć listy ID/opisów")
    # spójność wyniku z treścią
    oczek = "BŁĄD" if any(e.get("skutek") == "przebieg przerwany" for e in d["bledy"] if isinstance(e, dict)) else \
        "NIEPEŁNY" if any(isinstance(z, dict) and z.get("przeczytane") is None for z in d["zrodla"]) else \
        "ROZBIEŻNOŚĆ" if d["rozbieznosci"] else "OK"
    if d["wynik"] != oczek: b.append(f"`wynik` = {d['wynik']}, a z treści wynika {oczek}")
    return b


def dopisz(zrodlo):
    d = json.loads(sys.stdin.read() if zrodlo == "-" else pathlib.Path(zrodlo).read_text(encoding="utf-8"))
    d.setdefault("wersja", 1)
    d.setdefault("koniec", datetime.datetime.now().astimezone().replace(microsecond=0).isoformat())
    b = bledy_linii(d)
    if b:
        print("RAPORT ODRZUCONY:\n- " + "\n- ".join(b)); return 1
    data = str(d["start"])[:10]
    p = REPO / "przebiegi" / d["agent"] / f"{data}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"dopisano: {p.relative_to(REPO)} (wynik {d['wynik']}, tryb {d['tryb']})"); return 0


def sprawdz(pliki):
    kod = 0
    for pl in pliki:
        for nr, linia in enumerate(pathlib.Path(pl).read_text(encoding="utf-8").splitlines(), 1):
            if not linia.strip(): continue
            try: b = bledy_linii(json.loads(linia))
            except json.JSONDecodeError as e: b = [f"nie JSON: {e}"]
            if b: kod = 1; print(f"{pl}:{nr}: " + "; ".join(b))
    print("OK" if kod == 0 else "BŁĘDY"); return kod


def podsumuj(dni):
    od = datetime.date.today() - datetime.timedelta(days=dni - 1)
    w = collections.defaultdict(lambda: {"n": 0, "tryby": collections.Counter(), "wyniki": collections.Counter(), "rozb": 0, "bledy": 0, "ostatni": "", "koszt": 0.0, "koszt_n": 0,
                                         "ok": 0, "ok_bez_dowodu": 0, "czasy": []})
    razem = 0.0
    for p in sorted((REPO / "przebiegi").glob("*/*.jsonl")) if (REPO / "przebiegi").exists() else []:
        koszty = p.stem.startswith("koszty-")
        if (p.stem[len("koszty-"):] if koszty else p.stem) < od.isoformat(): continue
        for linia in p.read_text(encoding="utf-8").splitlines():
            if not linia.strip(): continue
            d = json.loads(linia); s = w[d.get("agent", p.parent.name)]
            if koszty:
                if isinstance(d.get("koszt_usd"), (int, float)): s["koszt"] += d["koszt_usd"]; s["koszt_n"] += 1; razem += d["koszt_usd"]
                continue
            s["n"] += 1; s["tryby"][d.get("tryb")] += 1; s["wyniki"][d.get("wynik")] += 1
            if d.get("wynik") == "OK" and d.get("tryb") != "CISZA":
                s["ok"] += 1
                if not str(d.get("outcome_evidence") or "").strip(): s["ok_bez_dowodu"] += 1
            try:
                a, b = datetime.datetime.fromisoformat(str(d["start"])), datetime.datetime.fromisoformat(str(d["koniec"]))
                s["czasy"].append((b - a).total_seconds())
            except (KeyError, ValueError, TypeError): pass
            s["rozb"] += len(d.get("rozbieznosci") or []); s["bledy"] += len(d.get("bledy") or []); s["ostatni"] = max(s["ostatni"], str(d.get("koniec", "")))
            if isinstance(d.get("koszt_usd"), (int, float)): s["koszt"] += d["koszt_usd"]; s["koszt_n"] += 1; razem += d["koszt_usd"]
    print(f"| Agent | Przebiegi ({dni} dni) | Tryby | Wyniki | Rozbieżności | Błędy | Koszt USD (n) | F7 koszt/OK | F8 OK bez dowodu | F9 p95 s | Ostatni |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for a in sorted(AGENCI):
        s = w.get(a)
        if not s: print(f"| {a} | 0 | – | – | – | – | – | – | – | – | **brak raportów** |"); continue
        f = lambda c: ", ".join(f"{k} {v}" for k, v in sorted(c.items()))
        koszt = f"{s['koszt']:.2f} ({s['koszt_n']})" if s["koszt_n"] else "–"
        f7 = f"{s['koszt'] / s['ok']:.2f}" if s["ok"] and s["koszt_n"] else "–"
        f8 = f"{100 * s['ok_bez_dowodu'] / s['ok']:.0f} % ({s['ok_bez_dowodu']}/{s['ok']})" if s["ok"] else "–"
        cz = sorted(s["czasy"]); f9 = f"{cz[max(0, int(round(0.95 * len(cz))) - 1)]:.0f}" if cz else "–"
        print(f"| {a} | {s['n']} | {f(s['tryby'])} | {f(s['wyniki'])} | {s['rozb']} | {s['bledy']} | {koszt} | {f7} | {f8} | {f9} | {s['ostatni'][:16]} |")
    print(f"\nKoszt floty razem ({dni} dni): {razem:.2f} USD – szacunek kliencki; źródło billingowe: telemetria (toolbelt/obserwowalnosc.md).")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "dopisz": sys.exit(dopisz(a[1]))
    if len(a) >= 2 and a[0] == "sprawdz": sys.exit(sprawdz(a[1:]))
    if a and a[0] == "podsumuj": sys.exit(podsumuj(int(a[1]) if len(a) > 1 else 7))
    print(__doc__); sys.exit(2)
