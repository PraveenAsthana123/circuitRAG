# RESOURCES: readonly
"""
Drill: run_drills.py scheduler honors read/write resource modes.

Not a drill of the system — a drill of the DRILL RUNNER itself.
Uses the internal APIs directly so we can assert on timing and
ordering without shelling out.

Flow:
 1. Three drills: A(read r1), B(read r1), C(write r1).
    Expect: A and B start together; C waits; after A+B release,
    C gets exclusive.
 2. Two drills: D(write r2), E(write r2).
    Expect: strict serialisation — total time >= 2 * per-drill.
 3. Empty-resource drill runs alongside anything.

Approach: plug a fake "run" into _run_one via a spy that records
start/end timestamps; don't actually run drill subprocesses.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_runner_scheduler.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

# Import the runner's internals directly
import run_drills as runner  # type: ignore  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


async def _fake_drill(
    table: runner._ResourceTable,  # noqa: SLF001
    name: str,
    resources: frozenset[tuple[str, str]],
    hold_s: float,
    log: list[tuple[float, str, str]],
) -> None:
    """Acquire, hold, release — record timestamps."""
    await table.acquire(resources)
    log.append((time.monotonic(), "start", name))
    await asyncio.sleep(hold_s)
    log.append((time.monotonic(), "end", name))
    await table.release(resources)


async def main() -> None:
    step("1. two readers share a resource; writer waits")
    table = runner._ResourceTable()
    log: list[tuple[float, str, str]] = []
    t0 = time.monotonic()
    await asyncio.gather(
        _fake_drill(table, "A-read", frozenset({("r1", "read")}), 0.3, log),
        _fake_drill(table, "B-read", frozenset({("r1", "read")}), 0.3, log),
        _fake_drill(table, "C-write", frozenset({("r1", "write")}), 0.1, log),
    )
    t1 = time.monotonic()
    # Extract start timestamps per drill
    starts = {n: ts for ts, ev, n in log if ev == "start"}
    ends = {n: ts for ts, ev, n in log if ev == "end"}
    # A and B should start within 10ms of each other
    if abs(starts["A-read"] - starts["B-read"]) > 0.05:
        fail(
            f"readers didn't start together: A={starts['A-read'] - t0:.3f}s "
            f"B={starts['B-read'] - t0:.3f}s"
        )
    # C must start AFTER both A and B have ended
    if starts["C-write"] < max(ends["A-read"], ends["B-read"]):
        fail(
            f"writer started before readers finished — "
            f"C-start={starts['C-write'] - t0:.3f}s "
            f"max(A-end,B-end)={max(ends['A-read'], ends['B-read']) - t0:.3f}s"
        )
    # Total wall ~= 0.3 (A+B in parallel) + 0.1 (C after)
    total = t1 - t0
    if total < 0.35 or total > 0.7:
        fail(f"total time suspicious: {total:.2f}s (expected ~0.4s)")
    ok(
        f"readers started within "
        f"{abs(starts['A-read'] - starts['B-read']) * 1000:.0f}ms; "
        f"writer waited; total {total:.2f}s"
    )

    step("2. two writers on same resource serialise")
    table = runner._ResourceTable()
    log = []
    t0 = time.monotonic()
    await asyncio.gather(
        _fake_drill(table, "D-write", frozenset({("r2", "write")}), 0.2, log),
        _fake_drill(table, "E-write", frozenset({("r2", "write")}), 0.2, log),
    )
    t1 = time.monotonic()
    total = t1 - t0
    if total < 0.38:
        fail(f"writers overlapped: total={total:.2f}s (expected >= 0.4s)")
    # Starts must be at least one hold apart
    starts = {n: ts for ts, ev, n in log if ev == "start"}
    gap = abs(starts["D-write"] - starts["E-write"])
    if gap < 0.18:
        fail(f"writer starts too close: {gap:.3f}s (expected >= 0.2s)")
    ok(f"writers serialised, gap={gap * 1000:.0f}ms, total={total:.2f}s")

    step("3. empty-resource drill never blocks")
    table = runner._ResourceTable()
    log = []
    t0 = time.monotonic()
    # A writer on r3 holds 0.3s; an empty-resource drill should finish instantly.
    async def _measure_empty():
        emp_t0 = time.monotonic()
        await _fake_drill(table, "empty", frozenset(), 0.01, log)
        return time.monotonic() - emp_t0

    fut = asyncio.create_task(_fake_drill(
        table, "writer", frozenset({("r3", "write")}), 0.3, log,
    ))
    # Tiny delay to let the writer acquire first
    await asyncio.sleep(0.02)
    empty_elapsed = await _measure_empty()
    await fut
    if empty_elapsed > 0.05:
        fail(
            f"empty-resource drill was blocked: {empty_elapsed:.3f}s "
            f"(expected ~0.01s)"
        )
    ok(f"empty-resource drill finished in {empty_elapsed * 1000:.0f}ms (not blocked)")

    step("4. tag parser honors :read / :write modifiers")
    # DEFAULT untagged → {('mcp_hr','write'),('inference','write'),('pg','write')}
    d = runner._parse_resource_tokens(["mcp_hr", "inference:read", "pg:write"])
    if ("mcp_hr", "write") not in d:
        fail(f"bare token should default write: {d}")
    if ("inference", "read") not in d:
        fail(f"':read' not parsed: {d}")
    if ("pg", "write") not in d:
        fail(f"':write' not parsed: {d}")
    # Invalid mode falls back to write
    d2 = runner._parse_resource_tokens(["foo:bogus"])
    if ("foo", "write") not in d2:
        fail(f"unknown mode should fall back to write: {d2}")
    ok(f"parser: {sorted(d)}")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 SCHEDULER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
