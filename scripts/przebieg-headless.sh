#!/usr/bin/env bash
# Przebieg agenta bez aplikacji (Agent SDK / `claude -p`) z twardym limitem kosztu i zapisem kosztu przebiegu.
#
#   scripts/przebieg-headless.sh <agent> [<konto>]        # konto domyślnie org.yaml → runtime.konto
#
# Co robi: czyta prompt zadania (ceo/handoff/prompty/<agent>.md – generowany z flota/zadania.yaml), model i budżet
# przebiegu z manifestu, uruchamia `claude -p` z limitem --max-budget-usd i --max-turns, a wynik JSON
# (total_cost_usd, duration, num_turns, is_error) dopisuje do przebiegi/<agent>/koszty-<data>.jsonl i zapisuje scripts/zapisz.sh (ponowienia pushu).
# Agent sam w trakcie przebiegu pisze swoją linię kontraktu (przebiegi/<agent>/<data>.jsonl).
# Wymagania: ANTHROPIC_API_KEY (rozliczenie api) albo zalogowane `claude` na koncie floty (`claude /login` raz na maszynie).
# Tryb uprawnień: PRZEBIEG_TRYB=auto (klasyfikator, Claude Code ≥ 2.1.259; zalecany na serwerze) albo acceptEdits
# (domyślnie; narzędzia z PRZEBIEG_NARZEDZIA bez pytania – granice i tak trzyma hook .claude/hooks/uprawnienia.py).
# Starsze CLI nie zna --permission-prompts – flaga dodawana tylko, gdy `claude --help` ją wymienia.
# Telemetria: OTEL_RESOURCE_ATTRIBUTES=agent.role=<agent>,… (eksport włącza ~/.claude/settings.json – toolbelt/obserwowalnosc.md).
# Zadania w chmurze (scheduled tasks) kosztu nie zwracają do repo – tam koszt liczy telemetria.
set -u
agent=${1:?Użycie: $0 <agent> [konto]}; konto=${2:-}
repo=$(cd "$(dirname "$0")/.." && pwd); cd "$repo"
case "$agent" in *[!a-z0-9-]*|'') echo "Zła nazwa agenta: $agent" >&2; exit 2 ;; esac
command -v claude >/dev/null || { echo "BŁĄD: brak polecenia claude" >&2; exit 1; }

eval "$(python3 - "$agent" <<'PY'
import sys, yaml, shlex
agent = sys.argv[1]
m = yaml.safe_load(open("flota/zadania.yaml")); o = yaml.safe_load(open("org.yaml"))
z = next((x for x in m["zadania"] if x["agent"] == agent), None)
if not z: sys.exit("BŁĄD: agent %s nie istnieje w flota/zadania.yaml" % agent)
print("PROMPT=%s" % shlex.quote(z["prompt"]))
kl = z.get("model") or m.get("model") or "mocny"; mod = (o.get("runtime") or {}).get("modele") or {}
if kl not in mod: sys.exit("BŁĄD: klasa modelu %s nie istnieje w org.yaml → runtime.modele" % kl)
print("MODEL=%s" % shlex.quote(mod[kl]))
print("BUDZET=%s" % shlex.quote(str(z.get("budzet_usd_przebieg") or m.get("budzet_usd_przebieg", 2))))
print("TURY=%s" % shlex.quote(str(z.get("max_tur") or m.get("max_tur", 60))))
rt = o.get("runtime") or {}
print("KONTO0=%s" % shlex.quote(str(rt.get("konto") or (rt.get("konta") or ["A"])[0]).upper()))
print("PREFIKS=%s" % shlex.quote(str(o["organizacja"]["prefiks"])))
PY
)" || exit 1
konto=${konto:-$KONTO0}
[ -f "$PROMPT" ] || { echo "BŁĄD: brak pliku promptu $PROMPT (python3 flota/generuj.py)" >&2; exit 1; }

tryb=${PRZEBIEG_TRYB:-acceptEdits}
narzedzia=${PRZEBIEG_NARZEDZIA:-"Bash,Read,Edit,Write,Glob,Grep,WebFetch,WebSearch"}
dodatkowe=()
claude --help 2>/dev/null | grep -q -- "--permission-prompts" && dodatkowe+=(--permission-prompts none)
[ "$tryb" = auto ] || dodatkowe+=(--allowedTools "$narzedzia")

export PRZEBIEG_HEADLESS=1   # koszt zapisuje ten skrypt z wyniku CLI – scripts/koszt.py go nie dubluje
export OTEL_RESOURCE_ATTRIBUTES="agent.role=$agent,org.prefiks=$PREFIKS,konto=$konto${OTEL_RESOURCE_ATTRIBUTES:+,$OTEL_RESOURCE_ATTRIBUTES}"
start=$(date +%s)
tresc_promptu=$(sed "s/^Konto: .*/Konto: $konto/" "$PROMPT")
wynik_plik=$(mktemp -t "przebieg-$agent")
claude -p "$tresc_promptu" --output-format json --model "$MODEL" --max-budget-usd "$BUDZET" --max-turns "$TURY" \
       --permission-mode "$tryb" "${dodatkowe[@]}" >"$wynik_plik" 2>"/tmp/przebieg-headless-$agent.err"
kod=$?
koniec=$(date +%s)

python3 - "$agent" "$konto" "$MODEL" "$BUDZET" "$kod" "$start" "$koniec" "$wynik_plik" <<'PY'
import json, sys, pathlib, datetime
agent, konto, model, budzet, kod, start, koniec, wynik_plik = sys.argv[1:9]
try:
    d = json.loads(pathlib.Path(wynik_plik).read_text() or "{}")
except ValueError:
    d = {}
teraz = datetime.datetime.now().astimezone()
linia = {"czas": teraz.isoformat(timespec="seconds"), "agent": agent, "konto": konto, "model": model,
         "koszt_usd": d.get("total_cost_usd"), "budzet_usd": float(budzet), "czas_s": int(koniec) - int(start),
         "tury": d.get("num_turns"), "blad": bool(d.get("is_error")) or int(kod) != 0, "kod": int(kod),
         "sesja": d.get("session_id"), "wynik": (d.get("result") or "")[:300]}
p = pathlib.Path("przebiegi") / agent / ("koszty-%s.jsonl" % teraz.strftime("%Y-%m-%d"))
p.parent.mkdir(parents=True, exist_ok=True)
with p.open("a", encoding="utf-8") as f:
    f.write(json.dumps(linia, ensure_ascii=False) + "\n")
print("koszt %s: %s USD, %ss, tury %s, błąd %s → %s" % (agent, linia["koszt_usd"], linia["czas_s"], linia["tury"], linia["blad"], p))
if linia["blad"]:
    print("wynik: %s" % linia["wynik"], file=sys.stderr)
PY
rm -f "$wynik_plik"

# Zapis kosztu: tylko własne ścieżki, dociągnięcie zmian innych i push z ponowieniami (scripts/zapisz.sh; bez --force).
"$repo/scripts/zapisz.sh" "przebieg $agent: koszt" "przebiegi/$agent/" \
  || echo "UWAGA: zapis kosztu nieudany (zapisz.sh – ślad wyżej; commit zostaje lokalnie)" >&2
exit $kod
