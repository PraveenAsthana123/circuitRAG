# 6-plane architecture audit — 2026-05-04

> Operator's brutal final rule: "Do not build agent council only. Build:
> Agent Council + Control Plane + Evaluation Plane + Security Plane +
> Observability Plane + Recovery Plane."
>
> This doc maps current state vs the 6-plane spec and ranks the gaps.

## The 3-tool minimum (operator-supplied)

| Tool | Status | Notes |
|------|--------|-------|
| **LangGraph** | ✅ installed | Not yet wired into Gemma council (manual orchestration today) |
| **LlamaIndex** | ✅ installed | Not yet wired into ingestion-svc |
| **LangSmith** | ✅ just installed | Paid SaaS — Langfuse (✅ self-hosted) is the open-source equivalent already installed |

## Plane-by-plane state

### 1. Agent Plane (this is the COUNCIL)

| Component | Tool | State | Drill |
|-----------|------|-------|-------|
| 5-role Gemma council | scripts/gemma_agent_council.py | ✅ Stage-1 + live-smoke 5/5 | drill_gemma_agent_council_stage1 |
| 3-model author/reviewer/advisor | scripts/local_council.py | ✅ wired | drill_council_polisai_gate |
| Intent router | scripts/agent_router.py | ✅ Stage-2 (Ollama + heuristic fallback) | drill_agent_router_stage2_ollama |
| Apply pre-flight | scripts/local_council.py:_git_apply_check_only | ✅ Tier 1.3.b | drill_apply_check_preflight |

**Gap:** LangGraph DAG rewrite of Gemma council (Stage-2). Today's council
orchestrates manually; LangGraph would give retries, branching, durable
state. Composing with Temporal would give crash-safe long-running flows.

### 2. Control Plane (governance + permissions)

| Component | Tool | State |
|-----------|------|-------|
| Agent registry | (not built) | ❌ gap |
| Model registry | MLflow (✅ installed); LangSmith (✅) | ⚠ not wired |
| Prompt registry | LangSmith / Langfuse (✅) | ⚠ versioning lives in inference-svc/app/schemas |
| Tool registry | mcp/server_*.py (✅ 9 servers) | ✅ |
| Permission engine | OPA (✅ installed); PolisAI eval (✅ wired) | ✅ |
| Human approval gate | Sidecar advisor + `/admin/drafts` | ✅ wired |
| Policy engine | OPA + JSON↔Rego sync (✅) | ✅ |
| Secrets management | Vault 1.18.0 (✅ installed) | ⚠ not initialized; .env files still |
| Sandbox execution | Docker (✅) + Paperclip Stage-3 sandbox | ✅ |
| Multi-tenant isolation | tenant_id on every DB/Qdrant write | ✅ |

**Biggest gap:** **agent registry + model registry wiring**. We have
MLflow installed but no models registered yet. Per the user's spec,
this is the "control plane" that says "which agent exists, version,
owner, capability."

### 3. Evaluation Plane

| Component | Tool | State |
|-----------|------|-------|
| RAG eval | RAGAS (✅), DeepEval (✅), TruLens (not installed) | ⚠ not wired |
| Empirical apply-rate retest | scripts/empirical_apply_test.py | ✅ wired |
| Eval dataset | (golden questions) | ❌ not curated |
| Regression testing | drill catalog (✅ 338 drills) | ✅ partial |
| Decision audit | .loop/*audit.jsonl (5 surfaces) | ✅ wired |

**Biggest gap:** RAGAS / DeepEval **not wired into evaluation-svc**. Both
installed, but no test harness exists yet. Per docs/architecture/
rag-deep-test-2026-05-04.md the empirical baseline is now measured —
RAGAS would automate the per-query scoring.

### 4. Security Plane

| Component | Tool | State |
|-----------|------|-------|
| CONTENT safety | shieldgemma:2b/9b via Gemma council | ✅ Stage-1 |
| ACTOR safety (PolisAI) | scripts/policy_check.py | ✅ wired |
| TRANSPORT safety (MCP gate) | scripts/mcp_gateway.py | ✅ wired |
| APPLY safety | Tier 1.3.b apply-check pre-flight | ✅ wired |
| **PII redaction** | Presidio (✅ installed + Stage-1 adapter shipped this commit) | ⚠ not wired |
| Rate limiting | ingestion-svc 10/window/tenant; retrieval-svc | ✅ wired |
| Circuit breaker | libs/py/documind_core/circuit_breaker.py | ✅ wired |
| Secrets | Vault binary present (✅) | ⚠ not initialized |
| Container scan | Trivy 0.70.0 (✅) | ⚠ not in CI |
| SBOM | Syft 1.44.0 (✅) | ⚠ not in CI |
| Image signing | Cosign 2.4.0 (✅) | ⚠ not in CI |
| Policy-as-code | OPA 0.68.0 + Conftest 0.55.0 (✅); Rego scaffold (✅) | ⚠ Stage-3 swap pending |
| Red-team tests | drill_polisai_*.py (✅ negative-deny drills) | ⚠ no formal prompt-injection corpus |

**Biggest gap:** **PII redaction not wired into ingestion + inference**.
Stage-1 adapter shipped this commit. Stage-2 wires:
1. Ingestion: redact BEFORE chunking → no PII in vector DB
2. Inference: redact AFTER retrieval, BEFORE prompt → no PII in LLM context

### 5. Observability Plane

| Component | Tool | State |
|-----------|------|-------|
| Metrics | Prometheus 2.54.1 (✅ docker) | ✅ |
| Tracing | OTel collector + Jaeger 1.60 (✅ docker) | ✅ |
| Dashboards | Grafana 11.2.0 (✅ docker) | ✅ |
| LLM observability | Langfuse (✅ installed); LangSmith (✅ installed) | ⚠ not wired |
| Decision audit | .loop/*audit.jsonl (✅ 5 surfaces) | ✅ |
| Health pulse | /admin/health-pulse (✅ live dashboard) | ✅ |
| Drift dashboard | /admin/drift (advisory; APPROVE-rate 27.4%) | ✅ — flagged for op investigation |

**Biggest gap:** **Langfuse / LangSmith not wired into inference-svc**.
Both installed; need a hook in rag_inference.py that emits a trace per
ask call with prompt + retrieval + answer + latency. Composes with
existing OTel spans.

### 6. Recovery Plane

| Component | Tool | State |
|-----------|------|-------|
| Fallback model | OpenAI/LiteLLM (✅ installed) | ⚠ not wired |
| Cached answer | Redis + retrieval-svc cache (✅) | ✅ partial |
| Circuit breaker | libs/py/documind_core/circuit_breaker.py (✅) | ✅ wired |
| Queue system | Kafka 7.6.0 (✅ docker, healthy) | ✅ infra; not all writes go through it |
| Durable workflows | Temporal (✅ py installed) | ⚠ no Temporal server running |
| Incident runbooks | docs/runbooks/ (✅ 12 files) | ✅ partial |
| Rollback plan | git revert + docker compose down/up | ✅ documented |

**Biggest gap:** **Temporal server not deployed**. Python client
installed but no broker. Without it, long-running agent flows have no
durable state — a daemon crash mid-flow loses position.

## What this commit ships

✅ **PII redactor Stage-1 adapter** — closes the highest-impact security-plane gap

- `scripts/pii_redactor.py` — 200-line Presidio wrapper
- `mcp/tests/drill_pii_redactor_stage1.py` — 8/8 green; 6 negative
- Live smoke detected 4/5 PII entities (PERSON, EMAIL, PHONE, IP) at default threshold 0.5
- Default-deny: `PII_REDACTOR_ENABLED=1` required
- Lazy Presidio + spaCy load (~2s first call; cached)
- 9 default entity types: PERSON, EMAIL, PHONE, CREDIT_CARD, SSN, IP, IBAN, BANK_NUMBER, MEDICAL_LICENSE

✅ **LangSmith + Presidio installed** — completes the 3-tool minimum + PII gap

## Prioritized next iterations (per plane)

| Priority | Plane | Action | Effort |
|----------|-------|--------|--------|
| **P0** | Security | Wire PII redactor into ingestion-svc BEFORE chunking | 4 hrs |
| **P0** | Security | Wire PII redactor into inference-svc AFTER retrieval | 4 hrs |
| **P0** | Observability | Wire Langfuse traces into rag_inference.py | 6 hrs |
| **P1** | Agent | LangGraph DAG rewrite of gemma_agent_council (Stage-2) | 8 hrs |
| **P1** | Evaluation | RAGAS metrics runner + dashboard endpoint | 8 hrs |
| **P1** | Recovery | Temporal server in docker-compose | 4 hrs |
| **P2** | Control | MLflow model registry — register existing Ollama models | 4 hrs |
| **P2** | Security | Vault dev-mode + migrate .env secrets | 6 hrs |
| **P2** | Security | Trivy + Syft + Cosign in CI pipeline | 4 hrs |
| **P3** | Evaluation | Curate golden Q&A dataset for empirical retest | 8 hrs |

## Composes with

- `docs/architecture/gemma-agent-council.md` — agent plane
- `docs/architecture/compression-tools-audit-2026-05-04.md` — tool-table baseline
- `docs/architecture/rag-deep-test-2026-05-04.md` — empirical baseline
- `docs/architecture/techstack-install-2026-05-04.md` — install state of every tool
- §38 / §39 / §43 / §47 / §48 / §52 / §56 — all 7 architecture clauses compose here

## The brutal rule

> Don't ship the agent council without the 5 supporting planes. The
> council is the BRAIN; the planes are the SKELETON, NERVES, MUSCLE,
> SKIN, and IMMUNE SYSTEM. Today's commit ships skin (PII redaction)
> and surfaces 10 prioritized iterations to fill the rest. Each one is
> its own Stage-1 adapter + drill — the §56 6-gate process scales the
> work without losing safety.
