"""Idempotency-key helpers for POST /api/v1/agentic/tasks (Phase C2).

Two pure functions + an in-memory cache adapter. The Postgres-backed
store (orchestration.idempotency_keys) is consulted via a small
abstraction so the same code can run in dev (in-memory) and prod (DB).

Contract per §6.3:
  - Same (tenant_id, key) + same body_hash → cached task_id (201).
  - Same (tenant_id, key) + different body_hash → 409 Conflict.
  - No key → behaviour unchanged (backward compat per §28).

The endpoint (app/main.py) is responsible for hashing the request body
and passing the result here; this module is transport-agnostic.

Drill: mcp/tests/drill_idempotency.py
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol


def hash_body(body: dict[str, Any]) -> str:
    """Stable SHA-256 of the request body in canonical JSON form.

    Sorting keys + separators kills field-order non-determinism: the
    same logical payload always hashes to the same string. Critical
    because our 'same body' check is byte-exact on this hash.
    """
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotencyRecord:
    tenant_id: str
    key: str
    task_id: str
    body_hash: str


class IdempotencyConflict(ValueError):
    """Same (tenant_id, key) seen before with a DIFFERENT body_hash.

    Caller must return HTTP 409 to the client — silently overwriting
    would corrupt the request-response invariant.
    """


class IdempotencyStore(Protocol):
    async def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None: ...
    async def save(self, record: IdempotencyRecord) -> None: ...


class InMemoryIdempotencyStore:
    """Process-local store for dev / tests. Lost on restart — fine for
    a 24h-TTL idempotency window in single-instance deployments.
    Production multi-instance must use the Postgres-backed store."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        return self._records.get((tenant_id, key))

    async def save(self, record: IdempotencyRecord) -> None:
        self._records[(record.tenant_id, record.key)] = record


async def lookup_or_reserve(
    *,
    store: IdempotencyStore,
    tenant_id: str,
    key: str,
    body_hash: str,
) -> IdempotencyRecord | None:
    """Return existing record IF same body_hash. None means 'go ahead and
    create the task; then call save_record() to register the key'.

    Raises IdempotencyConflict on (tenant_id, key) match with different
    body_hash — caller must surface as 409.

    Why not save here too: the caller doesn't have task_id yet. Pattern
    is: lookup → create task → save_record(task_id).
    """
    existing = await store.get(tenant_id, key)
    if existing is None:
        return None
    if existing.body_hash != body_hash:
        raise IdempotencyConflict(
            f"Idempotency-Key {key!r} previously used with different body "
            f"(hash {existing.body_hash[:8]}... vs {body_hash[:8]}...). "
            "Use a fresh key for a new request."
        )
    return existing


async def save_record(
    *,
    store: IdempotencyStore,
    tenant_id: str,
    key: str,
    task_id: str,
    body_hash: str,
) -> None:
    """Register the (key, task_id, body_hash) tuple after successful
    task creation. Idempotent itself: re-saving the same record is a
    no-op via the store's natural upsert semantics."""
    await store.save(IdempotencyRecord(
        tenant_id=tenant_id, key=key, task_id=task_id, body_hash=body_hash,
    ))
