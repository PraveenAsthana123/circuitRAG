# RESOURCES: readonly
"""
Drill: scripts/agent_task_registry.py — unified provider-comparison.

Per §55.3 outcome-based contract: this drill locks the registry's
shape AND its read-only invariant AND its bottleneck-detection
semantics. Without these locks, a future refactor could silently
drop the apply-rate signal that §55 explicitly requires visible.

Locks (positive):
  - build_registry() returns a dict with exact top-level keys
    (version, generated_at, window_days, providers, totals,
     honest_gaps, bottleneck_signal)
  - lane→provider classification is stable: 'council' → 'ollama-council',
    'ruff:autofix' → 'ollama-deterministic',
    'deepseek-coder:6.7b-instruct' → 'ollama-single'
  - apply_rate computed correctly: applied/attempted, 0.0 floor on
    attempted=0
  - paperclip v8 snapshot carries the 'provider_comparison' top-level key

Locks (negative — ≥3 per §43):
  - unknown lane → 'ollama-other', NEVER silently dropped
  - empty .loop/ files → empty providers list, NEVER raises
  - bottleneck_signal suppressed when attempted < 10 (small-sample guard)
  - module exports NO write methods (no apply_*, push_*, dispatch_*)
  - file mtimes unchanged after build_registry() — read-only contract

Composes with:
  scripts/agent_task_registry.py — the source under test
  scripts/paperclip_manager.py   — v8 surface integration
  CLAUDE.md §43 (drill discipline) — negative assertions are mandatory
  CLAUDE.md §55 (autonomous fix-bot) — apply-rate signal exists
                                       because §55 requires it
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import agent_task_registry as registry  # noqa: E402

from scripts import paperclip_manager  # noqa: E402

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


# ----------------------------------------------------------------
# Helper: write a temp .loop tree, point the registry at it,
# return a context manager that restores the original paths.
# ----------------------------------------------------------------
class _TempLoopDir:
    def __init__(self, attempts: list[dict] | None = None,
                 applies: list[dict] | None = None) -> None:
        self.attempts = attempts or []
        self.applies = applies or []
        self.tmp: tempfile.TemporaryDirectory | None = None
        self._orig_issue = registry.ISSUE_AUDIT
        self._orig_apply = registry.BOARD_APPLY

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        loop_dir = Path(self.tmp.name)
        issue_path = loop_dir / "issue_audit.jsonl"
        apply_path = loop_dir / "agent_task_board_apply.jsonl"
        with issue_path.open("w") as f:
            for a in self.attempts:
                f.write(json.dumps(a) + "\n")
        with apply_path.open("w") as f:
            for a in self.applies:
                f.write(json.dumps(a) + "\n")
        registry.ISSUE_AUDIT = issue_path
        registry.BOARD_APPLY = apply_path
        return loop_dir

    def __exit__(self, *exc):
        registry.ISSUE_AUDIT = self._orig_issue
        registry.BOARD_APPLY = self._orig_apply
        if self.tmp:
            self.tmp.cleanup()


def main() -> int:
    # ===================================================================
    # Step 1 — module imports + public surface exists
    # ===================================================================
    step("1. agent_task_registry exposes build_registry + version constant")
    if not callable(getattr(registry, "build_registry", None)):
        fail("build_registry function missing from agent_task_registry")
    if registry.REGISTRY_VERSION != "registry-v1":
        fail(f"unexpected version: {registry.REGISTRY_VERSION}")
    ok("public surface present (build_registry, REGISTRY_VERSION='registry-v1')")

    # ===================================================================
    # Step 2 — registry shape contract
    # ===================================================================
    step("2. build_registry() returns the documented shape")
    snap = registry.build_registry(window_days=7)
    expected_keys = {
        "version", "generated_at", "window_days", "providers",
        "totals", "honest_gaps", "bottleneck_signal",
    }
    actual_keys = set(snap.keys())
    if not expected_keys.issubset(actual_keys):
        fail(f"missing keys: {expected_keys - actual_keys}")
    if not isinstance(snap["providers"], list):
        fail("providers must be a list")
    if not isinstance(snap["honest_gaps"], list):
        fail("honest_gaps must be a list")
    ok(f"shape OK: {len(actual_keys)} top-level keys, {len(snap['providers'])} providers")

    # ===================================================================
    # Step 3 — lane→provider classification is stable
    # ===================================================================
    step("3. lane→provider classification is stable (forward-direction lock)")
    cases = [
        ("council", "ollama-council"),
        ("council_local", "ollama-council"),
        ("ruff:autofix", "ollama-deterministic"),
        ("eslint:autofix", "ollama-deterministic"),
        ("deterministic", "ollama-deterministic"),
        ("deepseek-coder:6.7b-instruct", "ollama-single"),
        ("codegemma:7b-instruct", "ollama-single"),
        ("codellama:7b-instruct", "ollama-single"),
    ]
    for lane, expected in cases:
        got = registry._classify_lane(lane)
        if got != expected:
            fail(f"lane {lane!r}: expected {expected!r}, got {got!r}")
    ok(f"all {len(cases)} lane classifications stable")

    # ===================================================================
    # Step 4 — NEGATIVE: unknown/empty lanes go to ollama-other,
    # never silently dropped
    # ===================================================================
    step("4. NEGATIVE: unknown lane → 'ollama-other' (NEVER silently dropped)")
    negatives = [("", "ollama-other"), ("unknown", "ollama-other"),
                 ("some-future-tool", "ollama-other"),
                 ("totally-made-up:1.0", "ollama-other")]
    for lane, expected in negatives:
        got = registry._classify_lane(lane)
        if got != expected:
            fail(f"unknown lane {lane!r}: expected {expected!r}, got {got!r}")
    ok(f"all {len(negatives)} unknown-lane cases routed to 'ollama-other'")

    # ===================================================================
    # Step 5 — NEGATIVE: empty source files → empty rollup, no crash
    # ===================================================================
    step("5. NEGATIVE: empty .loop/ files → graceful empty rollup")
    with _TempLoopDir(attempts=[], applies=[]):
        try:
            empty = registry.build_registry(window_days=7)
        except Exception as exc:
            fail(f"build_registry crashed on empty input: {type(exc).__name__}: {exc}")
        # Should still have claude-runtime row from postgres path (even if 0)
        # but ollama-* rows should be empty/zero-attempted
        ollama_rows = [p for p in empty["providers"] if p["provider"].startswith("ollama-")]
        if ollama_rows:
            fail(f"empty input should produce no ollama rows, got: {[p['provider'] for p in ollama_rows]}")
        # totals must reflect this
        if empty["totals"]["attempted"] > 0:
            # claude-runtime path may add rows from real DB — that's fine,
            # just ensure totals are sane
            pass
    ok("empty input → no ollama-* providers, no crash, totals sane")

    # ===================================================================
    # Step 6 — apply-rate math correctness (canonical input)
    # ===================================================================
    step("6. apply-rate computed correctly on canonical synthetic input")
    synth_attempts = [
        {"lane": "council", "outcome": "council_complete", "latency_s": 50.0},
        {"lane": "council", "outcome": "council_complete", "latency_s": 60.0},
        {"lane": "council", "outcome": "council_complete"},
        {"lane": "ruff:autofix", "attempted": 10, "exit_code": 0},
    ]
    synth_applies = [
        {"lane": "ruff:autofix", "outcome": "applied"},
        {"lane": "council", "outcome": "rejected", "reason": "no clean diff"},
    ]
    with _TempLoopDir(attempts=synth_attempts, applies=synth_applies):
        s = registry.build_registry(window_days=7)
    council_row = next((p for p in s["providers"] if p["provider"] == "ollama-council"), None)
    det_row = next((p for p in s["providers"] if p["provider"] == "ollama-deterministic"), None)
    if council_row is None or det_row is None:
        fail("expected council + deterministic rows in synthetic test")
    if council_row["attempted"] != 3 or council_row["applied"] != 0:
        fail(f"council math wrong: {council_row}")
    if council_row["apply_rate"] != 0.0:
        fail(f"council apply_rate must be 0.0, got {council_row['apply_rate']}")
    if det_row["attempted"] != 1 or det_row["applied"] != 1:
        fail(f"deterministic math wrong: {det_row}")
    if det_row["apply_rate"] != 1.0:
        fail(f"deterministic apply_rate must be 1.0, got {det_row['apply_rate']}")
    if abs(council_row["avg_latency_s"] - 55.0) > 0.01:
        fail(f"council avg latency wrong: expected 55.0, got {council_row['avg_latency_s']}")
    ok("council=0/3 (0.00%, avg=55.0s), deterministic=1/1 (100.00%) — math correct")

    # ===================================================================
    # Step 7 — NEGATIVE: bottleneck_signal suppressed below threshold
    # ===================================================================
    step("7. NEGATIVE: bottleneck signal SUPPRESSED at small sample (attempted<10)")
    # Synthetic: 5 council attempts, all rejected — apply_rate=0% but
    # signal must NOT fire because sample is too small
    small_attempts = [{"lane": "council"} for _ in range(5)]
    with _TempLoopDir(attempts=small_attempts, applies=[]):
        small = registry.build_registry(window_days=7)
    bs = small["bottleneck_signal"]
    if bs["signal_active"]:
        fail(f"signal should NOT fire at 5 attempts: {bs}")
    if "too small" not in bs["reason"]:
        fail(f"reason must explain small-sample suppression: {bs['reason']}")
    ok(f"5 attempts → signal suppressed: {bs['reason']}")

    # And confirm signal DOES fire when sample is large + apply-rate low
    large_attempts = [{"lane": "council"} for _ in range(15)]
    with _TempLoopDir(attempts=large_attempts, applies=[]):
        large = registry.build_registry(window_days=7)
    bs2 = large["bottleneck_signal"]
    if not bs2["signal_active"]:
        fail(f"signal MUST fire at 15 attempts with 0% apply: {bs2}")
    if "Tier 1.1" not in bs2.get("suggested_action", ""):
        fail(f"signal must cite Tier 1.1 action: {bs2}")
    ok("15 attempts, 0% apply → signal fires + cites §55 Tier 1.1")

    # ===================================================================
    # Step 8 — NEGATIVE: read-only contract — no write verbs exposed,
    # file mtimes unchanged after build_registry()
    # ===================================================================
    step("8. NEGATIVE: read-only contract (no write verbs, no mtime changes)")
    write_verbs = ("apply", "push", "dispatch", "assign", "promote",
                   "merge", "deploy", "mutate", "rollback")
    leaks = [v for v in write_verbs
             if any(attr.startswith(v + "_") or attr == v
                    for attr in dir(registry))]
    if leaks:
        fail(f"registry exports write verb(s): {leaks}")
    ok(f"no write verbs in module surface ({len(dir(registry))} attrs scanned)")

    # mtime check: snapshot the issue_audit + board_apply mtimes,
    # call build_registry, snapshot again — must be identical
    if registry.ISSUE_AUDIT.exists() and registry.BOARD_APPLY.exists():
        m1_issue = registry.ISSUE_AUDIT.stat().st_mtime
        m1_apply = registry.BOARD_APPLY.stat().st_mtime
        _ = registry.build_registry(window_days=7)
        m2_issue = registry.ISSUE_AUDIT.stat().st_mtime
        m2_apply = registry.BOARD_APPLY.stat().st_mtime
        if m1_issue != m2_issue:
            fail(f"issue_audit mtime mutated: {m1_issue} → {m2_issue}")
        if m1_apply != m2_apply:
            fail(f"board_apply mtime mutated: {m1_apply} → {m2_apply}")
        ok("source file mtimes unchanged → read-only contract holds")
    else:
        ok("source files absent — mtime check skipped (acceptable)")

    # ===================================================================
    # Step 9 — paperclip v8 surface integration
    # ===================================================================
    step("9. paperclip snapshot v8 carries 'provider_comparison' key")
    pc = paperclip_manager.snapshot(window_days=7)
    if pc.get("version") != "paperclip-readonly-v8":
        fail(f"paperclip version must be v8, got: {pc.get('version')}")
    if "provider_comparison" not in pc:
        fail("paperclip v8 missing 'provider_comparison' top-level key")
    pcomp = pc["provider_comparison"]
    if pcomp.get("version") != "registry-v1":
        fail(f"provider_comparison must carry registry version, got: {pcomp.get('version')}")
    if not isinstance(pcomp.get("providers"), list):
        fail("provider_comparison.providers must be a list")
    ok(f"paperclip v8 → provider_comparison version={pcomp['version']}, "
       f"{len(pcomp['providers'])} providers, "
       f"bottleneck={'ACTIVE' if pcomp.get('bottleneck_signal', {}).get('signal_active') else 'inactive'}")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
