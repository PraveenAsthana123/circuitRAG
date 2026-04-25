# Python Runtime And Code Quality

This guide covers the Python-language and code-quality topics that most
strong backend engineers need in practice.

---

## Asyncio and concurrency

Most modern backend work is I/O-bound:

- HTTP calls
- DB and Redis access
- vector DB lookups
- tracing and audit writes

Core rules:

- `await` only helps when work is mostly waiting
- independent I/O should fan out concurrently
- concurrency must be bounded
- every boundary needs a timeout budget
- cancellation must be respected
- backpressure is required or memory and latency collapse

Use:

- `asyncio` for I/O-bound work
- threads for blocking sync I/O when needed
- processes/subprocesses for CPU-bound or unsafe work

---

## Decorators, `__call__`, protocols, and generics

These tools matter because large Python systems need pluggable behavior
without turning into inheritance mud.

Useful applications:

- decorators for logging, metrics, tracing, retries, auth, caching
- `__call__` for stateful function-like objects
- `Protocol` for clean interface boundaries
- `Generic` and `TypeVar` for reusable typed contracts

Warnings:

- decorator stacks add real debugging and control-flow cost
- closure capture bugs are common
- late binding in loops causes real bugs
- abstract only where semantics are truly shared

---

## Context propagation with `contextvars`

Use `contextvars` for cross-cutting metadata:

- correlation ID
- tenant ID
- authenticated user ID
- roles
- tracing metadata

Good rule:

- `contextvars` for ambient metadata
- explicit parameters for core business inputs

---

## Mutability, copying, aliasing, and memory behavior

Important reminders:

- assignment does not copy
- shallow copy does not duplicate nested mutable state
- mutable defaults are dangerous
- cached mutable objects can be corrupted later
- closures can retain large payloads unexpectedly

Common long-running-service retention sources:

- unbounded caches
- never-cleared task references
- queue backlog
- giant intermediates kept in memory
- registry/callback structures retaining objects too long

---

## Imports, packaging, module boundaries, and plugin architecture

Imports execute top-level code.

That means:

- import-time side effects are architectural decisions
- circular imports usually signal bad boundaries
- shared modules should stay low-level and side-effect light
- startup wiring should happen in app factories or lifespan hooks

Registry/plugin patterns are useful, but start simple:

1. dict registry
2. decorator registration
3. `__init_subclass__`
4. metaclass only if truly needed

---

## Code quality, standards, naming, and PEP 8

PEP 8 is the baseline, not the finish line.

Real code quality includes:

- readability
- consistency
- maintainability
- correctness pressure
- observability and operability
- honest failure behavior

### Naming

Prefer:

- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- explicit suffixes like `*_id`, `*_url`, `*_path`, `*_result`

Avoid:

- `data`, `obj`, `manager`, `helper`, `common`, `util`

### Good comments

Comments should explain:

- why something exists
- which invariant matters
- what tradeoff or failure mode is non-obvious

They should not narrate obvious syntax.

---

## Common mistakes and anti-patterns

Frequent failure-prone habits:

- unenforced assumptions
- duplicated control logic
- weak state transitions
- hidden side effects
- broad exception swallowing
- route handlers owning workflow logic
- import-time side effects
- generic helper sludge
- weak or misleading tests
- local convenience over system ownership

---

## Complexity, memory, time, space, and practical DSA

Algorithmic thinking matters when it stays practical.

Reason about:

- runtime growth with requests/items/chunks/events
- memory growth with backlog/batch/document size
- repeated scans, sorts, and nested loops
- top-k vs full ordering
- streaming vs materializing
- batching and queue behavior
- DB query shape and N+1 behavior

High-value structures:

- `dict` for lookup and grouping
- `set` for membership and dedupe
- bounded queues for pipelines
- heap/priority queue for top-k and scheduling

---

## Performance traps and optimization patterns

Optimize in this order:

1. fix architectural mistakes
2. measure
3. optimize queries and network round trips
4. bound concurrency and queue growth
5. batch where appropriate
6. cache where semantics allow
7. tune Python-level hot paths last

Common traps:

- CPU-heavy work on async request paths
- N+1 queries
- too much data movement
- repeated full scans/sorts
- unbounded concurrency
- wrong cache usage

---

## Good questions to ask

- Is this work I/O-bound or CPU-bound?
- Is this abstraction clarifying behavior or hiding it?
- What can mutate unexpectedly here?
- What should be streamed instead of materialized?
- Is this naming helping the reviewer understand the domain?
- Is there a simpler structure or data shape that fits the real access pattern?
