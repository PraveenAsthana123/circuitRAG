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
      { href: '/admin/system-design/chatbot', label: 'System design · chatbot map' },
      { href: '/admin/lang-family/rag', label: 'Lang family · RAG map' },
      { href: '/admin/compiler-stack/rag', label: 'LLVM / MLIR · RAG fit' },
      { href: '/admin/llmops', label: 'LLMOps scorecard' },
      { href: '/admin/llmops/deep', label: 'LLMOps deep dive (interview)' },
      { href: '/admin/database/deep', label: 'Database deep dive (interview)' },
      { href: '/admin/database/deep#kafka', label: 'Kafka (event store)' },
      { href: '/admin/mcp/deep', label: 'MCP deep dive (interview)' },
      { href: '/admin/breakers/deep', label: 'Breakers deep dive (interview)' },
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
      { href: '/admin/lang-family/rag', label: 'Lang family · RAG map' },
      { href: '/admin/compiler-stack/rag', label: 'LLVM / MLIR · RAG fit' },
      { href: '/tools/ollama-vllm', label: 'Ollama / vLLM' },
    ],
  },
  {
    heading: 'Roles (interview lens)',
    items: [
      { href: '/admin/architect/deep', label: 'Architect — system + ADRs' },
      { href: '/admin/techlead/deep', label: 'Tech Lead — API contract' },
      { href: '/admin/eng-manager/deep', label: 'Eng Manager — roadmap + risk' },
      { href: '/admin/technical-plan/deep', label: 'Technical Plan — BRD-to-code' },
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
              <li key={link.href}>
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
