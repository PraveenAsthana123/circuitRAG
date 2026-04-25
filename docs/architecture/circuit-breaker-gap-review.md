# Circuit Breaker Gap Review

This note reviews how circuit breakers are used in the repo today, where they are clearly valuable, and where the current coverage still has gaps.

The goal is not to argue for more breakers everywhere.
It is to identify where they are already helping, where they may be missing, and where operator visibility is still weak.

## 1. Why Circuit Breakers Matter In This Repo

This project has several failure-prone dependency boundaries:

- MCP tool servers
- Ollama generation
- Ollama embeddings
- retrieval backends
- observability exporters

These are exactly the kinds of paths where repeated slow failures can become cascading failures.

The base breaker implementation is in:

- [libs/py/documind_core/circuit_breaker.py](/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py)

It provides:

- `closed`
- `open`
- `half_open`
- failure counting
- fast rejection
- recovery timeout
- Prometheus metrics

## 2. Places Where Breakers Clearly Help Today

### MCP client

The MCP client wraps remote tool calls in a breaker and degrades to draft persistence when the dependency is open or failing.

Relevant file:

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)

This is a strong use of a breaker because:

- MCP is external to the caller
- tool execution can be slow or unavailable
- degraded mode is explicitly supported
- the caller has an honest fallback path

### Ollama generation

The non-streaming Ollama client uses a breaker around `/api/chat`.

Relevant file:

- [services/inference-svc/app/services/ollama_client.py](/mnt/deepa/rag/services/inference-svc/app/services/ollama_client.py)

This helps because model-serving latency and availability are classic cascading-failure triggers.

### Query embedding

Query embedding is breaker-protected in retrieval.

Relevant file:

- [services/retrieval-svc/app/services/embedder_client.py](/mnt/deepa/rag/services/retrieval-svc/app/services/embedder_client.py)

This is useful because embedding is a hard dependency for vector retrieval.

### Observability exporter path

The repo includes an observability-oriented breaker pattern and a metrics exporter that surfaces breaker state.

Relevant file:

- [services/inference-svc/app/workers/breaker_metrics.py](/mnt/deepa/rag/services/inference-svc/app/workers/breaker_metrics.py)

This matters because telemetry should not be allowed to take down request paths.

### Retrieval quality

This repo also uses a retrieval-quality breaker, which is more advanced than simple transport failure counting.

Relevant file:

- [services/retrieval-svc/app/services/hybrid_retriever.py](/mnt/deepa/rag/services/retrieval-svc/app/services/hybrid_retriever.py)

This is useful because a retrieval system can be technically “up” while returning poor results.

## 3. Main Gaps

### Gap 1: Streaming LLM path is not breaker-protected

In the Ollama client, the streaming path is not wrapped in the same breaker model as the non-streaming path.

Relevant file:

- [services/inference-svc/app/services/ollama_client.py](/mnt/deepa/rag/services/inference-svc/app/services/ollama_client.py)

Why this matters:

- streaming requests can still tie up request work
- degraded model behavior may differ between streaming and non-streaming paths
- transport instability may surface later than in the non-streaming path

Suggested improvement:

- add an explicit streaming protection strategy
- at minimum: timeout budget, bounded concurrency, and clearer failure policy

### Gap 2: Retrieval backend transport protection may be weaker than quality protection

The hybrid retriever clearly has quality-aware protection, but the main retrieval orchestration shown does not itself demonstrate transport-level breaker wrapping around vector and graph search calls.

Relevant file:

- [services/retrieval-svc/app/services/hybrid_retriever.py](/mnt/deepa/rag/services/retrieval-svc/app/services/hybrid_retriever.py)

Why this matters:

- Qdrant or Neo4j slowness can still cause slow fan-out
- transport-level pain and quality-level pain are different failure modes
- quality breaker does not replace timeout and fail-fast dependency isolation

Suggested improvement:

- verify whether `VectorSearcher` and `GraphSearcher` already enforce timeouts/fail-fast semantics
- if not, add transport-level protection there

### Gap 3: Breaker visibility in UI is still weak

The backend exposes breaker metrics and health surfaces, but the frontend admin experience does not yet surface live breaker state.

Relevant areas:

- [services/inference-svc/app/workers/breaker_metrics.py](/mnt/deepa/rag/services/inference-svc/app/workers/breaker_metrics.py)
- [services/frontend/app/admin/page.tsx](/mnt/deepa/rag/services/frontend/app/admin/page.tsx)

Why this matters:

- operators need to see which dependency is open
- replay backlog and degraded-mode counts should correlate with breaker state
- static docs are not an operations surface

Suggested improvement:

- add admin cards for:
  - live breaker state
  - pending drafts
  - replay backlog
  - degraded action counts

### Gap 4: Breaker semantics may drift across dependency classes

This repo has:

- generic breakers
- specialized breakers
- quality-aware breakers
- observability-oriented breakers

That is not inherently bad.
But it increases the chance of semantic drift in:

- thresholds
- recovery timeouts
- what counts as failure
- what operators should expect

Suggested improvement:

- define per-dependency-class breaker policy
- keep names, thresholds, and expected operator actions explicit

### Gap 5: Breakers are per-process, not global

The base breaker model is per dependency, per process.

Relevant file:

- [libs/py/documind_core/circuit_breaker.py](/mnt/deepa/rag/libs/py/documind_core/circuit_breaker.py)

Why this matters:

- multiple pods can observe slightly different failure histories
- open/half-open behavior may appear noisy across replicas
- operator expectations must account for local state rather than assuming cluster-wide coordination

This is not necessarily a bug.
It is just an operational property that must be understood.

## 4. Suggested Priority Order

### Priority 1

- verify and strengthen transport-level protection for vector and graph backends
- define the intended strategy for the streaming Ollama path

### Priority 2

- expose live breaker state in admin UI
- connect breaker state with draft backlog and degraded counts

### Priority 3

- standardize breaker policy by dependency class
- document thresholds and operator expectations

## 5. Good Drill Coverage To Keep Or Add

High-value breaker drills include:

- open -> half_open -> closed transitions
- degraded draft fallback when MCP is open
- namespace independence across multiple MCP breakers
- worker replay behavior when a namespace breaker is open
- retrieval degradation scenarios
- streaming model failure scenarios once streaming policy is tightened

## 6. Bottom Line

Circuit breakers are useful in this repo and are already applied in meaningful places.

The strongest current uses are:

- MCP tool calls
- Ollama non-streaming generation
- embedding requests
- observability export
- retrieval quality monitoring

The main gaps are:

- no equivalent protection strategy for streaming generation
- likely incomplete transport-level fail-fast protection around retrieval backends
- weak operator visibility in the frontend
- semantic drift risk across multiple breaker styles

The project does not need “more breakers everywhere.”
It needs the current breaker usage made more uniform, more visible, and more complete on the most failure-sensitive paths.
