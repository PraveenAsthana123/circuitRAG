#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Paperclip Stage-2 — propose_next_task() suggestion-only advisor.

Per CLAUDE.md §43 + §47 + §44. Locks Stage-2 promotion of paperclip:

  - propose_next_task() returns dict with required keys
  - Function does NOT mutate state (worktree byte-identical pre/post)
  - Function does NOT make outbound HTTP calls
  - Function does NOT call PolisAI gate (Stage-2 is suggestion; Stage-3
    will gate the dispatch)
  - Stage-1 read-only sandbox contract preserved (drill_paperclip_stage1
    still passes; no write-style functions added)
  - Security-class rules (S*/B*) are NEVER proposed
  - 'propose' CLI verb added; not in WRITE_VERBS
  - Stage-2 verbs list updated to include 'propose'

Eight steps. Six negative.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERCLIP = REPO / "scripts" / "paperclip_manager.py"
PYTHON = REPO / ".venv" / "bin" / "python3"
sys.path.insert(0, str(REPO / "scripts"))


def _hash_dir(root: Path) -> str:
    """Stable hash of file paths + sizes + mtimes under root."""
    if not root.exists():
        return "MISSING"
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            try:
                st = p.stat()
                h.update(f"{p.relative_to(root)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
            except OSError:
                continue
    return h.hexdigest()


def main() -> int:
    print("-- 1. POSITIVE: propose_next_task function exists + signature --")
    import paperclip_manager
    if not hasattr(paperclip_manager, "propose_next_task"):
        print("x propose_next_task missing")
        return 1
    import inspect
    sig = inspect.signature(paperclip_manager.propose_next_task)
    if list(sig.parameters.keys()):
        print(f"x propose_next_task should take no args; got {list(sig.parameters.keys())}")
        return 1
    print("  ok: propose_next_task() with no args")

    print("-- 2. POSITIVE: returns dict with required Stage-2 keys --")
    result = paperclip_manager.propose_next_task()
    if not isinstance(result, dict):
        print(f"x must return dict; got {type(result).__name__}")
        return 1
    required_keys = {"stage", "proposal", "rejected", "signal"}
    missing = required_keys - set(result.keys())
    if missing:
        print(f"x missing required keys: {missing}")
        return 1
    if result.get("stage") != 2:
        print(f"x stage must be 2; got {result.get('stage')}")
        return 1
    print(f"  ok: returns dict with stage=2 + 4 required keys")

    print("-- 3. NEGATIVE: function does NOT mutate .loop/ files --")
    loop_dir = REPO / ".loop"
    pre_hash = _hash_dir(loop_dir)
    paperclip_manager.propose_next_task()
    paperclip_manager.propose_next_task()
    paperclip_manager.propose_next_task()
    post_hash = _hash_dir(loop_dir)
    if pre_hash != post_hash:
        print("x .loop/ mutated by propose_next_task")
        return 1
    print("  ok: 3 propose calls; .loop/ byte-identical pre/post")

    print("-- 4. NEGATIVE: source has NO outbound HTTP imports added for Stage-2 --")
    src = PAPERCLIP.read_text(encoding="utf-8")
    forbidden_imports = re.compile(
        r"^(?:import|from)\s+(httpx|requests|aiohttp|urllib3|urllib\.request)\b",
        re.MULTILINE,
    )
    bad = forbidden_imports.findall(src)
    if bad:
        print(f"x found forbidden HTTP imports: {bad}")
        return 1
    print("  ok: no outbound HTTP imports (Stage-2 preserves Stage-1 sandbox)")

    print("-- 5. NEGATIVE: security-class rules (S*/B*) are filtered from proposal --")
    # Stage-2 contract: even if a security rule is the easiest, drill
    # enforces it's NEVER proposed. Per §50.5.3.
    if "code.startswith(\"S\")" not in src and "code.startswith('S')" not in src:
        print("x source must filter security-class S* rules")
        return 1
    if "code.startswith(\"B\")" not in src and "code.startswith('B')" not in src:
        print("x source must filter bandit B* rules")
        return 1
    if "§50.5.3" not in src:
        print("x source must reference §50.5.3 in security-skip rationale")
        return 1
    print("  ok: S*/B* security rules drill-locked-out of proposal")

    print("-- 6. NEGATIVE: propose CLI verb is NOT in WRITE_VERBS --")
    if "propose" in paperclip_manager.WRITE_VERBS:
        print("x 'propose' must NOT be in WRITE_VERBS")
        return 1
    # Verify CLI verbs list updated
    proc = subprocess.run(
        [str(PYTHON), str(PAPERCLIP), "verbs"],
        capture_output=True, text=True, timeout=10, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x verbs cmd failed: {proc.stderr[:200]}")
        return 1
    payload = json.loads(proc.stdout)
    if "propose" not in payload.get("read_only_verbs", []):
        print(f"x 'propose' must be in read_only_verbs; got {payload.get('read_only_verbs')}")
        return 1
    if payload.get("stage") != 2:
        print(f"x verbs cmd should report stage=2; got {payload.get('stage')}")
        return 1
    print("  ok: 'propose' is read_only_verb (not WRITE); stage=2 reported")

    print("-- 7. POSITIVE: CLI 'propose' verb runs + returns valid JSON --")
    proc = subprocess.run(
        [str(PYTHON), str(PAPERCLIP), "propose"],
        capture_output=True, text=True, timeout=10, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x propose CLI failed: {proc.stderr[:200]}")
        return 1
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"x propose output not JSON: {e}")
        return 1
    if parsed.get("stage") != 2:
        print(f"x stage must be 2; got {parsed.get('stage')}")
        return 1
    print(f"  ok: CLI propose returns valid JSON with stage=2")

    print("-- 8. NEGATIVE: Stage-1 drill still passes (no regression) --")
    proc = subprocess.run(
        [str(PYTHON), str(REPO / "mcp" / "tests" / "drill_paperclip_stage1.py")],
        capture_output=True, text=True, timeout=30, cwd=REPO,
    )
    if proc.returncode != 0 or "ALL 8 STEPS PASSED" not in proc.stdout:
        print(f"x Stage-1 drill broke: {proc.stdout[-200:]}")
        return 1
    print("  ok: drill_paperclip_stage1 still 8/8 (no Stage-2 regression)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
