# Tech Lead Audit Checklist

This note is a detailed audit checklist for a tech lead reviewing this project.

It is meant to answer:

- how to audit the project as a whole
- how to audit each service
- how to audit important functions and workflows
- how to audit the major tools and platform layers
- how to decide whether the project is truly trustworthy and ready for stronger environments

The checklist is intentionally split across multiple levels:

- project level
- service level
- function level
- tool level
- workflow level
- quality and benchmarking level

That is necessary because a system like this can look good at one layer while still being risky at another.

## 1. Project-Level Audit Checklist

## 1.1 Product and scope

- [ ] Is the project goal clear?
- [ ] Is the current state separated from the aspirational architecture?
- [ ] Is MVP scope clearly different from scale architecture?
- [ ] Are success criteria defined?
- [ ] Are non-goals explicit?

## 1.2 Architecture

- [ ] Are service boundaries coherent?
- [ ] Are route, service, store, and worker responsibilities clear?
- [ ] Are shared libraries shared mechanisms instead of policy dumps?
- [ ] Are critical workflows documented end to end?
- [ ] Are failure boundaries explicit?

## 1.3 Code quality

- [ ] Is linting enforced?
- [ ] Are tests meaningful instead of decorative?
- [ ] Are risky modules identifiable?
- [ ] Are large files or god modules growing unchecked?
- [ ] Are names and contracts clear?

## 1.4 Reliability

- [ ] Are retries, breakers, backpressure, and fallback paths defined?
- [ ] Is degraded mode intentional and tested?
- [ ] Is replay and recovery safe?
- [ ] Are state transitions race-safe?
- [ ] Are rollout and rollback behavior clear?

## 1.5 Security and governance

- [ ] Are auth, scopes, tenant isolation, and audit enforced?
- [ ] Are secrets and PII handled correctly?
- [ ] Are sensitive actions attributable to a real actor?
- [ ] Are approval or HITL points defined where needed?
- [ ] Are compliance-relevant logs and evidence retained?

## 1.6 Observability

- [ ] Can one request be traced end to end?
- [ ] Are latency, errors, breakers, drafts, replay, and audit failures visible?
- [ ] Are dashboards and alerts tied to owners?
- [ ] Are logs structured and correlation-aware?
- [ ] Can operators debug failures without code archaeology?

## 1.7 Production readiness

- [ ] Is there a real CI gate?
- [ ] Are load and capacity assumptions documented?
- [ ] Are benchmark baselines captured?
- [ ] Are runbooks present?
- [ ] Are ownership and on-call responsibilities explicit?

## 2. Service-Level Audit Checklist

Use this section for:

- `api-gateway`
- `identity-svc`
- `ingestion-svc`
- `retrieval-svc`
- `inference-svc`
- `evaluation-svc`
- `governance-svc`
- `finops-svc`
- `observability-svc`
- `frontend`

## 2.1 Responsibility

- [ ] Does the service have one clear job?
- [ ] Is it leaking business logic that belongs elsewhere?
- [ ] Does it depend on too many other services?

## 2.2 API and contracts

- [ ] Are request and response contracts explicit?
- [ ] Are error envelopes stable?
- [ ] Are auth and tenant requirements clear?
- [ ] Are breaking changes controlled?

## 2.3 State and storage

- [ ] Is state ownership clear?
- [ ] Are writes idempotent where needed?
- [ ] Are transitions guarded in storage, not only code?
- [ ] Are indexes and query paths sensible?

## 2.4 Failure handling

- [ ] What happens if dependencies are slow or down?
- [ ] Are retries bounded?
- [ ] Are breakers present where appropriate?
- [ ] Does the service fail honestly?

## 2.5 Monitoring

- [ ] Are p50, p95, p99, error rate, and saturation visible?
- [ ] Is backlog or queue state visible when relevant?
- [ ] Are alerts actionable?

## 2.6 Testing

- [ ] Are unit tests present for core logic?
- [ ] Are integration tests covering real flows?
- [ ] Are negative paths covered?
- [ ] Are drills or chaos scenarios present for critical failures?

## 3. Function-Level Audit Checklist

Use this for important functions, methods, and orchestration paths.

## 3.1 Inputs

- [ ] Are inputs validated?
- [ ] Are assumptions explicit?
- [ ] Are tenant and auth requirements enforced?

## 3.2 Outputs

- [ ] Is the return contract clear?
- [ ] Are error states distinguishable?
- [ ] Is degraded behavior explicit?

## 3.3 Side effects

- [ ] Does the function write DB state?
- [ ] Does it call an external service?
- [ ] Is idempotency handled?
- [ ] Is audit required?

## 3.4 Failure behavior

- [ ] What happens on timeout?
- [ ] What happens on duplicate execution?
- [ ] What happens on partial success?
- [ ] What happens on stale state?

## 3.5 Naming and readability

- [ ] Does the name reflect domain meaning?
- [ ] Can a reviewer understand the path quickly?
- [ ] Is it doing one real job?

## 4. Tool-Level Audit Checklist

## 4.1 MCP

- [ ] Are tool names and namespaces coherent?
- [ ] Are tool schemas explicit?
- [ ] Are required scopes correct?
- [ ] Are read vs write tools distinguished?
- [ ] Are idempotency and degraded fallback defined?
- [ ] Are per-tool metrics exported?
- [ ] Are replay and audit semantics correct?

## 4.2 Circuit breaker

- [ ] Is breaker placement correct?
- [ ] Are thresholds sane?
- [ ] Is half-open behavior tested?
- [ ] Are metrics exported?
- [ ] Is breaker state visible to operators?
- [ ] Are retries fighting the breaker?

## 4.3 RAG

- [ ] Is chunking strategy documented?
- [ ] Is embedding model and version tracked?
- [ ] Are pre-retrieval and post-retrieval stages explicit?
- [ ] Are retrieval quality metrics defined?
- [ ] Are citations and grounding checked?
- [ ] Is cache behavior visible?

## 4.4 Frontend

- [ ] Are core workflows usable on desktop and mobile?
- [ ] Are loading, error, and empty states real?
- [ ] Are browser-console and network failures handled?
- [ ] Are admin and operator views credible?
- [ ] Is accessibility acceptable?

## 4.5 Observability stack

- [ ] Is OTel instrumentation complete on critical paths?
- [ ] Are Prometheus metrics high-signal?
- [ ] Are Grafana dashboards tied to decisions?
- [ ] Are traces linked to drafts, audit, and tool calls?
- [ ] Is AI-specific tracing present or still missing?

## 4.6 Security tools

- [ ] Are scopes and RBAC enforced?
- [ ] Are PII controls real or only documented?
- [ ] Are secrets managed properly?
- [ ] Are unsafe tool paths blocked?
- [ ] Are audit failures visible?

## 5. Critical Workflow Audit Checklist

These workflows deserve explicit audit attention.

## 5.1 Ask flow

- [ ] Retrieval occurs correctly
- [ ] Generation remains grounded
- [ ] Latency is acceptable
- [ ] Errors are surfaced clearly

## 5.2 Ask plus MCP action flow

- [ ] Intent detection is correct
- [ ] Scope pre-check is correct
- [ ] Tool routing is correct
- [ ] Result envelope is correct

## 5.3 Degraded draft flow

- [ ] Breaker or dependency failure creates draft when expected
- [ ] User gets an honest degraded result
- [ ] Audit is written or failure is visible
- [ ] Duplicate side effects are avoided

## 5.4 Replay flow

- [ ] Only pending drafts replay
- [ ] Replay is idempotent
- [ ] Actor attribution is truthful
- [ ] Audit row is written
- [ ] Backlog drains after recovery

## 5.5 Governance flow

- [ ] Denials are visible
- [ ] Audit trail is complete
- [ ] Tenant isolation is preserved
- [ ] Sensitive actions are reviewable

## 6. Quality And Benchmark Audit Checklist

## 6.1 Code and test quality

- [ ] Lint is green
- [ ] Tests are meaningful
- [ ] Regression tests exist for past bugs
- [ ] Service tests are present
- [ ] Frontend tests are present

## 6.2 Performance

- [ ] Baseline load contract exists
- [ ] Peak load contract exists
- [ ] Stress behavior is known
- [ ] Recovery behavior is known
- [ ] Replay lag is measured
- [ ] Cost per request is measured

## 6.3 AI quality

- [ ] Retrieval quality benchmark exists
- [ ] Prompt regression checks exist
- [ ] Output evaluation exists
- [ ] Unsafe output is blocked
- [ ] Low-confidence behavior is defined

## 7. Red-Flag Checklist

These should be treated as immediate audit findings.

- [ ] Docs describe flows that code does not really implement
- [ ] Route handlers own workflow logic
- [ ] State transitions are enforced only in Python branches
- [ ] Breakers exist but are not observed
- [ ] Degraded mode exists but is not tested
- [ ] Audit is optional for sensitive actions with no failure visibility
- [ ] No per-tool metrics exist for MCP actions
- [ ] No easy way to follow trace -> draft -> replay -> audit
- [ ] Frontend hides failures instead of explaining them
- [ ] “Production-ready” claims exist without benchmarks or runbooks

## 8. Deliverables From The Audit

A strong audit should produce:

- findings ordered by severity
- ownership per finding
- quick fixes vs structural fixes
- benchmark gaps
- monitoring gaps
- workflow risk map
- release-readiness judgment
- explicit rationale for:
  - safe for stronger environments
  - not safe yet

## 9. Recommended Audit Output Format

Use this structure:

1. Executive summary
2. Strengths
3. Critical risks
4. Workflow findings
5. Tool and platform findings
6. Monitoring and benchmark findings
7. Security and governance findings
8. Recommended next 30, 60, and 90 day actions

## 10. Bottom Line

The right tech-lead audit is not:

- “does the code look clean?”

It is:

- does the system behave correctly?
- does it fail safely?
- can operators understand it?
- can the team trust it?
- can it be benchmarked, monitored, and governed?

That is the standard this repo should be judged against.
