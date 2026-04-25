'use client';

/**
 * Python deep-dive — interview-grade explanations for the senior-level
 * Python topics that matter most in this codebase, using the user's
 * 7-lens template:
 *
 *   1. Core concept (one sentence)
 *   2. Why it matters
 *   3. Challenges
 *   4. Edge cases
 *   5. Solutions
 *   6. Limitations
 *   7. Where it fits in this project (anchored)
 *
 * Plus an "interview line" — a quotable senior-level sentence per topic.
 *
 * Static content. No mermaid required (unlike /admin/llmops/deep where
 * cross-component sequencing matters). Where flow matters (async
 * fan-out), an inline SVG handles it.
 */

import { useState } from 'react';

interface Topic {
  slug: string;
  level: 'core' | 'intermediate' | 'advanced' | 'backend' | 'rag' | 'project';
  title: string;
  coreConcept: string;
  whyItMatters: string;
  challenges: string[];
  edgeCases: string[];
  solutions: string[];
  limitations: string[];
  projectFit: string[];
  interviewLine: string;
}

const TOPICS: Topic[] = [
  {
    slug: 'async-await',
    level: 'advanced',
    title: '1. async / await + event loop',
    coreConcept: 'Single-threaded cooperative concurrency for IO-heavy systems. Coroutines yield at await points; the loop schedules other ready coroutines.',
    whyItMatters: 'Backends spend most wall-clock waiting on IO (DB, HTTP, MCP). Async lets one process serve thousands of concurrent requests without thread overhead — but only if every dependency in the hot path is async-safe.',
    challenges: [
      'Blocking call inside async path stalls the entire event loop',
      'Forgetting `await` gives back a coroutine object instead of a value',
      'Cancellation handling — CancelledError propagates and must be caught intentionally',
      'Shared mutable state across concurrent tasks (no GIL protection at await points)',
      'Task leaks — fire-and-forget tasks outliving request context',
    ],
    edgeCases: [
      'Sync DB/client call (e.g. `requests.get`) in an async handler blocks every other request',
      'One failing branch of `asyncio.gather` cancels all others — usually unwanted',
      'Background task started in a request context outlives the request and crashes on cleanup',
      'Mixing async and sync libraries: psycopg vs asyncpg, requests vs httpx',
    ],
    solutions: [
      'Use async-native libraries (asyncpg, httpx, redis.asyncio)',
      'Isolate blocking work in `asyncio.to_thread` or a process pool',
      'Pass `return_exceptions=True` to gather when partial failure is OK',
      'Bound concurrency with semaphores; never unbounded fan-out',
      'Track tasks via `asyncio.create_task` references, not fire-and-forget',
    ],
    limitations: [
      'asyncio is concurrency, NOT CPU scaling — heavy compute still pegs one core',
      'Stack traces span multiple suspends; harder to read than sync',
      'A single sync misuse silently degrades the entire service',
    ],
    projectFit: [
      'FastAPI handlers in every Python service',
      '`asyncio.gather` for parallel upstream probes (`/api/v1/health/upstreams`)',
      'MCP client calls + draft replay worker',
      '`drill_inference_health_upstreams` step 2 locks parallel-probe latency bound (5 probes < 2.5s)',
    ],
    interviewLine: 'Async helps throughput for IO-heavy backends, but only if every dependency in the hot path is async-safe. One sync call silently blocks the whole loop.',
  },
  {
    slug: 'decorators',
    level: 'advanced',
    title: '2. Decorators',
    coreConcept: 'A decorator wraps behaviour around a function — the cleanest place to put cross-cutting concerns (retries, tracing, auth, timing).',
    whyItMatters: 'Cross-cutting concerns shouldn\'t pollute every business function. Decorators centralise the "how" so business code stays about the "what."',
    challenges: [
      'Hidden control flow — readers miss what the decorator does',
      'Stacked decorators obscure execution order (innermost wraps first)',
      'Metadata loss without `functools.wraps` (`__name__`, `__doc__`, signature)',
      'Wrong layering — decorator in the wrong order swallows or duplicates effects',
    ],
    edgeCases: [
      'Retry decorator on a non-idempotent write (POST without idempotency key) → duplicate side effects',
      'Tracing decorator that catches + swallows exceptions — root cause lost',
      'Async function wrapped by a sync decorator silently returns a coroutine, never awaited',
      'Decorator that uses `time.time()` for retries instead of monotonic clock',
    ],
    solutions: [
      'Use decorators only for cross-cutting concerns (retry, tracing, auth, rate-limit)',
      'Always `functools.wraps(fn)` to preserve identity',
      'Separate sync and async decorator flavours; don\'t auto-detect',
      'Apply retry only to idempotent or idempotency-key-protected operations',
    ],
    limitations: [
      'Decorators are powerful for policy and observability, but dangerous if they hide business semantics',
      'Performance overhead per call — fine for HTTP boundaries, not for hot loops',
      'Hard to test in isolation when stacked',
    ],
    projectFit: [
      'Retry + breaker primitives in `libs/py/documind_core/circuit_breaker.py`',
      'OTel auto-instrumentation decorators on FastAPI / asyncpg / httpx',
      'Audit-write helpers in `libs/py/documind_core/audit.py`',
    ],
    interviewLine: 'Decorators are powerful for policy and observability, but dangerous if they hide business semantics. Retry + breaker + tracing — never business logic.',
  },
  {
    slug: 'context-managers',
    level: 'intermediate',
    title: '3. Context managers',
    coreConcept: 'Resource lifecycle control via `with` / `async with` — pair setup with guaranteed teardown even on exceptions.',
    whyItMatters: 'Connection pools, file handles, transactions, locks — every external resource needs predictable cleanup. A leaked DB connection drains the pool; a leaked file handle exhausts FDs.',
    challenges: [
      'Forgetting cleanup when not using `with`',
      'Nested resources (DB transaction inside HTTP client) need correct ordering',
      'Async vs sync mismatch — `async with` only works for `__aenter__`/`__aexit__`',
      'Exception swallow — `__exit__` returning True suppresses the raised exception',
    ],
    edgeCases: [
      'DB connection not released on exception — pool eventually exhausts',
      'Temporary security context (set_config tenant) not reset, leaking across requests',
      'Async client used in sync `with` raises TypeError at runtime',
      'Multiple managers — one fails to enter, others may not unwind',
    ],
    solutions: [
      'Use `with`/`async with` for every external resource without exception',
      '`contextlib.contextmanager` + `@asynccontextmanager` for inline managers',
      'Encapsulate setup/teardown in a single class — never split across functions',
      'Drill the leak path: open in test, abort, verify resource released',
    ],
    limitations: [
      'Context managers are local — distributed transactions need explicit two-phase commit',
      'No async-context-aware cancellation handling out of the box',
    ],
    projectFit: [
      '`db_client.tenant_connection(tenant_id)` — sets app.current_tenant for RLS, releases on exit',
      'asyncpg pool acquire/release',
      'httpx `AsyncClient` with `async with`',
      'OTel span scopes',
    ],
    interviewLine: 'Every external resource — connection, transaction, span, file — must live inside a context manager. Anything else is a leak waiting for production.',
  },
  {
    slug: 'exceptions',
    level: 'core',
    title: '4. Exceptions',
    coreConcept: 'Structured error path for invalid state, dependency failure, and policy rejection. Production code needs an exception taxonomy, not `raise Exception`.',
    whyItMatters: 'Half-formed exception design is the source of most "mysterious 500s." Different errors deserve different HTTP responses, different alerts, different retry policies.',
    challenges: [
      'Catching too broadly (`except Exception`) hides root cause',
      'Mixing business errors (validation, not-found) with infrastructure (timeout, 5xx)',
      'Retrying non-retryable exceptions (e.g. ValidationError)',
      'Bare `except:` swallowing CancelledError + KeyboardInterrupt',
    ],
    edgeCases: [
      '`except Exception:` swallows asyncio cancellation, leaks tasks',
      'Converting every error to 500 — clients can\'t differentiate retry-able from not',
      'Dependency timeout treated like validation failure (wrong status, wrong alert)',
      'Reraising loses original `__traceback__` if not done with `raise` (no name)',
    ],
    solutions: [
      'Build an exception hierarchy: `AppError` → `NotFoundError` / `ValidationError` / `ExternalServiceError` / `RateLimitedError`',
      'Map error class to HTTP status in middleware',
      'Catch specific exceptions; never `except Exception` without re-raise',
      'Preserve context: `raise X from y` for chaining',
      'Retry only known transient failures (TimeoutError, ConnectionError)',
    ],
    limitations: [
      'Exceptions show failure, not automatic recovery',
      'Stack traces become noisy in async paths (multiple frames per await)',
    ],
    projectFit: [
      '`libs/py/documind_core/exceptions.py` — AppError hierarchy',
      '`libs/py/documind_core/error_handlers.py` — class-to-status mapping',
      'CircuitBreaker uses ExternalServiceError to distinguish from policy denials',
    ],
    interviewLine: 'A production Python backend needs an exception taxonomy, not just `raise Exception`. The taxonomy is what tells the gateway whether to retry, alert, or surface to the user.',
  },
  {
    slug: 'typing-pydantic',
    level: 'backend',
    title: '5. Typing + Pydantic',
    coreConcept: 'Type hints help humans + tools (mypy, IDEs); Pydantic turns those contracts into runtime guarantees at API boundaries.',
    whyItMatters: 'Dynamic typing is fast to write but weak at runtime. Schema-first APIs catch malformed payloads at the boundary, not in the middle of business logic.',
    challenges: [
      'Drift between hints and reality (hints lie when not validated)',
      'Overcomplicated type signatures readers skip',
      'Weak validation at service boundaries — middle layers assume well-formed input',
      'Optional vs union types — `Optional[X]` is clearer than `X | None` for some readers',
    ],
    edgeCases: [
      'JSON payload shape mismatch silently ignored when types lie',
      'Optional field assumed present (`req.foo.upper()` on None)',
      'Union types create ambiguous error messages without discriminator',
      'Pydantic v1 vs v2 migration — behaviour differs subtly',
    ],
    solutions: [
      'Pydantic models for every request + response (`response_model=` on every route)',
      'Validate at boundaries — middle layers can trust',
      'Use `Field(...)` constraints (min_length, ge, le, regex) instead of post-validation',
      'Schema-first: define the model, let the type follow',
      'Run mypy in CI — drift becomes loud',
    ],
    limitations: [
      'Validation has runtime cost (negligible at HTTP boundaries, real in hot loops)',
      'Pydantic v2 changed defaults; old patterns break silently',
    ],
    projectFit: [
      'Every `services/*/app/schemas/__init__.py`',
      '`HealthDetailedResponse`, `HealthToolsResponse`, `TraceLinkResponse`, ...',
      'Pydantic Settings (`BaseServiceSettings`) for env-driven config',
    ],
    interviewLine: 'Type hints help humans and tools; Pydantic is what turns those contracts into runtime guarantees. Without runtime validation, types are documentation that lies.',
  },
  {
    slug: 'iterators-generators',
    level: 'intermediate',
    title: '6. Iterators + generators',
    coreConcept: 'Lazy data flow — produce values on demand instead of materializing a whole list. Crucial for streaming and memory-bounded processing.',
    whyItMatters: 'Loading 100K rows / chunks / events into memory is fine in scripts; in services it triggers OOMs and stalls. Generators keep memory flat.',
    challenges: [
      'One-time consumption surprises (consuming a generator twice yields nothing)',
      'Generator exceptions surface late, often in the consumer',
      'Debugging lazy pipelines is harder than eager — call stack obscures source',
      'Mixing `yield` with `return` confuses readers',
    ],
    edgeCases: [
      'Reusing a generator object after it\'s exhausted — silent empty result',
      'Streaming response generator fails mid-stream — client sees partial output',
      'Generator-based DB cursor closes early when consumer abandons it',
      'Backpressure — fast producer + slow consumer = unbounded queue',
    ],
    solutions: [
      'Document consumption semantics on every generator',
      'Wrap generators with explicit error-handling that surfaces on first call',
      'Use for streaming responses, large scans, and event processing',
      'Async generators (`async def` + `yield`) for streaming HTTP responses',
    ],
    limitations: [
      'Lazy evaluation is harder to reason about than eager',
      'Some libraries (numpy, pandas) want materialized data',
    ],
    projectFit: [
      'Streaming LLM responses (token-by-token via `async for`)',
      'Large retrieval scans without OOM',
      'Pagination cursors over Postgres results',
    ],
    interviewLine: 'Generators are useful when the result is large or progressive — streaming responses, big scans, memory-safe processing. The cost is harder debugging when something goes wrong in the middle of the stream.',
  },
  {
    slug: 'gil-concurrency-models',
    level: 'advanced',
    title: '7. GIL + threading vs multiprocessing vs asyncio',
    coreConcept: 'Pick the concurrency model based on workload type: asyncio for IO, threads for blocking-IO compatibility, processes for CPU-bound work.',
    whyItMatters: 'Wrong concurrency model is the #1 production scaling bug. Threading a CPU-bound parser doesn\'t help (GIL serializes it); using processes for tiny tasks pays IPC overhead for nothing.',
    challenges: [
      'Misunderstanding GIL — "Python threads don\'t parallelize" only applies to pure-Python execution',
      'Using threads for CPU-bound work — no speedup',
      'Process overhead too high for small tasks (fork + IPC = 10-100ms)',
      'Forked process misses parent\'s app state (DB pool, connection objects)',
    ],
    edgeCases: [
      'CPU-heavy parsing (PDF, Markdown) on the request path blocks the event loop',
      'Thread-safe assumptions fail (e.g. dict mutation during iteration in another thread)',
      '`multiprocessing.Pool` losing in-flight work on worker crash',
      'Mixing `asyncio.to_thread` and CPU work — thread is fine for blocking IO, useless for CPU',
    ],
    solutions: [
      'asyncio for IO-bound (most service work)',
      'Threads via `asyncio.to_thread` for blocking-IO libraries that aren\'t async-native',
      'multiprocessing for CPU-bound batch work (NOT request path)',
      'C extensions release the GIL — numpy/pandas operations are parallel-safe',
    ],
    limitations: [
      'Each model has its own debugging story; mixing them multiplies complexity',
      'Process pools cost real memory; not free to spin up',
    ],
    projectFit: [
      'asyncio: all FastAPI services',
      'threads: not currently used (no blocking-IO library in the hot path)',
      'multiprocessing: ingestion-svc could use it for parallel PDF parse (currently single-process)',
    ],
    interviewLine: 'The concurrency model should follow the workload: asyncio for IO, processes for CPU. Threading is the trap — most "I\'ll add threads" attempts at scaling Python services hit the GIL wall.',
  },
  {
    slug: 'classes-inheritance-mro',
    level: 'advanced',
    title: '8. Classes + inheritance + MRO',
    coreConcept: 'Classes encapsulate state + behaviour. Inheritance reuses base behaviour but increases coupling. MRO (`__mro__`) defines the lookup order for multiple inheritance.',
    whyItMatters: 'Service code drifts toward god classes and deep hierarchies if not disciplined. Composition over inheritance is the senior-level reflex.',
    challenges: [
      'Over-objectification — every dict becomes a class',
      'Hidden mutable state on class attributes (shared across instances)',
      'God classes that mix config, IO, and business policy',
      'Deep hierarchies — fragile base class problem',
      'MRO surprises in multiple inheritance / mixins',
    ],
    edgeCases: [
      'Service object holds request-specific state across requests',
      'Mutable class attribute (`_cache = {}`) shared unexpectedly',
      'Subclass overrides method that base class calls internally — fragile',
      'Diamond inheritance (mixin overlap) → MRO not what reader expects',
    ],
    solutions: [
      'Prefer composition over inheritance unless contract is small + stable',
      'Dependency injection via constructor — services hold collaborators, not state',
      'Stateless service + stateful store/client split',
      'Use ABCs / Protocols for stable contracts (e.g. `IdempotencyStore`)',
      'Always use instance attributes (`self._cache = {}` in `__init__`), never class',
    ],
    limitations: [
      'Composition can be more verbose than inheritance for short hierarchies',
      'Type-checking with deep inheritance is slow in mypy',
    ],
    projectFit: [
      '`AppError` hierarchy in `exceptions.py` — small, stable',
      '`Repository` base class in `documind_core.db_client`',
      '`IdempotencyStore` Protocol — duck-typed contract',
      'AgentService composed of MCPClient + RagInferenceService — composition not inheritance',
    ],
    interviewLine: 'For service code, composition is usually safer than inheritance unless I\'m defining a small, stable contract. The fragile-base-class problem is real — every level of inheritance is a constraint on every subclass.',
  },
  {
    slug: 'fastapi-middleware',
    level: 'backend',
    title: '9. FastAPI patterns + middleware',
    coreConcept: 'Route → service → repository/store separation. Middleware handles cross-cutting concerns (auth, correlation, tenant) BEFORE the route runs.',
    whyItMatters: 'Thin routes + thick services scales; thick routes + DB-in-handler doesn\'t. Middleware order is load-bearing — get it wrong and rate limit fires before auth, or correlation IDs leak across requests.',
    challenges: [
      'Route handlers grow too large; business logic creeps in',
      'Dependencies sprawl — `Depends()` chains 5 deep',
      'Middleware order is invisible until something breaks',
      'Hidden request mutation in middleware confuses route handlers',
      'Async ⇄ sync mismatches (sync DB call in async route)',
    ],
    edgeCases: [
      'Route directly touches DB and external API — un-testable',
      'Error mapping inconsistent across endpoints (some 500, some 400)',
      'Tenant context middleware after rate limit → rate limited per IP not per tenant',
      'Correlation ID overwritten by upstream middleware',
    ],
    solutions: [
      'Routes stay HTTP-only; services own workflow; repositories own SQL',
      '`response_model=` on every route',
      'Pydantic models for every request body',
      'Middleware order: SecurityHeaders → CorrelationId → TenantContext → Auth → RateLimit',
      'Use `Depends()` factories from `core/dependencies.py`',
    ],
    limitations: [
      'FastAPI middleware uses ASGI BaseHTTPMiddleware which isn\'t streaming-friendly',
      'Dependency injection is shallow — no scopes beyond request',
    ],
    projectFit: [
      'Every Python service follows route → service → repo split',
      '`libs/py/documind_core/middleware.py` — shared middleware stack',
      'CorrelationIdMiddleware threads `X-Correlation-ID` through every request',
    ],
    interviewLine: 'Routes should be the thinnest layer that does HTTP shape; services should hold the workflow; repositories own SQL. Anything else makes routes un-testable.',
  },
  {
    slug: 'http-pool-retry-breaker',
    level: 'backend',
    title: '10. Async HTTP clients + pooling + retries + breakers + idempotency',
    coreConcept: 'Reliability primitives around external dependencies: pooled clients, bounded retries, circuit breakers around flaky deps, idempotency keys for write paths.',
    whyItMatters: 'Most production incidents are dependency failures cascading. The four primitives (pool, retry, breaker, idempotency) compose into a coherent reliability story.',
    challenges: [
      'Per-request client creation — connection setup cost on every call',
      'No timeout — slow upstream wedges the request indefinitely',
      'Connection leaks under load',
      'Retrying non-idempotent operations duplicates side effects',
      'Breaker + retry fighting each other (retry storms during outage)',
    ],
    edgeCases: [
      'Downstream succeeded but response lost — client retries, write happens twice',
      'Retry storm during incident — every client retries simultaneously, kills the recovering dep',
      'Breaker open during half-open probe → permanent stuck-open',
      'Idle connection in pool stale — first request after quiet period 5xx',
    ],
    solutions: [
      'Long-lived `httpx.AsyncClient` per service; never per-request',
      'Explicit timeout on every call (connect + read separately)',
      'Bounded retries with exponential backoff + jitter',
      'CircuitBreaker around flaky dependencies — fail fast when open',
      'Idempotency keys for write operations (POST `Idempotency-Key` header)',
      'Durable draft fallback when breaker is open',
    ],
    limitations: [
      'Idempotency requires storage (we use Postgres-backed `governance.mcp_idempotency`)',
      'Breaker state is per-process — multi-replica deployments need shared state (ADR-016 planned)',
    ],
    projectFit: [
      '`libs/py/documind_core/circuit_breaker.py` — unified breaker',
      '`mcp/idempotency.py` — IdempotencyStore protocol + Postgres impl',
      'Transport breakers around Qdrant + Neo4j (ADR-008)',
      'MCPClient wraps tool calls with breaker + retry + idempotency',
    ],
    interviewLine: 'Retries improve transient reliability; idempotency protects correctness; breakers protect the whole system. The three only work as a system — any one alone leaves a class of failures uncovered.',
  },
  {
    slug: 'observability-python',
    level: 'backend',
    title: '11. Structured logging + tracing + metrics',
    coreConcept: 'Three observability surfaces — logs (event detail), traces (causal chains), metrics (aggregate signals) — joined by correlation_id.',
    whyItMatters: 'Production debugging without these is anecdote. Distributed systems fragment evidence; the three surfaces reconnect it via shared context.',
    challenges: [
      'Too much noise — high-cardinality log lines drown signal',
      'Missing correlation IDs break the join',
      'High-cardinality Prometheus labels (e.g. tenant_id) blow up storage',
      'Traces without business meaning are decorative',
      'Sampling tradeoffs — sample too low, lose interesting requests',
    ],
    edgeCases: [
      'Frontend error can\'t link to backend trace (no shared cid)',
      'Latency issue with no error logs — symptom without cause',
      'One tenant floods metric labels → cardinality explosion',
      'Tracing wrapper catches + swallows exception — span shows ok=true on real failure',
    ],
    solutions: [
      'Structured JSON logs with `correlation_id`, `tenant_id`, `service`',
      'Bounded label sets — closed enums (per ADR-010)',
      'Custom OTel spans on critical workflows (guardrail.check, agent.tool)',
      'Same correlation_id across log + span + audit',
      'Sample at 100% for /agent/ask + critical paths; 10% for everything else',
    ],
    limitations: [
      'Observability shows symptoms, not root cause intelligence',
      'Sampling tradeoffs constrain what you can debug retroactively',
    ],
    projectFit: [
      '`libs/py/documind_core/observability.py` — OTel + Prometheus setup',
      '`logging_config.py` — JSON formatter with correlation_id',
      'Per-tool latency histogram + scope-denial counter (commits 598ca9a, 307cbc9)',
      'Guardrail span attributes (commit ada94b9)',
    ],
    interviewLine: 'Operational observability is strong when you can explain latency, failure, degradation, and recovery with evidence. Three surfaces, one correlation_id — that\'s the spine.',
  },
  {
    slug: 'rag-python',
    level: 'rag',
    title: '12. RAG-specific Python (chunking + embeddings + streaming)',
    coreConcept: 'RAG quality is downstream of data lifecycle. Token-aware chunking, versioned embeddings, streaming responses — each layer protects answer quality.',
    whyItMatters: 'A great model on bad context produces confidently wrong answers. The Python layers around the model — parsing, chunking, embedding, retrieval, post-processing — determine answer quality more than the model itself.',
    challenges: [
      'Chunk too small loses context; chunk too large reduces precision',
      'Embedding drift — model upgrade silently changes recall',
      'Repeated boilerplate (TOC, headers) pollutes retrieval',
      'Multilingual content needs language-aware chunking',
      'Streaming responses fail mid-stream — client sees partial output',
    ],
    edgeCases: [
      'Scanned PDF noise after OCR',
      'Tables/charts poorly represented as flat text',
      'New embedding model against old index — recall collapses',
      'Duplicate content flooding retrieval',
      'Missing tenant filter exposes wrong tenant\'s chunks',
    ],
    solutions: [
      'Token-aware chunking with overlap (256-1024 tokens, 10-20% overlap)',
      'Boilerplate stripping per document type',
      'Version embeddings + index; rebuild on model bump',
      'Strict per-tenant metadata filters + tenant-scoped collections',
      'Async generators for streaming responses',
      'Citation grounding via GuardrailChecker',
    ],
    limitations: [
      'Chunking is heuristic, not algorithmically optimal',
      'Embedding versioning isn\'t fully governed yet (open scorecard row)',
      'Retrieval quality is itself heuristic — RAG benchmarks are imperfect',
    ],
    projectFit: [
      'ingestion-svc: parse → chunk → embed pipeline',
      'retrieval-svc: hybrid vector + graph + cache (ADR-008 transport breakers)',
      'inference-svc: prompt assembly + GuardrailChecker',
      'Streaming responses via async generators',
      '`drill_retrieval_tenant_isolation` locks per-tenant filtering',
    ],
    interviewLine: 'Answer quality is downstream of retrieval quality, which is downstream of chunking quality. The Python layers around the model matter more than the model itself for enterprise RAG.',
  },
];

const LEVELS: Record<Topic['level'], { title: string; tone: string }> = {
  core: { title: 'Core', tone: '#1e3a8a' },
  intermediate: { title: 'Intermediate', tone: '#0d9488' },
  advanced: { title: 'Advanced', tone: '#7c2d12' },
  backend: { title: 'Backend engineering', tone: '#475569' },
  rag: { title: 'RAG-specific', tone: '#b45309' },
  project: { title: 'Project pattern', tone: '#065f46' },
};

function TopicSection({ t }: { t: Topic }) {
  return (
    <article id={t.slug} className="card" style={{ marginBottom: 32 }}>
      <header style={{ marginBottom: 12 }}>
        <h2 className="section-title" style={{ marginBottom: 6 }}>
          {t.title}{' '}
          <span
            className="badge"
            style={{ backgroundColor: LEVELS[t.level].tone, color: '#ffffff' }}
          >
            {LEVELS[t.level].title}
          </span>
        </h2>
        <p style={{ fontStyle: 'italic', color: '#374151' }}>{t.coreConcept}</p>
      </header>

      <div style={{ marginBottom: 12 }}>
        <strong>Why it matters</strong>
        <p style={{ marginTop: 4 }}>{t.whyItMatters}</p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
          <strong>Challenges</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.challenges.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
          <strong>Solutions</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.solutions.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
          <strong>Edge cases</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.edgeCases.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#f3f4f6' }}>
          <strong>Limitations</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.limitations.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <strong>Where it fits in this project</strong>
        <ul style={{ marginTop: 4, paddingLeft: 18 }}>
          {t.projectFit.map((p, i) => (
            <li key={i}>
              <code style={{ fontSize: 13 }}>{p}</code>
            </li>
          ))}
        </ul>
      </div>

      <div
        className="card"
        style={{ padding: 12, backgroundColor: '#dbeafe', borderColor: '#1e3a8a' }}
      >
        <strong>Interview line</strong>
        <p style={{ margin: '6px 0 0 0', fontStyle: 'italic' }}>
          &ldquo;{t.interviewLine}&rdquo;
        </p>
      </div>
    </article>
  );
}

export default function PythonDeepPage() {
  const [search, setSearch] = useState('');
  const [activeLevel, setActiveLevel] = useState<'all' | Topic['level']>('all');

  const filtered = TOPICS.filter((t) => {
    if (activeLevel !== 'all' && t.level !== activeLevel) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        t.title.toLowerCase().includes(q)
        || t.coreConcept.toLowerCase().includes(q)
        || t.whyItMatters.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Python deep dive — interview-grade explanations</h1>
          <p className="page-subtitle">
            Senior-level Python topics that matter most in this codebase, using the 7-lens template:
            core concept · why it matters · challenges · edge cases · solutions · limitations ·
            where it fits · interview line.
          </p>
        </div>
      </div>

      {/* TOC */}
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18, columnCount: 2, columnGap: 24 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>
                {t.title}
              </a>{' '}
              <span
                className="badge"
                style={{
                  backgroundColor: LEVELS[t.level].tone,
                  color: '#ffffff',
                  fontSize: 11,
                }}
              >
                {LEVELS[t.level].title}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Filter */}
      <div
        className="card"
        style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="field-help">Level</span>
          <select
            value={activeLevel}
            onChange={(e) =>
              setActiveLevel(e.target.value as 'all' | Topic['level'])
            }
            style={{
              padding: '4px 8px',
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          >
            <option value="all">all</option>
            {(Object.keys(LEVELS) as Topic['level'][]).map((l) => (
              <option key={l} value={l}>
                {LEVELS[l].title}
              </option>
            ))}
          </select>
        </label>
        <input
          type="text"
          placeholder="search topic / core concept / why-it-matters"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search Python topics"
          style={{
            flex: '1 1 240px',
            padding: '6px 10px',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: 13,
          }}
        />
        <span className="field-help">
          {filtered.length} of {TOPICS.length}
        </span>
      </div>

      {filtered.map((t) => (
        <TopicSection key={t.slug} t={t} />
      ))}

      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Final senior-level summary</strong>
        <p style={{ marginTop: 8, fontStyle: 'italic' }}>
          &ldquo;We use Python not just as a scripting language but as the
          service runtime for async APIs, governed workflows, RAG
          orchestration, audit, and resilience patterns. The key senior
          skill is not memorizing syntax; it is understanding mutability,
          async behaviour, validation, error taxonomy, and lifecycle
          control under production constraints.&rdquo;
        </p>
      </div>
    </>
  );
}
