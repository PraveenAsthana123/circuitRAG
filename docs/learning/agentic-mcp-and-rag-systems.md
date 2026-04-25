# Agentic, MCP, And RAG Systems

This guide collects the agentic, MCP, control-plane, and AI/RAG-specific
topics discussed in the roadmap.

---

## Agentic systems

### Foundations

- what an agent is
- observe, reason, act, evaluate loop
- stateless vs stateful agents
- deterministic workflow vs LLM-guided workflow
- single-agent vs multi-agent setups

### Planning and execution

- task decomposition
- tool selection
- step planning vs reactive execution
- short-term vs long-term memory
- context-window management
- fallback and retry strategy

### Safety and control

- permission boundaries
- tool allowlists
- scope-based execution
- human-in-the-loop approval
- guardrails and policy checks
- auditability of agent actions

### Reliability

- idempotent actions
- recovery after partial failure
- handling unavailable tools
- degraded-mode behavior
- draft persistence as fallback
- timeout and retry discipline

### Evaluation

- tool-choice quality
- action correctness
- recovery behavior
- policy compliance
- latency and cost
- end-to-end workflow success

---

## MCP

### Foundations

- MCP client/server model
- tool abstraction
- tool discovery and catalogs
- request/response contracts
- namespace-based routing
- multi-server topology

### Tool contracts

- input schema design
- output schema design
- error envelope shape
- idempotency semantics
- side-effect classification
- compatibility/versioning expectations

### Security

- authentication
- authorization and scopes
- per-tool role requirements
- tenant propagation
- auth forwarding between hops
- tool misuse prevention

### Reliability and workflow

- retry discipline
- idempotent writes
- draft fallback under degradation
- replay and resolve flow
- multi-server failure handling
- recovery after server outage

### Observability

- tool-call metrics
- per-tool outcome labeling
- correlation IDs
- trace propagation
- audit records
- operational visibility by namespace/tool

### Testing

- contract tests
- scope enforcement tests
- error-envelope tests
- routing tests
- replay/regression tests
- drill-based workflow validation

---

## Circuit breaker

### Foundations

- why circuit breakers exist
- cascading-failure prevention
- dependency-health modeling
- closed / open / half-open states
- failure threshold
- recovery timeout

### Behavior design

- what counts as failure
- what should not count as failure
- half-open probe behavior
- fast rejection semantics
- retry interaction
- degraded-mode interaction

### Operational usage

- per-dependency breaker design
- per-process semantics
- worker-aware breaker behavior
- breaker-aware scheduling
- multi-dependency isolation
- fallback integration

### Observability

- current state metrics
- opens
- rejections
- transitions
- per-dependency visibility
- alerting on unhealthy dependencies

### Testing

- open after threshold
- fast reject while open
- half-open recovery
- half-open failure
- multi-breaker independence
- drill/chaos validation

### Architecture concerns

- avoid duplicated breaker implementations
- keep one semantic model where possible
- unify metric model across breaker types
- separate mechanism from workflow-specific policy
- centralize only where that improves clarity

---

## Combined system thinking

### Agent + MCP

- agent chooses tool, MCP executes it
- permission and scope flow
- routing across namespaces/servers
- draft persistence as agent-facing degraded path

### MCP + circuit breaker

- tool server outage handling
- fast-fail vs retry
- degraded fallback instead of repeated hammering
- breaker-aware replay and recovery behavior

### Agent + MCP + breaker

- safe multi-step agent workflows
- recovery after tool outage
- operator vs worker vs service attribution
- human approval for risky actions
- end-to-end drill coverage for composed behavior

---

## AI/RAG-specific docs, eval, and monitoring

### AI-specific documentation

- prompt versioning
- retrieval strategy docs
- chunking policy docs
- model selection docs
- governance and guardrail docs
- model cards, prompt cards, retrieval cards, component cards

### Model monitoring and eval

Track:

- retrieval quality
- faithfulness
- citation quality
- tool correctness
- latency and cost
- policy violation rate
- drift after prompt/model/retrieval changes

### Operational signals

- offline regression eval
- online quality signals
- drift monitoring
- controlled rollout, canary, and shadow comparison

---

## Repo-specific practice areas

### Agentic

- scope pre-check behavior
- denial audit and metrics
- namespace routing
- degraded action persistence

### MCP

- client error normalization
- tool catalog TTL behavior
- server scope enforcement
- multi-server routing
- draft replay and admin resolve semantics

### Circuit breaker

- client-side breaker behavior
- breaker metrics export
- breaker-aware worker scheduling
- replay under open breaker
- Prometheus/drill visibility

---

## Recommended study order

1. circuit breaker basics
2. MCP client/server contracts
3. MCP auth and scope enforcement
4. draft fallback and replay workflow
5. agentic tool-use loop
6. human-in-the-loop and policy controls
7. multi-server routing and resilience
8. evaluation and drills for the full composed system
