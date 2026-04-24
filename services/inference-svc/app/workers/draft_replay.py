"""
Draft replay worker — periodically resolves pending MCP drafts.

Design
------
This is the autonomous counterpart to the admin API. Operators can still
hit ``POST /api/v1/drafts/{id}/resolve`` manually; the worker just
automates the common case ("MCP was down, it's back, go through the
backlog and try again").

The worker runs as an ``asyncio.Task`` attached to the inference-svc
lifespan. Every ``interval_s`` seconds it walks the configured tenant
list, asks the :class:`MCPClient` for that tenant's pending drafts,
and replays one at a time. If the first replay comes back ``degraded``
(MCP still unreachable), the worker bails out for this cycle — no
point hammering further rows when the downstream is visibly down.

Per-draft backoff
~~~~~~~~~~~~~~~~~
A small in-memory ``{draft_id: last_attempt_monotonic}`` map prevents
the worker from retrying the same draft every tick. If MCP is flapping,
a draft that failed 5s ago would otherwise be tried on every cycle —
``per_draft_backoff_s`` enforces a minimum gap.

Why not push this into the client or the store?
  * The client should stay synchronous-on-request — adding a scheduler
    there would couple tool calls to retry state.
  * The store is passive.
  * The worker is the *policy* layer; client + store are mechanism.

Tenant enumeration
~~~~~~~~~~~~~~~~~~
We require the tenant list via config rather than discovering it
(``documind_app`` is NOBYPASSRLS; listing tenants means crossing the
isolation boundary, which is a governance decision). In production a
separate "tenants to sweep" feed — identity-svc, a feature flag — fills
it in. Today, a comma-separated env var is enough.

Env config (read by the lifespan, not by this module):
  DOCUMIND_REPLAY_WORKER_ENABLED  -- "true" to start the loop
  DOCUMIND_REPLAY_WORKER_TENANTS  -- CSV of UUIDs
  DOCUMIND_REPLAY_WORKER_INTERVAL_S (default 20)
  DOCUMIND_REPLAY_WORKER_BACKOFF_S  (default 60)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger(__name__)


class DraftReplayWorker:
    def __init__(
        self,
        *,
        mcp_client: Any,
        tenant_ids: list[str],
        interval_s: int = 20,
        per_draft_backoff_s: int = 60,
    ) -> None:
        self._mcp = mcp_client
        self._tenants = list(tenant_ids)
        self._interval = max(1, interval_s)
        self._backoff = max(1, per_draft_backoff_s)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_attempt: dict[str, float] = {}
        # Observable counters — useful in tests + metrics later.
        self.stats = {
            "cycles": 0,
            "replayed": 0,
            "skipped_backoff": 0,
            "degraded_bailouts": 0,
            "errors": 0,
        }

    async def start(self) -> None:
        if self._task is not None:
            return
        log.info(
            "draft_replay_worker_start tenants=%d interval=%ds backoff=%ds",
            len(self._tenants), self._interval, self._backoff,
        )
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="draft_replay_worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=self._interval + 5)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        log.info("draft_replay_worker_stopped stats=%s", self.stats)

    async def sweep_once(self) -> None:
        """Run a single cycle — exposed for tests that want deterministic ticks."""
        await self._sweep()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sweep()
            except Exception as exc:  # noqa: BLE001
                self.stats["errors"] += 1
                log.error("draft_replay_worker_cycle_failed err=%s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass  # interval elapsed → next cycle

    async def _sweep(self) -> None:
        self.stats["cycles"] += 1
        now = time.monotonic()
        for tenant in self._tenants:
            try:
                drafts = await self._mcp.list_pending_drafts(tenant)
            except Exception as exc:  # noqa: BLE001
                self.stats["errors"] += 1
                log.error("draft_replay_list_failed tenant=%s err=%s", tenant, exc)
                continue
            if not drafts:
                continue
            log.info(
                "draft_replay_sweep tenant=%s pending=%d", tenant, len(drafts),
            )
            for draft in drafts:
                last = self._last_attempt.get(draft.draft_id, 0.0)
                if now - last < self._backoff:
                    self.stats["skipped_backoff"] += 1
                    continue
                self._last_attempt[draft.draft_id] = now
                try:
                    result = await self._mcp.resolve_draft(
                        draft.draft_id, tenant_id=tenant,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.stats["errors"] += 1
                    log.error(
                        "draft_replay_call_failed draft_id=%s err=%s",
                        draft.draft_id, exc,
                    )
                    continue
                if result.ok:
                    self.stats["replayed"] += 1
                    ticket = (result.data or {}).get("ticket_id")
                    log.info(
                        "draft_replayed_by_worker draft_id=%s tenant=%s ticket=%s",
                        draft.draft_id, tenant, ticket,
                    )
                elif result.degraded:
                    # MCP still down — bail for this cycle; the loop sleeps
                    # and the CB eventually reopens the happy path.
                    self.stats["degraded_bailouts"] += 1
                    log.info(
                        "draft_replay_mcp_still_down draft_id=%s — skipping rest of cycle",
                        draft.draft_id,
                    )
                    return
                else:
                    log.warning(
                        "draft_replay_failed draft_id=%s err=%s",
                        draft.draft_id, result.error,
                    )
