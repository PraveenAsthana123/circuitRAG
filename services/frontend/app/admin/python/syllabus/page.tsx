import Link from 'next/link';
import Mermaid from '../../../../components/Mermaid';

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

function statusStyle(status: Status) {
  if (status === 'shipped') return { label: 'shipped', bg: '#16a34a' };
  if (status === 'partial') return { label: 'partial', bg: '#d97706' };
  return { label: 'todo', bg: '#6b7280' };
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function coreConcept(topic: Topic, heading: string): string {
  if (heading.includes('RAG')) return `${topic.name} is a RAG pipeline building block that affects retrieval quality, answer quality, or operational latency.`;
  if (heading.includes('Backend')) return `${topic.name} is a backend implementation pattern used to keep service code reliable, observable, and maintainable.`;
  if (heading.includes('Typing')) return `${topic.name} is part of the contract layer that keeps Python code understandable at both lint time and runtime.`;
  if (heading.includes('Dunder')) return `${topic.name} is part of Python's protocol model, which lets your objects participate in built-in language behavior.`;
  if (heading.includes('runtime') || heading.includes('advanced')) return `${topic.name} is a runtime-level concept that controls how Python executes work, schedules tasks, or resolves behavior.`;
  return `${topic.name} is a Python language concept that shapes how you write clear, correct, and reusable code.`;
}

function fiveW(topic: Topic, heading: string) {
  const location = topic.href ? `Explained in ${topic.href}` : `Tracked in the ${heading.toLowerCase()} syllabus section`;
  return {
    what: topic.blurb,
    why: `It matters because ${topic.name.toLowerCase()} affects correctness, readability, and interview depth in this codebase.`,
    when: `Use it whenever the code path genuinely needs ${topic.name.toLowerCase()}, not just because the feature exists in Python.`,
    where: location,
    who: heading.includes('RAG') ? 'Backend / RAG engineers, platform engineers, and interviewers probing production AI depth.' : 'Backend engineers, platform engineers, reviewers, and interviewers for senior Python roles.',
  };
}

function interviewExplanation(topic: Topic, heading: string): string {
  if (heading.includes('RAG')) {
    return `Explain where ${topic.name} sits in the ingest -> retrieve -> generate flow, what quality or latency risk it controls, and how you would observe failures in production.`;
  }
  if (heading.includes('Backend')) {
    return `Explain the boundary where ${topic.name} belongs, the failure mode it prevents, and how it interacts with retries, timeouts, observability, or service layering.`;
  }
  if (heading.includes('Typing')) {
    return `Explain the difference between static understanding and runtime enforcement, and show how ${topic.name} reduces ambiguity at API boundaries.`;
  }
  if (heading.includes('Dunder')) {
    return `Explain which Python protocol ${topic.name} participates in, when you would implement it yourself, and what surprises it can create if done poorly.`;
  }
  return `Explain the core rule of ${topic.name}, the most common misuse, and how it shows up in real production Python instead of toy examples.`;
}

function sampleCode(topic: Topic): string {
  const key = topic.name.toLowerCase();

  if (key.includes('decorator')) {
    return `import functools

def traced(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        print(f"start {fn.__name__}")
        try:
            return fn(*args, **kwargs)
        finally:
            print(f"end {fn.__name__}")
    return wrapper`;
  }
  if (key.includes('context manager')) {
    return `from contextlib import contextmanager

@contextmanager
def tenant_connection(pool, tenant_id: str):
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)`;
  }
  if (key.includes('async / await') || key === 'asyncio' || key.includes('coroutine') || key.includes('event loop')) {
    return `async def fetch_user(client, user_id: str):
    resp = await client.get(f"/users/{user_id}")
    return resp.json()`;
  }
  if (key.includes('asyncio task orchestration') || key.includes('fan-out')) {
    return `results = await asyncio.gather(
    fetch_vector_hits(query),
    fetch_graph_hits(query),
    fetch_cache_hits(query),
)`;
  }
  if (key.includes('generator') || key.includes('__iter__') || key.includes('__next__')) {
    return `def iter_chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i:i + size]`;
  }
  if (key.includes('pydantic')) {
    return `from pydantic import BaseModel

class AskRequest(BaseModel):
    question: str
    tenant_id: str`;
  }
  if (key.includes('fastapi')) {
    return `@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, svc: AskService = Depends(get_ask_service)):
    return await svc.run(req)`;
  }
  if (key.includes('retry') || key.includes('breaker') || key.includes('timeout')) {
    return `async with asyncio.timeout(3):
    if not breaker.allow():
        raise CircuitOpenError("dependency unavailable")
    result = await client.get("/health")`;
  }
  if (key.includes('logging')) {
    return `logger.info("request_complete", correlation_id=cid, tenant_id=tenant_id, route="/ask")`;
  }
  if (key.includes('trace')) {
    return `with tracer.start_as_current_span("ask.run") as span:
    span.set_attribute("tenant.id", tenant_id)
    answer = await svc.run(req)`;
  }
  if (key.includes('metric')) {
    return `REQUEST_LATENCY.labels(route="/ask").observe(duration_s)`;
  }
  if (key.includes('chunk')) {
    return `def chunk_text(tokens: list[str], size: int = 512, overlap: int = 64):
    for start in range(0, len(tokens), size - overlap):
        yield tokens[start:start + size]`;
  }
  if (key.includes('embedding')) {
    return `vectors = await embedder.embed_batch(chunks, model="text-embed-v1")`;
  }
  if (key.includes('vector db') || key.includes('qdrant')) {
    return `hits = await qdrant.search(
    collection_name="chunks",
    query_vector=query_vec,
    query_filter={"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]},
)`;
  }
  if (key.includes('cache')) {
    return `cache_key = f"{tenant_id}:answer:{question_hash}"
cached = await redis.get(cache_key)`;
  }
  if (key.includes('dataclass')) {
    return `from dataclasses import dataclass

@dataclass(frozen=True)
class ChunkRef:
    doc_id: str
    page: int`;
  }
  if (key.includes('property')) {
    return `class Config:
    @property
    def is_prod(self) -> bool:
        return self.env == "prod"`;
  }
  if (key.includes('classmethod')) {
    return `class User:
    @classmethod
    def from_row(cls, row: dict):
        return cls(**row)`;
  }
  if (key.includes('abc') || key.includes('abstract base classes')) {
    return `from abc import ABC, abstractmethod

class Embedder(ABC):
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...`;
  }
  if (key.includes('protocol')) {
    return `from typing import Protocol

class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...`;
  }
  if (key.includes('typeddict')) {
    return `class ChunkMeta(TypedDict):
    doc_id: str
    tenant_id: str`;
  }
  if (key.includes('__call__')) {
    return `class Scorer:
    def __call__(self, score: float) -> bool:
        return score > 0.8`;
  }
  if (key.includes('__enter__') || key.includes('__exit__')) {
    return `class Session:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        self.close()`;
  }
  if (key.includes('__aenter__') || key.includes('__aexit__')) {
    return `class AsyncSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        await self.close()`;
  }
  if (key.includes('__getitem__')) {
    return `class Row:
    def __getitem__(self, key: str):
        return self.data[key]`;
  }
  if (key.includes('__setitem__')) {
    return `class Row:
    def __setitem__(self, key: str, value):
        self.data[key] = value`;
  }
  if (key.includes('__len__')) {
    return `class Batch:
    def __len__(self) -> int:
        return len(self.items)`;
  }
  if (key.includes('__bool__')) {
    return `class Result:
    def __bool__(self) -> bool:
        return self.ok`;
  }
  if (key.includes('equality') || key.includes('hash')) {
    return `class ChunkRef:
    def __eq__(self, other):
        return (self.doc_id, self.page) == (other.doc_id, other.page)
    def __hash__(self):
        return hash((self.doc_id, self.page))`;
  }
  if (key.includes('list / dict / set comprehensions')) {
    return `filenames = [doc.filename for doc in docs if doc.state == "ready"]`;
  }
  if (key.includes('iterator')) {
    return `class Counter:
    def __iter__(self):
        return self
    def __next__(self):
        raise StopIteration`;
  }
  if (key.includes('lambda')) {
    return `sorted_docs = sorted(docs, key=lambda d: d.updated_at)`;
  }
  if (key.includes('closure')) {
    return `def make_prefixer(prefix: str):
    def add_prefix(value: str) -> str:
        return f"{prefix}{value}"
    return add_prefix`;
  }
  if (key.includes('*args') || key.includes('**kwargs')) {
    return `def wrapper(*args, **kwargs):
    return target(*args, **kwargs)`;
  }
  if (key.includes('unpacking')) {
    return `first, *rest = values
payload = {**base_meta, **extra_meta}`;
  }
  if (key.includes('enumerate') || key.includes('zip') || key.includes('map') || key.includes('filter')) {
    return `for idx, (question, answer) in enumerate(zip(questions, answers), start=1):
    print(idx, question, answer)`;
  }
  if (key.includes('type hints')) {
    return `def normalize(text: str) -> str:
    return text.strip().lower()`;
  }
  if (key.includes('union')) {
    return `def parse_value(value: str | int) -> int:
    return int(value)`;
  }
  if (key.includes('optional')) {
    return `def title_or_default(title: str | None) -> str:
    return title or "untitled"`;
  }
  if (key.includes('generic')) {
    return `T = TypeVar("T")

def first(items: list[T]) -> T:
    return items[0]`;
  }
  if (key.includes('memory') || key.includes('gc') || key.includes('weak')) {
    return `import weakref

cache = weakref.WeakValueDictionary()`;
  }
  if (key.includes('import system')) {
    return `# Avoid circular imports by moving shared contracts to a lower-level module.
from app.schemas import AskRequest`;
  }

  return `# ${topic.name}
# ${topic.blurb}
def example():
    pass`;
}

// Mermaid v11 strict-mode-safe label sanitizer: drops chars that
// break the parser inside [node] labels.
function safe(s: string): string {
  return s.replace(/[`"|;<>(){}[\]\\]/g, ' ').replace(/\s+/g, ' ').trim();
}

function flowchart(topic: Topic, heading: string): string {
  const t = safe(topic.name).slice(0, 40);
  const h = safe(heading).slice(0, 30);
  return `flowchart LR
  i[Input ${t}] --> p[Process ${h}]
  p --> c{Decision ok}
  c -->|yes| o[Output applied]
  c -->|no| f[Fallback or raise]
  o --> v[Verify with drill]
  f --> v`;
}

function sequence(topic: Topic): string {
  const t = safe(topic.name).slice(0, 30);
  return `sequenceDiagram
  autonumber
  participant Cli as Caller
  participant Mod as Module
  participant Dep as Dependency
  Cli->>Mod: invoke ${t}
  Mod->>Dep: prepare context
  Dep-->>Mod: bound resource
  Mod-->>Cli: result OR exception
  Note over Mod,Dep: drill verifies success and failure paths`;
}

function implementationSteps(topic: Topic, heading: string): string[] {
  const k = topic.name.toLowerCase();
  if (k.includes('decorator')) return [
    'Define wrapper function that takes the target function as input',
    'Use functools.wraps to preserve metadata',
    'Add cross-cutting logic before and after the target call',
    'Return the wrapper; apply via @decorator syntax',
    'Test the decorated and undecorated paths',
  ];
  if (k.includes('context manager')) return [
    'Implement __enter__ to acquire the resource',
    'Implement __exit__ to release; handle exception types',
    'OR use @contextmanager + yield for the same shape',
    'Wrap usage in `with` block to guarantee teardown',
    'Test that __exit__ runs even when the body raises',
  ];
  if (k.includes('async / await') || k.includes('asyncio')) return [
    'Mark the function as async def',
    'await any IO-bound call; never block the event loop',
    'Use asyncio.gather for fan-out, asyncio.wait_for for timeouts',
    'Run via asyncio.run or under FastAPI lifespan',
    'Test under concurrency to catch race conditions',
  ];
  if (k.includes('iterator') || k.includes('generator')) return [
    'Implement __iter__ returning self (or use yield in a function)',
    'Implement __next__ producing one value at a time, raising StopIteration when done',
    'Consume via for loop or list comprehension',
    'Memory profile vs eager-list approach',
  ];
  return [
    'Identify input and required preconditions',
    `Apply ${heading} idiom with explicit types`,
    'Handle the edge case (empty, None, invalid)',
    'Wire into the surrounding control flow',
    'Add a unit test covering success + failure',
  ];
}

function TopicDetail({ topic, heading }: { topic: Topic; heading: string }) {
  const fivew = fiveW(topic, heading);
  const steps = implementationSteps(topic, heading);
  return (
    <div
      style={{
        marginTop: 10,
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        background: '#fff',
        padding: '12px 14px',
      }}
    >
      <div>
        <strong>§1. Core concept</strong>
        <div style={{ marginTop: 4, fontSize: 14, color: '#111827' }}>{coreConcept(topic, heading)}</div>
      </div>

      <div style={{ marginTop: 14 }}>
        <strong>§2. 5W</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18, fontSize: 14, lineHeight: 1.6, color: '#111827' }}>
          <li><strong>What:</strong> {fivew.what}</li>
          <li><strong>Why:</strong> {fivew.why}</li>
          <li><strong>When:</strong> {fivew.when}</li>
          <li><strong>Where:</strong> {fivew.where}</li>
          <li><strong>Who:</strong> {fivew.who}</li>
        </ul>
      </div>

      <div style={{ marginTop: 14, padding: 12, background: '#dbeafe', borderRadius: 6, borderLeft: '4px solid #1e3a8a' }}>
        <strong>§3. Interview point</strong>
        <div style={{ marginTop: 4, fontSize: 14, color: '#111827', fontStyle: 'italic' }}>
          {interviewExplanation(topic, heading)}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        <strong>§4. Flowchart</strong>
        <Mermaid chart={flowchart(topic, heading)} />
      </div>

      <div style={{ marginTop: 14 }}>
        <strong>§5. Sequence chart</strong>
        <Mermaid chart={sequence(topic)} />
      </div>

      <div style={{ marginTop: 14 }}>
        <strong>§6. Implementation steps</strong>
        <ol style={{ marginTop: 6, paddingLeft: 22, fontSize: 14, lineHeight: 1.6, color: '#111827' }}>
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>

      <div style={{ marginTop: 14 }}>
        <strong>§7. Sample code</strong>
        <pre className="md-pre" style={{ marginTop: 6 }}>
          <code>{sampleCode(topic)}</code>
        </pre>
      </div>

      {topic.href ? (
        <div style={{ marginTop: 12 }}>
          <Link href={topic.href} style={{ color: '#1d4ed8', fontWeight: 600 }}>
            Open deeper linked explanation →
          </Link>
        </div>
      ) : null}
    </div>
  );
}

function StatusBadge({ status }: { status: Status }) {
  const cfg = statusStyle(status);
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
          Complete topic catalog organized by category. Each topic now includes a compact
          detailed explanation surface with core concept, 5W, interview framing, and sample code.
          <code> shipped</code> and <code>partial</code> topics also link to the deeper pages.
        </p>
        <div style={{ marginTop: 12, display: 'flex', gap: 16, fontSize: 14, color: '#000', flexWrap: 'wrap' }}>
          <span><strong>Total:</strong> {total}</span>
          <span style={{ color: '#16a34a' }}><strong>shipped:</strong> {counts.shipped}</span>
          <span style={{ color: '#b45309' }}><strong>partial:</strong> {counts.partial}</span>
          <span style={{ color: '#374151' }}><strong>todo:</strong> {counts.todo}</span>
        </div>
        <nav className="scen-toc" style={{ marginTop: 16 }}>
          {CATEGORIES.map((c) => (
            <a
              key={c.heading}
              href={`#${slugify(c.heading)}`}
              className="scen-toc-link"
            >
              {c.heading} <span className="scen-toc-count">({c.topics.length})</span>
            </a>
          ))}
        </nav>
      </header>

      {CATEGORIES.map((cat) => (
        <section key={cat.heading} id={slugify(cat.heading)} className="design-areas-group">
          <h2 className="design-areas-group-title">{cat.heading}</h2>
          <p style={{ color: '#000', marginBottom: 12, fontStyle: 'italic' }}>{cat.intro}</p>
          <ul style={{ paddingLeft: 18, color: '#000' }}>
            {cat.topics.map((t) => (
              <li key={t.name} style={{ marginBottom: 14 }}>
                {t.href ? (
                  <Link href={t.href} style={{ color: '#1e3a8a', fontWeight: 700 }}>
                    {t.name}
                  </Link>
                ) : (
                  <strong style={{ color: '#991b1b' }}>{t.name}</strong>
                )}
                <StatusBadge status={t.status} />
                <div style={{ fontSize: 13, color: '#000', marginTop: 4 }}>{t.blurb}</div>
                <TopicDetail topic={t} heading={cat.heading} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
