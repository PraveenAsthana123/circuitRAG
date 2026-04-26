import Link from 'next/link';

export const metadata = { title: 'Python syllabus — DocuMind' };

type Status = 'shipped' | 'partial' | 'todo';

type Topic = {
  name: string;
  blurb: string;
  status: Status;
  href?: string;
};

type Category = {
  heading: string;
  intro: string;
  topics: Topic[];
};

// Status mapping: where the deeper content lives, or TODO if not yet
// covered. Anchors point at /admin/python/deep#<slug> where they
// already exist; otherwise to the closest related deep dive.
const CATEGORIES: Category[] = [
  {
    heading: 'Intermediate Python concepts',
    intro: 'The 15 idioms every backend Pythonista uses daily.',
    topics: [
      { name: 'List / dict / set comprehensions', blurb: 'Inline iterable transforms; performance vs readability.', status: 'todo' },
      { name: 'Iterators', blurb: 'Lazy data flow via __iter__ + __next__.', status: 'partial', href: '/admin/python/deep#iterators-generators' },
      { name: 'Generators', blurb: 'Yield-based lazy producers; memory-bounded streaming.', status: 'partial', href: '/admin/python/deep#iterators-generators' },
      { name: 'Decorators', blurb: 'Wrap behavior around functions: retries, tracing, auth, timing.', status: 'shipped', href: '/admin/python/deep#decorators' },
      { name: 'Context managers', blurb: 'Resource lifecycle with `with`/`async with` — guaranteed teardown.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: 'Lambda functions', blurb: 'Single-expression anonymous callables; sort/key/map idioms.', status: 'todo' },
      { name: 'Closures', blurb: 'Function captures enclosing scope; powers decorators + factories.', status: 'todo' },
      { name: '*args and **kwargs', blurb: 'Variadic argument capture + forwarding.', status: 'todo' },
      { name: 'Unpacking', blurb: 'Tuple/list/dict destructuring; star + double-star patterns.', status: 'todo' },
      { name: 'enumerate / zip / map / filter', blurb: 'Functional iteration helpers.', status: 'todo' },
      { name: 'Dataclasses', blurb: 'Boilerplate-free value objects via @dataclass.', status: 'todo' },
      { name: 'Properties', blurb: 'Attribute access via descriptors; @property + .setter.', status: 'todo' },
      { name: 'Class methods + static methods', blurb: '@classmethod for alt-constructors; @staticmethod for namespace-only.', status: 'todo' },
      { name: 'Abstract base classes', blurb: 'abc.ABC + @abstractmethod for pluggable interfaces.', status: 'todo' },
      { name: 'Typing basics', blurb: 'Type hints, Optional, Union — humans + tools win.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
    ],
  },
  {
    heading: 'Advanced Python language / runtime',
    intro: 'How Python runs under the hood — needed for every senior + architect interview.',
    topics: [
      { name: 'async / await', blurb: 'Cooperative concurrency for IO-heavy systems.', status: 'shipped', href: '/admin/python/deep#async-await' },
      { name: 'Coroutines', blurb: 'Suspendable functions; `await` is the suspension point.', status: 'partial', href: '/admin/python/deep#async-await' },
      { name: 'Event loop', blurb: 'Scheduler that picks next ready coroutine.', status: 'partial', href: '/admin/python/deep#async-await' },
      { name: 'asyncio task orchestration', blurb: 'gather, wait, as_completed, TaskGroups (3.11+).', status: 'partial', href: '/admin/python/deep#async-await' },
      { name: 'Concurrency vs parallelism', blurb: 'Coroutines vs threads vs processes — pick by workload type.', status: 'partial', href: '/admin/python/deep#gil-concurrency-models' },
      { name: 'Threading', blurb: 'Concurrent IO; bounded by GIL for CPU work.', status: 'partial', href: '/admin/python/deep#gil-concurrency-models' },
      { name: 'Multiprocessing', blurb: 'True parallelism for CPU-bound; IPC + fork costs.', status: 'partial', href: '/admin/python/deep#gil-concurrency-models' },
      { name: 'Futures + executors', blurb: 'concurrent.futures abstraction over thread/process pools.', status: 'todo' },
      { name: 'GIL', blurb: 'Global Interpreter Lock — bytecode-level mutex.', status: 'shipped', href: '/admin/python/deep#gil-concurrency-models' },
      { name: 'Descriptors', blurb: '__get__ / __set__ / __delete__ — how properties + ORMs work.', status: 'todo' },
      { name: 'Metaclasses', blurb: 'type() of types — class creation hooks.', status: 'todo' },
      { name: 'MRO', blurb: 'Method Resolution Order via C3 linearization.', status: 'shipped', href: '/admin/python/deep#classes-inheritance-mro' },
      { name: 'Dunder methods', blurb: 'Double-underscore protocols — __init__, __call__, etc. See category 3.', status: 'partial' },
      { name: 'Callable objects', blurb: 'Anything with __call__; functions, classes, instances.', status: 'todo' },
      { name: 'Advanced exception modeling', blurb: 'AppError hierarchy + raise X from y; retry-able vs not.', status: 'shipped', href: '/admin/python/deep#exceptions' },
      { name: 'Memory model + object lifecycle', blurb: 'Refcounting + cycle detector; __del__ caveats.', status: 'todo' },
      { name: 'Garbage collection', blurb: 'gc module; cyclic collector; debugging leaks.', status: 'todo' },
      { name: 'Weak references', blurb: 'weakref for caches that don\'t prevent GC.', status: 'todo' },
      { name: 'Import system behavior', blurb: 'sys.modules, finders, loaders; circular import gotchas.', status: 'todo' },
    ],
  },
  {
    heading: 'Dunder methods (especially relevant)',
    intro: 'The protocol layer Python exposes. Knowing these gives you tools + ORMs + iterators for free.',
    topics: [
      { name: '__init__', blurb: 'Instance initialization (NOT instance creation).', status: 'todo' },
      { name: '__new__', blurb: 'Instance creation; rare; used for immutables + metaclasses.', status: 'todo' },
      { name: '__call__', blurb: 'Make an instance callable.', status: 'todo' },
      { name: '__repr__', blurb: 'Unambiguous developer-facing repr; eval-able if possible.', status: 'todo' },
      { name: '__str__', blurb: 'User-facing string; falls back to __repr__.', status: 'todo' },
      { name: '__iter__ / __next__', blurb: 'Iterator protocol.', status: 'partial', href: '/admin/python/deep#iterators-generators' },
      { name: '__enter__ / __exit__', blurb: 'Context manager protocol.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: '__aenter__ / __aexit__', blurb: 'Async context manager protocol.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: '__getattr__', blurb: 'Fallback attribute access.', status: 'todo' },
      { name: '__getattribute__', blurb: 'Always-run attribute access; rare; powers descriptors.', status: 'todo' },
      { name: '__setattr__', blurb: 'Intercept assignment; powers Pydantic + immutable types.', status: 'todo' },
      { name: '__getitem__', blurb: 'obj[key] access; needed for sequence/mapping protocol.', status: 'todo' },
      { name: '__setitem__', blurb: 'obj[key] = value assignment.', status: 'todo' },
      { name: '__len__', blurb: 'len(obj); also makes obj truthy if non-zero.', status: 'todo' },
      { name: '__bool__', blurb: 'Custom truthiness; falls back to __len__.', status: 'todo' },
      { name: 'Equality + hashing dunders', blurb: '__eq__, __hash__, __ne__; required for set/dict keys.', status: 'todo' },
    ],
  },
  {
    heading: 'Typing + schema design',
    intro: 'Type hints + Pydantic — runtime guarantees at API boundaries.',
    topics: [
      { name: 'Type hints', blurb: 'PEP 484+; mypy + IDE awareness.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Union types', blurb: 'X | Y (3.10+) or Union[X, Y].', status: 'partial', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Optional types', blurb: 'X | None — explicit nullability.', status: 'partial', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Generics', blurb: 'TypeVar + Generic[T] — reusable polymorphic types.', status: 'todo' },
      { name: 'Type variables', blurb: 'TypeVar bounds + variance.', status: 'todo' },
      { name: 'Protocols', blurb: 'Structural subtyping (PEP 544) — duck typing with type-checking.', status: 'todo' },
      { name: 'TypedDict', blurb: 'Dict with named keys — for legacy dict APIs.', status: 'todo' },
      { name: 'Pydantic models', blurb: 'Runtime validation at API boundaries; v2 is fast.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Runtime validation vs static typing', blurb: 'mypy catches at lint; Pydantic catches at request — both needed.', status: 'partial', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Schema-first API design', blurb: 'Pydantic models drive request/response; OpenAPI auto-generated.', status: 'shipped', href: '/admin/techlead/deep#cross-team-api-contract' },
    ],
  },
  {
    heading: 'Backend engineering Python',
    intro: 'Production patterns this repo uses across every service.',
    topics: [
      { name: 'FastAPI patterns', blurb: 'Thin routers, response_model, lifespan hooks.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Request / response modeling', blurb: 'Pydantic schemas + SuccessResponse / ErrorResponse envelopes.', status: 'shipped', href: '/admin/techlead/deep#cross-team-api-contract' },
      { name: 'Dependency injection', blurb: 'Depends() factories for repos + services.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Middleware', blurb: 'CorrelationId + auth + rate-limit + security headers.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Async HTTP clients', blurb: 'httpx.AsyncClient with timeout + pool + retry.', status: 'shipped', href: '/admin/python/deep#http-pool-retry-breaker' },
      { name: 'Database clients', blurb: 'asyncpg + tenant_connection() context manager.', status: 'shipped', href: '/admin/database/deep#postgres-rls' },
      { name: 'Connection pooling', blurb: 'asyncpg pool sized to (services × workers × concurrency).', status: 'shipped', href: '/admin/database/deep#postgres-rls' },
      { name: 'Retries', blurb: 'Exponential backoff + jitter; only on retry-able errors.', status: 'shipped', href: '/admin/python/deep#http-pool-retry-breaker' },
      { name: 'Timeouts', blurb: 'Always set; HTTP, DB, subprocess, background tasks.', status: 'shipped', href: '/admin/python/deep#http-pool-retry-breaker' },
      { name: 'Circuit breakers', blurb: 'Generic + Retrieval + Token + Agent + CCB.', status: 'shipped', href: '/admin/breakers/deep' },
      { name: 'Idempotency', blurb: 'X-Idempotency-Key + IdempotencyStore; safe retries.', status: 'shipped', href: '/admin/techlead/deep#cross-team-api-contract' },
      { name: 'Structured logging', blurb: 'JsonFormatter + correlation_id + UTC.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Tracing instrumentation', blurb: 'OTel spans with tenant_id + correlation_id.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Metrics emission', blurb: 'Prometheus client; latency + breaker state + audit fail count.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Configuration management', blurb: 'Pydantic BaseSettings; env-driven; no os.environ.get.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Env-driven setup', blurb: '.env.template; secrets via Vault, not files.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Secrets handling', blurb: 'Vault / AWS Secrets; rotation; never in code.', status: 'partial', href: '/admin/sso/deep#sso-saml-oidc' },
    ],
  },
  {
    heading: 'Python concepts heavily used in RAG',
    intro: 'The Python primitives every RAG implementation lives or dies on.',
    topics: [
      { name: 'Text preprocessing', blurb: 'Tokenize, normalize, language detect.', status: 'partial', href: '/admin/data/deep' },
      { name: 'Chunking logic', blurb: 'Token-aware splitting with overlap.', status: 'shipped', href: '/admin/rag/deep#chunking' },
      { name: 'Token-aware splitting', blurb: 'Use tiktoken / model tokenizer; 256-1024 tokens, 10-20% overlap.', status: 'shipped', href: '/admin/rag/deep#chunking' },
      { name: 'Embedding client integration', blurb: 'Versioned wrapper; batch calls; retry on failure.', status: 'shipped', href: '/admin/rag/deep#embedding' },
      { name: 'Vector DB client usage', blurb: 'QdrantRepo with tenant_id required.', status: 'shipped', href: '/admin/database/deep#qdrant' },
      { name: 'Metadata filtering', blurb: 'must.tenant_id payload filter on every search.', status: 'shipped', href: '/admin/database/deep#qdrant' },
      { name: 'Reranking pipelines', blurb: 'Cross-encoder top-20 → top-5.', status: 'shipped', href: '/admin/rag/deep#post-retrieval' },
      { name: 'Retrieval orchestration', blurb: 'Hybrid (vector + graph + cache) with breakers.', status: 'shipped', href: '/admin/rag/deep#hybrid-retrieval' },
      { name: 'Prompt assembly', blurb: 'Template + chunks + citations; token budget.', status: 'partial', href: '/admin/llmops/deep#prompt-registry' },
      { name: 'Response post-processing', blurb: 'Strip + cite + redact + audit.', status: 'partial', href: '/admin/guardrails/deep' },
      { name: 'Citation packaging', blurb: 'Link chunk_id → doc_id + page; surface to UI.', status: 'shipped', href: '/admin/rag/deep#post-retrieval' },
      { name: 'Caching', blurb: 'Redis tenant-prefixed; TTL-aware.', status: 'shipped', href: '/admin/database/deep#redis' },
      { name: 'Background indexing jobs', blurb: 'Saga: parse → chunk → embed → index → stamp.', status: 'partial', href: '/admin/microservices/deep' },
      { name: 'Batching', blurb: 'Embed N at a time; balance latency vs throughput.', status: 'partial', href: '/admin/rag/deep#embedding' },
      { name: 'Error handling around model calls', blurb: 'Timeout + retry + breaker + degrade.', status: 'shipped', href: '/admin/python/deep#exceptions' },
      { name: 'Latency budgeting', blurb: 'p99 SLA broken down per step.', status: 'partial', href: '/admin/architect/deep' },
      { name: 'Fallback logic', blurb: 'Smaller model + cached response + degraded flag.', status: 'shipped', href: '/admin/breakers/deep' },
    ],
  },
  {
    heading: 'Advanced Python in RAG systems',
    intro: 'Where async + decorators + typing land in real RAG code.',
    topics: [
      { name: 'Async fan-out for retrieval/model calls', blurb: 'asyncio.gather across vector + graph + cache.', status: 'partial', href: '/admin/python/deep#async-await' },
      { name: 'Concurrency control for embeddings/search', blurb: 'Semaphore-bounded fan-out.', status: 'todo' },
      { name: 'Context managers for clients/resources', blurb: '__aenter__/__aexit__ for pool acquisition.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: 'Decorators for retries, tracing, rate limiting', blurb: '@retry, @traced, @rate_limit composable.', status: 'partial', href: '/admin/python/deep#decorators' },
      { name: 'Dataclasses or Pydantic for chunk/query/result models', blurb: 'Pydantic at API boundary; dataclasses internal.', status: 'partial', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Generators for streaming responses', blurb: 'AsyncIterator yields token chunks.', status: 'partial', href: '/admin/python/deep#iterators-generators' },
      { name: 'Typed interfaces for retrievers/rerankers/providers', blurb: 'Protocol + ABC for plugin shape.', status: 'todo' },
      { name: 'Caching abstractions', blurb: 'Cache.tenant_key(t, k) signature.', status: 'shipped', href: '/admin/database/deep#redis' },
      { name: 'Plugin-style architecture for model/vector providers', blurb: 'Pluggable Embedder, VectorSearcher, GraphSearcher.', status: 'partial', href: '/admin/architect/deep' },
      { name: 'Serialization/deserialization for documents and metadata', blurb: 'JSON + msgpack + Pydantic.', status: 'todo' },
    ],
  },
  {
    heading: 'Python concepts especially used in this project pattern',
    intro: 'Patterns specific to DocuMind\'s architecture.',
    topics: [
      { name: 'Async service entrypoints', blurb: 'main.py with FastAPI() + lifespan.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'FastAPI app lifecycle hooks', blurb: 'lifespan ctx manager; startup + shutdown.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Shared library patterns under libs/py', blurb: 'documind_core: db, breakers, cache, audit shared.', status: 'shipped', href: '/admin/architect/deep' },
      { name: 'Client wrapper classes', blurb: 'QdrantRepo, RedisRepo, KafkaProducer; tenant_id at boundary.', status: 'shipped', href: '/admin/database/deep#qdrant' },
      { name: 'Circuit breaker abstraction', blurb: 'Generic CB + state machine + decorators.', status: 'shipped', href: '/admin/breakers/deep' },
      { name: 'Rate limiter abstraction', blurb: 'Per-tenant + per-IP; Redis-backed.', status: 'partial', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Audit / event helpers', blurb: 'audit.log_decision() with hash-chain.', status: 'shipped', href: '/admin/database/deep#postgres-rls' },
      { name: 'Draft persistence models', blurb: 'action_drafts state machine with CHECK constraints.', status: 'shipped', href: '/admin/database/deep#postgres-rls' },
      { name: 'Replay worker logic', blurb: 'Tail outbox; retry stuck sagas; bounded.', status: 'partial', href: '/admin/microservices/deep' },
      { name: 'MCP client/server wrappers', blurb: 'MCPClient enforces tenant_id + scope; MCPServer auths + traces.', status: 'shipped', href: '/admin/mcp/deep' },
      { name: 'Request correlation propagation', blurb: 'CorrelationIdMiddleware + ContextVar for async.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Observability helpers', blurb: 'with_span() + with_metric() + log_with_context().', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Background tasks and workers', blurb: 'FastAPI BackgroundTasks + Kafka consumers.', status: 'partial', href: '/admin/microservices/deep' },
      { name: 'Policy/gateway-friendly service boundaries', blurb: 'Each service owns its schema; thin routers.', status: 'shipped', href: '/admin/microservices/deep' },
    ],
  },
  {
    heading: 'High-value advanced Python topics for this repo',
    intro: 'If you can explain these well, you can lead this codebase.',
    topics: [
      { name: 'asyncio', blurb: 'Event loop + tasks + cancellation + TaskGroups.', status: 'shipped', href: '/admin/python/deep#async-await' },
      { name: 'Decorators', blurb: 'Composable cross-cutting concerns.', status: 'shipped', href: '/admin/python/deep#decorators' },
      { name: 'Context managers', blurb: 'Resource lifecycle discipline.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: 'Pydantic and typing', blurb: 'Runtime + static contracts at boundaries.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Dataclasses vs Pydantic', blurb: 'When dataclass is enough vs when Pydantic earns its weight.', status: 'todo' },
      { name: 'Async HTTP and DB clients', blurb: 'httpx + asyncpg patterns.', status: 'shipped', href: '/admin/python/deep#http-pool-retry-breaker' },
      { name: 'Retries, breakers, idempotency', blurb: 'The three together; alone any one is incomplete.', status: 'shipped', href: '/admin/breakers/deep' },
      { name: 'Structured logging + OTel hooks', blurb: 'JSON + correlation + spans + tenant tags.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Worker patterns', blurb: 'Consumer + replay + DLQ + backoff.', status: 'partial', href: '/admin/microservices/deep' },
      { name: 'Generators and streaming', blurb: 'AsyncIterator for token streams.', status: 'partial', href: '/admin/python/deep#iterators-generators' },
      { name: 'Descriptors and dunder methods', blurb: 'How Pydantic + ORMs work under the hood.', status: 'todo' },
      { name: 'Concurrency control', blurb: 'Semaphores + locks + async-safe data structures.', status: 'todo' },
      { name: 'Package / module boundary design', blurb: 'libs/py/documind_core vs services; clean imports.', status: 'shipped', href: '/admin/architect/deep' },
      { name: 'Testing async code', blurb: 'pytest-asyncio + AsyncMock + fixtures.', status: 'todo' },
      { name: 'Mocking external clients safely', blurb: 'AsyncMock + cassette + replay.', status: 'todo' },
    ],
  },
  {
    heading: 'Most important if your goal is RAG + MCP + backend',
    intro: 'The 13 must-haves for shipping production RAG / MCP / backend services.',
    topics: [
      { name: 'async / await', blurb: 'Foundational concurrency model.', status: 'shipped', href: '/admin/python/deep#async-await' },
      { name: 'FastAPI', blurb: 'The HTTP layer.', status: 'shipped', href: '/admin/python/deep#fastapi-middleware' },
      { name: 'Pydantic', blurb: 'Runtime validation + schema generation.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Typing', blurb: 'mypy + IDE + Pydantic ergonomics.', status: 'shipped', href: '/admin/python/deep#typing-pydantic' },
      { name: 'Decorators', blurb: 'Retry + trace + rate-limit composition.', status: 'shipped', href: '/admin/python/deep#decorators' },
      { name: 'Context managers', blurb: 'Pool + transaction + resource lifecycle.', status: 'shipped', href: '/admin/python/deep#context-managers' },
      { name: 'Retries and breakers', blurb: 'Resilience primitives.', status: 'shipped', href: '/admin/breakers/deep' },
      { name: 'Background workers', blurb: 'Kafka consumer + DLQ + replay.', status: 'partial', href: '/admin/microservices/deep' },
      { name: 'Async client wrappers', blurb: 'QdrantRepo / RedisRepo / KafkaProducer.', status: 'shipped', href: '/admin/database/deep#qdrant' },
      { name: 'Caching', blurb: 'Tenant-prefixed; TTL-aware; cache-through.', status: 'shipped', href: '/admin/database/deep#redis' },
      { name: 'Observability hooks', blurb: 'log + trace + metric per request.', status: 'shipped', href: '/admin/python/deep#observability-python' },
      { name: 'Error modeling', blurb: 'AppError taxonomy → HTTP status mapping.', status: 'shipped', href: '/admin/python/deep#exceptions' },
      { name: 'Plugin / provider abstraction', blurb: 'Protocol + ABC for swappable backends.', status: 'partial', href: '/admin/architect/deep' },
    ],
  },
];

function StatusBadge({ status }: { status: Status }) {
  const cfg = {
    shipped: { label: 'shipped', bg: '#16a34a' },
    partial: { label: 'partial', bg: '#eab308' },
    todo:    { label: 'todo',    bg: '#6b7280' },
  }[status];
  return (
    <span
      style={{
        fontSize: 11,
        padding: '2px 6px',
        borderRadius: 4,
        background: cfg.bg,
        color: '#fff',
        marginLeft: 8,
        verticalAlign: 'middle',
      }}
    >
      {cfg.label}
    </span>
  );
}

export default function PythonSyllabusPage() {
  const counts = CATEGORIES.flatMap((c) => c.topics).reduce(
    (a, t) => ((a[t.status] = (a[t.status] || 0) + 1), a),
    {} as Record<Status, number>,
  );
  const total = counts.shipped + counts.partial + counts.todo;
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Python — Syllabus</h1>
        <p className="design-areas-sub">
          Complete topic catalog organized by category. Each topic links to its deeper
          content (deep-dive page or anchor) where shipped or partial; <code>todo</code>
          items are tracked here as the next-iteration backlog.
        </p>
        <div style={{ marginTop: 12, display: 'flex', gap: 16, fontSize: 14, color: '#000' }}>
          <span><strong>Total:</strong> {total}</span>
          <span style={{ color: '#16a34a' }}><strong>shipped:</strong> {counts.shipped}</span>
          <span style={{ color: '#b45309' }}><strong>partial:</strong> {counts.partial}</span>
          <span style={{ color: '#374151' }}><strong>todo:</strong> {counts.todo}</span>
        </div>
        <nav className="scen-toc" style={{ marginTop: 16 }}>
          {CATEGORIES.map((c) => (
            <a
              key={c.heading}
              href={`#${c.heading.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')}`}
              className="scen-toc-link"
            >
              {c.heading} <span className="scen-toc-count">({c.topics.length})</span>
            </a>
          ))}
        </nav>
      </header>

      {CATEGORIES.map((cat) => {
        const slug = cat.heading.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
        return (
          <section key={cat.heading} id={slug} className="design-areas-group">
            <h2 className="design-areas-group-title">{cat.heading}</h2>
            <p style={{ color: '#000', marginBottom: 12, fontStyle: 'italic' }}>{cat.intro}</p>
            <ul style={{ paddingLeft: 18, color: '#000' }}>
              {cat.topics.map((t) => (
                <li key={t.name} style={{ marginBottom: 6 }}>
                  {t.href ? (
                    <Link href={t.href} style={{ color: '#1e3a8a', fontWeight: 600 }}>
                      {t.name}
                    </Link>
                  ) : (
                    <strong>{t.name}</strong>
                  )}
                  <StatusBadge status={t.status} />
                  <div style={{ fontSize: 13, color: '#000', marginTop: 2 }}>{t.blurb}</div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
