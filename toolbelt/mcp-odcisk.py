#!/usr/bin/env python3
"""SHA-256 listy narzędzi serwera MCP (nazwa + opis + schemat wejścia), niezależny od kolejności.
  python3 -I toolbelt/mcp-odcisk.py narzedzia.json     # JSON: lista obiektów {name, description, inputSchema} albo {"tools": [...]}"""
import hashlib, json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
n = d.get("tools", d) if isinstance(d, dict) else d
kanon = json.dumps(sorted(({"name": t.get("name"), "description": t.get("description"), "inputSchema": t.get("inputSchema") or t.get("input_schema")} for t in n),
                          key=lambda t: str(t["name"])), sort_keys=True, ensure_ascii=False)
print(hashlib.sha256(kanon.encode("utf-8")).hexdigest(), len(n))
