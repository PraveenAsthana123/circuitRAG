'use client';

/**
 * Python concepts page — every Python topic from the user's catalog,
 * organized by level (core / intermediate / advanced / dunder /
 * typing / backend / rag / project-pattern), each with a short
 * "what it is" and "why it matters here." Plus inline SVG flowcharts
 * for the two RAG-relevant runtime topics: asyncio fan-out and
 * the RAG request lifecycle.
 *
 * Static content — no API call, no auto-refresh. Pure educational
 * surface. Per the user request "update all these on UI under
 * python" + "in detail with flowchart."
 */

import Link from 'next/link';
import { Fragment, useState } from 'react';
import Mermaid from '../../../components/Mermaid';

type Level =
  | 'core'
  | 'intermediate'
  | 'advanced'
  | 'dunder'
  | 'typing'
  | 'backend'
  | 'rag'
  | 'project';

interface Topic {
  name: string;
  level: Level;
  blurb: string;
  // One-line "where it shows up" — anchored to circuitRAG when possible
  whereInRepo?: string;
  // Inline mermaid flowchart for topics where flow matters more than blurb.
  // Optional — most catalog topics stay compact.
  flowchart?: string;
  // Sequence diagram for the same runtime path when caller/dependency
  // interaction matters.
  sequence?: string;
  // Sequential implementation steps for interview / implementation
  // discussion. Kept short and concrete.
  implementationSteps?: string[];
  // Anchor on /admin/python/deep when this topic has a deep-dive entry.
  // Renders a "Deep dive →" link inline.
  deepSlug?: string;
}

function mermaidLabel(value: string): string {
  return value.replace(/[`"]/g, '').replace(/[<>]/g, '');
}

function defaultFlowchart(topic: Topic): string {
  const label = mermaidLabel(topic.name);
  const repo = topic.whereInRepo ? mermaidLabel(topic.whereInRepo) : 'Apply in service or utility layer';
  return `flowchart LR
  i[Input: ${label}] --> p[Process: Understand rules and apply ${label}]
  p --> c[Check: correctness + readability + safety]
  c --> r[Repo fit: ${repo}]
  r --> o[Output: working ${label} usage]`;
}

function defaultSequence(topic: Topic): string {
  const label = mermaidLabel(topic.name);
  return `sequenceDiagram
  autonumber
  participant Dev as Engineer
  participant Code as Application code
  participant Runtime as Python runtime
  participant Repo as Repo pattern
  Dev->>Code: implement ${label}
  Code->>Runtime: execute ${label}
  Runtime-->>Code: behavior / result
  Code->>Repo: integrate with boundary
  Repo-->>Dev: observable outcome`;
}

function defaultImplementationSteps(topic: Topic): string[] {
  const shared = [
    `Understand the core rule of ${topic.name} before using it in application code.`,
    `Apply ${topic.name} first in a small, testable unit instead of a broad refactor.`,
    `Connect ${topic.name} to the repo's existing service, schema, or observability patterns.`,
    `Verify the behavior with tests and one realistic failure or edge case.`,
  ];

  switch (topic.level) {
    case 'core':
      return [
        `Define the smallest code example that demonstrates ${topic.name}.`,
        `Apply ${topic.name} in a function or class with explicit inputs and outputs.`,
        `Check common runtime traps such as None handling, mutability, or control-flow ambiguity.`,
        `Keep the final usage simple enough that another engineer can read it without hidden behavior.`,
      ];
    case 'intermediate':
      return [
        `Introduce ${topic.name} only where it improves clarity or reuse over plain code.`,
        `Keep the abstraction narrow so the behavior stays obvious to callers.`,
        `Test one happy path and one misuse path for ${topic.name}.`,
        `Document the tradeoff if ${topic.name} changes control flow or readability.`,
      ];
    case 'advanced':
      return [
        `Identify the runtime problem that actually requires ${topic.name}.`,
        `Choose the correct execution model or lifecycle for ${topic.name}.`,
        `Add timeouts, cancellation, or failure handling where ${topic.name} crosses a boundary.`,
        `Measure the result so the advanced abstraction solves a real performance or reliability problem.`,
      ];
    case 'dunder':
      return [
        `Use ${topic.name} only when native Python protocol support is genuinely needed.`,
        `Keep the object contract predictable for callers of the class.`,
        `Verify that ${topic.name} does not create surprising side effects or recursion traps.`,
        `Add repr/tests/examples so the protocol behavior remains maintainable.`,
      ];
    case 'typing':
      return [
        `Define the type or schema contract for ${topic.name} before writing the handler logic.`,
        `Validate the boundary where external data enters the system.`,
        `Keep the type surface readable; avoid type complexity that obscures intent.`,
        `Run static checks and one malformed payload test for ${topic.name}.`,
      ];
    case 'backend':
      return [
        `Place ${topic.name} at the correct backend layer: middleware, router, service, repository, or client.`,
        `Wire explicit timeouts, logging, and error handling around ${topic.name} if it touches IO.`,
        `Keep HTTP concerns at the edge and domain behavior in the service layer.`,
        `Verify the path through logs, traces, or metrics after implementation.`,
      ];
    case 'rag':
      return [
        `Define where ${topic.name} sits in the ingest, retrieval, or generation pipeline.`,
        `Keep metadata and tenant boundaries intact while applying ${topic.name}.`,
        `Evaluate both quality impact and latency impact of ${topic.name}.`,
        `Add one failure-path behavior so degraded retrieval or model output stays explainable.`,
      ];
    case 'project':
      return [
        `Check whether ${topic.name} already exists as a shared primitive before adding new code.`,
        `Implement ${topic.name} once in the shared layer and reuse it through dependency wiring.`,
        `Preserve correlation, audit, and observability behavior while applying ${topic.name}.`,
        `Add one integration test proving the project pattern is not bypassed.`,
      ];
    default:
      return shared;
  }
}

function resolveFlowchart(topic: Topic): string {
  return topic.flowchart ?? defaultFlowchart(topic);
}

function resolveSequence(topic: Topic): string {
  return topic.sequence ?? defaultSequence(topic);
}

function resolveImplementationSteps(topic: Topic): string[] {
  return topic.implementationSteps ?? defaultImplementationSteps(topic);
}

const LEVELS: Record<Level, { title: string; tone: string }> = {
  core: { title: 'Core', tone: '#1e3a8a' },
  intermediate: { title: 'Intermediate', tone: '#0d9488' },
  advanced: { title: 'Advanced', tone: '#7c2d12' },
  dunder: { title: 'Dunder methods', tone: '#5b21b6' },
  typing: { title: 'Typing & schema', tone: '#0369a1' },
  backend: { title: 'Backend engineering', tone: '#475569' },
  rag: { title: 'RAG-specific', tone: '#b45309' },
  project: { title: 'Project pattern', tone: '#065f46' },
};

const TOPICS: Topic[] = [
  // ---- core ----
  { name: 'variables and data types', level: 'core', blurb: 'int, float, str, bool, None — Python is dynamically typed; variables are names bound to objects.' },
  { name: 'strings, lists, tuples, sets, dicts', level: 'core', blurb: 'str/list/dict are mutable-ish (str is immutable); set is unordered unique; tuple is immutable list. Hash discipline matters for set/dict keys.' },
  { name: 'conditionals', level: 'core', blurb: 'if / elif / else. Truthy/falsy: empty containers + 0 + None are falsy.' },
  { name: 'loops', level: 'core', blurb: 'for-each over iterables; while for predicate-driven. break / continue / for-else.' },
  { name: 'functions', level: 'core', blurb: 'def. First-class objects: passable, assignable, returnable.' },
  { name: 'modules and imports', level: 'core', blurb: 'A module is a .py file. import resolves via sys.path; circular imports are a real failure mode.' },
  {
    name: 'exceptions',
    level: 'core',
    blurb: 'raise / try / except / else / finally. Catch specific; never bare except without re-raise.',
    whereInRepo: 'libs/py/documind_core/exceptions.py — AppError hierarchy',
    deepSlug: 'exceptions',
    flowchart: `flowchart LR
  c[Code path] --> r{raise?}
  r -->|yes| t[try/except]
  t -->|known transient| ret[Retry policy]
  t -->|domain error| map[Map to HTTP 4xx]
  t -->|infra error| map5[Map to HTTP 5xx]
  ret --> log[Log + audit]
  map --> log
  map5 --> log`,
    sequence: `sequenceDiagram
  autonumber
  participant R as Router
  participant S as Service
  participant D as Dependency
  participant H as Error handler
  R->>S: call workflow()
  S->>D: dependency call
  alt dependency succeeds
    D-->>S: result
    S-->>R: domain result
  else dependency fails
    D-->>S: raise AppError subclass
    S-->>R: propagate typed error
    R->>H: map error to API response
    H-->>R: 4xx/5xx + context
  end`,
    implementationSteps: [
      'Define an AppError hierarchy for domain, validation, policy, and dependency failures.',
      'Raise typed exceptions in services; do not raise HTTPException from domain logic.',
      'Add one router/global error-mapping layer that converts AppError subclasses to API responses.',
      'Log the full request context and keep retries limited to explicitly transient failures.',
    ],
  },
  { name: 'file handling', level: 'core', blurb: 'open() with context manager (`with open(...) as f`) — always.' },
  { name: 'classes and objects', level: 'core', blurb: '__init__ for construction, methods for behavior. Instance vs class attributes.' },
  {
    name: 'inheritance',
    level: 'core',
    blurb: 'class Foo(Base): super().__init__(...). Watch the MRO when multiple bases.',
    deepSlug: 'classes-inheritance-mro',
    flowchart: `flowchart LR
  i[Instance.method()] --> mro[MRO lookup]
  mro --> c1[Class 1?]
  c1 -->|found| call[Invoke]
  c1 -->|not| c2[Class 2?]
  c2 -->|found| call
  c2 -->|not| b[Base]
  b --> call`,
    implementationSteps: [
      'Prefer composition first; use inheritance only when the subtype contract is stable.',
      'Keep the base class narrow and document what subclasses are allowed to override.',
      'Use super() consistently across the hierarchy so cooperative multiple inheritance remains valid.',
      'Check __mro__ when combining mixins to confirm the actual lookup order.',
    ],
  },
  { name: 'packages', level: 'core', blurb: '__init__.py marks a package. Re-export at the package level for clean import surfaces.' },
  { name: 'virtual environments', level: 'core', blurb: 'python -m venv / poetry / uv / pixi. Project deps isolated from the system.' },
  // ---- intermediate ----
  { name: 'list/dict/set comprehensions', level: 'intermediate', blurb: '[f(x) for x in xs if pred] — concise, fast, lazy when wrapped in genexp `(...)`.' },
  { name: 'iterators', level: 'intermediate', blurb: 'Anything with __iter__ + __next__. for-loops use this protocol.' },
  {
    name: 'generators',
    level: 'intermediate',
    blurb: 'def with yield — lazy iterator factory. Memory-efficient for big sequences.',
    deepSlug: 'iterators-generators',
    flowchart: `flowchart LR
  c[Call gen()] --> g[Generator object]
  g --> n[next()]
  n --> y[yield value]
  y --> p[Pause]
  p --> n2[next()]
  n2 --> y
  y --> e[exhausted → StopIteration]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Caller
  participant G as Generator
  C->>G: create generator
  loop per item
    C->>G: next()
    G-->>C: yielded value
  end
  C->>G: next() after final yield
  G-->>C: StopIteration`,
    implementationSteps: [
      'Identify the path where producing all results eagerly would waste memory or latency.',
      'Refactor the function to yield items progressively instead of returning a full list.',
      'Document single-consumption semantics so callers do not assume the generator is reusable.',
      'Wrap the consumer side with explicit error handling if failure can happen mid-stream.',
    ],
  },
  {
    name: 'decorators',
    level: 'intermediate',
    blurb: '@decorator wraps a function. functools.wraps preserves metadata. Used for retries, tracing, auth.',
    whereInRepo: 'documind_core retry/tracing decorators',
    deepSlug: 'decorators',
    flowchart: `flowchart LR
  d[@decorator] --> w[wrapper(*args, **kw)]
  w --> b[Before: trace start / auth check]
  b --> f[fn(*args, **kw)]
  f --> a[After: trace end / record outcome]
  a --> r[Return result]
  f -->|raise| h[On error: log + reraise]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Caller
  participant W as Wrapper
  participant F as Wrapped function
  C->>W: invoke()
  W->>W: before hook
  W->>F: call original
  alt success
    F-->>W: result
    W->>W: after hook
    W-->>C: result
  else error
    F-->>W: exception
    W->>W: log / trace / metric
    W-->>C: re-raise
  end`,
    implementationSteps: [
      'Define the cross-cutting concern clearly: retry, tracing, auth, timing, or policy.',
      'Write a wrapper that accepts *args and **kwargs and preserves metadata with functools.wraps.',
      'Handle sync and async functions deliberately; do not wrap async functions with sync-only logic.',
      'Apply the decorator only where the behavior is semantically safe, especially for retries.',
    ],
  },
  {
    name: 'context managers',
    level: 'intermediate',
    blurb: '`with` blocks. Implements __enter__/__exit__. contextlib.contextmanager turns a generator into one.',
    deepSlug: 'context-managers',
    flowchart: `flowchart LR
  w[with cm as r] --> e[__enter__]
  e --> b[Body runs]
  b -->|normal| x[__exit__ - None args]
  b -->|exception| x2[__exit__ - exc args]
  x --> done[Done]
  x2 -->|return True| done
  x2 -->|return False| reraise[Re-raise]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Caller
  participant M as Context manager
  C->>M: __enter__()
  M-->>C: resource handle
  C->>C: run body
  alt normal exit
    C->>M: __exit__(None, None, None)
    M-->>C: cleanup complete
  else exception in body
    C->>M: __exit__(exc_type, exc, tb)
    alt suppress
      M-->>C: True
    else re-raise
      M-->>C: False
    end
  end`,
    implementationSteps: [
      'Wrap resource acquisition and release in one object or contextlib helper.',
      'Put only setup in __enter__ and only cleanup in __exit__.',
      'Return False from __exit__ unless you intentionally want to suppress the exception.',
      'Use async context managers for resources with async open/close behavior.',
    ],
  },
  { name: 'lambda functions', level: 'intermediate', blurb: 'Anonymous single-expression functions. Use sparingly; named functions read better.' },
  { name: 'closures', level: 'intermediate', blurb: 'Inner function captures outer-scope variables. Watch for late-binding gotchas in loops.' },
  { name: '*args / **kwargs', level: 'intermediate', blurb: 'Variadic positional / keyword args. Combined with unpacking for forwarding wrappers.' },
  { name: 'unpacking', level: 'intermediate', blurb: 'a, *rest = xs. Iterable unpacking + dict spread `{**a, **b}` + function call `f(*a, **kw)`.' },
  { name: 'enumerate / zip / map / filter', level: 'intermediate', blurb: 'Built-in iterables. zip stops at shortest; itertools has the long form.' },
  { name: 'dataclasses', level: 'intermediate', blurb: '@dataclass auto-generates __init__/__repr__/__eq__. frozen=True for immutability.' },
  { name: 'properties', level: 'intermediate', blurb: '@property turns a method into attribute access. Setter via @prop.setter.' },
  { name: 'class methods / static methods', level: 'intermediate', blurb: '@classmethod takes cls; @staticmethod takes nothing. Used for alt constructors / pure utilities.' },
  { name: 'abstract base classes', level: 'intermediate', blurb: 'abc.ABC + @abstractmethod. Can\'t instantiate without overriding. Useful for plugin contracts.' },
  { name: 'typing basics', level: 'intermediate', blurb: 'list[int], dict[str, X], Optional[X], Union[A, B] (or A | B in 3.10+). Static type checkers (mypy, pyright).' },
  // ---- advanced ----
  {
    name: 'async / await',
    level: 'advanced',
    blurb: 'Coroutine functions return awaitables. await suspends until done. Single-threaded concurrency.',
    whereInRepo: 'every service uses async FastAPI handlers',
    deepSlug: 'async-await',
    flowchart: `flowchart LR
  c[async def f] --> a[await io_op]
  a --> s[Suspend - yield control]
  s --> l[Event loop runs others]
  l --> r[IO ready - wake]
  r --> rt[Resume f]
  rt --> done[Return value]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Caller
  participant Co as Coroutine
  participant L as Event loop
  participant IO as IO dependency
  C->>Co: await handler()
  Co->>IO: start async IO
  Co->>L: suspend
  L->>IO: keep waiting while other tasks run
  IO-->>L: ready
  L->>Co: resume
  Co-->>C: return result`,
    implementationSteps: [
      'Make the hot-path function async only if its dependencies are async or IO-bound.',
      'Replace blocking clients with async-native libraries such as httpx.AsyncClient or asyncpg.',
      'Await every network, DB, and model call explicitly and set timeouts on each boundary.',
      'Handle cancellation and backpressure so one slow dependency does not stall the whole event loop.',
    ],
  },
  { name: 'coroutines', level: 'advanced', blurb: 'Functions defined with `async def`. Don\'t run until awaited or scheduled.', deepSlug: 'async-await' },
  { name: 'event loop', level: 'advanced', blurb: 'asyncio.run() owns one. Schedules + drives coroutines + IO. Single thread by default.', deepSlug: 'async-await' },
  {
    name: 'asyncio task orchestration',
    level: 'advanced',
    blurb: 'asyncio.gather / create_task / wait. Cancellation propagates via CancelledError.',
    whereInRepo: 'services/inference-svc/app/routers — health/upstreams probes in parallel',
    deepSlug: 'async-await',
    flowchart: `flowchart LR
  g[asyncio.gather] --> t1[task 1]
  g --> t2[task 2]
  g --> t3[task 3]
  t1 --> r[Aggregate]
  t2 --> r
  t3 --> r
  t2 -->|exception| c[Cancel siblings - default]
  c --> r`,
    sequence: `sequenceDiagram
  autonumber
  participant H as Handler
  participant G as gather()
  participant A as Task A
  participant B as Task B
  participant C as Task C
  H->>G: gather(A, B, C)
  G->>A: schedule
  G->>B: schedule
  G->>C: schedule
  alt all succeed
    A-->>G: result
    B-->>G: result
    C-->>G: result
    G-->>H: aggregated tuple
  else one task fails
    B-->>G: exception
    G->>A: cancel sibling
    G->>C: cancel sibling
    G-->>H: raise / return exception policy
  end`,
    implementationSteps: [
      'Identify independent IO branches that can run concurrently instead of serially.',
      'Create one task per branch and aggregate them with asyncio.gather or TaskGroup.',
      'Set explicit timeout and exception policy for each branch before aggregation.',
      'Decide whether one branch failure should cancel siblings or degrade and continue.',
    ],
  },
  { name: 'concurrency vs parallelism', level: 'advanced', blurb: 'Concurrency = interleaved progress; parallelism = simultaneous on multiple cores. asyncio is concurrent, not parallel.' },
  { name: 'threading', level: 'advanced', blurb: 'OS threads, but GIL serializes pure-Python execution. Useful for IO-bound non-asyncio code.' },
  { name: 'multiprocessing', level: 'advanced', blurb: 'Spawns subprocesses with their own GIL. CPU-bound work scales here.' },
  { name: 'futures / executors', level: 'advanced', blurb: 'concurrent.futures: ThreadPoolExecutor / ProcessPoolExecutor. Submit returns Future.' },
  {
    name: 'GIL',
    level: 'advanced',
    blurb: 'Global Interpreter Lock. One thread runs Python bytecode at a time. Released for IO + C extensions.',
    deepSlug: 'gil-concurrency-models',
    flowchart: `flowchart LR
  w[Workload] --> q{Bound by?}
  q -->|IO| a[asyncio]
  q -->|Blocking IO library| t[threads via to_thread]
  q -->|CPU| p[multiprocessing]
  q -->|C extension - numpy/pandas| c[Threads OK - GIL released]`,
    implementationSteps: [
      'Classify the workload first: pure Python CPU, blocking IO, async IO, or C-extension heavy.',
      'Use asyncio for async IO, threads for blocking IO compatibility, and processes for CPU-bound Python.',
      'Avoid adding threads as a default scaling answer for CPU-heavy service code.',
      'Measure event-loop latency and worker utilization before changing concurrency model.',
    ],
  },
  { name: 'descriptors', level: 'advanced', blurb: 'Objects implementing __get__/__set__/__delete__ — power properties + ORM fields.' },
  { name: 'metaclasses', level: 'advanced', blurb: 'Classes whose instances are classes. type() at the limit. Used by ABCs + ORMs; rarely needed in app code.' },
  { name: 'MRO (method resolution order)', level: 'advanced', blurb: 'C3 linearization of the inheritance graph. SomeClass.__mro__ shows the lookup order.' },
  { name: 'callable objects', level: 'advanced', blurb: 'Anything with __call__. Functions are objects; instances can be functions.' },
  { name: 'memory model + GC', level: 'advanced', blurb: 'Reference counting + cycle collector. weakref module for non-owning references.' },
  // ---- dunder ----
  { name: '__init__ / __new__', level: 'dunder', blurb: '__new__ allocates; __init__ initializes. Override __new__ for singletons / metaclass tricks.' },
  { name: '__call__', level: 'dunder', blurb: 'Lets an instance be called like a function. Useful for stateful "callables."' },
  { name: '__repr__ / __str__', level: 'dunder', blurb: 'repr() = unambiguous (debug); str() = readable (display). Default repr() falls back to __repr__.' },
  { name: '__iter__ / __next__', level: 'dunder', blurb: 'Iterator protocol. Yield iter(self) to make a class iterable in for-loops.' },
  { name: '__enter__ / __exit__', level: 'dunder', blurb: 'Context manager. __exit__(exc_type, exc, tb) returns True to suppress raised exceptions.' },
  { name: '__aenter__ / __aexit__', level: 'dunder', blurb: 'Async context manager. `async with` triggers them.' },
  { name: '__getattr__ / __getattribute__', level: 'dunder', blurb: '__getattribute__ intercepts ALL attribute access; __getattr__ only the misses. Common __getattribute__ trap: infinite recursion.' },
  { name: '__getitem__ / __setitem__', level: 'dunder', blurb: 'obj[key] / obj[key] = v. Plus __len__ + __contains__ for full container protocol.' },
  { name: 'eq / hash dunders', level: 'dunder', blurb: 'Override __eq__ → must also override __hash__ (or set __hash__ = None to make instances unhashable).' },
  // ---- typing ----
  { name: 'type hints + generics', level: 'typing', blurb: 'list[T], dict[K, V], Generic[T]. Static-only; runtime can ignore.' },
  { name: 'Optional / Union', level: 'typing', blurb: 'Optional[X] = X | None. Union[A, B] or A | B (3.10+).' },
  { name: 'TypeVar / Protocol', level: 'typing', blurb: 'TypeVar for generic functions. Protocol for structural subtyping (duck-typed interfaces).' },
  { name: 'TypedDict', level: 'typing', blurb: 'Dict-shaped types where keys are known strings. Useful for JSON-shaped payloads.' },
  {
    name: 'Pydantic models',
    level: 'typing',
    blurb: 'Runtime validation. Field(...) for constraints. ClassVar to escape the field machinery.',
    whereInRepo: 'services/*/app/schemas/__init__.py',
    deepSlug: 'typing-pydantic',
    flowchart: `flowchart LR
  r[Request body] --> v{Pydantic validate}
  v -->|valid| h[Handler runs]
  v -->|invalid| e[422 + structured error]
  h --> rm[Response model]
  rm --> resp[Serialize JSON]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cl as Client
  participant F as FastAPI
  participant P as Pydantic
  participant H as Handler
  Cl->>F: JSON request
  F->>P: validate body
  alt valid
    P-->>F: typed model
    F->>H: call with model
    H-->>F: response object
    F->>P: validate response_model
    P-->>Cl: JSON response
  else invalid
    P-->>Cl: 422 validation error
  end`,
    implementationSteps: [
      'Define request and response models first, before writing handler logic.',
      'Put parsing and type coercion at the API boundary, not inside the service body.',
      'Use field constraints and enums to make invalid states unrepresentable as early as possible.',
      'Keep internal domain objects separate if runtime validation is not needed on every hop.',
    ],
  },
  // ---- backend ----
  {
    name: 'FastAPI patterns',
    level: 'backend',
    blurb: 'Router → Service → Repository. Depends() for DI. response_model on every endpoint.',
    deepSlug: 'fastapi-middleware',
    flowchart: `flowchart LR
  req[Request] --> mw[Middleware - cid + tenant + auth]
  mw --> r[Router]
  r --> svc[Service layer - workflow]
  svc --> repo[Repository - SQL]
  repo --> svc
  svc --> r
  r --> resp[response_model serialize]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant M as Middleware
  participant R as Router
  participant S as Service
  participant Repo as Repository
  C->>M: request
  M->>R: cid + tenant + auth context
  R->>S: validated input
  S->>Repo: persistence/query call
  Repo-->>S: domain data
  S-->>R: response DTO
  R-->>C: serialized response_model`,
    implementationSteps: [
      'Keep routers thin: validation, dependency wiring, and HTTP mapping only.',
      'Move workflow and policy decisions into a service layer with explicit dependencies.',
      'Isolate SQL and persistence details behind repository/store objects.',
      'Validate both request and response shapes with Pydantic models at the edge.',
    ],
  },
  { name: 'request/response modeling', level: 'backend', blurb: 'Pydantic in/out. Never raw dicts. Validate at boundaries.' },
  { name: 'dependency injection', level: 'backend', blurb: 'Depends() factories. Singleton services in app.state; per-request services as deps.' },
  { name: 'middleware', level: 'backend', blurb: 'CorrelationId, SecurityHeaders, TenantContext, RateLimit. Run BEFORE the route.' },
  { name: 'async HTTP clients', level: 'backend', blurb: 'httpx.AsyncClient with timeout. Reuse instance; don\'t create per-request.' },
  { name: 'connection pooling', level: 'backend', blurb: 'asyncpg.create_pool(min, max). Acquire/release in a context manager. RLS via set_config in tenant_connection.' },
  {
    name: 'retries / breakers / idempotency',
    level: 'backend',
    blurb: 'Retry with exponential backoff. CircuitBreaker around dependencies. Idempotency key for write ops.',
    whereInRepo: 'libs/py/documind_core/circuit_breaker.py + mcp/idempotency.py',
    deepSlug: 'http-pool-retry-breaker',
    flowchart: `flowchart LR
  c[Caller] --> b{CB allow?}
  b -->|no| ff[Fast-fail - degrade]
  b -->|yes| h[HTTP call]
  h -->|success| s[record_success]
  h -->|transient fail| r{Retries left?}
  r -->|yes| h
  r -->|no| f[record_failure - persist draft]
  f --> ff
  s --> resp[Return]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Caller
  participant B as Breaker
  participant D as Dependency
  participant S as Store
  C->>B: request(idempotency_key)
  alt breaker open
    B-->>C: fast-fail / degrade
  else breaker allows
    B->>D: call with timeout
    alt success
      D-->>B: result
      B->>B: record_success
      B-->>C: response
    else transient failure
      D-->>B: timeout / 5xx
      B->>B: retry policy
      alt retries exhausted
        B->>S: persist draft / failure state
        B-->>C: degraded response
      end
    end
  end`,
    implementationSteps: [
      'Define which operations are safe to retry and add an idempotency key for writes.',
      'Wrap the external dependency with explicit timeout, retry budget, and circuit-breaker state.',
      'Persist a durable fallback state when side-effecting work cannot complete immediately.',
      'Expose degraded behavior honestly instead of silently pretending the dependency succeeded.',
    ],
  },
  { name: 'structured logging', level: 'backend', blurb: 'JSON formatter; correlation_id in every log line. Never print() in prod.' },
  {
    name: 'tracing instrumentation',
    level: 'backend',
    blurb: 'OTel: instrument_fastapi/httpx/asyncpg/redis. Custom spans on critical workflows.',
    deepSlug: 'observability-python',
    flowchart: `flowchart LR
  req[Request + cid] --> s1[OTel root span]
  s1 --> s2[child span - DB]
  s1 --> s3[child span - HTTP]
  s1 --> s4[child span - guardrail]
  s2 --> j[Jaeger]
  s3 --> j
  s4 --> j
  s4 --> a[Span attrs - actor + outcome]`,
    sequence: `sequenceDiagram
  autonumber
  participant C as Client
  participant A as API span
  participant DB as DB span
  participant H as HTTP span
  participant O as OTel backend
  C->>A: request + correlation id
  A->>DB: child span start
  DB-->>A: db result
  A->>H: child span start
  H-->>A: upstream result
  A->>O: export trace tree
  A-->>C: response`,
    implementationSteps: [
      'Start one root span at the request boundary and propagate correlation context through the stack.',
      'Add child spans only at meaningful boundaries: DB, HTTP, model, guardrail, queue, or cache.',
      'Attach outcome attributes that operators can query without exploding cardinality.',
      'Make telemetry export non-blocking so tracing failure never blocks the user path.',
    ],
  },
  { name: 'metrics emission', level: 'backend', blurb: 'prometheus_client Counter/Histogram/Gauge. Cardinality discipline: bound label sets.', deepSlug: 'observability-python' },
  // ---- rag ----
  { name: 'text preprocessing + chunking', level: 'rag', blurb: 'Tokenizer-aware splitting (e.g., sliding window with overlap). 256-1024 tokens, 10-20% overlap.' },
  { name: 'embedding client integration', level: 'rag', blurb: 'Async batched calls to embedder. Version-tag the embedding model — re-embed on bump.' },
  { name: 'vector DB client', level: 'rag', blurb: 'qdrant-client / weaviate / milvus. Tenant-scoped collections or filter on tenant_id.' },
  { name: 'reranking pipelines', level: 'rag', blurb: 'Cross-encoder rerank top-K from vector search. Lifts precision at recall cost.' },
  { name: 'retrieval orchestration', level: 'rag', blurb: 'Hybrid: vector + BM25 + graph. Fuse with RRF or weighted scores.' },
  { name: 'prompt assembly', level: 'rag', blurb: 'System + user template. Include context with citations; truncate to fit context window.' },
  { name: 'response post-processing', level: 'rag', blurb: 'Citation extraction, guardrails (PII, hallucination-citation, empty answer).', whereInRepo: 'services/inference-svc/app/services/guardrails.py' },
  { name: 'streaming responses', level: 'rag', blurb: 'Generator yielding partial tokens. SSE or chunked HTTP. await client.aiter_bytes().' },
  { name: 'fallback logic', level: 'rag', blurb: 'Primary → secondary model on breaker open. Never silent — surface degradation.' },
  // ---- project ----
  { name: 'async service entrypoints', level: 'project', blurb: 'lifespan() for startup/shutdown. Initialize pools + clients in startup; close in shutdown.' },
  { name: 'shared library patterns (libs/py)', level: 'project', blurb: 'Reusable abstractions: DbClient, AuditWriter, CircuitBreaker, MCPClient, EventProducer.' },
  { name: 'circuit breaker abstraction', level: 'project', blurb: 'CircuitBreaker.allow() / record_success() / record_failure(). State: closed/open/half_open.' },
  { name: 'audit/event helpers', level: 'project', blurb: 'AuditWriter.write() with hash chain + fail_closed per call. EventProducer for Kafka.' },
  { name: 'draft persistence + replay', level: 'project', blurb: 'PostgresDraftStore for durable drafts. DraftReplayWorker sweeps + retries.' },
  { name: 'MCP client/server wrappers', level: 'project', blurb: 'mcp/client.py + mcp/server_common.py — shared scope enforcement, idempotency, OTel.' },
  { name: 'request correlation propagation', level: 'project', blurb: 'CorrelationIdMiddleware reads/sets X-Correlation-ID. Threads through every log + audit + span.' },
  { name: 'observability helpers', level: 'project', blurb: 'libs/py/documind_core/observability.py — setup_observability + per-instrumentation helpers.' },
];

// ---- Inline SVG flowcharts ------------------------------------------------

function AsyncFanoutFlowchart() {
  // RAG request: parallel async fan-out for retrieval + auth + LLM call.
  // Demonstrates: gather, breakers, fallback path.
  return (
    <svg
      viewBox="0 0 720 280"
      style={{ width: '100%', maxWidth: 720, height: 'auto' }}
      role="img"
      aria-label="Async fan-out flow for a RAG request"
    >
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
        </marker>
      </defs>
      {/* Request entry */}
      <rect x="10" y="120" width="100" height="40" rx="6" fill="#dbeafe" stroke="#1e3a8a" />
      <text x="60" y="145" textAnchor="middle" fontSize="13" fill="#1e3a8a">Request</text>
      {/* Auth + tenant ctx */}
      <rect x="140" y="120" width="120" height="40" rx="6" fill="#fef3c7" stroke="#b45309" />
      <text x="200" y="145" textAnchor="middle" fontSize="12" fill="#b45309">Auth + tenant</text>
      <line x1="110" y1="140" x2="140" y2="140" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* gather() fan-out */}
      <rect x="290" y="120" width="120" height="40" rx="6" fill="#ecfdf5" stroke="#065f46" />
      <text x="350" y="145" textAnchor="middle" fontSize="12" fill="#065f46">asyncio.gather</text>
      <line x1="260" y1="140" x2="290" y2="140" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* Three parallel branches */}
      <rect x="450" y="40" width="140" height="40" rx="6" fill="#f1f5f9" stroke="#475569" />
      <text x="520" y="65" textAnchor="middle" fontSize="12" fill="#0f172a">Vector retrieval</text>
      <rect x="450" y="120" width="140" height="40" rx="6" fill="#f1f5f9" stroke="#475569" />
      <text x="520" y="145" textAnchor="middle" fontSize="12" fill="#0f172a">Graph traversal</text>
      <rect x="450" y="200" width="140" height="40" rx="6" fill="#f1f5f9" stroke="#475569" />
      <text x="520" y="225" textAnchor="middle" fontSize="12" fill="#0f172a">Cache lookup</text>
      <line x1="410" y1="140" x2="450" y2="60" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      <line x1="410" y1="140" x2="450" y2="140" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      <line x1="410" y1="140" x2="450" y2="220" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      {/* Aggregate → LLM */}
      <rect x="610" y="120" width="100" height="40" rx="6" fill="#ede9fe" stroke="#5b21b6" />
      <text x="660" y="145" textAnchor="middle" fontSize="12" fill="#5b21b6">LLM call</text>
      <line x1="590" y1="60" x2="610" y2="135" stroke="#475569" strokeWidth="1.2" markerEnd="url(#arrow)" />
      <line x1="590" y1="140" x2="610" y2="140" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow)" />
      <line x1="590" y1="220" x2="610" y2="145" stroke="#475569" strokeWidth="1.2" markerEnd="url(#arrow)" />
    </svg>
  );
}

function CoroutineLifecycle() {
  // States a coroutine moves through under the asyncio loop.
  return (
    <svg
      viewBox="0 0 720 200"
      style={{ width: '100%', maxWidth: 720, height: 'auto' }}
      role="img"
      aria-label="asyncio coroutine lifecycle"
    >
      <defs>
        <marker
          id="arrow2"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
        </marker>
      </defs>
      <rect x="10" y="80" width="120" height="40" rx="6" fill="#dbeafe" stroke="#1e3a8a" />
      <text x="70" y="105" textAnchor="middle" fontSize="13" fill="#1e3a8a">async def f()</text>
      <rect x="160" y="80" width="120" height="40" rx="6" fill="#fef3c7" stroke="#b45309" />
      <text x="220" y="105" textAnchor="middle" fontSize="12" fill="#b45309">create_task()</text>
      <line x1="130" y1="100" x2="160" y2="100" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
      <rect x="310" y="80" width="120" height="40" rx="6" fill="#fce7f3" stroke="#7c2d12" />
      <text x="370" y="105" textAnchor="middle" fontSize="12" fill="#7c2d12">pending → running</text>
      <line x1="280" y1="100" x2="310" y2="100" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
      <rect x="460" y="40" width="120" height="40" rx="6" fill="#ecfdf5" stroke="#065f46" />
      <text x="520" y="65" textAnchor="middle" fontSize="12" fill="#065f46">await → suspend</text>
      <rect x="460" y="120" width="120" height="40" rx="6" fill="#fee2e2" stroke="#7f1d1d" />
      <text x="520" y="145" textAnchor="middle" fontSize="12" fill="#7f1d1d">cancel()</text>
      <line x1="430" y1="100" x2="460" y2="60" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
      <line x1="430" y1="100" x2="460" y2="140" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
      <rect x="610" y="80" width="100" height="40" rx="6" fill="#ede9fe" stroke="#5b21b6" />
      <text x="660" y="105" textAnchor="middle" fontSize="12" fill="#5b21b6">done</text>
      <line x1="580" y1="60" x2="610" y2="95" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
      <line x1="580" y1="140" x2="610" y2="105" stroke="#475569" strokeWidth="1.5" markerEnd="url(#arrow2)" />
    </svg>
  );
}

function ImplementationSteps({ steps }: { steps: string[] }) {
  return (
    <div style={{ padding: '8px 12px' }}>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#1f2937' }}>
        Sequential steps to implement
      </div>
      <ol style={{ margin: 0, paddingLeft: 18, color: '#374151', fontSize: 13, lineHeight: 1.6 }}>
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </div>
  );
}

export default function PythonPage() {
  const [search, setSearch] = useState('');
  const [activeLevel, setActiveLevel] = useState<'all' | Level>('all');

  const filtered = TOPICS.filter((t) => {
    if (activeLevel !== 'all' && t.level !== activeLevel) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        t.name.toLowerCase().includes(q) || t.blurb.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Group by level for rendering
  const byLevel = (Object.keys(LEVELS) as Level[]).map((level) => ({
    level,
    topics: filtered.filter((t) => t.level === level),
  })).filter((g) => g.topics.length > 0);

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Python concepts for RAG + backend</h1>
          <p className="page-subtitle">
            From core syntax to coroutine internals. Each topic carries a
            short "what" and where it shows up in this codebase. Filter by
            level or search the catalog.
          </p>
        </div>
      </div>

      {/* Flowcharts up top — the visual half. */}
      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Async fan-out: RAG request lifecycle</strong>
          <div className="field-help">
            One request → auth → <code>asyncio.gather</code> over vector +
            graph + cache → LLM call. Parallel IO bounds latency to the
            slowest leg, not the sum.
          </div>
        </div>
        <AsyncFanoutFlowchart />
      </div>

      <div className="card">
        <div className="card-header" style={{ marginBottom: 12 }}>
          <strong>Coroutine state machine</strong>
          <div className="field-help">
            <code>async def</code> creates a coroutine; <code>create_task</code>
            schedules it on the event loop; <code>await</code> suspends until
            the awaitable completes. Cancellation propagates as a
            <code>CancelledError</code>.
          </div>
        </div>
        <CoroutineLifecycle />
      </div>

      {/* Filter / search controls. */}
      <div
        className="card"
        style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="field-help">Level</span>
          <select
            value={activeLevel}
            onChange={(e) => setActiveLevel(e.target.value as 'all' | Level)}
            style={{
              padding: '4px 8px',
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          >
            <option value="all">all</option>
            {(Object.keys(LEVELS) as Level[]).map((l) => (
              <option key={l} value={l}>
                {LEVELS[l].title}
              </option>
            ))}
          </select>
        </label>
        <input
          type="text"
          placeholder="search topic name / description"
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

      {/* Topic groups. */}
      {byLevel.map(({ level, topics }) => (
        <div key={level} className="card">
          <div
            className="card-header"
            style={{ marginBottom: 12, borderLeft: `4px solid ${LEVELS[level].tone}`, paddingLeft: 8 }}
          >
            <strong style={{ color: LEVELS[level].tone }}>
              {LEVELS[level].title}
            </strong>{' '}
            <span className="field-help">({topics.length})</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 200 }}>Topic</th>
                  <th>What it is</th>
                  <th style={{ width: 220 }}>Where in this repo</th>
                  <th style={{ width: 110 }}>Deep dive</th>
                </tr>
              </thead>
              <tbody>
                {topics.map((t) => (
                  <Fragment key={`${t.level}::${t.name}`}>
                    <tr>
                      <td>
                        <code style={{ color: '#b91c1c', fontWeight: 700 }}>{t.name}</code>
                      </td>
                      <td>{t.blurb}</td>
                      <td>
                        {t.whereInRepo ? (
                          <code style={{ fontSize: 12 }}>{t.whereInRepo}</code>
                        ) : (
                          <span className="field-help">—</span>
                        )}
                      </td>
                      <td>
                        {t.deepSlug ? (
                          <Link
                            href={`/admin/python/deep#${t.deepSlug}`}
                            style={{ color: '#1e3a8a', fontSize: 13 }}
                          >
                            Open →
                          </Link>
                        ) : (
                          <span className="field-help">—</span>
                        )}
                        </td>
                      </tr>
                    {/* Inline flowchart row when the topic has one. Spans all
                        4 columns; renders the same self-hosted Mermaid
                        component as the deep pages. */}
                    <tr key={`${t.level}::${t.name}::flow`}>
                      <td colSpan={4} style={{ padding: 0 }}>
                        <div style={{ padding: 8, backgroundColor: '#f9fafb' }}>
                          <div style={{ fontWeight: 600, margin: '0 0 8px 0', color: '#1f2937' }}>
                            Flowchart
                          </div>
                          <Mermaid chart={resolveFlowchart(t)} />
                        </div>
                      </td>
                    </tr>
                    <tr key={`${t.level}::${t.name}::sequence`}>
                      <td colSpan={4} style={{ padding: 0 }}>
                        <div style={{ padding: 8, backgroundColor: '#f8fafc', borderTop: '1px solid #e5e7eb' }}>
                          <div style={{ fontWeight: 600, margin: '0 0 8px 0', color: '#1f2937' }}>
                            Sequence diagram
                          </div>
                          <Mermaid chart={resolveSequence(t)} />
                        </div>
                      </td>
                    </tr>
                    <tr key={`${t.level}::${t.name}::steps`}>
                      <td colSpan={4} style={{ padding: 0 }}>
                        <div style={{ backgroundColor: '#ffffff', borderTop: '1px solid #e5e7eb' }}>
                          <ImplementationSteps steps={resolveImplementationSteps(t)} />
                        </div>
                      </td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}
