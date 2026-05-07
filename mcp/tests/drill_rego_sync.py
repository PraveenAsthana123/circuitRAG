#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: PolisAI Stage-2 — JSON/Rego policy sync.

Per CLAUDE.md §43 + §44 + §47. Locks Stage-2 promotion of PolisAI:
  - Rego file exists at config/policies/agent_dispatch.rego
  - rego_sync_check.py validator exists + parses both files
  - JSON + Rego have IDENTICAL rule fingerprints (actor, tool, scopes)
  - Drift between the two FAILS the drill loud

Eight steps. Five negative.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGO_FILE = REPO / "config" / "policies" / "agent_dispatch.rego"
JSON_FILE = REPO / "config" / "policies" / "agent_dispatch.json"
SYNC_SCRIPT = REPO / "scripts" / "rego_sync_check.py"
PYTHON = REPO / ".venv" / "bin" / "python3"
sys.path.insert(0, str(REPO / "scripts"))


def main() -> int:
    print("-- 1. POSITIVE: Rego file + JSON + sync script all exist --")
    for path in (REGO_FILE, JSON_FILE, SYNC_SCRIPT):
        if not path.exists():
            print(f"x missing: {path}")
            return 1
    print("  ok: 3 files present (rego + json + validator)")

    print("-- 2. POSITIVE: rego_sync_check.py --json runs cleanly --")
    proc = subprocess.run(
        [str(PYTHON), str(SYNC_SCRIPT), "--json"],
        capture_output=True, text=True, timeout=10, cwd=REPO,
    )
    if proc.returncode not in (0, 1):
        print(f"x sync script must exit 0 (sync) or 1 (drift); got {proc.returncode}")
        return 1
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"x output not JSON: {e}")
        return 1
    for key in ("json_rule_count", "rego_rule_count", "in_sync", "json_only", "rego_only"):
        if key not in report:
            print(f"x report missing key: {key}")
            return 1
    print("  ok: report shape correct (5 documented fields)")

    print("-- 3. POSITIVE: JSON has 12 rules + Rego has 12 rules --")
    if report["json_rule_count"] != 12:
        print(f"x expected 12 JSON rules; got {report['json_rule_count']}")
        return 1
    if report["rego_rule_count"] != 12:
        print(f"x expected 12 Rego rules; got {report['rego_rule_count']}")
        return 1
    print("  ok: both files have 12 rules")

    print("-- 4. NEGATIVE: in_sync=True (no drift) --")
    if not report["in_sync"]:
        print("x JSON + Rego must be in sync")
        if report.get("json_only"):
            print(f"  JSON-only: {report['json_only']}")
        if report.get("rego_only"):
            print(f"  Rego-only: {report['rego_only']}")
        return 1
    print("  ok: 0 JSON-only + 0 Rego-only rules (perfect sync)")

    print("-- 5. NEGATIVE: parse_rego_rules handles nested braces correctly --")
    # Critical drill: the brace-counter must NOT stop at the first
    # inner }. Test by directly importing the parser.
    import rego_sync_check
    rego_rules = rego_sync_check.parse_rego_rules()
    if len(rego_rules) != 12:
        print(f"x parser returned {len(rego_rules)} rules; expected 12")
        return 1
    # Each rule must have actor + tool + scopes
    for r in rego_rules:
        for key in ("actor", "tool", "scopes"):
            if key not in r:
                print(f"x rego rule missing {key!r}: {r}")
                return 1
    print("  ok: parser handled nested braces; extracted 12 valid rules")

    print("-- 6. NEGATIVE: Rego file uses 'default allow := false' (default-deny posture) --")
    rego_src = REGO_FILE.read_text(encoding="utf-8")
    if "default allow := false" not in rego_src:
        print("x Rego must declare 'default allow := false' (default-deny)")
        return 1
    if "package documind.agent_dispatch" not in rego_src:
        print("x Rego must declare package documind.agent_dispatch")
        return 1
    print("  ok: default-deny + correct package declaration")

    print("-- 7. NEGATIVE: every Rego allow block uses 'required & granted == required' --")
    # The set-intersection-equality pattern is the canonical Rego idiom
    # for "all required scopes are granted." Drill enforces consistency.
    if "required & granted == required" not in rego_src:
        print("x Rego must use 'required & granted == required' scope-check idiom")
        return 1
    # Count occurrences — should match rule count
    intersect_count = rego_src.count("required & granted == required")
    if intersect_count < 12:
        print(f"x expected >=12 scope-check idioms; got {intersect_count}")
        return 1
    print(f"  ok: {intersect_count} scope-check idioms (one per rule)")

    print("-- 8. POSITIVE: JSON-side and Rego-side actor sets match --")
    # Stronger sync check: every actor that appears in JSON must
    # appear in Rego (and vice versa).
    json_doc = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    json_actors = {r["actor"] for r in json_doc["rules"] if r.get("effect") == "allow"}
    rego_actors = {r["actor"] for r in rego_rules}
    if json_actors != rego_actors:
        only_json = json_actors - rego_actors
        only_rego = rego_actors - json_actors
        print(f"x actor sets differ: only_json={only_json}, only_rego={only_rego}")
        return 1
    print(f"  ok: {len(json_actors)} actors match exactly across files")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
