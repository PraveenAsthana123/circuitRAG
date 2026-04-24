# ADR-0002: Saga pattern over two-phase commit for ingestion

**Status:** Accepted
**Date:** 2026-04-23
**Context:** Spec §18, §19.

## Context

The ingestion pipeline writes to 4 stores in sequence: PostgreSQL (chunk
rows), MinIO (raw blob), Qdrant (vectors), Neo4j (graph). None of these
participate in a common transaction manager. If step 3 fails, we need to
clean up steps 1 and 2.

Options considered:

1. **Two-phase commit (XA)** — requires an XA coordinator + all participants
   supporting XA. Postgres supports it; Qdrant, Neo4j, MinIO don't.
   Dead end.
2. **Saga (orchestrator)** — ingestion-svc explicitly runs steps + their
   compensations. State persisted in `ingestion.sagas`.
3. **Saga (choreography)** — each service reacts to events. More scalable
   but harder to reason about for a tight pipeline.

## Decision

Orchestrator saga. Ingestion-svc drives the sequence. Each step has an
idempotent compensating action. Saga state is persisted, so a crash
mid-flight can be recovered.

## Consequences

**Pros**

* One file (`app/saga/document_saga.py`) describes the whole pipeline —
  easy to reason about.
* Compensations are testable in isolation.
* Persisted state enables crash recovery.

**Cons**

* No atomic guarantee: between step N succeeding and step N+1 failing +
  compensating, a concurrent reader might observe the partial state.
* We work around this by promoting to the `ACTIVE` state only on the last
  step — retrieval-svc filters by state, so only ACTIVE docs are visible.

**Invariants**

* Every compensation is idempotent (running twice is safe).
* Saga state transitions are monotonic: running → {completed, failed, compensated}.
* A failed compensation raises SEV2 — operators must resolve manually.
