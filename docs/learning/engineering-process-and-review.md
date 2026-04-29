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

---

## Interview framework for code governance topics

When explaining code governance, do not recite checklists first. Start
with the control model:

1. core concept
2. why it exists
3. what failure it prevents
4. where it is enforced
5. what evidence proves it
6. what happens if it is bypassed

Use this 10-part structure for every pillar:

1. core concept
2. 5W
3. input -> process -> output
4. flowchart
5. sequence
6. challenges
7. edge cases
8. solutions
9. limitations
10. interview talking point

### Example: code review process

**Core concept**

Code review is the human control layer above automation.

**5W**

- `What:` peer and owner review of code changes before merge
- `Why:` CI catches mechanics; review catches design and risk
- `Who:` author, peer reviewer, code owner, security SME when required
- `When:` for every PR before merge
- `Where:` GitHub PR workflow and status gates

**Input -> Process -> Output**

- `Input:` PR, tests, migration notes, rollback plan
- `Process:` CI runs, reviewer checks behavior/risk/ownership, code owners approve
- `Output:` mergeable or blocked change

**Flowchart**

```text
Developer opens PR
  -> CI runs
  -> reviewer checks behavior + tests + rollback
  -> security review if sensitive path touched
  -> approve or request changes
  -> merge only if all gates are green
```

**Sequence**

```text
Author -> GitHub: open PR
GitHub -> CI: run lint/test/build/security
Reviewer -> PR: inspect design, tests, docs
CODEOWNER -> PR: approve or reject
GitHub -> main: merge if required checks pass
```

### Challenges to call out in interviews

- shallow rubber-stamp review
- approvals without risk understanding
- security-sensitive code reviewed by the wrong people
- PRs with no rollback story
- green CI hiding missing scenario coverage

### Edge cases to call out

- migration PR with tiny diff but huge operational risk
- config-only change with bigger blast radius than code change
- generated files or lockfiles hiding dependency risk
- hotfix pressure pushing teams toward bypassing review

### Limitations

- review quality is cultural as much as procedural
- a required approval is not proof of deep understanding
- automated checks can pass while runtime or rollout discipline is weak

---

## Universal flowchart + sequence template

Apply this to standards, review, audit, observability, CI, or release
workflow topics.

### Flowchart template

```text
Trigger / change request
  -> determine which policy surface is touched
  -> run automated gates
  -> run human review or audit path
  -> approve / reject / defer
  -> merge / remediate
```

### Sequence template

```text
Author -> Control surface: submit change
Control surface -> Automation: lint/test/build/scan
Automation -> Reviewer/Auditor: evidence
Reviewer/Auditor -> Control surface: approve or request changes
Control surface -> Runtime/main branch: allow or block
```

### What interviewers want to hear

- the control exists for a reason, not tradition
- the control has evidence, not just policy text
- the control has failure modes
- the control has ownership
- the control has limitations

That is what turns "process" into architecture-grade reasoning.
