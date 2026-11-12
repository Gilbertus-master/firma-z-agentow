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
Polecenie złożone (`a && b`, `a; b`, `a | b`, `$(a)`): sprawdzany jest każdy człon osobno – jedna odmowa blokuje całość.
Zwrot = także nota kredytowa i zwrot/nota przez MCP operatora płatności (ten sam próg kwotowy); więcej niż jeden zwrot albo nota
w jednym poleceniu = odmowa (bramka czyta jedną kwotę).
Kill switch: plik `bezpieczenstwo/HALT` (treść = powód) → każde narzędzie poza odczytem zablokowane, sesja zatrzymana.
BLOKOWANIE DOMYŚLNE: wolno tylko to, co jest na liście `dozwolone-polecenia.txt` (polecenia Bash, narzędzia wbudowane,
wzorce narzędzi MCP) albo jest czynnością z `uprawnienia.yaml`, do której rola ma prawo. Polecenie spoza listy = czynność
`spoza_listy` (poziom wlasciciel). Polecenie Bash jest rozbierane z uwzględnieniem cudzysłowów, `$(…)`, heredoków,
`bash -c`, `xargs`, `find -exec` – każdy człon osobno. Zapis do plików sterujących (hook, settings, uprawnienia, zasady,
lista, progi, audyt) = `zmiana_zasad_lub_uprawnien`; zapis do rejestru decyzji = `zapis_decyzji`.
Awaria = odmowa: nieczytelne wejście, brak `uprawnienia.yaml`, brak listy, polecenie nie do rozebrania → ZABLOKOWANE.
GRANICE (to poręcz, nie piaskownica): dozwolony interpreter (python3, node, bash plik.sh) wykona dowolny kod; rola z
`.agent-rola` jest deklaracją, nie uwierzytelnieniem; odczyt sieci (curl GET, WebFetch) pozostaje kanałem wycieku.
Izolację dają dopiero: osobne konto/kontener, sekrety poza zasięgiem agenta, uprawnienia tokenów po stronie usług.
Detekcja pętli: to samo polecenie Bash ≥ LIMIT_POWTORZEN razy z rzędu w jednej sesji → ZABLOKOWANE (incydent #15909).
Audyt: `bezpieczenstwo/audyt/RRRR-MM.jsonl` (merge=union), każdy rekord z `prev_hash` i `hash` (SHA-256 łańcuch).
"""
import fnmatch
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
    (r"(\bcat\b|\bless\b|\bhead\b|\btail\b|\bsource\b|\bexport\b)[^|;&]*(\.env(?!\.(?:example|sample|template|dist)\b)\b|~/\.ssh/|~/\.aws/|id_rsa|id_ed25519)", "odczyt pliku z sekretami"),
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
    # nota kredytowa = zwrot (zwraca albo zalicza pieniądze klientowi); podgląd (/preview) i odczyt (GET) – nie
    (r"api\.stripe\.com/v1/credit_notes(?!/preview)[^|;&]*(?:-X\s*POST|\s-d\s|\s--data|\s-F\s)|\bstripe\s+credit_notes\s+create\b",
     "zwrot_klientowi"),
    (r"api\.stripe\.com/v1/(prices|products|coupons)[^|;&]*(-X\s*(POST|DELETE)|-d\s)|\bstripe\s+(prices|products|coupons)\s+(create|update|delete)\b", "zmiana_cen"),
    (r"api\.stripe\.com/v1/(transfers|payouts)|\bstripe\s+(transfers|payouts)\s+create\b", "przelew"),
    (r"\b(xcrun\s+altool|fastlane\s+(deliver|supply|pilot)|eas\s+submit)\b", "wydanie_w_sklepach"),
    (r"\b(ssh|scp)\b[^|;&]*\b(prod|produkcja|vps)\b", "wdrozenie_produkcja"),
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
# Zwrot i nota kredytowa przez MCP operatora płatności (ID operacji albo ścieżka API) – ta sama bramka kwotowa co w powłoce.
OPERATORZY_PLATNOSCI = ("stripe",)
RE_ZWROT_MCP = re.compile(r'"(?:PostRefunds|PostCreditNotes)"|"/v1/(?:refunds|credit_notes)"')
# Każdy zwrot albo nota w tekście polecenia – bramka czyta jedną kwotę, więc drugi zwrot w tym samym poleceniu = odmowa.
RE_ZWROT_W_TEKSCIE = re.compile(r"\brefunds\s+create\b|/v1/refunds\b|\bcredit[_-]?notes\s+create\b|/v1/credit_notes\b(?!/preview)", re.I)
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


# ---------- lista dozwolonych (blokowanie domyślne) ----------

PLIK_LISTY = "dozwolone-polecenia.txt"
NARZEDZIA_ZAPISU = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
NARZEDZIA_HARMONOGRAMU = {"CronCreate", "CronDelete", "RemoteTrigger"}
OPCJE_Z_WARTOSCIA = {
    "git": {"-C", "-c", "--git-dir", "--work-tree", "--namespace"},
    "gh": {"-R", "--repo"},
    "npm": {"--prefix", "-w", "--workspace"},
}
KATALOGI_SYSTEMOWE = ("/bin/", "/usr/bin/", "/usr/local/bin/", "/opt/homebrew/bin/", "/sbin/", "/usr/sbin/")
SLOWA_KLUCZOWE = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}", "time", "done", "fi", "esac", "[[", "(("}
SLOWA_CALOSC = {"for", "select", "case", "in", "function"}
# opakowanie -> opcje, które biorą wartość (reszta po opakowaniu jest oceniana jak osobne polecenie)
OPAKOWANIA = {
    "env": {"-u", "-C", "-S"}, "nohup": set(), "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "gtimeout": {"-s", "-k", "--signal", "--kill-after"}, "command": set(), "nice": {"-n"},
    "caffeinate": {"-t", "-w"}, "stdbuf": {"-i", "-o", "-e"}, "exec": {"-a"}, "builtin": set(), "noglob": set(),
    "time": {"-o", "-f"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-J", "-R"},
}
ZAWSZE_ODMOWA = {"sudo", "doas", "su", "eval"}
POWLOKI = {"bash", "sh", "zsh", "dash", "ksh"}
INTERPRETERY = {"node", "deno", "bun", "perl", "ruby", "php", "psql", "sqlite3", "mysql", "osascript", "ssh", "tsx", "ts-node"}
# polecenia, których rozpoznana czynność (uprawnienia.yaml) zastępuje wpis na liście dozwolonych
POLECENIA_CZYNNOSCI = {"gh", "fly", "flyctl", "vercel", "wrangler", "netlify", "supabase", "psql", "stripe", "xcrun",
                       "fastlane", "eas", "ssh", "scp", "curl", "wget"}
CHRONIONE_PLIKI = (".claude/settings.json", ".claude/settings.local.json", "uprawnienia.yaml", "zasady.md", PLIK_LISTY,
                   "polityki/progi.yaml", "bezpieczenstwo/blokady.jsonl", ".agent-rola",
                   "bezpieczenstwo/zasady-skroty.json", "flota/szablony/bloki/zasady-bezpieczenstwa.md")
CHRONIONE_KATALOGI = (".claude/hooks", "bezpieczenstwo/audyt")
CHRONIONE_RODZICE = (".", ".claude", ".claude/hooks", "bezpieczenstwo", "bezpieczenstwo/audyt", "polityki", "decyzje")


def czytaj_liste(repo):
    """Czyta dozwolone-polecenia.txt -> {"polecenia": [krotki słów], "sciezki": [], "narzedzia": set, "mcp": []}.
    Brak pliku albo błąd odczytu -> None (wtedy przechodzą wyłącznie narzędzia odczytu)."""
    try:
        tekst = (repo / PLIK_LISTY).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    wyn = {"polecenia": [], "sciezki": [], "narzedzia": set(), "mcp": []}
    sekcja = None
    for linia in tekst.splitlines():
        linia = linia.split("#", 1)[0].strip()
        if not linia:
            continue
        if linia.startswith("[") and linia.endswith("]"):
            sekcja = linia[1:-1].strip()
            continue
        if sekcja == "polecenia":
            wyn["polecenia"].append(tuple(linia.split()))
        elif sekcja == "narzedzia":
            wyn["narzedzia"].update(linia.split())
        elif sekcja in ("sciezki", "mcp"):
            wyn[sekcja].append(linia)
    return wyn


def slowa_pozycyjne(slowa):
    """Nazwa polecenia + kolejne słowa niebędące opcjami (z pominięciem wartości znanych opcji)."""
    if not slowa:
        return []
    nazwa = slowa[0]
    z_wartoscia = OPCJE_Z_WARTOSCIA.get(nazwa, ())
    wyn, pomin = [nazwa], False
    for s in slowa[1:]:
        if pomin:
            pomin = False
        elif s in z_wartoscia:
            pomin = True
        elif not s.startswith("-"):
            wyn.append(s)
    return wyn


def na_liscie(lista, slowa):
    poz = slowa_pozycyjne(slowa)
    return any(tuple(poz[:len(w)]) == w for w in lista["polecenia"])

# ---------- rozbiór polecenia powłoki ----------

class Blad(Exception):
    """Polecenia nie da się jednoznacznie rozebrać – odmowa."""


ZNAK = "\x00"   # miejsce po podstawieniu polecenia $(…) – wartość nieznana


def _apostrof(s, i):
    """s[i] == "'" -> indeks zamykającego apostrofu."""
    j = s.find("'", i + 1)
    if j < 0:
        raise Blad("niezamknięty apostrof")
    return j


def _cudzyslow(s, i):
    """s[i] == '"' -> indeks zamykającego cudzysłowu (z pominięciem \\x i zagnieżdżonych $(…))."""
    j, n = i + 1, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
        elif c == '"':
            return j
        elif c == "$" and s.startswith("$(", j):
            j = dopasuj(s, j + 1) + 1
        elif c == "`":
            j = _grawis(s, j) + 1
        else:
            j += 1
    raise Blad("niezamknięty cudzysłów")


def _grawis(s, i):
    j, n = i + 1, len(s)
    while j < n:
        if s[j] == "\\":
            j += 2
        elif s[j] == "`":
            return j
        else:
            j += 1
    raise Blad("niezamknięty grawis")


RE_HEREDOK = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def dopasuj(s, i, otw="(", zam=")"):
    """s[i] == otw -> indeks pasującego zam, z pominięciem cytatów i treści heredoków."""
    gl, j, n, hered = 0, i, len(s), []
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            j = _apostrof(s, j)
        elif c == '"':
            j = _cudzyslow(s, j)
        elif c == "`":
            j = _grawis(s, j)
        elif c == "<" and otw == "(" and s.startswith("<<", j) and not s.startswith("<<<", j):
            m = RE_HEREDOK.match(s, j)
            if m:
                hered.append((m.group(2), s[j + 2:j + 3] == "-"))
                j = m.end() - 1
        elif c == "\n" and hered:
            j += 1
            while hered:
                term, tab = hered.pop(0)
                while j < n:
                    k = s.find("\n", j)
                    k = n if k < 0 else k
                    linia, j = s[j:k], min(k + 1, n)
                    if (linia.lstrip("\t") if tab else linia) == term:
                        break
            continue
        elif c == otw:
            gl += 1
        elif c == zam:
            gl -= 1
            if gl == 0:
                return j
        j += 1
    raise Blad("niezamknięty nawias")


def podstawienia(t, glebia, wyn):
    """Tekst z cudzysłowu, heredoka, ${…}, [[ … ]]: rozbiera zawarte podstawienia poleceń do `wyn`
    i zwraca tekst, w którym każde z nich zastępuje ZNAK."""
    j, n, out = 0, len(t), []
    while j < n:
        c = t[j]
        if c == "\\":
            out.append(t[j + 1:j + 2])
            j += 2
        elif c == "$" and t.startswith("$((", j):
            k = dopasuj(t, j + 1)
            podstawienia(t[j + 3:k - 1], glebia, wyn)
            out.append("0")
            j = k + 1
        elif c == "$" and t.startswith("$(", j):
            k = dopasuj(t, j + 1)
            rozbierz(t[j + 2:k], glebia + 1, wyn)
            out.append(ZNAK)
            j = k + 1
        elif c == "`":
            k = _grawis(t, j)
            rozbierz(t[j + 1:k].replace("\\`", "`"), glebia + 1, wyn)
            out.append(ZNAK)
            j = k + 1
        else:
            out.append(c)
            j += 1
    return "".join(out)

RE_FD = re.compile(r"\d+-?|-")
RE_FUNKCJA = re.compile(r"\(\s*\)")


class _Stan:
    def __init__(self):
        self.slowa, self.zapis, self.hered = [], [], []
        self.slowo, self.cyt, self.cel, self.tab = None, False, None, False


def rozbierz(s, glebia=0, wyn=None):
    """Rozbiera polecenie powłoki na płaską listę członów (także z podstawień i podpowłok).
    -> (człony, nazwy funkcji zdefiniowanych w poleceniu). Człon: {"slowa", "zapis", "sep", "heredoki"}."""
    if glebia > 8:
        raise Blad("zbyt głębokie zagnieżdżenie")
    if wyn is None:
        wyn = ([], set())
    segs, funkcje = wyn
    baza, st, oczek = len(segs), _Stan(), []
    n, i, nawiasy, jest_case = len(s), 0, 0, False

    def dodaj(t, cyt=False):
        st.slowo = (st.slowo or "") + t
        st.cyt = st.cyt or cyt

    def koniec_slowa():
        nonlocal jest_case
        w = st.slowo
        if w is None:
            return
        if st.cel == "zapis":
            st.zapis.append(w)
        elif st.cel == "heredok":
            oczek.append((w, st.tab, st.cyt, st.hered))
        elif st.cel is None:
            st.slowa.append(w)
            jest_case = jest_case or (w == "case" and not st.cyt)
        st.slowo, st.cel, st.cyt = None, None, False

    def koniec_segmentu(sep):
        koniec_slowa()
        if st.cel:
            raise Blad("przekierowanie bez celu")
        if st.slowa or st.zapis or any(o[3] is st.hered for o in oczek):
            segs.append({"slowa": st.slowa, "zapis": st.zapis, "sep": sep, "heredoki": st.hered})
        st.slowa, st.zapis, st.hered = [], [], []

    def na_poczatku():
        return st.slowo is None and all(w in SLOWA_KLUCZOWE for w in st.slowa)

    while i < n:
        c = s[i]
        if c == "\\":
            if s[i + 1:i + 2] != "\n":
                dodaj(s[i + 1:i + 2], True)
            i += 2
        elif c == "'":
            j = _apostrof(s, i)
            dodaj(s[i + 1:j], True)
            i = j + 1
        elif c == '"':
            j = _cudzyslow(s, i)
            dodaj(podstawienia(s[i + 1:j], glebia, wyn), True)
            i = j + 1
        elif c == "$":
            if s.startswith("$'", i):
                j = i + 2
                while j < n and s[j] != "'":
                    j += 2 if s[j] == "\\" else 1
                if j >= n:
                    raise Blad("niezamknięty apostrof")
                dodaj(s[i + 2:j], True)
            elif s.startswith("$((", i):
                j = dopasuj(s, i + 1)
                podstawienia(s[i + 3:j - 1], glebia, wyn)
                dodaj("0")
            elif s.startswith("$(", i):
                j = dopasuj(s, i + 1)
                rozbierz(s[i + 2:j], glebia + 1, wyn)
                dodaj(ZNAK)
            elif s.startswith("${", i):
                j = dopasuj(s, i + 1, "{", "}")
                podstawienia(s[i + 2:j], glebia, wyn)
                dodaj(s[i:j + 1])
            else:
                j = i
                dodaj("$")
            i = j + 1
        elif c == "`":
            j = _grawis(s, i)
            rozbierz(s[i + 1:j].replace("\\`", "`"), glebia + 1, wyn)
            dodaj(ZNAK)
            i = j + 1
        elif c == "#" and st.slowo is None:
            j = s.find("\n", i)
            i = n if j < 0 else j
        elif c in " \t":
            koniec_slowa()
            i += 1
        elif c == "\n":
            koniec_segmentu("\n")
            i += 1
            while oczek:                                    # treści heredoków zaczynają się po końcu wiersza
                term, tab, cyt, lista = oczek.pop(0)
                linie = []
                while i < n:
                    j = s.find("\n", i)
                    j = n if j < 0 else j
                    linia, i = s[i:j], min(j + 1, n)
                    if (linia.lstrip("\t") if tab else linia) == term:
                        break
                    linie.append(linia)
                tresc = "\n".join(linie)
                lista.append(tresc if cyt else podstawienia(tresc, glebia, wyn))
        elif c == ";":
            koniec_segmentu(";")
            i += 2 if s.startswith(";;", i) else 1
        elif c == "&":
            if s.startswith("&&", i):
                koniec_segmentu("&&")
                i += 2
            elif s.startswith("&>", i):
                koniec_slowa()
                st.cel = "zapis"
                i += 3 if s.startswith("&>>", i) else 2
            else:
                koniec_segmentu("&")
                i += 1
        elif c == "|":
            dwa = s.startswith("||", i)
            koniec_segmentu("||" if dwa else "|")
            i += 2 if dwa or s.startswith("|&", i) else 1
        elif c in "<>":
            if s.startswith(c + "(", i):                    # podstawienie procesu <(…) >(…)
                j = dopasuj(s, i + 1)
                rozbierz(s[i + 2:j], glebia + 1, wyn)
                dodaj(ZNAK)
                i = j + 1
                continue
            if st.slowo is not None and st.slowo.isdigit() and not st.cyt:
                st.slowo = None                             # numer deskryptora przed przekierowaniem
            koniec_slowa()
            if st.cel:
                raise Blad("przekierowanie bez celu")
            if s.startswith("<<<", i):
                st.cel, i = "odczyt", i + 3
            elif s.startswith("<<", i):
                i += 2
                st.tab = s[i:i + 1] == "-"
                i += 1 if st.tab else 0
                st.cel = "heredok"
            else:
                i += 1
                if c == ">" and s[i:i + 1] in (">", "|"):
                    i += 1
                if s[i:i + 1] == "&":
                    i += 1
                    m = RE_FD.match(s, i)
                    if m:
                        i = m.end()
                        continue
                st.cel = "zapis" if c == ">" else "odczyt"
        elif c == "(":
            m = RE_FUNKCJA.match(s, i)
            if st.slowo is not None:
                if m and not st.cyt and (not st.slowa or st.slowa == ["function"]):
                    funkcje.add(st.slowo)                   # definicja funkcji: nazwa()
                    st.slowo, st.slowa, i = None, [], m.end()
                else:                                       # tablica a=(…) albo wzorzec z nawiasem
                    j = dopasuj(s, i)
                    dodaj(podstawienia(s[i:j + 1], glebia, wyn))
                    i = j + 1
            elif s.startswith("((", i) and (na_poczatku() or st.slowa == ["for"]):
                j = dopasuj(s, i)
                podstawienia(s[i + 2:j - 1], glebia, wyn)
                st.slowa.append("((")
                i = j + 1
            elif m and st.slowa and (len(st.slowa) == 1 or st.slowa[0] == "function"):
                funkcje.add(st.slowa[-1])                   # definicja funkcji: nazwa ()
                st.slowa, i = [], m.end()
            elif na_poczatku():
                koniec_segmentu("(")
                nawiasy += 1
                i += 1
            elif jest_case:
                i += 1
            else:
                raise Blad("nawias w nieoczekiwanym miejscu")
        elif c == ")":
            if nawiasy > 0:
                koniec_segmentu(")")
                nawiasy -= 1
            elif jest_case:                                 # wzorzec gałęzi `case`: słowa przed `)` nie są poleceniem
                st.slowo, st.slowa, st.cel = None, [], None
                while len(segs) > baza and segs[-1]["sep"] == "|":
                    segs.pop()
            else:
                raise Blad("nawias zamykający bez otwierającego")
            i += 1
        elif c == "[" and st.slowo is None and s.startswith("[[", i) and s[i + 2:i + 3].isspace() and na_poczatku():
            j = s.find("]]", i)
            if j < 0:
                raise Blad("niezamknięte [[")
            podstawienia(s[i + 2:j], glebia, wyn)
            st.slowa.append("[[")
            i = j + 2
        else:
            dodaj(c)
            i += 1
    koniec_segmentu("")
    return wyn

# ---------- pliki chronione i zapisy HTTP ----------

ZASADY = "zmiana_zasad_lub_uprawnien"
RE_LOKALNY = re.compile(r"^(https?://)?(localhost|127\.0\.0\.1|\[::1\])([:/]|$)")
RE_HTTP_KOD = re.compile(
    r"""\b(requests|httpx|session|client|axios|http)\.(post|put|patch|delete)\s*\(|method\s*[=:]\s*['"](POST|PUT|PATCH|DELETE)['"]"""
    r"""|urlopen\([^)]*data\s*=|Request\([^)]*data\s*=|\.request\(\s*['"](POST|PUT|PATCH|DELETE)""", re.I)
RE_SQL_NISZCZY = re.compile(r"\b(DROP|TRUNCATE|DELETE\s+FROM)\b", re.I)
RE_SQL_ZMIENIA = re.compile(r"\b(ALTER|CREATE|INSERT|UPDATE)\b", re.I)


def w_katalogu(katalog, sciezka):
    """-> ścieżka względna (z ukośnikami) wewnątrz katalogu, "." dla niego samego, None gdy poza nim."""
    k = os.path.realpath(str(katalog))
    p = os.path.realpath(sciezka)
    if p == k:
        return "."
    if p.startswith(k + os.sep):
        return p[len(k) + 1:].replace(os.sep, "/")
    return None


def chroniony(repo, cwd, p, rodzic=False):
    """Zapis do pliku sterującego organizacją -> nazwa czynności; inaczej None."""
    p = str(p)
    if not p:
        return None
    if "$" in p or ZNAK in p:                               # ścieżki nie da się ustalić – ocena po tekście
        if any(f in p for f in CHRONIONE_PLIKI + CHRONIONE_KATALOGI):
            return ZASADY
        return "zapis_decyzji" if re.search(r"decyzje(/|\.md)", p) else None
    if p.startswith("~"):
        p = os.path.expanduser(p)
    katalogi = list(cwd) if isinstance(cwd, (list, tuple)) else [cwd]   # po `cd` w poleceniu: wszystkie możliwe katalogi
    if not os.path.isabs(p) and None in katalogi:                       # `cd` do katalogu ustalanego w trakcie wykonania
        nazwa = os.path.basename(p.rstrip("/"))
        znane = {os.path.basename(f) for f in CHRONIONE_PLIKI + CHRONIONE_KATALOGI}
        for d in CHRONIONE_KATALOGI:
            try:
                znane.update(os.listdir(os.path.join(str(repo), d)))
            except OSError:
                pass
        if nazwa in znane:
            return ZASADY
    kandydaci = [p] if os.path.isabs(p) else [os.path.join(str(k), p) for k in katalogi + [repo] if k]
    for k in kandydaci:
        rel = w_katalogu(repo, k)
        if rel is None:
            continue
        if rel in CHRONIONE_PLIKI or any(rel == d or rel.startswith(d + "/") for d in CHRONIONE_KATALOGI):
            return ZASADY
        if rodzic and rel in CHRONIONE_RODZICE:
            return ZASADY
        if any(z in rel for z in "*?[") and any(
                fnmatch.fnmatch(x, rel) or fnmatch.fnmatch(x.split("/")[0], rel) for x in CHRONIONE_PLIKI + CHRONIONE_KATALOGI):
            return ZASADY
        if rel == "decyzje.md" or (rel.startswith("decyzje/") and rel.endswith(".md")):
            return "zapis_decyzji"
    return None


def mutacje(nazwa, slowa, repo, cwd):
    """Czynności wynikające z tego, że polecenie zmienia albo usuwa pliki chronione."""
    opcje = slowa[1:]
    args = [a for a in opcje if not a.startswith("-")]
    cele, rodzic = [], False
    if nazwa in ("rm", "mv", "unlink", "shred", "rmdir"):
        cele, rodzic = args, True
    elif nazwa in ("tee", "truncate", "chmod", "chown", "touch"):
        cele = args
    elif nazwa == "sed" and any(re.match(r"-[a-zA-Z]*i|--in-place", a) for a in opcje):
        cele = args
    elif nazwa == "perl" and any(re.match(r"-[a-zA-Z0-9]*i", a) for a in opcje):
        cele = args
    elif nazwa in ("cp", "install", "ln", "rsync"):
        cele = args[-1:]
    elif nazwa == "dd":
        cele = [a[3:] for a in opcje if a.startswith("of=")]
    elif nazwa == "git":
        poz = slowa_pozycyjne(slowa)
        if len(poz) > 1 and poz[1] in ("checkout", "restore", "rm", "mv"):
            cele = poz[2:]
    wyn = []
    for c in cele:
        cz = chroniony(repo, cwd, c, rodzic)
        if cz and cz not in wyn:
            wyn.append(cz)
    return wyn


def zapis_http(nazwa, slowa, kod):
    """Polecenie, które zmienia stan usługi zewnętrznej przez HTTP -> zmiana_ustawien_uslugi."""
    cz, args = "zmiana_ustawien_uslugi", slowa[1:]
    if nazwa == "curl":
        pisze = False
        for k, a in enumerate(args):
            if a in ("-d", "-F", "-T", "--json", "--upload-file", "--form", "--form-string") or a.startswith("--data") \
                    or re.match(r"-[dFT].", a):
                pisze = True
            elif a.startswith("-X") or a.startswith("--request"):
                metoda = a[2:] if a.startswith("-X") else a[10:]
                metoda = metoda or (args[k + 1] if k + 1 < len(args) else "")
                pisze = pisze or metoda.upper() not in ("GET", "HEAD", "OPTIONS")
        if not pisze:
            return None
        adresy = [a for a in args if re.match(r"https?://|localhost|127\.0\.0\.1|\[::1\]", a) or a[:1] in ("$", ZNAK)]
        return None if adresy and all(RE_LOKALNY.match(a) for a in adresy) else cz
    if nazwa == "wget":
        return cz if any(a.startswith(("--post", "--method", "--body")) for a in args) else None
    if nazwa == "gh" and slowa_pozycyjne(slowa)[1:2] == ["api"]:
        metoda, pola = None, False
        for k, a in enumerate(args):
            if a in ("-X", "--method"):
                metoda = args[k + 1] if k + 1 < len(args) else ""
            elif a.startswith("--method="):
                metoda = a[9:]
            elif a.startswith("-X"):
                metoda = a[2:]
            elif a in ("-f", "-F", "--field", "--raw-field", "--input") or re.match(r"-[fF].|--(raw-)?field=|--input=", a):
                pola = True
        if "graphql" in args:
            return cz if re.search(r"\bmutation\b|=@", " ".join(args)) else None
        if metoda:
            return None if metoda.upper() in ("GET", "HEAD") else cz
        return cz if pola else None
    if kod and RE_HTTP_KOD.search(kod):
        return cz
    return None


def czynnosc_sql(nazwa, slowa, pelny):
    if nazwa in ("psql", "mysql", "sqlite3") or slowa[:3] == ["supabase", "db", "execute"]:
        if RE_SQL_NISZCZY.search(pelny):
            return "migracja_niszczaca_dane"
        if RE_SQL_ZMIENIA.search(pelny):
            return "migracja_zgodna_wstecz"
    return None

# ---------- ocena polecenia: każdy człon osobno, domyślnie odmowa ----------

SPOZA = "spoza_listy"
RE_PRZYPISANIE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]*\])?\+?=")
RE_ZMIENNA = re.compile(r"\$(\w+)|\$\{(\w+)\}")
RE_OPCJA_C = re.compile(r"^-[a-z]*c[a-z]*$")
TYLKO_TEKST = {"echo", "printf", "grep", "egrep", "fgrep", "rg"}      # ich argumenty to treść, nie polecenie
OPCJE_TRESCI = {"git": ("-m", "--message"), "gh": ("--body", "-b", "--title", "-t", "--notes", "-n")}
# Kod podany interpreterowi (heredok albo -c/-e) to najczęściej edycja plików, a w niej cudze teksty: nazwy poleceń,
# adresy, SQL. Wzorce czynności stosujemy do niego tylko wtedy, gdy sam kod (bez literałów) coś uruchamia albo łączy się z siecią.
OPCJE_KODU = {"python": ("-c",), "node": ("-e", "-p", "--eval", "--print"), "deno": ("-e", "-p", "--eval", "--print"),
              "bun": ("-e", "-p", "--eval", "--print"), "tsx": ("-e", "--eval"), "ts-node": ("-e", "--eval"),
              "perl": ("-e", "-E"), "ruby": ("-e",), "php": ("-r",)}
RE_LITERAL = re.compile(r"'''.*?'''|" r'""".*?"""|' r"'(?:\\.|[^'\\\n])*'|" r'"(?:\\.|[^"\\\n])*"|`[^`]*`', re.S)
RE_URUCHAMIA = re.compile(r"\b(subprocess|os\.system|os\.popen|os\.exec\w*|os\.spawn\w*|child_process|execSync|spawnSync|execFile\w*|"
                          r"spawn|popen|Deno\.Command|Bun\.spawn|pty|shutil\.rmtree)\b|(?<![.\w])(system|exec)\s*\(|\bqx\b")
RE_SIEC = re.compile(r"\b(requests|httpx|urllib\w*|urlopen|aiohttp|http\.client|fetch|axios|https?\.request|XMLHttpRequest|socket|"
                     r"LWP|Net::HTTP|curl_\w+)\b")


def kod_interpretera(nazwa, slowa, hered):
    """-> (słowa bez kodu z -c/-e, kod) dla interpretera; (słowa, None), gdy polecenie nim nie jest."""
    klucz = "python" if nazwa.startswith("python") else nazwa
    if klucz not in OPCJE_KODU:
        return slowa, ("\n".join(hered) if nazwa in INTERPRETERY else None)
    wyn, kod, k = [], list(hered), 0
    while k < len(slowa):
        if k and slowa[k] in OPCJE_KODU[klucz] and k + 1 < len(slowa):
            kod.append(slowa[k + 1])
            k += 2
        else:
            wyn.append(slowa[k])
            k += 1
    return wyn, "\n".join(kod)


def _spoza(co):
    return [("CZYNNOSC", SPOZA, co)]


def sciezka_dozwolona(p, ctx):
    """Program wskazany ścieżką: wolno skryptom z repo (ścieżka względna bez `..` albo wewnątrz repo) i wzorcom z [sciezki]."""
    if "$" in p or ZNAK in p:
        return False
    q = os.path.expanduser(p)
    for w in ctx["lista"]["sciezki"]:
        if fnmatch.fnmatch(p, w) or fnmatch.fnmatch(q, os.path.expanduser(w)):
            return True
    if not os.path.isabs(q):
        if ".." not in q.split("/"):
            return True
        q = os.path.join(str(ctx["cwd"]), q)
    return w_katalogu(ctx["repo"], q) is not None


def bez_opakowania(nazwa, slowa):
    """Słowa po opakowaniu (env, timeout, xargs…) – z pominięciem jego opcji; None = samo zapytanie (command -v)."""
    z_wartoscia, i, czas = OPAKOWANIA[nazwa], 1, nazwa in ("timeout", "gtimeout")
    while i < len(slowa):
        a = slowa[i]
        if nazwa == "command" and a in ("-v", "-V"):
            return None
        if a in z_wartoscia:
            i += 2
        elif a.startswith("-") or (nazwa == "env" and RE_PRZYPISANIE.match(a)):
            i += 1
        elif czas:
            czas, i = False, i + 1
        else:
            break
    return slowa[i:]


def tekstowe(nazwa, slowa, kod, ctx, wymaga_listy=True):
    """Zakazy, czynności z uprawnienia.yaml, zapisy do plików chronionych i lista dozwolonych – dla jednego polecenia."""
    wyn = [("CZYNNOSC", cz, " ".join(slowa)) for cz in mutacje(nazwa, slowa, ctx["repo"], ctx.get("katalogi") or ctx["cwd"])]
    cz = None
    if nazwa not in TYLKO_TEKST:
        tresc, widoczne, pomin = OPCJE_TRESCI.get(nazwa, ()), [], False
        for w in slowa:
            if pomin:
                pomin = False
            elif w in tresc:
                pomin = True
            elif not any(w.startswith(o + "=") for o in tresc if o.startswith("--")):
                widoczne.append(w)
        kod_cz = kod_siec = kod
        if kod and (nazwa.startswith("python") or nazwa in OPCJE_KODU):
            goly = RE_LITERAL.sub("''", kod)
            kod_cz = kod if RE_URUCHAMIA.search(goly) else ""
            kod_siec = kod if RE_SIEC.search(goly) else ""
        pelny = " ".join(widoczne) + ("\n" + kod_cz if kod_cz else "")
        for wzor, opis in ZAKAZANE:
            if re.search(wzor, pelny):
                return [("ZAKAZANE", opis, pelny)]
        for wzor, c in WZORCE_BASH:
            if re.search(wzor, pelny, re.I):
                cz = c
                break
        cz = cz or zapis_http(nazwa, slowa, kod_siec) or czynnosc_sql(nazwa, slowa, pelny)
    if cz:
        wyn.append(("CZYNNOSC", cz, " ".join(slowa)))
        if nazwa in POLECENIA_CZYNNOSCI:
            return wyn
    if wymaga_listy and not na_liscie(ctx["lista"], slowa):
        wyn += _spoza("polecenie „%s”" % " ".join(slowa_pozycyjne(slowa)[:2]))
    return wyn


def ocen_slowa(slowa, hered, funkcje, zmienne, ctx, glebia):
    if glebia > 8:
        return _spoza("polecenie zbyt głęboko zagnieżdżone")
    pierwsze = RE_ZMIENNA.sub(lambda m: zmienne.get(m.group(1) or m.group(2), m.group(0)), slowa[0])
    if pierwsze != slowa[0]:
        slowa = pierwsze.split() + slowa[1:]
        if not slowa:
            return []
    nazwa = slowa[0]
    if "$" in nazwa or ZNAK in nazwa:
        return _spoza("polecenie o nazwie ustalanej w trakcie wykonania")
    if "/" in nazwa:
        if nazwa.startswith(KATALOGI_SYSTEMOWE):
            nazwa = os.path.basename(nazwa)
            slowa = [nazwa] + slowa[1:]
        elif sciezka_dozwolona(nazwa, ctx):
            return tekstowe(nazwa, slowa, "", ctx, wymaga_listy=False)
        else:
            return _spoza("program „%s” spoza repo" % nazwa)
    if nazwa in funkcje:
        return []
    if nazwa in ZAWSZE_ODMOWA:
        return [("ZAKAZANE", "%s (podniesienie uprawnień albo wykonanie sklejonego tekstu)" % nazwa, " ".join(slowa))]
    if nazwa in OPAKOWANIA:
        reszta = bez_opakowania(nazwa, slowa)
        return ocen_slowa(reszta, hered, funkcje, zmienne, ctx, glebia + 1) if reszta else []
    wyn, args = [], slowa[1:]
    if nazwa == "find":
        k = 0
        while k < len(args):
            if args[k] in ("-exec", "-execdir", "-ok", "-okdir"):
                j = k + 1
                while j < len(args) and args[j] not in (";", "+"):
                    j += 1
                if args[k + 1:j]:
                    wyn += ocen_slowa(args[k + 1:j], [], funkcje, zmienne, ctx, glebia + 1)
                k = j
            k += 1
    elif nazwa in POWLOKI:
        k, skrypt, kod_c = 0, None, None
        while k < len(args):
            a = args[k]
            if RE_OPCJA_C.match(a):
                kod_c = args[k + 1] if k + 1 < len(args) else ""
                break
            if a in ("-o", "+o", "-O", "+O"):
                k += 1
            elif not a.startswith(("-", "+")):
                skrypt = a
                break
            k += 1
        if kod_c is not None:
            wyn += ocen_tekst(kod_c, ctx, glebia + 1, zmienne)
        elif skrypt is not None:
            if not sciezka_dozwolona(RE_ZMIENNA.sub(lambda m: zmienne.get(m.group(1) or m.group(2), m.group(0)), skrypt), ctx):
                wyn += _spoza("skrypt „%s” spoza repo" % skrypt)
        elif hered:
            for h in hered:
                wyn += ocen_tekst(h, ctx, glebia + 1, zmienne)
        else:
            wyn += _spoza("powłoka „%s” wykonująca polecenia z wejścia" % nazwa)
    elif nazwa in ("source", "."):
        if not args or not sciezka_dozwolona(args[0], ctx):
            wyn += _spoza("skrypt „%s” spoza repo" % (args[0] if args else ""))
    elif nazwa == "trap":
        poz = [a for a in args if not a.startswith("-")]
        if poz and poz[0].strip():
            wyn += ocen_tekst(poz[0], ctx, glebia + 1, zmienne)
    slowa, kod = kod_interpretera(nazwa, slowa, hered)
    return wyn + tekstowe(nazwa, slowa, kod or "", ctx)


def ocen_tekst(polecenie, ctx, glebia=0, zmienne=None):
    """-> lista (rodzaj, czynność albo opis zakazu, szczegół); pusta = wolno."""
    try:
        segs, funkcje = rozbierz(polecenie)
    except (Blad, RecursionError, IndexError) as e:
        for wzor, opis in ZAKAZANE:
            if re.search(wzor, polecenie):
                return [("ZAKAZANE", opis, polecenie)]
        return _spoza("polecenie, którego nie da się jednoznacznie rozebrać (%s)" % (str(e) or e.__class__.__name__))
    zmienne = dict(zmienne if zmienne is not None else ctx["zmienne"])
    wyn, poprz = [], None
    for seg in segs:
        hered = list(seg["heredoki"])
        if poprz is not None and poprz["sep"] == "|":
            hered += poprz["heredoki"]                      # cat <<EOF | bash
        poprz = seg
        for z in seg["zapis"]:
            cz = chroniony(ctx["repo"], ctx.get("katalogi") or ctx["cwd"], z)
            if cz:
                wyn.append(("CZYNNOSC", cz, "zapis do " + z))
        slowa = list(seg["slowa"])
        while slowa:
            m = RE_PRZYPISANIE.match(slowa[0])
            if m:
                v = slowa[0][m.end():]
                if "$" in v or ZNAK in v:
                    zmienne.pop(m.group(1), None)
                else:
                    zmienne[m.group(1)] = v
            elif slowa[0] not in SLOWA_KLUCZOWE:
                break
            slowa.pop(0)
        if not slowa:
            continue
        if slowa[0] in SLOWA_CALOSC:
            if slowa[0] == "function" and len(slowa) > 1:
                funkcje.add(slowa[1])
            continue
        if slowa[0] in ("cd", "pushd"):                     # ścieżki względne w dalszych członach liczą się od nowego katalogu
            cel = next((a for a in slowa[1:] if not a.startswith("-")), "~")
            cel = RE_ZMIENNA.sub(lambda m: zmienne.get(m.group(1) or m.group(2), m.group(0)), cel)
            kat = ctx.setdefault("katalogi", [ctx["cwd"]])
            if "$" in cel or ZNAK in cel or cel == "-":
                kat.append(None)
            else:
                ctx["cwd"] = os.path.normpath(os.path.join(str(ctx["cwd"]), os.path.expanduser(cel)))
                kat.append(ctx["cwd"])
        wyn += ocen_slowa(slowa, hered, funkcje, zmienne, ctx, glebia)
    return wyn


def czynnosc_z_wejscia(narzedzie, wejscie, repo, cwd, lista):
    """-> (lista (rodzaj: ZAKAZANE|CZYNNOSC, czynność/opis, szczegół), szczegół wywołania). Pusta lista = wolno."""
    brak = lista is None
    lista = lista or {"polecenia": [], "sciezki": [], "narzedzia": set(), "mcp": []}
    if narzedzie == "Bash":
        cmd = str(wejscie.get("command", ""))
        ctx = {"repo": repo, "cwd": cwd or str(repo), "lista": lista,
               "zmienne": {"HOME": os.path.expanduser("~"), "CLAUDE_PROJECT_DIR": str(repo), "PWD": cwd or str(repo)}}
        wyn, widziane = [], set()
        for a in sorted(ocen_tekst(cmd, ctx), key=lambda a: a[0] != "ZAKAZANE"):
            if a[:2] not in widziane:
                widziane.add(a[:2])
                wyn.append(a)
        return wyn, cmd
    if narzedzie in NARZEDZIA_ODCZYTU:
        return [], ""
    if narzedzie.startswith("mcp__"):
        if any(o in narzedzie for o in OPERATORZY_PLATNOSCI) and RE_ZWROT_MCP.search(json.dumps(wejscie, ensure_ascii=False)):
            return [("CZYNNOSC", "zwrot_klientowi", narzedzie)], narzedzie   # przed ogólnym „zapis w usłudze”
        for wzor, cz in WZORCE_MCP:
            if re.search(wzor, narzedzie):
                return [("CZYNNOSC", cz, narzedzie)], narzedzie
        czesci = narzedzie.split("__", 2)
        krotka = czesci[2] if len(czesci) == 3 else narzedzie
        if any(fnmatch.fnmatch(krotka, w) or fnmatch.fnmatch(narzedzie, w) for w in lista["mcp"]):
            return [], narzedzie
        return _spoza("narzędzie MCP „%s”" % narzedzie), narzedzie
    if narzedzie in NARZEDZIA_HARMONOGRAMU:
        return [("CZYNNOSC", "nowy_agent_lub_zadanie_cykliczne", narzedzie)], narzedzie
    if narzedzie in NARZEDZIA_ZAPISU:
        p = str(wejscie.get("file_path") or wejscie.get("notebook_path") or "")
        cz = chroniony(repo, cwd, p)
        if cz:
            return [("CZYNNOSC", cz, "zapis do " + p)], p
        return ([] if narzedzie in lista["narzedzia"] else _spoza("narzędzie „%s”" % narzedzie)), p
    if narzedzie in lista["narzedzia"]:
        return [], ""
    return _spoza("narzędzie „%s”%s" % (narzedzie, " (brak pliku %s)" % PLIK_LISTY if brak else "")), ""


RE_NOTA = re.compile(r"credit[_-]?notes\b(?!/preview)", re.I)
SKLADNIKI_NOTY = ("credit_amount", "refund_amount", "out_of_band_amount")


def _kwota_klucza(tekst, klucz):
    """Liczba przy kluczu: -d k=…, --k-z-myslnikami …, JSON "k": … (`amount` nie łapie `refund_amount` ani `lines[0][amount]`)."""
    m = re.search(r"(?<![\w\[-])(?:--)?(?:%s|%s)(?:\"?\s*:\s*\"?|=|\s+)(\d+(?:\.\d+)?)" % (klucz, klucz.replace("_", "-")), tekst)
    return float(m.group(1)) if m else None


def kwota_noty(tekst):
    """Kwota noty kredytowej: `amount`, a bez niego suma składników (credit/refund/out_of_band_amount); przy obu – większa.
    Brak = None (odmowa jak przy zwrocie bez kwoty). Jednostka jak w poleceniu."""
    a = _kwota_klucza(tekst, "amount")
    cz = [v for v in (_kwota_klucza(tekst, k) for k in SKLADNIKI_NOTY) if v is not None]
    if a is None and not cz:
        return None
    return max(a or 0.0, sum(cz))


def kwota_z_wejscia(narzedzie, wejscie, szczegol):
    """Kwota w USD z polecenia (stripe --amount w centach; -d amount=; JSON amount) albo z wejścia MCP (także `parameters`).
    Nota kredytowa – kwota_noty. None = nieznana."""
    tekst_mcp = "" if narzedzie == "Bash" else json.dumps(wejscie, ensure_ascii=False)
    if RE_NOTA.search(szczegol if narzedzie == "Bash" else tekst_mcp):
        v = kwota_noty(szczegol if narzedzie == "Bash" else tekst_mcp)
        centy = re.search(r"\bstripe\b|api\.stripe\.com", szczegol) if narzedzie == "Bash" else "stripe" in narzedzie
        return None if v is None else (v / 100 if centy else v)
    if narzedzie == "Bash":
        m = re.search(r"(?:--amount[= ]|amount=|\"amount\"\s*:\s*)(\d+(?:\.\d+)?)", szczegol)
        if not m:
            return None
        v = float(m.group(1))
        return v / 100 if re.search(r"\bstripe\b|api\.stripe\.com", szczegol) else v
    parametry = wejscie.get("parameters") if isinstance(wejscie.get("parameters"), dict) else {}
    for zrodlo in (wejscie, parametry):
        for k in ("amount", "kwota", "amount_usd", "refund_amount"):
            v = zrodlo.get(k)
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


def znajdz_repo(dane):
    """Repo organizacji: CLAUDE_PROJECT_DIR, potem położenie tego pliku (.claude/hooks/), na końcu katalog bieżący."""
    kandydaci = [os.environ.get("CLAUDE_PROJECT_DIR")]
    try:
        kandydaci.append(str(Path(__file__).resolve().parents[2]))
    except (IndexError, OSError):
        pass
    kandydaci += [dane.get("cwd"), "."]
    for k in kandydaci:
        if k:
            repo = katalog_repo(k)
            if repo is not None:
                return repo
    return None


def main():
    try:
        dane = json.load(sys.stdin)
        if not isinstance(dane, dict):
            raise ValueError("wejście nie jest obiektem")
    except ValueError:                                      # fail-closed: bez wejścia nie da się niczego ocenić
        print("ZABLOKOWANE: hook uprawnień nie odczytał wejścia (niepoprawny JSON) – domyślnie odmowa.", file=sys.stderr)
        return 2
    narzedzie = str(dane.get("tool_name") or "")
    wejscie = dane.get("tool_input") if isinstance(dane.get("tool_input"), dict) else {}
    faza = "post" if dane.get("hook_event_name") == "PostToolUse" else "pre"
    repo = znajdz_repo(dane)
    if repo is None:
        if faza == "post" or narzedzie in NARZEDZIA_ODCZYTU:
            return 0
        print("ZABLOKOWANE: hook uprawnień nie znalazł repo organizacji (uprawnienia.yaml) – domyślnie odmowa; "
              "przechodzą tylko narzędzia odczytu.", file=sys.stderr)
        return 2
    teraz = datetime.now(timezone.utc)
    sesja = dane.get("session_id") or ""
    r = rola(repo)
    akcje, szczegol = czynnosc_z_wejscia(narzedzie, wejscie, repo, dane.get("cwd") or str(repo), czytaj_liste(repo))
    rodzaj, co = (akcje[0][0], akcje[0][1]) if akcje else ("WOLNO", "")
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

    if not akcje:
        rekord.update({"decyzja": "allow", "regula": "wolno"})
        zapisz_audyt(repo, teraz, rekord, ogon)
        return 0

    uprawnienia = czytaj_uprawnienia(repo)
    typ = typ_agenta(repo, r)
    decyzja = decyzja_z_srodowiska(repo, szczegol if narzedzie == "Bash" else "")
    progi = czytaj_progi(repo)
    regula, kwota = "wolno", None
    for i, (rodz, cz, etykieta) in enumerate(akcje):       # polecenie złożone: każda czynność przechodzi własną kontrolę
        dalsza = "" if i == 0 else " (polecenie złożone – każda czynność jest sprawdzana osobno)"
        if rodz == "CZYNNOSC" and typ in ("reader", "researcher") and cz in CZYNNOSCI_ACTOR and not (
                typ == "reader" and cz == "wysylka_maila" and r in uprawnienia.get("wysylka_maila", {}).get("sam", [])):
            rekord.update({"decyzja": "deny", "regula": "regula-dwoch:" + typ})
            zapisz_audyt(repo, teraz, rekord, ogon)
            zapisz_blokade(repo, r, narzedzie, cz, szczegol)
            print("ZABLOKOWANE (reguła dwóch): agent typu %s (czyta niezaufane treści / tylko jawne źródła) nie wykonuje „%s” – zleć agentowi typu actor (zlecenia/README.md).%s" % (typ, cz, dalsza), file=sys.stderr)
            return 2
        u = uprawnienia.get(cz, {})
        czy_cz = rodz == "CZYNNOSC"
        if czy_cz and cz == "zwrot_klientowi" and narzedzie == "Bash" and len(RE_ZWROT_W_TEKSCIE.findall(szczegol)) > 1:
            rekord.update({"decyzja": "deny", "regula": "zwrot_klientowi:wiele-zwrotow", "decyzja_id": decyzja})
            zapisz_audyt(repo, teraz, rekord, ogon)                # kwota jest czytana z pierwszego zwrotu – drugi ominąłby próg
            zapisz_blokade(repo, r, narzedzie, cz, szczegol)
            print("ZABLOKOWANE: „zwrot_klientowi” – jeden zwrot albo jedna nota na polecenie (bramka kwotowa czyta jedną kwotę).%s"
                  % dalsza, file=sys.stderr)
            return 2
        kw = kwota_z_wejscia(narzedzie, wejscie, szczegol) if czy_cz and u.get("bramka") == "kwota" else None
        bramka_pr = bramka_scalania(repo, szczegol, r, decyzja) if czy_cz and u.get("bramka") == "pr" else None
        wolno, komunikat, reg = decyduj(rodz, cz, uprawnienia, r, decyzja, kw, progi, bramka_pr)
        if i == 0:
            regula, kwota = reg, kw
        if not wolno:
            if cz == SPOZA:
                komunikat = ("ZABLOKOWANE: %s nie jest na liście dozwolonych (%s) – domyślnie odmowa. Jeśli jest potrzebne: zgłoś CEO; "
                             "właściciel dopisuje je do listy (zmiana przez PR) albo wydaje decyzję: DECYZJA=D-… <polecenie>."
                             % (etykieta, PLIK_LISTY))
            elif cz in (ZASADY, "zapis_decyzji"):
                komunikat += " Dotyczy: %s." % etykieta[:160]
            rekord.update({"decyzja": "deny", "regula": reg, "decyzja_id": decyzja, "kwota_usd": kw})
            zapisz_audyt(repo, teraz, rekord, ogon)
            zapisz_blokade(repo, r, narzedzie, cz, szczegol)
            print(komunikat + dalsza, file=sys.stderr)
            return 2
    rekord.update({"decyzja": "allow", "regula": regula, "decyzja_id": decyzja, "kwota_usd": kwota})
    if len(akcje) > 1:
        rekord["czynnosci"] = [a[1] for a in akcje]
    zapisz_audyt(repo, teraz, rekord, ogon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
