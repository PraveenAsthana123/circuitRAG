# RESOURCES: pg
"""
Drill: DraftReplayWorker._sweep emits a single OTel span per cycle
with correlation_id + tenant_count attributes.

Catalog gap (cited 2× — AIOps-and-OpenTelemetry §13 + rag-data-
layers §15): worker logs carried `correlation_id` per draft but
the *sweep itself* had no span. Jaeger search by sweep was
impossible — operators could see individual draft replay calls
but couldn't group them by the sweep that initiated them.

Negative-assertion §43-style:
 1. One sweep → exactly one ``draft_replay.sweep`` span. NEGATIVE:
    must NOT emit per-tenant or per-draft sweep spans (those
    belong on the resolve_draft path, not the worker).
 2. Span carries documind.correlation_id (UUID-shaped string).
    NEGATIVE: missing/empty correlation_id would break the
    log↔trace cross-join.
 3. Span carries worker.tenant_count = len(tenant_ids). NEGATIVE:
    a future regression to "sum of pending drafts" or any other
    derivation would silently drift dashboards.
 4. Span carries worker.kind = "draft_replay". NEGATIVE: a future
    worker variant (e.g. ingestion-replay) must emit a different
    kind so dashboards can split them.
 5. Two sweeps → two distinct spans with different correlation_ids.
    NEGATIVE: a single global correlation_id would defeat the
    "group by sweep cycle" Jaeger query.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_worker_sweep_span.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "inference-svc"))

# Install in-memory span exporter BEFORE importing the worker so the
# tracer the worker captures is the one wired to our exporter.
from opentelemetry import trace as _otel_trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

_provider = TracerProvider()
_exporter = InMemorySpanExporter()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
_otel_trace.set_tracer_provider(_provider)

# Now import the worker — its module-level _TRACER picks up our provider.
from app.workers.draft_replay import DraftReplayWorker  # type: ignore  # noqa: E402

TENANT = os.getenv("TENANT_ID") or str(uuid.uuid4())
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


class _FakeDb:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def tenant_connection(self, t: str):
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


def _sweep_spans() -> list[Any]:
    """Filter to draft_replay.sweep spans only — the test exporter
    captures every span the SDK emits, including any from imports."""
    return [s for s in _exporter.get_finished_spans() if s.name == "draft_replay.sweep"]


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=PG_DSN, min_size=1, max_size=2)
    try:
        # Need a real PG-backed reader so list_pending_drafts works.
        from mcp import MCPClient, PostgresDraftStore  # noqa: E402

        store = PostgresDraftStore(_FakeDb(pool))
        # Empty queue is fine — the span happens regardless of
        # whether any drafts are pending. We avoid touching MCP at all.
        client = MCPClient(
            base_url="http://127.0.0.1:0",
            draft_store=store,
            recovery_timeout=1.0,
        )

        TENANT_LIST = [TENANT, str(uuid.uuid4())]  # 2 tenants
        worker = DraftReplayWorker(
            mcp_clients={"hr": client},
            tenant_ids=TENANT_LIST,
            interval_s=1,
            per_draft_backoff_s=999,
        )

        step("1. One sweep → exactly one draft_replay.sweep span")
        _exporter.clear()
        await worker.sweep_once()
        spans = _sweep_spans()
        if len(spans) != 1:
            fail(f"expected 1 sweep span, got {len(spans)}: {[s.name for s in spans]}")
        ok(f"1 span emitted (name={spans[0].name})")

        step("2. Span carries documind.correlation_id (UUID-shaped)")
        sp = spans[0]
        cid = sp.attributes.get("documind.correlation_id")
        if not isinstance(cid, str) or len(cid) < 16:
            fail(f"correlation_id missing or malformed: {cid!r}")
        # Loose check — accept hex form (no dashes) since worker uses uuid4().hex.
        try:
            int(cid, 16)
        except ValueError:
            fail(f"correlation_id is not hex: {cid!r}")
        ok(f"documind.correlation_id={cid[:12]}…")

        step("3. Span carries worker.tenant_count = len(tenant_ids)")
        tc = sp.attributes.get("worker.tenant_count")
        if tc != len(TENANT_LIST):
            fail(
                f"tenant_count={tc!r} but tenant_ids has {len(TENANT_LIST)} "
                f"entries — drift between worker config and span attribute"
            )
        ok(f"worker.tenant_count={tc} matches len(tenant_ids)")

        step("4. Span carries worker.kind = \"draft_replay\"")
        kind = sp.attributes.get("worker.kind")
        if kind != "draft_replay":
            fail(
                f"worker.kind={kind!r}, expected 'draft_replay'. A future "
                f"worker variant (e.g. ingestion-replay) MUST emit a "
                f"different kind so dashboards can split them."
            )
        ok(f"worker.kind={kind!r}")

        step("5. Two sweeps → two spans with distinct correlation_ids")
        _exporter.clear()
        await worker.sweep_once()
        # Brief gap so the second sweep has a chance to start a new span
        # AFTER the first finished — InMemorySpanExporter only captures
        # finished spans.
        await worker.sweep_once()
        spans = _sweep_spans()
        if len(spans) != 2:
            fail(
                f"expected 2 sweep spans across 2 sweep_once() calls, "
                f"got {len(spans)}"
            )
        cids = {s.attributes.get("documind.correlation_id") for s in spans}
        if len(cids) != 2:
            fail(
                f"two sweeps emitted the SAME correlation_id "
                f"({cids!r}) — a single global cid would defeat the "
                f"'group by sweep cycle' Jaeger query"
            )
        ok(f"2 distinct correlation_ids emitted across 2 sweeps")

        await client.close()

    finally:
        await pool.close()

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL 5 SWEEP-SPAN STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")


if __name__ == "__main__":
    asyncio.run(main())
