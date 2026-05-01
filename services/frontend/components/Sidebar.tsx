'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

type Entry = { href: string; label: string };
type Group = { heading?: string; items: Entry[] };

const GROUPS: Group[] = [
  {
    items: [
      { href: '/upload', label: 'Upload' },
      { href: '/documents', label: 'Documents' },
      { href: '/ask', label: 'Ask' },
    ],
  },
  {
    heading: 'Tools',
    items: [
      { href: '/tools', label: 'Tool index' },
      { href: '/tools/system-design', label: 'System Design' },
      { href: '/tools/design-areas', label: '74 Design Features' },
      { href: '/tools/scenarios', label: 'All Scenarios Catalog' },
    ],
  },
  {
    heading: 'Catalogs',
    items: [
      { href: '/tools/circuit-breakers-list', label: 'Circuit Breakers' },
      { href: '/tools/rag-scenarios', label: '36 RAG Scenarios' },
      { href: '/tools/microservice-scenarios', label: 'Microservice Scenarios' },
      { href: '/tools/database-scenarios', label: 'Database Scenarios' },
      { href: '/tools/methodologies', label: 'Methodologies' },
      { href: '/tools/code-governance', label: 'Code Governance' },
    ],
  },
  {
    heading: 'Admin',
    items: [
      { href: '/admin', label: 'Operator Dashboard' },
      { href: '/admin/techstack', label: 'Techstack' },
      { href: '/admin/python', label: 'Python (concepts + flow)' },
      { href: '/admin/python/deep', label: 'Python deep dive (interview)' },
      { href: '/admin/python/syllabus', label: 'Python syllabus (full catalog)' },
      { href: '/admin/system-design/chatbot', label: '1. Chatbot design' },
      { href: '/admin/lang-family/rag', label: '2. Lang family · RAG map' },
      { href: '/admin/compiler-stack/rag', label: '3. LLVM / MLIR · RAG fit' },
      { href: '/admin/audio/tts', label: '4. Audio / TTS for chatbot' },
      { href: '/admin/llmops', label: 'LLMOps scorecard' },
      { href: '/admin/llmops/deep', label: 'LLMOps deep dive (interview)' },
      { href: '/admin/techlead/deep#ultimate-tech-lead-master-checklist', label: 'Tech Lead checklist' },
      { href: '/admin/monitoring', label: 'Monitoring + health' },
      { href: '/admin/agentic', label: 'Agentic tasks' },
      { href: '/admin/agentic/control-plane', label: 'Agentic control plane' },
      { href: '/admin/database/deep', label: 'Database deep dive (interview)' },
      { href: '/admin/database/deep#kafka', label: 'Kafka (event store)' },
      { href: '/admin/mcp/deep', label: 'MCP deep dive (interview)' },
      { href: '/admin/memory/deep', label: 'Memory deep dive (sidecar + orchestrator)' },
      { href: '/admin/aiops/deep', label: 'AIOps deep dive (ratchet + LLM incident)' },
      { href: '/admin/output-eval/deep', label: 'Output evaluation (citation + golden set)' },
      { href: '/admin/service-mesh/deep', label: 'Service mesh + Istio (sidecar + authz)' },
      { href: '/admin/api-gateway/deep', label: 'API gateway (BFF + planned NGINX/Go)' },
      { href: '/admin/scaling-patterns/deep', label: 'Scaling patterns (LB + page-index + vectorless RAG)' },
      { href: '/admin/agent-registry/deep', label: 'Agent registry (roles + sidecar council)' },
      { href: '/admin/stack-architecture/deep', label: 'Stack architecture (frontend + backend)' },
      { href: '/admin/knowledge-graph/deep', label: 'Knowledge graph (ontology + graph)' },
      { href: '/admin/ops-fabric/deep', label: 'Ops fabric (runbooks + integrations + debugging)' },
      { href: '/admin/local-models', label: '🦙 Local models (live operator view)' },
      { href: '/admin/simulation', label: '🛰 Simulation hub (live agent + tool state)' },
      { href: '/admin/pipelines', label: '🪢 Pipelines hub (all RAG flows in one node)' },
      { href: '/admin/breakers/deep', label: 'Breakers deep dive (interview)' },
      { href: '/admin/forensics', label: 'Forensics (trace → draft → audit → HITL)' },
      { href: '/admin/rag/deep', label: 'RAG deep dive (interview)' },
      { href: '/admin/microservices/deep', label: 'Microservices deep dive' },
      { href: '/admin/data/deep', label: 'Data preprocessing deep dive' },
      { href: '/admin/deep-dives', label: 'Deep dives — index' },
      { href: '/admin/client-errors', label: 'Client errors (F12 capture)' },
    ],
  },
  {
    heading: 'Stack (tools)',
    items: [
      { href: '/tools/otel-stack', label: 'Observability (OTel + Prom + Jaeger)' },
      { href: '/tools/elk', label: 'ELK (logs)' },
      { href: '/tools/ollama-vllm', label: 'Ollama / vLLM' },
      { href: '/tools/postgres-rls', label: 'Postgres + RLS' },
      { href: '/tools/qdrant', label: 'Qdrant (vector DB)' },
      { href: '/tools/neo4j', label: 'Neo4j (graph DB)' },
      { href: '/tools/redis', label: 'Redis (cache)' },
      { href: '/tools/kafka', label: 'Kafka (event log)' },
      { href: '/tools/istio', label: 'Istio (service mesh)' },
      { href: '/tools/api-gateway', label: 'API Gateway' },
      { href: '/tools/nginx-cdn', label: 'NGINX (edge / CDN)' },
      { href: '/tools/circuit-breakers', label: 'Circuit Breakers (×5)' },
      { href: '/tools/ccb', label: 'Cognitive Circuit Breaker' },
      { href: '/tools/code-governance', label: 'Code governance' },
    ],
  },
  {
    heading: 'RAG quick-jump',
    items: [
      { href: '/admin/rag/deep#chunking', label: 'RAG · Chunking' },
      { href: '/admin/rag/deep#hybrid-retrieval', label: 'RAG · Hybrid retrieval' },
      { href: '/admin/rag/deep#embedding', label: 'RAG · Embedding + version' },
      { href: '/admin/rag/deep#pre-retrieval', label: 'RAG · Pre-retrieval' },
      { href: '/admin/rag/deep#post-retrieval', label: 'RAG · Post-retrieval' },
      { href: '/tools/rag-scenarios', label: 'RAG · 36 scenarios' },
    ],
  },
  {
    heading: 'Data quick-jump',
    items: [
      { href: '/admin/database/deep#postgres-rls', label: 'Relational · Postgres + RLS' },
      { href: '/admin/database/deep#qdrant', label: 'Vector DB · Qdrant' },
      { href: '/tools/neo4j', label: 'Graph DB · Neo4j' },
      { href: '/admin/database/deep#redis', label: 'Cache DB · Redis' },
      { href: '/admin/database/deep#kafka', label: 'Event log · Kafka' },
      { href: '/admin/database/deep#clickhouse', label: 'Historical / time-series · ClickHouse' },
      { href: '/admin/database/deep#object-storage', label: 'Object storage · MinIO/S3' },
    ],
  },
  {
    heading: 'Edge & Identity',
    items: [
      { href: '/tools/api-gateway', label: 'API Gateway (Go)' },
      { href: '/tools/nginx-cdn', label: 'CDN (NGINX edge)' },
      { href: '/tools/nginx-cdn', label: 'Load balancer (NGINX)' },
      { href: '/admin/rbac/deep', label: 'RBAC + ABAC (3-layer)' },
      { href: '/admin/sso/deep', label: 'SSO (SAML / OIDC)' },
      { href: '/admin/ldap/deep', label: 'LDAP (enterprise sync)' },
      { href: '/admin/pii/deep', label: 'PII (detect + redact)' },
      { href: '/admin/guardrails/deep', label: 'AI Guardrails (in/out/behavior)' },
    ],
  },
  {
    heading: 'AI Orchestration (3-layer)',
    items: [
      { href: '/admin/ai-orchestration/deep', label: 'Architecture overview' },
      { href: '/admin/ai-orchestration/deep#policy-layer', label: '🛡 Policy layer (OPA + Guardrails + Presidio)' },
      { href: '/admin/ai-orchestration/deep#paperclip-manager', label: '🧠 Paperclip — Manager (planner)' },
      { href: '/admin/ai-orchestration/deep#openclaw-workers', label: '✋ OpenClaw — Workers (executors)' },
    ],
  },
  {
    heading: 'Audio / TTS',
    items: [
      { href: '/admin/audio/tts/topics', label: '🔊 Topics — read-aloud catalog' },
      { href: '/admin/audio/tts', label: 'Architecture (API contract + flow)' },
    ],
  },
  {
    heading: 'Fine-tuning',
    items: [
      { href: '/admin/fine-tuning/deep', label: 'Overview (10 scenarios + decision)' },
      { href: '/admin/fine-tuning/deep#supervised-fine-tuning', label: 'Supervised (SFT) — format + tone' },
      { href: '/admin/fine-tuning/deep#unsupervised-fine-tuning', label: 'Unsupervised — domain language' },
      { href: '/admin/fine-tuning/deep#semi-supervised-fine-tuning', label: 'Semi-supervised — pseudo-label + SME' },
      { href: '/admin/fine-tuning/deep#rag-vs-fine-tuning', label: 'RAG vs Fine-tuning (decision)' },
      { href: '/admin/fine-tuning/deep#alignment-training', label: 'Alignment — RLHF / DPO / ORPO / KTO / RLAIF' },
      { href: '/admin/fine-tuning/deep#peft-techniques', label: 'PEFT — LoRA / QLoRA / DoRA / Adapters' },
      { href: '/admin/fine-tuning/deep#raft-retrieval-augmented-ft', label: 'RAFT — Retrieval-Augmented FT' },
      { href: '/admin/fine-tuning/deep#tool-use-fine-tuning', label: 'Tool-use / function-calling FT' },
      { href: '/admin/fine-tuning/deep#knowledge-distillation', label: 'Knowledge distillation (teacher → student)' },
      { href: '/admin/fine-tuning/deep#full-fine-tuning', label: 'Full fine-tuning (all params)' },
    ],
  },
  {
    heading: 'AI lifecycle',
    items: [
      { href: '/admin/llmops/deep#evaluation', label: 'Output evaluation (golden + sampling)' },
      { href: '/admin/llmops/deep#prompt-registry', label: 'Prompt registry' },
      { href: '/admin/llmops/deep#audit', label: 'Decision audit' },
      { href: '/admin/llmops/deep#observability', label: 'AI observability' },
      { href: '/admin/llmops/deep#deployment', label: 'Model deployment' },
      { href: '/admin/llmops/deep#experiment-tracking', label: 'Experiment tracking' },
      { href: '/admin/llmops/deep#model-management', label: 'Model registry' },
    ],
  },
  {
    heading: 'AI runtime / compiler',
    items: [
      { href: '/admin/lang-family/rag', label: '2. Lang family · RAG map' },
      { href: '/admin/compiler-stack/rag', label: '3. LLVM / MLIR · RAG fit' },
      { href: '/tools/ollama-vllm', label: 'Ollama / vLLM' },
    ],
  },
  {
    heading: 'Voice / audio',
    items: [
      { href: '/admin/audio/tts', label: '4. Audio / TTS for chatbot' },
    ],
  },
  {
    heading: 'Roles (interview lens)',
    items: [
      { href: '/admin/architect/deep', label: 'Architect — system + ADRs' },
      { href: '/admin/techlead/deep', label: 'Tech Lead — API contract + checklist' },
      { href: '/admin/techlead/deep#ultimate-tech-lead-master-checklist', label: 'Tech Lead — checklist section' },
      { href: '/admin/eng-manager/deep', label: 'Eng Manager — roadmap + risk' },
      { href: '/admin/technical-plan/deep', label: 'Technical Plan — BRD-to-code' },
    ],
  },
  {
    heading: 'C4 model (7 levels · AI-extended)',
    items: [
      { href: '/admin/c4-model/deep', label: 'C4 — overview' },
      { href: '/admin/c4-model/deep#level-1-system-context', label: 'L1 · System context' },
      { href: '/admin/c4-model/deep#level-2-containers', label: 'L2 · Containers' },
      { href: '/admin/c4-model/deep#level-3-components', label: 'L3 · Components' },
      { href: '/admin/c4-model/deep#level-4-code', label: 'L4 · Code' },
      { href: '/admin/c4-model/deep#level-5-governance', label: 'L5 · Governance' },
      { href: '/admin/c4-model/deep#level-6-observability', label: 'L6 · Observability' },
      { href: '/admin/c4-model/deep#level-7-lifecycle', label: 'L7 · Lifecycle' },
    ],
  },
  {
    heading: 'ADR — Architecture Decision Record',
    items: [
      { href: '/admin/adr/deep', label: 'ADR — overview' },
      { href: '/admin/adr/deep#adr-fundamentals', label: 'ADR · Fundamentals + template' },
      { href: '/admin/adr/deep#adr-001-ai-assisted-dev', label: 'ADR-001 · AI-assisted dev (worked)' },
      { href: '/admin/adr/deep#adr-catalog-ai-sdlc', label: 'ADR catalog · AI-SDLC (10 ADRs)' },
    ],
  },
  {
    heading: 'JAD — Joint Application Design',
    items: [
      { href: '/admin/jad/deep', label: 'JAD — overview' },
      { href: '/admin/jad/deep#jad-fundamentals', label: 'JAD · Fundamentals + roles' },
      { href: '/admin/jad/deep#jad-day-by-day-execution', label: 'JAD · Day-by-day execution' },
      { href: '/admin/jad/deep#jad-adr-c4-unified-chain', label: 'JAD → BRD → C4 → ADR chain' },
    ],
  },
  {
    heading: 'Voice AI — JFA → ECAPA-TDNN',
    items: [
      { href: '/admin/voice-ai/deep', label: 'Voice AI — overview' },
      { href: '/admin/voice-ai/deep#jfa-to-x-vector', label: 'JFA · GMM-UBM → i-vector → x-vector' },
      { href: '/admin/voice-ai/deep#voice-auth-system', label: 'Voice auth · ECAPA-TDNN system' },
    ],
  },
  {
    heading: 'Security — OWASP + DevSecOps + SOC2',
    items: [
      { href: '/admin/security/deep', label: 'Security — overview' },
      { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'OWASP 2025 + STRIDE + AI threats' },
      { href: '/admin/security/deep#devsecops-pipeline', label: 'DevSecOps pipeline (shift-left)' },
      { href: '/admin/security/deep#cloud-soc2-iam', label: 'Cloud · SOC2 + IAM controls' },
    ],
  },
  {
    heading: 'Rollout · rollback + health probes',
    items: [
      { href: '/admin/rollout/deep', label: 'Rollout — overview' },
      { href: '/admin/rollout/deep#rollback-strategy', label: 'Rollback · app + DB + AI + infra' },
      { href: '/admin/rollout/deep#k8s-health-probes', label: 'K8s · startup / liveness / readiness' },
    ],
  },
  {
    heading: 'Architecture principles',
    items: [
      { href: '/admin/principles/deep', label: 'Principles — overview' },
      { href: '/admin/principles/deep#solid-ai-microservices', label: 'SOLID · AI-SDLC + microservices' },
      { href: '/admin/principles/deep#twelve-factor-kiss-yagni-dry', label: '12-factor + KISS / YAGNI / DRY' },
    ],
  },
  {
    heading: 'Load testing — k6 + JMeter + AI',
    items: [
      { href: '/admin/load-testing/deep', label: 'Load testing — overview' },
      { href: '/admin/load-testing/deep#k6-jmeter-multi-phase', label: 'k6 + JMeter · multi-phase' },
      { href: '/admin/load-testing/deep#rag-ai-load-testing', label: 'RAG / AI · layered + breakpoint' },
      { href: '/admin/load-testing/deep#performance-tuning-outage-playbook', label: 'Tuning + outage playbook' },
    ],
  },
  {
    heading: 'CI/CD + TDD',
    items: [
      { href: '/admin/cicd/deep', label: 'CI/CD + TDD — overview' },
      { href: '/admin/cicd/deep#cicd-master-pipeline', label: 'CI/CD · master pipeline + AI gates' },
      { href: '/admin/cicd/deep#tdd-framework-ai', label: 'TDD · F.I.R.S.T. + contract + AI eval' },
    ],
  },
  {
    heading: 'Release ops — deploy + verify',
    items: [
      { href: '/admin/post-release/deep', label: 'Release ops — overview' },
      { href: '/admin/post-release/deep#deployment-playbook', label: 'Deployment playbook · strategy fit' },
      { href: '/admin/post-release/deep#pdv-monitoring', label: 'PDV · golden + AI signals + matrix' },
    ],
  },
  {
    heading: 'Distributed tracing + baggage',
    items: [
      { href: '/admin/tracing/deep', label: 'Tracing + baggage — overview' },
      { href: '/admin/tracing/deep#baggage-propagation', label: 'Baggage propagation · chain across hops' },
      { href: '/admin/tracing/deep#trace-draft-audit-linkage', label: 'Trace → draft → audit · forensics by request_id' },
    ],
  },
  {
    heading: 'Production-readiness checklist',
    items: [
      { href: '/admin/checklist/deep', label: 'Master checklist — overview' },
      { href: '/admin/checklist/deep#lifecycle-checklist', label: 'Lifecycle · sections 1–10' },
      { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance + ops + 6 hard stops' },
    ],
  },
  {
    heading: 'AI Explainability + Interpretability',
    items: [
      { href: '/admin/explainability/deep', label: 'Explainability — overview' },
      { href: '/admin/explainability/deep#global-local-xai', label: 'Global + local · SHAP / counterfactual' },
      { href: '/admin/explainability/deep#audit-rag-contract-regulation', label: 'Audit row · RAG four-part · EU AI Act' },
    ],
  },
  {
    heading: 'Code quality — lint + format + types',
    items: [
      { href: '/admin/code-quality/deep', label: 'Code quality — overview' },
      { href: '/admin/code-quality/deep#linting-strategy-three-tier', label: 'Linting · 3-tier (IDE + pre-commit + CI)' },
      { href: '/admin/code-quality/deep#pep8-auto-formatting-python', label: 'PEP 8 · Ruff + Black + Mypy strict' },
    ],
  },
  {
    heading: 'Tech evolution + efficiency',
    items: [
      { href: '/admin/tech-evolution/deep', label: 'Tech evolution — overview' },
      { href: '/admin/tech-evolution/deep#tech-radar-paved-road', label: 'Tech Radar + paved road + deprecation' },
      { href: '/admin/tech-evolution/deep#finops-devex', label: 'FinOps + DevEx (sustainability pair)' },
    ],
  },
];

/** Left-menu nav. Grouped so the 10+ links are scannable. */
export default function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + '/');
  return (
    <nav className="sidebar-nav">
      {GROUPS.map((g, gi) => (
        <div key={gi} className="sidebar-group">
          {g.heading && <div className="sidebar-heading">{g.heading}</div>}
          <ul>
            {g.items.map((link) => (
              // Composite key: label is part of the key because some
              // groups intentionally surface the same href under
              // multiple aliases (e.g. "CDN" and "Load balancer" both
              // pointing at /tools/nginx-cdn). Keying only on href
              // collides for those rows and triggers React's
              // duplicate-key warning.
              <li key={`${link.href}::${link.label}`}>
                <Link href={link.href} className={isActive(link.href) ? 'active' : ''}>
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
