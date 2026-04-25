# RESOURCES: pg
"""
Drill: AuditWriter.write supports per-call fail_open vs fail_closed.

The reviewer flagged audit fail-open as the right default but said
governance-critical actions need a hard guarantee. We added a single
parameter — ``fail_closed: bool = False`` — instead of a policy
table. Caller decides per call.

Two assertions proven here, both negative:
  fail_closed=False → exception is swallowed, counter increments,
                      caller's flow continues. (Default. The right
                      posture for retries / draft creation.)
  fail_closed=True  → exception escapes as DataError(500), caller
                      visibly fails. The right posture for operator-
                      driven admin actions.

Setup
  We construct an AuditWriter against a "failing DbClient" — its
  tenant_connection raises a controlled error every time. That gives
  us deterministic audit-write failure regardless of the real DB
  state, so the drill is fast, hermetic, and doesn't pollute
  governance.audit_log.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit_fail_closed.py
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from documind_core.audit import AuditWriter, _audit_write_failures  # noqa: E402
from documind_core.exceptions import DataError  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


class _BoomError(RuntimeError):
    """Sentinel exception so we can verify the writer classified + relayed correctly."""


class _FailingDbClient:
    """
    DbClient shape that always raises on connection acquire. Lets us
    deterministically exercise the audit-write failure path without
    actually touching Postgres.
    """

    def tenant_connection(self, tenant_id: str):
        @asynccontextmanager
        async def _cm():
            raise _BoomError(f"injected failure for tenant {tenant_id}")
            yield  # pragma: no cover  (unreachable, satisfies asynccontextmanager)
        return _cm()

    def admin_connection(self):
        @asynccontextmanager
        async def _cm():
            raise _BoomError("injected admin failure")
            yield  # pragma: no cover
        return _cm()


def _failure_count_for(action: str, error_type: str) -> float:
    """Read the Prometheus counter value for a (action, error_type) pair."""
    if _audit_write_failures is None:
        return 0.0
    # ``labels(...)._value.get()`` works on prometheus_client.Counter.
    sample = _audit_write_failures.labels(action=action, error_type=error_type)
    return sample._value.get()  # noqa: SLF001 — internal but stable across versions


async def main() -> None:
    db = _FailingDbClient()
    writer = AuditWriter(db_client=db, service="drill_fail_closed")

    step("1. fail_closed=False (default) → swallow, counter increments, caller continues")
    before = _failure_count_for("drill.fc_false", "_Boom")
    # No exception expected. The writer's exception handler runs,
    # logs, increments the counter, and returns normally.
    await writer.write(
        tenant_id="137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
        action="drill.fc_false",
        actor_type="service",
        details={"drill": "fail_closed_default"},
        correlation_id="00000000-0000-0000-0000-000000000001",
    )
    after = _failure_count_for("drill.fc_false", "_Boom")
    if after - before != 1.0:
        fail(
            f"counter did not increment: before={before} after={after}. "
            f"Expected exactly 1 increment for the drop event."
        )
    ok(f"swallowed; counter {before} → {after} (Δ=+1)")

    step("2. fail_closed=True → DataError raised, counter still increments")
    before = _failure_count_for("drill.fc_true", "_Boom")
    raised: BaseException | None = None
    try:
        await writer.write(
            tenant_id="137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
            action="drill.fc_true",
            actor_type="operator",
            actor_id="alice@drill",
            details={"drill": "fail_closed_true"},
            correlation_id="00000000-0000-0000-0000-000000000002",
            fail_closed=True,
        )
    except DataError as exc:
        raised = exc
    if raised is None:
        fail("fail_closed=True swallowed the failure — caller has no signal!")
    if raised.__cause__ is None or not isinstance(raised.__cause__, _BoomError):
        fail(
            f"DataError didn't preserve the original cause: "
            f"__cause__={raised.__cause__!r}. Lost forensic chain."
        )
    after = _failure_count_for("drill.fc_true", "_Boom")
    if after - before != 1.0:
        fail(
            f"counter didn't increment in fail_closed mode either: "
            f"before={before} after={after}. Both modes MUST graph."
        )
    ok(
        f"DataError raised with __cause__ preserved; counter {before} → {after} (Δ=+1)"
    )

    step("3. Caller can override fail_closed per call (no instance state)")
    # Same writer, two calls back to back, different postures. Verifies
    # the parameter is purely per-call — no hidden state on the writer.
    await writer.write(
        tenant_id="137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
        action="drill.fc_mixed",
        actor_type="service",
        details={},
    )  # fail_open
    raised2: BaseException | None = None
    try:
        await writer.write(
            tenant_id="137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
            action="drill.fc_mixed",
            actor_type="operator",
            details={},
            fail_closed=True,
        )  # fail_closed
    except DataError as exc:
        raised2 = exc
    if raised2 is None:
        fail("second call (fail_closed=True) was swallowed — parameter not honored per-call")
    ok("same writer, two postures back-to-back — parameter is per-call only")

    step("4. fail_closed=False is the DEFAULT (no breaking-change for existing callers)")
    # Explicit assertion: omitting the parameter is the safe default.
    # If someone flips this default in the future, they have to fix
    # this drill — which is the regression surface.
    raised3: BaseException | None = None
    try:
        await writer.write(
            tenant_id="137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a",
            action="drill.fc_default",
            actor_type="service",
            details={},
        )
    except Exception as exc:  # noqa: BLE001
        raised3 = exc
    if raised3 is not None:
        fail(
            f"OMITTING fail_closed raised {type(raised3).__name__}! "
            f"Default MUST be fail_open or every existing caller breaks."
        )
    ok("default behaviour unchanged — existing callers safe")

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 4 AUDIT-FAIL-CLOSED STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
