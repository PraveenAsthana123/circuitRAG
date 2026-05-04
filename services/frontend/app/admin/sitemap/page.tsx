/**
 * /admin/sitemap — categorized index of all admin surfaces.
 *
 * Server Component (static). Per §49 — every page composes with others;
 * this page is the operator's single entry point to find them.
 */

import Link from 'next/link';

type SitemapEntry = {
  href: string;
  label: string;
  description: string;
  status: 'shipped' | 'partial' | 'index-only';
};

const SITEMAP: { category: string; emoji: string; entries: SitemapEntry[] }[] = [
  {
    category: 'Architecture overview',
    emoji: '🏛',
    entries: [
      { href: '/admin', label: 'Health dashboard (default landing)',
        description: 'Live /api/v1/health/detailed — circuit breakers, readiness, uptime. 5s auto-refresh.', status: 'shipped' },
      { href: '/admin/enterprise-architecture', label: 'Enterprise architecture (20+17+12)',
        description: 'Canonical 20-tool sequence + 17 missing components + 12 MCP servers. Maps each row to current state.', status: 'shipped' },
      { href: '/admin/stack-architecture/deep', label: 'Stack architecture deep-dive',
        description: 'Frontend + backend layers, dependency graph, build sequences.', status: 'shipped' },
      { href: '/admin/system-design', label: 'System design',
        description: 'High-level system design rationale.', status: 'shipped' },
    ],
  },
  {
    category: 'Layer 3-11 surfaces (the 11-layer stack)',
    emoji: '🔢',
    entries: [
      { href: '/admin/agent-router', label: 'Layer 3 — Agent Router',
        description: 'Heuristic intent + risk classifier. 12 patterns; conservative-default.', status: 'shipped' },
      { href: '/admin/policy', label: 'Layer 4 — PolisAI Policy',
        description: 'Default-deny rules engine. 12+ rules; allow-rate; recent decisions.', status: 'shipped' },
      { href: '/admin/local-models', label: 'Layer 5 — Council models (Ollama)',
        description: 'Live council-model state: AUTHOR/REVIEWER/ADVISOR/RESEARCHER + audit.', status: 'shipped' },
      { href: '/admin/agentic', label: 'Layer 6 — Agentic framework',
        description: 'LangGraph DAG + agent runtime overview.', status: 'shipped' },
      { href: '/admin/paperclip', label: 'Layer 7 — Paperclip Sandbox',
        description: 'Stage-1 read-only aggregator. apply_rate honesty signal; 6 documented keys.', status: 'shipped' },
      { href: '/admin/kafka-events', label: 'Layer 8 — Kafka event-publisher',
        description: '4 topics for new-layer audits. Opt-in via KAFKA_PUBLISH=1.', status: 'shipped' },
      { href: '/admin/mcp-gateway', label: 'Layer 8 — MCP Gateway',
        description: '4-layer defense for MCP calls. Allowlist + PolisAI + rate-limit + audit.', status: 'shipped' },
      { href: '/admin/vectorless-elasticsearch', label: 'Layer 9 — Vectorless RAG (ES)',
        description: 'BM25 / hybrid retrieval over Elasticsearch. Index mapping + query patterns.', status: 'shipped' },
      { href: '/admin/eval-harness', label: 'Layer 10 — Eval Harness',
        description: 'Ragas + Guardrails + DeepEval + Snyk Stage-1 scaffolds. Stage-2 wiring plan.', status: 'shipped' },
      { href: '/admin/openclaw', label: 'Layer 11 — OpenClaw A2A',
        description: 'Stage-1 gate-only A2A coordinator. 6 agents; default-deny posture.', status: 'shipped' },
    ],
  },
  {
    category: 'Adapter & integration inventory',
    emoji: '🔌',
    entries: [
      { href: '/admin/adapters', label: 'Adapter inventory',
        description: 'LiteLLM + PydanticAI + Kafka publisher. Status per-adapter; swap target documented.', status: 'shipped' },
      { href: '/admin/tool-evaluation', label: 'Tool evaluation (13 tools)',
        description: 'Useful + safe analysis. CrewAI/Agno/PraisonAI rejected; LiteLLM/PydanticAI integrate.', status: 'shipped' },
      { href: '/admin/techstack-audit', label: 'Techstack audit (§56 gate 4)',
        description: 'Empirical install verification. 38/62 installed; 9/9 critical present.', status: 'shipped' },
    ],
  },
  {
    category: 'Operations & deployment',
    emoji: '🚀',
    entries: [
      { href: '/admin/pr-management', label: 'PR management — push queue',
        description: 'Unpushed-commit queue with pressure indicator. §42 gated.', status: 'shipped' },
      { href: '/admin/breakers/deep', label: 'Circuit breakers deep-dive',
        description: 'Per-namespace breaker state, open/closed transitions, failure analysis.', status: 'shipped' },
      { href: '/admin/checklist', label: 'Checklist — pending issues',
        description: 'Issue scanner output: ruff/mypy/bandit/eslint findings.', status: 'shipped' },
      { href: '/admin/forensics', label: 'Forensics — trace → draft → audit',
        description: 'Cross-layer forensic reconstruction by correlation_id.', status: 'shipped' },
      { href: '/admin/post-release/deep', label: 'Post-release deep-dive',
        description: 'Post-deployment validation + drift detection.', status: 'shipped' },
      { href: '/admin/rollout/deep', label: 'Rollout deep-dive',
        description: '4-layer rollback plan; Argo Rollouts patterns.', status: 'shipped' },
    ],
  },
  {
    category: 'Data & RAG',
    emoji: '📚',
    entries: [
      { href: '/admin/data/deep', label: 'Data preprocessing deep-dive',
        description: 'Chunking, embedding versioning, ingestion pipeline.', status: 'shipped' },
      { href: '/admin/rag/deep', label: 'RAG deep-dive',
        description: 'Hybrid retrieval + reranking + citation traceability.', status: 'shipped' },
      { href: '/admin/knowledge-graph/deep', label: 'Knowledge graph deep-dive',
        description: 'Neo4j ontology, multi-hop queries, graph-aware retrieval.', status: 'shipped' },
      { href: '/admin/database', label: 'Database',
        description: 'Postgres + Redis + Qdrant + Neo4j + MinIO state.', status: 'shipped' },
      { href: '/admin/pipelines', label: 'Pipelines hub',
        description: 'All RAG flows in one node visualization.', status: 'shipped' },
    ],
  },
  {
    category: 'Security & governance',
    emoji: '🔐',
    entries: [
      { href: '/admin/explainability', label: 'Explainability',
        description: '§48.4 audit row schema, decision evidence trail.', status: 'shipped' },
      { href: '/admin/security', label: 'Security overview',
        description: 'STRIDE table per container, OWASP+SOC2 mapping.', status: 'shipped' },
      { href: '/admin/rbac', label: 'RBAC',
        description: 'Role-based access control catalog.', status: 'shipped' },
      { href: '/admin/sso', label: 'SSO',
        description: 'Single sign-on integration points.', status: 'shipped' },
      { href: '/admin/pii', label: 'PII handling',
        description: 'PII detection + masking surface.', status: 'shipped' },
      { href: '/admin/guardrails', label: 'Guardrails',
        description: 'Output safety + jailbreak defense.', status: 'shipped' },
    ],
  },
  {
    category: 'Observability',
    emoji: '📊',
    entries: [
      { href: '/admin/monitoring', label: 'Monitoring',
        description: 'Prometheus + Grafana metric dashboards.', status: 'shipped' },
      { href: '/admin/tracing', label: 'Tracing',
        description: 'OpenTelemetry + Jaeger distributed traces.', status: 'shipped' },
      { href: '/admin/llmops', label: 'LLMOps',
        description: 'Langfuse traces, prompt registry, cost tracking.', status: 'shipped' },
      { href: '/admin/aiops', label: 'AIOps',
        description: 'AI-powered ops: anomaly detection, root cause analysis.', status: 'shipped' },
      { href: '/admin/output-eval', label: 'Output evaluation',
        description: 'RAGAS/DeepEval scores; per-query quality.', status: 'shipped' },
      { href: '/admin/load-testing', label: 'Load testing',
        description: 'k6/Locust playbook; 5-phase load test results.', status: 'shipped' },
    ],
  },
  {
    category: 'Architecture decision records',
    emoji: '📜',
    entries: [
      { href: '/admin/adr', label: 'ADR registry',
        description: 'All ADRs with status (proposed/accepted/superseded).', status: 'shipped' },
      { href: '/admin/jad', label: 'JAD sessions',
        description: 'Joint Application Design session records.', status: 'shipped' },
      { href: '/admin/c4-model', label: 'C4 model',
        description: '4-level C4 + L5 governance + L6 observability + L7 lifecycle.', status: 'shipped' },
      { href: '/admin/principles', label: 'Principles',
        description: 'SOLID + 17-factor + KISS/YAGNI/DRY applied.', status: 'shipped' },
      { href: '/admin/architect/deep', label: 'Architect deep-dive',
        description: 'Architect role responsibilities, review workflow.', status: 'shipped' },
    ],
  },
  {
    category: 'Specific deep-dives',
    emoji: '🔬',
    entries: [
      { href: '/admin/deep-dives', label: 'Deep dives — index',
        description: 'Index of all /admin/*/deep pages.', status: 'index-only' },
      { href: '/admin/microservices/deep', label: 'Microservices deep-dive',
        description: 'Service-by-service architecture with C4 mapping.', status: 'shipped' },
      { href: '/admin/api-gateway', label: 'API Gateway',
        description: 'Go gateway: routing + auth + rate limit + correlation.', status: 'shipped' },
      { href: '/admin/agent-registry', label: 'Agent registry',
        description: 'Agent catalog with capability cards + scopes.', status: 'shipped' },
      { href: '/admin/cicd', label: 'CI/CD',
        description: 'GitHub Actions workflow + deployment pipeline.', status: 'shipped' },
      { href: '/admin/scaling-patterns', label: 'Scaling patterns',
        description: 'Horizontal/vertical scaling + autoscaling triggers.', status: 'shipped' },
      { href: '/admin/service-mesh', label: 'Service mesh',
        description: 'Istio/Kiali — mTLS, routing, retries.', status: 'shipped' },
      { href: '/admin/code-quality', label: 'Code quality',
        description: 'Linting, complexity metrics, coverage gates.', status: 'shipped' },
      { href: '/admin/python', label: 'Python language family',
        description: 'Python deps + version pinning rationale.', status: 'shipped' },
      { href: '/admin/lang-family', label: 'Language families',
        description: 'Polyglot stack — Python + Go + TypeScript.', status: 'shipped' },
      { href: '/admin/compiler-stack', label: 'Compiler stack',
        description: 'TypeScript + Go build chain.', status: 'shipped' },
      { href: '/admin/memory', label: 'Memory management',
        description: 'Agent memory + retention + tenant isolation.', status: 'shipped' },
      { href: '/admin/fine-tuning', label: 'Fine-tuning',
        description: 'LoRA + RLHF playbook (Phase C #3.15-16).', status: 'shipped' },
      { href: '/admin/audio', label: 'Audio / Voice AI',
        description: 'TTS + speech reader integration.', status: 'shipped' },
      { href: '/admin/voice-ai', label: 'Voice AI',
        description: 'Speech recognition + cloning patterns.', status: 'shipped' },
    ],
  },
  {
    category: 'Hubs',
    emoji: '🪢',
    entries: [
      { href: '/admin/simulation', label: 'Simulation hub',
        description: 'Live agent + tool state simulation.', status: 'shipped' },
      { href: '/admin/ops-fabric/deep', label: 'Ops fabric',
        description: 'Runbooks + integrations + debugging surfaces.', status: 'shipped' },
      { href: '/admin/eng-manager', label: 'Engineering manager view',
        description: 'EM-friendly dashboard: SLA, cost, on-call rotation.', status: 'shipped' },
      { href: '/admin/techlead/deep', label: 'Tech lead deep-dive',
        description: 'TL workflow + command reference.', status: 'shipped' },
      { href: '/admin/technical-plan', label: 'Technical plan',
        description: 'Quarterly technical roadmap.', status: 'shipped' },
      { href: '/admin/tech-evolution', label: 'Tech evolution',
        description: 'Stack evolution timeline.', status: 'shipped' },
    ],
  },
];

export default function SitemapPage() {
  const totalEntries = SITEMAP.reduce((acc, c) => acc + c.entries.length, 0);

  return (
    <div style={{ padding: '24px', maxWidth: 1300, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Admin Sitemap</h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          Categorized index of all <strong>{totalEntries}</strong> admin
          surfaces across <strong>{SITEMAP.length}</strong> categories.
          Each row links to a live page.
        </p>
      </header>

      {SITEMAP.map((cat) => (
        <section
          key={cat.category}
          style={{
            marginBottom: 32,
            padding: 16,
            border: '1px solid #ddd',
            borderRadius: 4,
          }}
        >
          <h2 style={{ marginTop: 0 }}>
            {cat.emoji} {cat.category} ({cat.entries.length})
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8 }}>
            {cat.entries.map((e) => (
              <div
                key={e.href}
                style={{
                  padding: 8,
                  borderLeft: '3px solid #ccc',
                  background: '#fafafa',
                }}
              >
                <Link
                  href={e.href}
                  style={{
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    color: '#0061a4',
                    textDecoration: 'none',
                  }}
                >
                  {e.label}
                </Link>{' '}
                <code style={{ fontSize: '0.75rem', color: '#888' }}>{e.href}</code>
                <div style={{ fontSize: '0.85rem', color: '#666', marginTop: 4 }}>
                  {e.description}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <section
        style={{
          padding: 16,
          border: '1px dashed #999',
          borderRadius: 4,
          background: '#f8f8f8',
          fontSize: '0.85rem',
        }}
      >
        <strong>Discovery rule:</strong> every new admin page added in a
        commit MUST have a sidebar entry AND a sitemap entry. The sidebar
        is the navigation; the sitemap is the search-by-purpose. Both stay
        in sync via the §49 compose-footer pattern at each page.
      </section>
    </div>
  );
}
