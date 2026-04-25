# Platform And Tooling Gap Review

This note reviews several platform and tooling components in the context of this repo:

- Istio
- API gateway
- load balancer / edge layer
- Kiali
- MCP
- A2A
- agentic framework
- Langfuse and similar services

The goal is not to recommend every trendy platform layer.
It is to identify what clearly helps this project, what is optional, and what still appears missing.

## 1. Components That Clearly Help This Project

### MCP

MCP is a strong fit for this repo.

Why:

- the system is not only answering questions
- it also performs tool or action workflows
- degraded mode and replay are already first-class concepts
- scope enforcement and audit are important

Relevant areas:

- [mcp/client.py](/mnt/deepa/rag/mcp/client.py)
- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)
- [mcp/drafts.py](/mnt/deepa/rag/mcp/drafts.py)
- [services/inference-svc/app/services/agent.py](/mnt/deepa/rag/services/inference-svc/app/services/agent.py)

Conclusion:

MCP is not optional architecture theater here.
It is part of the control plane.

### API gateway

The API gateway is clearly useful and already implemented.

Why:

- single external entrypoint
- JWT verification
- tenant and user propagation
- rate limiting
- body limits
- admin-route isolation
- downstream service routing

Relevant areas:

- [services/api-gateway/cmd/main.go](/mnt/deepa/rag/services/api-gateway/cmd/main.go)
- [services/api-gateway/internal/middleware](/mnt/deepa/rag/services/api-gateway/internal/middleware)

Conclusion:

The API gateway is load-bearing in this repo.

### Load balancer / edge layer

An edge layer in front of the gateway is useful here.

Why:

- TLS termination
- stable ingress
- edge rate limiting
- browser/static asset delivery
- cache control at the edge

Relevant area:

- [infra/nginx/nginx.conf](/mnt/deepa/rag/infra/nginx/nginx.conf)

Conclusion:

This is a good fit and already represented in the repo.

### Agentic orchestration

An agentic layer is useful in this project because the system mixes:

- retrieval
- inference
- tool or action execution
- governance-sensitive decisions

Relevant areas:

- [services/inference-svc/app/services/agent.py](/mnt/deepa/rag/services/inference-svc/app/services/agent.py)
- [services/inference-svc/app/agents/multi_hop_agent.py](/mnt/deepa/rag/services/inference-svc/app/agents/multi_hop_agent.py)

Conclusion:

Agentic logic is justified here, but it should stay bounded and observable.

## 2. Components That Help Mostly At Deployment Scale

### Istio

Istio is useful when the system is deployed as a real multi-service cluster.

Why:

- mesh-wide mTLS
- AuthorizationPolicy between services
- traffic shaping and canary behavior
- mesh telemetry

Relevant areas:

- [infra/istio](/mnt/deepa/rag/infra/istio)

Conclusion:

Istio helps this project in a real Kubernetes environment.
It is not essential for local development or a very small deployment footprint.

### Kiali

Kiali helps only if Istio is actually active.

Why:

- visualizes service-to-service traffic
- helps debug policy and mesh routing issues
- improves operator understanding of mesh behavior

Relevant area:

- [infra/kiali/kiali.yaml](/mnt/deepa/rag/infra/kiali/kiali.yaml)

Conclusion:

Useful with Istio.
Not independently important without the mesh.

## 3. Components That Are More Optional Right Now

### A2A

Agent-to-agent architecture appears more conceptual or evaluation-oriented than operationally necessary right now.

Why:

- current system value comes more from:
  - solid MCP flows
  - retrieval
  - action execution
  - governance and replay
- multi-agent coordination adds complexity quickly

Conclusion:

A2A is not the next highest-leverage investment for this repo.

## 4. Main Missing Or Underdeveloped Areas

### Missing area 1: stronger AI-specific observability surface

The repo already has observability infrastructure, but the AI-specific product visibility layer is still relatively thin.

What is present:

- Prometheus / Grafana / OTel / Jaeger oriented infra
- breaker and service metrics
- traces
- governance and audit surfaces

What still feels missing:

- prompt and completion tracing UI
- easier prompt or model version inspection
- run-level LLM debugging
- eval and feedback review workflow
- better operator visibility into AI-specific quality and cost behavior

Conclusion:

This is the most obvious platform/tooling gap.

### Missing area 2: stronger admin and operator surfaces

The backend architecture supports governance, health, and breakers, but operator UX is still thin.

Examples:

- live breaker state should be easier to see
- replay backlog and degraded counts should be visible
- policy rollout and HITL state should be more operationally accessible

Conclusion:

This is not a missing backend platform so much as a missing operational UI layer.

### Missing area 3: clearer retrieval and model behavior review surfaces

The repo has strong design intent for:

- retrieval
- RAG
- evaluation
- governance

But operator-facing review of those behaviors still appears less mature than the architectural scaffolding.

Conclusion:

This is another reason an LLM-specific observability/eval tool would help.

## 5. Langfuse And Similar Services

### Langfuse

Langfuse is a strong candidate for this repo.

Why:

- prompt and completion tracing
- token and cost tracking
- eval and feedback loops
- easier debugging of agent and RAG behavior
- useful for prompt version and run inspection

Why it fits this project:

- the repo already has agentic flows
- MCP adds tool-call complexity
- RAG adds retrieval complexity
- governance and evaluation already exist conceptually

Conclusion:

Langfuse is probably the highest-value missing external service in this category.

### Phoenix / Arize Phoenix

Also useful for:

- RAG observability
- retrieval and generation inspection
- evaluation and debugging

Conclusion:

A good alternative if the team prefers stronger RAG/eval-oriented tooling over a general prompt tracing product.

### LangSmith

Potentially useful if the stack leans more heavily into a LangChain-style ecosystem.

Conclusion:

Less obviously aligned than Langfuse unless the codebase shifts that direction.

### Promptfoo

Useful for:

- offline prompt regression
- CI-level prompt evaluation

Conclusion:

Good complement to runtime observability.
Not a replacement for it.

## 6. Must-Have Vs Nice-To-Have

### Must-have or already load-bearing

- MCP
- API gateway
- load balancer / edge layer
- agentic orchestration
- core observability stack

### Nice-to-have at deployment scale

- Istio
- Kiali

### Lower priority right now

- A2A runtime architecture

### Most obvious missing addition

- Langfuse-like AI observability and evaluation surface

## 7. Best Next Investments

If the goal is maximum leverage, the best next investments appear to be:

1. stronger admin and operator UI
2. live breaker, draft, replay, and degraded-mode visibility
3. Langfuse or Phoenix-style AI observability
4. tighter retrieval and evaluation surfaces
5. Istio and Kiali only when the cluster deployment actually needs them

## 8. Bottom Line

This repo already has a solid backbone for:

- service boundary enforcement
- gateway-based trust handling
- MCP control-plane behavior
- agentic orchestration
- resilience and observability

The biggest gap is not “we need more infrastructure.”
The biggest gap is:

- making AI and retrieval behavior easier to inspect
- making operators see degradation and control-plane state clearly
- avoiding premature complexity like A2A before the current single-agent and MCP surfaces are fully mature

---

## 9. How These Map To DocuMind Today

### Already shipped (load-bearing)

| Component | Where in repo | Status |
| --- | --- | --- |
| API gateway | `services/api-gateway/cmd/main.go` + `internal/middleware` | live |
| nginx edge | `data/nginx-tls/`, `data/nginx-cache/`, `data/nginx-logs/` | configured |
| MCP control plane | `mcp/server_*.py`, `mcp/client.py`, `mcp/idempotency.py` | live, drilled |
| Draft replay + audit | `mcp/drafts.py`, `libs/py/documind_core/audit.py` (hash-chained, fail_closed available) | live |
| Agent layer | `services/inference-svc/app/services/agent.py`, `app/agents/multi_hop_agent.py` | live |
| OTel + Prometheus + Jaeger | `libs/py/documind_core/observability.py`, per-service `mount_metrics_endpoint` | live |
| Circuit-breaker fleet | `libs/py/documind_core/circuit_breaker.py` (canonical, post-unification) | live |
| Quality breaker | `libs/py/documind_core/breakers.py:RetrievalCircuitBreaker` | live |
| Transport breakers (Qdrant, Neo4j) | `services/retrieval-svc/app/services/hybrid_retriever.py` | live (commit 87816d9) |

### Configured but not necessarily exercised at scale

| Component | Where | Notes |
| --- | --- | --- |
| Istio | `infra/istio/` | manifests present; mesh-up is a deployment decision |
| Kiali | `infra/kiali/kiali.yaml` | only useful when Istio is active |

### Gaps the review flagged — actionable next picks

| Gap | Severity | Suggested next step |
| --- | --- | --- |
| Operator/admin dashboard (live breaker/queue/draft state) | **high** | Wire `/api/v1/health/detailed` data into `services/frontend/app/admin/page.tsx`. ~150 LoC, one drill. |
| Langfuse-style LLM/RAG product visibility | high | Either: ship a tracing/eval doc OR integrate Langfuse SDK in `OllamaService` + `agent.py` (token + cost + prompt-version recording). |
| Streaming Ollama protection | medium | Add timeout budget + concurrency cap around `OllamaService.stream`; matches the circuit-breaker review's #2. |
| Eval workflow productization | medium | `services/evaluation-svc/` exists but the eval-run script + eval-result UI are missing. |
| Prompt + model + retrieval registry | medium | Single source of truth for "which prompt produced which audit row?" Today partially in audit `details`. |
| Cost monitoring per tenant / model / workflow | medium | No metric series; would need a token-counter middleware on inference-svc. |

### The biggest single move

**Operator admin dashboard.** Frontend's `app/admin/page.tsx` is the
operator-facing surface; backend's `/api/v1/health/detailed` already
exposes the data (breaker state per namespace + readiness flags +
recovery_timeout_s). Wiring those together turns "admin is a
placeholder" (frontend review item #3) AND "operator visibility"
(this doc's section 4) into one shipped iteration.

The data pipeline is already there:

```
/api/v1/health/detailed JSON
    → Server Component fetch in app/admin
    → table-rendered breakers + readiness
    → 5-second client-side refresh
```

Bounded next-loop pick.
