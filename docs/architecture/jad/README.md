# JAD — Joint Application Design Records

> Per CLAUDE.md §47.5 (JAD chain) + §57.1 (production-grade only):
> The unidirectional flow `JAD session → BRD → C4 (L1–L7) → ADRs →
> Backlog → Sprints` requires written JAD records. New constraints
> trigger a new mini-JAD, never a hidden in-flight pivot.

## What lives here

Every joint design session that locks a major constraint produces
a record in this directory. JAD records are operator-readable — a
new engineer should be able to reconstruct WHY a decision was made,
not just WHAT it was.

| Field | Purpose |
|---|---|
| Session ID | `JAD-YYYYMMDD-NN` (date + sequence) |
| Stakeholders | Who attended; their decision rights |
| Driving constraint | What problem triggered this session |
| Options considered | What alternatives were on the table |
| Decision | What was locked |
| ADRs created | Numbered ADR files derived from this JAD |
| Backlog items | Tickets / iters created from this JAD |
| Re-open trigger | What would force a new mini-JAD |

## Index

| ID | Date | Topic | ADRs | Status |
|---|---|---|---|---|
| JAD-20260507-01 | 2026-05-07 | RAG Platform Architecture Foundation | ADR-001..010 | LOCKED |
| JAD-20260507-02 | 2026-05-07 | Council + MCP Fleet Expansion | ADR-025..029 | LOCKED |

## JAD Records

### [JAD-20260507-01] RAG Platform Architecture Foundation

**Stakeholders:** platform-architect, platform-data, platform-ai,
platform-comms, platform-cloud (decision rights), operator (final
sign-off).

**Driving constraint:** establish the boundaries of the RAG
platform such that 28+ MCP servers can be added without breaking
the core read/write surface separation, the §47 7-design-surface
contract, or the §51 forensic-substrate guarantee.

**Options considered:**

1. **Single FastAPI monolith** — all tools as routes on one service.
   Rejected because: tenant isolation (§41.3) becomes per-route, not
   per-service; explosion in routing complexity at >10 tools.
2. **Per-tool microservice** — each tool a separate container.
   Rejected because: operational overhead (28+ services), no
   namespace boundary, drill discovery becomes O(n²).
3. **MCP server per namespace** — chosen. ~1 service per logical
   namespace (slack / github / aws / etc). Each ships read-only
   Stage-1; write surfaces require separate ADR.

**Decision:** MCP server pattern with the `_live_or_stub` env-driven
contract, `/health`+`/tools/list`+`/tools/call` canonical routes,
`required_scopes` per tool, side_effects=read|write metadata, and
default-deny OPA policy bundle.

**ADRs created:** ADR-001 (LLM provider) through ADR-010 (token
budget). See `docs/architecture/adr/`.

**Backlog items:** iters 1–28 of the autonomous-loop (each MCP
server). Reference: `git log --grep "iter-"`.

**Re-open trigger:** any of: a tool needing >2 namespaces of
context; write-tool count exceeding 5 total; OPA policy default
flipping from deny.

---

### [JAD-20260507-02] Council + MCP Fleet Expansion

**Stakeholders:** platform-ai (council architecture), platform-data
(catalog schema), platform-qa (drill discipline), operator.

**Driving constraint:** the operator needs to know "which agents
are working" empirically, not by claim. Per §57: vibes don't cut it;
production-grade is what the scorecard says it is.

**Options considered:**

1. **Health endpoint per service** — only verifies process is up.
   Rejected because: doesn't prove the service can do useful work
   (a generation, an apply, a council vote).
2. **Manual ad-hoc smoke tests** — rejected because operator can't
   run them at 2 AM during incident.
3. **4-inventory fleet monitor + 7-dim readiness probe + 5-dim
   scorecard** — chosen. Empirical, scheduled, surfaced in UI,
   drilled.

**Decision:** ship `scripts/mcp_fleet_health.py` (iter-72),
`scripts/agent_readiness_check.py` (iter-76),
`scripts/production_readiness_scorecard.py` (iter-78), all with
matching UI pages and drills.

**ADRs created:** ADR-025 (council role mapping), ADR-027 (agent
framework), ADR-028 (CSV-to-DB write surface contract), ADR-029
(business usecase to docs framework).

**Backlog items:** iters 72–80 of the autonomous-loop. Reference:
`git log b3ece5d` and predecessors.

**Re-open trigger:** scorecard threshold below 70 across any
dimension for 7+ days; new policy section added (§58+); council
apply rate trending below 50% post-§55-Tier-1 implementation.

## Compose with §47

JAD is upstream of every other §47 surface. A new constraint surfaces
in JAD before it touches:

- C4 (L1–L7) diagrams
- ADR registry
- Security STRIDE tables
- Rollout runbooks
- Load test scenarios

If a change touches code without a JAD trail, the change is by
definition unauthorized — it bypassed stakeholder approval.

## The brutal rule

> A locked decision without a JAD record is tribal knowledge. Six
> months from now, no one remembers the *why* — only the code, which
> is the *what*. The why is the load-bearing artifact.
