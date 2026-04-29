import Link from 'next/link';
import Mermaid from '../../../components/Mermaid';

export const metadata = { title: 'Code Governance — DocuMind' };

type Pillar = {
  id: string;
  title: string;
  summary: string;
  coreConcept: string;
  whyItMatters: string;
  checklist: string[];
  challenges: string[];
  edgeCases: string[];
  limitations: string[];
  evidence: string[];
  refUrl: string;
  refLabel: string;
};

function safe(value: string, maxLen = 72): string {
  return value
    .replace(/\.$/, '')
    .replace(/[\n\r]/g, ' ')
    .replace(/["`]/g, "'")
    .replace(/[<>{}]/g, '')
    .slice(0, maxLen);
}

function buildFlowchart(p: Pillar): string {
  return `flowchart LR
  t[Trigger: ${safe(p.whyItMatters, 84)}] --> g{${safe(p.title, 40)} applies?}
  g -->|yes| a[Apply control: ${safe(p.coreConcept, 84)}]
  g -->|no| b[Bypass / drift path]
  a --> c[Checks run: ${safe(p.checklist[0] ?? 'repo policy', 72)}]
  c --> o[Outcome: safer release / review / runtime]
  b --> r[Risk: inconsistent code / hidden failure mode]
  r --> o`;
}

function buildSequence(p: Pillar): string {
  return `sequenceDiagram
  autonumber
  participant Dev as Engineer
  participant Gate as ${safe(p.title, 28)}
  participant Tool as Tooling / Reviewer
  participant Repo as Repo / CI
  Dev->>Gate: propose change
  Gate->>Tool: apply rule / review / audit
  alt passes
    Tool->>Repo: approved change
    Repo-->>Dev: merge / release path
  else fails
    Tool-->>Dev: findings / blocked checks
    Dev->>Gate: revise implementation
  end
  Note over Gate: ${safe(p.whyItMatters, 96)}`;
}

function buildNetwork(p: Pillar): string {
  return `flowchart TB
  subgraph edge [Edge]
    dev[Engineer workstation]
    pr[Pull request]
  end
  subgraph ctrl [Governance control]
    lint[Lint / format / type]
    review[Review / audit]
    ci[CI pipeline]
  end
  subgraph runtime [Runtime evidence]
    svc[Services]
    obs[Logs / traces / metrics]
    doc[Docs / ADR / runbook]
  end
  dev --> pr
  pr --> lint
  pr --> review
  lint --> ci
  review --> ci
  ci --> svc
  svc --> obs
  review --> doc
  obs --> review
  doc --> dev
  note1[${safe(p.title, 32)}]:::ghost
  classDef ghost fill:#fff,stroke:#fff,color:#991b1b;`;
}

function implementationSteps(p: Pillar): string[] {
  const firstChecklist = p.checklist.slice(0, 4);
  return [
    `Define the governance rule for ${p.title.toLowerCase()} in one place before enforcing it broadly.`,
    `Wire the control into the right mechanism: lint, review, CI, middleware, or runtime guard.`,
    ...(firstChecklist.length > 0
      ? firstChecklist.map((item) => `Enforce: ${item}.`)
      : [`Encode at least one explicit automated or review-time check for ${p.title.toLowerCase()}.`]),
    `Verify the control with one normal path and one failure path before relying on it in production.`,
  ];
}

const PILLARS: Pillar[] = [
  {
    id: 'standards',
    title: 'Code Standards & Guidelines',
    summary:
      'Mechanical standards enforced by tools, not reviewers. If the linter says no, it means no.',
    coreConcept:
      'Code standards turn subjective style preferences into objective, automated policy. Reviewers should spend time on behavior and risk, not formatting and import order.',
    whyItMatters:
      'Without mechanical standards, teams debate style on every PR, risky shortcuts slip in, and code quality becomes personality-driven instead of enforceable.',
    checklist: [
      'Python: ruff (E, W, F, I, N, UP, B, A, C4, SIM, S) + black 120col + mypy',
      'TypeScript: strict mode, ESLint Next preset, Prettier',
      'Go: gofmt + golangci-lint',
      'No f-string SQL, ever. Parameterized queries only',
      'No `os.environ.get`; every setting via Pydantic BaseSettings',
      'Domain exceptions in services; HTTPException only in routers',
      'No module-level mutable state — instance attributes only',
      'All list endpoints paginated with offset/limit; max limit 500',
      'All HTTP/DB/subprocess calls have explicit timeouts',
    ],
    challenges: [
      'Keeping Python, Go, and TypeScript rule sets aligned without creating contradictory local conventions',
      'Avoiding rule explosion that produces noise instead of value',
      'Blocking dangerous patterns consistently without frustrating valid exceptions',
    ],
    edgeCases: [
      'Generated files or vendored snippets may need documented exclusions instead of ad hoc linter disables',
      'Strict formatting can conflict with readability on complex SQL, Mermaid, or matrix-heavy docs',
      'Static typing can lag behind runtime reality if boundary validation is weak',
    ],
    limitations: [
      'Passing lint/format/type checks does not prove behavior is correct',
      'Standards reduce variance, but they do not replace design review or testing',
    ],
    evidence: [
      'pyproject.toml (ruff/black/mypy/pytest config)',
      'libs/py/pyproject.toml (per-package overrides, kept in sync)',
      '.pre-commit-config.yaml (blocking gate)',
    ],
    refUrl: 'https://docs.astral.sh/ruff/',
    refLabel: 'Ruff — lint rules',
  },
  {
    id: 'review',
    title: 'Code Review Process',
    summary:
      'Every change reviewed by one peer minimum. Security-sensitive paths need a named SME. No self-approval.',
    coreConcept:
      'Code review is the human control layer above automation. CI proves the change passes checks; review proves the change makes sense.',
    whyItMatters:
      'Many production failures are not syntax errors. They are design mistakes, rollback blind spots, weak tests, or missing security reasoning that only appear under informed review.',
    checklist: [
      'PR description explains WHY, not just what',
      'At least one approval from CODEOWNERS for the touched directory',
      'Security-tagged paths (auth, RLS, encryption, prompts) need a second reviewer from the security group',
      'CI must be green: lint, unit tests, mypy, build, smoke E2E',
      'If the diff touches a migration: explicit rollback plan in description',
      'No merge commits on main; rebase-and-squash only',
      'Reviewer checks: tests added/updated, docs touched, .env.template updated, no secrets committed',
    ],
    challenges: [
      'Avoiding shallow rubber-stamp approvals on large diffs',
      'Ensuring sensitive paths are reviewed by someone who understands the actual threat model',
      'Keeping review latency low without lowering the bar',
    ],
    edgeCases: [
      'Migration PRs can look tiny but carry the highest rollback risk',
      'Infra or prompt changes may affect many services while touching only a few files',
      'A green CI run can still hide a missing scenario or degraded-path test',
    ],
    limitations: [
      'Review quality is cultural as much as procedural',
      'A required approval is not proof that the reviewer fully understood the failure modes',
    ],
    evidence: [
      '.github/CODEOWNERS',
      '.github/pull_request_template.md',
      '.github/workflows/ci.yml (required status checks)',
    ],
    refUrl: 'https://google.github.io/eng-practices/review/',
    refLabel: 'Google — Engineering Practices: Code Review',
  },
  {
    id: 'audit',
    title: 'Audit Review Process',
    summary:
      'A second loop beyond code review: every quarter the architect group re-reads the load-bearing surfaces and files an audit report.',
    coreConcept:
      'Audit is system-level revalidation. It asks whether the whole platform is still trustworthy, not whether a single PR looks safe.',
    whyItMatters:
      'PR review is local and change-based. Audits revisit guarantees like tenant isolation, breaker behavior, and dependency posture that can drift over months.',
    checklist: [
      'RLS boundary: run the cross-tenant test against a real PG (not mocked)',
      'Encryption: rotate Fernet key on a test DB and verify rollback',
      'Prompt injection: replay the latest jailbreak corpus against current detector',
      'Outbox: kill the relay mid-publish, verify no event loss / no duplicates',
      'Circuit breakers: chaos test (kill Ollama), verify fail-fast, no cascade',
      'SLOs: compare last 30d to targets; if missed, file an incident retro',
      'Dependency audit: pip-audit + npm audit + govulncheck; triage every finding',
      'Access review: who has access to prod secrets, does it match the org chart',
    ],
    challenges: [
      'Keeping audits evidence-based instead of turning them into paperwork',
      'Running proof tests against real stores and real failure paths, not mocks',
      'Assigning and closing findings instead of letting them accumulate as permanent debt',
    ],
    edgeCases: [
      'Mocked RLS or encryption tests can produce a false sense of safety',
      'A quarterly audit may miss drift introduced by emergency changes unless incident follow-up is strong',
      'Dependency scans may produce many low-signal findings that still need triage discipline',
    ],
    limitations: [
      'Audits are periodic, not continuous',
      'An audit can identify risk, but it does not fix the underlying implementation automatically',
    ],
    evidence: [
      'docs/AUDIT-2026-04-23.md (template for quarterly audits)',
      'docs/ARCHITECT-TALKING-POINTS.md §5 (the RLS audit story)',
      'libs/py/tests/test_rls_isolation.py (the proof test)',
    ],
    refUrl: 'https://www.nist.gov/cyberframework',
    refLabel: 'NIST Cybersecurity Framework',
  },
  {
    id: 'reusability',
    title: 'Code Reusability',
    summary:
      'If the same code appears twice, a helper is overdue. If it appears three times, it is a bug.',
    coreConcept:
      'Reusable code is about preserving shared invariants, not reducing keystrokes. Stable mechanisms belong in shared libraries; unstable policy stays local.',
    whyItMatters:
      'Duplication across services causes observability drift, inconsistent auth behavior, and repeated bug fixes in slightly different forms.',
    checklist: [
      'Shared primitives live in libs/py/documind_core/ (never duplicated per service)',
      'DI via FastAPI Depends — every repo and service is constructor-injected',
      'Interfaces behind every external dep (VectorSearcher, GraphSearcher, Chunker, Embedder)',
      'Frontend components live in services/frontend/components/ when used in 2+ places',
      'Hooks in services/frontend/hooks/ when logic is shared across components',
      'No copy-pasted migrations — each is numbered once, idempotent',
    ],
    challenges: [
      'Avoiding premature abstractions that hide meaningful differences',
      'Keeping shared libraries small, stable, and infrastructure-focused',
      'Preventing service-specific policy from leaking into repo-wide primitives',
    ],
    edgeCases: [
      'Two flows can look similar but differ in auth or failure semantics',
      'A shared helper can accidentally encode one service’s assumptions into every consumer',
      'Frontend reuse can create bloated generic components if done too early',
    ],
    limitations: [
      'Reuse can increase coupling when the abstraction boundary is wrong',
      'Some duplication is cheaper than an abstraction that hides important semantics',
    ],
    evidence: [
      'libs/py/documind_core/ (all shared primitives)',
      'services/frontend/components/Markdownish.tsx, ToolTabs.tsx, CodeBlock.tsx, Mermaid.tsx',
      'services/*/app/core/dependencies.py (DI factories)',
    ],
    refUrl: 'https://martinfowler.com/bliki/DontRepeatYourself.html',
    refLabel: 'Martin Fowler — DRY',
  },
  {
    id: 'debuggability',
    title: 'Code Debuggability',
    summary:
      'You cannot fix what you cannot see. Every request must be traceable from edge to DB and back.',
    coreConcept:
      'Debuggability means the system can explain what happened, where it failed, and which request, actor, and tenant were affected.',
    whyItMatters:
      'Incident response in distributed systems collapses without trace continuity, structured logs, and operator-visible failure state.',
    checklist: [
      'Correlation-ID injected at the gateway, propagated through every hop',
      'JSON structured logs via structlog — never print()',
      'OTel traces on every inter-service call; Jaeger always-on in dev',
      '?debug=true query flag exposes CCB snapshot + breaker states in the response',
      'Every exception logs with the full context dict, not just the message',
      'No bare `except:`; specific exception types or re-raise',
      'Key metrics exported to Prometheus with bounded labels (no tenant_id in metric labels)',
    ],
    challenges: [
      'Capturing enough context without flooding logs and traces with noise',
      'Maintaining correlation IDs across gateway, services, MCP, and frontend error reporting',
      'Making dashboards actionable instead of decorative',
    ],
    edgeCases: [
      'A timeout may look like a generic 500 unless dependency and breaker state are both visible',
      'A request can fail on the frontend while the backend succeeded unless the correlation chain is preserved',
      'High-cardinality labels can break Prometheus long before the product is under real user load',
    ],
    limitations: [
      'Observability provides evidence, not automatic diagnosis',
      'A well-instrumented system can still be hard to debug if state models are poorly designed',
    ],
    evidence: [
      'libs/py/documind_core/logging_config.py (JsonFormatter + correlation_id)',
      'libs/py/documind_core/middleware.py (CorrelationIdMiddleware)',
      'libs/py/documind_core/observability.py (OTel setup)',
    ],
    refUrl: 'https://opentelemetry.io/docs/concepts/observability-primer/',
    refLabel: 'OTel — observability primer',
  },
  {
    id: 'explainability',
    title: 'Code Explainability',
    summary:
      'Comments explain WHY, not WHAT. Names do the "what". Every load-bearing decision has an ADR.',
    coreConcept:
      'Explainability in code means future engineers can reconstruct intent, tradeoffs, and failure modes without relying on tribal knowledge.',
    whyItMatters:
      'Load-bearing systems decay quickly when only the original author understands why a breaker threshold, regex, or policy rule exists.',
    checklist: [
      'File-level docstring on every module: purpose, why this exists, design tradeoff',
      'Class-level docstring: responsibilities + constructor args + failure modes',
      'No comments that paraphrase the next line of code',
      'Non-obvious regex, thresholds, magic numbers: inline comment with the rationale',
      'Every ADR (Architecture Decision Record) captured in docs/architecture/ADRs/',
      'Every tool in /tools has a first-person Interview tab explaining rationale in plain English',
    ],
    challenges: [
      'Keeping documentation honest as implementation evolves',
      'Explaining non-obvious decisions without drowning files in low-value commentary',
      'Capturing architecture reasoning before it disappears into chat and memory',
    ],
    edgeCases: [
      'A magic number can look arbitrary until an incident reveals why it exists',
      'A regex may be correct but unsafe to maintain without rationale and examples',
      'A complex fallback path may be understandable to the author but opaque to reviewers',
    ],
    limitations: [
      'Documentation can drift from code',
      'Comments and ADRs improve comprehension, but they do not enforce correctness',
    ],
    evidence: [
      'docs/architecture/ADRs/ (decision records)',
      'docs/ARCHITECT-TALKING-POINTS.md (10 load-bearing decisions + counter-questions)',
      'libs/py/documind_core/ccb.py (example: docstring explains the paper + tradeoffs)',
    ],
    refUrl: 'https://adr.github.io',
    refLabel: 'ADR (Architectural Decision Records)',
  },
  {
    id: 'exceptions',
    title: 'Exception Handling',
    summary:
      'Exceptions are typed, caught at the right layer, and never silently swallowed.',
    coreConcept:
      'Typed exceptions define the failure vocabulary of the system. Domain, policy, and dependency failures should not all look like generic 500s.',
    whyItMatters:
      'Production systems need predictable failure semantics for retries, breakers, API mapping, incident triage, and operator remediation.',
    checklist: [
      'AppError hierarchy in documind_core/exceptions.py (NotFoundError, ValidationError, PolicyViolationError, CircuitOpenError, …)',
      'Services raise AppError subclasses; routers translate to HTTP in one place (error_handlers.py)',
      'No raw `except:` — specific types or re-raise with context',
      'Every external call wrapped in CircuitBreaker (fail-fast, not hang)',
      'Background tasks MUST set a failed-job status on exception; never die silently',
      'DLQ for events that fail N times',
    ],
    challenges: [
      'Preventing broad catch blocks from hiding the true failure class',
      'Mapping exceptions consistently across routers, workers, and async tasks',
      'Making retries safe only for genuinely transient failures',
    ],
    edgeCases: [
      'A timed-out dependency may have completed remotely, creating duplicate-risk on retry',
      'Background workers can fail silently unless job state is updated on exception',
      'Policy violations can be accidentally surfaced as generic internal errors',
    ],
    limitations: [
      'Exception taxonomy improves clarity but does not guarantee graceful recovery',
      'Async and background contexts still require explicit status and audit handling',
    ],
    evidence: [
      'libs/py/documind_core/exceptions.py',
      'services/*/app/core/error_handlers.py',
      'libs/py/documind_core/circuit_breaker.py + breakers.py',
      'libs/py/documind_core/kafka_client.py (DLQ pattern)',
    ],
    refUrl: 'https://docs.python.org/3/tutorial/errors.html',
    refLabel: 'Python — Errors & Exceptions',
  },
  {
    id: 'logging',
    title: 'Logging, Tracing, Metrics',
    summary:
      'Three signals, structured, correlated. Logs for forensics; traces for flows; metrics for SLOs.',
    coreConcept:
      'Observability is a multi-signal discipline: logs capture events, traces capture flow, and metrics capture system behavior over time.',
    whyItMatters:
      'Without all three signals, it is hard to distinguish a bad request, a slow dependency, a degraded fallback, and a systemic outage.',
    checklist: [
      'Logs: JSON, timestamp UTC, correlation_id, tenant_id (never PII in message body)',
      'Traces: OTel spans on every boundary crossing; parent-child properly propagated',
      'Metrics: Prometheus counters/gauges/histograms; bounded cardinality',
      'Observability CB wraps every exporter — dead telemetry NEVER blocks user requests',
      'ELK for log search; Jaeger for traces; Grafana dashboards per SLO',
      'Sampling policy: 100% errors, 10% normal traffic, 100% slow (p99+)',
    ],
    challenges: [
      'Choosing bounded labels and useful span attributes',
      'Ensuring telemetry exporters never become part of the user-facing failure path',
      'Linking frontend, backend, and operator views into the same request story',
    ],
    edgeCases: [
      'A slow but successful dependency call may not show in error dashboards without latency alerts',
      'Sampling can hide the interesting request unless errors and slow paths are always captured',
      'PII can leak through logs if message bodies are not disciplined',
    ],
    limitations: [
      'Telemetry volume can become expensive and noisy',
      'Observability tells you what happened; it still takes engineering judgment to decide what to change',
    ],
    evidence: [
      'libs/py/documind_core/logging_config.py',
      'libs/py/documind_core/observability.py',
      'services/observability-svc/migrations/001_initial.sql (slo_targets)',
    ],
    refUrl: 'https://sre.google/sre-book/monitoring-distributed-systems/',
    refLabel: 'Google SRE — Monitoring Distributed Systems',
  },
  {
    id: 'build',
    title: 'Code Build & CI',
    summary:
      'One command to lint, one to test, one to build. CI runs them on every PR.',
    coreConcept:
      'Build and CI form the automated enforcement path from source change to releasable artifact.',
    whyItMatters:
      'If the local quality bar and the CI quality bar diverge, teams eventually optimize for the easier one and ship surprises.',
    checklist: [
      '`make lint` — ruff + black + mypy + tsc + next lint + golangci-lint',
      '`make test` — pytest (matrix per service) + vitest (frontend)',
      '`make build` — docker build per service + next build',
      '`make migrate` — applies all migrations in order',
      '`make smoke` — spins up compose, hits /health on every service',
      'CI matrix: lint → test → build → e2e → security scan (pip-audit, bandit, npm audit)',
      'Required status checks: every PR blocks on green CI',
    ],
    challenges: [
      'Keeping the pipeline fast enough to be respected while still catching real regressions',
      'Avoiding flaky tests that train reviewers to ignore red builds',
      'Ensuring smoke environments reflect runtime reality closely enough to matter',
    ],
    edgeCases: [
      'Build can pass while runtime still fails because stale processes or bad rollout discipline exist',
      'A migration may succeed on empty databases and fail on realistic seeded state',
      'Frontend tests may be absent even when the build is green, leaving runtime-only defects',
    ],
    limitations: [
      'CI only catches the checks we have actually encoded',
      'A green pipeline is necessary but never sufficient proof of production readiness',
    ],
    evidence: [
      'Makefile (all targets)',
      '.github/workflows/ci.yml (pipeline)',
      'docker-compose.yml (local smoke env)',
    ],
    refUrl: 'https://docs.github.com/en/actions',
    refLabel: 'GitHub Actions docs',
  },
  {
    id: 'management',
    title: 'Code Management',
    summary:
      'Conventional commits + CODEOWNERS + trunk-based workflow. Nothing exotic.',
    coreConcept:
      'Code management is the workflow and ownership model that makes change understandable, attributable, and reversible.',
    whyItMatters:
      'When branching, ownership, release notes, and dependency history are sloppy, incident response and accountability both degrade.',
    checklist: [
      'Conventional Commits: feat/fix/chore/docs/refactor/test',
      'feature/* branches from main; PR back to main; rebase-and-squash',
      'No force-push to main (protected branch)',
      'Every PR template: summary, test plan, rollback plan',
      'CODEOWNERS enforces reviewer group per directory',
      'Semantic versioning for public artifacts; CHANGELOG.md kept in lockstep',
      'Dependencies pinned with a range; lockfile committed; Dependabot opens weekly PR',
    ],
    challenges: [
      'Maintaining ownership clarity across a growing polyglot monorepo',
      'Keeping PR descriptions and changelog entries meaningful rather than ceremonial',
      'Preventing direct-main hotfixes from bypassing normal release evidence',
    ],
    edgeCases: [
      'A small dependency bump can have a wider blast radius than a large feature diff',
      'A PR can touch multiple design surfaces with no single obvious owner unless CODEOWNERS is well maintained',
      'Rollback is slower when the release intent and blast radius were never documented',
    ],
    limitations: [
      'Strong workflow can still be undermined by weak team discipline',
      'Process alone does not compensate for missing technical safeguards',
    ],
    evidence: [
      '.github/CODEOWNERS',
      '.github/pull_request_template.md',
      'CHANGELOG.md',
      'requirements.txt + requirements-dev.txt',
    ],
    refUrl: 'https://www.conventionalcommits.org/',
    refLabel: 'Conventional Commits',
  },
];

const PER_DESIGN_CHECKLIST = [
  { area: 'Any persistent write',        items: ['Migration has rollback SQL', 'Tenant boundary (RLS or explicit WHERE tenant_id=)', 'Idempotency key strategy documented', 'Outbox if event published alongside write'] },
  { area: 'Any external call',           items: ['Circuit breaker wrapping the call', 'Timeout set explicitly', 'Retry policy with exponential backoff', 'Fallback / degraded response defined'] },
  { area: 'Any LLM invocation',          items: ['PromptInjectionDetector on input (fail-closed)', 'PIIScanner on input + output', 'CCB watching the token stream', 'Prompt version stamped on the decision record', 'Token budget checked before call'] },
  { area: 'Any agent flow',              items: ['Agent-Loop CB with max depth + wall-clock', 'Tool allowlist per tenant/role', 'HITL escalation path defined', 'Kill-switch feature flag wired'] },
  { area: 'Any cache read/write',        items: ['Tenant-namespaced key', 'TTL set', 'Never cache PII responses', 'Invalidation path traced to source change'] },
  { area: 'Any new endpoint',            items: ['Pydantic response_model set', 'offset/limit if listing', 'Idempotency-Key if creating', 'Rate-limit bucket assigned', 'Correlation-ID propagated'] },
  { area: 'Any new service',             items: ['Health probe + readiness probe', 'Structured JSON logs', 'OTel instrumentation', 'Prometheus /metrics endpoint', 'Graceful shutdown hook', 'CODEOWNERS entry'] },
  { area: 'Any new event type',          items: ['CloudEvents envelope', 'JSON Schema in schemas/events/', 'DLQ path', 'Consumer idempotency', 'Producer via outbox (not direct)'] },
];

export default function CodeGovernance() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Code Governance — Admin &amp; Code-Manager View</h1>
        <p className="design-areas-sub">
          Every dimension an engineering manager, architect, or auditor needs to verify before the code
          goes to production. Each pillar has a concrete checklist, links to the in-repo evidence, and a
          canonical reference. The final section is a <strong>per-design-area checklist</strong> — use it as
          the PR-review filter.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
      </header>

      <div className="method-grid">
        {PILLARS.map((p) => (
          <article key={p.id} id={p.id} className="method-card">
            <div className="method-card-head">
              <h3 className="method-name">{p.title}</h3>
            </div>
            <p className="method-tagline">{p.summary}</p>
            <dl className="cb-card-dl">
              <dt>Flowchart</dt>
              <dd><Mermaid chart={buildFlowchart(p)} /></dd>
              <dt>Sequence diagram</dt>
              <dd><Mermaid chart={buildSequence(p)} /></dd>
              <dt>Network diagram</dt>
              <dd><Mermaid chart={buildNetwork(p)} /></dd>
              <dt>Step to implement</dt>
              <dd>
                <ol className="cg-checklist" style={{ paddingLeft: 18 }}>
                  {implementationSteps(p).map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </dd>
              <dt>Checklist</dt>
              <dd>
                <ul className="cg-checklist">
                  {p.checklist.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </dd>
              <dt>Core concept</dt>
              <dd>{p.coreConcept}</dd>
              <dt>Why it matters</dt>
              <dd>{p.whyItMatters}</dd>
              <dt>Challenges</dt>
              <dd>
                <ul className="cg-checklist">
                  {p.challenges.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </dd>
              <dt>Edge cases</dt>
              <dd>
                <ul className="cg-checklist">
                  {p.edgeCases.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </dd>
              <dt>Limitations</dt>
              <dd>
                <ul className="cg-checklist">
                  {p.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </dd>
              <dt>In-repo evidence</dt>
              <dd>
                <ul className="cg-evidence">
                  {p.evidence.map((e, i) => (
                    <li key={i}><code>{e}</code></li>
                  ))}
                </ul>
              </dd>
              <dt>Reference</dt>
              <dd>
                <a href={p.refUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                  {p.refLabel} ↗
                </a>
              </dd>
            </dl>
          </article>
        ))}
      </div>

      <section className="cg-per-design-section">
        <h2 className="design-areas-group-title">Per-Design-Area Review Checklist</h2>
        <p className="design-areas-sub">
          When a PR touches one of these design surfaces, the reviewer walks the matching checklist.
          If any item is missing, the PR is either fixed or deferred — never merged partial.
        </p>
        <table className="design-areas-table">
          <thead>
            <tr>
              <th className="da-col-name">Surface</th>
              <th>Mandatory checks</th>
            </tr>
          </thead>
          <tbody>
            {PER_DESIGN_CHECKLIST.map((row) => (
              <tr key={row.area}>
                <td className="da-col-name">{row.area}</td>
                <td>
                  <ul className="cg-checklist cg-inline">
                    {row.items.map((i, idx) => (
                      <li key={idx}>{i}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
