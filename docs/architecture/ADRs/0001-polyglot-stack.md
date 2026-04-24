# ADR-0001: Polyglot stack (Go + Python + TypeScript)

**Status:** Accepted
**Date:** 2026-04-23
**Context:** See spec §2 and §21.

## Context

DocuMind has two very different workloads:

1. **Edge / control-plane / aggregation** — high concurrency, low latency,
   mostly I/O-bound: API gateway, identity, governance policy evaluation,
   FinOps aggregation, observability metric collection.
2. **ML / RAG** — CPU- and GPU-bound work that benefits from Python's
   ecosystem: document parsing (pypdf, python-docx), tokenization
   (tiktoken), embedding (Ollama client), graph construction (neo4j-driver).

A single-language stack would force us to compromise one workload.

## Decision

* **Go** for api-gateway, identity-svc, governance-svc, finops-svc, observability-svc.
* **Python** for ingestion-svc, retrieval-svc, inference-svc, evaluation-svc.
* **TypeScript** (React + Vite) for the frontend.

Services communicate over gRPC internally + REST at the edge. Events go
through Kafka with CloudEvents envelopes — transport-agnostic.

## Consequences

**Pros**

* Each service uses the right tool for its workload.
* Go services get goroutine concurrency + low GC — gateway can handle high
  QPS with little memory.
* Python services get the ML ecosystem without shoehorning.

**Cons**

* Two build toolchains, two test runners, two lint pipelines.
* Schema sharing requires Proto → codegen in both languages.
* Onboarding is higher: engineers need to read both Go and Python.

**Mitigations**

* A single `Makefile` hides both toolchains behind uniform targets (`make
  test`, `make lint`).
* `libs/py` and `libs/go` mirror each other's shape (CorrelationID
  middleware, CircuitBreaker, structured logs) so jumping between the
  languages feels consistent.
* Each service's README starts with its language + port + dependencies so
  you never wonder which side of the fence a given file lives on.
