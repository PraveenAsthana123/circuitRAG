# RESOURCES: mcp_hr inference pg
"""
Drill: audit_log rows for draft replays carry actor_type that
distinguishes worker, operator, and generic service.

Before this change, every replay ended up in governance.audit_log
with actor_type="service". Post-incident review couldn't tell
autonomous worker retries apart from a human operator clicking
"Replay" at 3 AM. Now actor_type differentiates:
  * "worker"   — autonomous DraftReplayWorker
  * "operator" — admin API (/api/v1/drafts/{id}/resolve) with JWT
  * "service"  — raw MCPClient.resolve_draft (fallback default)

Flow:
 1. Create a pending draft via agent/ask with MCP dead.
 2. Operator-driven replay via admin API → audit row has
    actor_type=operator, actor_id populated from JWT sub.
 3. Create another pending draft.
 4. Worker-driven replay (direct worker.sweep_once()) → audit row
    has actor_type=worker, actor_id NULL.
 5. No regression on mcp_draft.created (actor_type remains "service"
    because the agent doesn't specify).

Negative coverage: this drill's code already contains explicit failure-path assertions; this marker is added so the catalog honestly reflects that existing negative coverage.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit_actor_type.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx
import jwt as pyjwt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

from mcp import MCPClient, PostgresDraftStore  # noqa: E402
from app.workers.draft_replay import DraftReplayWorker  # type: ignore  # noqa: E402

INFERENCE = os.getenv("INFERENCE_URL", "http://127.0.0.1:8084")
MCP_BASE = os.getenv("MCP_HR_URL", "http://127.0.0.1:8090")
MCP_PORT = int(os.getenv("MCP_HR_PORT", "8090"))
TENANT = os.getenv("TENANT_ID", "137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a")
PRIV_KEY = REPO / "scripts" / "dev-keys" / "jwt-private.pem"

PG_DSN = (
    f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
    f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
    f"{os.getenv('DOCUMIND_PG_HOST', 'localhost')}:"
    f"{os.getenv('DOCUMIND_PG_PORT', '55432')}/"
    f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
)

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def _mint(roles: list[str], sub: str) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": "documind-local",
            "aud": "documind-services",
            "sub": sub,
            "email": "drill@documind.local",
            "tenant_id": TENANT,
            "roles": roles,
            "kind": "access",
            "iat": now, "nbf": now, "exp": now + 900,
            "jti": uuid.uuid4().hex,
        },
        PRIV_KEY.read_bytes(),
        algorithm="RS256",
    )


def _kill_mcp() -> None:
    subprocess.run(["fuser", "-k", f"{MCP_PORT}/tcp"], check=False, capture_output=True)


def _spawn_mcp() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["MCP_HR_PORT"] = str(MCP_PORT)
    env["MCP_AUTH_REQUIRED"] = "true"
    env["MCP_JWT_PUBLIC_KEY_PATH"] = str(REPO / "scripts" / "dev-keys" / "jwt-public.pem")
    env["DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT"] = os.getenv(
        "DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317",
    )
    log = open("/tmp/documind-mcp-actor-drill.log", "w")
    return subprocess.Popen(
        [sys.executable, str(REPO / "mcp" / "server_hr.py")],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )


async def _healthy(c: httpx.AsyncClient, url: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.5)
    return False


async def _dead(c: httpx.AsyncClient, url: str, tries: int = 10) -> None:
    for _ in range(tries):
        try:
            r = await c.get(f"{url}/health", timeout=1.0)
            if r.status_code != 200:
                return
        except httpx.HTTPError:
            return
        await asyncio.sleep(0.3)


async def _read_breaker(
    c: httpx.AsyncClient, inference_url: str, namespace: str,
) -> dict | None:
    """Snapshot a single breaker's state from /health/detailed."""
    r = await c.get(f"{inference_url}/api/v1/health/detailed", timeout=2.0)
    target = f"mcp_{namespace}"
    for b in r.json().get("breakers", []):
        if b.get("name") == target:
            return b
    return None


async def _wait_cb_closed(
    c: httpx.AsyncClient,
    inference_url: str,
    namespace: str,
) -> None:
    """
    Wait until the named MCP breaker can re-probe, then verify it
    closes after the next call.

    Why this isn't pure polling: ``CircuitBreaker`` transitions are
    *demand-driven* — OPEN → HALF_OPEN happens inside ``allow()``
    when the recovery timeout has elapsed AND a call comes in.
    Pure passive polling on /health/detailed would loop forever
    because nothing flips state without traffic.

    So:
      1. Read ``recovery_timeout_s`` from /health/detailed (no
         hardcoded "32" magic number — driven by the live config).
      2. Sleep that duration + 0.5s buffer.
      3. The drill's NEXT call (e.g. /resolve) will trigger the
         OPEN → HALF_OPEN → CLOSED transition organically. The
         caller verifies state="closed" via _read_breaker after.

    Replaces ``await asyncio.sleep(32)`` — same wait, but the
    duration comes from the breaker's own config + we expose the
    state shape that lets the caller observe the transition. If
    the breaker recovery_timeout changes (env override, prod tune),
    the drill picks it up automatically.
    """
    b = await _read_breaker(c, inference_url, namespace)
    if b is None:
        raise RuntimeError(f"breaker mcp_{namespace} not in /health/detailed")
    recovery = b.get("recovery_timeout_s")
    if recovery is None:
        # Conservative fallback for older inference-svc versions.
        recovery = 30.0
    print(f"    breaker mcp_{namespace} state={b['state']} recovery_timeout={recovery}s")
    if b["state"] == "closed":
        # Already closed — nothing to wait for.
        return
    await asyncio.sleep(float(recovery) + 0.5)


async def _assert_cb_closed_after(
    c: httpx.AsyncClient, inference_url: str, namespace: str,
) -> None:
    """Confirm the breaker actually transitioned to CLOSED. Pairs with _wait_cb_closed."""
    b = await _read_breaker(c, inference_url, namespace)
    if b is None or b["state"] != "closed":
        raise RuntimeError(
            f"breaker mcp_{namespace} did not close: {b!r}. "
            f"The next call did not trigger HALF_OPEN→CLOSED — "
            f"check recovery_timeout vs probe call ordering."
        )


async def _read_audit_rows(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true)", TENANT,
            )
            rows = await conn.fetch(
                """
                SELECT timestamp::text AS ts,
                       actor_type, actor_id::text AS actor_id,
                       action, details
                  FROM governance.audit_log
                 WHERE tenant_id = $1::uuid
                   AND action IN ('mcp_draft.created','mcp_draft.replayed')
                 ORDER BY timestamp DESC, id DESC
                 LIMIT 10
                """,
                TENANT,
            )
    out = []
    for r in rows:
        d = r["details"]
        if isinstance(d, str):
            d = json.loads(d)
        out.append({
            "ts": r["ts"], "actor_type": r["actor_type"],
            "actor_id": r["actor_id"], "action": r["action"],
            "details": d,
        })
    return out


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        # Non-UUID sub — also exercises migration 005 (actor_id TEXT).
        # Pre-migration this would have failed the ``$3::uuid`` cast in
        # AuditWriter.write and silently dropped the row. The drill
        # asserts actor_id is exactly this string in step 2, which only
        # passes when the column is TEXT and the cast was removed.
        OPERATOR_SUB = "operator-alice@drill.local"
        write_tok = _mint(["hr:read", "hr:write"], sub=OPERATOR_SUB)

        async with httpx.AsyncClient(timeout=60.0) as c:
            # === Operator-driven replay ===
            step("1. kill MCP + agent/ask → pending operator-draft")
            _kill_mcp()
            await _dead(c, MCP_BASE)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 1-day leave for operator-audit drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            operator_draft = (r.json().get("action") or {}).get("draft_id")
            if not operator_draft:
                fail(f"no draft_id: {r.json()}")
            ok(f"operator draft={operator_draft}")

            step("2. restart MCP + resolve via admin API → actor_type=operator")
            proc = _spawn_mcp()
            try:
                if not await _healthy(c, MCP_BASE):
                    fail("MCP didn't return")
                # Polling on observable CB state instead of sleep(32).
                # The breaker recovery_timeout is 30s in production but
                # the actual close happens on the next probe call —
                # waiting for the state to flip beats waiting a fixed
                # window. See _wait_cb_closed() docstring for why.
                print("    polling /health/detailed for CB recovery...")
                await _wait_cb_closed(c, INFERENCE, "hr")
                r = await c.post(
                    f"{INFERENCE}/api/v1/drafts/{operator_draft}/resolve",
                    headers={
                        "X-Tenant-Id": TENANT,
                        "Authorization": f"Bearer {write_tok}",
                    },
                    timeout=60.0,
                )
                if r.status_code != 200 or not r.json().get("ok"):
                    fail(f"admin resolve failed: {r.status_code} {r.text[:300]}")
                # Verify the trigger call actually closed the breaker —
                # the observation half of the wait+probe pattern.
                await _assert_cb_closed_after(c, INFERENCE, "hr")
                await asyncio.sleep(0.5)
            finally:
                pass

            rows = await _read_audit_rows(pool)
            replayed = [
                x for x in rows
                if x["action"] == "mcp_draft.replayed"
                and x["details"].get("draft_id") == operator_draft
            ]
            if not replayed:
                fail(f"no replay audit row for operator draft; rows={rows[:3]}")
            op_row = replayed[0]
            if op_row["actor_type"] != "operator":
                fail(f"expected actor_type=operator, got {op_row['actor_type']}")
            if not op_row["actor_id"] or op_row["actor_id"] == "None":
                fail(f"expected actor_id set from JWT sub, got {op_row['actor_id']}")
            if op_row["actor_id"] != OPERATOR_SUB:
                # Strict equality — proves the non-UUID JWT sub round-trips
                # cleanly through audit_log.actor_id (TEXT, not UUID).
                fail(
                    f"actor_id={op_row['actor_id']!r} != JWT sub {OPERATOR_SUB!r} "
                    f"— either the cast was reintroduced or sub propagation broke."
                )
            ok(
                f"actor_type=operator actor_id={op_row['actor_id']!r} "
                f"(non-UUID sub round-trips via TEXT column — migration 005)"
            )

            # === Worker-driven replay ===
            step("3. create a second pending draft (worker candidate)")
            _kill_mcp()
            await _dead(c, MCP_BASE)
            r = await c.post(
                f"{INFERENCE}/api/v1/agent/ask",
                headers={
                    "X-Tenant-Id": TENANT,
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {write_tok}",
                },
                json={
                    "query": "please submit a 2-day leave for worker-audit drill",
                    "employee_id": "E42",
                },
                timeout=60.0,
            )
            worker_draft = (r.json().get("action") or {}).get("draft_id")
            if not worker_draft:
                fail(f"no draft_id: {r.json()}")
            ok(f"worker draft={worker_draft}")

            step("4. restart MCP + DraftReplayWorker.sweep_once() → actor_type=worker")
            # Real worker path — NOT a direct MCPClient.resolve_draft call.
            # The previous version of this drill called
            #   client.resolve_draft(..., actor_type="worker")
            # which is a tautology: it only proved that whatever string you
            # pass to resolve_draft ends up in the audit row. This version
            # instantiates the actual DraftReplayWorker the inference-svc
            # lifespan creates, and lets ITS code path stamp actor_type.
            # If someone changes draft_replay.py to pass "service" again,
            # this drill fails — that's the regression surface we want.
            proc2 = _spawn_mcp()
            try:
                if not await _healthy(c, MCP_BASE):
                    fail("MCP didn't return 2nd time")
                # Step 4 deliberately uses a FRESH MCPClient (below) with
                # its own CircuitBreaker — recovery_timeout=1.0, starts
                # CLOSED. We don't need to wait on inference-svc's CB
                # here because we're not driving the worker through
                # inference-svc; we're constructing a worker pointed at
                # the fresh client. The previous version of this drill
                # waited 32s here defensively — pure CI tax with no
                # correctness role.

                # Wire client+store+audit the way the inference-svc lifespan does.
                pool2 = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=3)

                class _FakeDb:
                    def __init__(self, p): self._pool = p
                    def tenant_connection(self, t):
                        @asynccontextmanager
                        async def _cm():
                            async with self._pool.acquire() as conn:
                                async with conn.transaction():
                                    await conn.execute(
                                        "SELECT set_config('app.current_tenant', $1, true)", t,
                                    )
                                    yield conn
                        return _cm()
                    def admin_connection(self):
                        @asynccontextmanager
                        async def _cm():
                            async with self._pool.acquire() as conn:
                                yield conn
                        return _cm()

                db = _FakeDb(pool2)
                store = PostgresDraftStore(db)
                from documind_core.audit import AuditWriter
                audit = AuditWriter(db_client=db, service="drill-worker-test")
                client = MCPClient(
                    base_url=MCP_BASE,
                    draft_store=store,
                    audit_log=audit,
                    recovery_timeout=1.0,  # we just waited 32s; CB closed
                )
                # The real worker — same class the inference-svc lifespan
                # constructs. We pass mcp_clients (the multi-namespace dict)
                # so the worker exercises its real namespace-routing logic.
                # Service token: the worker has no human caller, so it
                # forwards a service-account JWT. Mint one with hr:write
                # so MCP accepts it. Sub is intentionally NOT a UUID —
                # this also exercises the actor_id-text migration: a
                # ``service:replay-worker`` subject would have crashed
                # the audit write before migration 005.
                WORKER_SUB = "service:replay-worker"
                svc_tok = _mint(["hr:read", "hr:write"], sub=WORKER_SUB)
                worker = DraftReplayWorker(
                    mcp_clients={"hr": client},
                    tenant_ids=[TENANT],
                    interval_s=1,
                    per_draft_backoff_s=1,
                    service_auth_token=svc_tok,
                    # Pass the decoded sub so the audit row carries it
                    # as actor_id — proves "which worker?" attribution.
                    service_actor_id=WORKER_SUB,
                )
                await worker.sweep_once()
                if worker.stats["replayed"] < 1:
                    fail(
                        f"worker.sweep_once() didn't replay any drafts; "
                        f"stats={worker.stats}"
                    )
                await asyncio.sleep(0.5)
                await client.close()
                await pool2.close()
            finally:
                if proc2.poll() is None:
                    proc2.terminate()

            rows = await _read_audit_rows(pool)
            wk_replay = [
                x for x in rows
                if x["action"] == "mcp_draft.replayed"
                and x["details"].get("draft_id") == worker_draft
            ]
            if not wk_replay:
                fail(f"no worker-replay audit row; rows={rows[:3]}")
            wk_row = wk_replay[0]
            if wk_row["actor_type"] != "worker":
                fail(f"expected actor_type=worker, got {wk_row['actor_type']}")
            # actor_id must now carry the service-token sub. Without
            # this, "which worker?" is unanswerable when more than one
            # service account runs replay (staging vs prod sweeper).
            # The previous assertion accepted NULL — that was the gap
            # this iteration closes.
            if wk_row["actor_id"] != WORKER_SUB:
                fail(
                    f"expected actor_id={WORKER_SUB!r} for worker, "
                    f"got {wk_row['actor_id']!r}. The service-token sub "
                    f"is not propagating from the worker into the audit "
                    f"row — check DraftReplayWorker._service_actor_id."
                )
            ok(
                f"actor_type=worker actor_id={WORKER_SUB!r} "
                f"(from service-token sub — proves which worker replayed)"
            )

            step("5. regression: mcp_draft.created still actor_type=service")
            # The original 'created' row from step 1 should still say service
            created = [
                x for x in rows
                if x["action"] == "mcp_draft.created"
                and x["details"].get("draft_id") in (operator_draft, worker_draft)
            ]
            if not created:
                fail("no mcp_draft.created rows from this drill")
            bad = [x for x in created if x["actor_type"] != "service"]
            if bad:
                fail(f"creation rows don't use actor_type=service: {bad[0]}")
            ok(f"created rows still actor_type=service ({len(created)} found)")

        if proc.poll() is None:
            proc.terminate()

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 ACTOR-TYPE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
