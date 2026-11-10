#!/usr/bin/env python3
"""Kontrola ewaluacji (CI i agent bezpieczeństwa): każdy UTWORZONY agent z kontaktem zewnętrznym ma komplet scenariuszy
w ewaluacje/<agent>/ (co najmniej te z ewaluacje/_startowe/), a każdy scenariusz ma sekcje Wejście / Oczekiwane / Ocena.

  python3 -I ewaluacje/sprawdz.py          # kod 1 przy brakach
Same scenariusze uruchamia agent bezpieczeństwa (sesja z modelem) po każdej zmianie agent.md/roli/polityki; tu tylko
sprawdzamy, że istnieją i są kompletne – deterministycznie, bez LLM.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KONTAKT_ZEWNETRZNY = ("obsluga", "recepcja", "sprzedaz", "marketing", "inwestorzy", "aplikacje", "ochrona-danych")
SEKCJE = ("Wejście:", "Oczekiwane:", "Ocena:")


def main():
    startowe = sorted(p.name for p in (REPO / "ewaluacje" / "_startowe").glob("*.md"))
    bledy = []
    for agent in KONTAKT_ZEWNETRZNY:
        if not (REPO / agent / "agent.md").exists():
            continue  # agent jeszcze nie utworzony
        kat = REPO / "ewaluacje" / agent
        pliki = {p.name for p in kat.glob("*.md")} if kat.is_dir() else set()
        for s in startowe:
            if s not in pliki:
                bledy.append("%s: brak scenariusza %s (skopiuj z ewaluacje/_startowe/)" % (agent, s))
        for p in sorted(kat.glob("*.md")) if kat.is_dir() else []:
            t = p.read_text(encoding="utf-8")
            for sek in SEKCJE:
                if not re.search(r"^\**%s" % re.escape(sek), t, re.M):
                    bledy.append("%s/%s: brak sekcji „%s”" % (agent, p.name, sek.rstrip(":")))
            if "zakazane_narzedzia:" not in t.split("---")[1] if t.startswith("---") and t.count("---") >= 2 else True:
                bledy.append("%s/%s: brak asercji `zakazane_narzedzia` we frontmatterze (ewaluacje/uruchom.py)" % (agent, p.name))
    for b in bledy:
        print("BŁĄD:", b)
    if not bledy:
        print("ewaluacje: OK (%d scenariuszy startowych, agenci sprawdzeni: %s)" % (
            len(startowe), ", ".join(a for a in KONTAKT_ZEWNETRZNY if (REPO / a / "agent.md").exists()) or "żaden"))
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
