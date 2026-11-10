#!/usr/bin/env python3
"""Hook PreToolUse/PostToolUse: egzekwuje `uprawnienia.yaml` i zakazy z `zasady.md` deterministycznie, zanim narzędzie
się wykona, i prowadzi audyt KAŻDEJ decyzji (allow/deny, pre- i post-execution) w łańcuchu hashy.

Claude Code wywołuje go przed każdym narzędziem (.claude/settings.json, matcher "*", onFailure: block – awaria hooka
blokuje narzędzie). Na stdin JSON {hook_event_name, tool_name, tool_input, tool_use_id, session_id, cwd, agent_id…}.
Kod wyjścia 0 = wolno, 2 = ZABLOKOWANE (komunikat na stderr trafia do agenta). JSON {"continue": false} = zatrzymanie sesji
(kill switch). Bez LLM, bez sieci (wyjątek: `git fetch` i `gh` przy scalaniu PR-a). Test: python3 -I .claude/hooks/test_uprawnienia.py

Rola agenta (kolejno): zmienna AGENT_ROLA; plik `.agent-rola` w repo (pisze `scripts/przebieg.sh start <agent>`; czat:
`echo ceo > .agent-rola`); brak = „nieznany” (tylko czynności `sam` bez listy agentów).
Zgoda właściciela: DECYZJA=D-RRRRMMDD-NN w środowisku albo jako prefiks polecenia – ID musi istnieć w `decyzje.md`;
odblokowuje poziomy `ceo` i `wlasciciel`. Poziom `operator`, `nigdy` i zakazy git nie mają wyjątków.
Bramki deterministyczne (uprawnienia.yaml → `bramka:`): `kwota` (kwota z polecenia ≤ próg z polityki/progi.yaml),
`pr` (o scaleniu decyduje kolejka: `scripts/scalanie.py` → `bramka` – tylko polecenie z tabeli, dla aktualnego commita,
pod blokadą scalania; klasa GOTOWY dla każdej roli, pozostałe tylko CEO; opis: ceo/scalanie/README.md).
Polecenie złożone (`a && b`, `a; b`, `a | b`): sprawdzana jest każda czynność osobno – jedna odmowa blokuje całość.
Kill switch: plik `bezpieczenstwo/HALT` (treść = powód) → każde narzędzie poza odczytem zablokowane, sesja zatrzymana.
Detekcja pętli: to samo polecenie Bash ≥ LIMIT_POWTORZEN razy z rzędu w jednej sesji → ZABLOKOWANE (incydent #15909).
Audyt: `bezpieczenstwo/audyt/RRRR-MM.jsonl` (merge=union), każdy rekord z `prev_hash` i `hash` (SHA-256 łańcuch).
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LIMIT_POWTORZEN = 3
AUDYT_OGON_LINII = 400

# Zakazy bezwzględne (zasady.md, „Git” i pkt 3) – niezależnie od roli i decyzji.
ZAKAZANE = [
    (r"\bgit\b[^|;&]*\breset\b[^|;&]*--hard", "git reset --hard"),
    (r"\bgit\b[^|;&]*\bstash\b", "git stash"),
    (r"\bgit\b[^|;&]*\bclean\b", "git clean"),
    (r"\bgit\b[^|;&]*\bcheckout\b[^|;&]*\s--\s+\.(\s|$)", "git checkout -- ."),
    (r"\bgit\b[^|;&]*\brestore\b[^|;&]*(\s\.(\s|$)|--staged\s+\.)", "git restore ."),
    (r"\bgit\b[^|;&]*\bpush\b[^|;&]*(\s-f\b|--force)", "git push --force"),
    (r"\bgit\b[^|;&]*\badd\b[^|;&]*(\s-A\b|--all\b|\s\.(\s|$))", "git add -A / git add ."),
    (r"\bgit\b[^|;&]*\bbranch\b[^|;&]*\s-D\b", "git branch -D"),
    (r"\brm\b[^|;&]*\s-[a-zA-Z]*r[a-zA-Z]*f?[^|;&]*\s(/|~|\$HOME)(\s|$)", "rm -rf katalogu domowego lub /"),
    (r"(\bcat\b|\bless\b|\bhead\b|\btail\b|\bsource\b|\bexport\b)[^|;&]*(\.env\b|~/\.ssh/|~/\.aws/|id_rsa|id_ed25519)", "odczyt pliku z sekretami"),
    (r"(?i)\bpulls/\d+/merge\b|\b(mergePullRequest|enablePullRequestAutoMerge|enqueuePullRequest)\b",
     "scalenie PR-a poza kolejką (API GitHuba) – scala się tylko poleceniem z tabeli: python3 -I scripts/scalanie.py; stan PR-a: gh pr view <nr> --json state"),
]

# Mapowanie polecenia Bash → czynność z uprawnienia.yaml (pierwsze dopasowanie wygrywa).
WZORCE_BASH = [
    # ten sam wzorzec co RE_SCAL w scripts/scalanie.py (flaga -R/--repo może stać przed `pr` i przed `merge`)
    (r"\bgh\b(?:\s+(?:-R|--repo)(?:\s+|=)\S+)*\s+pr\b(?:\s+(?:-R|--repo)(?:\s+|=)\S+)*\s+merge\b", "pr_scalenie_bez_migracji"),
    (r"\bgh\s+pr\s+create\b", "pr_otwarcie"),
    (r"\bgh\s+(repo\s+edit|secret\s+set|variable\s+set|api\b[^|;&]*-X\s*(PUT|PATCH|DELETE))", "zmiana_ustawien_uslugi"),
    (r"\bgh\s+release\s+create\b", "wdrozenie_produkcja"),
    (r"\b(fly\s+deploy|vercel\b[^|;&]*--prod|wrangler\s+(deploy|publish)|netlify\s+deploy[^|;&]*--prod|supabase\s+functions\s+deploy)", "wdrozenie_produkcja"),
    (r"\bsupabase\s+(db\s+push|migration\s+up)\b", "migracja_zgodna_wstecz"),
    (r"\b(psql|supabase\s+db\s+execute)\b[^|;&]*\b(DROP|TRUNCATE|DELETE\s+FROM)\b", "migracja_niszczaca_dane"),
    (r"\b(psql|supabase\s+db\s+execute)\b[^|;&]*\b(ALTER|CREATE|INSERT|UPDATE)\b", "migracja_zgodna_wstecz"),
    (r"api\.resend\.com/(emails|broadcasts)", "wysylka_maila"),
    (r"api\.stripe\.com/v1/refunds|\bstripe\s+refunds\s+create\b", "zwrot_klientowi"),
    (r"api\.stripe\.com/v1/(prices|products|coupons)[^|;&]*(-X\s*(POST|DELETE)|-d\s)|\bstripe\s+(prices|products|coupons)\s+(create|update|delete)\b", "zmiana_cen"),
    (r"api\.stripe\.com/v1/(transfers|payouts)|\bstripe\s+(transfers|payouts)\s+create\b", "przelew"),
    (r"\b(xcrun\s+altool|fastlane\s+(deliver|supply|pilot)|eas\s+submit)\b", "wydanie_w_sklepach"),
    (r"\b(ssh|scp)\b[^|;&]*\b(prod|produkcja|vps)\b", "wdrozenie_produkcja"),
    (r"\bcurl\b[^|;&]*-X\s*(POST|PUT|PATCH|DELETE)\b", "zmiana_ustawien_uslugi"),  # każdy inny zapis przez HTTP
]

# Narzędzia MCP (nazwa `mcp__<serwer>__<narzędzie>`) → czynność.
WZORCE_MCP = [
    (r"__(send-email|send-batch-emails|send-new-inbox-email|reply-to-inbox-thread-email|forward-inbox-thread-email|send-inbox-draft|send_message|reply|forward)$", "wysylka_maila"),
    (r"__(send-broadcast|create-broadcast)$", "wysylka_masowa"),
    (r"__(apply_migration|execute_sql)$", "migracja_zgodna_wstecz"),
    (r"__(deploy_edge_function|merge_branch|delete_branch|reset_branch|pause_project|restore_project)$", "wdrozenie_produkcja"),
    (r"__(create_project|create-domain|remove-domain|update-domain|create-api-key|remove-api-key|create-webhook|update-webhook|remove-webhook|revoke-oauth-grant)$", "zmiana_ustawien_uslugi"),
    (r"__stripe_api_write$", "zmiana_ustawien_uslugi"),
    (r"__manage_stripe_accounts$", "zmiana_ustawien_uslugi"),
    (r"__(create_scheduled_task|update_scheduled_task|delete_scheduled_task)$", "nowy_agent_lub_zadanie_cykliczne"),
    (r"__(trash_|delete_|remove-contact|remove-segment|remove-template|remove-topic|remove-automation)", "kasowanie_danych_osobowych"),
    (r"__(mark_.*spam|label_|unlabel_|update_message_labels|create_label|update_label|add-suppression|batch-add-suppressions)", "zmiana_ustawien_uslugi"),
]
NARZEDZIA_ODCZYTU = {"Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch", "TodoRead", "TaskList", "TaskGet", "ToolSearch"}


# ---------- konfiguracja z repo ----------

def katalog_repo(cwd):
    p = Path(cwd or ".").resolve()
    for k in (p, *p.parents):
        if (k / "uprawnienia.yaml").exists():
            return k
    return None


def czytaj_uprawnienia(repo):
    """Wiersze `nazwa: { poziom: X, agenci: [a, b], sam: [c], bramka: kwota|pr, warunki: "…" }` -> {nazwa: {...}}."""
    wynik = {}
    tekst = (repo / "uprawnienia.yaml").read_text(encoding="utf-8")
    for m in re.finditer(r"^\s{2}([a-z0-9_]+):\s*\{(.*)\}\s*$", tekst, re.M):
        nazwa, cialo = m.group(1), m.group(2)
        poziom = re.search(r"\bpoziom:\s*([a-z]+)", cialo)
        agenci = re.search(r"\bagenci:\s*\[([^\]]*)\]", cialo)
        sam = re.search(r"\bsam:\s*\[([^\]]*)\]", cialo)
        bramka = re.search(r"\bbramka:\s*([a-z_]+)", cialo)
        warunki = re.search(r'warunki:\s*"([^"]*)"', cialo)
        lista = lambda mm: [a.strip() for a in mm.group(1).split(",") if a.strip()] if mm else []  # noqa: E731
        wynik[nazwa] = {"poziom": poziom.group(1) if poziom else "wlasciciel", "agenci": lista(agenci), "sam": lista(sam),
                        "bramka": bramka.group(1) if bramka else "", "warunki": warunki.group(1) if warunki else ""}
    return wynik


def czytaj_progi(repo):
    """polityki/progi.yaml: proste `klucz: liczba` (USD). Brak pliku = brak progów (bramka kwotowa nie przepuszcza)."""
    p = repo / "polityki" / "progi.yaml"
    progi = {}
    if p.exists():
        for m in re.finditer(r"^([a-z0-9_]+):\s*([0-9]+(?:\.[0-9]+)?)", p.read_text(encoding="utf-8"), re.M):
            progi[m.group(1)] = float(m.group(2))
    return progi


CZYNNOSCI_ACTOR = {"wysylka_maila", "wysylka_masowa", "mail_nowy_kontrahent", "publikacja_tresci_social", "zwrot_klientowi",
                   "wydatek_ponizej_progu", "wydatek_powyzej_progu", "przelew", "zmiana_cen", "wdrozenie_produkcja", "wydanie_w_sklepach",
                   "migracja_zgodna_wstecz", "migracja_niszczaca_dane", "pr_scalenie_bez_migracji", "zmiana_ustawien_uslugi",
                   "faktura_wystawienie", "kasowanie_danych_osobowych", "nowy_agent_lub_zadanie_cykliczne"}


def typ_agenta(repo, rola_):
    """flota/zadania.yaml → typ (reader|actor|researcher) agenta o katalogu = rola; brak = actor (zgodność wstecz)."""
    try:
        man = (repo / "flota" / "zadania.yaml").read_text(encoding="utf-8")
    except OSError:
        return "actor"
    for blok in re.split(r"^- agent:", man, flags=re.M)[1:]:
        kat = re.search(r"^\s*katalog:\s*([a-z0-9-]+)", blok, re.M)
        if kat and kat.group(1) == rola_:
            typ = re.search(r"^\s*typ:\s*([a-z]+)", blok, re.M)
            return typ.group(1) if typ else "actor"
    return "actor"


def rola(repo):
    r = os.environ.get("AGENT_ROLA", "").strip()
    if not r and repo and (repo / ".agent-rola").exists():
        linie = (repo / ".agent-rola").read_text(encoding="utf-8").strip().splitlines()
        r = linie[0].strip() if linie else ""
    return re.sub(r"[^a-z0-9-]", "", r.lower()) or "nieznany"


def decyzja_z_srodowiska(repo, polecenie=""):
    kandydat = os.environ.get("DECYZJA", "")
    m = re.search(r"(?:^|\s)DECYZJA=(D-\d{8}-\d{2})\b", polecenie)
    if m:
        kandydat = m.group(1)
    if not re.fullmatch(r"D-\d{8}-\d{2}", kandydat or ""):
        return None
    plik = repo / "decyzje" / (kandydat + ".md")
    if plik.exists():  # rejestr katalogowy: liczy się tylko status accepted
        try:
            fm = plik.read_text(encoding="utf-8").split("---")[1] if plik.read_text(encoding="utf-8").startswith("---") else ""
        except OSError:
            return None
        return kandydat if re.search(r"^status:\s*accepted\b", fm, re.M) else None
    try:
        tekst = (repo / "decyzje.md").read_text(encoding="utf-8")  # zgodność wstecz: nagłówek ### D-… w pliku
    except OSError:
        return None
    return kandydat if re.search(r"^###\s+%s\b" % re.escape(kandydat), tekst, re.M) else None


# ---------- rozpoznanie czynności ----------

def czynnosc_z_wejscia(nazwa_narzedzia, wejscie):
    """-> (rodzaj: ZAKAZANE|CZYNNOSC|WOLNO, czynność/opis, szczegół)."""
    if nazwa_narzedzia == "Bash":
        cmd = str(wejscie.get("command", ""))
        for wzor, opis in ZAKAZANE:
            if re.search(wzor, cmd):
                return "ZAKAZANE", opis, cmd
        for wzor, cz in WZORCE_BASH:
            if re.search(wzor, cmd, re.I):
                return "CZYNNOSC", cz, cmd
        return "WOLNO", "", cmd
    if nazwa_narzedzia.startswith("mcp__"):
        for wzor, cz in WZORCE_MCP:
            if re.search(wzor, nazwa_narzedzia):
                return "CZYNNOSC", cz, nazwa_narzedzia
        return "WOLNO", "", nazwa_narzedzia  # nieznane/odczytowe narzędzie MCP – strażnik i recenzent widzą skutki
    if nazwa_narzedzia in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "WOLNO", "", str(wejscie.get("file_path", ""))
    return "WOLNO", "", ""


def czynnosci_bash(cmd):
    """Wszystkie czynności polecenia złożonego: pierwszy pasujący wzorzec z każdego członu (człony dzielą ; & | i nowa linia)."""
    wyn = []
    for czlon in re.split(r"[;&|\n]+", str(cmd)):
        for wzor, cz in WZORCE_BASH:
            if re.search(wzor, czlon, re.I):
                if cz not in wyn:
                    wyn.append(cz)
                break
    return wyn


def kwota_z_wejscia(narzedzie, wejscie, szczegol):
    """Kwota w USD z polecenia (stripe --amount w centach; -d amount=; JSON amount) albo z wejścia MCP. None = nieznana."""
    if narzedzie == "Bash":
        m = re.search(r"(?:--amount[= ]|amount=|\"amount\"\s*:\s*)(\d+(?:\.\d+)?)", szczegol)
        if not m:
            return None
        v = float(m.group(1))
        return v / 100 if re.search(r"\bstripe\b|api\.stripe\.com", szczegol) else v
    for k in ("amount", "kwota", "amount_usd", "refund_amount"):
        v = wejscie.get(k)
        if isinstance(v, (int, float)):
            return float(v) / 100 if "stripe" in narzedzie else float(v)
    return None


def bramka_scalania(repo, polecenie, rola_, decyzja):
    """Bramka `pr`: o scaleniu decyduje kolejka (scripts/scalanie.py → bramka) – ta sama klasyfikacja, którą dostaje agent
    scalający w tabeli. -> (True, opis) albo (False, powód). Brak skryptu, wyjątek, brak czasu = odmowa."""
    skrypt = repo / "scripts" / "scalanie.py"
    if not skrypt.exists():
        return False, "brak scripts/scalanie.py – bez kolejki scalania nie scala nikt"
    try:
        import importlib.util
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("scalanie_bramka", str(skrypt))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        wolno, opis = mod.bramka(repo, polecenie, rola_=rola_, decyzja=bool(decyzja))
        return bool(wolno), str(opis)
    except Exception as e:                                  # fail-closed: błąd bramki nigdy nie otwiera scalenia
        return False, "bramka scalania nie działa (%s)" % e.__class__.__name__


# ---------- decyzja ----------

def decyduj(rodzaj, co, uprawnienia, rola_, decyzja, kwota=None, progi=None, bramka_pr=None):
    """-> (wolno: bool, komunikat, regula_id)."""
    progi = progi or {}
    if rodzaj == "ZAKAZANE":
        return False, "ZABLOKOWANE (zasady.md): %s – bez wyjątków. Pracuj we własnym worktree, commituj tylko swoje pliki." % co, "zakaz"
    if rodzaj != "CZYNNOSC":
        return True, "", "wolno"
    u = uprawnienia.get(co, {"poziom": "wlasciciel", "agenci": [], "sam": [], "bramka": "", "warunki": "czynność spoza uprawnienia.yaml"})
    poziom, agenci, warunki, bramka = u["poziom"], u["agenci"], u["warunki"], u.get("bramka", "")
    if poziom == "nigdy":
        return False, "ZABLOKOWANE: „%s” ma poziom nigdy (uprawnienia.yaml). Przygotuj dane dla operatora (operator/kolejka.md)." % co, co + ":nigdy"
    if poziom == "operator":
        return False, ("ZABLOKOWANE: „%s” wykonuje człowiek (poziom operator) – także z decyzją. Gotowe kroki do operator/kolejka.md "
                       "przez CEO. Warunki: %s" % (co, warunki or "–")), co + ":operator"
    # Bramki deterministyczne – przepuszczają samodzielnie, gdy warunek sprawdzalny jest spełniony.
    # Dotyczą ról z `sam`/`agenci`; bez żadnej listy – każdej roli. Inne role idą zwykłą ścieżką poziomów.
    bramka_dla_roli = (not agenci and not u.get("sam")) or rola_ in agenci or rola_ in u.get("sam", [])
    if bramka == "kwota" and bramka_dla_roli:
        prog = progi.get(co + "_sam_usd")
        if kwota is None:
            return False, "ZABLOKOWANE: „%s” – nie da się odczytać kwoty z polecenia; podaj --amount/amount=, bramka kwotowa wymaga kwoty." % co, co + ":kwota-nieznana"
        if prog is None:
            return False, "ZABLOKOWANE: „%s” – brak progu `%s_sam_usd` w polityki/progi.yaml (właściciel ustala)." % (co, co), co + ":brak-progu"
        if kwota <= prog:
            return True, "", co + ":kwota≤prog"
        if decyzja:
            return True, "", co + ":decyzja"
        return False, "ZABLOKOWANE: „%s” na %.2f USD > próg %.2f USD (polityki/progi.yaml) – do właściciela (ceo/do-decyzji.md); z decyzją: DECYZJA=D-… <polecenie>." % (co, kwota, prog), co + ":kwota>prog"
    if bramka == "pr" and bramka_dla_roli:
        ok, powod = bramka_pr if bramka_pr is not None else (False, "bramka pr nie sprawdzona")
        if ok:
            return True, "", co + ":bramka"
        return False, ("ZABLOKOWANE: „%s” – %s. Scala się tylko poleceniem z tabeli kolejki (python3 -I scripts/scalanie.py), "
                       "pod blokadą scalania; opis: ceo/scalanie/README.md." % (co, powod)), co + ":pr"
    if rola_ in u.get("sam", []):
        return True, "", co + ":sam"
    if poziom == "sam":
        if not agenci or rola_ in agenci:
            return True, "", co + ":sam"
        return False, ("ZABLOKOWANE: „%s” wolno agentom %s, Twoja rola: %s. Zleć właściwemu agentowi (zlecenia/README.md)."
                       % (co, ", ".join(agenci), rola_)), co + ":inna-rola"
    if poziom == "ceo" and rola_ == "ceo":
        return True, "", co + ":ceo"
    if decyzja and agenci and rola_ not in agenci and rola_ != "ceo":
        return False, "ZABLOKOWANE: „%s” z decyzją %s wykonują agenci %s (rola: %s)." % (co, decyzja, ", ".join(agenci), rola_), co + ":inna-rola"
    if decyzja:
        return True, "", co + ":decyzja"
    gdzie = {"ceo": "zgłoś CEO – wykona albo wpisze [Decyzja CEO] w decyzje.md; z ID decyzji: DECYZJA=D-… <polecenie>",
             "wlasciciel": "wpis w ceo/do-decyzji.md przez CEO; po decyzji D-… w decyzje.md: DECYZJA=D-… <polecenie>"}.get(poziom, "uprawnienia.yaml")
    war = (" Warunki: %s." % warunki) if warunki else ""
    return False, "ZABLOKOWANE: „%s” ma poziom %s (rola: %s). %s.%s" % (co, poziom, rola_, gdzie, war), co + ":" + poziom


# ---------- audyt (łańcuch hashy), HALT, pętle ----------

def plik_audytu(repo, teraz):
    return repo / "bezpieczenstwo" / "audyt" / ("%s.jsonl" % teraz.strftime("%Y-%m"))


def ogon_audytu(repo, teraz, n=AUDYT_OGON_LINII):
    p = plik_audytu(repo, teraz)
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            rozmiar = f.tell()
            f.seek(max(0, rozmiar - 200 * n))
            linie = f.read().decode("utf-8", "replace").splitlines()[-n:]
    except OSError:
        return []
    wynik = []
    for l in linie:
        try:
            wynik.append(json.loads(l))
        except ValueError:
            continue
    return wynik


def zapisz_audyt(repo, teraz, rekord, ogon):
    prev = ogon[-1].get("hash", "") if ogon else ""
    rekord["prev_hash"] = prev
    tresc = json.dumps(rekord, ensure_ascii=False, sort_keys=True)
    rekord["hash"] = hashlib.sha256((prev + tresc).encode("utf-8")).hexdigest()
    try:
        p = plik_audytu(repo, teraz)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rekord, ensure_ascii=False) + "\n")
    except OSError:
        pass


def zapisz_blokade(repo, rola_, narzedzie, co, szczegol):
    try:
        p = repo / "bezpieczenstwo" / "blokady.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"czas": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rola": rola_,
                                "narzedzie": narzedzie, "czynnosc": co, "szczegol": szczegol[:200]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def halt(repo):
    p = repo / "bezpieczenstwo" / "HALT"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()[:300] or "HALT"
        except OSError:
            return "HALT"
    return None


def petla(ogon, sesja, narzedzie, szczegol):
    """Ile razy z rzędu ta sesja wykonała identyczne polecenie Bash (łącznie z bieżącym)."""
    if narzedzie != "Bash" or not szczegol.strip():
        return 1
    h = hashlib.sha256(szczegol.strip().encode("utf-8")).hexdigest()
    n = 1
    for r in reversed(ogon):
        if r.get("faza") != "pre" or r.get("sesja") != sesja or r.get("narzedzie") != "Bash":
            continue
        if r.get("wejscie_hash") == h:
            n += 1
        else:
            break
    return n


# ---------- main ----------

def main():
    try:
        dane = json.load(sys.stdin)
    except ValueError:
        return 0
    narzedzie = dane.get("tool_name") or ""
    wejscie = dane.get("tool_input") or {}
    faza = "post" if dane.get("hook_event_name") == "PostToolUse" else "pre"
    repo = katalog_repo(dane.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    if repo is None:
        return 0  # poza repo organizacji hook nie działa
    teraz = datetime.now(timezone.utc)
    sesja = dane.get("session_id") or ""
    r = rola(repo)
    rodzaj, co, szczegol = czynnosc_z_wejscia(narzedzie, wejscie)
    wejscie_hash = hashlib.sha256((szczegol.strip() or json.dumps(wejscie, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
    ogon = ogon_audytu(repo, teraz)
    rekord = {"czas": teraz.isoformat(timespec="seconds"), "faza": faza, "sesja": sesja, "agent_id": dane.get("agent_id"),
              "rola": r, "narzedzie": narzedzie, "tool_use_id": dane.get("tool_use_id"), "czynnosc": co, "rodzaj": rodzaj,
              "wejscie_hash": wejscie_hash, "tryb": dane.get("permission_mode")}

    if faza == "post":
        odp = dane.get("tool_response")
        rekord["wyjscie_hash"] = hashlib.sha256(json.dumps(odp, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest() if odp is not None else None
        rekord["decyzja"] = "wykonane"
        zapisz_audyt(repo, teraz, rekord, ogon)
        return 0

    powod_halt = halt(repo)
    if powod_halt and narzedzie not in NARZEDZIA_ODCZYTU:
        rekord.update({"decyzja": "deny", "regula": "HALT"})
        zapisz_audyt(repo, teraz, rekord, ogon)
        print(json.dumps({"continue": False, "stopReason": "HALT: %s – flota zatrzymana (bezpieczenstwo/HALT); usuwa operator." % powod_halt,
                          "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": "HALT: " + powod_halt}}, ensure_ascii=False))
        return 0

    n = petla(ogon, sesja, narzedzie, szczegol)
    if n >= LIMIT_POWTORZEN:
        rekord.update({"decyzja": "deny", "regula": "petla", "powtorzenia": n})
        zapisz_audyt(repo, teraz, rekord, ogon)
        zapisz_blokade(repo, r, narzedzie, "petla", szczegol)
        print("ZABLOKOWANE: to samo polecenie %d razy z rzędu – pętla. Zmień podejście albo zakończ przebieg z wynikiem BŁĄD (incydent #15909)." % n, file=sys.stderr)
        return 2

    if rodzaj == "WOLNO":
        rekord.update({"decyzja": "allow", "regula": "wolno"})
        zapisz_audyt(repo, teraz, rekord, ogon)
        return 0

    uprawnienia = czytaj_uprawnienia(repo)
    typ = typ_agenta(repo, r)
    decyzja = decyzja_z_srodowiska(repo, szczegol if narzedzie == "Bash" else "")
    progi = czytaj_progi(repo)
    lista = [co]                                            # polecenie złożone: każda czynność przechodzi własną kontrolę
    if rodzaj == "CZYNNOSC" and narzedzie == "Bash":
        lista += [c for c in czynnosci_bash(szczegol) if c != co]
    regula, kwota = "wolno", None
    for i, cz in enumerate(lista):
        dalsza = "" if i == 0 else " (polecenie złożone – każda czynność jest sprawdzana osobno)"
        if typ in ("reader", "researcher") and cz in CZYNNOSCI_ACTOR and not (typ == "reader" and cz == "wysylka_maila" and r in uprawnienia.get("wysylka_maila", {}).get("sam", [])):
            rekord.update({"decyzja": "deny", "regula": "regula-dwoch:" + typ})
            zapisz_audyt(repo, teraz, rekord, ogon)
            zapisz_blokade(repo, r, narzedzie, cz, szczegol)
            print("ZABLOKOWANE (reguła dwóch): agent typu %s (czyta niezaufane treści / tylko jawne źródła) nie wykonuje „%s” – zleć agentowi typu actor (zlecenia/README.md).%s" % (typ, cz, dalsza), file=sys.stderr)
            return 2
        u = uprawnienia.get(cz, {})
        kw = kwota_z_wejscia(narzedzie, wejscie, szczegol) if u.get("bramka") == "kwota" else None
        czy_cz = rodzaj == "CZYNNOSC"
        bramka_pr = bramka_scalania(repo, szczegol, r, decyzja) if u.get("bramka") == "pr" and czy_cz else None
        wolno, komunikat, reg = decyduj(rodzaj if i == 0 else "CZYNNOSC", cz, uprawnienia, r, decyzja, kw, progi, bramka_pr)
        if i == 0:
            regula, kwota = reg, kw
        if not wolno:
            rekord.update({"decyzja": "deny", "regula": reg, "decyzja_id": decyzja, "kwota_usd": kw})
            zapisz_audyt(repo, teraz, rekord, ogon)
            zapisz_blokade(repo, r, narzedzie, cz, szczegol)
            print(komunikat + dalsza, file=sys.stderr)
            return 2
    rekord.update({"decyzja": "allow", "regula": regula, "decyzja_id": decyzja, "kwota_usd": kwota})
    if len(lista) > 1:
        rekord["czynnosci"] = lista
    zapisz_audyt(repo, teraz, rekord, ogon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
