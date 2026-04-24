/**
 * 36 RAG-specific microservice scenarios organized by 10 layers.
 *
 * Rendered by /tools/rag-scenarios. Each scenario feeds the shared
 * DerivedRows renderer so every card gets flowchart / sequence /
 * data-flow / network-flow / IPO / pros / cons / comparison / 5W /
 * limitations / recommendations / best practices / interview —
 * one topic per row.
 */

export type RagScenario = {
  id: number;
  layer: string;
  name: string;
  problem: string;
  solution: string;
  example: string;
  docsUrl?: string;
};

export const RAG_SCENARIOS: RagScenario[] = [
  // -------- 1. Ingestion (1–3) ------------------------------------------
  {
    id: 1, layer: 'Ingestion', name: 'Document Upload & Processing',
    problem: 'User uploads a PDF; the system must parse, chunk, embed, and index it without blocking the upload response.',
    solution: 'Signed-URL upload to MinIO → emit Kafka event → ingestion-svc runs parse → chunk → embed saga → writes to Qdrant + Postgres.',
    example: 'POST /api/v1/documents returns 202 + document_id immediately. Saga transitions: uploaded → parsing → chunking → embedding → indexing → active.',
    docsUrl: 'https://microservices.io/patterns/data/saga.html',
  },
  {
    id: 2, layer: 'Ingestion', name: 'Multi-source Enterprise Ingestion',
    problem: 'Docs live in SharePoint / Confluence / Drive; one-off copy leads to drift.',
    solution: 'MCP adapters pull + normalize from each source; chunk + embed; tag with tenant + department + source metadata; store original blob + parsed text in MinIO.',
    example: 'mcp/server_sharepoint.py provides a Source tool; ingestion-svc consumes; retries + CB on API flakes; checkpoint on partial failure.',
    docsUrl: 'https://modelcontextprotocol.io',
  },
  {
    id: 3, layer: 'Ingestion', name: 'Incremental Re-indexing',
    problem: 'A document changes; re-embedding the whole corpus is wasteful and produces stale vectors in the interim.',
    solution: 'Compute per-chunk content hash; re-chunk + re-embed only changed chunks; shadow-index via embedding_version stamp.',
    example: 'ChunkRepo.stamp_embedding_model + shadow collection in Qdrant; read flips via feature flag once quality gate passes.',
    docsUrl: 'https://qdrant.tech/documentation/tutorials/aliases/',
  },

  // -------- 2. Retrieval (4–6) ------------------------------------------
  {
    id: 4, layer: 'Retrieval', name: 'Hybrid Retrieval (vector + keyword)',
    problem: 'Vector-only retrieval misses exact-match terms; keyword-only misses semantic matches.',
    solution: 'Parallel Qdrant ANN + BM25 keyword; reciprocal rank fusion; cross-encoder rerank top-20 → top-5.',
    example: 'retrieval-svc/app/services/hybrid_retriever.py. Empty vector hits → fallback to keyword. Slow rerank → skip + log.',
    docsUrl: 'https://arxiv.org/abs/2212.09156',
  },
  {
    id: 5, layer: 'Retrieval', name: 'Tenant-aware Retrieval (RLS for vectors)',
    problem: 'One wrong filter = cross-tenant data leak — same class of bug as RLS bypass.',
    solution: 'Extract tenant_id from JWT at the gateway; enforce Qdrant payload filter {must: {tenant_id}}; enforce Postgres RLS app.current_tenant; never accept raw filter from client.',
    example: 'QdrantRepo API has no way to query without tenant_id. Verified by libs/py/tests/test_rls_isolation.py against live DB.',
    docsUrl: 'https://www.postgresql.org/docs/current/ddl-rowsecurity.html',
  },
  {
    id: 6, layer: 'Retrieval', name: 'Graph-augmented Retrieval',
    problem: 'Multi-hop questions ("clauses mentioning entity A AND entity B") fail under pure ANN.',
    solution: 'ANN retrieves top chunks; Neo4j traverses 1-hop neighbours (:Chunk)-[:MENTIONS]->(:Entity); merge with MMR.',
    example: 'GraphSearcher alongside VectorSearcher; Neo4j CB protects caller when graph slow.',
    docsUrl: 'https://neo4j.com/docs/cypher-manual/',
  },

  // -------- 3. Inference (7–10) -----------------------------------------
  {
    id: 7, layer: 'Inference', name: 'Standard Grounded RAG Answer',
    problem: 'LLM hallucinates without source grounding.',
    solution: 'Pack top-K chunks into prompt with explicit instructions to cite; constrained decoding emits [doc_id, chunk_id] per fact.',
    example: 'inference-svc + PromptBuilder; citations validated by governance before response returns.',
    docsUrl: 'https://docs.ragas.io/',
  },
  {
    id: 8, layer: 'Inference', name: 'Model Fallback (CB + cheaper tier)',
    problem: 'Premium model slow / down; user should still get an answer.',
    solution: 'CB wraps premium call; on OPEN state, route to smaller local model (llama3) with same prompt.',
    example: 'inference-svc/breakers.py — if ollama CB is OPEN, TokenCB decides downgrade; logged as model_fallback=true.',
    docsUrl: 'https://martinfowler.com/bliki/CircuitBreaker.html',
  },
  {
    id: 9, layer: 'Inference', name: 'Streaming Response',
    problem: 'Synchronous responses feel unresponsive for long generations.',
    solution: 'Stream tokens via Server-Sent Events; CCB watches the stream for repetition / drift / jailbreak; can BLOCK mid-generation.',
    example: 'inference-svc streaming endpoint; CCB (libs/py/documind_core/ccb.py) emits interrupt on repetition threshold.',
    docsUrl: 'https://arxiv.org/abs/2604.13417',
  },
  {
    id: 10, layer: 'Inference', name: 'Context Window Optimization',
    problem: 'Top-K chunks overflow the model context window or blow the token budget.',
    solution: 'Greedy pack highest-score chunks until budget; compress low-score chunks via map-reduce summary; drop on overflow.',
    example: 'Context builder in retrieval-svc sizes against (window - prompt - reserve). Token CB pre-checks budget.',
    docsUrl: 'https://arxiv.org/abs/2307.03172',
  },

  // -------- 4. MCP / Agent (11–14) --------------------------------------
  {
    id: 11, layer: 'MCP / Agent', name: 'Tool Invocation via MCP',
    problem: 'Answering isn\'t enough — users want actions ("create a ticket for this").',
    solution: 'Agent declares MCP tool use; MCP client calls declared server; server executes against ITSM.',
    example: 'mcp/client.py + mcp/server_itsm.py; schema in mcp/schema/tool_schema.json; permission matrix per tenant.',
    docsUrl: 'https://modelcontextprotocol.io',
  },
  {
    id: 12, layer: 'MCP / Agent', name: 'Action + RAG Combined',
    problem: 'Grounded answer + real-world side effect in one flow ("look up the policy, then open a ticket with it cited").',
    solution: 'Retrieve policy → generate answer with citations → invoke MCP tool with {answer, citations} as arguments.',
    example: 'Agent flow orchestrates retrieval-svc → inference-svc → mcp client. Audit row captures every step.',
    docsUrl: 'https://www.anthropic.com/engineering/building-effective-agents',
  },
  {
    id: 13, layer: 'MCP / Agent', name: 'MCP Failure — draft-only fallback',
    problem: 'MCP server down; silently skipping the action makes users think it succeeded.',
    solution: 'Agent-Loop CB trips; return the draft action + explicit "not submitted — MCP server unavailable" marker to UI.',
    example: 'governance.hitl_queue captures draft so a human can submit once the MCP server is back.',
    docsUrl: 'https://microservices.io/patterns/reliability/circuit-breaker.html',
  },
  {
    id: 14, layer: 'MCP / Agent', name: 'Multi-tool Agent Flow (search → compute → submit)',
    problem: 'Task needs sequential tools; a failure mid-way must not leave half-executed state.',
    solution: 'Orchestrated saga over MCP tool calls; compensation per step; agent-loop CB caps depth + wall-clock.',
    example: 'Tool 1: search HR doc; Tool 2: calc allowance; Tool 3: submit expense. Step 2 fail → compensate step 1 audit.',
    docsUrl: 'https://microservices.io/patterns/data/saga.html',
  },

  // -------- 5. Governance (15–17) ---------------------------------------
  {
    id: 15, layer: 'Governance', name: 'Policy Enforcement (RBAC + ABAC)',
    problem: 'Finance department shouldn\'t see HR docs, even when retrieval happens to surface them.',
    solution: 'Policy engine evaluates (user, resource, action) triple per decision; filters retrieval results; logs allow/deny.',
    example: 'governance.policies table + CEL expressions; decision audit row with policy_version + evaluated_inputs.',
    docsUrl: 'https://www.openpolicyagent.org/docs/latest/',
  },
  {
    id: 16, layer: 'Governance', name: 'Human-in-the-Loop',
    problem: 'Low-confidence or high-impact answers need human approval before they ship.',
    solution: 'Confidence + policy gates queue request in governance.hitl_queue; reviewer resolves; user gets partial response + status.',
    example: 'Confidence < 0.7 OR policy="sensitive" → HITL; reviewer UI in governance-svc; SLA alert on pending > N minutes.',
    docsUrl: 'https://ai.google.dev/responsible/docs/human-oversight',
  },
  {
    id: 17, layer: 'Governance', name: 'Output Guardrail (PII scan)',
    problem: 'Model might hallucinate or leak PII in the response.',
    solution: 'ResponsibleAIChecker + PIIScanner scan the output pre-emit; fail-closed → redact or block + audit.',
    example: 'ai_governance.py scanners; unresolved = HITL; per-tenant opt-in for "we handle PII" policies.',
    docsUrl: 'https://microsoft.github.io/presidio/',
  },

  // -------- 6. Evaluation (18–20) ---------------------------------------
  {
    id: 18, layer: 'Evaluation', name: 'Offline Evaluation (golden dataset)',
    problem: 'Without a frozen evaluation set, you can\'t tell if a prompt/model change is progress or regression.',
    solution: 'Golden dataset of (question, expected_sources, expected_answer); run queries; compute precision@k, nDCG, faithfulness.',
    example: 'evaluation-svc POST /api/v1/evaluation/run; results stored in eval schema; CI gates merges on regression > 5%.',
    docsUrl: 'https://docs.ragas.io/',
  },
  {
    id: 19, layer: 'Evaluation', name: 'Online Evaluation (production sampling)',
    problem: 'Offline eval can\'t predict long-tail queries; real traffic exposes drift.',
    solution: 'Sampling consumer reads small % of live responses; scores against heuristics or LLM-judge; pushes drift metrics.',
    example: 'Kafka consumer tied to query.served events; flagged failures tipped into eval.feedback for human review.',
    docsUrl: 'https://www.anthropic.com/news/evaluating-ai-systems',
  },
  {
    id: 20, layer: 'Evaluation', name: 'Regression Gate (CI)',
    problem: 'Prompt/model change shipped; quality silently regressed.',
    solution: 'CI job runs eval against the new config; compares to last-green baseline; fails on drop > threshold per metric.',
    example: '.github/workflows/eval.yml reads evaluation-svc output; blocks merge if precision@5 drops > 5% or faithfulness > 3%.',
    docsUrl: 'https://ai.google/responsibility/principles/',
  },

  // -------- 7. FinOps (21–23) -------------------------------------------
  {
    id: 21, layer: 'FinOps', name: 'Token Tracking per Query',
    problem: 'Without per-query cost data, capacity and billing are guesses.',
    solution: 'inference-svc emits token-usage event on every call: {tenant, model, prompt_tokens, completion_tokens, cost_usd}.',
    example: 'finops.token_usage table partitioned daily; Grafana panel $/tenant/day; alert at 80% of budget.',
    docsUrl: 'https://cloud.google.com/architecture/ai-ml/cost-optimization-generative-ai',
  },
  {
    id: 22, layer: 'FinOps', name: 'Budget Enforcement',
    problem: 'A bad prompt can run up a $1000 bill in an hour.',
    solution: 'Token CB checks per-tenant running spend; decision allow / throttle / block based on policy tier.',
    example: 'TokenCircuitBreaker in libs/py/documind_core/breakers.py; returns TokenBreakerDecision.BLOCK over budget.',
    docsUrl: 'https://www.finops.org/framework/',
  },
  {
    id: 23, layer: 'FinOps', name: 'Cost Optimization (cache + cheaper model)',
    problem: 'Same question asked twice costs twice.',
    solution: 'Answer cache with sha256(tenant || question || model_version); ~30% hit rate at steady-state; degrade to cheaper model when budget tightens.',
    example: 'Cache key namespace per tenant; never cache PII responses; cache-busting on content-change events.',
    docsUrl: 'https://redis.io/docs/manual/eviction/',
  },

  // -------- 8. Observability (24–27) ------------------------------------
  {
    id: 24, layer: 'Observability', name: 'End-to-End Trace',
    problem: 'Cross-service debugging requires threading a single request across gateway → retrieval → inference → MCP.',
    solution: 'W3C traceparent propagation at every hop; correlation-id header; OTel spans on every boundary; Observability CB around the exporter.',
    example: 'One request_id shows 4 spans in Jaeger; Kibana KQL correlation_id:"xyz" returns every log line.',
    docsUrl: 'https://www.w3.org/TR/trace-context/',
  },
  {
    id: 25, layer: 'Observability', name: 'Circuit Breaker Monitoring',
    problem: 'A silently OPEN breaker is as bad as no breaker.',
    solution: 'Each breaker emits state gauge (0 closed / 1 half_open / 2 open) + opens/rejections/failures counters; Grafana panel per breaker; alert on OPEN > 5 min.',
    example: 'documind_circuit_breaker_* metrics; Alertmanager → PagerDuty with runbook URL.',
    docsUrl: 'https://prometheus.io/docs/practices/alerting/',
  },
  {
    id: 26, layer: 'Observability', name: 'Latency SLO Monitoring',
    problem: 'Averages hide the slow tail where users actually live.',
    solution: 'Histograms with explicit buckets covering p50/p95/p99; burn-rate alerts on multi-window error-budget depletion.',
    example: 'observability.slo_targets seeds 4 SLOs (availability, p95 latency, precision, faithfulness); Prom alerts.',
    docsUrl: 'https://sre.google/sre-book/monitoring-distributed-systems/',
  },
  {
    id: 27, layer: 'Observability', name: 'Failure Replay',
    problem: 'A production bug you can\'t reproduce is a bug you can\'t fix.',
    solution: 'Capture failed request envelope + correlation context to a replay bucket; reproduce locally against a stub.',
    example: 'governance-svc stores DLQ + HITL-queued requests with full context so they can be re-run in dev.',
    docsUrl: 'https://www.confluent.io/blog/event-sourcing-using-apache-kafka/',
  },

  // -------- 9. Resilience (28–32) ---------------------------------------
  {
    id: 28, layer: 'Resilience', name: 'Vector DB Down → keyword fallback',
    problem: 'Qdrant outage tanks every query if retrieval is vector-only.',
    solution: 'Retrieval CB detects Qdrant OPEN; degrade to Postgres full-text / BM25; label response with degraded=true.',
    example: 'retrieval-svc/hybrid_retriever.py detects CB state; UI shows "results may be less accurate" banner.',
    docsUrl: 'https://martinfowler.com/bliki/CircuitBreaker.html',
  },
  {
    id: 29, layer: 'Resilience', name: 'LLM Down → cached or smaller model',
    problem: 'Ollama/vLLM down blocks every answer.',
    solution: 'Inference CB OPEN; serve cached answer if hit; else route to smaller local model; else return "service busy".',
    example: 'Inference-svc cascades: ollama primary → ollama fallback (tiny) → cache → degraded-response envelope.',
    docsUrl: 'https://qdrant.tech/articles/serverless-cost-optimization/',
  },
  {
    id: 30, layer: 'Resilience', name: 'MCP Down → disable actions, keep Q&A',
    problem: 'MCP outage shouldn\'t kill the read-only Q&A path.',
    solution: 'MCP CB isolates action path; Q&A flows ignore MCP state; UI greys out action buttons with tooltip.',
    example: 'Action endpoints return 503 with Retry-After; read endpoints unaffected.',
    docsUrl: 'https://microservices.io/patterns/reliability/bulkhead.html',
  },
  {
    id: 31, layer: 'Resilience', name: 'Kafka Down → sync logging path',
    problem: 'Kafka outage halts audit + eval + billing pipelines.',
    solution: 'Producer writes to outbox table synchronously (always); relay switches to "drain via HTTP to downstream" fallback; backpressure only ingestion.',
    example: 'libs/py/documind_core/outbox.py + kafka_client.py with fallback HTTP sink. Outbox never blocks user requests.',
    docsUrl: 'https://microservices.io/patterns/data/transactional-outbox.html',
  },
  {
    id: 32, layer: 'Resilience', name: 'Redis Down → cache disabled, app continues',
    problem: 'Cache outage should degrade latency, not kill availability.',
    solution: 'Cache wrapper catches Redis timeouts; returns miss; always falls through to source; background alert fires.',
    example: 'Cache.get returns None on CB OPEN; load path executes; p95 spikes but no 5xx.',
    docsUrl: 'https://redis.io/topics/sentinel',
  },

  // -------- 10. System Design (33–36) -----------------------------------
  {
    id: 33, layer: 'System Design', name: 'High Traffic Surge (100K users)',
    problem: 'Launch spike crushes capacity model.',
    solution: 'HPA on custom metric (inference_inflight); gateway rate-limit per tenant; cache absorbs reads; Token CB throttles spend; Kafka queues writes.',
    example: 'Locust scenario hitting 100K RPS; HPA scales inference-svc 3→20 pods; cache hit ratio moves from 30% to 60% under load.',
    docsUrl: 'https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/',
  },
  {
    id: 34, layer: 'System Design', name: 'Multi-tenant Isolation',
    problem: 'One tenant reading another\'s data is a breach.',
    solution: 'Four layers: Postgres FORCE RLS + role separation; Qdrant payload filter tenant_id; Redis keys tenant-namespaced; logs filterable by tenant.',
    example: 'test_rls_isolation.py passes against live PG: tenant A cannot read tenant B. Proven, not assumed.',
    docsUrl: 'https://www.postgresql.org/docs/current/ddl-rowsecurity.html',
  },
  {
    id: 35, layer: 'System Design', name: 'Real-time Agent System',
    problem: 'Agents must execute multi-step tools with bounded risk.',
    solution: 'Agent-Loop CB (depth + wall-clock); Cognitive CB on stream; tool allowlist per tenant/role; HITL escalation for high-risk; kill-switch flag.',
    example: 'MultiHopRagAgent trips breakers at depth > 5 or wall-clock > 30s; HITL queue surfaces the interrupted state.',
    docsUrl: 'https://www.anthropic.com/engineering/building-effective-agents',
  },
  {
    id: 36, layer: 'System Design', name: 'Disaster Recovery / Regional Failover',
    problem: 'Region outage = product outage.',
    solution: 'Active-passive initially: backups PITR to region B; DNS failover; Kafka MirrorMaker for cross-region events. Active-active later.',
    example: 'RPO < 15 min, RTO < 1 h for critical tier. Quarterly drill: fail over to region B, verify SLOs hold.',
    docsUrl: 'https://learn.microsoft.com/en-us/azure/well-architected/reliability/disaster-recovery',
  },
];

export const LAYER_ORDER = [
  'Ingestion',
  'Retrieval',
  'Inference',
  'MCP / Agent',
  'Governance',
  'Evaluation',
  'FinOps',
  'Observability',
  'Resilience',
  'System Design',
];
