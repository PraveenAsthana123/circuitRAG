/**
 * 74 design areas — 67 core + CCB (E1) + 6 AI-governance extras (E2–E7).
 *
 * Mirrors `docs/design-areas/table/00-INDEX.md`. Update in lockstep if the
 * canonical table changes.
 */

export type DAStatus = 'implemented' | 'partial' | 'designed';

export type DesignArea = {
  id: string;            // "1", "E1", etc
  group: string;         // semantic grouping for the UI
  name: string;
  status: DAStatus;
  classRef: string;      // the primary class / file pointer
};

export const DESIGN_AREAS: DesignArea[] = [
  // 01 — System & Boundaries (1–8)
  { id: '1',  group: 'System & Boundaries', name: 'System Boundary', status: 'implemented', classRef: 'infra/nginx/nginx.conf + services/api-gateway/cmd/main.go' },
  { id: '2',  group: 'System & Boundaries', name: 'Responsibility Boundary', status: 'implemented', classRef: 'schema-per-service in db_client.py + migrations' },
  { id: '3',  group: 'System & Boundaries', name: 'Trust Boundary', status: 'implemented', classRef: 'documind_core/middleware.py, encryption.py, infra/istio/20-peer-authentication.yaml' },
  { id: '4',  group: 'System & Boundaries', name: 'Failure Boundary', status: 'implemented', classRef: 'documind_core/circuit_breaker.py + breakers.py (5 specialized)' },
  { id: '5',  group: 'System & Boundaries', name: 'Tenant Boundary', status: 'implemented', classRef: 'DbClient.tenant_connection + FORCE RLS migrations' },
  { id: '6',  group: 'System & Boundaries', name: 'Control Plane', status: 'partial',     classRef: 'services/governance-svc + policy tables' },
  { id: '7',  group: 'System & Boundaries', name: 'Data Plane', status: 'implemented', classRef: 'ingestion-svc, retrieval-svc, inference-svc' },
  { id: '8',  group: 'System & Boundaries', name: 'Management Plane', status: 'partial',     classRef: 'observability-svc + Prom + Grafana + Kibana + Kiali' },

  // 02 — State / Consistency / Async (9–20)
  { id: '9',  group: 'State & Async', name: 'State Model', status: 'implemented', classRef: 'DocumentRepo.ALLOWED_TRANSITIONS' },
  { id: '10', group: 'State & Async', name: 'Session State', status: 'partial',     classRef: 'documind_core.cache (Redis)' },
  { id: '11', group: 'State & Async', name: 'Agent State', status: 'partial',     classRef: 'AgentLoopCircuitBreaker + MultiHopRagAgent skeleton' },
  { id: '12', group: 'State & Async', name: 'Consistency Model', status: 'implemented', classRef: 'tenant_connection + Kafka idempotent consumers' },
  { id: '13', group: 'State & Async', name: 'Read Path vs Write Path', status: 'implemented', classRef: 'ingestion-svc (write) ≠ retrieval-svc (read)' },
  { id: '14', group: 'State & Async', name: 'Admin Path Isolation', status: 'implemented', classRef: '/api/v1/admin/* in api-gateway' },
  { id: '15', group: 'State & Async', name: 'Evaluation Path Isolation', status: 'implemented', classRef: 'evaluation-svc + eval schema' },
  { id: '16', group: 'State & Async', name: 'Sync vs Async', status: 'implemented', classRef: 'run_saga_inline flag + Kafka consumer' },
  { id: '17', group: 'State & Async', name: 'Event-Driven Design', status: 'implemented', classRef: 'documind_core/kafka_client.py + schemas/events/*.json' },
  { id: '18', group: 'State & Async', name: 'Workflow Orchestration', status: 'implemented', classRef: 'ingestion-svc/app/saga/document_saga.py' },
  { id: '19', group: 'State & Async', name: 'Compensation Logic', status: 'implemented', classRef: 'DocumentIngestionSaga._run_compensations' },
  { id: '20', group: 'State & Async', name: 'Idempotency Strategy', status: 'implemented', classRef: 'IdempotencyStore + IdempotencyMiddleware' },

  // 03 — Services (21–29)
  { id: '21', group: 'Services', name: 'Service Decomposition', status: 'implemented', classRef: '10 services; Go for IO, Python for ML' },
  { id: '22', group: 'Services', name: 'Identity Service', status: 'partial',     classRef: 'services/identity-svc (Go skeleton + proto)' },
  { id: '23', group: 'Services', name: 'Knowledge Ingestion Service', status: 'implemented', classRef: 'services/ingestion-svc' },
  { id: '24', group: 'Services', name: 'Retrieval Service', status: 'implemented', classRef: 'services/retrieval-svc' },
  { id: '25', group: 'Services', name: 'Inference Service', status: 'implemented', classRef: 'services/inference-svc' },
  { id: '26', group: 'Services', name: 'Evaluation Service', status: 'implemented', classRef: 'services/evaluation-svc' },
  { id: '27', group: 'Services', name: 'Governance Service', status: 'partial',     classRef: 'services/governance-svc (Go skeleton)' },
  { id: '28', group: 'Services', name: 'Observability Service', status: 'partial',     classRef: 'services/observability-svc (Go skeleton + alert rules)' },
  { id: '29', group: 'Services', name: 'FinOps Service', status: 'partial',     classRef: 'services/finops-svc (Go skeleton + shadow-pricing)' },

  // 04 — Contracts / Retrieval / Cache (30–42)
  { id: '30', group: 'Contracts & Retrieval', name: 'API Contract Strategy', status: 'implemented', classRef: 'REST (OpenAPI) + gRPC protos' },
  { id: '31', group: 'Contracts & Retrieval', name: 'Event Contract Strategy', status: 'implemented', classRef: 'schemas/events/*.json (CloudEvents)' },
  { id: '32', group: 'Contracts & Retrieval', name: 'Prompt Contract Strategy', status: 'implemented', classRef: 'PromptBuilder + PROMPT_TEMPLATES + governance.prompts' },
  { id: '33', group: 'Contracts & Retrieval', name: 'Output Contract Strategy', status: 'implemented', classRef: 'GuardrailChecker + CCB signals' },
  { id: '34', group: 'Contracts & Retrieval', name: 'Retrieval Schema', status: 'implemented', classRef: 'retrieval-svc/app/schemas + proto RetrievedChunk' },
  { id: '35', group: 'Contracts & Retrieval', name: 'Knowledge Lifecycle', status: 'implemented', classRef: 'document state machine (10 states)' },
  { id: '36', group: 'Contracts & Retrieval', name: 'Source Trust Model', status: 'designed',    classRef: 'spec only' },
  { id: '37', group: 'Contracts & Retrieval', name: 'Historical Knowledge Policy', status: 'designed',    classRef: 'spec only (cold-tier archive)' },
  { id: '38', group: 'Contracts & Retrieval', name: 'Index Lifecycle', status: 'partial',     classRef: 'QdrantRepo.ensure_collection + zero-downtime swap doc' },
  { id: '39', group: 'Contracts & Retrieval', name: 'Embedding Lifecycle', status: 'partial',     classRef: 'model-versioning fields; re-embed worker deferred' },
  { id: '40', group: 'Contracts & Retrieval', name: 'Cache Architecture', status: 'implemented', classRef: 'documind_core/cache.py' },
  { id: '41', group: 'Contracts & Retrieval', name: 'Cache Consistency', status: 'implemented', classRef: 'TTL + invalidate_prefix + event-driven helpers' },
  { id: '42', group: 'Contracts & Retrieval', name: 'Tenant-Aware Cache', status: 'implemented', classRef: 'Cache.tenant_key namespace' },

  // 05 — Capacity / Resilience / Release (43–55)
  { id: '43', group: 'Capacity & Release', name: 'Capacity Model', status: 'partial',     classRef: 'HPA manifests + inference_inflight metric' },
  { id: '44', group: 'Capacity & Release', name: 'Queue Strategy', status: 'implemented', classRef: 'Kafka + DLQ in kafka_client.py' },
  { id: '45', group: 'Capacity & Release', name: 'Backpressure Strategy', status: 'implemented', classRef: '4 layers: nginx → gateway → service → CB' },
  { id: '46', group: 'Capacity & Release', name: 'Database Strategy', status: 'implemented', classRef: 'Postgres schema-per-service + RLS + WAL' },
  { id: '47', group: 'Capacity & Release', name: 'Vector DB Strategy', status: 'implemented', classRef: 'QdrantRepo HNSW + scalar quantization' },
  { id: '48', group: 'Capacity & Release', name: 'Graph Strategy', status: 'implemented', classRef: 'Neo4jRepo entity-chunk-document' },
  { id: '49', group: 'Capacity & Release', name: 'HA Strategy', status: 'implemented', classRef: '2+ replicas + anti-affinity + probes' },
  { id: '50', group: 'Capacity & Release', name: 'DR Strategy', status: 'partial',     classRef: 'runbooks/DR_RUNBOOK.md; automated restore test deferred' },
  { id: '51', group: 'Capacity & Release', name: 'Multi-Region Strategy', status: 'designed',    classRef: 'design docs only' },
  { id: '52', group: 'Capacity & Release', name: 'Blast Radius Control', status: 'implemented', classRef: 'NetworkPolicy + Istio AuthorizationPolicy + tenant quotas' },
  { id: '53', group: 'Capacity & Release', name: 'Release Isolation', status: 'implemented', classRef: 'Istio VS canary + K8s rolling' },
  { id: '54', group: 'Capacity & Release', name: 'Rollback Isolation', status: 'implemented', classRef: 'kubectl rollout undo + feature-flag kill switches' },
  { id: '55', group: 'Capacity & Release', name: 'Feature Flag Strategy', status: 'partial',     classRef: 'governance.feature_flags schema; runtime client deferred' },

  // 06 — Policy / Eval / Observability (56–67)
  { id: '56', group: 'Policy & Eval', name: 'Policy-as-Code', status: 'partial',     classRef: 'governance.policies table; CEL engine deferred' },
  { id: '57', group: 'Policy & Eval', name: 'Human-in-the-Loop', status: 'partial',     classRef: 'governance.hitl_queue schema; reviewer UI deferred' },
  { id: '58', group: 'Policy & Eval', name: 'Feedback Architecture', status: 'partial',     classRef: 'eval.feedback schema; capture endpoints deferred' },
  { id: '59', group: 'Policy & Eval', name: 'Offline Evaluation', status: 'implemented', classRef: 'evaluation-svc POST /run + metrics' },
  { id: '60', group: 'Policy & Eval', name: 'Online Evaluation', status: 'designed',    classRef: 'sampling consumer not yet built' },
  { id: '61', group: 'Policy & Eval', name: 'Regression Gate', status: 'partial',     classRef: 'AIops alert rule active; compute-and-compare deferred' },
  { id: '62', group: 'Policy & Eval', name: 'Observability by Design', status: 'implemented', classRef: 'documind_core.observability + breaker-guarded exporters' },
  { id: '63', group: 'Policy & Eval', name: 'Auditability by Design', status: 'partial',     classRef: 'governance.audit_log; hash-chain writer deferred' },
  { id: '64', group: 'Policy & Eval', name: 'SLO-Driven Design', status: 'implemented', classRef: 'observability.slo_targets + Prom alerts' },
  { id: '65', group: 'Policy & Eval', name: 'Design-for-Change', status: 'implemented', classRef: 'every external dep behind an interface' },
  { id: '66', group: 'Policy & Eval', name: 'Design-for-Debuggability', status: 'implemented', classRef: '?debug=true + correlation IDs + CB metrics' },
  { id: '67', group: 'Policy & Eval', name: 'Socio-Technical', status: 'implemented', classRef: 'docs/runbooks/* + per-service ownership' },

  // 07 — AI-governance extras (E1–E7)
  { id: 'E1', group: 'AI Governance (Extras)', name: 'Cognitive Circuit Breaker', status: 'implemented', classRef: 'libs/py/documind_core/ccb.py' },
  { id: 'E2', group: 'AI Governance (Extras)', name: 'Debuggability (AI-specific)', status: 'implemented', classRef: 'InterpretabilityTrace + ?debug=true + CB snapshot' },
  { id: 'E3', group: 'AI Governance (Extras)', name: 'Explainability (XAI)', status: 'implemented', classRef: 'ai_governance.py::AIExplainer' },
  { id: 'E4', group: 'AI Governance (Extras)', name: 'Responsibility (RAI)', status: 'implemented', classRef: 'ai_governance.py::ResponsibleAIChecker' },
  { id: 'E5', group: 'AI Governance (Extras)', name: 'Secure AI', status: 'implemented', classRef: 'PromptInjectionDetector + AdversarialInputFilter + PIIScanner' },
  { id: 'E6', group: 'AI Governance (Extras)', name: 'Portability', status: 'implemented', classRef: 'interface-based; vLLM/Ollama compat; cloud-agnostic K8s' },
  { id: 'E7', group: 'AI Governance (Extras)', name: 'Interpretability (business-step)', status: 'implemented', classRef: 'ai_governance.py::InterpretabilityTrace' },
];

export const STATUS_META: Record<DAStatus, { label: string; emoji: string; cssClass: string }> = {
  implemented: { label: 'Implemented', emoji: '✅', cssClass: 'status-implemented' },
  partial:     { label: 'Partial',     emoji: '🟡', cssClass: 'status-partial' },
  designed:    { label: 'Designed',    emoji: '❌', cssClass: 'status-designed' },
};

export const GROUP_ORDER = [
  'System & Boundaries',
  'State & Async',
  'Services',
  'Contracts & Retrieval',
  'Capacity & Release',
  'Policy & Eval',
  'AI Governance (Extras)',
];
