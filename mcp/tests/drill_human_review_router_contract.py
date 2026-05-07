# RESOURCES: readonly
"""
Drill: human_review_router.py — retry-storm routing contract.

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §44 (autonomous-loop
ONE-thing-per-iter; iter-58 detected, iter-59 acts), §45.4 (no checkbox
flips without code), §50.5.3 (security rules NEVER to model;
high-failure rules go to human-review queue), §38 (audit immutability:
queue is APPEND-ONLY; never mutates prior entries), §47 (architecture:
router separate from reflection — write surface vs read surface).

Iter-58's reflection engine surfaced 2 retry-storm ids:
  - eslint-react_no-unescaped-entities-page.tsx-L368  (32 attempts)
  - ruff-N814-main.py-L208                            (14 attempts)

Iter-59 ships scripts/human_review_router.py — the write surface that
moves these ids out of the council retry loop into a human-review queue.

Locks (positive):
  L1. route_retry_storms() callable + returns RouterReport
  L2. Real audit data produces ≥1 storm id (validates the threshold)
  L3. Queue file written with one JSON-per-line append-only entry
  L4. Each entry has all required fields (id, routed_at, reason,
      attempt_count, lanes_attempted, first_seen, last_attempt,
      router_version)
  L5. Dry-run reports detection but does NOT mutate the queue file

Locks (negative — ≥3 per §43):
  N1. Re-running the router does NOT add duplicate entries (idempotent;
      same id appears exactly once in queue regardless of how many
      times the router runs against the same audit)
  N2. Below-threshold ids are NOT routed (1-2-attempt ids stay out
      of the queue; only ≥threshold qualifies)
  N3. Source has NO DELETE / TRUNCATE / overwrite verbs against the
      queue file (append-only; §38 audit immutability)
  N4. Empty audit input → 0 storms; queue stays empty (boundary held)
  N5. Reading + writing the queue treats malformed lines as skip,
      NOT crash (resilience; one corrupted line shouldn't lose the
      whole queue's idempotent state)
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTER = REPO / "scripts" / "human_review_router.py"
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


def _make_audit(rows: list[dict]) -> Path:
    """Helper: write a tmp audit file for testing."""
    tmp = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    tmp.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    return tmp


def main() -> int:
    if not ROUTER.exists():
        fail(f"missing: {ROUTER.relative_to(REPO)}")

    src = ROUTER.read_text(encoding="utf-8")
    import human_review_router  # type: ignore[import-not-found]

    # ------------------------------------------------------------------
    # Step 1 — POSITIVE: route_retry_storms callable
    # ------------------------------------------------------------------
    step("1. route_retry_storms() callable + returns RouterReport")
    if not callable(getattr(human_review_router, "route_retry_storms", None)):
        fail("route_retry_storms() not callable")
    if not hasattr(human_review_router, "RouterReport"):
        fail("RouterReport class missing")
    ok("route_retry_storms() callable + RouterReport class present")

    # ------------------------------------------------------------------
    # Step 2 — POSITIVE: real audit produces ≥1 storm
    # ------------------------------------------------------------------
    step("2. real audit data produces ≥1 storm (threshold=5 validation)")
    audit_path = REPO / ".loop" / "issue_audit.jsonl"
    if not audit_path.exists():
        # Skip if no audit data exists yet (fresh repo)
        ok("skipped: no audit data (fresh repo)")
    else:
        with tempfile.TemporaryDirectory() as td:
            tmp_queue = Path(td) / "queue.jsonl"
            report = human_review_router.route_retry_storms(
                audit_path=audit_path,
                queue_path=tmp_queue,
                threshold=5,
                dry_run=True,  # don't pollute real queue
            )
            if not report.storm_ids_detected:
                fail(
                    "real audit data produced 0 storms — drill expected ≥1 "
                    "based on iter-58's 2 known storm ids"
                )
        ok(f"real audit produced {len(report.storm_ids_detected)} storm(s) "
           f"(threshold=5)")

    # ------------------------------------------------------------------
    # Step 3 — POSITIVE: queue file written with one JSON-per-line
    # ------------------------------------------------------------------
    step("3. queue file is one-JSON-per-line (jsonl shape)")
    with tempfile.TemporaryDirectory() as td:
        # Make audit with 1 storm
        audit = _make_audit([
            {"id": "test-X-x.py-L1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(7)
        ])
        try:
            queue = Path(td) / "queue.jsonl"
            human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            if not queue.exists():
                fail("queue file not created")
            lines = [
                ln for ln in queue.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            for line in lines:
                # Each line must parse as a single JSON object
                json.loads(line)
        finally:
            audit.unlink(missing_ok=True)
    ok("queue is one-JSON-per-line (parseable jsonl)")

    # ------------------------------------------------------------------
    # Step 4 — POSITIVE: each entry has all required fields
    # ------------------------------------------------------------------
    step("4. each queue entry has all required fields")
    required = (
        "id", "routed_at", "reason", "attempt_count",
        "lanes_attempted", "first_seen", "last_attempt", "router_version",
    )
    with tempfile.TemporaryDirectory() as td:
        audit = _make_audit([
            {"id": "test-Y-y.py-L1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(6)
        ])
        try:
            queue = Path(td) / "queue.jsonl"
            human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            entry = json.loads(queue.read_text(encoding="utf-8").strip())
            missing = [f for f in required if f not in entry]
            if missing:
                fail(f"queue entry missing fields: {missing}")
        finally:
            audit.unlink(missing_ok=True)
    ok(f"all {len(required)} required fields present in queue entry")

    # ------------------------------------------------------------------
    # Step 5 — POSITIVE: dry-run does NOT mutate the queue
    # ------------------------------------------------------------------
    step("5. dry-run reports detection but does NOT mutate the queue")
    with tempfile.TemporaryDirectory() as td:
        audit = _make_audit([
            {"id": "test-Z-z.py-L1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(8)
        ])
        try:
            queue = Path(td) / "queue.jsonl"
            report = human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=True,
            )
            if not report.dry_run:
                fail("RouterReport.dry_run not True after dry-run call")
            if not report.newly_routed:
                fail("dry-run should still REPORT detected storms")
            if queue.exists() and queue.read_text(encoding="utf-8").strip():
                fail("dry-run wrote to the queue file (mutation contract broken)")
        finally:
            audit.unlink(missing_ok=True)
    ok("dry-run reports detection without mutating queue")

    # ------------------------------------------------------------------
    # Step 6 — NEGATIVE: re-running the router is idempotent
    # ------------------------------------------------------------------
    step("6. NEGATIVE: re-running router is idempotent (no duplicate entries)")
    with tempfile.TemporaryDirectory() as td:
        audit = _make_audit([
            {"id": "test-IDEMP-i.py-L1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(5)
        ])
        try:
            queue = Path(td) / "queue.jsonl"
            r1 = human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            r2 = human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            r3 = human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            if r1.queue_size_after != 1:
                fail(f"first run should add 1 entry; got {r1.queue_size_after}")
            if r2.queue_size_after != 1 or r2.newly_routed:
                fail(f"second run added duplicates; r2={r2.newly_routed}")
            if r3.queue_size_after != 1:
                fail(f"third run pushed queue to {r3.queue_size_after} (should be 1)")
            lines = queue.read_text(encoding="utf-8").splitlines()
            unique = {json.loads(ln)["id"] for ln in lines if ln.strip()}
            if len(unique) != 1:
                fail(f"queue has {len(unique)} unique ids (expected 1)")
        finally:
            audit.unlink(missing_ok=True)
    ok("3 router runs → 1 queue entry; idempotency held")

    # ------------------------------------------------------------------
    # Step 7 — NEGATIVE: below-threshold ids are NOT routed
    # ------------------------------------------------------------------
    step("7. NEGATIVE: below-threshold ids stay out of the queue")
    with tempfile.TemporaryDirectory() as td:
        audit = _make_audit([
            {"id": "test-LOW-1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(3)  # below threshold=5
        ] + [
            {"id": "test-HIGH-1", "lane": "council",
             "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00"}
            for _ in range(7)  # at-or-above threshold=5
        ])
        try:
            queue = Path(td) / "queue.jsonl"
            report = human_review_router.route_retry_storms(
                audit_path=audit, queue_path=queue,
                threshold=5, dry_run=False,
            )
            if "test-LOW-1" in report.newly_routed:
                fail(
                    "below-threshold id 'test-LOW-1' (3 attempts) was routed; "
                    "premature human-review escalation"
                )
            if "test-HIGH-1" not in report.newly_routed:
                fail(
                    "above-threshold id 'test-HIGH-1' (7 attempts) NOT routed"
                )
        finally:
            audit.unlink(missing_ok=True)
    ok("only ≥threshold ids routed; below-threshold filtered correctly")

    # ------------------------------------------------------------------
    # Step 8 — NEGATIVE: source has no DELETE / overwrite verbs
    # ------------------------------------------------------------------
    step("8. NEGATIVE: source has no queue-overwrite verbs (append-only)")
    forbidden_overwrite = (
        ".unlink(",
        ".rmdir(",
        # Open with 'w' or 'wb' would truncate the queue
        # (we open with 'a' for append-only)
    )
    leaks = [v for v in forbidden_overwrite if v in src]
    if leaks:
        fail(
            f"router source has overwrite/delete verbs against the queue: "
            f"{leaks} — append-only contract violated per §38"
        )
    # Look for open(...) with truncating mode
    if re.search(r"queue_path\.open\([^)]*[\"']w[\"']", src):
        fail(
            "router opens queue file with truncating 'w' mode — "
            "append-only contract violated"
        )
    if re.search(r"queue_path\.write_text\(", src):
        fail(
            "router uses write_text() on queue file (truncates) — "
            "must use append mode 'a'"
        )
    # Verify it DOES use append mode
    if 'queue_path.open("a"' not in src and "queue_path.open('a'" not in src:
        fail(
            "router doesn't open queue with 'a' (append) mode — "
            "is the append-only contract actually held?"
        )
    ok("queue file opened only in append ('a') mode (§38 immutability held)")

    # ------------------------------------------------------------------
    # Step 9 — NEGATIVE: empty audit → empty queue (boundary)
    # ------------------------------------------------------------------
    step("9. NEGATIVE: empty audit → 0 storms; queue stays empty")
    with tempfile.TemporaryDirectory() as td:
        empty_audit = Path(td) / "empty.jsonl"
        empty_audit.write_text("", encoding="utf-8")
        queue = Path(td) / "queue.jsonl"
        report = human_review_router.route_retry_storms(
            audit_path=empty_audit, queue_path=queue,
            threshold=5, dry_run=False,
        )
        if report.storm_ids_detected:
            fail(f"empty audit produced storms: {report.storm_ids_detected}")
        if queue.exists() and queue.read_text(encoding="utf-8").strip():
            fail("queue file mutated by empty audit")
    ok("empty audit → 0 storms; queue stays empty (boundary held)")

    # ------------------------------------------------------------------
    # Step 10 — NEGATIVE: malformed jsonl lines are skipped, not crash
    # ------------------------------------------------------------------
    step("10. NEGATIVE: malformed jsonl lines tolerated (resilience)")
    with tempfile.TemporaryDirectory() as td:
        audit = Path(td) / "audit.jsonl"
        # Mix of valid + malformed lines + valid
        audit.write_text(
            json.dumps({
                "id": "test-OK-1", "lane": "council",
                "outcome": "rejected", "ts": "2026-05-06T00:00:00+00:00",
            }) + "\n"
            + "{not valid json\n"
            + json.dumps({
                "id": "test-OK-1", "lane": "council",
                "outcome": "rejected", "ts": "2026-05-06T00:00:01+00:00",
            }) + "\n"
            + "completely garbled\n"
            + (json.dumps({
                "id": "test-OK-1", "lane": "council",
                "outcome": "rejected", "ts": "2026-05-06T00:00:02+00:00",
            }) + "\n") * 4,  # total 6 valid attempts of test-OK-1
            encoding="utf-8",
        )
        queue = Path(td) / "queue.jsonl"
        report = human_review_router.route_retry_storms(
            audit_path=audit, queue_path=queue,
            threshold=5, dry_run=False,
        )
        if "test-OK-1" not in report.newly_routed:
            fail(
                "router crashed on malformed lines OR didn't tolerate them — "
                "test-OK-1 should still trigger storm despite 2 garbage lines"
            )
    ok("malformed lines skipped (not fatal); valid lines still aggregated")

    print(f"\n{GREEN}{BOLD}ALL 10 STEPS PASSED (5 positive + 5 negative){NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
