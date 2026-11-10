#!/usr/bin/env python3
"""Testy scripts/scalanie.py – bez sieci, bez prawdziwego `gh` i bez LLM:
python3 -m unittest discover -s scripts -p 'test_scalanie.py'

Klasyfikacja działa na wstrzykniętym `Kontekst` (bez gita i plików). Blokada, kolejka oczekujących i zapisy – tylko w katalogach
tymczasowych: zmienne SCALANIE_* nigdy nie wskazują domyślnych ścieżek w katalogu domowym. Testy integracyjne używają prawdziwego
gita w katalogu tymczasowym (bare origin + klon, konfiguracja hermetyczna) i atrapy `gh` podstawionej w PATH."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True      # test nie zostawia scripts/__pycache__ (także pod python3 -I)

TU = pathlib.Path(__file__).resolve().parent


def _modul(nazwa, sciezka):
    spec = importlib.util.spec_from_file_location(nazwa, sciezka)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S = _modul("scalanie", TU / "scalanie.py")
B = _modul("backlog", TU.parent / "pm" / "narzedzia" / "backlog.py")

TERAZ = dt.datetime(2026, 11, 9, 10, 0)
TERAZ_ISO = "2026-11-09T10:00"
TERAZ_S = 1794214800.0                                  # dowolna stała epoka – testy nie czytają zegara
R1, R2 = "firma/produkt", "firma/firma-agenci"          # R1 = repo produktu (klucz: goły numer), R2 = repo organizacji
HEAD, HEAD2 = "a" * 40, "b" * 40
NIGDZIE = pathlib.Path("/nie-ma-takiego-katalogu-scalanie")   # klasyfikacja nie czyta plików ani gita

_siatka = []


def setUpModule():
    """Siatka bezpieczeństwa na cały moduł: ścieżki blokady, tętna i katalogu roboczego w katalogu tymczasowym (żaden test,
    nawet bez własnego ustawienia, nie dotknie ~/.org-scalanie*), git bez konfiguracji użytkownika i systemu, bez roli sesji."""
    tmp = tempfile.TemporaryDirectory()
    baza = pathlib.Path(tmp.name).resolve()
    (baza / "gitconfig").write_text("", encoding="utf-8")
    srod = mock.patch.dict(os.environ, {
        "SCALANIE_BLOKADA": str(baza / "blokada.lock"), "SCALANIE_TETNO": str(baza / "tetno.json"),
        "SCALANIE_KATALOG": str(baza / "robocze" / "wt"), "GIT_CONFIG_GLOBAL": str(baza / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    srod.start()
    for zm in ("AGENT_ROLA", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        os.environ.pop(zm, None)
    _siatka.extend([srod, tmp])


def tearDownModule():
    srod, tmp = _siatka
    srod.stop()
    tmp.cleanup()


# ---------- pomocnicze ----------

def pr(nr=12, head=HEAD, base="main", mergeable="MERGEABLE", ci="SUCCESS", pliki=("src/a.py",), tytul="Zmiana", body="",
       szkic=False, etykiety=(), galaz="agent/inzynier-zmiana", utworzony="2026-11-09T07:00:00Z", zmienione=None):
    """PR w kształcie `gh pr list --json …`; ci: wynik jedynego checku, None = brak checków, lista = gotowy statusCheckRollup."""
    checki = ci if isinstance(ci, list) else [] if ci is None else [{"name": "testy", "conclusion": ci}]
    return {"number": nr, "title": tytul, "body": body, "baseRefName": base, "headRefName": galaz, "headRefOid": head,
            "mergeable": mergeable, "statusCheckRollup": checki, "files": [{"path": p} for p in pliki],
            "changedFiles": len(pliki) if zmienione is None else zmienione, "isDraft": szkic, "createdAt": utworzony,
            "labels": [{"name": e} for e in etykiety]}


def werdykt(sha="aaaaaaa", wynik="OK", scalenie="tak", kiedy="2026-11-09 09:00", **kw):
    """Werdykt recenzenta z polami maszynowymi; scalenie=None = pola brak."""
    w = {"sha": sha, "wynik": wynik, "warunki": [], "kroki": [], "kiedy": kiedy}
    if scalenie is not None:
        w["scalenie"] = scalenie
    w.update(kw)
    return w


def kon(rec=None, st=None, wstrz=None, repo=NIGDZIE, ust=None, prg=None, **kw):
    """Kontekst z wstrzykniętymi danymi – niczego nie czyta z dysku ani z gita, niczego nie pyta GitHuba."""
    u = {k: (list(v) if isinstance(v, list) else v) for k, v in S.UST_DOMYSLNE.items()}
    u.update(ust or {})
    p = dict(S.PROGI_DOMYSLNE)
    p.update(prg or {})
    par = dict(teraz=TERAZ, repa=[R1, R2], ust=u, prg=p, rec=rec if rec is not None else {},
               st=st if st is not None else {"zgloszone": {}, "przepiete": {}}, wstrz=wstrz if wstrz is not None else {},
               org_github=R2, agenci=["inzynier", "recenzent"], teraz_s=TERAZ_S,
               f_stan_pr=lambda r, n: None, f_stan_galezi=lambda r, g: None, f_migracje=lambda r, u_: [])
    par.update(kw)
    return S.Kontekst(repo, **par)


def wyjscie(f, *a, **kw):
    """-> (wynik funkcji, tekst wypisany na stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        wyn = f(*a, **kw)
    return wyn, buf.getvalue()


class Pomocnicze(unittest.TestCase):
    def test_czysc_zostawia_jedna_linie_bez_skladni_powloki(self):
        self.assertEqual(S.czysc("a\n b `rm` $(x) | y"), "a b ?rm? ?(x) ? y")
        self.assertEqual(S.czysc("x" * 100, 10), "x" * 10 + "…")
        self.assertEqual(S.czysc(None), "")

    def test_wzorce_sciezek(self):
        self.assertTrue(S.pasuje("infra/a.tf", ["infra/"]))                 # „/” na końcu = katalog od początku ścieżki
        self.assertFalse(S.pasuje("src/infra/a.tf", ["infra/"]))
        self.assertTrue(S.pasuje("app/migrations/0001.sql", ["*/migrations/*"]))
        self.assertTrue(S.pasuje("konfig/prod.env", ["*.env"]))             # bez „/” = glob po nazwie pliku
        self.assertFalse(S.pasuje("Dockerfile.dev", ["Dockerfile"]))

    def test_klucz_pierwszego_repo_to_goly_numer(self):
        repa = [R1, R2]
        self.assertEqual(S.klucz(R1, 5, repa), "5")
        self.assertEqual(S.klucz(R2, 5, repa), "firma-agenci#5")
        self.assertEqual(S.z_klucza("5", repa), (R1, "5"))
        self.assertEqual(S.z_klucza("firma-agenci#5", repa), (R2, "5"))
        for zly in ("obce#5", "abc", "", "5a"):
            self.assertIsNone(S.z_klucza(zly, repa), zly)

    def test_czas_werdyktu_dokladny_tylko_z_pola_kiedy(self):
        self.assertEqual(S.czas_werdyktu({"kiedy": "2026-11-09 09:00"}), (dt.datetime(2026, 11, 9, 9, 0), True))
        self.assertEqual(S.czas_werdyktu({"data": "2026-11-09"}), (dt.datetime(2026, 11, 9), False))
        self.assertEqual(S.czas_werdyktu({"kiedy": "wczoraj"}), (None, False))

    def test_czas_z_githuba_jest_przeliczany_na_strefe_organizacji(self):
        self.assertEqual(S.czas_gh("2026-11-09T07:00:00Z", NIGDZIE), dt.datetime(2026, 11, 9, 8, 0))
        self.assertIsNone(S.czas_gh("kiedyś", NIGDZIE))

    def test_brak_czasu_z_githuba_to_none_a_nie_zegar(self):
        """Brak czasu to None – nigdy bieżący zegar (inaczej wiek PR-a i czas scalenia liczyłyby się od „teraz”)."""
        for brak in (None, "", "   ", 0):
            self.assertIsNone(S.czas_gh(brak, NIGDZIE), brak)


class PolaWerdyktu(unittest.TestCase):
    """werdykt_pol: skrypt czyta tylko pola maszynowe; wszystko, czego nie rozumie, to NIEJASNY (nigdy scalenie)."""

    def pol(self, w, repo_gh=R1, **kw):
        return S.werdykt_pol(w, repo_gh, kon(**kw))

    def test_tak_bez_warunkow(self):
        self.assertEqual(self.pol(werdykt()), ("TAK", ""))
        self.assertEqual(self.pol(werdykt(wynik="ok z uwagami")), ("TAK", ""))

    def test_nieznany_wynik(self):
        self.assertEqual(self.pol(werdykt(wynik="CHYBA OK")), ("NIEJASNY", "nieznany wynik werdyktu"))

    def test_brak_pola_scalenie(self):
        self.assertEqual(self.pol(werdykt(scalenie=None)), ("NIEJASNY", "brak pola „scalenie”"))
        self.assertEqual(self.pol(werdykt(wynik="ZMIANY", scalenie=None)), ("NIE", "werdykt ZMIANY"))

    def test_scalenie_nie_i_wartosci_spoza_slownika(self):
        self.assertEqual(self.pol(werdykt(scalenie="nie")), ("NIE", "scalenie: nie"))
        self.assertEqual(self.pol(werdykt(scalenie="chyba")), ("NIEJASNY", "pole „scalenie” spoza tak / nie / warunek"))
        self.assertEqual(self.pol(werdykt(wynik="ZMIANY", scalenie="tak")), ("NIEJASNY", "wynik ZMIANY sprzeczny ze scalenie: tak"))

    def test_warunki_i_kroki_musza_byc_listami(self):
        self.assertEqual(self.pol(werdykt(warunki="po #7")), ("NIEJASNY", "„warunki” i „kroki” muszą być listami"))
        self.assertEqual(self.pol(werdykt(scalenie="warunek")), ("NIEJASNY", "scalenie: warunek bez warunków i kroków"))

    def test_zaleznosc_od_innego_pr(self):
        w = werdykt(scalenie="warunek", warunki=["po #7"])
        self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: "OPEN"), ("ZALEZNOSC", "czeka na 7"))
        self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: "MERGED"), ("TAK", ""))
        self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: None), ("ZALEZNOSC", "czeka na 7 (stan nieznany)"))
        for stan in ("CLOSED", "BRAK"):
            self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: stan), ("NIEJASNY", "zależność 7 nie jest ani otwarta, ani scalona"))

    def test_zaleznosc_w_innym_repozytorium(self):
        pytane = []

        def f(r, n):
            pytane.append((r, n))
            return "OPEN"

        for warunek in ("po firma-agenci#3", "po firma/firma-agenci#3"):
            self.assertEqual(self.pol(werdykt(warunki=[warunek]), f_stan_pr=f), ("ZALEZNOSC", "czeka na firma-agenci#3"))
        self.assertEqual(pytane, [(R2, "3"), (R2, "3")])
        self.assertEqual(self.pol(werdykt(warunki=["po obce#3"])), ("NIEJASNY", "warunek wskazuje nieznane repozytorium: po obce#3"))

    def test_warunki_do_oceny_i_kroki_ida_do_ceo(self):
        w = werdykt(scalenie="warunek", warunki=["zgoda właściciela na cennik", "po #7"], kroki=["włącz flagę", "sprawdź logi"])
        self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: "OPEN"), ("WARUNEK", "warunki do oceny: 1, kroki: 2; czeka też na 7"))
        self.assertEqual(self.pol(w, f_stan_pr=lambda r, n: "MERGED"), ("WARUNEK", "warunki do oceny: 1, kroki: 2"))

    def test_otwarty_pr_z_tabeli_nie_wymaga_pytania_githuba(self):
        k = kon(f_stan_pr=lambda r, n: self.fail("GitHub nie powinien być pytany"))
        k.otwarte = {R1: [pr(nr=7)]}
        self.assertEqual(S.werdykt_pol(werdykt(warunki=["po 7"]), R1, k), ("ZALEZNOSC", "czeka na 7"))

    def test_stan_zaleznosci_jest_pytany_raz_na_przebieg(self):
        pytane = []
        k = kon(f_stan_pr=lambda r, n: pytane.append(n) or "MERGED")
        for _ in range(3):
            S.werdykt_pol(werdykt(warunki=["po #7"]), R1, k)
        self.assertEqual(pytane, ["7"])


class Klasyfikacja(unittest.TestCase):
    """klasa(): jedna klasa na PR; kolejność – najpierw to, co wyklucza scalenie, na końcu to, co wymaga czyjejś decyzji."""

    def kl(self, p=None, w=None, repo_gh=R1, **kw):
        """w=False = PR bez werdyktu; w=None = werdykt „OK, scalenie: tak” dla bieżącego head."""
        p = p if p is not None else pr()
        rec = {} if w is False else {S.klucz(repo_gh, p["number"], [R1, R2]): w if w is not None else werdykt()}
        return S.klasa(p, repo_gh, kon(rec=rec, **kw))

    def test_gotowy(self):
        self.assertEqual(self.kl(), ("GOTOWY", ""))
        self.assertEqual(self.kl(repo_gh=R2), ("GOTOWY", ""))

    def test_nieczytelny_head(self):
        self.assertEqual(self.kl(pr(head="zzz")), ("NIEZNANY", "nieczytelny head"))
        self.assertEqual(self.kl(pr(head="")), ("NIEZNANY", "nieczytelny head"))

    def test_szkic_i_pr_wylaczony_z_recenzji(self):
        self.assertEqual(self.kl(pr(szkic=True))[0], "SZKIC")
        self.assertEqual(self.kl(pr(tytul="[nie recenzować] próba")), ("SZKIC", "szkic albo PR wyłączony z recenzji"))

    def test_bez_werdyktu_swiezy_i_po_progu(self):
        self.assertEqual(self.kl(w=False), ("BRAK_WERDYKTU", "bez werdyktu od 120 min (próg 60)"))
        self.assertEqual(self.kl(pr(utworzony="2026-11-09T08:30:00Z"), w=False), ("SWIEZY", "czeka na recenzję 30 min"))
        self.assertEqual(self.kl(pr(utworzony="kiedyś"), w=False), ("BRAK_WERDYKTU", "bez werdyktu od ? min (próg 60)"))
        self.assertEqual(self.kl(w=False, prg={"pr_bez_werdyktu_min": 180})[0], "SWIEZY")

    def test_werdykt_dla_innego_commita(self):
        self.assertEqual(self.kl(w=werdykt(sha="bbbbbbb")), ("NOWY_HEAD", "werdykt dla bbbbbbb, head aaaaaaaaaa"))
        for sha in ("aaaa", "", "AAAAAAG", "aaaaaaa; rm"):                  # za krótki, pusty, nie-hex
            self.assertEqual(self.kl(w=werdykt(sha=sha))[0], "NOWY_HEAD", sha)
        self.assertEqual(self.kl(w=werdykt(sha="AAAAAAAAAA"))[0], "GOTOWY")    # wielkość liter bez znaczenia

    def test_werdykt_zmiany_nie_idzie_do_scalenia(self):
        self.assertEqual(self.kl(w=werdykt(wynik="ZMIANY", scalenie=None)), ("NIE_SCALAC", "werdykt ZMIANY"))
        self.assertEqual(self.kl(w=werdykt(scalenie="nie")), ("NIE_SCALAC", "scalenie: nie"))
        self.assertEqual(self.kl(w=werdykt(scalenie=None)), ("NIEJASNY", "brak pola „scalenie”"))

    def test_baza_inna_niz_glowna(self):
        p, baza = pr(base="agent/inzynier-rodzic"), "agent/inzynier-rodzic"
        self.assertEqual(self.kl(p, f_stan_galezi=lambda r, g: "OPEN"), ("CZEKA_NA_RODZICA", "baza %s – rodzic otwarty" % baza))
        self.assertEqual(self.kl(p, f_stan_galezi=lambda r, g: "MERGED"), ("PRZEPNIJ", "rodzic scalony – baza %s do zmiany na main" % baza))
        self.assertEqual(self.kl(p, f_stan_galezi=lambda r, g: None), ("NIEZNANY", "stan rodzica nieznany (GitHub nie odpowiedział)"))
        self.assertEqual(self.kl(p, f_stan_galezi=lambda r, g: "CLOSED"),
                         ("WARUNEK", "baza %s nie jest gałęzią główną, a jej PR nie jest ani otwarty, ani scalony" % baza))

    def test_rodzic_otwarty_w_tabeli_nie_wymaga_pytania_githuba(self):
        k = kon(rec={"12": werdykt()}, f_stan_galezi=lambda r, g: self.fail("GitHub nie powinien być pytany"))
        k.otwarte = {R1: [pr(nr=11, galaz="agent/inzynier-rodzic")]}
        self.assertEqual(S.klasa(pr(base="agent/inzynier-rodzic"), R1, k)[0], "CZEKA_NA_RODZICA")

    def test_konflikt_wyprzedza_ci(self):
        self.assertEqual(self.kl(pr(mergeable="CONFLICTING")), ("KONFLIKT", "konflikt z main"))
        self.assertEqual(self.kl(pr(mergeable="CONFLICTING", ci="FAILURE"))[0], "KONFLIKT")

    def test_brak_checkow_to_nie_zielone(self):
        self.assertEqual(self.kl(pr(ci=None)), ("BRAK_CI", "brak checków dla head"))
        self.assertEqual(self.kl(pr(ci=None), ust={"ci_wymagane": False}), ("GOTOWY", ""))
        self.assertEqual(self.kl(pr(ci=None), ust={"bez_ci": [R1]}), ("GOTOWY", ""))
        self.assertEqual(self.kl(pr(ci=None), repo_gh=R2, ust={"bez_ci": [R1]})[0], "BRAK_CI")

    def test_ci_czerwone_wymienia_najwyzej_trzy_checki(self):
        self.assertEqual(self.kl(pr(ci="FAILURE")), ("CI_CZERWONE", "czerwone: testy"))
        checki = [{"name": "lint", "conclusion": "FAILURE"}, {"context": "build", "state": "ERROR"},
                  {"name": "e2e", "conclusion": "CANCELLED"}, {"name": "typy", "conclusion": "TIMED_OUT"},
                  {"name": "zielony", "conclusion": "SUCCESS"}]
        self.assertEqual(self.kl(pr(ci=checki)), ("CI_CZERWONE", "czerwone: lint, build, e2e"))

    def test_ci_w_toku_i_scalalnosc_jeszcze_liczona(self):
        self.assertEqual(self.kl(pr(ci=[{"name": "testy", "status": "IN_PROGRESS"}])), ("CI_TRWA", "CI w toku"))
        self.assertEqual(self.kl(pr(ci=[{"name": "a", "conclusion": "SUCCESS"}, {"name": "b", "status": "QUEUED"}]))[0], "CI_TRWA")
        self.assertEqual(self.kl(pr(mergeable="UNKNOWN")), ("CI_TRWA", "GitHub jeszcze liczy scalalność"))
        zielone = [{"name": "a", "conclusion": "SUCCESS"}, {"name": "b", "conclusion": "SKIPPED"}, {"context": "c", "state": "NEUTRAL"}]
        self.assertEqual(self.kl(pr(ci=zielone)), ("GOTOWY", ""))

    def test_po_zmianie_bazy_inna_lista_plikow_wraca_do_recenzenta(self):
        def st(sha=HEAD, pliki=("src/a.py", "src/b.py")):
            return {"zgloszone": {}, "przepiete": {"12": {"sha": sha, "pliki": list(pliki)}}}

        self.assertEqual(self.kl(st=st()), ("PO_PRZEPIECIU", "po zmianie bazy lista plików inna niż w recenzji"))
        self.assertEqual(self.kl(st=st(pliki=("src/a.py",))), ("GOTOWY", ""))                  # ta sama lista
        self.assertEqual(self.kl(st=st(), w=werdykt(po_przepieciu=True)), ("GOTOWY", ""))      # recenzent potwierdził
        self.assertEqual(self.kl(st=st(sha=HEAD2)), ("GOTOWY", ""))                            # zapis dotyczył innego commita

    def test_lista_plikow_pusta_albo_niepelna(self):
        wzor = "lista plików pusta albo niepełna (%s z %s) – nie da się sprawdzić ścieżek"
        self.assertEqual(self.kl(pr(pliki=())), ("WYJATEK", wzor % (0, 0)))
        self.assertEqual(self.kl(pr(zmienione=3)), ("WYJATEK", wzor % (1, 3)))
        sto = tuple("src/p%03d.py" % i for i in range(100))
        self.assertEqual(self.kl(pr(pliki=sto)), ("WYJATEK", wzor % (100, 100)))                # limit odpowiedzi GitHuba
        p = pr(pliki=())
        p["changedFiles"] = None
        self.assertEqual(self.kl(p), ("WYJATEK", wzor % (0, "?")))

    def test_sciezki_wylaczone(self):
        self.assertEqual(self.kl(pr(pliki=(".github/workflows/ci.yml", "src/a.py"))),
                         ("WYJATEK", "ścieżki wyłączone: .github/workflows/ci.yml"))
        cztery = tuple(".github/%s.yml" % x for x in "abcd")
        self.assertEqual(self.kl(pr(pliki=cztery)),
                         ("WYJATEK", "ścieżki wyłączone: .github/a.yml, .github/b.yml, .github/c.yml i 1 innych"))

    def test_pliki_regul_wylaczone_tylko_w_repo_organizacji(self):
        p, ust = pr(pliki=("role/inzynier.md",)), {"reguly": ["role/"]}
        self.assertEqual(self.kl(p, ust=ust), ("GOTOWY", ""))
        self.assertEqual(self.kl(p, repo_gh=R2, ust=ust), ("WYJATEK", "ścieżki wyłączone: role/inzynier.md"))

    def test_warunek_zaleznosc_i_niejasny_dopiero_po_ci_i_sciezkach(self):
        krok = werdykt(scalenie="warunek", kroki=["włącz flagę"])
        self.assertEqual(self.kl(w=krok), ("WARUNEK", "warunki do oceny: 0, kroki: 1"))
        self.assertEqual(self.kl(pr(pliki=(".github/a.yml",)), w=krok)[0], "WYJATEK")
        self.assertEqual(self.kl(pr(ci="FAILURE"), w=krok)[0], "CI_CZERWONE")
        self.assertEqual(self.kl(w=werdykt(warunki=["po #7"]), f_stan_pr=lambda r, n: "OPEN"), ("ZALEZNOSC", "czeka na 7"))
        self.assertEqual(self.kl(pr(ci=None), w=werdykt(scalenie=None))[0], "BRAK_CI")

    def test_migracja_idzie_do_ceo(self):
        p = pr(pliki=("db/migrations/0007_tabela.sql", "src/a.py"))
        klasa_b = ("MIGRACJA", "klasa B albo brak klasy – decyzja właściciela")
        self.assertEqual(self.kl(p), klasa_b)
        self.assertEqual(self.kl(p, w=werdykt(klasa_migracji={"0007": "a"})), ("MIGRACJA", "klasa A – scalenie i zastosowanie: CEO"))
        self.assertEqual(self.kl(p, w=werdykt(klasa_migracji={"0007": "A", "0008": "B"})), klasa_b)
        self.assertEqual(self.kl(w=werdykt(klasa_migracji={"0007": "A"}))[0], "MIGRACJA")      # klasa w werdykcie bez pliku migracji
        self.assertEqual(self.kl(p, f_migracje=lambda r, u: ["db/migrations/0007_tabela.sql"]), klasa_b)   # ten sam plik to nie kolizja

    def test_numery_migracji_nieznane_albo_zajete(self):
        p = pr(pliki=("db/migrations/0007_tabela.sql",))
        self.assertEqual(self.kl(p, f_migracje=lambda r, u: None),
                         ("NIEZNANY", "nie udało się sprawdzić numerów migracji na gałęzi głównej"))
        self.assertEqual(self.kl(p, f_migracje=lambda r, u: ["db/migrations/0007_inna.sql", "db/migrations/0006_x.sql"]),
                         ("KOLIZJA_MIGRACJI", "numer 0007 zajęty na gałęzi głównej: db/migrations/0007_inna.sql"))
        self.assertEqual(self.kl(p, f_migracje=lambda r, u: ["inne/migrations/0007_inna.sql"])[0], "MIGRACJA")   # inny katalog

    def test_ten_sam_numer_migracji_w_starszym_otwartym_pr(self):
        p = pr(pliki=("db/migrations/0007_tabela.sql",))
        k = kon(rec={"12": werdykt()})
        k.otwarte = {R1: [pr(nr=5, pliki=("db/migrations/0007_stara.sql",)), p]}
        self.assertEqual(S.klasa(p, R1, k), ("KOLIZJA_MIGRACJI", "numer 0007 ma też starszy PR 5"))
        k = kon(rec={"12": werdykt()})
        k.otwarte = {R1: [p, pr(nr=20, pliki=("db/migrations/0007_nowsza.sql",))]}
        self.assertEqual(S.klasa(p, R1, k)[0], "MIGRACJA")                 # ustępuje młodszy PR, nie starszy

    def test_znaczniki_nie_scalac(self):
        ust = {"etykiety_stop": ["nie-scalac"]}
        self.assertEqual(self.kl(pr(etykiety=("Nie-Scalac",)), ust=ust), ("DECYZJA", "etykieta: nie-scalac"))
        self.assertEqual(self.kl(pr(etykiety=("nie-scalac",))), ("GOTOWY", ""))                # etykiety spoza ustawień nie liczą się
        znacznik = ("DECYZJA", "znacznik „nie scalać” w tytule albo opisie")
        for tytul in ("WIP: zmiana", "Zmiana (nie scalać)", "DNM cennik", "Zmiana – wymaga zgody"):
            self.assertEqual(self.kl(pr(tytul=tytul)), znacznik, tytul)
        self.assertEqual(self.kl(pr(body="Proszę nie scalac przed piątkiem")), znacznik)
        self.assertEqual(self.kl(pr(body="Opis: usuwa stary znacznik WIP z szablonu")), ("GOTOWY", ""))   # opis: tylko jednoznaczne zwroty


class Wstrzymania(unittest.TestCase):
    """Rejestr CEO nakłada się na PR-y, które bez niego poszłyby do scalenia albo do CEO."""

    def kl(self, wpis, p=None, w=None):
        p = p if p is not None else pr()
        return S.klasa(p, R1, kon(rec={"12": w if w is not None else werdykt()}, wstrz={"12": wpis}))

    def test_wstrzymany_dla_biezacego_head(self):
        for wpis in ({"sha": HEAD, "tryb": "head", "powod": "czekamy na umowę"}, {"sha": "aaaaaaa", "tryb": "do_odwolania",
                     "powod": "czekamy na umowę"}, {"powod": "czekamy na umowę"}):
            self.assertEqual(self.kl(wpis), ("WSTRZYMANY", "wstrzymany przez CEO: czekamy na umowę"))

    def test_nowy_commit_zdejmuje_wstrzymanie_tylko_w_trybie_head(self):
        self.assertEqual(self.kl({"sha": HEAD2, "tryb": "head", "powod": "x"}), ("GOTOWY", ""))
        self.assertEqual(self.kl({"sha": HEAD2, "tryb": "do_odwolania", "powod": "x"}),
                         ("DO_ZWOLNIENIA", "wstrzymany do odwołania, nowy head z werdyktem"))

    def test_wstrzymanie_nie_zaslania_pracy_autora_i_recenzenta(self):
        wpis = {"sha": HEAD, "tryb": "do_odwolania", "powod": "x"}
        self.assertEqual(self.kl(wpis, pr(mergeable="CONFLICTING"))[0], "KONFLIKT")
        self.assertEqual(self.kl(wpis, pr(ci="FAILURE"))[0], "CI_CZERWONE")
        self.assertEqual(self.kl(wpis, w=werdykt(sha="bbbbbbb"))[0], "NOWY_HEAD")
        self.assertEqual(self.kl(wpis, pr(pliki=(".github/a.yml",)))[0], "WSTRZYMANY")         # wiersz do CEO – zasłonięty
        stary = {"sha": HEAD2, "tryb": "do_odwolania", "powod": "x"}
        self.assertEqual(self.kl(stary, pr(pliki=(".github/a.yml",)))[0], "WYJATEK")           # nowy head: klasa do CEO zostaje


class Wiersz(unittest.TestCase):
    def w(self, p=None, w=None, repo_gh=R1, **kw):
        p = p if p is not None else pr()
        rec = {} if w is False else {S.klucz(repo_gh, p["number"], [R1, R2]): w if w is not None else werdykt()}
        return S.wiersz(p, repo_gh, kon(rec=rec, **kw))

    def test_gotowy_dostaje_polecenie_scalenia_z_przypietym_head(self):
        w = self.w()
        self.assertEqual((w["klucz"], w["klasa"], w["adresat"], w["do_zrobienia"], w["zgloszony"]), ("12", "GOTOWY", "scal", True, False))
        self.assertEqual(w["polecenia"], ["gh pr merge 12 --repo firma/produkt --merge --match-head-commit " + HEAD])
        self.assertEqual((w["werdykt"], w["min_od_werdyktu"], w["etap"], w["klucz_zgl"], w["sha_zgl"]), ("OK", 60, 1, "12", HEAD))
        w = self.w(repo_gh=R2, ust={"metoda": "squash"})
        self.assertEqual(w["klucz"], "firma-agenci#12")
        self.assertEqual(w["polecenia"], ["gh pr merge 12 --repo firma/firma-agenci --squash --match-head-commit " + HEAD])

    def test_adresaci(self):
        self.assertEqual(self.w(pr(mergeable="CONFLICTING"))["adresat"], "inzynier")                       # autor z nazwy gałęzi
        self.assertEqual(self.w(pr(mergeable="CONFLICTING", galaz="agent/nieznany-x"))["adresat"], "ceo")
        self.assertEqual(self.w(pr(mergeable="CONFLICTING", galaz="poprawka"))["adresat"], "ceo")
        self.assertEqual(self.w(w=False)["adresat"], "recenzent")
        self.assertEqual(self.w(pr(pliki=(".github/a.yml",)))["adresat"], "ceo")
        self.assertEqual(self.w(pr(ci=None))["adresat"], "własna")
        bez_ruchu = self.w(pr(szkic=True))
        self.assertEqual((bez_ruchu["adresat"], bez_ruchu["do_zrobienia"], bez_ruchu["polecenia"]), ("–", False, []))

    def test_autor_bez_wstrzyknietej_listy_wynika_z_pliku_roli(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "role").mkdir()
            (pathlib.Path(d) / "role" / "inzynier.md").write_text("# rola\n", encoding="utf-8")
            k = kon(repo=pathlib.Path(d), agenci=None)
            self.assertEqual(k.autor("agent/inzynier-zmiana"), "inzynier")
            self.assertEqual(k.autor("agent/analityk-zmiana"), "ceo")

    def test_tytul_i_galaz_to_dane_bez_skladni_powloki(self):
        w = self.w(pr(tytul="Zmiana `rm -rf` $(x)\nnowa linia", galaz="agent/inzynier-a;b"))
        self.assertEqual(w["tytul"], "Zmiana ?rm -rf? ?(x) nowa linia")
        self.assertEqual(w["galaz"], "agent/inzynier-a;b")

    def test_przepnij_ma_trzy_polecenia(self):
        w = self.w(pr(base="agent/inzynier-rodzic"), f_stan_galezi=lambda r, g: "MERGED")
        self.assertEqual((w["klasa"], w["adresat"]), ("PRZEPNIJ", "własna"))
        self.assertEqual(w["polecenia"], ["gh pr edit 12 --repo firma/produkt --base main", "gh pr close 12 --repo firma/produkt",
                                          "gh pr reopen 12 --repo firma/produkt"])

    def test_zgloszony_wiersz_nie_jest_do_zrobienia(self):
        def st(klasa, sha=HEAD, kiedy="2026-11-09 09:50", **kw):
            return {"zgloszone": {"12": dict(sha=sha, klasa=klasa, kiedy=kiedy, **kw)}, "przepiete": {}}

        konflikt = pr(mergeable="CONFLICTING")
        w = self.w(konflikt, st=st("KONFLIKT"))
        self.assertEqual((w["zgloszony"], w["do_zrobienia"], w["polecenia"]), (True, False, []))
        self.assertTrue(self.w(konflikt, st=st("KONFLIKT", sha=HEAD2))["do_zrobienia"])        # zgłoszenie dla starego commita
        self.assertTrue(self.w(konflikt, st=st("CI_CZERWONE"))["do_zrobienia"])                # zgłoszona była inna klasa

    def test_brak_ci_po_ponowieniu_idzie_do_ceo(self):
        def w(kiedy, **kw):
            st = {"zgloszone": {"12": dict(sha=HEAD, klasa="BRAK_CI", kiedy=kiedy, **kw)}, "przepiete": {}}
            return self.w(pr(ci=None), st=st)

        pierwszy = self.w(pr(ci=None))
        self.assertEqual((pierwszy["etap"], pierwszy["adresat"]), (1, "własna"))
        self.assertEqual(pierwszy["polecenia"], ["gh pr close 12 --repo firma/produkt", "gh pr reopen 12 --repo firma/produkt"])
        czeka = w("2026-11-09 09:31")                                       # 29 min po ponowieniu – jeszcze czekamy
        self.assertEqual((czeka["etap"], czeka["zgloszony"], czeka["do_zrobienia"]), (1, True, False))
        for kiedy in ("2026-11-09 09:29", "nieczytelne"):                   # 31 min albo czas nieczytelny – etap 2
            e2 = w(kiedy)
            self.assertEqual((e2["etap"], e2["adresat"], e2["uwaga"], e2["zgloszony"], e2["do_zrobienia"], e2["polecenia"]),
                             (2, "ceo", "brak checków mimo ponowienia", False, True, []))
        po = w("2026-11-09 08:00", etap=2)                                  # etap 2 zgłoszony – bez dubla
        self.assertEqual((po["etap"], po["zgloszony"], po["do_zrobienia"]), (1, True, False))

    def test_odrzucony_gotowy_jest_ponawiany_po_terminie_zlecenia(self):
        def w(kiedy, **kw):
            return self.w(st={"zgloszone": {"12": {"sha": HEAD, "klasa": "GOTOWY", "kiedy": kiedy}}, "przepiete": {}}, **kw)

        swiezy = w("2026-11-09 06:00")                                      # dokładnie 4 h – jeszcze nie
        self.assertEqual((swiezy["zgloszony"], swiezy["do_zrobienia"], swiezy["polecenia"]), (True, False, []))
        stary = w("2026-11-09 05:59")
        self.assertEqual((stary["zgloszony"], stary["do_zrobienia"]), (False, True))
        self.assertEqual(len(stary["polecenia"]), 1)
        self.assertTrue(w("2026-11-09 09:00", prg={"zlecenie_scalania_termin_h": 0.5})["do_zrobienia"])
        self.assertTrue(w("brak czasu")["do_zrobienia"])


# ---------- tabela: zatrzymanie kolejki, pliki sporne, rezerwa CEO, wydruk ----------

ZIELONA = ("OK", "c" * 40)


def tab(k, listy, f_pr=None, glowna=ZIELONA, spania=None):
    """tabela() z atrapami: listy = {repo: [PR-y] albo None (błąd gh)}; glowna = wynik albo funkcja (repo, ust)."""
    f_glowna = glowna if callable(glowna) else (lambda r, u: glowna)
    spij = spania.append if spania is not None else (lambda s: None)
    return S.tabela(k, f_otwarte=lambda r: listy.get(r, []), f_pr=f_pr or (lambda r, nr, pola=None: None), spij=spij, f_glowna=f_glowna)


def rec_ok(*klucze, **kw):
    return {kk: werdykt(**kw) for kk in klucze}


class Tabela(unittest.TestCase):
    def test_wiersze_w_kolejnosci_repozytoriow_i_numerow(self):
        k = kon(rec=rec_ok("3", "20", "firma-agenci#1"))
        wiersze, bledy = tab(k, {R1: [pr(nr=20), pr(nr=3)], R2: [pr(nr=1)]})
        self.assertEqual([w["klucz"] for w in wiersze], ["3", "20", "firma-agenci#1"])
        self.assertEqual([w["klasa"] for w in wiersze], ["GOTOWY"] * 3)
        self.assertEqual((bledy, k.uwagi, k.sporne), ([], [], []))
        self.assertEqual(sorted(k.otwarte), sorted([R1, R2]))

    def test_blad_gh_pomija_repozytorium_a_smieci_w_liscie_sa_odrzucane(self):
        k = kon(rec=rec_ok("firma-agenci#1"))
        wiersze, bledy = tab(k, {R1: None, R2: [pr(nr=1), "śmieć", None]})
        self.assertEqual(bledy, [R1])
        self.assertEqual([w["klucz"] for w in wiersze], ["firma-agenci#1"])

    def test_niepoliczona_scalalnosc_jest_dopytywana_raz(self):
        pytane, spania = [], []

        def f_pr(r, nr, pola=None):                     # trzeci parametr opcjonalny: tabela woła z dwoma, polecenia z trzema
            pytane.append((r, nr, pola))
            return {"mergeable": "MERGEABLE"} if nr == 1 else None

        k = kon(rec=rec_ok("1", "2", "4"))
        listy = {R1: [pr(nr=1, mergeable="UNKNOWN"), pr(nr=2), pr(nr=3, mergeable="UNKNOWN", szkic=True), pr(nr=4, mergeable="")]}
        wiersze, _ = tab(k, listy, f_pr=f_pr, spania=spania)
        self.assertEqual(spania, [2])
        self.assertEqual(pytane, [(R1, 1, None), (R1, 4, None)])        # szkic i PR z policzoną scalalnością – bez pytania
        self.assertEqual([(w["klucz"], w["klasa"]) for w in wiersze], [("1", "GOTOWY"), ("2", "GOTOWY"), ("3", "SZKIC"), ("4", "CI_TRWA")])
        self.assertEqual(wiersze[3]["uwaga"], "GitHub jeszcze liczy scalalność")

    def test_bez_niepewnych_pr_nie_ma_czekania_a_dopytan_jest_najwyzej_20(self):
        spania, pytane = [], []
        tab(kon(), {R1: [pr(nr=1), pr(nr=2, mergeable="CONFLICTING")]}, spania=spania)
        self.assertEqual(spania, [])
        tab(kon(), {R1: [pr(nr=i, mergeable="UNKNOWN") for i in range(1, 26)]}, f_pr=lambda r, nr, pola=None: pytane.append(nr))
        self.assertEqual(len(pytane), 20)


class CzerwonaGlowna(unittest.TestCase):
    LISTY = {R1: [pr(nr=1), pr(nr=2), pr(nr=3, mergeable="CONFLICTING")], R2: [pr(nr=4)]}
    SHA = "c" * 40

    def wiersze(self, glowna=None, **kw):
        k = kon(rec=rec_ok("1", "2", "3", "firma-agenci#4"), **kw)
        domyslna = lambda r, u: ("CZERWONE", self.SHA) if r == R1 else ZIELONA      # noqa: E731
        w, _ = tab(k, self.LISTY, glowna=glowna or domyslna)
        return {x["klucz"]: x for x in w}, k

    def test_pierwszy_gotowy_niesie_zgloszenie_pozostale_czekaja(self):
        w, k = self.wiersze()
        p = w["1"]
        self.assertEqual((p["klasa"], p["adresat"], p["klucz_zgl"], p["sha_zgl"], p["do_zrobienia"], p["zgloszony"], p["polecenia"]),
                         ("GLOWNA_CZERWONA", "ceo", "glowna:produkt", self.SHA, True, False, []))
        self.assertEqual(p["uwaga"], "CI gałęzi main czerwone (cccccccccc) – gotowe PR-y w firma/produkt czekają: 2")
        d = w["2"]
        self.assertEqual((d["klasa"], d["adresat"], d["do_zrobienia"], d["polecenia"], d["uwaga"]),
                         ("CZEKA_NA_GLOWNA", "–", False, [], "czeka na zieloną gałąź główną"))
        self.assertEqual(w["3"]["klasa"], "KONFLIKT")                       # praca autora idzie dalej
        self.assertEqual(w["firma-agenci#4"]["klasa"], "GOTOWY")            # drugie repozytorium ma zieloną główną
        self.assertEqual(len(w["firma-agenci#4"]["polecenia"]), 1)
        self.assertEqual(k.uwagi, [])

    def test_zgloszenie_raz_na_czerwony_commit(self):
        def st(sha):
            return {"zgloszone": {"glowna:produkt": {"sha": sha, "klasa": "GLOWNA_CZERWONA", "kiedy": "2026-11-09 09:00"}}, "przepiete": {}}

        w, _ = self.wiersze(st=st(self.SHA))
        self.assertEqual((w["1"]["klasa"], w["1"]["zgloszony"], w["1"]["do_zrobienia"]), ("GLOWNA_CZERWONA", True, False))
        w, _ = self.wiersze(st=st("d" * 40))                                # nowy czerwony commit – nowe zgłoszenie
        self.assertEqual((w["1"]["zgloszony"], w["1"]["do_zrobienia"]), (False, True))

    def test_stan_nieznany_nie_zatrzymuje_kolejki(self):
        w, k = self.wiersze(glowna=lambda r, u: (None, ""))
        self.assertEqual([w[x]["klasa"] for x in ("1", "2", "firma-agenci#4")], ["GOTOWY"] * 3)
        self.assertEqual(k.uwagi, ["UWAGA: %s – stan CI gałęzi głównej nieznany, kolejka nie jest zatrzymana" % r for r in (R1, R2)])

    def test_ci_w_toku_albo_brak_ci_glownej_nie_zatrzymuje(self):
        for stan in ("TRWA", "BRAK", "OK"):
            w, k = self.wiersze(glowna=lambda r, u: (stan, self.SHA))
            self.assertEqual((w["1"]["klasa"], k.uwagi), ("GOTOWY", []), stan)

    def test_wylaczone_ustawieniem_nie_pyta_o_glowna(self):
        w, _ = self.wiersze(glowna=lambda r, u: self.fail("CI głównej nie powinno być pytane"), ust={"stop_gdy_glowna_czerwona": False})
        self.assertEqual(w["1"]["klasa"], "GOTOWY")

    def test_repozytorium_bez_gotowych_pr_nie_jest_pytane(self):
        pytane = []
        k = kon(rec=rec_ok("firma-agenci#4"))
        tab(k, {R1: [pr(nr=3, mergeable="CONFLICTING")], R2: [pr(nr=4)]}, glowna=lambda r, u: pytane.append(r) or ZIELONA)
        self.assertEqual(pytane, [R2])


class RejestrNieczytelny(unittest.TestCase):
    LISTY = {R1: [pr(nr=1), pr(nr=2, mergeable="CONFLICTING")], R2: [pr(nr=4)]}

    def wiersze(self, **kw):
        k = kon(rec=rec_ok("1", "2", "firma-agenci#4"), wstrz_blad=True, **kw)
        w, _ = tab(k, self.LISTY, glowna=lambda r, u: self.fail("bez gotowych PR-ów CI głównej nie jest pytane"))
        return {x["klucz"]: x for x in w}, k

    def test_nic_nie_jest_scalane_a_do_ceo_idzie_jedno_zgloszenie(self):
        w, k = self.wiersze()
        p = w["1"]
        self.assertEqual((p["klasa"], p["adresat"], p["klucz_zgl"], p["sha_zgl"], p["do_zrobienia"], p["polecenia"]),
                         ("REJESTR", "ceo", "rejestr:wstrzymane", "2026-11-09", True, []))
        self.assertEqual(p["uwaga"], "rejestr wstrzymań nieczytelny – gotowe PR-y czekają: 2")
        d = w["firma-agenci#4"]
        self.assertEqual((d["klasa"], d["adresat"], d["do_zrobienia"], d["polecenia"], d["uwaga"]),
                         ("WSTRZYMANY", "–", False, [], "rejestr wstrzymań nieczytelny"))
        self.assertEqual(w["2"]["klasa"], "KONFLIKT")
        self.assertEqual(k.uwagi, ["UWAGA: ceo/scalanie/wstrzymane.json nieczytelny – do naprawy pliku nic nie jest scalane"])

    def test_zgloszenie_raz_dziennie(self):
        def st(dzien):
            return {"zgloszone": {"rejestr:wstrzymane": {"sha": dzien, "klasa": "REJESTR", "kiedy": dzien + " 08:00"}}, "przepiete": {}}

        w, _ = self.wiersze(st=st("2026-11-09"))
        self.assertEqual((w["1"]["klasa"], w["1"]["zgloszony"], w["1"]["do_zrobienia"]), ("REJESTR", True, False))
        w, _ = self.wiersze(st=st("2026-11-08"))
        self.assertEqual((w["1"]["zgloszony"], w["1"]["do_zrobienia"]), (False, True))

    def test_czytelny_rejestr_niczego_nie_zmienia(self):
        k = kon(rec=rec_ok("1"))
        w, _ = tab(k, {R1: [pr(nr=1)]})
        self.assertEqual((w[0]["klasa"], k.uwagi, S.zatrzymaj_na_rejestrze(w, k)), ("GOTOWY", [], []))


class PlikiSporne(unittest.TestCase):
    LISTY = {R1: [pr(nr=1, pliki=("src/teksty.json", "src/a.py")), pr(nr=2, pliki=("src/teksty.json", "src/b.py")),
                  pr(nr=3, pliki=("src/teksty.json", "src/a.py")), pr(nr=4, pliki=("src/teksty.json", "src/a.py"), szkic=True)],
             R2: [pr(nr=1, pliki=("pm/backlog.md",)), pr(nr=2, pliki=("pm/backlog.md",))]}

    def test_plik_w_trzech_otwartych_pr_bez_szkicow(self):
        k = kon()
        tab(k, self.LISTY)
        self.assertEqual(k.sporne, [(R1, "src/teksty.json", 3)])
        self.assertEqual(S.pliki_sporne(k), k.sporne)

    def test_prog_z_ustawien_i_kolejnosc_od_najczestszego(self):
        k = kon(prg={"pliki_sporne_min_pr": 2})
        tab(k, self.LISTY)
        self.assertEqual(k.sporne, [(R1, "src/teksty.json", 3), (R2, "pm/backlog.md", 2), (R1, "src/a.py", 2)])


class RezerwaCeo(unittest.TestCase):
    def rez(self, minuty, tetno_min=None, **kw):
        wiersze = [{"klasa": "GOTOWY", "do_zrobienia": True, "min_od_werdyktu": m} for m in minuty]
        return S.rezerwa(wiersze, kon(tetno_s=None if tetno_min is None else TERAZ_S - tetno_min * 60, **kw))

    def test_nic_nie_czeka(self):
        self.assertEqual(self.rez([]), ("NIE", "nic nie czeka na scalenie"))
        zgloszony = [{"klasa": "GOTOWY", "do_zrobienia": False, "min_od_werdyktu": 500},
                     {"klasa": "KONFLIKT", "do_zrobienia": True, "min_od_werdyktu": 500}]
        self.assertEqual(S.rezerwa(zgloszony, kon()), ("NIE", "nic nie czeka na scalenie"))

    def test_gotowe_bez_czasu_werdyktu(self):
        self.assertEqual(self.rez([None, None]), ("NIE", "gotowe PR-y bez czasu werdyktu (pole kiedy albo data)"))

    def test_ponizej_progu(self):
        self.assertEqual(self.rez([10, 45, None]), ("NIE", "najstarszy gotowy PR czeka 45 min (próg 45)"))

    def test_agent_dzialal_niedawno(self):
        self.assertEqual(self.rez([60], tetno_min=10), ("NIE", "agent scalający działał 10 min temu"))
        self.assertEqual(self.rez([60], tetno_min=45), ("NIE", "agent scalający działał 45 min temu"))

    def test_agent_bez_sladu(self):
        tak = ("TAK", "gotowy PR czeka 60 min, agent scalający bez śladu od ponad 45 min")
        self.assertEqual(self.rez([60]), tak)                               # tętna nie ma wcale
        self.assertEqual(self.rez([60, 5], tetno_min=46), tak)
        self.assertEqual(self.rez([60], tetno_min=46, prg={"gotowy_rezerwa_ceo_min": 90})[0], "NIE")


class Wydruk(unittest.TestCase):
    def test_tabela_do_zrobienia_bez_ruchu_i_rezerwa(self):
        st = {"zgloszone": {"2": {"sha": HEAD, "klasa": "KONFLIKT", "kiedy": "2026-11-09 09:30"}}, "przepiete": {}}
        k = kon(rec=rec_ok("1", "2"), st=st)
        wiersze, bledy = tab(k, {R1: [pr(nr=1), pr(nr=2, mergeable="CONFLICTING"), pr(nr=3, szkic=True)], R2: None})
        _, out = wyjscie(S.wypisz, wiersze, bledy, k)
        linie = out.splitlines()
        self.assertEqual(linie[0], "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 3, do zrobienia: 1")
        self.assertEqual(linie[1], "BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu")
        self.assertEqual(linie[2].split(), ["1", "GOTOWY", "->", "scal", "aaaaaaaaaa"])
        self.assertEqual(linie[3], "    $ gh pr merge 1 --repo firma/produkt --merge --match-head-commit " + HEAD)
        self.assertEqual(linie[4], "bez ruchu: KONFLIKT (zgłoszone) 1, SZKIC 1")
        self.assertEqual(linie[5], "REZERWA_CEO: TAK – gotowy PR czeka 60 min, agent scalający bez śladu od ponad 45 min")
        self.assertEqual(len(linie), 6)

    def test_wszystko_pokazuje_kazdy_wiersz_z_gwiazdka_przy_zgloszonych(self):
        st = {"zgloszone": {"2": {"sha": HEAD, "klasa": "KONFLIKT", "kiedy": "2026-11-09 09:30"}}, "przepiete": {}}
        k = kon(rec=rec_ok("1", "2"), st=st)
        wiersze, bledy = tab(k, {R1: [pr(nr=1), pr(nr=2, mergeable="CONFLICTING"), pr(nr=3, szkic=True)]})
        _, out = wyjscie(S.wypisz, wiersze, bledy, k, wszystko=True)
        linie = out.splitlines()
        self.assertEqual(linie[3].split()[:5], ["2", "KONFLIKT*", "->", "inzynier", "aaaaaaaaaa"])
        self.assertEqual(linie[4].split()[:4], ["3", "SZKIC", "->", "–"])
        self.assertFalse(any(x.startswith("bez ruchu") for x in linie))
        self.assertTrue(linie[-1].startswith("REZERWA_CEO: "))

    def test_pusta_kolejka(self):
        k = kon()
        wiersze, bledy = tab(k, {})
        _, out = wyjscie(S.wypisz, wiersze, bledy, k)
        self.assertEqual(out.splitlines(), ["KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 0, do zrobienia: 0", "NIC DO ZROBIENIA",
                                            "REZERWA_CEO: NIE – nic nie czeka na scalenie"])

    def test_uwagi_i_pliki_sporne_w_naglowku(self):
        k = kon()
        k.uwagi = ["UWAGA: przykład"]
        k.sporne = [(R1, "src/p%d.json" % i, 9 - i) for i in range(6)]
        _, out = wyjscie(S.wypisz, [], [], k)
        linie = out.splitlines()
        self.assertEqual(linie[1], "UWAGA: przykład")
        self.assertTrue(linie[2].startswith("PLIKI SPORNE: src/p0.json (9 PR-ów, produkt); src/p1.json (8 PR-ów, produkt); "))
        self.assertTrue(linie[2].endswith("src/p4.json (5 PR-ów, produkt) i 1 innych"))


# ---------- blokada, tętno i kolejka oczekujących – wszystko w katalogu tymczasowym ----------

class Tymczasowe(unittest.TestCase):
    """Każdy test ma własny katalog: repozytorium, blokadę, tętno i katalog roboczy. Nic nie trafia do katalogu domowego."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.blokada = self.tmp / "blokada.lock"
        self.plik_tetna = self.tmp / "tetno.json"
        self.katalog = self.tmp / "robocze" / "wt"
        p = mock.patch.dict(os.environ, {"SCALANIE_BLOKADA": str(self.blokada), "SCALANIE_TETNO": str(self.plik_tetna),
                                         "SCALANIE_KATALOG": str(self.katalog)})
        p.start()
        self.addCleanup(p.stop)
        self.prg = dict(S.PROGI_DOMYSLNE)

    def wez(self, kto="scalanie-a", teraz_s=TERAZ_S):
        return S.wez_blokade(self.repo, kto, teraz_s, self.prg)


class Blokada(Tymczasowe):
    def test_sciezki_ze_zmiennych_srodowiska(self):
        self.assertEqual(S.sciezki(self.repo), {"blokada": self.blokada, "tetno": self.plik_tetna, "katalog": self.katalog,
                                                "oczekujace": self.tmp / "robocze" / "oczekujace.jsonl"})

    def test_wziecie_zapisuje_wlasciciela_i_token(self):
        kod, token = self.wez()
        self.assertEqual(kod, 0)
        self.assertRegex(token, r"^[0-9a-f]{16}$")
        self.assertEqual(json.loads((self.blokada / "kto").read_text(encoding="utf-8")),
                         {"kto": "scalanie-a", "token": token, "od_s": TERAZ_S, "protokol": S.PROTOKOL})
        self.assertEqual(S.blokada_info(self.blokada), {"kto": "scalanie-a", "token": token, "od_s": TERAZ_S})
        self.assertEqual([p.name for p in self.blokada.iterdir()], ["kto"])          # bez resztek pliku tymczasowego

    def test_druga_proba_dostaje_zajeta_takze_dokladnie_na_progu(self):
        self.wez()
        self.assertEqual(self.wez("ceo-czat", TERAZ_S + 5 * 60), (10, "BLOKADA zajęta: scalanie-a od 5 min"))
        self.assertEqual(self.wez("ceo-czat", TERAZ_S + 30 * 60), (10, "BLOKADA zajęta: scalanie-a od 30 min"))
        self.assertEqual(S.blokada_info(self.blokada)["kto"], "scalanie-a")

    def test_przestarzala_blokada_jest_przejmowana(self):
        _, stary = self.wez()
        (kod, nowy), out = wyjscie(self.wez, "ceo-czat", TERAZ_S + 31 * 60)
        self.assertEqual(kod, 0)
        self.assertNotEqual(nowy, stary)
        self.assertEqual(out.strip(), "BLOKADA przejęta po scalanie-a (bez znaku od 31 min, próg 30)")
        self.assertEqual(S.blokada_info(self.blokada), {"kto": "ceo-czat", "token": nowy, "od_s": TERAZ_S + 31 * 60})
        self.assertEqual(S.sprawdz_token(self.repo, stary)[0], 11)                   # stary właściciel już nie zapisuje
        self.assertEqual([p.name for p in self.tmp.iterdir() if ".stara-" in p.name], [])

    def test_prog_przejecia_z_progow_organizacji(self):
        self.wez()
        self.prg["blokada_scalania_min"] = 5
        (kod, _), out = wyjscie(self.wez, "scalanie-b", TERAZ_S + 6 * 60)
        self.assertEqual(kod, 0)
        self.assertEqual(out.strip(), "BLOKADA przejęta po scalanie-a (bez znaku od 6 min, próg 5)")

    def test_blokada_bez_czytelnego_wlasciciela(self):
        # przebieg zabity między mkdir a zapisem pliku `kto`: wiek z daty katalogu, właściciel „?”
        self.blokada.mkdir()
        (self.blokada / "kto").write_text("{nie json", encoding="utf-8")
        od = self.blokada.stat().st_mtime
        self.assertEqual(S.blokada_info(self.blokada), {"kto": "?", "token": "", "od_s": od})
        self.assertEqual(self.wez("ceo-czat", od + 60), (10, "BLOKADA zajęta: ? od 1 min"))
        self.assertEqual(S.sprawdz_token(self.repo, ""), (11, "BLOKADA nie twoja: trzyma ją ? – niczego nie scalaj ani nie zapisuj"))
        (kod, token), out = wyjscie(self.wez, "ceo-czat", od + 31 * 60)
        self.assertEqual((kod, out.strip()), (0, "BLOKADA przejęta po ? (bez znaku od 31 min, próg 30)"))
        self.assertEqual(S.sprawdz_token(self.repo, token)[0], 0)

    def test_blad_systemu_plikow_to_kod_12(self):
        gdzie = self.tmp / "nie-ma-katalogu" / "blokada.lock"
        with mock.patch.dict(os.environ, {"SCALANIE_BLOKADA": str(gdzie)}):
            self.assertEqual(self.wez(), (12, "BŁĄD SYSTEMU PLIKÓW: nie da się założyć blokady %s (FileNotFoundError)" % gdzie))
        self.assertFalse(gdzie.parent.exists())

    def test_nieudany_zapis_wlasciciela_nie_zostawia_blokady(self):
        with mock.patch.object(S, "zapisz_plik", side_effect=PermissionError("brak praw")):
            self.assertEqual(self.wez(), (12, "BŁĄD SYSTEMU PLIKÓW: nie da się zapisać właściciela blokady (PermissionError)"))
        self.assertFalse(self.blokada.exists())

    def test_sprawdz_token(self):
        brak = (10, "BRAK BLOKADY: najpierw `scalanie.py blokada <kto>` – bez blokady niczego nie scalaj ani nie zapisuj")
        self.assertEqual(S.sprawdz_token(self.repo, "0" * 16), brak)
        _, token = self.wez()
        cudza = (11, "BLOKADA nie twoja: trzyma ją scalanie-a – niczego nie scalaj ani nie zapisuj")
        self.assertEqual(S.sprawdz_token(self.repo, "0" * 16), cudza)
        self.assertEqual(S.sprawdz_token(self.repo, ""), cudza)
        self.assertEqual(S.sprawdz_token(self.repo, None), cudza)
        self.assertEqual(S.sprawdz_token(self.repo, token), (0, {"kto": "scalanie-a", "token": token, "od_s": TERAZ_S}))

    def test_odswiezenie_przesuwa_znak_zycia(self):
        _, token = self.wez()
        self.assertEqual(S.odswiez(self.repo, token, TERAZ_S + 20 * 60), (0, "BLOKADA odświeżona"))
        self.assertEqual(S.blokada_info(self.blokada), {"kto": "scalanie-a", "token": token, "od_s": TERAZ_S + 20 * 60})
        # 40 min po wzięciu, ale 20 min po odświeżeniu – nikt jej nie przejmie
        self.assertEqual(self.wez("ceo-czat", TERAZ_S + 40 * 60), (10, "BLOKADA zajęta: scalanie-a od 20 min"))

    def test_odswiezenie_cudzej_albo_zadnej_blokady(self):
        self.assertEqual(S.odswiez(self.repo, "0" * 16, TERAZ_S)[0], 10)
        self.wez()
        self.assertEqual(S.odswiez(self.repo, "0" * 16, TERAZ_S + 600),
                         (11, "BLOKADA nie twoja: trzyma ją scalanie-a – niczego nie scalaj ani nie zapisuj"))
        self.assertEqual(S.blokada_info(self.blokada)["od_s"], TERAZ_S)

    def test_odswiezenie_przy_bledzie_zapisu(self):
        _, token = self.wez()
        with mock.patch.object(S, "zapisz_plik", side_effect=PermissionError("brak praw")):
            self.assertEqual(S.odswiez(self.repo, token, TERAZ_S + 60), (12, "BŁĄD SYSTEMU PLIKÓW: blokada nieodświeżona (PermissionError)"))

    def test_odblokowanie(self):
        self.assertEqual(S.odblokuj(self.repo, "0" * 16, TERAZ_S), (0, "BLOKADY nie było"))
        self.assertFalse(self.plik_tetna.exists())
        _, token = self.wez()
        self.assertEqual(S.odblokuj(self.repo, "0" * 16, TERAZ_S + 60), (11, "BLOKADA nie twoja: trzyma ją scalanie-a – zostaje"))
        self.assertEqual(S.odblokuj(self.repo, "", TERAZ_S + 60)[0], 11)
        self.assertTrue(self.blokada.is_dir())
        self.assertFalse(self.plik_tetna.exists())
        self.assertEqual(S.odblokuj(self.repo, token, TERAZ_S + 60), (0, "BLOKADA zwolniona"))
        self.assertFalse(self.blokada.exists())
        self.assertEqual(self.wez("ceo-czat", TERAZ_S + 61)[0], 0)                   # zwolniona blokada jest od razu do wzięcia

    def test_tetno_zapisuje_tylko_agent_scalajacy(self):
        self.assertIsNone(S.tetno(self.repo))
        _, token = self.wez("ceo-czat")
        S.odblokuj(self.repo, token, TERAZ_S + 60)
        self.assertFalse(self.plik_tetna.exists())                                   # czat CEO nie udaje agenta
        _, token = self.wez("scalanie-a", TERAZ_S + 120)
        S.odblokuj(self.repo, token, TERAZ_S + 180, z_tetnem=False)
        self.assertFalse(self.plik_tetna.exists())                                   # przebieg przerwany błędem – bez śladu
        _, token = self.wez("scalanie-a", TERAZ_S + 240)
        S.odblokuj(self.repo, token, TERAZ_S + 300)
        self.assertEqual(json.loads(self.plik_tetna.read_text(encoding="utf-8")), {"kto": "scalanie-a", "kiedy_s": TERAZ_S + 300})
        self.assertEqual(S.tetno(self.repo), TERAZ_S + 300)

    def test_tetno_nieczytelne_to_none(self):
        for tresc in ("", "{nie json", "[1]", '{"kiedy_s": "wczoraj"}', '{"kto": "scalanie-a"}'):
            self.plik_tetna.write_text(tresc, encoding="utf-8")
            self.assertIsNone(S.tetno(self.repo), tresc)


class KolejkaOczekujacych(Tymczasowe):
    def test_brak_pliku_to_pusta_kolejka(self):
        self.assertEqual(S.oczekujace(self.repo), [])
        S.wyczysc_oczekujace(self.repo)                                              # brak pliku nie jest błędem

    def test_dopisanie_odczyt_i_czyszczenie(self):
        ops = [{"op": "stan_del", "sekcja": "zgloszone", "klucz": "5"},
               {"op": "dziennik", "linia": {"klucz": "5", "sha": HEAD, "kto": "żółw"}}]
        S.dopisz_oczekujace(self.repo, ops[:1])
        S.dopisz_oczekujace(self.repo, ops[1:])
        plik = self.tmp / "robocze" / "oczekujace.jsonl"
        linie = plik.read_text(encoding="utf-8").splitlines()
        self.assertEqual(linie[0], '{"klucz": "5", "op": "stan_del", "sekcja": "zgloszone"}')
        self.assertIn("żółw", linie[1])
        self.assertEqual(S.oczekujace(self.repo), ops)
        self.assertFalse(self.katalog.exists())                                      # kolejka leży obok katalogu roboczego, nie w nim
        S.wyczysc_oczekujace(self.repo)
        self.assertFalse(plik.exists())
        self.assertEqual(S.oczekujace(self.repo), [])

    def test_smieci_w_pliku_sa_pomijane(self):
        plik = self.tmp / "robocze" / "oczekujace.jsonl"
        plik.parent.mkdir(parents=True)
        plik.write_text('nie json\n[1, 2]\n{"bez": "op"}\n{"op": ""}\n\n{"op": "stan_del", "sekcja": "przepiete", "klucz": "7"}\n',
                        encoding="utf-8")
        self.assertEqual(S.oczekujace(self.repo), [{"op": "stan_del", "sekcja": "przepiete", "klucz": "7"}])


# ---------- nakładanie zapisów na katalog roboczy ----------

def zlec(klucz_="5", adresat="ceo", podpis=None, wpis=None, dzien="20261109", klasa="KONFLIKT"):
    """Zapis „zlecenie” w kształcie z ops_zgloszenia (bez gita; treść wpisu skrócona)."""
    podpis = podpis if podpis is not None else "Kolejka: %s · %s · aaaaaaaaaaaa" % (klucz_, klasa)
    if wpis is None:
        wpis = "## [otwarte] 2026-11-09 10:00 · od: scalanie · temat – PR %s · {ID}\ntreść\n%s\nOdpowiedź:" % (klucz_, podpis)
    o = {"op": "zlecenie", "adresat": adresat, "wpis": wpis, "podpis": podpis, "dzien": dzien}
    if klucz_ is not None:
        o["klucz"] = klucz_
    return o


class Zastosuj(Tymczasowe):
    NAGLOWEK = "# Zlecenia – %s\n\nFormat wpisu i zasady: `zlecenia/README.md`.\n"

    def plik(self, rel):
        return (self.repo / rel).read_text(encoding="utf-8")

    def wpisz(self, rel, tekst):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tekst, encoding="utf-8")

    def test_stan_set_i_stan_del(self):
        w5, w7 = {"sha": HEAD, "klasa": "KONFLIKT", "kiedy": "2026-11-09 10:00"}, {"sha": HEAD2, "z_bazy": "agent/rodzic", "pliki": ["a.py"]}
        zm, idy = S.zastosuj(self.repo, [{"op": "stan_set", "sekcja": "zgloszone", "klucz": "5", "wartosc": w5},
                                         {"op": "stan_set", "sekcja": "przepiete", "klucz": 7, "wartosc": w7}], TERAZ)
        self.assertEqual((zm, idy), (["ceo/scalanie/stan.json"], {}))
        oczekiwany = {"przepiete": {"7": w7}, "zgloszone": {"5": w5}}
        self.assertEqual(self.plik("ceo/scalanie/stan.json"), json.dumps(oczekiwany, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertEqual(S.stan(self.repo), oczekiwany)
        zm, _ = S.zastosuj(self.repo, [{"op": "stan_del", "sekcja": "zgloszone", "klucz": "5"},
                                       {"op": "stan_del", "sekcja": "przepiete", "klucz": "nie-ma"}], TERAZ)
        self.assertEqual(zm, ["ceo/scalanie/stan.json"])
        self.assertEqual(S.stan(self.repo), {"przepiete": {"7": w7}, "zgloszone": {}})

    def test_bledne_zapisy_stanu_sa_pomijane(self):
        ops = [{"op": "stan_set", "sekcja": "inne", "klucz": "5", "wartosc": {"sha": HEAD}},
               {"op": "stan_set", "sekcja": "zgloszone", "klucz": "5", "wartosc": "tekst"},
               {"op": "stan_set", "sekcja": "zgloszone", "klucz": "", "wartosc": {"sha": HEAD}},
               {"op": "stan_del", "sekcja": "inne", "klucz": "5"}, {"op": "stan_del", "sekcja": "zgloszone", "klucz": "5"},
               {"op": "dziennik", "linia": "tekst"}, {"op": "nieznany"}, {}]
        self.assertEqual(S.zastosuj(self.repo, ops, TERAZ), ([], {}))
        self.assertEqual(list(self.repo.iterdir()), [])                              # nic nie powstało

    def test_dziennik_bez_powtorek(self):
        stara = json.dumps({"klucz": "5", "sha": HEAD})
        self.wpisz("ceo/scalanie/dziennik.jsonl", stara)                             # bez końca linii
        nowa = {"klucz": "6", "sha": HEAD2, "kto": "scalanie-a", "werdykt": "OK – żółć"}
        zm, _ = S.zastosuj(self.repo, [{"op": "dziennik", "linia": {"klucz": "5", "sha": HEAD, "kto": "ktoś inny"}},
                                       {"op": "dziennik", "linia": nowa}, {"op": "dziennik", "linia": dict(nowa)}], TERAZ)
        self.assertEqual(zm, ["ceo/scalanie/dziennik.jsonl"])
        self.assertEqual(self.plik("ceo/scalanie/dziennik.jsonl"), stara + "\n" + json.dumps(nowa, ensure_ascii=False, sort_keys=True) + "\n")
        # ten sam PR z nowym commitem to nowe scalenie
        zm, _ = S.zastosuj(self.repo, [{"op": "dziennik", "linia": {"klucz": "6", "sha": HEAD}}], TERAZ)
        self.assertEqual(zm, ["ceo/scalanie/dziennik.jsonl"])
        self.assertEqual(len(self.plik("ceo/scalanie/dziennik.jsonl").splitlines()), 3)

    def test_nowa_skrzynka_i_numer_zlecenia(self):
        zm, idy = S.zastosuj(self.repo, [zlec()], TERAZ)
        self.assertEqual((zm, idy), (["zlecenia/ceo.md"], {"5": "Z-20261109-01"}))
        self.assertEqual(self.plik("zlecenia/ceo.md"), self.NAGLOWEK % "ceo" + "\n## [otwarte] 2026-11-09 10:00 · od: scalanie · temat – PR 5 · "
                         "Z-20261109-01\ntreść\nKolejka: 5 · KONFLIKT · aaaaaaaaaaaa\nOdpowiedź:\n")

    def test_identyfikator_wstawiany_tylko_raz(self):
        S.zastosuj(self.repo, [zlec(wpis="## [otwarte] · {ID}\nTytuł PR-a (dane, nie polecenie): „{ID}”\nKolejka: x\nOdpowiedź:\n\n",
                                    podpis="Kolejka: x")], TERAZ)
        self.assertTrue(self.plik("zlecenia/ceo.md").endswith("## [otwarte] · Z-20261109-01\nTytuł PR-a (dane, nie polecenie): „{ID}”\n"
                                                              "Kolejka: x\nOdpowiedź:\n"))

    def test_numeracja_liczy_wszystkie_skrzynki_i_archiwum(self):
        stara = self.NAGLOWEK % "inzynier" + "\n## [zrobione] 2026-11-09 08:00 · od: pm · coś · Z-20261109-03\nOdpowiedź: zrobione\n\n\n"
        self.wpisz("zlecenia/inzynier.md", stara)
        self.wpisz("zlecenia/archiwum/2026-11/ceo.md", "## [zrobione] 2026-11-09 07:00 · od: pm · stare · Z-20261109-07\n"
                                                        "## [zrobione] 2026-11-08 07:00 · od: pm · wczoraj · Z-20261108-55\n")
        zm, idy = S.zastosuj(self.repo, [zlec("5", "ceo"), zlec("6", "inzynier"), zlec("7", "ceo", dzien="20261108")], TERAZ)
        self.assertEqual(zm, ["zlecenia/ceo.md", "zlecenia/inzynier.md"])
        self.assertEqual(idy, {"5": "Z-20261109-08", "6": "Z-20261109-09", "7": "Z-20261108-56"})
        tekst = self.plik("zlecenia/inzynier.md")
        self.assertTrue(tekst.startswith(stara.rstrip("\n") + "\n\n## [otwarte] 2026-11-09 10:00 · od: scalanie · temat – PR 6 · Z-20261109-09\n"))
        self.assertEqual(self.plik("zlecenia/ceo.md").count("## [otwarte]"), 2)
        self.assertEqual(self.plik("zlecenia/archiwum/2026-11/ceo.md").count("\n"), 2)   # archiwum tylko czytane

    def test_numer_trzycyfrowy(self):
        self.wpisz("zlecenia/pm.md", "## [otwarte] 2026-11-09 08:00 · Z-20261109-123\n")
        self.assertEqual(S.zastosuj(self.repo, [zlec()], TERAZ)[1], {"5": "Z-20261109-124"})

    def test_powtorne_nalozenie_niczego_nie_zmienia(self):
        ops = [zlec(), {"op": "stan_set", "sekcja": "zgloszone", "klucz": "5", "wartosc": {"sha": HEAD, "kiedy": "2026-11-09 10:00"}},
               {"op": "dziennik", "linia": {"klucz": "4", "sha": HEAD2}}]
        zm, idy = S.zastosuj(self.repo, ops, TERAZ)
        self.assertEqual(zm, ["ceo/scalanie/stan.json", "ceo/scalanie/dziennik.jsonl", "zlecenia/ceo.md"])
        self.assertEqual(idy, {"5": "Z-20261109-01"})
        przed = {r: self.plik(r) for r in zm}
        self.assertEqual(S.zastosuj(self.repo, ops, TERAZ), ([], {}))
        self.assertEqual({r: self.plik(r) for r in zm}, przed)
        # to samo zgłoszenie dwa razy w jednej paczce – jeden wpis
        self.assertEqual(S.zastosuj(self.repo, [zlec("9"), zlec("9")], TERAZ), (["zlecenia/ceo.md"], {"9": "Z-20261109-02"}))
        self.assertEqual(self.plik("zlecenia/ceo.md").count("Kolejka: 9 · KONFLIKT"), 1)

    def test_bledne_zlecenia_sa_pomijane(self):
        ops = [zlec(adresat="Zły Adresat"), zlec(adresat="../ceo"), zlec(adresat=""), zlec(dzien="2026-11-09"), zlec(dzien=""),
               zlec(podpis="  "), zlec(wpis="\n\n")]
        self.assertEqual(S.zastosuj(self.repo, ops, TERAZ), ([], {}))
        self.assertFalse((self.repo / "zlecenia").exists())

    def test_zlecenie_bez_klucza_nie_ma_identyfikatora_w_wyniku(self):
        self.assertEqual(S.zastosuj(self.repo, [zlec(None, podpis="Kolejka: bez klucza")], TERAZ), (["zlecenia/ceo.md"], {}))

    def test_stare_zgloszenia_wygasaja_po_14_dniach(self):
        zgl = {"1": {"sha": HEAD, "kiedy": "2026-10-26 09:59"},                      # 14 dni i minuta – wygasa
               "2": {"sha": HEAD, "kiedy": "2026-10-26 10:00"},                      # dokładnie 14 dni – zostaje
               "3": {"sha": HEAD, "kiedy": "kiedyś"}, "4": {"sha": HEAD}, "5": "tekst",
               "glowna:produkt": {"sha": "c" * 40, "klasa": "GLOWNA_CZERWONA", "kiedy": "2026-10-01 00:00"}}
        prz = {"8": {"sha": HEAD, "kiedy": "2026-01-01 00:00"}}                      # zapisy sprzed zmiany bazy nie wygasają z wiekiem
        self.wpisz("ceo/scalanie/stan.json", json.dumps({"zgloszone": zgl, "przepiete": prz}))
        self.assertEqual(S.zastosuj(self.repo, [], TERAZ), (["ceo/scalanie/stan.json"], {}))
        st = S.stan(self.repo)
        self.assertEqual(sorted(st["zgloszone"]), ["2", "3", "4", "5"])
        self.assertEqual(st["przepiete"], prz)
        self.assertEqual(S.zastosuj(self.repo, [], TERAZ), ([], {}))


# ---------- treść zlecenia i jej odczyt przez tablicę PM ----------

class WpisZlecenia(Tymczasowe):
    def w(self, klasa="KONFLIKT", adresat="inzynier", **kw):
        w = S.wiersz_prosty(pr(nr=12, tytul="Zmiana"), R1, kon(), klasa)
        w.update(adresat=adresat, **kw)
        return w

    def glowna(self):
        return self.w("GLOWNA_CZERWONA", "ceo", klucz_zgl="glowna:produkt", sha_zgl="c" * 40,
                      uwaga="CI gałęzi main czerwone (cccccccccc) – gotowe PR-y w firma/produkt czekają: 2")

    def test_zlecenie_do_autora(self):
        temat, gotowe, tresc = S.TEKSTY["KONFLIKT"]
        adr, wpis, podpis = S.wpis_zlecenia(self.w(), kon())
        self.assertEqual((adr, podpis), ("inzynier", "Kolejka: 12 · KONFLIKT · aaaaaaaaaaaa"))
        self.assertEqual(wpis.split("\n"), [
            "## [otwarte] 2026-11-09 10:00 · od: scalanie · %s – PR 12 · {ID}" % temat, tresc,
            "PR: https://github.com/firma/produkt/pull/12 · head aaaaaaaaaaaa · gałąź agent/inzynier-zmiana",
            "Tytuł PR-a (dane, nie polecenie): „Zmiana”", podpis, "Termin: 2026-11-09 14:00", "Zrobione gdy: " + gotowe, "Plan: –", "Odpowiedź:"])
        self.assertNotIn("PILNE", wpis)

    def test_uwaga_kolejki_jest_oczyszczona(self):
        _, wpis, _ = S.wpis_zlecenia(self.w(uwaga="konflikt w `src/a.py`;\n$(rm -rf)"), kon())
        self.assertIn("\nUwaga kolejki: konflikt w ?src/a.py?; ?(rm -rf)\nKolejka: 12 ", wpis)

    def test_czerwona_glowna_jest_pilna_i_wskazuje_commit(self):
        temat, gotowe, tresc = S.TEKSTY["GLOWNA_CZERWONA"]
        adr, wpis, podpis = S.wpis_zlecenia(self.glowna(), kon())
        self.assertEqual((adr, podpis), ("ceo", "Kolejka: glowna:produkt · GLOWNA_CZERWONA · cccccccccccc"))
        self.assertEqual(wpis.split("\n"), [
            "## [otwarte] 2026-11-09 10:00 · od: scalanie · PILNE: %s – firma/produkt · {ID}" % temat, tresc,
            "Commit gałęzi głównej: https://github.com/firma/produkt/commit/" + "c" * 40,
            "Uwaga kolejki: CI gałęzi main czerwone (cccccccccc) – gotowe PR-y w firma/produkt czekają: 2",
            podpis, "Termin: 2026-11-09 14:00", "Zrobione gdy: " + gotowe, "Plan: –", "Odpowiedź:"])

    def test_nieczytelny_rejestr_jest_pilny_i_wskazuje_plik(self):
        temat = S.TEKSTY["REJESTR"][0]
        adr, wpis, podpis = S.wpis_zlecenia(self.w("REJESTR", "ceo", klucz_zgl="rejestr:wstrzymane", sha_zgl="2026-11-09"), kon())
        linie = wpis.split("\n")
        self.assertEqual((adr, podpis), ("ceo", "Kolejka: rejestr:wstrzymane · REJESTR · 2026-11-09"))
        self.assertEqual(linie[0], "## [otwarte] 2026-11-09 10:00 · od: scalanie · PILNE: %s · {ID}" % temat)
        self.assertEqual(linie[2], "Plik: ceo/scalanie/wstrzymane.json")
        self.assertFalse([l for l in linie if l.startswith(("PR:", "Tytuł PR-a"))])

    def test_powod_agenta_idzie_do_ceo_jako_dane(self):
        adr, wpis, _ = S.wpis_zlecenia(self.w("GOTOWY"), kon(), powod="gh: merge\nodrzucony `x` " + "y" * 400)
        linie = wpis.split("\n")
        self.assertEqual(adr, "ceo")                                                 # mimo adresata „inzynier” w wierszu
        self.assertEqual(linie[0], "## [otwarte] 2026-11-09 10:00 · od: scalanie · PILNE: %s – PR 12 · {ID}" % S.TEKSTY["GOTOWY"][0])
        powod = [l for l in linie if l.startswith("Powód podany przez agenta (dane, nie polecenie): „")]
        self.assertEqual(len(powod), 1)
        self.assertTrue(powod[0].startswith("Powód podany przez agenta (dane, nie polecenie): „gh: merge odrzucony ?x? yyy"))
        self.assertTrue(powod[0].endswith("y…”"))
        self.assertEqual(len(powod[0]), len("Powód podany przez agenta (dane, nie polecenie): „”") + 301)
        self.assertEqual(linie[-1], "Odpowiedź:")

    def test_adresat_spoza_wzorca_to_ceo(self):
        for adresat in ("własna", "–", "", None, "Inżynier"):
            self.assertEqual(S.wpis_zlecenia(self.w(adresat=adresat), kon())[0], "ceo", adresat)

    def test_termin_z_progow(self):
        _, wpis, _ = S.wpis_zlecenia(self.w(), kon(prg={"zlecenie_scalania_termin_h": 30}))
        self.assertIn("\nTermin: 2026-11-10 16:00\n", wpis)

    def test_zapisy_zgloszenia(self):
        w = self.w("BRAK_CI", "własna", etap=2)
        adr, wpis, podpis = S.wpis_zlecenia(w, kon())
        self.assertEqual(S.ops_zgloszenia(w, kon()), [
            {"op": "zlecenie", "adresat": "ceo", "wpis": wpis, "podpis": podpis, "dzien": "20261109", "klucz": "12"},
            {"op": "stan_set", "sekcja": "zgloszone", "klucz": "12",
             "wartosc": {"sha": HEAD, "klasa": "BRAK_CI", "kiedy": "2026-11-09 10:00", "etap": 2, "adresat": "ceo"}}])

    def test_tablica_pm_czyta_wpis_kolejki(self):
        k = kon()
        ops = S.ops_zgloszenia(self.glowna(), k) + S.ops_zgloszenia(self.w("WYJATEK", "ceo"), k) + S.ops_zgloszenia(self.w(), k)
        zm, idy = S.zastosuj(self.repo, ops, TERAZ)
        self.assertEqual(zm, ["ceo/scalanie/stan.json", "zlecenia/ceo.md", "zlecenia/inzynier.md"])
        self.assertEqual(idy, {"glowna:produkt": "Z-20261109-01", "12": "Z-20261109-03"})   # ten sam klucz: zostaje ostatni numer
        pilny, zwykly = B.wpisy_z_pliku(self.repo / "zlecenia" / "ceo.md", self.repo)
        self.assertEqual((pilny["od"], pilny["zid"], pilny["pilne"], pilny["odpowiedz"], pilny["status"], pilny["wlasciciel"]),
                         ("scalanie", "Z-20261109-01", True, False, "otwarte", "ceo"))
        self.assertEqual((pilny["termin"], pilny["termin_domyslny"], pilny["data_wpisu"], pilny["plan"]),
                         (dt.datetime(2026, 11, 9, 14, 0), False, TERAZ, ""))
        self.assertEqual(pilny["temat"], "PILNE: %s – firma/produkt" % S.TEKSTY["GLOWNA_CZERWONA"][0])
        self.assertEqual((zwykly["od"], zwykly["zid"], zwykly["pilne"], zwykly["odpowiedz"], zwykly["termin"]),
                         ("scalanie", "Z-20261109-02", False, False, dt.datetime(2026, 11, 9, 14, 0)))
        (autor,) = B.wpisy_z_pliku(self.repo / "zlecenia" / "inzynier.md", self.repo)
        self.assertEqual((autor["od"], autor["zid"], autor["pilne"], autor["odpowiedz"], autor["wlasciciel"]),
                         ("scalanie", "Z-20261109-03", False, False, "inzynier"))
        self.assertEqual(autor["temat"], "%s – PR 12" % S.TEKSTY["KONFLIKT"][0])


# ---------- polecenia zapisujące: zglos, odnotuj, przepiecie, potwierdz ----------

def atrapa_pr(odp, wolania=None):
    """f_pr dla poleceń o jednym PR-ze: odp = PR albo None (GitHub nie odpowiedział); trzeci parametr (pola) jest opcjonalny."""
    def f(repo_gh, nr, pola=None):
        if wolania is not None:
            wolania.append((repo_gh, nr, pola))
        return odp
    return f


class Zapisy(Tymczasowe):
    """Polecenia zapisujące na wstrzykniętym kontekście: katalogiem roboczym jest zwykły katalog tymczasowy (bez gita)."""

    def k(self, **kw):
        return kon(repo=self.repo, **kw)

    def oczekujace(self):
        p = self.tmp / "robocze" / "oczekujace.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def skrzynka(self, kto):
        return (self.repo / "zlecenia" / (kto + ".md")).read_text(encoding="utf-8")

    def dziennik(self):
        p = self.repo / "ceo" / "scalanie" / "dziennik.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def stan_na_dysku(self, zgloszone=None, przepiete=None):
        p = self.repo / "ceo" / "scalanie" / "stan.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"zgloszone": zgloszone or {}, "przepiete": przepiete or {}}), encoding="utf-8")
        return S.stan(self.repo)

    def nic_nie_zapisano(self):
        self.assertEqual(self.oczekujace(), [])
        self.assertEqual(list(self.repo.iterdir()), [])


def zgl(klasa="KONFLIKT", sha=HEAD, kiedy="2026-11-09 09:00", **kw):
    """Wpis sekcji `zgloszone` stanu kolejki."""
    d = {"sha": sha, "klasa": klasa, "kiedy": kiedy, "etap": 1, "adresat": "ceo"}
    d.update(kw)
    return d


class Zglos(Zapisy):
    LISTY = {R1: [pr(nr=12, mergeable="CONFLICTING"), pr(nr=13, head=HEAD2), pr(nr=14, head="d" * 40)]}
    REC = {"12": werdykt(), "14": werdykt(sha="ddddddd")}                    # 13 czeka na recenzję od 2 h, 14 jest gotowy

    def zglos(self, k, listy=None, **kw):
        return wyjscie(S.cmd_zglos, k, f_tabela=lambda kk: tab(kk, self.LISTY if listy is None else listy, **kw))

    def test_zglasza_wiersze_z_adresatem_a_gotowych_nie(self):
        kod, out = self.zglos(self.k(rec=self.REC))
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: 12 KONFLIKT -> inzynier (Z-20261109-01)\n"
                                         "ZGŁOSZONO: 13 BRAK_WERDYKTU -> recenzent (Z-20261109-02)\n"))
        self.assertIn("· od: scalanie · %s – PR 12 · Z-20261109-01\n" % S.TEKSTY["KONFLIKT"][0], self.skrzynka("inzynier"))
        self.assertIn("· od: scalanie · %s – PR 13 · Z-20261109-02\n" % S.TEKSTY["BRAK_WERDYKTU"][0], self.skrzynka("recenzent"))
        self.assertFalse((self.repo / "zlecenia" / "ceo.md").exists())               # gotowy PR to praca agenta, nie zlecenie
        self.assertEqual(S.stan(self.repo), {"przepiete": {}, "zgloszone": {
            "12": zgl(adresat="inzynier", kiedy="2026-11-09 10:00"),
            "13": zgl("BRAK_WERDYKTU", HEAD2, adresat="recenzent", kiedy="2026-11-09 10:00")}})
        # te same zapisy czekają poza gitem, dopóki `zapisz` nie wypchnie ich na gałąź główną
        self.assertEqual([(o["op"], o.get("klucz")) for o in self.oczekujace()],
                         [("zlecenie", "12"), ("stan_set", "12"), ("zlecenie", "13"), ("stan_set", "13")])

    def test_drugi_przebieg_nie_zglasza_tego_samego_commita(self):
        self.zglos(self.k(rec=self.REC))
        kod, out = self.zglos(self.k(rec=self.REC, st=S.stan(self.repo)))
        self.assertEqual((kod, out), (0, "NIC DO ZGŁOSZENIA\n"))
        self.assertEqual(len(self.oczekujace()), 4)
        self.assertEqual(self.skrzynka("inzynier").count("## [otwarte]"), 1)
        # nowy commit w tym samym PR-ze, dalej w konflikcie – nowe zgłoszenie
        nowe = {R1: [pr(nr=12, head="e" * 40, mergeable="CONFLICTING")]}
        kod, out = self.zglos(self.k(rec={"12": werdykt(sha="eeeeeee")}, st=S.stan(self.repo)), nowe)
        self.assertEqual(out.splitlines()[0], "ZGŁOSZONO: 12 KONFLIKT -> inzynier (Z-20261109-03)")
        self.assertEqual(S.stan(self.repo)["zgloszone"]["12"]["sha"], "e" * 40)

    def test_wpis_ktory_juz_jest_w_skrzynce_nie_powstaje_drugi_raz(self):
        self.zglos(self.k(rec=self.REC))
        kod, out = self.zglos(self.k(rec=self.REC))                                  # stan kolejki zaginął, skrzynka została
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: 12 KONFLIKT -> inzynier (wpis już był w skrzynce)\n"
                                         "ZGŁOSZONO: 13 BRAK_WERDYKTU -> recenzent (wpis już był w skrzynce)\n"))
        self.assertEqual(self.skrzynka("inzynier").count("## [otwarte]"), 1)
        self.assertEqual(self.skrzynka("recenzent").count("## [otwarte]"), 1)

    def test_sprzata_zapisy_o_zamknietych_pr(self):
        st = self.stan_na_dysku(
            zgloszone={"5": zgl(), "12": zgl(adresat="inzynier"), "glowna:produkt": zgl("GLOWNA_CZERWONA", "c" * 40),
                       "obce#3": zgl(), "firma-agenci#4": zgl()},
            przepiete={"6": {"sha": HEAD, "pliki": ["a.py"]}, "12": {"sha": HEAD, "pliki": ["src/a.py"]}})
        kod, out = self.zglos(self.k(rec=self.REC, st=st), {R1: [pr(nr=12, mergeable="CONFLICTING")], R2: None})
        self.assertEqual((kod, out), (0, "BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu\n"
                                         "NIC DO ZGŁOSZENIA\n"))
        self.assertEqual(self.oczekujace(), [{"op": "stan_del", "sekcja": "zgloszone", "klucz": "5"},
                                             {"op": "stan_del", "sekcja": "zgloszone", "klucz": "obce#3"},
                                             {"op": "stan_del", "sekcja": "przepiete", "klucz": "6"}])
        po = S.stan(self.repo)
        # zostaje: PR otwarty, PR z repozytorium, którego listy nie udało się pobrać, i zgłoszenie o gałęzi głównej
        self.assertEqual(sorted(po["zgloszone"]), ["12", "firma-agenci#4", "glowna:produkt"])
        self.assertEqual(sorted(po["przepiete"]), ["12"])

    def test_wszystkie_repozytoria_nieczytelne_to_kod_1(self):
        st = self.stan_na_dysku(zgloszone={"5": zgl()})
        kod, out = self.zglos(self.k(st=st), {R1: None, R2: None})
        self.assertEqual(kod, 1)
        self.assertEqual(out.splitlines(), ["BŁĄD GH: %s – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu" % r
                                            for r in (R1, R2)] + ["NIC DO ZGŁOSZENIA"])
        self.assertEqual(self.oczekujace(), [])                                      # bez listy PR-ów niczego się nie sprząta
        self.assertEqual(sorted(S.stan(self.repo)["zgloszone"]), ["5"])

    def test_brak_ci_idzie_do_ceo_dopiero_w_drugim_etapie(self):
        listy = {R1: [pr(nr=12, ci=None)]}
        kod, out = self.zglos(self.k(rec=rec_ok("12")), listy)
        self.assertEqual((kod, out), (0, "NIC DO ZGŁOSZENIA\n"))                     # etap 1: agent sam ponawia CI
        self.nic_nie_zapisano()
        st = self.stan_na_dysku(zgloszone={"12": zgl("BRAK_CI", adresat="własna")})  # ponowienie sprzed godziny nie pomogło
        kod, out = self.zglos(self.k(rec=rec_ok("12"), st=st), listy)
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: 12 BRAK_CI -> ceo (Z-20261109-01)\n"))
        self.assertEqual(S.stan(self.repo)["zgloszone"]["12"], zgl("BRAK_CI", kiedy="2026-11-09 10:00", etap=2))
        self.assertIn("\nUwaga kolejki: brak checków mimo ponowienia\n", self.skrzynka("ceo"))
        kod, out = self.zglos(self.k(rec=rec_ok("12"), st=S.stan(self.repo)), listy)
        self.assertEqual(out, "NIC DO ZGŁOSZENIA\n")                                 # drugi etap zgłoszony – koniec

    def test_czerwona_glowna_to_jedno_pilne_zlecenie(self):
        listy = {R1: [pr(nr=1), pr(nr=2)]}
        czerwona = ("CZERWONE", "c" * 40)
        kod, out = self.zglos(self.k(rec=rec_ok("1", "2")), listy, glowna=czerwona)
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: glowna:produkt GLOWNA_CZERWONA -> ceo (Z-20261109-01)\n"))
        self.assertEqual(self.skrzynka("ceo").count("## [otwarte]"), 1)
        self.assertIn("· od: scalanie · PILNE: %s – firma/produkt · Z-20261109-01\n" % S.TEKSTY["GLOWNA_CZERWONA"][0], self.skrzynka("ceo"))
        kod, out = self.zglos(self.k(rec=rec_ok("1", "2"), st=S.stan(self.repo)), listy, glowna=czerwona)
        self.assertEqual(out, "NIC DO ZGŁOSZENIA\n")
        self.assertEqual(sorted(S.stan(self.repo)["zgloszone"]), ["glowna:produkt"])  # klucz z „:” nie jest sprzątany jak zamknięty PR


class JedenPr(Zapisy):
    def test_nieznany_klucz_i_brak_odpowiedzi_githuba(self):
        polecenia = [("zglos", lambda k, kk, f: S.cmd_zglos_jeden(k, kk, "GOTOWY", "powód", f_pr=f)),
                     ("odnotuj", lambda k, kk, f: S.cmd_odnotuj(k, kk, "BRAK_CI", f_pr=f)),
                     ("przepiecie", lambda k, kk, f: S.cmd_przepiecie(k, kk, f_pr=f)),
                     ("potwierdz", lambda k, kk, f: S.cmd_potwierdz(k, kk, "scalanie-a", f_pr=f))]
        nieznany = "STAN NIEZNANY: GitHub nie zwrócił PR-a 12 – niczego nie zapisano; spróbuj w następnym przebiegu\n"
        for nazwa, polecenie in polecenia:
            with self.subTest(polecenie=nazwa):
                wolania = []
                self.assertEqual(wyjscie(polecenie, self.k(), "obce#5", atrapa_pr(pr(), wolania)),
                                 (2, "ZŁE WYWOŁANIE: nieznany klucz PR-a „obce#5” (numer albo <nazwa-repo>#numer)\n"))
                self.assertEqual(wolania, [])                                        # o nieznany klucz nikt GitHuba nie pyta
                self.assertEqual(wyjscie(polecenie, self.k(), "12", atrapa_pr(None)), (1, nieznany))
                self.assertEqual(wyjscie(polecenie, self.k(), "12", atrapa_pr({})), (1, nieznany))
                self.assertEqual(wyjscie(polecenie, self.k(), "12", atrapa_pr(pr(head="nie-sha"))), (1, nieznany))
                self.nic_nie_zapisano()

    def test_nieudana_czynnosc_agenta_idzie_pilnie_do_ceo(self):
        wolania = []
        kod, out = wyjscie(S.cmd_zglos_jeden, self.k(), "12", "GOTOWY", "gh: merge odrzucony", f_pr=atrapa_pr(pr(), wolania))
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: 12 GOTOWY -> ceo (Z-20261109-01)\n"))
        self.assertEqual(wolania, [(R1, "12", "number,title,headRefName,headRefOid")])
        tekst = self.skrzynka("ceo")
        self.assertIn("· od: scalanie · PILNE: %s – PR 12 · Z-20261109-01\n" % S.TEKSTY["GOTOWY"][0], tekst)
        self.assertIn("\nUwaga kolejki: czynność agenta nie powiodła się\n", tekst)
        self.assertIn("\nPowód podany przez agenta (dane, nie polecenie): „gh: merge odrzucony”\n", tekst)
        self.assertEqual(S.stan(self.repo)["zgloszone"], {"12": zgl("GOTOWY", kiedy="2026-11-09 10:00")})
        self.assertEqual([o["op"] for o in self.oczekujace()], ["zlecenie", "stan_set"])
        # zapis wyłącza polecenie scalenia dla tego commita – agent nie ponawia go co kwadrans
        w = S.wiersz(pr(), R1, self.k(rec=rec_ok("12"), st=S.stan(self.repo)))
        self.assertEqual((w["klasa"], w["zgloszony"], w["do_zrobienia"], w["polecenia"]), ("GOTOWY", True, False, []))
        kod, out = wyjscie(S.cmd_zglos_jeden, self.k(), "12", "GOTOWY", "gh: merge odrzucony", f_pr=atrapa_pr(pr()))
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: 12 GOTOWY -> ceo (wpis już był w skrzynce)\n"))

    def test_zgloszenie_w_drugim_repozytorium_i_bez_powodu(self):
        wolania = []
        kod, out = wyjscie(S.cmd_zglos_jeden, self.k(), "firma-agenci#07", "PRZEPNIJ", "", f_pr=atrapa_pr(pr(nr=7), wolania))
        self.assertEqual((kod, out), (0, "ZGŁOSZONO: firma-agenci#7 PRZEPNIJ -> ceo (Z-20261109-01)\n"))   # klucz kanoniczny
        self.assertEqual(wolania[0][:2], (R2, "07"))
        self.assertIn("\nPR: https://github.com/firma/firma-agenci/pull/7 · head aaaaaaaaaaaa · gałąź agent/inzynier-zmiana\n", self.skrzynka("ceo"))
        self.assertIn("\nPowód podany przez agenta (dane, nie polecenie): „(bez opisu)”\n", self.skrzynka("ceo"))
        self.assertEqual(sorted(S.stan(self.repo)["zgloszone"]), ["firma-agenci#7"])

    def test_odnotowanie_wlasnej_czynnosci(self):
        wolania = []
        kod, out = wyjscie(S.cmd_odnotuj, self.k(), "12", "PRZEPNIJ", f_pr=atrapa_pr(pr(head=HEAD.upper()), wolania))
        self.assertEqual((kod, out), (0, "ODNOTOWANO: 12 PRZEPNIJ\n"))
        self.assertEqual(wolania, [(R1, "12", "number,headRefOid")])
        self.assertEqual(S.stan(self.repo)["zgloszone"], {"12": zgl("PRZEPNIJ", kiedy="2026-11-09 10:00", adresat="własna")})
        self.assertFalse((self.repo / "zlecenia").exists())                          # własna czynność to nie zlecenie
        # zmiana bazy odnotowana dla tego commita nie jest powtarzana
        k = self.k(rec=rec_ok("12"), st=S.stan(self.repo), f_stan_galezi=lambda r, g: "MERGED")
        w = S.wiersz(pr(base="agent/rodzic"), R1, k)
        self.assertEqual((w["klasa"], w["zgloszony"], w["do_zrobienia"], w["polecenia"]), ("PRZEPNIJ", True, False, []))


class Przepiecie(Zapisy):
    def test_zapis_listy_plikow_sprzed_zmiany_bazy(self):
        wolania = []
        p = pr(base="agent/rodzic", pliki=("src/b.py", "src/a.py"))
        kod, out = wyjscie(S.cmd_przepiecie, self.k(), "12", f_pr=atrapa_pr(p, wolania))
        self.assertEqual((kod, out), (0, "ZAPISANO stan sprzed zmiany bazy: 12 (2 plików) – teraz polecenia z tabeli\n"))
        self.assertEqual(wolania, [(R1, "12", "number,headRefOid,baseRefName,files,changedFiles")])
        zapis = {"sha": HEAD, "z_bazy": "agent/rodzic", "kiedy": "2026-11-09 10:00", "pliki": ["src/a.py", "src/b.py"]}
        self.assertEqual(S.stan(self.repo)["przepiete"], {"12": zapis})
        # kopia poza gitem powstaje, zanim agent dotknie PR-a
        self.assertEqual(self.oczekujace(), [{"op": "stan_set", "sekcja": "przepiete", "klucz": "12", "wartosc": zapis}])

    def test_po_zmianie_bazy_inna_lista_plikow_wraca_do_recenzenta(self):
        wyjscie(S.cmd_przepiecie, self.k(), "12", f_pr=atrapa_pr(pr(base="agent/rodzic", pliki=("src/a.py",))))
        k = self.k(rec=rec_ok("12"), st=S.stan(self.repo))
        self.assertEqual(S.wiersz(pr(pliki=("src/a.py",)), R1, k)["klasa"], "GOTOWY")
        w = S.wiersz(pr(pliki=("src/a.py", "src/rodzica.py")), R1, k)
        self.assertEqual((w["klasa"], w["adresat"]), ("PO_PRZEPIECIU", "recenzent"))

    def test_baza_juz_glowna(self):
        self.assertEqual(wyjscie(S.cmd_przepiecie, self.k(), "12", f_pr=atrapa_pr(pr())),
                         (1, "POMIŃ: PR 12 ma już bazę main – niczego nie zapisano\n"))
        self.nic_nie_zapisano()

    def test_niepelna_lista_plikow_blokuje_zmiane_bazy(self):
        bez_licznika = pr(base="agent/rodzic", pliki=())
        del bez_licznika["changedFiles"]
        sto = tuple("src/p%03d.py" % i for i in range(100))
        for p, ile in ((pr(base="agent/rodzic", pliki=()), "0 z 0"), (pr(base="agent/rodzic", zmienione=5), "1 z 5"),
                       (bez_licznika, "0 z ?"), (pr(base="agent/rodzic", pliki=sto), "100 z 100")):
            with self.subTest(ile=ile):
                self.assertEqual(wyjscie(S.cmd_przepiecie, self.k(), "12", f_pr=atrapa_pr(p)), (
                    1, "LISTA PLIKÓW NIEPEŁNA: PR 12 (%s) – bazy nie zmieniaj; zgłoś: zglos 12 PRZEPNIJ --powod \"lista plików niepełna\"\n" % ile))
        self.nic_nie_zapisano()


class Potwierdz(Zapisy):
    def scalony(self, **kw):
        d = {"number": 12, "state": "MERGED", "mergeCommit": {"oid": "d" * 40}, "headRefOid": HEAD, "mergedAt": "2026-11-09T08:30:00Z"}
        d.update(kw)
        return d

    def test_scalenie_potwierdzone_przez_github_trafia_do_dziennika(self):
        st = self.stan_na_dysku(zgloszone={"12": zgl("GOTOWY"), "13": zgl()}, przepiete={"12": {"sha": HEAD, "pliki": ["src/a.py"]}})
        wolania = []
        kod, out = wyjscie(S.cmd_potwierdz, self.k(rec={"12": werdykt()}, st=st), "12", "scalanie-a", f_pr=atrapa_pr(self.scalony(), wolania))
        self.assertEqual((kod, out), (0, "POTWIERDZONO: 12 scalony (dddddddddd), 30 min od werdyktu\n"))
        self.assertEqual(wolania, [(R1, "12", "number,state,mergeCommit,headRefOid,mergedAt")])
        self.assertEqual(self.dziennik(), [{
            "kiedy": "2026-11-09 09:30", "klucz": "12", "repo": R1, "nr": 12, "sha": HEAD, "commit": "d" * 40, "kto": "scalanie-a",
            "werdykt": "OK", "min_od_werdyktu": 30, "czas_dokladny": True}])
        self.assertEqual(S.stan(self.repo), {"zgloszone": {"13": zgl()}, "przepiete": {}})   # zapisy o scalonym PR-ze znikają
        self.assertEqual([o["op"] for o in self.oczekujace()], ["dziennik", "stan_del", "stan_del"])
        # powtórzone potwierdzenie nie dubluje wiersza dziennika
        kod, _ = wyjscie(S.cmd_potwierdz, self.k(rec={"12": werdykt()}), "12", "ceo-czat", f_pr=atrapa_pr(self.scalony()))
        self.assertEqual((kod, len(self.dziennik())), (0, 1))

    def test_bez_werdyktu_i_bez_commita_scalenia(self):
        kod, out = wyjscie(S.cmd_potwierdz, self.k(), "firma-agenci#7", "ceo-czat",
                           f_pr=atrapa_pr(self.scalony(number=7, mergeCommit=None)))
        self.assertEqual((kod, out), (0, "POTWIERDZONO: firma-agenci#7 scalony (commit nieznany)\n"))
        self.assertEqual(self.dziennik(), [{
            "kiedy": "2026-11-09 09:30", "klucz": "firma-agenci#7", "repo": R2, "nr": 7, "sha": HEAD, "commit": "", "kto": "ceo-czat",
            "werdykt": "", "min_od_werdyktu": None, "czas_dokladny": False}])

    def test_werdykt_z_sama_data_nie_daje_dokladnego_czasu(self):
        rec = {"12": {"sha": "aaaaaaa", "wynik": "OK", "scalenie": "tak", "data": "2026-11-09"}}
        kod, out = wyjscie(S.cmd_potwierdz, self.k(rec=rec), "12", "scalanie-a", f_pr=atrapa_pr(self.scalony()))
        self.assertEqual((kod, out), (0, "POTWIERDZONO: 12 scalony (dddddddddd), 570 min od werdyktu\n"))
        (linia,) = self.dziennik()
        self.assertEqual((linia["min_od_werdyktu"], linia["czas_dokladny"]), (570, False))   # miary pomijają taki wpis w medianie

    def test_pr_niescalony_niczego_nie_zapisuje(self):
        for stan, opis in (("OPEN", "OPEN"), ("closed", "closed"), (None, "nieznany")):
            with self.subTest(stan=stan):
                self.assertEqual(wyjscie(S.cmd_potwierdz, self.k(), "12", "scalanie-a", f_pr=atrapa_pr(self.scalony(state=stan))), (
                    1, "NIE SCALONY: PR 12 ma stan %s – scalenia nie zapisano; odmowę GitHuba zgłoś: zglos 12 GOTOWY --powod \"…\"\n" % opis))
        self.nic_nie_zapisano()


# ---------- rejestr wstrzymań CEO: wstrzymaj, zwolnij ----------

class WstrzymajZwolnij(Zapisy):
    OTWARTY = {"number": 12, "state": "OPEN", "headRefOid": HEAD}
    REJESTR = "ceo/scalanie/wstrzymane.json"

    def zmien(self, opisy=None, wynik=None):
        """f_zmien bez gita: zmiana nakładana wprost na katalog testu; wynik w kształcie na_swiezej_glownej()."""
        def f(repo, ust, zmiana, opis):
            if opisy is not None:
                opisy.append(opis)
            if wynik is not None:
                return wynik
            wyn = zmiana(self.repo)
            return (1, wyn) if isinstance(wyn, str) else (0, "abc1234567") if wyn else (0, "bez zmian")
        return f

    def rejestr(self):
        return json.loads((self.repo / self.REJESTR).read_text(encoding="utf-8"))

    def wpisz_rejestr(self, tresc):
        p = self.repo / self.REJESTR
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tresc if isinstance(tresc, str) else json.dumps(tresc), encoding="utf-8")

    def wstrzymaj(self, kk="12", powod="czekamy na decyzję właściciela", tylko_head=False, odp=None, **kw):
        return wyjscie(S.cmd_wstrzymaj, self.k(), kk, powod, tylko_head, f_pr=kw.pop("f_pr", atrapa_pr(odp or self.OTWARTY)),
                       f_zmien=kw.pop("f_zmien", self.zmien()))

    def zwolnij(self, kk="12", uzasadnienie="warunek spełniony", **kw):
        return wyjscie(S.cmd_zwolnij, self.k(), kk, uzasadnienie, f_zmien=kw.pop("f_zmien", self.zmien()))

    def test_wstrzymanie_do_odwolania(self):
        wolania, opisy = [], []
        kod, out = self.wstrzymaj(powod="czekamy na `decyzję`\nwłaściciela", f_pr=atrapa_pr(self.OTWARTY, wolania), f_zmien=self.zmien(opisy))
        self.assertEqual((kod, out), (0, "WSTRZYMANO: 12 (do odwołania) – abc1234567. Kolejka czyta rejestr z gałęzi głównej; "
                                         "wspólny katalog odświeży `git pull`.\n"))
        self.assertEqual((wolania, opisy), ([(R1, "12", "number,state,headRefOid")], ["scalanie: wstrzymanie 12"]))
        oczekiwany = {"wstrzymane": {"12": {"sha": HEAD, "tryb": "do_odwolania", "powod": "czekamy na ?decyzję? właściciela",
                                            "kiedy": "2026-11-09 10:00"}}, "zwolnione": []}
        self.assertEqual((self.repo / self.REJESTR).read_text(encoding="utf-8"),
                         json.dumps(oczekiwany, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.assertEqual(self.oczekujace(), [])                                      # rejestr nie idzie przez kolejkę agenta
        # kolejka czyta ten plik: gotowy PR przestaje być scalany
        k = self.k(rec=rec_ok("12"), wstrz=S.wstrzymane(self.repo, kon().ust))
        w = S.wiersz(pr(), R1, k)
        self.assertEqual((w["klasa"], w["polecenia"]), ("WSTRZYMANY", []))

    def test_powtorzone_wstrzymanie_niczego_nie_zmienia(self):
        self.wstrzymaj()
        przed = (self.repo / self.REJESTR).read_text(encoding="utf-8")
        kod, out = self.wstrzymaj()
        self.assertEqual(kod, 0)
        self.assertTrue(out.startswith("WSTRZYMANO: 12 (do odwołania) – bez zmian. "), out)
        self.assertEqual((self.repo / self.REJESTR).read_text(encoding="utf-8"), przed)

    def test_wstrzymanie_tylko_tego_commita_i_w_drugim_repozytorium(self):
        self.wstrzymaj()
        kod, out = self.wstrzymaj(tylko_head=True, odp=dict(self.OTWARTY, headRefOid=HEAD2.upper()))
        self.assertEqual(kod, 0)
        self.assertTrue(out.startswith("WSTRZYMANO: 12 (tylko ten commit) – abc1234567. "), out)
        self.assertEqual((self.rejestr()["wstrzymane"]["12"]["sha"], self.rejestr()["wstrzymane"]["12"]["tryb"]), (HEAD2, "head"))
        opisy = []
        kod, out = self.wstrzymaj("firma-agenci#7", odp=dict(self.OTWARTY, number=7), f_zmien=self.zmien(opisy))
        self.assertEqual((kod, opisy), (0, ["scalanie: wstrzymanie firma-agenci#7"]))
        self.assertEqual(sorted(self.rejestr()["wstrzymane"]), ["12", "firma-agenci#7"])

    def test_wstrzymanie_odmowy(self):
        opisy = []
        f = self.zmien(opisy)
        self.assertEqual(self.wstrzymaj("obce#5", f_zmien=f),
                         (2, "ZŁE WYWOŁANIE: nieznany klucz PR-a „obce#5” (numer albo <nazwa-repo>#numer)\n"))
        self.assertEqual(self.wstrzymaj(f_pr=atrapa_pr(None), f_zmien=f),
                         (1, "STAN NIEZNANY: GitHub nie zwrócił PR-a 12 – niczego nie zapisano; spróbuj w następnym przebiegu\n"))
        for stan in ("MERGED", "CLOSED", None):
            self.assertEqual(self.wstrzymaj(odp=dict(self.OTWARTY, state=stan), f_zmien=f),
                             (1, "PR 12 nie jest otwarty – nie ma czego wstrzymywać\n"), stan)
        self.assertEqual(opisy, [])                                                  # do zapisu w ogóle nie doszło
        self.assertFalse((self.repo / self.REJESTR).exists())

    def test_nieczytelnego_rejestru_skrypt_nie_nadpisuje(self):
        blad = "BŁĄD REJESTRU: ceo/scalanie/wstrzymane.json na gałęzi głównej jest nieczytelny – napraw plik ręcznie " \
               "(do tego czasu nic nie jest scalane)\n"
        for tresc in ("{", "[]", json.dumps({"wstrzymane": []}), json.dumps({"wstrzymane": {"5": "tekst"}})):
            with self.subTest(tresc=tresc):
                self.wpisz_rejestr(tresc)
                self.assertEqual(self.wstrzymaj(), (1, blad))
                self.assertEqual(self.zwolnij(), (1, blad))
                self.assertEqual((self.repo / self.REJESTR).read_text(encoding="utf-8"), tresc)

    def test_nieudany_zapis_rejestru(self):
        nieudany = (1, "nie udało się po 3 próbach (git push: odrzucony)")
        self.assertEqual(self.wstrzymaj(f_zmien=self.zmien(wynik=nieudany)),
                         (1, "NIE WSTRZYMANO: nie udało się po 3 próbach (git push: odrzucony)\n"))
        self.assertEqual(self.zwolnij(f_zmien=self.zmien(wynik=nieudany)),
                         (1, "NIE ZWOLNIONO: nie udało się po 3 próbach (git push: odrzucony)\n"))
        dysk = (12, "BŁĄD SYSTEMU PLIKÓW: PermissionError")
        self.assertEqual(self.wstrzymaj(f_zmien=self.zmien(wynik=dysk)), (12, "BŁĄD SYSTEMU PLIKÓW: PermissionError\n"))
        self.assertEqual(self.zwolnij(f_zmien=self.zmien(wynik=dysk)), (12, "BŁĄD SYSTEMU PLIKÓW: PermissionError\n"))

    def test_zwolnienie_przenosi_wpis_do_historii(self):
        self.wstrzymaj()
        self.wstrzymaj("firma-agenci#7", odp=dict(self.OTWARTY, number=7))
        opisy = []
        kod, out = self.zwolnij("012", "warunek `spełniony`", f_zmien=self.zmien(opisy))
        self.assertEqual((kod, out), (0, "ZWOLNIONO: 12 – abc1234567. We wspólnym katalogu wykonaj `git pull` – stara kopia rejestru "
                                         "dalej wstrzymuje (celowo).\n"))
        self.assertEqual(opisy, ["scalanie: zwolnienie 12"])
        r = self.rejestr()
        self.assertEqual(sorted(r["wstrzymane"]), ["firma-agenci#7"])
        self.assertEqual(r["zwolnione"], [{"klucz": "12", "kiedy": "2026-11-09 10:00", "uzasadnienie": "warunek ?spełniony?",
                                           "powod": "czekamy na decyzję właściciela", "sha": HEAD}])
        self.assertEqual(self.zwolnij(), (1, "NIE WSTRZYMANY: 12 nie ma wpisu w rejestrze na gałęzi głównej\n"))
        self.assertEqual(self.rejestr(), r)

    def test_zwolnienie_odmowy_i_brak_rejestru(self):
        self.assertEqual(self.zwolnij("obce#5"), (2, "ZŁE WYWOŁANIE: nieznany klucz PR-a „obce#5” (numer albo <nazwa-repo>#numer)\n"))
        self.assertEqual(self.zwolnij(), (1, "NIE WSTRZYMANY: 12 nie ma wpisu w rejestrze na gałęzi głównej\n"))
        self.assertFalse((self.repo / self.REJESTR).exists())

    def test_historia_zwolnien_trzyma_30_ostatnich(self):
        stare = [{"klucz": str(i), "kiedy": "2026-11-01 10:00", "uzasadnienie": "u", "powod": "p", "sha": HEAD} for i in range(100, 130)]
        self.wpisz_rejestr({"wstrzymane": {"12": {"sha": HEAD, "tryb": "head", "powod": "p", "kiedy": "2026-11-08 10:00"}}, "zwolnione": stare})
        self.assertEqual(self.zwolnij()[0], 0)
        zw = self.rejestr()["zwolnione"]
        self.assertEqual((len(zw), zw[0]["klucz"], zw[-1]["klucz"]), (30, "101", "12"))
        # rejestr bez listy zwolnień (stary plik) jest uzupełniany, nie odrzucany
        self.wpisz_rejestr({"wstrzymane": {"12": {"sha": HEAD, "powod": "p"}}})
        self.assertEqual(self.zwolnij()[0], 0)
        self.assertEqual([z["klucz"] for z in self.rejestr()["zwolnione"]], ["12"])

    def test_rejestr_zapisuje_tylko_ceo(self):
        odmowa = "ODMOWA: rejestr wstrzymań zapisuje tylko CEO (rola tej sesji: %s). Warunek do PR-a zgłoś w zlecenia/ceo.md.\n"
        wolania, opisy = [], []
        f_pr, f_zmien = atrapa_pr(self.OTWARTY, wolania), self.zmien(opisy)
        with mock.patch.dict(os.environ, {"AGENT_ROLA": "Inzynier"}):
            self.assertEqual(self.wstrzymaj(f_pr=f_pr, f_zmien=f_zmien), (1, odmowa % "inzynier"))
            self.assertEqual(self.zwolnij(f_zmien=f_zmien), (1, odmowa % "inzynier"))
        (self.repo / ".agent-rola").write_text("recenzent\n", encoding="utf-8")       # rola z pliku, gdy zmiennej brak
        self.assertEqual(self.wstrzymaj(f_pr=f_pr, f_zmien=f_zmien), (1, odmowa % "recenzent"))
        self.assertEqual(self.zwolnij(f_zmien=f_zmien), (1, odmowa % "recenzent"))
        self.assertEqual((wolania, opisy), ([], []))                                 # odmowa przed pytaniem GitHuba i przed zapisem
        self.assertFalse((self.repo / self.REJESTR).exists())
        with mock.patch.dict(os.environ, {"AGENT_ROLA": "CEO"}):                     # zmienna ma pierwszeństwo przed plikiem
            self.assertEqual(self.wstrzymaj(f_pr=f_pr, f_zmien=f_zmien)[0], 0)
            self.assertEqual(self.zwolnij(f_zmien=f_zmien)[0], 0)
        (self.repo / ".agent-rola").write_text("ceo\n", encoding="utf-8")
        self.assertEqual(self.wstrzymaj(f_pr=f_pr, f_zmien=f_zmien)[0], 0)
        (self.repo / ".agent-rola").unlink()                                         # bez roli = człowiek przy klawiaturze
        self.assertEqual(self.zwolnij(f_zmien=f_zmien)[0], 0)


# ---------- miary ----------

class Miary(Zapisy):
    DZIENNIK = [
        {"kiedy": "2026-11-02 09:59", "kto": "scalanie-a", "min_od_werdyktu": 1, "czas_dokladny": True},       # minutę przed oknem 7 dni
        {"kiedy": "2026-11-02 10:00", "kto": "scalanie-a", "min_od_werdyktu": 10, "czas_dokladny": True},      # granica okna – liczy się
        {"kiedy": "2026-11-05 12:00", "kto": "scalanie-a", "min_od_werdyktu": 20, "czas_dokladny": True},
        {"kiedy": "2026-11-08 12:00", "kto": "ceo-czat", "min_od_werdyktu": 300, "czas_dokladny": True},
        {"kiedy": "2026-11-09 09:00", "kto": "scalanie-a", "min_od_werdyktu": 570, "czas_dokladny": False},    # werdykt z samą datą
        {"kiedy": "2026-11-09 09:30", "min_od_werdyktu": -5, "czas_dokladny": True},                           # scalony przed werdyktem
        {"kiedy": "2026-11-09 09:40", "kto": "scalanie-a", "min_od_werdyktu": None, "czas_dokladny": True},
        {"kiedy": "2026-11-09 09:45", "kto": "scalanie-a", "min_od_werdyktu": 40, "czas_dokladny": True},
        {"kiedy": "kiedyś", "kto": "scalanie-a", "min_od_werdyktu": 5, "czas_dokladny": True}]
    LISTY = {R1: [pr(nr=1, mergeable="CONFLICTING"), pr(nr=2, mergeable="CONFLICTING"), pr(nr=3, mergeable="CONFLICTING"),
                  pr(nr=4, mergeable="CONFLICTING", szkic=True), pr(nr=5), pr(nr=6), pr(nr=7), pr(nr=8), "śmieć"],
             R2: [pr(nr=9, mergeable="conflicting")]}
    REC = {"5": werdykt(kiedy="2026-11-09 07:59"),                       # OK od 121 min – ponad próg 2 h
           "6": werdykt(kiedy="2026-11-09 08:00"),                       # dokładnie 2 h – jeszcze nie
           "7": werdykt(wynik="POPRAWKI", scalenie="nie", kiedy="2026-11-08 08:00"),
           "8": werdykt(sha="bbbbbbb", kiedy="2026-11-08 08:00"),        # werdykt dla poprzedniego commita
           "firma-agenci#9": werdykt(kiedy="2026-11-08 08:00", data="2026-11-08")}    # OK od ponad doby, drugie repozytorium
    PROGI = ["PR-y z werdyktem OK niescalone ponad 2 h", "PR-y w konflikcie", "minuty od ostatniego przebiegu agenta scalającego"]

    def miary(self, dni=7, jako_json=False, listy=None, dziennik=None, **kw):
        p = self.repo / "ceo" / "scalanie" / "dziennik.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        wpisy = self.DZIENNIK if dziennik is None else dziennik
        p.write_text("".join(json.dumps(d) + "\n" for d in wpisy) + "to nie jest json\n\n", encoding="utf-8")
        par = dict(rec=self.REC, tetno_s=TERAZ_S - 50 * 60 - 30, wstrz={"3": {"sha": HEAD}},
                   st={"zgloszone": {"1": zgl(), "2": zgl()}, "przepiete": {}})
        par.update(kw)
        listy = self.LISTY if listy is None else listy
        kod, out = wyjscie(S.cmd_miary, self.k(**par), dni, jako_json, f_otwarte=lambda r: listy.get(r, []))
        self.assertEqual(kod, 0)
        return out

    def test_percentyl_najblizszej_rangi(self):
        self.assertIsNone(S._ranga([], 50))
        self.assertEqual((S._ranga([5], 50), S._ranga([5], 90)), (5, 5))
        self.assertEqual((S._ranga(range(10, 0, -1), 50), S._ranga(range(10, 0, -1), 90)), (5, 9))
        self.assertEqual((S._ranga([10, 20, 40, 300], 50), S._ranga([10, 20, 40, 300], 90)), (20, 300))

    def test_wydruk(self):
        self.assertEqual(self.miary().splitlines(), [
            "MIARY SCALANIA 2026-11-09 10:00 – ostatnie 7 dni",
            "scalone PR-y: 7 (? 1, ceo-czat 1, scalanie-a 5)",
            "czas od werdyktu do scalenia: mediana 20 min, p90 300 min (z 4 wpisów z dokładnym czasem werdyktu)",
            "otwarte zgłoszenia kolejki: 2 · wstrzymania CEO: 1",
            "PR-y z werdyktem OK niescalone ponad 2 h: 2 (próg 3) – OK",                 # 5 i firma-agenci#9
            "PR-y w konflikcie: 4 (próg 3) – PRZEKROCZONY",                              # 1, 2, 3 i firma-agenci#9; szkic 4 nie
            "minuty od ostatniego przebiegu agenta scalającego: 50 (próg 45) – PRZEKROCZONY"])

    def test_json(self):
        out = self.miary(jako_json=True)
        d = json.loads(out)
        self.assertEqual(d, {
            "okno_dni": 7, "scalone": 7, "kto": {"?": 1, "ceo-czat": 1, "scalanie-a": 5}, "z_dokladnym_czasem": 4, "mediana_min": 20,
            "p90_min": 300, "zgloszone": 2, "wstrzymane": 1, "bledy_gh": [],
            "progi": [{"miara": self.PROGI[0], "wartosc": 2, "prog": 3, "stan": "OK"},
                      {"miara": self.PROGI[1], "wartosc": 4, "prog": 3, "stan": "PRZEKROCZONY"},
                      {"miara": self.PROGI[2], "wartosc": 50, "prog": 45, "stan": "PRZEKROCZONY"}]})
        self.assertEqual(out, json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def test_okno_i_progi_z_ustawien(self):
        d = json.loads(self.miary(dni=1, jako_json=True, prg={"werdykt_ok_niescalony_h": 1, "werdykt_ok_niescalony_max": 1,
                                                             "pr_konflikty_max": 4, "gotowy_rezerwa_ceo_min": 50}))
        self.assertEqual((d["okno_dni"], d["scalone"], d["z_dokladnym_czasem"], d["mediana_min"], d["p90_min"]), (1, 5, 2, 40, 300))
        self.assertEqual([(p["miara"], p["wartosc"], p["prog"], p["stan"]) for p in d["progi"]], [
            ("PR-y z werdyktem OK niescalone ponad 1 h", 3, 1, "PRZEKROCZONY"),      # 5, 6 i firma-agenci#9
            (self.PROGI[1], 4, 4, "OK"), (self.PROGI[2], 50, 50, "OK")])                 # wartość równa progowi mieści się w nim

    def test_blad_gh_i_brak_tetna_to_brak_danych(self):
        out = self.miary(listy={R1: self.LISTY[R1], R2: None}, tetno_s=None)
        self.assertEqual(out.splitlines()[4:], [
            "BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, progi na żywo bez danych",
            "PR-y z werdyktem OK niescalone ponad 2 h: brak (próg 3) – BRAK DANYCH",
            "PR-y w konflikcie: brak (próg 3) – BRAK DANYCH",
            "minuty od ostatniego przebiegu agenta scalającego: brak (próg 45) – BRAK DANYCH"])
        d = json.loads(self.miary(jako_json=True, listy={R1: None, R2: None}, tetno_s=TERAZ_S + 600))
        self.assertEqual(d["bledy_gh"], [R1, R2])
        self.assertEqual([(p["wartosc"], p["stan"]) for p in d["progi"]], [(None, "BRAK DANYCH"), (None, "BRAK DANYCH"), (0, "OK")])

    def test_pusty_dziennik(self):
        out = self.miary(dziennik=[], listy={}, st={"zgloszone": {}, "przepiete": {}}, wstrz={})
        self.assertEqual(out.splitlines()[:4], [
            "MIARY SCALANIA 2026-11-09 10:00 – ostatnie 7 dni", "scalone PR-y: 0",
            "czas od werdyktu do scalenia: brak danych (werdykty bez pola `kiedy` albo brak scaleń w oknie)",
            "otwarte zgłoszenia kolejki: 0 · wstrzymania CEO: 0"])
        self.assertTrue(out.splitlines()[4].endswith(": 0 (próg 3) – OK"))

    def test_same_wpisy_bez_dokladnego_czasu(self):
        d = json.loads(self.miary(jako_json=True, dziennik=[self.DZIENNIK[4]]))
        self.assertEqual((d["scalone"], d["z_dokladnym_czasem"], d["mediana_min"], d["p90_min"]), (1, 0, None, None))


# ---------- wywołanie: main, kody wyjścia, wymóg tokenu i katalogu roboczego (bez gita, `gh` podstawione w procesie) ----------

ORG_YAML = ('organizacja:\n  strefa: "Europe/Warsaw"\n  prefiks: "org"\n'
            'repo:\n  github: "firma/firma-agenci"\n  produkt: ["firma/produkt"]\n')
OBCY_TOKEN = "0123456789abcdef"                         # poprawny kształt, ale takiej blokady nikt nie wziął


def atrapa_gh(odp, wolania):
    """Zamiennik S.gh: odp = {początek argumentów: (kod, stdout, stderr)}; wywołanie spoza słownika to błąd testu,
    więc żaden test tej sekcji nie sięgnie po prawdziwe `gh`."""
    def f(*a, timeout=60):
        wolania.append(a)
        for poczatek, wynik in odp.items():
            if a[:len(poczatek)] == poczatek:
                return wynik
        raise AssertionError("niespodziewane wywołanie gh: %r" % (a,))
    return f


def widok(nr, repo_gh, **pola):
    """Odpowiedź `gh pr view <nr> -R <repo>` – klucz i wynik dla atrapy gh."""
    d = {"number": nr, "title": "Zmiana", "headRefName": "agent/inzynier-zmiana", "headRefOid": HEAD, "state": "OPEN",
         "baseRefName": "main"}
    d.update(pola)
    return ("pr", "view", str(nr), "-R", repo_gh), (0, json.dumps(d), "")


class PrzezMain:
    """Wspólne dla testów uruchamiających skrypt przez main: atrapa w miejscu S.gh i przechwycone wyjścia."""

    def podstaw_gh(self):
        self.gh_odp, self.gh_wolania = {}, []
        p = mock.patch.object(S, "gh", atrapa_gh(self.gh_odp, self.gh_wolania))
        p.start()
        self.addCleanup(p.stop)

    def main(self, *a, repo=None, teraz=TERAZ_ISO):
        """-> (kod, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = S.main(list(a) + ["--repo", str(repo or self.repo)] + (["--teraz", teraz] if teraz else []))
        return kod, out.getvalue(), err.getvalue()

    def pisz(self, *a, token=None, **kw):
        """Polecenie zapisujące uruchomione tak, jak każe protokół: z katalogu roboczego i z tokenem blokady."""
        return self.main(*(a + ("--token", token or self.token)), repo=self.wt, **kw)

    def zle(self, wynik, powod):
        kod, out, err = wynik
        self.assertEqual((kod, out), (2, ""))
        self.assertEqual(err, ("ZŁE WYWOŁANIE: %s\n" % powod if powod else "") + S.__doc__ + "\n")


class Wywolanie(PrzezMain, Zapisy):
    """main na zwykłych katalogach: self.repo = wspólny katalog floty, self.wt = katalog roboczy (SCALANIE_KATALOG)."""

    def setUp(self):
        super().setUp()
        self.wt = self.katalog
        self.wt.mkdir(parents=True)
        for kat in (self.repo, self.wt):
            (kat / "org.yaml").write_text(ORG_YAML, encoding="utf-8")
        self.podstaw_gh()

    def test_zle_wywolania_to_kod_2_i_opis_na_stderr(self):
        blokada = "blokada <kto> [--protokol N]; <kto> np. scalanie-a, ceo-czat, ceo-przebieg"
        miary = "miary [--dni N] [--json]"
        for a, powod in [
                (["--nieznana"], ""),                                                    # nieznana opcja: sam opis użycia
                (["tabela", "--token", "xyz"], "--token: oczekiwany token z polecenia `blokada`"),
                (["blokada"], blokada), (["blokada", "Zła Nazwa"], blokada), (["blokada", "scalanie-a", "drugi"], blokada),
                (["blokada", "scalanie-a", "--protokol", "x"], blokada),
                (["odswiez"], "odswiez <token>"), (["odswiez", "abc"], "odswiez <token>"),
                (["odblokuj"], "odblokuj <token>"), (["odblokuj", OBCY_TOKEN.upper()], "odblokuj <token>"),
                (["scal", "5"], "nieznane polecenie „scal”"),
                (["wstrzymaj", "abc", "powód"], "klucz PR-a: numer albo <nazwa-repo>#numer"),
                (["tabela", "5"], "tabela nie przyjmuje argumentów"),
                (["miary", "5"], miary), (["miary", "--dni", "0"], miary), (["miary", "--dni", "x"], miary),
                (["wstrzymaj", "5"], 'wstrzymaj <klucz> "powód" [--head]'),
                (["wstrzymaj", "5", "  "], 'wstrzymaj <klucz> "powód" [--head]'),
                (["zwolnij", "5"], 'zwolnij <klucz> "uzasadnienie"')]:
            with self.subTest(a=a):
                self.zle(self.main(*a), powod)
        self.zle(self.main("tabela", teraz="wczoraj"), "--teraz: oczekiwany czas ISO, np. 2026-01-31T12:00")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(S.main(["tabela", "--repo"]), 2)       # opcja bez wartości
        self.assertEqual(err.getvalue(), S.__doc__ + "\n")
        self.assertEqual(self.gh_wolania, [])                       # złe wywołanie niczego nie pyta i niczego nie zostawia
        self.assertFalse(self.blokada.exists())
        self.assertEqual(self.oczekujace(), [])

    def test_kazdy_zapis_wymaga_tokenu(self):
        for a in (["zglos"], ["zglos", "5", "GOTOWY", "--powod", "odmowa"], ["potwierdz", "5"], ["przepiecie", "5"],
                  ["odnotuj", "5", "PRZEPNIJ"], ["zapisz"]):
            with self.subTest(a=a):
                self.zle(self.main(*a, repo=self.wt), "%s wymaga --token <token z polecenia blokada>" % a[0])
        self.assertEqual((self.gh_wolania, self.oczekujace()), ([], []))

    def test_zapis_bez_blokady_to_10_a_z_cudzym_tokenem_11(self):
        polecenia = (["zglos"], ["zglos", "5", "GOTOWY", "--powod", "odmowa"], ["potwierdz", "5"], ["przepiecie", "5"],
                     ["odnotuj", "5", "PRZEPNIJ"], ["zapisz"])
        for a in polecenia:
            with self.subTest(a=a, blokada="brak"):
                self.assertEqual(self.pisz(*a, token=OBCY_TOKEN), (
                    10, "BRAK BLOKADY: najpierw `scalanie.py blokada <kto>` – bez blokady niczego nie scalaj ani nie zapisuj\n", ""))
        self.wez("scalanie-b")
        for a in polecenia:
            with self.subTest(a=a, blokada="cudza"):
                self.assertEqual(self.pisz(*a, token=OBCY_TOKEN), (
                    11, "BLOKADA nie twoja: trzyma ją scalanie-b – niczego nie scalaj ani nie zapisuj\n", ""))
        self.assertEqual((self.gh_wolania, self.oczekujace()), ([], []))
        self.assertEqual(S.blokada_info(self.blokada)["od_s"], TERAZ_S)             # cudzej blokady nikt nie przedłużył

    def test_zapis_spoza_katalogu_roboczego_to_2(self):
        token = self.wez()[1]
        for a in (["zglos"], ["potwierdz", "5"], ["przepiecie", "5"], ["odnotuj", "5", "BRAK_CI"], ["zapisz"]):
            with self.subTest(a=a):
                self.assertEqual(self.main(*(a + ["--token", token])), (
                    2, "ZŁE WYWOŁANIE: zapisy tylko z katalogu roboczego (%s) – wejdź do niego poleceniem cd i uruchom skrypt "
                       "stamtąd\n" % self.wt, ""))
        self.assertEqual((self.gh_wolania, self.oczekujace()), ([], []))

    def test_zle_argumenty_zapisow_to_2_takze_z_blokada(self):
        self.token = self.wez()[1]
        zglos = 'zglos <klucz> <GOTOWY|PRZEPNIJ|BRAK_CI> --powod "co odpowiedział GitHub" --token T'
        for a, powod in [
                (["zglos", "5"], zglos), (["zglos", "5", "KONFLIKT", "--powod", "x"], zglos),     # zgłosić wolno tylko własną czynność
                (["zglos", "5", "GOTOWY"], zglos), (["zglos", "5", "GOTOWY", "--powod", "  "], zglos),
                (["potwierdz"], "potwierdz <klucz> [--kto X] --token T"),
                (["potwierdz", "5", "6"], "potwierdz <klucz> [--kto X] --token T"),
                (["potwierdz", "5", "--kto", "Ktoś Inny"], "potwierdz <klucz> [--kto X] --token T"),
                (["przepiecie"], "przepiecie <klucz> --token T"), (["przepiecie", "5", "6"], "przepiecie <klucz> --token T"),
                (["odnotuj", "5"], "odnotuj <klucz> <PRZEPNIJ|BRAK_CI> --token T"),
                (["odnotuj", "5", "GOTOWY"], "odnotuj <klucz> <PRZEPNIJ|BRAK_CI> --token T"),
                (["zapisz", "5"], "zapisz --token T"),
                (["potwierdz", "obce#"], "klucz PR-a: numer albo <nazwa-repo>#numer")]:
            with self.subTest(a=a):
                self.zle(self.pisz(*a), powod)
        self.assertEqual((self.gh_wolania, self.oczekujace()), ([], []))

    def test_brak_repozytoriow_to_1(self):
        komunikat = "BRAK REPOZYTORIÓW: uzupełnij repo.github / repo.produkt w org.yaml\n"
        self.token = self.wez()[1]
        for tresc in (None, ORG_YAML.replace("firma/", "OWNER/"), 'repo:\n  github: "bez-ukosnika"\n'):
            for kat in (self.repo, self.wt):
                if tresc is None:
                    (kat / "org.yaml").unlink()
                else:
                    (kat / "org.yaml").write_text(tresc, encoding="utf-8")
            with self.subTest(org=tresc):
                for a in (["tabela"], [], ["miary"], ["wstrzymaj", "5", "powód"], ["zwolnij", "5", "uzasadnienie"]):
                    self.assertEqual(self.main(*a), (1, komunikat, ""), a)
                for a in (["zglos"], ["potwierdz", "5"], ["odnotuj", "5", "BRAK_CI"]):
                    self.assertEqual(self.pisz(*a), (1, komunikat, ""), a)
        self.assertEqual((self.gh_wolania, self.oczekujace()), ([], []))

    def test_odswiez_i_odblokuj(self):
        token = self.wez()[1]
        self.assertEqual(self.main("odswiez", OBCY_TOKEN)[:2], (11, "BLOKADA nie twoja: trzyma ją scalanie-a – niczego nie scalaj "
                                                                      "ani nie zapisuj\n"))
        self.assertEqual(self.main("odswiez", token, teraz="2026-11-09T10:20"), (0, "BLOKADA odświeżona\n", ""))
        self.assertEqual(S.blokada_info(self.blokada), {"kto": "scalanie-a", "token": token, "od_s": TERAZ_S + 20 * 60})
        self.assertEqual(self.main("odblokuj", OBCY_TOKEN), (11, "BLOKADA nie twoja: trzyma ją scalanie-a – zostaje\n", ""))
        self.assertFalse(self.plik_tetna.exists())
        self.assertEqual(self.main("odblokuj", token, teraz="2026-11-09T10:25"), (0, "BLOKADA zwolniona\n", ""))
        self.assertFalse(self.blokada.exists())
        self.assertEqual(json.loads(self.plik_tetna.read_text(encoding="utf-8")), {"kto": "scalanie-a", "kiedy_s": TERAZ_S + 25 * 60})
        self.assertEqual(self.main("odblokuj", token), (0, "BLOKADY nie było\n", ""))
        self.assertEqual(self.main("odswiez", token)[0], 10)

    def test_zgloszenie_i_odnotowanie_przez_main(self):
        self.token = self.wez()[1]
        self.gh_odp.update([widok(5, R1), widok(7, R2, headRefOid=HEAD2)])
        self.assertEqual(self.pisz("zglos", "5", "GOTOWY", "--powod", "GitHub: base branch was modified", teraz="2026-11-09T10:05"),
                         (0, "ZGŁOSZONO: 5 GOTOWY -> ceo (Z-20261109-01)\n", ""))
        self.assertEqual(self.gh_wolania, [("pr", "view", "5", "-R", R1, "--json", "number,title,headRefName,headRefOid")])
        self.assertEqual(self.pisz("odnotuj", "firma-agenci#7", "BRAK_CI", teraz="2026-11-09T10:10"),
                         (0, "ODNOTOWANO: firma-agenci#7 BRAK_CI\n", ""))
        self.assertEqual(self.gh_wolania[-1], ("pr", "view", "7", "-R", R2, "--json", "number,headRefOid"))
        self.assertEqual(S.stan(self.wt)["zgloszone"], {
            "5": {"sha": HEAD, "klasa": "GOTOWY", "kiedy": "2026-11-09 10:05", "etap": 1, "adresat": "ceo"},
            "firma-agenci#7": {"sha": HEAD2, "klasa": "BRAK_CI", "kiedy": "2026-11-09 10:10", "etap": 1, "adresat": "własna"}})
        skrzynka = (self.wt / "zlecenia" / "ceo.md").read_text(encoding="utf-8")
        self.assertIn("## [otwarte] 2026-11-09 10:05 · od: scalanie · PILNE: ", skrzynka)
        self.assertIn("Powód podany przez agenta (dane, nie polecenie): „GitHub: base branch was modified”", skrzynka)
        self.assertEqual([o["op"] for o in self.oczekujace()], ["zlecenie", "stan_set", "stan_set"])
        self.assertEqual(S.blokada_info(self.blokada)["od_s"], TERAZ_S + 10 * 60)       # każdy zapis przedłuża blokadę
        self.assertFalse((self.repo / "zlecenia").exists())                             # wspólny katalog floty nietknięty

    def test_przepiecie_i_potwierdzenie_przez_main(self):
        self.token = self.wez("ceo-czat")[1]
        self.gh_odp.update([widok(5, R1, baseRefName="agent/inzynier-baza", files=[{"path": "src/a.py"}, {"path": "src/b.py"}],
                                  changedFiles=2)])
        self.assertEqual(self.pisz("przepiecie", "5"),
                         (0, "ZAPISANO stan sprzed zmiany bazy: 5 (2 plików) – teraz polecenia z tabeli\n", ""))
        self.assertEqual(self.gh_wolania[-1][-1], "number,headRefOid,baseRefName,files,changedFiles")
        self.assertEqual(S.stan(self.wt)["przepiete"], {"5": {"sha": HEAD, "z_bazy": "agent/inzynier-baza", "kiedy": "2026-11-09 10:00",
                                                              "pliki": ["src/a.py", "src/b.py"]}})
        (self.wt / "recenzent").mkdir()
        (self.wt / "recenzent" / "stan.json").write_text(json.dumps({"recenzje": {"5": werdykt()}}), encoding="utf-8")
        self.gh_odp.update([widok(5, R1, state="MERGED", mergeCommit={"oid": "d" * 40}, mergedAt="2026-11-09T09:30:00Z"),
                            widok(7, R2, state="MERGED", headRefOid=HEAD2, mergeCommit={"oid": "e" * 40},
                                  mergedAt="2026-11-09T09:35:00Z")])
        self.assertEqual(self.pisz("potwierdz", "5", teraz="2026-11-09T10:40"),
                         (0, "POTWIERDZONO: 5 scalony (dddddddddd), 90 min od werdyktu\n", ""))
        self.assertEqual(self.gh_wolania[-1][-1], "number,state,mergeCommit,headRefOid,mergedAt")
        self.assertEqual(self.pisz("potwierdz", "firma-agenci#7", "--kto", "scalanie-b", teraz="2026-11-09T10:41"),
                         (0, "POTWIERDZONO: firma-agenci#7 scalony (eeeeeeeeee)\n", ""))
        dziennik = [json.loads(l) for l in (self.wt / "ceo" / "scalanie" / "dziennik.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(d["klucz"], d["kto"], d["kiedy"], d["min_od_werdyktu"], d["czas_dokladny"]) for d in dziennik], [
            ("5", "ceo-czat", "2026-11-09 10:30", 90, True),                # bez --kto: posiadacz blokady
            ("firma-agenci#7", "scalanie-b", "2026-11-09 10:35", None, False)])
        self.assertEqual(S.stan(self.wt)["przepiete"], {})                  # scalony PR znika ze stanu
        self.gh_odp.update([widok(5, R1, state="OPEN")])
        kod, out, _ = self.pisz("potwierdz", "5")
        self.assertEqual((kod, out.split(" – ")[0]), (1, "NIE SCALONY: PR 5 ma stan OPEN"))

    def test_zapisz_bez_gita_zostawia_zapisy_w_kolejce(self):
        self.token = self.wez()[1]
        self.assertEqual(self.pisz("zapisz"), (0, "NIC DO ZAPISANIA\n", ""))
        self.gh_odp.update([widok(5, R1)])
        self.pisz("odnotuj", "5", "PRZEPNIJ")
        kod, out, err = self.pisz("zapisz")                                 # katalog roboczy nie jest tu repozytorium gita
        self.assertEqual((kod, err), (1, ""))
        self.assertTrue(out.startswith("NIE ZAPISANO po 3 próbach (git fetch: "), out)
        self.assertTrue(out.endswith(") – 1 zapisów czeka poza gitem (%s); dokończy je następny przebieg\n"
                                     % (self.tmp / "robocze" / "oczekujace.jsonl")), out)
        self.assertEqual([o["op"] for o in self.oczekujace()], ["stan_set"])

    def test_tabela_i_miary_przez_main_przy_bledach_gh(self):
        lista1, lista2 = ("pr", "list", "-R", R1), ("pr", "list", "-R", R2)
        self.gh_odp.update({lista1: (0, json.dumps([pr(5)]), ""), lista2: (1, "", "HTTP 502")})
        kod, out, err = self.main("tabela")
        self.assertEqual((kod, err), (0, ""))                               # jedno repozytorium odpowiedziało – przebieg ma sens
        self.assertEqual(self.gh_wolania[:2], [
            ("pr", "list", "-R", R1, "--state", "open", "--limit", "200", "--json", S.POLA),
            ("pr", "list", "-R", R2, "--state", "open", "--limit", "200", "--json", S.POLA)])
        self.assertEqual(out.splitlines()[:2], [
            "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 1, do zrobienia: 1",
            "BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu"])
        kod, out, _ = self.main("miary", "--dni", "3")
        self.assertEqual(kod, 0)
        self.assertEqual(out.splitlines()[0], "MIARY SCALANIA 2026-11-09 10:00 – ostatnie 3 dni")
        self.assertIn("BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, progi na żywo bez danych", out.splitlines())
        d = json.loads(self.main("miary", "--json")[1])
        self.assertEqual((d["okno_dni"], d["scalone"], d["bledy_gh"]), (7, 0, [R2]))
        self.gh_odp[lista1] = (0, "nie lista", "")                          # kod 0, ale to nie JSON z listą PR-ów
        self.assertEqual(self.main("tabela"), (1, "\n".join([
            "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 0, do zrobienia: 0",
            "BŁĄD GH: firma/produkt – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu",
            "BŁĄD GH: firma/firma-agenci – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu",
            "NIC DO ZROBIENIA", "REZERWA_CEO: NIE – nic nie czeka na scalenie"]) + "\n", ""))
        self.assertEqual(json.loads(self.main("tabela", "--json")[1])["bledy"], [R1, R2])


# ---------- prawdziwy git w katalogu tymczasowym: blokada → zapisy → zapisz ----------

SZKIELET = ("scripts/scalanie.py", "ceo/scalanie/stan.json", "ceo/scalanie/wstrzymane.json", "ceo/scalanie/dziennik.jsonl",
            "ceo/scalanie/ustawienia.yaml", "zlecenia/README.md")
AUTOR = ("Flota Testowa", "flota@example.invalid")
SZKIELET_OPIS = "szkielet organizacji"


def _git(kat, *a):
    """Prawdziwy git w katalogu tymczasowym (bez konfiguracji użytkownika – patrz setUpModule); niepowodzenie to błąd testu."""
    w = subprocess.run(["git", "-C", str(kat)] + list(a), capture_output=True, text=True, timeout=60)
    if w.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(a), w.stderr.strip()))
    return w.stdout.strip()


class UkladFloty(PrzezMain, Zapisy):
    """Układ jak we flocie: origin (bare), wspólny katalog floty = klon (self.repo); prywatny katalog roboczy zakłada skrypt.
    Na origin/main leży org.yaml z nazwami repozytoriów, kopia skryptu, pliki kolejki, skrzynki zleceń i werdykt recenzenta."""

    def setUp(self):
        super().setUp()
        self.origin, self.inny = self.tmp / "origin.git", self.tmp / "inna-sesja"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.inny)], check=True, capture_output=True)
        self.podpisz(self.inny, "Inna Sesja", "inna@example.invalid")
        for rel in SZKIELET:
            (self.inny / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(TU.parent / rel, self.inny / rel)
        for rel, tresc in (("org.yaml", ORG_YAML), ("role/inzynier.md", "# Inżynier\n"),
                           ("recenzent/stan.json", json.dumps({"recenzje": {"12": werdykt()}}) + "\n")):
            (self.inny / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.inny / rel).write_text(tresc, encoding="utf-8")
        _git(self.inny, "add", "-A")
        _git(self.inny, "commit", "-q", "-m", SZKIELET_OPIS)
        _git(self.inny, "remote", "add", "origin", str(self.origin))
        _git(self.inny, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)], check=True, capture_output=True)
        self.podpisz(self.repo, *AUTOR)
        self.wt = self.katalog

    def podpisz(self, kat, nazwa, email):
        _git(kat, "config", "user.name", nazwa)
        _git(kat, "config", "user.email", email)

    def cudzy_commit(self, rel, tresc, opis):
        """Inna sesja wypycha własną zmianę na gałąź główną. -> sha commita."""
        _git(self.inny, "pull", "-q", "--ff-only", "origin", "main")
        (self.inny / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.inny / rel).write_text(tresc, encoding="utf-8") if tresc is not None else (self.inny / rel).unlink()
        _git(self.inny, "add", "-A")
        _git(self.inny, "commit", "-q", "-m", opis)
        _git(self.inny, "push", "-q", "origin", "main")
        return _git(self.inny, "rev-parse", "HEAD")

    def glowna(self, rel):
        return _git(self.origin, "show", "main:" + rel)

    def historia(self):
        return _git(self.origin, "log", "--format=%s", "main").splitlines()

    def blokuj(self, kto="scalanie-a", teraz=TERAZ_ISO):
        """Polecenie `blokada` jak w treści zadania. Ustawia self.token; -> linie wypisane przed tokenem."""
        kod, out, err = self.main("blokada", kto, "--protokol", "1", teraz=teraz)
        self.assertEqual((kod, err), (0, ""), out)
        linie = out.splitlines()
        self.assertEqual(linie[-1], "KATALOG=%s" % self.wt)
        self.assertTrue(linie[-2].startswith("BLOKADA wzięta TOKEN="), out)
        self.token = linie[-2].split("TOKEN=")[1]
        self.assertRegex(self.token, S.RE_TOKEN)
        return linie[:-2]

    def wspolny_nietkniety(self):
        """Wspólny katalog floty: ta sama gałąź, ten sam commit, zero zmian – skrypt pracuje wyłącznie obok."""
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(_git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(_git(self.repo, "log", "-1", "--format=%s"), SZKIELET_OPIS)


class NaPrawdziwymGicie(UkladFloty):
    """Skrypt na prawdziwym gicie; `gh` podstawione w procesie (S.gh), więc GitHuba nikt nie pyta."""

    def setUp(self):
        super().setUp()
        self.podstaw_gh()

    def test_blokada_zgloszenie_i_zapisz_trafiaja_na_galaz_glowna(self):
        self.assertEqual(self.blokuj(), [])
        self.assertEqual(_git(self.wt, "rev-parse", "HEAD"), _git(self.origin, "rev-parse", "main"))
        self.assertEqual(_git(self.wt, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")       # odłączony HEAD, żadnej gałęzi
        self.gh_odp.update([widok(12, R1)])
        self.assertEqual(self.pisz("zglos", "12", "GOTOWY", "--powod", "GitHub: required status check is expected"),
                         (0, "ZGŁOSZONO: 12 GOTOWY -> ceo (Z-20261109-01)\n", ""))
        self.assertEqual(self.historia(), [SZKIELET_OPIS])                                 # do `zapisz` nic nie trafia do gita
        kod, out, err = self.pisz("zapisz", teraz="2026-11-09T10:05")
        skrot = _git(self.origin, "rev-parse", "--short=10", "main")
        self.assertEqual((kod, out, err), (0, "ZAPISANE: %s (ceo/scalanie/stan.json, zlecenia/ceo.md)\n" % skrot, ""))
        self.assertEqual(self.historia(), ["scalanie: stan kolejki 2026-11-09 10:05", SZKIELET_OPIS])
        self.assertEqual(_git(self.origin, "log", "-1", "--format=%an <%ae>", "main"), "%s <%s>" % AUTOR)
        self.assertEqual(_git(self.origin, "show", "--name-only", "--format=", "main").splitlines(),
                         ["ceo/scalanie/stan.json", "zlecenia/ceo.md"])
        self.assertEqual(json.loads(self.glowna("ceo/scalanie/stan.json")),
                         {"przepiete": {}, "zgloszone": {"12": zgl("GOTOWY", kiedy="2026-11-09 10:00")}})
        skrzynka = self.glowna("zlecenia/ceo.md")
        self.assertIn("## [otwarte] 2026-11-09 10:00 · od: scalanie · PILNE: scalenie odrzucone przez GitHub – PR 12 · Z-20261109-01",
                      skrzynka.splitlines())
        self.assertIn("PR: https://github.com/firma/produkt/pull/12 · head aaaaaaaaaaaa · gałąź agent/inzynier-zmiana", skrzynka.splitlines())
        self.assertEqual(self.oczekujace(), [])                                            # kolejka poza gitem opróżniona
        self.assertEqual(self.pisz("zapisz"), (0, "NIC DO ZAPISANIA\n", ""))
        self.wspolny_nietkniety()
        # kopia stanu we wspólnym katalogu jest stara – poza katalogiem roboczym skrypt czyta stan z gałęzi głównej
        self.assertEqual(S.stan(self.repo)["zgloszone"], {})
        self.assertEqual(list(S._kontekst(self.repo, TERAZ, TERAZ_S).st["zgloszone"]), ["12"])
        self.assertEqual(self.main("odblokuj", self.token, teraz="2026-11-09T10:06"), (0, "BLOKADA zwolniona\n", ""))
        self.assertFalse(self.blokada.exists())
        self.assertEqual(json.loads(self.plik_tetna.read_text(encoding="utf-8")), {"kto": "scalanie-a", "kiedy_s": TERAZ_S + 360})

    def test_cudzy_push_przed_zapisz_niczego_nie_gubi(self):
        self.blokuj()
        self.gh_odp.update([widok(12, R1)])
        self.pisz("zglos", "12", "GOTOWY", "--powod", "odmowa GitHuba")
        # inna sesja dopisała w tym czasie własne zlecenie do tej samej skrzynki i zajęła pierwszy numer dnia
        cudzy = self.cudzy_commit("zlecenia/ceo.md", "# Zlecenia – ceo\n\n## [otwarte] 2026-11-09 09:55 · od: pm · raport · Z-20261109-01\n"
                                                     "Treść cudzego zlecenia.\nOdpowiedź:\n", "pm: zlecenie dla ceo")
        kod, out, err = self.pisz("zapisz")
        self.assertEqual((kod, err), (0, ""), out)
        self.assertEqual(self.historia(), ["scalanie: stan kolejki 2026-11-09 10:00", "pm: zlecenie dla ceo", SZKIELET_OPIS])
        self.assertEqual(_git(self.origin, "rev-list", "--parents", "-1", "main").split()[1:], [cudzy])   # zwykły commit: bez scalenia
        skrzynka = self.glowna("zlecenia/ceo.md")
        self.assertIn("Treść cudzego zlecenia.", skrzynka)
        self.assertIn("– PR 12 · Z-20261109-02", skrzynka)                  # numer liczony przy nakładaniu, nie przy zgłoszeniu
        self.assertEqual(skrzynka.count("Z-20261109-01"), 1)
        self.assertTrue(skrzynka.endswith("Plan: –\nOdpowiedź:"), skrzynka[-80:])

    def test_wyscig_przy_push_powtarza_na_swiezej_glownej(self):
        self.blokuj()
        self.gh_odp.update([widok(12, R1)])
        self.pisz("odnotuj", "12", "BRAK_CI")
        prawdziwy, zostalo = S.git, [1]

        def git_z_wyscigiem(repo, *a, **kw):
            if a[:1] == ("push",) and zostalo[0]:          # między fetch a push ktoś zdążył wypchnąć swoje
                zostalo[0] -= 1
                self.cudzy_commit("notatki/dzien.md", "notatka\n", "pm: notatka dnia")
            return prawdziwy(repo, *a, **kw)

        with mock.patch.object(S, "git", git_z_wyscigiem):
            kod, out, err = self.pisz("zapisz")
        self.assertEqual((kod, err), (0, ""), out)
        self.assertEqual(out, "ZAPISANE: %s (ceo/scalanie/stan.json)\n" % _git(self.origin, "rev-parse", "--short=10", "main"))
        self.assertEqual(self.historia(), ["scalanie: stan kolejki 2026-11-09 10:00", "pm: notatka dnia", SZKIELET_OPIS])
        self.assertEqual(self.glowna("notatki/dzien.md"), "notatka")
        self.assertEqual(json.loads(self.glowna("ceo/scalanie/stan.json"))["zgloszone"]["12"]["klasa"], "BRAK_CI")
        self.assertEqual(self.oczekujace(), [])
        self.assertEqual(_git(self.wt, "status", "--porcelain"), "")

    def test_przerwany_przebieg_dokancza_nastepny(self):
        self.blokuj()
        stary = self.token
        self.gh_odp.update([widok(12, R1)])
        self.pisz("zglos", "12", "GOTOWY", "--powod", "odmowa GitHuba")
        self.assertEqual(_git(self.wt, "status", "--porcelain", "--untracked-files=all").split("\n"),
                         ["M ceo/scalanie/stan.json", "?? zlecenia/ceo.md"])
        # przebieg ginie bez `zapisz` i bez `odblokuj`; następny przejmuje blokadę po progu i zaczyna od świeżej gałęzi głównej
        kod, out, _ = self.main("blokada", "scalanie-b", "--protokol", "1", teraz="2026-11-09T10:20")
        self.assertEqual((kod, out), (10, "BLOKADA zajęta: scalanie-a od 20 min\n"))
        self.assertEqual(self.blokuj("scalanie-b", teraz="2026-11-09T10:45"), [
            "BLOKADA przejęta po scalanie-a (bez znaku od 45 min, próg 30)",
            "OCZEKUJĄCE: 2 zapisów z poprzedniego przebiegu nałożone – wypchnie je `zapisz`"])
        self.assertEqual(self.pisz("zapisz", token=stary, teraz="2026-11-09T10:46")[0], 11)    # stary przebieg już nie zapisze
        self.assertEqual(self.historia(), [SZKIELET_OPIS])
        kod, out, _ = self.pisz("zapisz", teraz="2026-11-09T10:46")
        self.assertEqual((kod, out.split(" (")[1]), (0, "ceo/scalanie/stan.json, zlecenia/ceo.md)\n"))
        self.assertEqual(self.historia(), ["scalanie: stan kolejki 2026-11-09 10:46", SZKIELET_OPIS])
        self.assertEqual(self.glowna("zlecenia/ceo.md").count("## [otwarte]"), 1)
        self.assertEqual(json.loads(self.glowna("ceo/scalanie/stan.json"))["zgloszone"]["12"]["kiedy"], "2026-11-09 10:00")
        # trzeci przebieg: nic nie czeka, a ponowne zgłoszenie tego samego nie dubluje wpisu w skrzynce
        self.main("odblokuj", self.token, teraz="2026-11-09T10:47")
        self.assertEqual(self.blokuj("scalanie-a", teraz="2026-11-09T11:00"), [])
        self.assertEqual(self.pisz("zglos", "12", "GOTOWY", "--powod", "odmowa GitHuba", teraz="2026-11-09T11:00"),
                         (0, "ZGŁOSZONO: 12 GOTOWY -> ceo (wpis już był w skrzynce)\n", ""))
        self.pisz("zapisz", teraz="2026-11-09T11:01")
        self.assertEqual(self.glowna("zlecenia/ceo.md").count("## [otwarte]"), 1)
        self.wspolny_nietkniety()

    def test_niezgodny_protokol_to_13_i_zadnej_blokady(self):
        rada = (". Podmień razem treść zadania i skrypt (python3 flota/generuj.py, treść zadania zaplanowanego, "
                "git pull we wspólnym katalogu). Blokady nie wzięto.\n")
        ustawienia = (TU.parent / "ceo" / "scalanie" / "ustawienia.yaml").read_text(encoding="utf-8")
        self.assertIn("\nprotokol: 1 ", ustawienia)

        def proba(*opcje):
            kod, out, err = self.main("blokada", "scalanie-a", *opcje)
            self.assertFalse(self.blokada.exists())                         # blokada wraca…
            self.assertFalse(self.plik_tetna.exists())                      # …bez śladu „agent działał”
            self.assertEqual(self.oczekujace(), [])
            return kod, out, err

        self.assertEqual(proba("--protokol", "2"), (13, "NIEZGODNY PROTOKÓŁ: skrypt uruchomiony 1, skrypt na gałęzi głównej 1, "
                                                        "ustawienia na gałęzi głównej 1, treść zadania 2" + rada, ""))
        self.cudzy_commit("ceo/scalanie/ustawienia.yaml", ustawienia.replace("\nprotokol: 1 ", "\nprotokol: 2 "), "ceo: protokół 2")
        self.assertEqual(proba("--protokol", "1"), (13, "NIEZGODNY PROTOKÓŁ: skrypt uruchomiony 1, skrypt na gałęzi głównej 1, "
                                                        "ustawienia na gałęzi głównej 2, treść zadania 1" + rada, ""))
        self.cudzy_commit("scripts/scalanie.py", None, "porządki: skrypt usunięty")
        self.assertEqual(proba(), (13, "NIEZGODNY PROTOKÓŁ: skrypt uruchomiony 1, skrypt na gałęzi głównej brak, "
                                       "ustawienia na gałęzi głównej 2" + rada, ""))
        # po przywróceniu zgodności ten sam katalog roboczy służy dalej
        self.cudzy_commit("ceo/scalanie/ustawienia.yaml", ustawienia, "ceo: protokół 1")
        self.cudzy_commit("scripts/scalanie.py", (TU / "scalanie.py").read_text(encoding="utf-8"), "skrypt wraca")
        self.assertEqual(self.blokuj(), [])
        self.assertEqual(_git(self.wt, "rev-parse", "HEAD"), _git(self.origin, "rev-parse", "main"))

    def test_blokada_bez_dzialajacego_gita_wraca(self):
        pusty = self.tmp / "nie-repo"
        pusty.mkdir()
        kod, out, err = self.main("blokada", "scalanie-a", repo=pusty)
        self.assertEqual((kod, err), (1, ""))
        self.assertTrue(out.startswith("BŁĄD GIT: fetch nie przeszedł (") and out.endswith(") – blokady nie wzięto\n"), out)
        self.assertFalse(self.blokada.exists())
        self.assertFalse(self.plik_tetna.exists())

    def test_obce_rzeczy_w_katalogu_roboczym_sa_odkladane_nie_kasowane(self):
        self.wt.mkdir(parents=True)
        (self.wt / "notatka.txt").write_text("czyjaś notatka\n", encoding="utf-8")
        linie = self.blokuj()                                               # pod ścieżką katalogu roboczego leżał zwykły katalog
        self.assertEqual(len(linie), 1)
        self.assertTrue(linie[0].startswith("UWAGA: %s nie był katalogiem roboczym git – odłożony jako odlozone-20261109-100000-" % self.wt))
        odlozone = [p for p in self.wt.parent.iterdir() if p.name.startswith("odlozone-")]
        self.assertEqual([(p / "notatka.txt").read_text(encoding="utf-8") for p in odlozone], ["czyjaś notatka\n"])
        self.main("odblokuj", self.token)
        # ktoś pracował w prywatnym katalogu kolejki: zmiana śledzonego pliku i nowy plik – oba lądują obok, katalog wraca do czystości
        (self.wt / "org.yaml").write_text(ORG_YAML + "# dopisek\n", encoding="utf-8")
        (self.wt / "szkic" ).mkdir()
        (self.wt / "szkic" / "plan.md").write_text("szkic\n", encoding="utf-8")
        (self.wt / "zlecenia" / "ceo.md").write_text("własny plik kolejki – nie jest obcy\n", encoding="utf-8")
        linie = self.blokuj(teraz="2026-11-09T10:15")
        self.assertEqual(len(linie), 1)
        kosz = [p for p in self.wt.parent.iterdir() if p.name.startswith("odlozone-20261109-101500-")]
        self.assertEqual(linie, ["UWAGA: w katalogu roboczym były obce zmiany (2 plików) – odłożone do %s; kolejka ich nie używa" % kosz[0]])
        self.assertEqual((kosz[0] / "nowe" / "szkic" / "plan.md").read_text(encoding="utf-8"), "szkic\n")
        self.assertIn("+# dopisek", (kosz[0] / "zmiany.patch").read_text(encoding="utf-8"))
        self.assertEqual(_git(self.wt, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual((self.wt / "org.yaml").read_text(encoding="utf-8"), ORG_YAML)
        self.assertFalse((self.wt / "zlecenia" / "ceo.md").exists())

    def test_wstrzymaj_i_zwolnij_zapisuja_rejestr_na_galezi_glownej(self):
        self.gh_odp.update([widok(12, R1)])
        ogon_w = ". Kolejka czyta rejestr z gałęzi głównej; wspólny katalog odświeży `git pull`.\n"
        ogon_z = ". We wspólnym katalogu wykonaj `git pull` – stara kopia rejestru dalej wstrzymuje (celowo).\n"
        skrot = lambda: _git(self.origin, "rev-parse", "--short=10", "main")
        with mock.patch.object(tempfile, "tempdir", str(self.tmp)):         # jednorazowy katalog roboczy też w katalogu testu
            self.assertEqual(self.main("wstrzymaj", "12", "czekamy na decyzję o cenniku"),
                             (0, "WSTRZYMANO: 12 (do odwołania) – %s%s" % (skrot(), ogon_w), ""))
            self.assertEqual(self.gh_wolania, [("pr", "view", "12", "-R", R1, "--json", "number,state,headRefOid")])
            wpis = {"sha": HEAD, "tryb": "do_odwolania", "powod": "czekamy na decyzję o cenniku", "kiedy": "2026-11-09 10:00"}
            self.assertEqual(json.loads(self.glowna(S.REJESTR)), {"wstrzymane": {"12": wpis}, "zwolnione": []})
            self.assertEqual(self.historia(), ["scalanie: wstrzymanie 12", SZKIELET_OPIS])
            self.assertEqual(_git(self.origin, "log", "-1", "--format=%an <%ae>", "main"), "%s <%s>" % AUTOR)
            self.assertEqual(self.main("wstrzymaj", "12", "czekamy na decyzję o cenniku", teraz="2026-11-09T10:30"),
                             (0, "WSTRZYMANO: 12 (do odwołania) – bez zmian" + ogon_w, ""))
            # kolejka we wspólnym katalogu widzi wstrzymanie bez `git pull` – czyta rejestr z origin/main
            self.assertEqual(S.wstrzymane(self.repo, S.ustawienia(self.repo)), {"12": wpis})
            self.assertEqual(json.loads((self.repo / S.REJESTR).read_text(encoding="utf-8"))["wstrzymane"], {})
            _git(self.repo, "config", "--unset", "user.name")               # sesja bez tożsamości gita też zapisze rejestr
            _git(self.repo, "config", "--unset", "user.email")
            self.assertEqual(self.main("zwolnij", "12", "decyzja zapadła: cennik bez zmian", teraz="2026-11-09T11:00"),
                             (0, "ZWOLNIONO: 12 – %s%s" % (skrot(), ogon_z), ""))
            self.assertEqual(json.loads(self.glowna(S.REJESTR)), {"wstrzymane": {}, "zwolnione": [
                {"klucz": "12", "kiedy": "2026-11-09 11:00", "uzasadnienie": "decyzja zapadła: cennik bez zmian",
                 "powod": "czekamy na decyzję o cenniku", "sha": HEAD}]})
            self.assertEqual(self.historia()[0], "scalanie: zwolnienie 12")
            self.assertEqual(_git(self.origin, "log", "-1", "--format=%an <%ae>", "main"), "scalanie <scalanie@localhost>")
            self.assertEqual(self.main("zwolnij", "12", "drugi raz"),
                             (1, "NIE WSTRZYMANY: 12 nie ma wpisu w rejestrze na gałęzi głównej\n", ""))
        self.assertEqual(len(self.historia()), 3)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith("scalanie-")], [])   # po jednorazowych katalogach ani śladu
        self.assertEqual(_git(self.repo, "worktree", "list", "--porcelain").count("worktree "), 1)
        self.assertFalse(self.blokada.exists())                             # polecenia CEO nie biorą blokady kolejki
        self.wspolny_nietkniety()


# ---------- koniec do końca: skrypt przez main, prawdziwy git, a w PATH atrapa programu `gh` ----------

ATRAPA_GH = r'''#!@PYTHON@
"""Atrapa `gh` na czas testów scalanie.py. Odpowiedzi czyta z pliku wskazanego zmienną ATRAPA_GH_DANE:
{"początek argumentów rozdzielonych spacją": [kod wyjścia, stdout, stderr]} – wygrywa najdłuższy pasujący początek.
Każde wywołanie dopisuje do pliku ATRAPA_GH_WOLANIA. Wywołanie spoza danych kończy się kodem 97: atrapa niczego
nie zgaduje i nigdy nie sięga do sieci ani do prawdziwego gh."""
import json
import os
import sys

a = sys.argv[1:]
with open(os.environ["ATRAPA_GH_WOLANIA"], "a", encoding="utf-8") as f:
    f.write(json.dumps(a) + "\n")
with open(os.environ["ATRAPA_GH_DANE"], encoding="utf-8") as f:
    dane = json.load(f)
wolanie = " ".join(a)
pasujace = sorted((p for p in dane if wolanie == p or wolanie.startswith(p + " ")), key=len)
if not pasujace:
    sys.stderr.write("atrapa gh: wywolanie spoza danych testu: %s\n" % wolanie)
    sys.exit(97)
kod, out, err = dane[pasujace[-1]]
sys.stdout.buffer.write(out.encode("utf-8"))
sys.stderr.buffer.write(err.encode("utf-8"))
sys.exit(kod)
'''
SHA_GLOWNEJ = "c" * 40
LISTA = "pr list -R %s --state open"
BIEGI, STATUS = "api repos/%s/commits/main/check-runs?per_page=100", "api repos/%s/commits/main/status"
DRZEWO = "api repos/%s/git/trees/main?recursive=1"
BLAD_LISTY = "BŁĄD GH: %s – lista PR-ów nieczytelna, repozytorium pominięte w tym przebiegu"


def rzad(klucz, klasa, adresat, uwaga="", head=HEAD):
    """Wiersz tabeli w układzie wydruku (dosłowny wzór pilnuje klasa Wydruk)."""
    return "%-16s %-17s -> %-10s %s  %s" % (klucz, klasa, adresat, head[:10], uwaga)


class KoniecDoKonca(UkladFloty):
    """Cała droga jak w przebiegu zaplanowanym: main → git w katalogu tymczasowym → program `gh` znaleziony w PATH.
    S.gh nie jest podstawione – skrypt naprawdę uruchamia proces `gh`, tyle że pierwsza w PATH stoi atrapa."""

    def setUp(self):
        super().setUp()
        kat = self.tmp / "bin"
        kat.mkdir()
        python = sys.executable + " -I" if sys.executable and " " not in sys.executable else "/usr/bin/env python3"
        (kat / "gh").write_text(ATRAPA_GH.replace("@PYTHON@", python), encoding="utf-8")
        (kat / "gh").chmod(0o755)
        self.dane, self.plik_wolan = self.tmp / "gh-dane.json", self.tmp / "gh-wolania.jsonl"
        srod = mock.patch.dict(os.environ, {"PATH": str(kat) + os.pathsep + os.environ.get("PATH", ""),
                                            "ATRAPA_GH_DANE": str(self.dane), "ATRAPA_GH_WOLANIA": str(self.plik_wolan)})
        srod.start()
        self.addCleanup(srod.stop)
        self.wszystkie = []                                                 # każde wywołanie gh w teście, po kolei
        self.ustaw_github({})
        rec = {k: werdykt() for k in ("12", "13", "15", "18", "firma-agenci#3")}
        rec.update({"16": werdykt(klasa_migracji={"0008": "A"}), "17": werdykt(warunki=["po 11"]),
                    "firma-agenci#4": werdykt(sha="bbbbbbb")})
        # werdykty trafiają na gałąź główną po sklonowaniu wspólnego katalogu: skrypt ma je zobaczyć bez `git pull`
        self.cudzy_commit("recenzent/stan.json", json.dumps({"recenzje": rec}) + "\n", "recenzent: werdykty")

    def ustaw_github(self, odp):
        """odp: {początek wywołania: dane (→ JSON, kod 0) | tekst (kod 0) | (kod, stdout, stderr)}."""
        self.dane.write_text(json.dumps({p: list(w) if isinstance(w, tuple) else [0, w if isinstance(w, str) else json.dumps(w), ""]
                                         for p, w in odp.items()}), encoding="utf-8")

    def wolania(self):
        """Wywołania `gh` od poprzedniego odczytu – listy argumentów."""
        if not self.plik_wolan.exists():
            return []
        nowe = [json.loads(l) for l in self.plik_wolan.read_text(encoding="utf-8").splitlines()]
        self.plik_wolan.unlink()
        self.wszystkie += nowe
        return nowe

    def zwykly_dzien(self, bez=(), **zmiany_pr):
        """Odpowiedzi GitHuba: dwa repozytoria, dziewięć otwartych PR-ów, zielona gałąź główna produktu.
        bez = numery PR-ów produktu, których już nie ma na liście; zmiany_pr = {"pr15": {pole: wartość}}."""
        produkt = [pr(12), pr(13, mergeable="CONFLICTING", galaz="agent/inzynier-cennik"), pr(14, galaz="agent/inzynier-raport"),
                   pr(15, base="agent/inzynier-rodzic", galaz="agent/inzynier-dziecko"),
                   pr(16, pliki=("db/migrate/0008_rabaty.sql",)), pr(17, pliki=("src/b.py",)),
                   pr(18, pliki=("db/migrate/0007_cennik.sql",), galaz="agent/analityk-tabela")]   # roli „analityk” nie ma → CEO
        for p in produkt:
            p.update(zmiany_pr.get("pr%d" % p["number"], {}))
        return {LISTA % R1: [p for p in produkt if p["number"] not in bez],
                LISTA % R2: [pr(3, pliki=("zasady.md",), galaz="agent/pm-zasady"), pr(4, head=HEAD2, ci="IN_PROGRESS")],
                "pr list -R %s --state all --head agent/inzynier-rodzic" % R1: [{"state": "MERGED", "number": 9}],
                "pr view 11 -R %s" % R1: {"state": "MERGED"},
                DRZEWO % R1: "db/migrate/0006_start.sql\ndb/migrate/0007_inne.sql\nsrc/a.py\n",
                BIEGI % R1: {"check_runs": [{"conclusion": "success", "status": "completed", "head_sha": SHA_GLOWNEJ}]},
                STATUS % R1: {"sha": SHA_GLOWNEJ, "total_count": 0, "state": "pending"}}

    def test_tabela_od_listy_pr_do_polecen(self):
        self.ustaw_github(self.zwykly_dzien())
        kod, out, err = self.main("tabela")
        self.assertEqual((kod, err), (0, ""))
        scal = "    $ gh pr merge %d --repo firma/produkt --merge --match-head-commit " + HEAD
        self.assertEqual(out.splitlines(), [
            "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 9, do zrobienia: 8",
            "PLIKI SPORNE: src/a.py (4 PR-ów, produkt)",
            rzad("12", "GOTOWY", "scal"), scal % 12,
            rzad("13", "KONFLIKT", "inzynier", "konflikt z main"),
            rzad("14", "BRAK_WERDYKTU", "recenzent", "bez werdyktu od 120 min (próg 60)"),
            rzad("15", "PRZEPNIJ", "własna", "rodzic scalony – baza agent/inzynier-rodzic do zmiany na main"),
            "    $ gh pr edit 15 --repo firma/produkt --base main",
            "    $ gh pr close 15 --repo firma/produkt",
            "    $ gh pr reopen 15 --repo firma/produkt",
            rzad("16", "MIGRACJA", "ceo", "klasa A – scalenie i zastosowanie: CEO"),
            rzad("17", "GOTOWY", "scal"), scal % 17,
            rzad("18", "KOLIZJA_MIGRACJI", "ceo", "numer 0007 zajęty na gałęzi głównej: db/migrate/0007_inne.sql"),
            rzad("firma-agenci#3", "WYJATEK", "ceo", "ścieżki wyłączone: zasady.md"),
            "bez ruchu: CI_TRWA 1",
            "REZERWA_CEO: TAK – gotowy PR czeka 60 min, agent scalający bez śladu od ponad 45 min"])
        # dokładnie te pytania do GitHuba i w tej kolejności: dwie listy, rodzic PR-a 15, migracje na głównej (raz na repo),
        # zależność z werdyktu PR-a 17, CI gałęzi głównej tylko tam, gdzie jest co scalać
        otwarte = ["--state", "open", "--limit", "200", "--json", S.POLA]
        self.assertEqual(self.wolania(), [
            ["pr", "list", "-R", R1] + otwarte, ["pr", "list", "-R", R2] + otwarte,
            ["pr", "list", "-R", R1, "--state", "all", "--head", "agent/inzynier-rodzic", "--limit", "10", "--json", "state,number"],
            ["api", DRZEWO.split()[1] % R1, "--jq", ".tree[].path"],
            ["pr", "view", "11", "-R", R1, "--json", "state"],
            ["api", BIEGI.split()[1] % R1], ["api", STATUS.split()[1] % R1]])
        self.wspolny_nietkniety()                                           # werdykty przyszły z origin/main, nie z `git pull`
        self.assertFalse(self.blokada.exists())                             # tabela niczego nie blokuje i niczego nie zapisuje
        self.assertEqual(self.oczekujace(), [])

    def test_tabela_json_i_wszystko(self):
        self.ustaw_github(self.zwykly_dzien())
        kod, out, err = self.main("tabela", "--json")
        self.assertEqual((kod, err), (0, ""))
        d = json.loads(out)
        self.assertEqual(sorted(d), ["bledy", "pliki_sporne", "rezerwa", "teraz", "uwagi", "wiersze"])
        self.assertEqual([(w["klucz"], w["klasa"], w["adresat"], w["do_zrobienia"]) for w in d["wiersze"]], [
            ("12", "GOTOWY", "scal", True), ("13", "KONFLIKT", "inzynier", True), ("14", "BRAK_WERDYKTU", "recenzent", True),
            ("15", "PRZEPNIJ", "własna", True), ("16", "MIGRACJA", "ceo", True), ("17", "GOTOWY", "scal", True),
            ("18", "KOLIZJA_MIGRACJI", "ceo", True), ("firma-agenci#3", "WYJATEK", "ceo", True),
            ("firma-agenci#4", "CI_TRWA", "–", False)])
        self.assertEqual(d["wiersze"][0]["polecenia"], ["gh pr merge 12 --repo firma/produkt --merge --match-head-commit " + HEAD])
        self.assertEqual((d["teraz"], d["bledy"], d["uwagi"]), ("2026-11-09 10:00", [], []))
        self.assertEqual(d["pliki_sporne"], [{"repo": R1, "plik": "src/a.py", "pr": 4}])
        self.assertEqual(d["rezerwa"], {"stan": "TAK", "powod": "gotowy PR czeka 60 min, agent scalający bez śladu od ponad 45 min"})
        kod, out, _ = self.main("tabela", "--wszystko")
        linie = out.splitlines()
        self.assertEqual((kod, linie[-2]), (0, rzad("firma-agenci#4", "CI_TRWA", "–", "CI w toku", head=HEAD2)))
        self.assertFalse([l for l in linie if l.startswith("bez ruchu")])

    def test_czerwona_galaz_glowna_i_github_ktory_nie_odpowiada(self):
        gh = self.zwykly_dzien()
        gh[BIEGI % R1] = {"check_runs": [{"conclusion": "failure", "status": "completed", "head_sha": SHA_GLOWNEJ}]}
        gh[LISTA % R2] = "<html>502 Bad Gateway</html>"                     # kod 0, ale to nie jest lista
        self.ustaw_github(gh)
        kod, out, err = self.main("tabela")
        linie = out.splitlines()
        self.assertEqual((kod, err), (0, ""))                               # jedno repozytorium milczy – reszta kolejki działa
        self.assertEqual(linie[:2], ["KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 7, do zrobienia: 6", BLAD_LISTY % R2])
        self.assertIn(rzad("12", "GLOWNA_CZERWONA", "ceo", "CI gałęzi main czerwone (cccccccccc) – gotowe PR-y w firma/produkt czekają: 2"),
                      linie)
        self.assertFalse([l for l in linie if "gh pr merge" in l])          # zatrzymana linia: żadnego polecenia scalenia
        self.assertEqual(linie[-2:], ["bez ruchu: CZEKA_NA_GLOWNA 1", "REZERWA_CEO: NIE – nic nie czeka na scalenie"])
        # stan CI gałęzi głównej nie do odczytania: kolejka nie staje, ale mówi o tym w nagłówku
        gh = self.zwykly_dzien()
        del gh[STATUS % R1]
        self.ustaw_github(gh)
        kod, out, _ = self.main("tabela")
        self.assertEqual(kod, 0)
        self.assertEqual(out.splitlines()[1], "UWAGA: firma/produkt – stan CI gałęzi głównej nieznany, kolejka nie jest zatrzymana")
        self.assertEqual(len([l for l in out.splitlines() if "gh pr merge" in l]), 2)
        # GitHub nie odpowiada wcale (każde wywołanie gh kończy się błędem) – kod 1, żadnych wierszy z domysłu
        self.ustaw_github({})
        self.assertEqual(self.main("tabela"), (1, "\n".join([
            "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 0, do zrobienia: 0", BLAD_LISTY % R1, BLAD_LISTY % R2,
            "NIC DO ZROBIENIA", "REZERWA_CEO: NIE – nic nie czeka na scalenie"]) + "\n", ""))
        kod, out, _ = self.main("miary", "--json")
        self.assertEqual((kod, json.loads(out)["bledy_gh"]), (0, [R1, R2]))

    def test_caly_przebieg_jak_w_zadaniu_zaplanowanym(self):
        """Kroki treści zadania po kolei. Czynności agenta w GitHubie (scalenie, zmiana bazy) odgrywa podmiana danych atrapy –
        skrypt sam niczego w GitHubie nie zmienia i ten test pilnuje tego na liście wywołań `gh`."""
        gh = self.zwykly_dzien()
        gh.update({"pr view 15 -R %s" % R1: pr(15, base="agent/inzynier-rodzic", galaz="agent/inzynier-dziecko"),
                   "pr view 17 -R %s" % R1: dict(pr(17, pliki=("src/b.py",)), state="OPEN")})
        self.ustaw_github(gh)
        self.assertEqual(self.blokuj(), [])
        kod, out, _ = self.main("tabela", repo=self.wt)
        linie = out.splitlines()
        self.assertEqual((kod, linie[0]), (0, "KOLEJKA SCALANIA 2026-11-09 10:00 – otwarte PR-y: 9, do zrobienia: 8"))
        self.assertEqual(linie[-1], "REZERWA_CEO: TAK – gotowy PR czeka 60 min, agent scalający bez śladu od ponad 45 min")
        # zgłoszenia: każdy wiersz z adresatem dostaje zlecenie; GOTOWY i PRZEPNIJ to robota agenta, nie zlecenia
        self.assertEqual(self.pisz("zglos"), (0, "".join("ZGŁOSZONO: %s (Z-20261109-%02d)\n" % (z, i) for i, z in enumerate([
            "13 KONFLIKT -> inzynier", "14 BRAK_WERDYKTU -> recenzent", "16 MIGRACJA -> ceo", "18 KOLIZJA_MIGRACJI -> ceo",
            "firma-agenci#3 WYJATEK -> ceo"], 1)), ""))
        # wiersz PRZEPNIJ: lista plików sprzed zmiany bazy, (agent zmienia bazę), odnotowanie własnej czynności
        self.assertEqual(self.pisz("przepiecie", "15"), (0, "ZAPISANO stan sprzed zmiany bazy: 15 (1 plików) – teraz polecenia z tabeli\n", ""))
        self.assertEqual(self.pisz("odnotuj", "15", "PRZEPNIJ"), (0, "ODNOTOWANO: 15 PRZEPNIJ\n", ""))
        # wiersze GOTOWY: scalenie PR-a 12 GitHub przyjął, scalenia PR-a 17 odmówił
        gh["pr view 12 -R %s" % R1] = {"number": 12, "state": "MERGED", "mergeCommit": {"oid": "d" * 40}, "headRefOid": HEAD,
                                       "mergedAt": "2026-11-09T09:05:00Z"}
        self.ustaw_github(gh)
        self.assertEqual(self.pisz("potwierdz", "12", teraz="2026-11-09T10:06"),
                         (0, "POTWIERDZONO: 12 scalony (dddddddddd), 65 min od werdyktu\n", ""))
        self.assertEqual(self.pisz("potwierdz", "17", teraz="2026-11-09T10:07"), (1, "NIE SCALONY: PR 17 ma stan OPEN – scalenia "
                         "nie zapisano; odmowę GitHuba zgłoś: zglos 17 GOTOWY --powod \"…\"\n", ""))
        self.assertEqual(self.pisz("zglos", "17", "GOTOWY", "--powod", "GitHub: head branch was modified", teraz="2026-11-09T10:07"),
                         (0, "ZGŁOSZONO: 17 GOTOWY -> ceo (Z-20261109-06)\n", ""))
        self.assertEqual(self.historia(), ["recenzent: werdykty", SZKIELET_OPIS])           # do `zapisz` nic nie trafia do gita
        kod, out, err = self.pisz("zapisz", teraz="2026-11-09T10:08")
        self.assertEqual((kod, out, err), (0, "ZAPISANE: %s (ceo/scalanie/stan.json, ceo/scalanie/dziennik.jsonl, zlecenia/inzynier.md, "
                                              "zlecenia/recenzent.md, zlecenia/ceo.md)\n" % _git(self.origin, "rev-parse", "--short=10", "main"), ""))
        self.assertEqual(self.main("odblokuj", self.token, teraz="2026-11-09T10:10"), (0, "BLOKADA zwolniona\n", ""))
        # na gałęzi głównej: jeden commit kolejki, stan, dziennik i sześć zleceń w trzech skrzynkach
        self.assertEqual(self.historia(), ["scalanie: stan kolejki 2026-11-09 10:08", "recenzent: werdykty", SZKIELET_OPIS])
        o_10 = {"kiedy": "2026-11-09 10:00"}
        self.assertEqual(json.loads(self.glowna("ceo/scalanie/stan.json")), {
            "przepiete": {"15": {"sha": HEAD, "z_bazy": "agent/inzynier-rodzic", "kiedy": "2026-11-09 10:00", "pliki": ["src/a.py"]}},
            "zgloszone": {"13": zgl("KONFLIKT", adresat="inzynier", **o_10), "14": zgl("BRAK_WERDYKTU", adresat="recenzent", **o_10),
                          "15": zgl("PRZEPNIJ", adresat="własna", **o_10), "16": zgl("MIGRACJA", **o_10),
                          "17": zgl("GOTOWY", kiedy="2026-11-09 10:07"), "18": zgl("KOLIZJA_MIGRACJI", **o_10),
                          "firma-agenci#3": zgl("WYJATEK", **o_10)}})
        self.assertEqual([json.loads(l) for l in self.glowna("ceo/scalanie/dziennik.jsonl").splitlines()], [
            {"kiedy": "2026-11-09 10:05", "klucz": "12", "repo": R1, "nr": 12, "sha": HEAD, "commit": "d" * 40, "kto": "scalanie-a",
             "werdykt": "OK", "min_od_werdyktu": 65, "czas_dokladny": True}])
        wpisy = [w for kto in ("inzynier", "recenzent", "ceo") for w in B.wpisy_z_pliku(self.wt / "zlecenia" / (kto + ".md"), self.wt)]
        self.assertEqual([(w["wlasciciel"], w["zid"], w["od"], w["pilne"]) for w in wpisy], [
            ("inzynier", "Z-20261109-01", "scalanie", False), ("recenzent", "Z-20261109-02", "scalanie", False),
            ("ceo", "Z-20261109-03", "scalanie", False), ("ceo", "Z-20261109-04", "scalanie", False),
            ("ceo", "Z-20261109-05", "scalanie", False), ("ceo", "Z-20261109-06", "scalanie", True)])
        self.assertEqual(json.loads(self.plik_tetna.read_text(encoding="utf-8")), {"kto": "scalanie-a", "kiedy_s": TERAZ_S + 600})

        # kwadrans później: PR 12 scalony, PR 15 ma już bazę główną, autor zamknął PR 13
        self.ustaw_github(self.zwykly_dzien(bez=(12, 13), pr15={"baseRefName": "main"}))
        pozniej = "2026-11-09T10:15"
        kod, out, err = self.main("tabela", teraz=pozniej)                  # ze wspólnego katalogu: stan czytany z gałęzi głównej
        self.assertEqual((kod, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            "KOLEJKA SCALANIA 2026-11-09 10:15 – otwarte PR-y: 7, do zrobienia: 1",
            rzad("15", "GOTOWY", "scal"), "    $ gh pr merge 15 --repo firma/produkt --merge --match-head-commit " + HEAD,
            "bez ruchu: BRAK_WERDYKTU (zgłoszone) 1, CI_TRWA 1, GOTOWY (zgłoszone) 1, KOLIZJA_MIGRACJI (zgłoszone) 1, "
            "MIGRACJA (zgłoszone) 1, WYJATEK (zgłoszone) 1",
            "REZERWA_CEO: NIE – agent scalający działał 5 min temu"])
        self.assertEqual(self.main("miary", teraz=pozniej), (0, "\n".join([
            "MIARY SCALANIA 2026-11-09 10:15 – ostatnie 7 dni", "scalone PR-y: 1 (scalanie-a 1)",
            "czas od werdyktu do scalenia: mediana 65 min, p90 65 min (z 1 wpisów z dokładnym czasem werdyktu)",
            "otwarte zgłoszenia kolejki: 7 · wstrzymania CEO: 0",
            "PR-y z werdyktem OK niescalone ponad 2 h: 0 (próg 3) – OK", "PR-y w konflikcie: 0 (próg 3) – OK",
            "minuty od ostatniego przebiegu agenta scalającego: 5 (próg 45) – OK"]) + "\n", ""))
        # następny przebieg: nic się nie dubluje, a zapis o zamkniętym PR-ze 13 znika ze stanu
        self.assertEqual(self.blokuj(teraz=pozniej), [])
        self.assertEqual(self.pisz("zglos", teraz=pozniej), (0, "NIC DO ZGŁOSZENIA\n", ""))
        kod, out, err = self.pisz("zapisz", teraz=pozniej)
        self.assertEqual((kod, out, err), (0, "ZAPISANE: %s (ceo/scalanie/stan.json)\n" % _git(self.origin, "rev-parse", "--short=10", "main"), ""))
        self.assertEqual(self.main("odblokuj", self.token, teraz=pozniej), (0, "BLOKADA zwolniona\n", ""))
        self.assertEqual(sorted(json.loads(self.glowna("ceo/scalanie/stan.json"))["zgloszone"]), ["14", "15", "16", "17", "18", "firma-agenci#3"])
        self.assertEqual(sum(self.glowna("zlecenia/%s.md" % kto).count("## [otwarte]") for kto in ("inzynier", "recenzent", "ceo")), 6)
        self.assertEqual(_git(self.origin, "show", "--name-only", "--format=", "main").splitlines(), ["ceo/scalanie/stan.json"])
        # skrypt tylko czytał GitHuba: listy, pojedyncze PR-y i zapytania GET do API – ani jednego polecenia, które coś zmienia
        self.wolania()
        self.assertGreater(len(self.wszystkie), 30)
        for a in self.wszystkie:
            self.assertTrue(a[:2] in (["pr", "list"], ["pr", "view"]) or a[0] == "api", a)
            self.assertFalse({"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"} & set(a), a)
        self.assertFalse(self.blokada.exists())
        self.assertEqual(self.oczekujace(), [])
        self.wspolny_nietkniety()


# ---------- bramka scalania (pyta ją hook uprawnień) i zatrzymanie awaryjne ----------

def scal(nr=12, head=HEAD, repo_gh=R1, metoda="--merge", inne=""):
    """Polecenie scalenia w postaci z tabeli kolejki."""
    return "gh pr merge %d --repo %s %s --match-head-commit %s%s" % (nr, repo_gh, metoda, head, inne)


class RozbiorScalenia(unittest.TestCase):
    def test_postac_z_tabeli_w_kazdym_dozwolonym_zapisie(self):
        self.assertEqual(S.rozbierz_scalenie(scal()), ((R1, 12, HEAD, "merge"), ""))
        self.assertEqual(S.rozbierz_scalenie("cd /tmp && gh pr merge -R %s --squash --match-head-commit=%s 7 2>&1" % (R2, HEAD.upper())),
                         ((R2, 7, HEAD, "squash"), ""))
        self.assertEqual(S.rozbierz_scalenie(scal(metoda="--rebase") + " && echo scalone"), ((R1, 12, HEAD, "rebase"), ""))

    def test_kazdy_inny_skladnik_to_odmowa_z_powodem(self):
        for polecenie, fragment in (
                ("gh pr merge 12 --repo %s --merge" % R1, "brakuje: --match-head-commit"),
                ("gh pr merge --repo %s --merge --match-head-commit %s" % (R1, HEAD), "brakuje: numer PR-a"),
                ("gh pr merge 12 --merge --match-head-commit %s" % HEAD, "brakuje: --repo"),
                (scal(metoda=""), "brakuje: metoda"),
                (scal(head="abc1234"), "oczekiwany pełny SHA commita"),
                (scal(repo_gh="produkt"), "oczekiwane właściciel/nazwa"),
                (scal(inne=" --admin"), "niedozwolony składnik „--admin”"),
                (scal(inne=" --auto"), "niedozwolony składnik „--auto”"),
                (scal(inne=" --delete-branch"), "niedozwolony składnik „--delete-branch”"),
                (scal(inne=" 13"), "więcej niż jeden numer PR-a"),
                (scal(inne=" --squash"), "więcej niż jedna metoda scalenia"),
                (scal(inne=" --repo inna/firma"), "--repo podane dwa razy"),
                (scal(inne=" --match-head-commit " + HEAD2), "--match-head-commit podane dwa razy"),
                (scal(inne=" --match-head-commit"), "bez wartości"),
                (scal(head="$(git rev-parse HEAD)"), "podstawienia i przekierowania powłoki"),
                (scal(inne=" > /tmp/wynik"), "podstawienia i przekierowania powłoki"),
                (scal(inne=" --body 'niedomknięty"), "nieczytelne cudzysłowy"),
                (scal() + " ; " + scal(13), "jedno scalenie na polecenie (znaleziono 2)"),
                ("gh pr list --search merge", "jedno scalenie na polecenie (znaleziono 0)"),
                ("gh -R %s pr merge 12 --merge --match-head-commit %s" % (R1, HEAD), "flagi między `gh pr` a `merge`"),
                (None, "jedno scalenie na polecenie (znaleziono 0)")):
            wyn, powod = S.rozbierz_scalenie(polecenie)
            self.assertIsNone(wyn, polecenie)
            self.assertIn(fragment, powod, polecenie)
            self.assertIn(S.WZOR_SCALENIA, powod)                       # odmowa zawsze mówi, jaka postać jest dozwolona


class Bramka(UkladFloty):
    """Prawdziwy git (werdykty i ustawienia z gałęzi głównej), fakty o PR-ach wstrzyknięte – GitHuba nikt nie pyta."""

    def setUp(self):
        super().setUp()
        self.podstaw_gh()
        self.gh_odp[("api", "repos/%s/git/trees/main?recursive=1" % R1)] = (0, "migrations/0001_start.sql\n", "")
        self.cudzy_commit("recenzent/stan.json", json.dumps({"recenzje": {
            "12": werdykt(),
            "13": werdykt(scalenie="warunek", warunki=["po zmianie konfiguracji usługi"]),
            "15": werdykt(klasa_migracji={"migrations/0002_tabela.sql": "B"}),
            "16": werdykt(klasa_migracji={"migrations/0003_indeks.sql": "A"}),
            "firma-agenci#3": werdykt()}}) + "\n", "recenzent: werdykty")
        _git(self.repo, "fetch", "-q", "origin")
        self.prs = {(R1, 12): pr(12), (R1, 13): pr(13), (R1, 14): pr(14),
                    (R1, 15): pr(15, pliki=("migrations/0002_tabela.sql",)),
                    (R1, 16): pr(16, pliki=("migrations/0003_indeks.sql",)),
                    (R2, 3): pr(3, pliki=("uprawnienia.yaml",))}
        self.stan_glownej, self.pobrane = ("OK", "c" * 40), True

    def bramka(self, polecenie=None, rola="inzynier", decyzja=False, repo=None, teraz_s=TERAZ_S + 60):
        return S.bramka(repo or self.repo, polecenie or scal(), rola, decyzja, TERAZ, teraz_s,
                        f_pr=lambda r, n: self.prs.get((r, n)), f_glowna=lambda r, ust: self.stan_glownej,
                        f_otwarte=lambda r: [p for (rr, _), p in sorted(self.prs.items()) if rr == r],
                        f_fetch=lambda kat: self.pobrane)

    def odmowa(self, fragment, *a, **kw):
        wolno, powod = self.bramka(*a, **kw)
        self.assertFalse(wolno, powod)
        self.assertIn(fragment, powod)
        return powod

    def zmien_blokade(self, kto):
        shutil.rmtree(self.blokada, ignore_errors=True)
        self.assertEqual(self.wez(kto)[0], 0)

    def test_gotowy_dla_kazdej_roli_ale_tylko_pod_wazna_blokada(self):
        self.odmowa("brak ważnej blokady scalania")
        self.wez()
        for rola in ("inzynier", "ceo", "obsluga", ""):
            self.assertEqual(self.bramka(rola=rola), (True, "GOTOWY %s#12 %s" % (R1, HEAD[:10])))
        self.assertTrue(self.bramka(scal(repo_gh=R1.upper()))[0])           # wielkość liter w nazwie repozytorium bez znaczenia
        self.assertTrue(self.bramka(teraz_s=TERAZ_S + 30 * 60)[0])          # dokładnie na progu blokada jeszcze ważna
        self.odmowa("brak ważnej blokady scalania", teraz_s=TERAZ_S + 31 * 60)
        self.assertEqual(self.gh_wolania, [])

    def test_tylko_polecenie_z_tabeli_dla_biezacego_commita(self):
        self.wez()
        for polecenie, fragment in (
                (scal(repo_gh="obca/firma"), "nie należy do organizacji"),
                (scal(metoda="--squash"), "metoda --squash, a ustawienia kolejki wymagają --merge"),
                (scal(head=HEAD2), "nie jest aktualnym commitem PR-a"),
                (scal(99), "GitHub nie zwrócił PR-a %s#99" % R1),
                (scal(inne=" --admin"), "niedozwolony składnik"),
                ("gh pr merge 12 --repo %s --merge" % R1, "brakuje: --match-head-commit")):
            self.odmowa(fragment, polecenie)
        self.pobrane = False
        self.assertEqual(self.bramka(), (False, "git fetch nie powiódł się – werdykty i wstrzymania mogły się zmienić; spróbuj ponownie"))

    def test_fakty_o_pr_zmieniaja_klase_i_gotowy_przestaje_przechodzic(self):
        self.wez("ceo-czat")
        for zmiana, klasa in ((dict(ci="FAILURE"), "CI_CZERWONE"), (dict(mergeable="CONFLICTING"), "KONFLIKT"),
                              (dict(ci=None), "BRAK_CI"), (dict(szkic=True), "SZKIC"), (dict(head=HEAD2), None)):
            self.prs[(R1, 12)] = pr(12, **zmiana)
            for rola in ("inzynier", "ceo"):                                # tych klas nie scala nikt, CEO też nie
                self.odmowa("ma klasę %s" % klasa if klasa else "nie jest aktualnym commitem PR-a", rola=rola)
        self.odmowa("ma klasę BRAK_WERDYKTU", scal(14), rola="ceo")

    def test_czerwona_galaz_glowna_zatrzymuje_linie_poza_ceo(self):
        self.wez("ceo-czat")
        self.stan_glownej = ("CZERWONE", "d" * 40)
        self.odmowa("ma klasę GLOWNA_CZERWONA")
        self.assertEqual(self.bramka(rola="ceo"), (True, "GLOWNA_CZERWONA %s#12 %s – ścieżka CEO" % (R1, HEAD[:10])))
        self.stan_glownej = (None, "")                                      # stan nieznany nie zatrzymuje (opisane ograniczenie)
        self.assertTrue(self.bramka()[0])

    def test_sciezka_ceo_wymaga_roli_i_wlasnej_blokady(self):
        self.wez()                                                          # blokadę trzyma agent scalający
        powod = self.odmowa("ma klasę WARUNEK", scal(13))
        self.assertIn("adresat: ceo; bez decyzji CEO scala się tylko klasę GOTOWY", powod)
        self.odmowa("wymaga blokady wziętej jako ceo-czat albo ceo-przebieg (teraz trzyma ją „scalanie-a”)", scal(13), rola="ceo")
        self.zmien_blokade("ceo-przebieg")
        self.assertEqual(self.bramka(scal(13), rola="ceo"), (True, "WARUNEK %s#13 %s – ścieżka CEO" % (R1, HEAD[:10])))
        self.odmowa("ma klasę WARUNEK", scal(13), rola="inzynier")           # blokada CEO nie daje uprawnień innej roli
        self.odmowa("ma klasę WARUNEK", scal(13), rola="")

    def test_zasady_uprawnienia_i_migracja_b_tylko_z_decyzja_wlasciciela(self):
        self.zmien_blokade("ceo-czat")
        p = scal(3, repo_gh=R2)
        self.odmowa("potrzebna decyzja właściciela (prefiks DECYZJA=D-RRRRMMDD-NN przed poleceniem): zasady i uprawnienia: uprawnienia.yaml",
                    p, rola="ceo")
        self.assertEqual(self.bramka(p, rola="ceo", decyzja=True),
                         (True, "WYJATEK %s#3 %s – ścieżka CEO z decyzją właściciela" % (R2, HEAD[:10])))
        self.odmowa("ma klasę WYJATEK", p, rola="inzynier", decyzja=True)    # sama decyzja nie zastępuje roli
        self.odmowa("potrzebna decyzja właściciela", scal(15), rola="ceo")
        self.assertIn("migracja klasy B albo bez klasy", self.bramka(scal(15), rola="ceo")[1])
        self.assertEqual(self.bramka(scal(15), rola="ceo", decyzja=True),
                         (True, "MIGRACJA %s#15 %s – ścieżka CEO z decyzją właściciela" % (R1, HEAD[:10])))
        self.assertEqual(self.bramka(scal(16), rola="ceo"), (True, "MIGRACJA %s#16 %s – ścieżka CEO" % (R1, HEAD[:10])))
        self.odmowa("ma klasę MIGRACJA", scal(16))                           # agent scalający migracji nie scala nigdy

    def test_kolizja_numerow_migracji_i_brak_listy_pr(self):
        self.zmien_blokade("ceo-czat")
        self.prs[(R1, 16)] = pr(16, pliki=("migrations/0001_inna.sql",))     # numer 0001 jest już na gałęzi głównej
        self.odmowa("ma klasę KOLIZJA_MIGRACJI", scal(16), rola="ceo")
        self.gh_odp[("api", "repos/%s/git/trees/main?recursive=1" % R1)] = (1, "", "błąd")
        self.odmowa("ma klasę NIEZNANY", scal(16), rola="ceo")

    def test_wstrzymanie_ceo_i_nieczytelny_rejestr_zatrzymuja_takze_gotowy(self):
        self.wez("ceo-czat")
        self.cudzy_commit("ceo/scalanie/wstrzymane.json", json.dumps({"wstrzymane": {"12": {"powod": "czeka na dane", "sha": "",
                          "tryb": "odwolanie", "kiedy": "2026-11-09 09:30"}}}) + "\n", "ceo: wstrzymanie")
        _git(self.repo, "fetch", "-q", "origin")
        for rola in ("inzynier", "ceo"):
            self.odmowa("ma klasę WSTRZYMANY", rola=rola)
        self.cudzy_commit("ceo/scalanie/wstrzymane.json", "{to nie jest json\n", "zepsuty rejestr")
        _git(self.repo, "fetch", "-q", "origin")
        self.odmowa("ma klasę", rola="inzynier")
        self.assertFalse(self.bramka(rola="ceo")[0])

    def test_blad_w_bramce_i_brak_czasu_to_odmowa(self):
        self.wez()
        self.assertEqual(S.bramka(self.repo, scal(), "ceo", False, TERAZ, TERAZ_S, f_pr=lambda r, n: 1 / 0, f_fetch=lambda kat: True),
                         (False, "błąd bramki scalania (ZeroDivisionError) – zgłoś CEO"))
        with mock.patch.object(S, "BRAMKA_TERMIN_S", 0):
            self.assertEqual(self.bramka(), (False, "bramka nie zdążyła sprawdzić faktów w 0 s – spróbuj ponownie"))
        self.assertIsNone(S.TERMIN)                                          # termin nie zostaje po bramce

    def test_lokalna_zmiana_ustawien_niczego_nie_otwiera(self):
        self.wez()
        plik = self.repo / "ceo" / "scalanie" / "ustawienia.yaml"
        plik.write_text(plik.read_text(encoding="utf-8").replace("metoda: merge", "metoda: squash"), encoding="utf-8")
        self.assertEqual(S.ustawienia(self.repo)["metoda"], "squash")
        self.assertEqual(S.ustawienia_uzgodnione(self.repo)["metoda"], "merge")
        self.assertTrue(self.bramka()[0])
        self.odmowa("ustawienia kolejki wymagają --merge", scal(metoda="--squash"))

    def test_polecenie_bramka_wypisuje_werdykt_i_kod(self):
        with mock.patch.object(S, "bramka", lambda repo, polecenie, **kw: (True, "GOTOWY x#1")):
            self.assertEqual(self.main("bramka", scal(), teraz=None)[:2], (0, "WOLNO: GOTOWY x#1\n"))
        with mock.patch.object(S, "bramka", lambda repo, polecenie, **kw: (False, "brak blokady")):
            self.assertEqual(self.main("bramka", scal(), teraz=None)[:2], (1, "ZABLOKOWANE: brak blokady\n"))


class ZatrzymanieAwaryjne(UkladFloty):
    """bezpieczenstwo/HALT zatrzymuje także kolejkę: blokady się nie bierze, bramka niczego nie przepuszcza –
    również z prywatnego katalogu roboczego, w którym lokalnego pliku HALT hook uprawnień nie widzi."""

    def setUp(self):
        super().setUp()
        self.podstaw_gh()

    def halt(self, tresc="incydent: wyciek klucza"):
        (self.repo / "bezpieczenstwo").mkdir(exist_ok=True)
        (self.repo / "bezpieczenstwo" / "HALT").write_text(tresc + "\n", encoding="utf-8")

    def test_blokady_nie_da_sie_wziac(self):
        self.halt()
        kod, out, err = self.main("blokada", "scalanie-a", "--protokol", "1")
        self.assertEqual((kod, err), (14, ""))
        self.assertEqual(out, "FLOTA ZATRZYMANA (bezpieczenstwo/HALT): incydent: wyciek klucza – blokady nie wzięto; plik usuwa operator\n")
        self.assertFalse(self.blokada.exists())
        self.assertFalse(self.plik_tetna.exists())
        self.assertFalse(self.katalog.exists())
        (self.repo / "bezpieczenstwo" / "HALT").unlink()
        self.assertEqual(self.blokuj(), [])                                  # po zdjęciu pliku kolejka rusza bez niczyjej pomocy

    def test_halt_po_wzieciu_blokady_widac_z_katalogu_roboczego(self):
        self.blokuj()
        self.assertIsNone(S.stop_awaryjny(self.wt))
        self.halt("")                                                        # pusty plik też zatrzymuje
        self.assertEqual(S.stop_awaryjny(self.repo), "HALT")
        self.assertEqual(S.stop_awaryjny(self.wt), "HALT")                   # prywatny worktree → wspólny katalog
        for kat in (self.wt, self.repo):
            wolno, powod = S.bramka(kat, scal(), "ceo", True, TERAZ, TERAZ_S, f_pr=lambda r, n: pr(12), f_fetch=lambda k: True)
            self.assertEqual((wolno, powod), (False, "flota zatrzymana (bezpieczenstwo/HALT): HALT – niczego nie scalamy; plik usuwa operator"))
        self.assertEqual(self.gh_wolania, [])

    def test_katalog_bez_gita_sprawdza_tylko_siebie(self):
        obok = self.tmp / "bez-gita"
        (obok / "bezpieczenstwo").mkdir(parents=True)
        self.assertIsNone(S.stop_awaryjny(obok))
        (obok / "bezpieczenstwo" / "HALT").write_text("stop „teraz” `rm -rf`\n", encoding="utf-8")
        self.assertEqual(S.stop_awaryjny(obok), "stop „teraz” ?rm -rf?")       # treść pliku to dane – oczyszczona
