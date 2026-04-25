# Engineering Process And Review

This guide covers the process, review, delivery, and growth topics that
turn code-writing into disciplined engineering.

---

## Testing methods: TDD, BDD, regression, drills

Different test styles fit different problems.

### TDD

Best for:

- parsers
- validators
- local state transition rules
- deterministic helper/domain logic

### BDD

Best for:

- user or operator workflow behavior
- auth and permission behavior
- acceptance-style scenarios
- shared understanding across roles

### Regression testing

Most valuable when:

- fixing real bugs
- hardening workflows after incidents
- preventing replay/auth/audit regressions

### Drill and integration testing

Best for:

- real composed service behavior
- degraded and recovery paths
- cross-service or worker-flow correctness
- breaker and replay behavior

Golden rule:

- a test must hit the real path it claims to validate

---

## Metrics, scoring, and honest quality measurement

There is no single honest quality score.

Track dimensions instead:

- correctness and incident rate
- maintainability hotspots
- churn in risky files
- flaky test rate
- review latency and PR size
- runtime latency, backlog, failure rates
- audit/breaker/degraded-path visibility

Bad habits:

- treating raw coverage as proof
- using one quality number as truth
- optimizing for vanity counts
- ignoring context and gaming incentives

---

## Visualization and diagramming

Use visuals to compress complexity, not decorate docs.

High-value diagram types:

- architecture diagrams
- dependency graphs
- sequence diagrams
- state diagrams
- data-flow diagrams

Useful repo visuals:

- draft replay sequence diagram
- draft state machine
- MCP client/server routing diagram
- boundary map for `mcp/`, `documind_core`, and services

---

## Planning, estimation, RFCs, and decision artifacts

### Planning

A good plan states:

- problem
- scope
- non-goals
- invariants
- risks
- dependencies
- proof of completion

### Estimation

Estimate based on:

- coupling
- migration complexity
- test and rollout cost
- cross-service or storage impact
- uncertainty and unknowns

Avoid fake precision.

### Decision artifacts

Useful forms:

- implementation plan
- design note
- RFC
- ADR
- migration checklist

Use just enough structure for the risk level.

---

## Reuse, abstraction, and shared-vs-local code decisions

Good reuse shares stable mechanism.
Bad reuse merges different policy under a fake abstraction.

Share code when:

- semantics are truly the same
- drift risk is real
- ownership becomes clearer
- invariants become easier to enforce

Keep code local when:

- behavior only looks similar
- policy meaning differs
- the abstraction would hide important differences
- local clarity is better than generic reuse

Most useful lens:

- shared mechanism vs shared policy

---

## Technical debt, refactoring, and review mindset

### Technical debt

Debt is best classified by risk:

- security/isolation debt
- correctness/state debt
- observability debt
- duplicated drift-prone logic
- performance debt on hot paths

### Refactoring

Safe refactoring is incremental:

1. characterize current behavior
2. introduce a seam
3. migrate one path
4. verify
5. migrate remaining callers
6. delete old path

### Review mindset

Good review is about spotting future incidents early:

- what invariant is weak?
- what assumption is unenforced?
- what can silently fail?
- what can race?
- what path is untested or falsely tested?
- what duplication will drift?

---

## Documentation strategy and AI-specific documentation

### Documentation types

- code-adjacent docs
- design docs
- ADRs
- runbooks
- policies and standards
- usage docs

### Keep docs honest

Avoid:

- stale snapshots in standing docs
- comments that claim more than code proves
- operational docs that assume tribal knowledge

### AI/RAG-specific documentation

- prompt versioning
- retrieval strategy docs
- chunking policy docs
- model selection docs
- evaluation criteria
- governance and guardrail docs
- component cards for prompts/models/retrievers

---

## Growth path: developer to senior to staff-level thinker

### Strong Python/backend engineer

- can implement features reliably
- understands APIs, async basics, DB usage, tests

### Senior backend engineer

- reasons in invariants and workflows
- spots design rot and concurrency hazards
- uses tests and refactors to make subsystems safer

### Staff-level/system-design engineer

- starts from guarantees and failure modes
- cares about migration, rollout, operability, and ownership
- shapes architecture so local changes become cheaper and safer

Default staff-level questions:

- what guarantees are required?
- what can fail silently?
- who owns this state and policy?
- what is the migration path?
- how will operators debug it?
- what future incident does this prevent or create?

