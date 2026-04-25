# Drill Testing Policy — DocuMind / circuitRAG

**Status:** Mandatory for every feature commit.
**Scope:** Project-level for this repository. Apply this policy together
with any user- or tool-level local instructions active in your
environment.

> **The rule:** every feature commit ships with a drill. Every commit
> that closes a bug ships with a drill that would have caught the bug
> if it had existed first. No exceptions.

---

## What a drill is

A **drill** is a standalone Python script under `mcp/tests/drill_*.py`
that:

1. Exercises a real running stack (docker-compose services + Python
   processes), not mocks.
2. Prints step-by-step progress with green `✓` / red `✗` markers.
3. Terminates with one of two deterministic banners:
   - `ALL N <CATEGORY> STEPS PASSED` (green) — exits 0
   - `✗ <failure message>` (red) — exits 1
4. Is discoverable by name matching `drill_<feature>_<aspect>.py`.
5. Declares its shared resources at the top of the file with a single
   comment — see "Resource tags" below.

## Why drills, not pytest

pytest is great for unit tests of in-process logic. Drills cover the
*compositions* — "the agent, the retrieval service, the MCP server,
and Postgres all correctly behave when MCP goes down mid-call and
then recovers." That's expensive to set up in pytest and cheap in a
drill: the drill talks to real services and asserts on real state.

Use pytest for: pure-function logic, schema validation, unit-level
correctness. Use drills for: cross-service behavior, chaos, state
machines, circuit breakers, HITL flows, multi-namespace routing.

## Resource tags

Every drill MAY declare a set of shared resources it touches. Parser:
a single comment line anywhere in the file of the form::

    # RESOURCES: mcp_hr inference pg

Valid resources (extend as needed):

| Token | Meaning |
| --- | --- |
| `mcp_hr` | MCP HR server on port 8090 — kills/restarts/mutates state |
| `mcp_itsm` | MCP ITSM server on port 8091 |
| `mcp_drills` | MCP drill runner on port 8092 |
| `inference` | inference-svc process — may restart |
| `retrieval` | retrieval-svc process |
| `ingestion` | ingestion-svc process |
| `pg` | Postgres mutations not confined to cleanup |
| `kafka` | Kafka brokers |
| `jaeger` | Jaeger collector (traces emitted will be observed) |
| `redis` | Redis — rate limiter + cache + idempotency |
| `readonly` / `none` | Pure reads; parallel with anything |

**Missing tag** defaults to `{mcp_hr, inference, pg}` — the safe
"touches everything" assumption, which serialises the drill against
every other drill. Explicit tags enable parallelism.

## Running drills

### One at a time (dev iteration):

```bash
PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_<name>.py
```

### Batch (CI, release gate):

```bash
scripts/run_drills.py --parallel 4
```

Resource-aware scheduler: drills that touch disjoint resources run
concurrently up to `--parallel N`. Drills that share a resource
serialise automatically. Exit code 0 iff every drill passed.

### Subset (ad-hoc smoke):

```bash
scripts/run_drills.py --only trace audit --parallel 2
```

`--only` is substring-filter on drill name. Multiple substrings
combine with OR.

### From an MCP agent (programmatic):

The `mcp-server-drills` server (port 8092) exposes the runner as two
tools:

- `drill.list` → `{"drills": [{name, resources}, ...]}`
- `drill.run` → `{ok, exit_code, steps_passed, duration_s, tail}`

Example:

```bash
curl -X POST http://127.0.0.1:8092/tools/call \
  -H 'Content-Type: application/json' \
  -d '{"name":"drill.run","arguments":{"name":"drill_tool_catalog_ttl"}}'
```

Scopes: `drill:read` for list, `drill:run` for run. When
`MCP_AUTH_REQUIRED=true` the server enforces JWT + roles like any
other MCP server.

## Commit discipline

Every feature commit includes:

1. The feature code.
2. A drill proving the feature works.
3. A doc under `docs/DEMO-*.md` summarising the feature + linking the
   drill output.
4. A commit message with:
   - Rationale (why the feature exists).
   - "Negative assertion" note — what the drill *rejects*, not just
     what it *accepts*. E.g. "step 4 proves no header → no dedup" —
     that's the negative test for an idempotency feature.

**Commits without a drill are blocked at review.** Bug-fix commits
must ship a drill that would have caught the bug. This is how the
regression surface grows: every bug becomes a test.

## Standard drill structure

```python
# RESOURCES: <space-separated-resources>
"""
One-paragraph purpose. What the drill proves + the failure mode it
closes.

Run:
    PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_<name>.py
"""
from __future__ import annotations
import asyncio

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"

def ok(msg): print(f"  {GREEN}✓ {msg}{NC}")
def fail(msg): print(f"  {RED}✗ {msg}{NC}"); raise SystemExit(1)
def step(title): print(f"\n{BOLD}── {title} ──{NC}")

async def main():
    step("1. <what we're asserting>")
    # ... test setup + assertion + ok() ...

    step("2. <next>")
    # ... ...

    print(f"\n{BOLD}{GREEN}════════════════════════════════════════{NC}")
    print(f"{BOLD}{GREEN}  ALL N <CATEGORY> STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}════════════════════════════════════════{NC}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Red flags

- **Drill that only tests the happy path.** Every drill needs at least
  one negative assertion — something that *should not happen* and the
  drill proves it didn't.
- **Drill that mocks any runtime dependency.** The whole point is
  exercising real services. Mocks belong in pytest.
- **Drill that requires manual setup steps.** The drill should
  start/restart services it needs; prerequisites are documented in a
  header comment but automatable.
- **Drill tagged `readonly` that writes to PG or restarts a service.**
  Tag dishonesty breaks the scheduler's isolation guarantees. Audit
  the drill before tagging and make it match reality.
- **Drill with a non-deterministic filter like "latest trace."** Use
  a drill-specific correlation_id or idempotency_key and filter on
  that. Otherwise the drill picks up stale state from prior runs and
  flakes in CI.

## Maintenance note

Keep this document normative rather than historical. Do not pin the
policy to session-specific counts like "N drills" or "last M commits"
inside the policy text; those numbers go stale quickly and turn a
project rule into a snapshot. If you want current coverage, inspect the
live drill inventory under `mcp/tests/drill_*.py` or capture the
current totals in a changelog, demo doc, or CI report instead.
