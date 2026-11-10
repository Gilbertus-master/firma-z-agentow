#!/usr/bin/env python3
"""Strażnik floty organizacji agentycznej – kontrole niezawodności co 15 min (GitHub Actions albo launchd), alerty przy
nowej rozbieżności. Konfiguracja z org.yaml repo (prefiks zadań, konta, strefa, repo produktu, aktywne kontrole).

  python3 moduly/straznik/straznik.py            # przebieg: kontrole, ceo/straznik.json, zdarzenia, alerty, commit
  python3 moduly/straznik/straznik.py --sucho    # prawdziwe źródła, wynik JSON na stdout, bez zapisów i alertów
  python3 moduly/straznik/straznik.py --dane moduly/straznik/testdane --sucho   # dane przykładowe

Repo robocze: STRAZNIK_REPO (domyślnie ~/projekty/organizacja-straznik – własny klon, nie wspólny checkout; w CI: checkout).
Zadania: STRAZNIK_ZADANIA (domyślnie ~/.claude/scheduled-tasks; brak katalogu przy runtime innym niż desktop = kontrola
konfiguracji pominięta). Sekrety: STRAZNIK_RESEND_KEY / STRAZNIK_SEKRET_<USLUGA> albo pęk kluczy. Opis: README.md obok.
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import timedelta
from pathlib import Path

sys.dont_write_bytecode = True
TU = Path(__file__).resolve().parent
sys.path.insert(0, str(TU))

import alerty as A  # noqa: E402
import kontrole as K  # noqa: E402
import zrodla as Z  # noqa: E402

DOMYSLNE_REPO = "~/projekty/organizacja-straznik"
DOMYSLNE_ZADANIA = "~/.claude/scheduled-tasks"
PLIK_STANU = "ceo/straznik.json"
PLIK_ZDARZEN = "ceo/straznik-zdarzenia.md"
PLIK_CEO = "zlecenia/ceo.md"
COMMIT_ZDARZEN_CO_MIN = 60
GALAZ_DOMYSLNA = "main"


def galaz_glowna(repo):
    """Nazwa gałęzi głównej origin (refs/remotes/origin/HEAD → main/master…); bez wskazania – main."""
    rc, out = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out.startswith("origin/"):
        return out.split("/", 1)[1].strip()
    rc, out = git(repo, "rev-parse", "-q", "--verify", "refs/remotes/origin/master")
    if rc == 0 and git(repo, "rev-parse", "-q", "--verify", "refs/remotes/origin/main")[0] != 0:
        return "master"
    return GALAZ_DOMYSLNA
NAGLOWEK_ZDARZEN = (
    "# Strażnik floty – zdarzenia\n\n"
    "Dopisuje `moduly/straznik/straznik.py` (co 15 min) tylko przy zmianie stanu kontroli (OK ↔ ROZBIEŻNOŚĆ, zmiana ID)\n"
    "i przy alertach. Pełny ostatni stan: `ceo/straznik.json` w klonie strażnika (poza repo). Najnowsze na dole.\n\n"
)


def git(repo, *args, timeout=90):
    try:
        p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, type(e).__name__


def zabezpiecz_przed_pull(repo):
    """Niezacommitowane pliki strażnika (zdarzenia, zlecenia/ceo.md) -> lokalny commit przed pull.
    Brudny plik w drzewie blokuje pull, gdy ktoś inny zmienił go w origin („Scalenie nadpisałoby zmiany”).
    Zdarzenia scala potem `merge=union` z .gitattributes (obie wersje linii). -> opis, gdy commit się udał, albo None."""
    sciezki = [s for s in (PLIK_ZDARZEN, PLIK_CEO)
               if git(repo, "status", "--porcelain", "--", s)[1].strip()]
    if not sciezki:
        return None
    if git(repo, "add", "--", *sciezki)[0] or git(repo, "commit", "-q", "-m", "straznik: zdarzenia przed pull", "--", *sciezki)[0]:
        return None
    return "commit przed pull (%s)" % ", ".join(sciezki)


def aktualizuj_klon(repo):
    """git pull --no-rebase w klonie strażnika. -> ("ok" | "zrodlo" | "uwaga", opis).
    Pull odmówił przy brudnych plikach strażnika -> lokalny commit (zabezpiecz_przed_pull) i druga próba; po udanym pull
    – push lokalnych commitów. Commit zdarzeń co godzinę zostaje, gdy pull przechodzi.
    Konflikt / rozjechana historia: `git merge --abort` (tylko gdy merge trwa), `git fetch`; gdy fetch działa, a pull nie –
    klon wymaga uwagi (kontrole liczone na migawce origin/main, bez commitów w klonie). Bez stash, reset i force."""
    rc, out = git(repo, "pull", "--no-rebase", "-q", timeout=30)
    if rc and git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD")[0] != 0 and zabezpiecz_przed_pull(repo):
        rc, out = git(repo, "pull", "--no-rebase", "-q", timeout=30)  # druga próba po commicie własnych plików
    if rc == 0:
        if git(repo, "rev-list", "--count", "@{u}..HEAD")[1].strip() not in ("", "0"):
            git(repo, "push", "-q", "origin", "HEAD", timeout=30)
        return "ok", ""
    powod = "git pull nieudany"
    if git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0:
        git(repo, "merge", "--abort")
        powod = "konflikt przy git pull (merge przerwany: git merge --abort)"
    rc2, out2 = git(repo, "fetch", "-q", "origin", timeout=30)
    if rc2:
        return "zrodlo", "git pull i fetch nieudane (sieć?): " + out2[:200]
    return "uwaga", "%s: %s" % (powod, out[:200])


def migawka_origin(repo, cel, ref=None):
    ref = ref or "origin/" + galaz_glowna(repo)
    """Kopia drzewa origin/main do katalogu tymczasowego (git archive – tylko odczyt, klon bez zmian)."""
    p = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref], capture_output=True, timeout=60)
    if p.returncode:
        raise RuntimeError("git archive %s: %s" % (ref, p.stderr.decode(errors="replace")[:200]))
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as t:
        if hasattr(tarfile, "data_filter"):
            t.extractall(cel, filter="data")
        else:  # Python 3.9 (/usr/bin/python3) – archiwum z własnego repo
            t.extractall(cel)
    return cel


def wynik_klonu(stan, opis, galaz="origin/" + GALAZ_DOMYSLNA):
    if stan == "ok":
        return K.wynik(K.OK, {"klon_wymaga_uwagi": 0}, [], "klon strażnika aktualny")
    if stan == "zrodlo":
        return K.wynik(K.BLAD, {}, [], "źródło niedostępne: " + opis, [], ["git:pull"])
    return K.wynik(K.ROZ, {"klon_wymaga_uwagi": 1}, ["klon:wymaga-uwagi"],
                   "klon strażnika wymaga uwagi – %s. Kontrole liczone na migawce %s (tylko odczyt); bez commitów i wpisów "
                   "w zlecenia/ceo.md do naprawy (moduly/straznik/README.md, „Klon wymaga uwagi”)." % (opis, galaz))


def commituj(repo, sciezki, wiadomosc):
    """Commit tylko podanych ścieżek + push (przy błędzie: pull --no-rebase i jedna ponowna próba). Bez stash/reset/force."""
    rc, out = git(repo, "add", "--", *sciezki)
    if rc:
        return "git add nieudany: " + out[:200]
    if git(repo, "diff", "--cached", "--quiet", "--", *sciezki)[0] == 0:
        return "bez zmian do commita"
    rc, out = git(repo, "commit", "-q", "-m", wiadomosc, "--", *sciezki)
    if rc:
        return "commit nieudany: " + out[:200]
    if git(repo, "push", "-q", "origin", "HEAD")[0] == 0:
        return "commit i push"
    rc, out = git(repo, "pull", "--no-rebase", "-q")
    if rc:
        git(repo, "merge", "--abort")
        return "commit lokalny; push i pull nieudane: " + out[:200]
    rc, out = git(repo, "push", "-q", "origin", "HEAD")
    return "commit i push (po pull)" if rc == 0 else "commit lokalny; push nieudany: " + out[:200]


def wpisy_ceo_obok(repo, wpisy, wiadomosc):
    """Klon zablokowany: wpisy do zlecenia/ceo.md przez tymczasowy worktree z origin/main (klon bez zmian).
    wpisy: [(wpis, klucz)]. -> (liczba wstawionych, opis). Bez stash, reset i force; push zwykły."""
    tmp = tempfile.mkdtemp(prefix="straznik-wpis-")
    wt = Path(tmp) / "wt"
    try:
        galaz = galaz_glowna(repo)
        rc, out = git(repo, "worktree", "add", "-q", "--detach", str(wt), "origin/" + galaz)
        if rc:
            return 0, "worktree nieudany: " + out[:200]
        n = sum(1 for wpis, k in wpisy if A.wstaw_wpis_ceo(wt / PLIK_CEO, wpis, k))
        if not n:
            return 0, "wpis w zlecenia/ceo.md już otwarty"
        if git(wt, "commit", "-q", "-m", wiadomosc, "--", PLIK_CEO)[0]:
            return 0, "commit obok klonu nieudany"
        rc, out = git(wt, "push", "-q", "origin", "HEAD:" + galaz, timeout=30)
        if rc:
            return 0, "push obok klonu nieudany: " + out[:200]
        return n, "wpis w zlecenia/ceo.md (obok zablokowanego klonu)"
    finally:
        git(repo, "worktree", "remove", "--force", str(wt))
        shutil.rmtree(tmp, ignore_errors=True)
        git(repo, "worktree", "prune")


def wczytaj_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def argumenty(argv):
    ap = argparse.ArgumentParser(description="Strażnik floty")
    ap.add_argument("--sucho", action="store_true", help="tylko kontrole i JSON na stdout – bez zapisów, maili, powiadomień i commitów")
    ap.add_argument("--dane", help="katalog z danymi przykładowymi (zewnetrzne.json, repo/, zadania/, teraz.txt)")
    ap.add_argument("--repo", help="repo robocze (domyślnie STRAZNIK_REPO albo %s; przy --dane: <dane>/repo)" % DOMYSLNE_REPO)
    ap.add_argument("--zadania", help="katalog zadań zaplanowanych (domyślnie STRAZNIK_ZADANIA albo %s)" % DOMYSLNE_ZADANIA)
    ap.add_argument("--teraz", help="czas przebiegu ISO (testy)")
    return ap.parse_args(argv)


def main(argv=None):
    a = argumenty(argv)
    t0 = time.monotonic()
    dane_kat = Path(a.dane).resolve() if a.dane else None
    if a.teraz:
        teraz = K.parsuj_czas(a.teraz)[0]
    elif dane_kat and (dane_kat / "teraz.txt").exists():
        teraz = K.parsuj_czas((dane_kat / "teraz.txt").read_text().strip())[0]
    else:
        teraz = K.utc_teraz()
    if teraz is None:
        print("Zły czas --teraz", file=sys.stderr)
        return 2
    if dane_kat:
        repo = Path(a.repo or dane_kat / "repo").expanduser()
        zadania = Path(a.zadania or dane_kat / "zadania").expanduser()
    else:
        repo = Path(a.repo or os.environ.get("STRAZNIK_REPO") or DOMYSLNE_REPO).expanduser()
        zadania = Path(a.zadania or os.environ.get("STRAZNIK_ZADANIA") or DOMYSLNE_ZADANIA).expanduser()
    efekty = not a.sucho and not dane_kat  # mail, powiadomienie, git – tylko prawdziwy przebieg
    uwagi = []
    klon_stan, repo_danych, migawka = "ok", repo, None
    if efekty:
        klon_stan, opis_klonu = aktualizuj_klon(repo)
        if klon_stan != "ok":
            uwagi.append("klon: " + opis_klonu)
        if klon_stan == "uwaga":
            try:
                migawka = tempfile.mkdtemp(prefix="straznik-migawka-")
                repo_danych = Path(migawka_origin(repo, migawka))
            except Exception as e:  # noqa: BLE001
                uwagi.append("migawka origin/%s nieudana: %s – kontrole na plikach klonu" % (galaz_glowna(repo), str(e)[:200]))
                repo_danych = repo

    try:
        org = Z.konfiguruj(Z.czytaj_org(repo_danych))
        o = org.get("organizacja", {}) if org else {}
        if o.get("domena") and "STRAZNIK_MAIL_OD" not in os.environ:
            A.MAIL_OD = "Strażnik floty <straznik@%s>" % o["domena"]
        operator = (org.get("ludzie", {}) if org else {}).get("operator", {})
        if operator.get("kontakt_firmowy") and "STRAZNIK_MAIL_DO" not in os.environ:
            A.MAIL_DO = operator["kontakt_firmowy"]
        zewn = Z.zewnetrzne_z_pliku(dane_kat) if dane_kat else Z.pobierz_zewnetrzne(repo)
        dane = Z.zloz(repo_danych, zadania, zewn)
        wyniki = K.uruchom_wszystkie(dane, teraz, Z.KONTROLE_AKTYWNE)
        if efekty:
            wyniki["klon"] = wynik_klonu(klon_stan, opis_klonu, "origin/" + galaz_glowna(repo))
        try:
            wyciszenia = A.czytaj_wyciszenia((Path(repo_danych) / PLIK_CEO).read_text(encoding="utf-8"))
        except OSError:
            wyciszenia = []
    finally:
        if migawka:
            shutil.rmtree(migawka, ignore_errors=True)
    czas_s = round(time.monotonic() - t0, 1)

    if a.sucho:
        json.dump({"czas": K.iso(teraz), "czas_przebiegu_s": czas_s, "repo": str(repo), "kontrole": wyniki},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0

    plik_stanu, plik_zdarzen, plik_ceo = repo / PLIK_STANU, repo / PLIK_ZDARZEN, repo / PLIK_CEO
    poprzedni = wczytaj_json(plik_stanu)
    stan_alertow, zdarzenia, do_alertu = A.przetworz(poprzedni, wyniki, teraz, wyciszenia)
    klon_ok = klon_stan != "uwaga"
    czas_txt = teraz.astimezone(K.WAW).strftime("%Y-%m-%d %H:%M")
    mail_stan = poprzedni.get("mail")
    alerty_przebiegu, ceo_zmieniony, wpisy_obok = [], False, []
    for nazwa, w, k in do_alertu:
        skutki = []
        if efekty:
            if A.cisza_nocna(teraz):
                skutki.append("powiadomienie pominięte (cisza nocna 23–7)")
            else:
                skutki.append(A.powiadom("%s: %s" % (K.NAZWY[nazwa], A.krotko(nazwa, w))))
            mail_stan = A.wyslij_mail(A.temat(nazwa, w), A.tresc(nazwa, w, teraz))
            skutki.append(mail_stan)
        else:
            skutki.append("bez maila i powiadomienia (--dane)")
        try:
            if not klon_ok:
                wpisy_obok.append((A.wpis_ceo(nazwa, w, k, teraz), k))
                skutki.append("wpis w zlecenia/ceo.md przez worktree obok klonu")
            elif A.wstaw_wpis_ceo(plik_ceo, A.wpis_ceo(nazwa, w, k, teraz), k):
                ceo_zmieniony = True
                skutki.append("wpis w zlecenia/ceo.md")
            else:
                skutki.append("wpis w zlecenia/ceo.md już otwarty")
        except OSError as e:
            skutki.append("wpis w zlecenia/ceo.md nieudany: %s" % type(e).__name__)
        zdarzenia.append("- %s · alert · %s · %s" % (czas_txt, nazwa, ", ".join(skutki)))
        alerty_przebiegu.append({"kontrola": nazwa, "klucz": A.skrot_klucza(k), "skutki": skutki})

    # Skutki deterministyczne (tylko prawdziwy przebieg): dead-letter dla martwych przebiegów, HALT przy sufitach organizacji.
    pliki_skutkow = []
    if efekty and klon_ok:
        for a in (wyniki.get("martwe") or {}).get("id") or []:
            pdl = repo / "przebiegi" / "dead-letter" / (a + ".md")
            if not pdl.exists():
                pdl.parent.mkdir(parents=True, exist_ok=True)
                pdl.write_text("# Dead-letter: %s\n\n%s – %s przebiegi z rzędu z wynikiem BŁĄD (strażnik). Zadanie wstrzymane: "
                               "`scripts/przebieg.sh` kończy kodem 10, dopóki ten plik istnieje.\n\nPrzegląd operatora/CEO: przyczyna "
                               "(`przebiegi/%s/`, dziennik), poprawka, **usunąć ten plik** = wznowienie. Wpis w `incydenty/`.\n" % (a, czas_txt, 3, a), encoding="utf-8")
                pliki_skutkow.append(str(pdl.relative_to(repo)))
                zdarzenia.append("- %s · dead-letter · %s · plik %s" % (czas_txt, a, pdl.relative_to(repo)))
        if "org:100" in ((wyniki.get("budzety") or {}).get("id") or []):
            ph = repo / "bezpieczenstwo" / "HALT"
            if not ph.exists():
                ph.parent.mkdir(parents=True, exist_ok=True)
                ph.write_text("budżet organizacji ≥ 100 %% w tym miesiącu (strażnik %s) – wznowienie: decyzja właściciela o budżecie, operator usuwa plik\n" % czas_txt, encoding="utf-8")
                pliki_skutkow.append(str(ph.relative_to(repo)))
                zdarzenia.append("- %s · HALT · budżet organizacji 100 %% · plik bezpieczenstwo/HALT" % czas_txt)

    if zdarzenia:
        plik_zdarzen.parent.mkdir(parents=True, exist_ok=True)
        nowy = not plik_zdarzen.exists()
        with plik_zdarzen.open("a", encoding="utf-8") as f:
            if nowy:
                f.write(NAGLOWEK_ZDARZEN)
            f.write("\n".join(zdarzenia) + "\n")

    ostatni_commit = poprzedni.get("ostatni_commit_zdarzen")
    commit_stan = None
    if efekty and not klon_ok:
        uwagi.append("git: bez commitów w klonie – klon wymaga uwagi")
        if wpisy_obok:
            n, opis = wpisy_ceo_obok(repo, wpisy_obok, "straznik: alert przy zablokowanym klonie (%s)" % czas_txt)
            uwagi.append("git: %s (%d)" % (opis, n))
    elif efekty:
        if ceo_zmieniony or pliki_skutkow:
            sciezki = ([PLIK_CEO] if ceo_zmieniony else []) + ([PLIK_ZDARZEN] if plik_zdarzen.exists() else []) + pliki_skutkow
            commit_stan = commituj(repo, sciezki, "straznik: alert %s (%s)" % (", ".join(sorted(set([n for n, _, _ in do_alertu] + (["skutki"] if pliki_skutkow else [])))), czas_txt))
        else:
            ostatni, _ = K.parsuj_czas(ostatni_commit)
            brudny = git(repo, "status", "--porcelain", "--", PLIK_ZDARZEN)[1].strip() != ""
            if brudny and (ostatni is None or teraz - ostatni >= timedelta(minutes=COMMIT_ZDARZEN_CO_MIN)):
                commit_stan = commituj(repo, [PLIK_ZDARZEN], "straznik: zdarzenia %s" % czas_txt)
        if commit_stan and commit_stan.startswith("commit"):
            ostatni_commit = K.iso(teraz)
        if commit_stan:
            uwagi.append("git: " + commit_stan)

    stan = {"czas": K.iso(teraz), "czas_przebiegu_s": round(time.monotonic() - t0, 1), "kontrole": wyniki,
            "alerty": stan_alertow["alerty"], "bledy_zrodel": stan_alertow["bledy_zrodel"],
            "alert_zrodel": stan_alertow["alert_zrodel"], "aktywne_id": stan_alertow["aktywne_id"],
            "wyciszenia": [dict(x, do=K.iso(x["do"])) for x in wyciszenia if x["do"] > teraz], "ostatni_commit_zdarzen": ostatni_commit, "mail": mail_stan,
            "alerty_przebiegu": alerty_przebiegu, "uwagi": uwagi}
    plik_stanu.parent.mkdir(parents=True, exist_ok=True)
    tmp = plik_stanu.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stan, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(plik_stanu)

    print("%s %s · alerty: %d · %.1f s%s" % (
        czas_txt, " ".join("%s=%s%s" % (n, w["status"], "(%d)" % len(w["id"]) if w["id"] else "") for n, w in wyniki.items()),
        len(alerty_przebiegu), stan["czas_przebiegu_s"], (" · " + "; ".join(uwagi)) if uwagi else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
