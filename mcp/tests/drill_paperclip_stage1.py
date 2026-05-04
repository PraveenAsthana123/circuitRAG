#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Paperclip Stage-1 read-only manager-layer contract.

Per CLAUDE.md §43 + §42 + ADR-012. Locks the contract that the
Stage-1 Paperclip aggregator:

  - exposes ONLY snapshot + verbs (read-only verbs)
  - refuses every write-shaped verb (push/dispatch/assign/...) with a
    §42 citation + exit code 2
  - has NO module-level write code paths (grep-proof)
  - does NOT mutate .loop/ files when snapshot runs (worktree
    byte-identical pre/post)
  - does NOT make outbound HTTP calls (offline-runnable; no httpx /
    requests / urllib import in the module)
  - returns a JSON snapshot with the 6 documented top-level keys
  - importing the module is side-effect-free
  - surfaces the brutal-honesty signal (apply_rate field present even
    when 0%)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERCLIP = REPO / "scripts" / "paperclip_manager.py"
PYTHON = REPO / ".venv" / "bin" / "python3"


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
    print("-- 1. POSITIVE: scripts/paperclip_manager.py exists + executable --")
    if not PAPERCLIP.exists():
        print(f"x {PAPERCLIP} missing")
        return 1
    src = PAPERCLIP.read_text(encoding="utf-8")
    print(f"  ok: {PAPERCLIP.name} present ({len(src)} chars)")

    print("-- 2. POSITIVE: snapshot returns valid JSON with 6 top-level keys --")
    proc = subprocess.run(
        [str(PYTHON), str(PAPERCLIP), "snapshot"],
        capture_output=True, text=True, timeout=30, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x snapshot exited {proc.returncode}: {proc.stderr[:200]}")
        return 1
    try:
        snap = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"x snapshot output not JSON: {e}")
        return 1
    required_keys = {
        "stage", "version", "council_batch", "apply_attempts",
        "audit_decisions", "pending_issues", "council_outcomes",
    }
    missing = required_keys - set(snap.keys())
    if missing:
        print(f"x snapshot missing keys: {missing}")
        return 1
    if snap.get("stage") != 1:
        print(f"x snapshot.stage != 1; got {snap.get('stage')!r}")
        return 1
    print(f"  ok: snapshot has {len(snap)} top-level keys; stage=1")

    print("-- 3. NEGATIVE: source has NO write-style function names --")
    # Stage-1 contract: no `def push_*`, `def dispatch_*`, `def write_*`,
    # `def update_*`, `def mutate_*`, `def delete_*`. Aggregators only.
    forbidden_def = re.compile(
        r"^def\s+(push|dispatch|assign|escalate|merge|deploy|"
        r"rollback|promote|write|update|mutate|delete|create|insert)_",
        re.MULTILINE,
    )
    matches = forbidden_def.findall(src)
    if matches:
        print(f"x found write-style function names: {matches}")
        return 1
    print("  ok: no write-shaped function definitions")

    print("-- 4. NEGATIVE: snapshot does NOT mutate .loop/ files --")
    loop_dir = REPO / ".loop"
    pre_hash = _hash_dir(loop_dir)
    subprocess.run(
        [str(PYTHON), str(PAPERCLIP), "snapshot"],
        capture_output=True, text=True, timeout=30, cwd=REPO,
    )
    post_hash = _hash_dir(loop_dir)
    if pre_hash != post_hash:
        print(f"x .loop/ mutated by snapshot run (pre={pre_hash[:12]} post={post_hash[:12]})")
        return 1
    print(f"  ok: .loop/ byte-identical pre/post snapshot ({pre_hash[:12]}...)")

    print("-- 5. NEGATIVE: source imports NO outbound HTTP libs --")
    # Stage-1 must be offline-runnable. No httpx, requests, urllib.request,
    # aiohttp, urllib3 imports allowed in the module. argparse + json + pathlib
    # + collections are fine.
    forbidden_imports = re.compile(
        r"^(?:import|from)\s+(httpx|requests|aiohttp|urllib3|urllib\.request)\b",
        re.MULTILINE,
    )
    bad = forbidden_imports.findall(src)
    if bad:
        print(f"x found forbidden HTTP imports: {bad}")
        return 1
    print("  ok: no outbound HTTP imports (offline-runnable)")

    print("-- 6. NEGATIVE: every WRITE_VERB is refused with §42 citation + exit 2 --")
    # Test 3 representative write verbs; each must exit 2 + parse to JSON +
    # have the §42 citation in the parsed message field. We check the parsed
    # field (not raw stdout) because json.dumps escapes § → § by default.
    for verb in ("push", "dispatch", "deploy"):
        proc = subprocess.run(
            [str(PYTHON), str(PAPERCLIP), verb],
            capture_output=True, text=True, timeout=10, cwd=REPO,
        )
        if proc.returncode != 2:
            print(f"x verb {verb!r} should exit 2 (§42-gated); got {proc.returncode}")
            return 1
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"x verb {verb!r} refusal output not JSON: {proc.stdout[:200]}")
            return 1
        if payload.get("ok") is not False:
            print(f"x verb {verb!r} refusal payload should have ok=false")
            return 1
        if payload.get("error_code") != "STAGE_1_READ_ONLY":
            print(f"x verb {verb!r} error_code wrong: {payload.get('error_code')!r}")
            return 1
        message = payload.get("message", "")
        if "§42" not in message:
            print(f"x verb {verb!r} message must cite §42; got: {message[:200]!r}")
            return 1
    print("  ok: 3 write verbs all refused with §42 + JSON refusal payload + exit 2")

    print("-- 7. NEGATIVE: importing module triggers NO side effects --")
    # A clean module import must not write files, hit network, or print.
    pre_hash = _hash_dir(loop_dir)
    code = (
        "import sys; sys.path.insert(0, 'scripts'); "
        "import paperclip_manager; "
        "print('IMPORT_OK')"
    )
    proc = subprocess.run(
        [str(PYTHON), "-c", code],
        capture_output=True, text=True, timeout=10, cwd=REPO,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if proc.returncode != 0:
        print(f"x module import failed: {proc.stderr[:200]}")
        return 1
    if "IMPORT_OK" not in proc.stdout:
        print(f"x module import missing sentinel; stdout: {proc.stdout[:200]}")
        return 1
    # Stdout must contain ONLY the sentinel — no other prints.
    extra = proc.stdout.replace("IMPORT_OK", "").strip()
    if extra:
        print(f"x module import had side-effect print output: {extra[:200]}")
        return 1
    post_hash = _hash_dir(loop_dir)
    if pre_hash != post_hash:
        print("x module import mutated .loop/")
        return 1
    print("  ok: import is pure (no prints, no .loop/ mutation)")

    print("-- 8. POSITIVE: snapshot surfaces brutal-honesty apply_rate signal --")
    # The §55.3 outcome contract: apply_rate must be present even at 0%.
    # Without this, Paperclip becomes a vanity dashboard.
    apply = snap.get("apply_attempts", {})
    if "apply_rate" not in apply:
        print(f"x snapshot.apply_attempts missing apply_rate field")
        return 1
    if "honesty_signal" not in apply:
        print(f"x snapshot.apply_attempts missing honesty_signal field")
        return 1
    rate = apply["apply_rate"]
    signal = apply["honesty_signal"]
    if not isinstance(rate, (int, float)):
        print(f"x apply_rate must be numeric; got {type(rate).__name__}")
        return 1
    if not isinstance(signal, str) or not signal:
        print(f"x honesty_signal must be non-empty string; got {signal!r}")
        return 1
    print(f"  ok: apply_rate={rate} | honesty_signal={signal!r}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
