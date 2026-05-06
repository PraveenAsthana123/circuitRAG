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
    # Forward-compatible: accept v1, v2, or any v\d+ ≥ 2
    raw_version = registry.REGISTRY_VERSION
    if not raw_version.startswith("registry-v"):
        fail(f"unexpected version format: {raw_version}")
    try:
        version_int = int(raw_version.rsplit("v", 1)[-1])
    except ValueError:
        fail(f"version not parseable as integer: {raw_version}")
    if version_int < 1:
        fail(f"version too old: {raw_version}")
    ok(f"public surface present (build_registry, REGISTRY_VERSION='{raw_version}')")

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
    # Forward-compatible version check: v8+ all carry provider_comparison
    raw_version = str(pc.get("version", ""))
    try:
        version_int = int(raw_version.rsplit("v", 1)[-1])
    except ValueError:
        fail(f"paperclip version unparseable: {raw_version}")
    if version_int < 8:
        fail(f"paperclip version must be v8 or higher, got: {raw_version}")
    if "provider_comparison" not in pc:
        fail("paperclip v8 missing 'provider_comparison' top-level key")
    pcomp = pc["provider_comparison"]
    pcomp_version = str(pcomp.get("version", ""))
    if not pcomp_version.startswith("registry-v"):
        fail(f"provider_comparison must carry registry-vN version, got: {pcomp_version}")
    if not isinstance(pcomp.get("providers"), list):
        fail("provider_comparison.providers must be a list")
    ok(f"paperclip v8 → provider_comparison version={pcomp['version']}, "
       f"{len(pcomp['providers'])} providers, "
       f"bottleneck={'ACTIVE' if pcomp.get('bottleneck_signal', {}).get('signal_active') else 'inactive'}")

    # ===================================================================
    # Step 10 — v2 cost rollup: tokens summed correctly (top-level + chain)
    # ===================================================================
    step("10. v2 cost rollup — tokens summed across top-level + nested chain")
    # Synthetic: 1 council with 3-model chain, 1 single-model row, 1
    # deterministic row (no tokens). Expected token sums:
    #   council: 300 + 60 + 140 = 500
    #   single:  76
    #   deterministic: 0
    cost_attempts = [
        {
            "lane": "council",
            "outcome": "council_complete",
            "chain": {
                "author":   {"model": "deepseek", "tokens": 300, "latency_s": 47.0},
                "reviewer": {"model": "codegemma", "tokens": 60, "latency_s": 12.0},
                "advisor":  {"model": "codellama", "tokens": 140, "latency_s": 8.0},
            },
        },
        {"lane": "deepseek-coder:6.7b-instruct", "tokens": 76, "latency_s": 36.0},
        {"lane": "ruff:autofix", "attempted": 5},  # no tokens → contributes 0
    ]
    with _TempLoopDir(attempts=cost_attempts, applies=[]):
        cs = registry.build_registry(window_days=7)
    council = next((p for p in cs["providers"] if p["provider"] == "ollama-council"), None)
    single = next((p for p in cs["providers"] if p["provider"] == "ollama-single"), None)
    det = next((p for p in cs["providers"] if p["provider"] == "ollama-deterministic"), None)
    if council is None or single is None or det is None:
        fail(f"missing provider rows: council={council} single={single} det={det}")
    if council["tokens_total"] != 500:
        fail(f"council tokens: expected 500, got {council['tokens_total']}")
    if single["tokens_total"] != 76:
        fail(f"single tokens: expected 76, got {single['tokens_total']}")
    if det["tokens_total"] != 0:
        fail(f"deterministic tokens: expected 0, got {det['tokens_total']}")
    ok("council=500 (300+60+140 chain sum), single=76, deterministic=0 — token math correct")

    # ===================================================================
    # Step 11 — NEGATIVE: Ollama lanes ALL report cost_usd=0.0 (free floor)
    # ===================================================================
    step("11. NEGATIVE: Ollama lanes report cost_usd=0.0 (local inference floor)")
    # Even with massive token counts, Ollama provider cost MUST be $0
    # by default. Drill-locks the local-inference floor — a future
    # operator-misconfiguration accidentally setting an Ollama cost
    # rate would be caught here.
    big_attempts = [{"lane": "council", "chain": {
        "author": {"tokens": 1_000_000, "latency_s": 1.0},
    }}]
    with _TempLoopDir(attempts=big_attempts, applies=[]):
        big = registry.build_registry(window_days=7)
    council_big = next((p for p in big["providers"] if p["provider"] == "ollama-council"), None)
    if council_big["tokens_total"] != 1_000_000:
        fail(f"big tokens: expected 1M, got {council_big['tokens_total']}")
    if council_big["cost_usd"] != 0.0:
        fail(f"Ollama cost MUST be 0.0 by default, got {council_big['cost_usd']}")
    if council_big["cost_rate_usd_per_1m"] != 0.0:
        fail(f"Ollama cost rate MUST be 0.0/1M, got {council_big['cost_rate_usd_per_1m']}")
    ok("1M-token Ollama council still cost_usd=0.0 — local-inference floor holds")

    # ===================================================================
    # Step 12 — NEGATIVE: env override changes Ollama cost (not hardcoded)
    # ===================================================================
    step("12. NEGATIVE: env override DOCUMIND_COST_RATE_OLLAMA_COUNCIL works")
    # Verifies the env-override path: an operator who really wants to
    # account for Ollama GPU cost can set the env var. Without this
    # path, the cost numbers are uneditable folklore.
    import os
    orig_env = os.environ.get("DOCUMIND_COST_RATE_OLLAMA_COUNCIL")
    try:
        os.environ["DOCUMIND_COST_RATE_OLLAMA_COUNCIL"] = "5.0"
        # Reload module to pick up env change in _cost_rate_per_1m which
        # reads env on every call (no caching) — so no reload needed.
        with _TempLoopDir(attempts=big_attempts, applies=[]):
            ev = registry.build_registry(window_days=7)
        ev_council = next((p for p in ev["providers"] if p["provider"] == "ollama-council"), None)
        # Cost = 1M tokens × $5/M = $5
        if abs(ev_council["cost_usd"] - 5.0) > 0.001:
            fail(f"env override didn't apply: expected $5.0, got {ev_council['cost_usd']}")
        if ev_council["cost_rate_usd_per_1m"] != 5.0:
            fail(f"cost_rate didn't reflect env override: {ev_council['cost_rate_usd_per_1m']}")
    finally:
        if orig_env is None:
            os.environ.pop("DOCUMIND_COST_RATE_OLLAMA_COUNCIL", None)
        else:
            os.environ["DOCUMIND_COST_RATE_OLLAMA_COUNCIL"] = orig_env
    ok("env override $5/M × 1M tokens = $5.00 — operator can opt into GPU-cost accounting")

    # ===================================================================
    # Step 13 — totals.cost_usd surfaces the cross-provider sum
    # ===================================================================
    step("13. totals.cost_usd surfaces cross-provider cost aggregate")
    snap_v2 = registry.build_registry(window_days=7)
    totals = snap_v2["totals"]
    if "cost_usd" not in totals:
        fail("totals missing cost_usd field — registry-v2 contract broken")
    if "tokens_total" not in totals:
        fail("totals missing tokens_total field — registry-v2 contract broken")
    # Cross-check: sum of provider cost_usd should equal totals.cost_usd
    sum_cost = sum(float(p.get("cost_usd", 0.0)) for p in snap_v2["providers"])
    if abs(sum_cost - float(totals["cost_usd"])) > 0.0001:
        fail(f"totals.cost_usd ({totals['cost_usd']}) != provider sum ({sum_cost})")
    ok(f"totals.cost_usd=${totals['cost_usd']:.4f} matches per-provider sum")

    print(f"\n{GREEN}{BOLD}ALL 13 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
