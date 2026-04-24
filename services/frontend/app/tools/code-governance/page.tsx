import Link from 'next/link';

export const metadata = { title: 'Code Governance — DocuMind' };

type Pillar = {
  id: string;
  title: string;
  summary: string;
  checklist: string[];
  evidence: string[];
  refUrl: string;
  refLabel: string;
};

const PILLARS: Pillar[] = [
  {
    id: 'standards',
    title: 'Code Standards & Guidelines',
    summary:
      'Mechanical standards enforced by tools, not reviewers. If the linter says no, it means no.',
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
    checklist: [
      'PR description explains WHY, not just what',
      'At least one approval from CODEOWNERS for the touched directory',
      'Security-tagged paths (auth, RLS, encryption, prompts) need a second reviewer from the security group',
      'CI must be green: lint, unit tests, mypy, build, smoke E2E',
      'If the diff touches a migration: explicit rollback plan in description',
      'No merge commits on main; rebase-and-squash only',
      'Reviewer checks: tests added/updated, docs touched, .env.template updated, no secrets committed',
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
    checklist: [
      'Shared primitives live in libs/py/documind_core/ (never duplicated per service)',
      'DI via FastAPI Depends — every repo and service is constructor-injected',
      'Interfaces behind every external dep (VectorSearcher, GraphSearcher, Chunker, Embedder)',
      'Frontend components live in services/frontend/components/ when used in 2+ places',
      'Hooks in services/frontend/hooks/ when logic is shared across components',
      'No copy-pasted migrations — each is numbered once, idempotent',
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
    checklist: [
      'Correlation-ID injected at the gateway, propagated through every hop',
      'JSON structured logs via structlog — never print()',
      'OTel traces on every inter-service call; Jaeger always-on in dev',
      '?debug=true query flag exposes CCB snapshot + breaker states in the response',
      'Every exception logs with the full context dict, not just the message',
      'No bare `except:`; specific exception types or re-raise',
      'Key metrics exported to Prometheus with bounded labels (no tenant_id in metric labels)',
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
    checklist: [
      'File-level docstring on every module: purpose, why this exists, design tradeoff',
      'Class-level docstring: responsibilities + constructor args + failure modes',
      'No comments that paraphrase the next line of code',
      'Non-obvious regex, thresholds, magic numbers: inline comment with the rationale',
      'Every ADR (Architecture Decision Record) captured in docs/architecture/ADRs/',
      'Every tool in /tools has a first-person Interview tab explaining rationale in plain English',
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
    checklist: [
      'AppError hierarchy in documind_core/exceptions.py (NotFoundError, ValidationError, PolicyViolationError, CircuitOpenError, …)',
      'Services raise AppError subclasses; routers translate to HTTP in one place (error_handlers.py)',
      'No raw `except:` — specific types or re-raise with context',
      'Every external call wrapped in CircuitBreaker (fail-fast, not hang)',
      'Background tasks MUST set a failed-job status on exception; never die silently',
      'DLQ for events that fail N times',
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
    checklist: [
      'Logs: JSON, timestamp UTC, correlation_id, tenant_id (never PII in message body)',
      'Traces: OTel spans on every boundary crossing; parent-child properly propagated',
      'Metrics: Prometheus counters/gauges/histograms; bounded cardinality',
      'Observability CB wraps every exporter — dead telemetry NEVER blocks user requests',
      'ELK for log search; Jaeger for traces; Grafana dashboards per SLO',
      'Sampling policy: 100% errors, 10% normal traffic, 100% slow (p99+)',
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
    checklist: [
      '`make lint` — ruff + black + mypy + tsc + next lint + golangci-lint',
      '`make test` — pytest (matrix per service) + vitest (frontend)',
      '`make build` — docker build per service + next build',
      '`make migrate` — applies all migrations in order',
      '`make smoke` — spins up compose, hits /health on every service',
      'CI matrix: lint → test → build → e2e → security scan (pip-audit, bandit, npm audit)',
      'Required status checks: every PR blocks on green CI',
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
    checklist: [
      'Conventional Commits: feat/fix/chore/docs/refactor/test',
      'feature/* branches from main; PR back to main; rebase-and-squash',
      'No force-push to main (protected branch)',
      'Every PR template: summary, test plan, rollback plan',
      'CODEOWNERS enforces reviewer group per directory',
      'Semantic versioning for public artifacts; CHANGELOG.md kept in lockstep',
      'Dependencies pinned with a range; lockfile committed; Dependabot opens weekly PR',
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
              <dt>Checklist</dt>
              <dd>
                <ul className="cg-checklist">
                  {p.checklist.map((c, i) => (
                    <li key={i}>{c}</li>
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
