# Phase 3 — Circuit Breaker Scenarios

**Status:** Stub. Primary catalog at [/tools/circuit-breakers-list](../../services/frontend/app/tools/circuit-breakers-list/page.tsx).

## Breakers in the codebase

| Breaker | Guards | Code |
| --- | --- | --- |
| Generic CB | any external call | `libs/py/documind_core/circuit_breaker.py` |
| Retrieval CB | Qdrant + Neo4j | `libs/py/documind_core/breakers.py` |
| Token CB | per-tenant token spend | `libs/py/documind_core/breakers.py` |
| Agent-Loop CB | agent recursion + wall-clock | `libs/py/documind_core/breakers.py` |
| Observability CB (inverted) | OTel + Prom push-gateway | `libs/py/documind_core/breakers.py` |
| Citation-Deadline Signal | stream-level — must emit citation by token N | `libs/py/documind_core/breakers.py` |
| Forbidden-Pattern Signal | stream-level — regex guardrails | `libs/py/documind_core/breakers.py` |
| Cognitive CB | stream-level — repetition / drift / rules | `libs/py/documind_core/ccb.py` |

## Phase-3 exit criteria

| Criterion | Verification |
| --- | --- |
| CB wraps every external call site | `grep -r 'httpx.AsyncClient\|asyncpg.connect\|qdrant_client\|aiokafka' services/ | wc -l` should match CB-wrapped callers |
| Timeout composed with CB | every call site has explicit `timeout=` |
| Retry composed with backoff | `@retry(max_attempts=2, backoff=exponential)` |
| Fallback branch explicit | every CB call has a documented `on_open` handler |
| Metrics per breaker | `documind_circuit_breaker_state{name="..."}` — one series per breaker |
| Thresholds config-driven | from env / ConfigMap, not hard-coded |

## Concrete next actions

- [ ] Write `@with_resilience(name, timeout, retries, fallback)` decorator in `libs/py/documind_core/`.
- [ ] Replace every raw external call with a decorated caller.
- [ ] Config-driven thresholds via `DOCUMIND_CB_<NAME>_THRESHOLD` env.
- [ ] Grafana dashboard JSON in `infra/grafana/dashboards/circuit-breakers.json`.
