# RESOURCES: readonly
"""
Drill: reflection_engine.py — periodic self-critique contract.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous
loop; reflection is the P1 signal layer), §45.4 (no checkbox flips
without code), §47 (architecture: reflection is a separate read-only
runtime concern), §53 row 45 (continuous improvement: outcomes →
drift signals → next iteration).

User's Environment State doc listed Reflection Engine as ❌ Missing
(P1). Iter-58 ships scripts/reflection_engine.py (read-only audit
analyzer) + this drill that locks the contract.

Locks (positive):
  L1. reflect() callable + returns ReflectionReport
  L2. ReflectionReport has all required fields (generated_at,
      window_days, total_attempts, applied, apply_rate, by_lane,
      by_rule_code, drift_signals, recommended_actions, honesty_signal)
  L3. apply_rate ∈ [0.0, 1.0] for both overall and per-lane
  L4. CLI --json mode emits valid JSON parseable by `json.loads`
  L5. Empty audit input → empty report (no crash; honesty_signal still set)

Locks (negative — ≥3 per §43):
  N1. Reflection engine NEVER writes to disk (read-only contract;
      drill greps source for write verbs in the engine module)
  N2. Reflection engine NEVER calls external services (no urlopen,
      no requests, no httpx, no socket — read-only audit analysis only)
  N3. drift signals only fire when min_attempts >= threshold (low-N
      lanes don't trigger spurious recommendations — flake guard)
  N4. apply_rate is capped at 1.0 (cross-source double-counting from
      audit + decisions JSONL must NOT push it > 1.0)
  N5. Empty input does NOT crash (boundary held; missing files OK)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "scripts" / "reflection_engine.py"
sys.path.insert(0, str(REPO / "scripts"))

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


def main() -> int:
    if not ENGINE.exists():
        fail(f"missing: {ENGINE.relative_to(REPO)}")

    src = ENGINE.read_text(encoding="utf-8")

    import reflection_engine  # type: ignore[import-not-found]

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: reflect() callable
    # ------------------------------------------------------------------
    step("1. reflection_engine.reflect() callable + returns ReflectionReport")
    if not callable(getattr(reflection_engine, "reflect", None)):
        fail("reflect() is not callable")
    if not hasattr(reflection_engine, "ReflectionReport"):
        fail("ReflectionReport class missing")
    report = reflection_engine.reflect(window_days=7)
    if not isinstance(report, reflection_engine.ReflectionReport):
        fail(f"reflect() returned {type(report).__name__}, not ReflectionReport")
    ok("reflect() callable + returns ReflectionReport")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: report has all required fields
    # ------------------------------------------------------------------
    step("2. ReflectionReport has all required fields")
    required_fields = (
        "generated_at",
        "window_days",
        "total_attempts",
        "applied",
        "apply_rate",
        "by_lane",
        "by_rule_code",
        "drift_signals",
        "recommended_actions",
        "honesty_signal",
    )
    missing = [f for f in required_fields if not hasattr(report, f)]
    if missing:
        fail(f"ReflectionReport missing fields: {missing}")
    ok(f"all {len(required_fields)} required fields present")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: apply_rate ∈ [0, 1] overall + per-lane
    # ------------------------------------------------------------------
    step("3. apply_rate ∈ [0, 1] for overall + every lane")
    if not 0.0 <= report.apply_rate <= 1.0:
        fail(f"overall apply_rate={report.apply_rate} outside [0, 1]")
    for lane, stats in report.by_lane.items():
        if not 0.0 <= stats.apply_rate <= 1.0:
            fail(
                f"lane {lane!r} apply_rate={stats.apply_rate} outside [0, 1]"
            )
        if stats.applied > stats.attempted:
            fail(
                f"lane {lane!r} applied={stats.applied} > "
                f"attempted={stats.attempted} (counter logic broken)"
            )
    ok(f"apply_rate ∈ [0, 1] for overall + {len(report.by_lane)} lane(s)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: CLI --json emits valid JSON
    # ------------------------------------------------------------------
    step("4. CLI --json mode emits parseable JSON")
    proc = subprocess.run(
        [
            "/mnt/deepa/rag/.venv/bin/python3",
            str(ENGINE),
            "--window",
            "7",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
    )
    if proc.returncode != 0:
        fail(f"CLI --json exited {proc.returncode}: {proc.stderr[:200]}")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        fail(f"CLI --json output not valid JSON: {e}")
    for f in ("generated_at", "apply_rate", "by_lane", "drift_signals"):
        if f not in parsed:
            fail(f"CLI --json output missing field: {f}")
    ok("CLI --json emits valid JSON with all top-level fields")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: empty input → empty report (no crash)
    # ------------------------------------------------------------------
    step("5. Empty input → empty report (no crash; honesty_signal set)")
    with tempfile.TemporaryDirectory() as td:
        empty_audit = Path(td) / "empty_audit.jsonl"
        empty_decisions = Path(td) / "empty_decisions.jsonl"
        empty_audit.write_text("", encoding="utf-8")
        empty_decisions.write_text("", encoding="utf-8")
        empty_report = reflection_engine.reflect(
            audit_path=empty_audit,
            decisions_path=empty_decisions,
            window_days=7,
        )
        if empty_report.total_attempts != 0:
            fail(
                f"empty input produced total_attempts={empty_report.total_attempts}"
            )
        if empty_report.apply_rate != 0.0:
            fail(f"empty input produced apply_rate={empty_report.apply_rate}")
        if not empty_report.honesty_signal:
            fail("empty input produced empty honesty_signal — operator can't see state")
    ok("empty input handled cleanly; honesty_signal still populated")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: engine source has NO write verbs
    # ------------------------------------------------------------------
    step("6. NEGATIVE: reflection_engine source has no write verbs (read-only)")
    forbidden_writes = (
        ".write(",
        ".write_text(",
        ".write_bytes(",
        "open(.*[\"']w[\"']",  # regex-shaped; checked separately
        "json.dump(",
    )
    leaks: list[str] = []
    for v in forbidden_writes:
        if v == "open(.*[\"']w[\"']":
            if re.search(r"open\([^)]*[\"']w[\"']", src):
                leaks.append("open(...,'w')")
            continue
        if v in src:
            # Allow .write( in standard-output `print` paths; we're scanning
            # for file-system writes specifically. The current source uses
            # only `print()` and JSON-serialization to stdout — no file ops.
            # If .write( ever appears, it'd be a regression.
            leaks.append(v)
    if leaks:
        fail(
            f"reflection_engine has write verbs: {leaks} — read-only "
            f"contract violated"
        )
    ok("no write verbs in source (read-only contract held)")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: engine source makes NO external calls
    # ------------------------------------------------------------------
    step("7. NEGATIVE: reflection_engine source makes no external calls")
    forbidden_external = (
        "urlopen(",
        "requests.",
        "httpx.",
        "import socket",
        "subprocess.run",
        "subprocess.Popen",
    )
    leaks = [v for v in forbidden_external if v in src]
    if leaks:
        fail(
            f"reflection_engine has external-call verbs: {leaks}. "
            f"Reflection is read-only audit analysis; no network/IPC."
        )
    ok("no external-call verbs (offline-pure analyzer)")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: drift signals respect min_attempts threshold
    # ------------------------------------------------------------------
    step("8. NEGATIVE: drift signals respect min_attempts threshold (flake guard)")
    # Build a tiny audit with 2 attempts of one lane (below default min=5).
    # Even if both fail, the drift signal should NOT fire.
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "audit.jsonl"
        decisions = Path(td) / "decisions.jsonl"
        audit.write_text(
            '\n'.join(
                json.dumps(
                    {
                        "id": "ruff-X-x.py-L1",
                        "lane": "council",
                        "outcome": "rejected",
                        "ts": "2026-05-06T00:00:00+00:00",
                        "latency_s": 1.0,
                        "tokens": 10,
                    }
                )
                for _ in range(2)
            ),
            encoding="utf-8",
        )
        decisions.write_text("", encoding="utf-8")
        report_low_n = reflection_engine.reflect(
            audit_path=audit,
            decisions_path=decisions,
            window_days=30,
            min_attempts=5,
        )
        # 2 attempts < 5 min — apply_rate is 0%, but drift_signals should
        # NOT include a "lane 'council'" entry (would be premature alarm)
        lane_signals = [
            s for s in report_low_n.drift_signals
            if s.startswith("lane 'council'")
        ]
        if lane_signals:
            fail(
                f"drift signal fired with only 2 attempts (min_attempts=5): "
                f"{lane_signals}. Flake guard broken."
            )
    ok("drift signals suppressed below min_attempts threshold (flake guard)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: apply_rate capped at 1.0 even with double-counting
    # ------------------------------------------------------------------
    step("9. NEGATIVE: apply_rate capped at 1.0 (no double-counting overflow)")
    # Engineered case: audit has 1 row marked applied; decisions ALSO has
    # the same id marked applied. Both contribute → naive count = 2 applied
    # for 1 attempted = apply_rate 2.0 → must be capped at 1.0.
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "audit.jsonl"
        decisions = Path(td) / "decisions.jsonl"
        ts = "2026-05-06T00:00:00+00:00"
        audit.write_text(
            json.dumps(
                {
                    "id": "ruff-Y-y.py-L1",
                    "lane": "council",
                    "outcome": "applied",
                    "ts": ts,
                }
            ) + "\n",
            encoding="utf-8",
        )
        decisions.write_text(
            json.dumps({"id": "ruff-Y-y.py-L1", "outcome": "applied", "ts": ts})
            + "\n",
            encoding="utf-8",
        )
        cap_report = reflection_engine.reflect(
            audit_path=audit,
            decisions_path=decisions,
            window_days=30,
            min_attempts=1,
        )
        for lane, stats in cap_report.by_lane.items():
            if stats.apply_rate > 1.0:
                fail(
                    f"lane {lane!r} apply_rate={stats.apply_rate} > 1.0 — "
                    f"double-counting cap broken"
                )
            if stats.applied > stats.attempted:
                fail(
                    f"lane {lane!r} applied={stats.applied} > "
                    f"attempted={stats.attempted}"
                )
        if cap_report.apply_rate > 1.0:
            fail(f"overall apply_rate={cap_report.apply_rate} > 1.0")
    ok("apply_rate capped at 1.0 (double-counting cap held)")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED (5 positive + 4 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
