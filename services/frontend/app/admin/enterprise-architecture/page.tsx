/**
 * /admin/enterprise-architecture — canonical 20-tool enterprise stack.
 *
 * Captures the user's 2026-05-04 architecture vision. Server Component
 * (static documentation) — no live queries. Maps each tool in the
 * sequence against our current stack (✅ shipped / ⚠️ partial / ❌ TODO).
 */

import Link from 'next/link';

type ToolRow = {
  seq: number;
  tool: string;
  purpose: string;
  input: string;
  process: string;
  output: string;
  integrates: string;
  ours: { state: 'shipped' | 'partial' | 'todo'; path: string };
};

const SEQUENCE: ToolRow[] = [
  { seq: 1, tool: 'Paperclip', purpose: 'Control plane', input: 'User goal, team, task', process: 'Goals, agents, budgets, approvals', output: 'Approved work item', integrates: 'LangGraph, Temporal, OPA',
    ours: { state: 'partial', path: '/admin/paperclip — Stage-1 sandbox aggregator (read-only); Stage-3 needed for control plane' } },
  { seq: 2, tool: 'OPA', purpose: 'Policy gate', input: 'User, role, tenant, tool', process: 'RBAC/ABAC decision', output: 'Allow / deny / approval needed', integrates: 'Paperclip, MCP, K8s',
    ours: { state: 'partial', path: '/admin/policy — Stage-1 PolisAI (Python eval; Stage-2 OPA + Rego pending)' } },
  { seq: 3, tool: 'Temporal', purpose: 'Durable workflow', input: 'Approved task', process: 'Retry, timeout, state recovery', output: 'Reliable workflow instance', integrates: 'LangGraph, queues',
    ours: { state: 'todo', path: 'NOT IN STACK — currently using LangGraph + asyncio for state' } },
  { seq: 4, tool: 'LangGraph', purpose: 'Agent runtime', input: 'Workflow state', process: 'Planner → agent nodes → decision edges', output: 'Agent execution state', integrates: 'AutoGen, CrewAI, MCP',
    ours: { state: 'shipped', path: 'services/agent-orchestrator-svc/app/langgraph_flow.py — LangGraph 1.1.10' } },
  { seq: 5, tool: 'AutoGen / CrewAI', purpose: 'Multi-agent collaboration', input: 'Task + agent roles', process: 'Discussion / delegation', output: 'Subtask result', integrates: 'LangGraph, A2A',
    ours: { state: 'partial', path: 'scripts/local_council.py 4-role council (researcher/author/reviewer/advisor); CrewAI/AutoGen NOT adopted per tool-eval' } },
  { seq: 6, tool: 'Pydantic AI', purpose: 'Structured output', input: 'LLM response', process: 'Schema validation', output: 'Typed JSON / result', integrates: 'LangGraph, APIs',
    ours: { state: 'shipped', path: '/admin/adapters — PydanticAI Stage-1 + Stage-2 fallback' } },
  { seq: 7, tool: 'A2A', purpose: 'Agent-to-agent protocol', input: 'Agent request', process: 'Capability discovery + collaboration', output: 'Agent response', integrates: 'AutoGen, remote agents',
    ours: { state: 'partial', path: '/admin/openclaw — Stage-1 gate-only; Stage-2 Dispatch RPC pending' } },
  { seq: 8, tool: 'MCP', purpose: 'Tool/data access', input: 'Tool call request', process: 'Tools/resources/prompts', output: 'Tool result/context', integrates: 'APIs, DBs, Git, RAG',
    ours: { state: 'shipped', path: 'mcp/server_*.py — 9 MCP servers (research/drills/deploy/hr/itsm/observe/ollama/tests/paperclip)' } },
  { seq: 9, tool: 'LlamaIndex / Haystack', purpose: 'RAG pipeline', input: 'User query', process: 'Retrieve, rerank, assemble', output: 'Grounded context', integrates: 'Vector DB, search',
    ours: { state: 'partial', path: 'services/retrieval-svc — LangChain-Core only; LlamaIndex/Haystack NOT adopted' } },
  { seq: 10, tool: 'Vector DB', purpose: 'Semantic search', input: 'Embedding query', process: 'Similarity search', output: 'Top-k chunks', integrates: 'RAG layer',
    ours: { state: 'shipped', path: 'docker-compose: Qdrant 1.11' } },
  { seq: 11, tool: 'Elasticsearch / OpenSearch', purpose: 'Keyword search', input: 'Text query', process: 'BM25 / filter search', output: 'Exact matches', integrates: 'Hybrid RAG',
    ours: { state: 'shipped', path: '/admin/vectorless-elasticsearch — Elasticsearch 8.15 in docker-compose' } },
  { seq: 12, tool: 'Neo4j', purpose: 'Graph context', input: 'Entity/relation query', process: 'Relationship traversal', output: 'Entity graph', integrates: 'RAG layer',
    ours: { state: 'shipped', path: 'docker-compose: Neo4j 5.21' } },
  { seq: 13, tool: 'Guardrails AI', purpose: 'Output safety', input: 'Draft answer', process: 'Validate format/safety/policy', output: 'Pass/fail/fix', integrates: 'LangGraph, OPA',
    ours: { state: 'partial', path: '/admin/eval-harness — Stage-1 fail-OPEN scaffold; Stage-2 wiring pending' } },
  { seq: 14, tool: 'RAGAS / DeepEval', purpose: 'Quality evaluation', input: 'Answer + context + ref', process: 'Groundedness, relevance, faithfulness', output: 'Quality score', integrates: 'Langfuse, CI/CD',
    ours: { state: 'partial', path: '/admin/eval-harness — Ragas + DeepEval scaffolds; Stage-2 wiring pending' } },
  { seq: 15, tool: 'Langfuse', purpose: 'LLM observability', input: 'Prompt, response, score, cost', process: 'Trace LLM calls', output: 'Prompt/eval dashboard', integrates: 'LangGraph, RAGAS',
    ours: { state: 'shipped', path: 'docker-compose: langfuse:2' } },
  { seq: 16, tool: 'OpenTelemetry', purpose: 'Infra tracing', input: 'Spans/logs/metrics', process: 'Distributed tracing', output: 'Trace IDs, latency', integrates: 'Grafana, Jaeger',
    ours: { state: 'shipped', path: 'docker-compose: otel-collector + Jaeger 1.60 + Prometheus 2.54' } },
  { seq: 17, tool: 'Kubernetes', purpose: 'Runtime', input: 'Container images', process: 'Deploy/scale/isolate', output: 'Running pods', integrates: 'Istio, Vault',
    ours: { state: 'todo', path: 'NOT IN STACK — currently docker-compose only; k8s manifests deferred' } },
  { seq: 18, tool: 'Istio', purpose: 'Zero-trust mesh', input: 'Service traffic', process: 'mTLS, routing, retries', output: 'Secure service calls', integrates: 'K8s, OPA',
    ours: { state: 'todo', path: 'NOT IN STACK — Kiali 1.86 viz shipped; Istio control plane needs k8s migration' } },
  { seq: 19, tool: 'Vault', purpose: 'Secrets', input: 'Secret request', process: 'Dynamic secret/token', output: 'Short-lived credentials', integrates: 'MCP, agents',
    ours: { state: 'todo', path: 'NOT IN STACK — using env vars + Fernet encryption per CLAUDE.md §4.2' } },
  { seq: 20, tool: 'ArgoCD / GitHub Actions', purpose: 'CI/CD', input: 'Code/config change', process: 'Build, scan, deploy', output: 'Versioned release', integrates: 'K8s, policy checks',
    ours: { state: 'partial', path: 'GitHub Actions partial (.github/workflows/snyk.yml + retrieval-svc-agent-ci.yml); ArgoCD NOT in stack' } },
];

type Missing = {
  area: string;
  recommendation: string;
  why: string;
  ours: { state: 'shipped' | 'partial' | 'todo'; note: string };
};

const MISSING: Missing[] = [
  { area: 'MCP registry', recommendation: 'Official MCP Registry / private catalog', why: 'Know which MCP servers are approved',
    ours: { state: 'todo', note: 'No registry; servers are file-discovered from mcp/server_*.py' } },
  { area: 'MCP security gateway', recommendation: 'MCP proxy + allowlist + sandbox', why: 'MCP tools can become RCE/data-leak risk',
    ours: { state: 'partial', note: 'Per-tool scope tokens via PolisAI; no central gateway' } },
  { area: 'Agent registry', recommendation: 'Agent catalog + capability cards', why: 'Know agent skills, owner, risk, version',
    ours: { state: 'partial', note: 'OpenClaw AGENT_REGISTRY (6 agents) + scripts/agent_registry.py' } },
  { area: 'Prompt registry', recommendation: 'Langfuse / PromptLayer-style', why: 'Version prompts like code',
    ours: { state: 'todo', note: 'Prompts inlined in code; no registry surface' } },
  { area: 'Model gateway', recommendation: 'LiteLLM / Portkey', why: 'Route models, control cost, fallback',
    ours: { state: 'partial', note: '/admin/adapters — LiteLLM Stage-1 + Stage-2 fallback shipped' } },
  { area: 'Memory governance', recommendation: 'TTL, tenant isolation, review', why: 'Prevent unsafe/stale memory',
    ours: { state: 'todo', note: 'Audit logs are append-only; no agent memory layer yet' } },
  { area: 'Dataset/versioning', recommendation: 'DVC / LakeFS / Delta Lake', why: 'Reproducible eval and training data',
    ours: { state: 'todo', note: 'No data versioning; ingestion-svc writes raw to MinIO' } },
  { area: 'Feature flags', recommendation: 'OpenFeature / Unleash', why: 'Safe rollout by tenant/user',
    ours: { state: 'partial', note: 'Env-flag pattern (KAFKA_PUBLISH, LITELLM_ENABLED, PYDANTICAI_ENABLED) — no central system' } },
  { area: 'Queue/DLQ', recommendation: 'Kafka DLQ', why: 'Failed agent events need recovery',
    ours: { state: 'partial', note: 'Kafka in docker-compose; DLQ topic pattern not yet wired' } },
  { area: 'Rate limit', recommendation: 'Envoy / API Gateway / Redis', why: 'Stop runaway agents',
    ours: { state: 'shipped', note: 'services/api-gateway + Redis-backed limiters per CLAUDE.md §4.4' } },
  { area: 'Kill switch', recommendation: 'Emergency stop service', why: 'Stop bad agent behavior fast',
    ours: { state: 'todo', note: 'No emergency-stop endpoint; § 42 boundaries only stop destructive ops' } },
  { area: 'Audit vault', recommendation: 'Immutable / WORM logs', why: 'Compliance and incident review',
    ours: { state: 'partial', note: '.loop/*.jsonl audit logs are append-only but not WORM-storage' } },
  { area: 'Threat modeling', recommendation: 'STRIDE / LINDDUN', why: 'Required before prod',
    ours: { state: 'partial', note: 'docs/architecture/security/ STRIDE per container per CLAUDE.md §47.6' } },
  { area: 'Supply-chain security', recommendation: 'Snyk, Trivy, Syft, Grype, Cosign', why: 'Protect containers/dependencies',
    ours: { state: 'partial', note: 'Snyk Stage-1 scaffold (.snyk + workflow); Trivy/Cosign not yet wired' } },
  { area: 'Policy testing', recommendation: 'OPA Conftest', why: 'Test governance rules before deploy',
    ours: { state: 'partial', note: 'PolisAI rules drill-tested; Conftest not yet adopted' } },
  { area: 'Chaos testing', recommendation: 'LitmusChaos / Chaos Mesh', why: 'Validate failure recovery',
    ours: { state: 'todo', note: 'No chaos engineering; circuit-breaker drills cover some failure paths' } },
  { area: 'Load testing', recommendation: 'k6 / Locust / JMeter', why: 'Validate 10K/100K/1M users',
    ours: { state: 'partial', note: 'Performance Agent layer + k6 binary detection per Tier 6 #6.3' } },
];

type MCPServer = {
  type: string;
  purpose: string;
  risk: 'medium' | 'high' | 'critical';
  ours: { state: 'shipped' | 'partial' | 'todo'; note: string };
};

const MCP_SERVERS: MCPServer[] = [
  { type: 'Filesystem MCP', purpose: 'Read/write files', risk: 'high',
    ours: { state: 'todo', note: 'Not exposed via MCP; council reads filesystem directly' } },
  { type: 'GitHub/Git MCP', purpose: 'Repo/code operations', risk: 'high',
    ours: { state: 'todo', note: 'Direct git subprocess; no MCP wrapper' } },
  { type: 'Postgres MCP', purpose: 'SQL/query access', risk: 'high',
    ours: { state: 'todo', note: 'Direct asyncpg per CLAUDE.md §3' } },
  { type: 'Slack/Teams MCP', purpose: 'Collaboration', risk: 'medium',
    ours: { state: 'todo', note: 'Not yet integrated' } },
  { type: 'Google Drive/SharePoint MCP', purpose: 'Documents/RAG', risk: 'high',
    ours: { state: 'todo', note: 'ingestion-svc handles MIME-typed files; no cloud-doc MCP' } },
  { type: 'Browser MCP', purpose: 'Web automation', risk: 'high',
    ours: { state: 'todo', note: 'Playwright/chrome-devtools available as Claude tools, not MCP' } },
  { type: 'Kubernetes MCP', purpose: 'Cluster operations', risk: 'critical',
    ours: { state: 'todo', note: 'No k8s in stack yet' } },
  { type: 'Databricks MCP', purpose: 'Lakehouse/RAG/data jobs', risk: 'critical',
    ours: { state: 'todo', note: 'Not in stack' } },
  { type: 'Jira/Linear MCP', purpose: 'Ticket workflow', risk: 'medium',
    ours: { state: 'todo', note: 'Not yet integrated' } },
  { type: 'CI/CD MCP', purpose: 'Build/deploy', risk: 'critical',
    ours: { state: 'partial', note: 'mcp/server_deploy.py exists but minimal' } },
  { type: 'Vault MCP', purpose: 'Secrets access', risk: 'critical',
    ours: { state: 'todo', note: 'Vault not in stack; using env + Fernet' } },
  { type: 'Observability MCP', purpose: 'Logs/traces/metrics', risk: 'medium',
    ours: { state: 'partial', note: 'mcp/server_observe.py — minimal observability surface' } },
];

const STATE_STYLE = {
  shipped: { bg: '#dff2dd', fg: '#1f8a4c', icon: '✅' },
  partial: { bg: '#fef3e1', fg: '#c47a1a', icon: '⚠️' },
  todo:    { bg: '#fdeaea', fg: '#a4262c', icon: '❌' },
};

const RISK_STYLE = {
  medium:   { bg: '#fef3e1', fg: '#c47a1a' },
  high:     { bg: '#fdeaea', fg: '#a4262c' },
  critical: { bg: '#a4262c', fg: '#fff' },
};

export default function EnterpriseArchitecturePage() {
  const seqStats = {
    shipped: SEQUENCE.filter((s) => s.ours.state === 'shipped').length,
    partial: SEQUENCE.filter((s) => s.ours.state === 'partial').length,
    todo: SEQUENCE.filter((s) => s.ours.state === 'todo').length,
  };
  const missingStats = {
    shipped: MISSING.filter((m) => m.ours.state === 'shipped').length,
    partial: MISSING.filter((m) => m.ours.state === 'partial').length,
    todo: MISSING.filter((m) => m.ours.state === 'todo').length,
  };
  const mcpStats = {
    shipped: MCP_SERVERS.filter((m) => m.ours.state === 'shipped').length,
    partial: MCP_SERVERS.filter((m) => m.ours.state === 'partial').length,
    todo: MCP_SERVERS.filter((m) => m.ours.state === 'todo').length,
  };

  return (
    <div style={{ padding: '24px', maxWidth: 1300, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Enterprise Architecture — 20-tool sequence + 17 missing + 12 MCP servers</h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          Captures the user-ratified 2026-05-04 enterprise stack vision.
          Maps each row against our current implementation state. Numbers
          beat prose: the 3 tables below total <strong>49 line items</strong> with{' '}
          <strong>{seqStats.shipped + missingStats.shipped + mcpStats.shipped} ✅ shipped</strong>{' '}
          / <strong>{seqStats.partial + missingStats.partial + mcpStats.partial} ⚠️ partial</strong>{' '}
          / <strong>{seqStats.todo + missingStats.todo + mcpStats.todo} ❌ TODO</strong>.
        </p>
      </header>

      {/* Section 1: 20-tool sequence */}
      <section style={{ marginBottom: 32 }}>
        <h2>1. The 20-tool production sequence</h2>
        <p style={{ color: '#666' }}>
          Stats: ✅ {seqStats.shipped} shipped · ⚠️ {seqStats.partial} partial · ❌ {seqStats.todo} TODO.
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              <th style={{ textAlign: 'left', padding: 6 }}>#</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Tool</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Purpose</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Status</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Our path</th>
            </tr>
          </thead>
          <tbody>
            {SEQUENCE.map((row) => {
              const s = STATE_STYLE[row.ours.state];
              return (
                <tr key={row.seq} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 6 }}>{row.seq}</td>
                  <td style={{ padding: 6, fontWeight: 600 }}>{row.tool}</td>
                  <td style={{ padding: 6 }}>{row.purpose}</td>
                  <td style={{ padding: 6 }}>
                    <span
                      style={{
                        background: s.bg,
                        color: s.fg,
                        padding: '2px 8px',
                        borderRadius: 3,
                        fontWeight: 600,
                      }}
                    >
                      {s.icon} {row.ours.state}
                    </span>
                  </td>
                  <td style={{ padding: 6, fontSize: '0.8rem', color: '#666' }}>{row.ours.path}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* Section 2: 17 missing components */}
      <section style={{ marginBottom: 32 }}>
        <h2>2. The 17 missing components (gap analysis)</h2>
        <p style={{ color: '#666' }}>
          Stats: ✅ {missingStats.shipped} shipped · ⚠️ {missingStats.partial} partial · ❌ {missingStats.todo} TODO.
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              <th style={{ textAlign: 'left', padding: 6 }}>Area</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Recommended</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Why</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Status</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Our note</th>
            </tr>
          </thead>
          <tbody>
            {MISSING.map((m) => {
              const s = STATE_STYLE[m.ours.state];
              return (
                <tr key={m.area} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 6, fontWeight: 600 }}>{m.area}</td>
                  <td style={{ padding: 6 }}>{m.recommendation}</td>
                  <td style={{ padding: 6, fontSize: '0.8rem' }}>{m.why}</td>
                  <td style={{ padding: 6 }}>
                    <span
                      style={{
                        background: s.bg,
                        color: s.fg,
                        padding: '2px 8px',
                        borderRadius: 3,
                        fontWeight: 600,
                      }}
                    >
                      {s.icon} {m.ours.state}
                    </span>
                  </td>
                  <td style={{ padding: 6, fontSize: '0.8rem', color: '#666' }}>{m.ours.note}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* Section 3: 12 MCP servers */}
      <section style={{ marginBottom: 32 }}>
        <h2>3. The 12 MCP servers (with risk levels)</h2>
        <p style={{ color: '#666' }}>
          Brutal rule from the spec: <strong>do not allow direct MCP access</strong>. Put every
          MCP server behind <strong>MCP Gateway + OPA + sandbox + audit</strong>.
          Stats: ✅ {mcpStats.shipped} shipped · ⚠️ {mcpStats.partial} partial · ❌ {mcpStats.todo} TODO.
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              <th style={{ textAlign: 'left', padding: 6 }}>MCP Server</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Purpose</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Risk</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Status</th>
              <th style={{ textAlign: 'left', padding: 6 }}>Our note</th>
            </tr>
          </thead>
          <tbody>
            {MCP_SERVERS.map((m) => {
              const s = STATE_STYLE[m.ours.state];
              const r = RISK_STYLE[m.risk];
              return (
                <tr key={m.type} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 6, fontWeight: 600 }}>{m.type}</td>
                  <td style={{ padding: 6 }}>{m.purpose}</td>
                  <td style={{ padding: 6 }}>
                    <span
                      style={{
                        background: r.bg,
                        color: r.fg,
                        padding: '2px 8px',
                        borderRadius: 3,
                        fontWeight: 600,
                      }}
                    >
                      {m.risk}
                    </span>
                  </td>
                  <td style={{ padding: 6 }}>
                    <span
                      style={{
                        background: s.bg,
                        color: s.fg,
                        padding: '2px 8px',
                        borderRadius: 3,
                        fontWeight: 600,
                      }}
                    >
                      {s.icon} {m.ours.state}
                    </span>
                  </td>
                  <td style={{ padding: 6, fontSize: '0.8rem', color: '#666' }}>{m.ours.note}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      {/* Final production sequence diagram */}
      <section style={{ marginBottom: 32 }}>
        <h2>4. The final production sequence (per the spec)</h2>
        <pre
          style={{
            background: '#f5f5f5',
            padding: 16,
            fontSize: '0.85rem',
            overflow: 'auto',
            lineHeight: 1.6,
          }}
        >
{`User / App
  → Load Balancer
  → API Gateway / WAF
  → REST / GraphQL / gRPC
  → SSO / OAuth / MFA
  → OPA + PolicyAI Pre-check         ← Layer 4 PolisAI today
  → Paperclip Control Plane          ← Stage-1 sandbox today
  → Agent Council                     ← 4-role local_council today (need 5+ governance roles)
  → Temporal Workflow                 ← ❌ NOT IN STACK
  → Kafka Event Bus                   ← Layer 8, Stage-1 wired
  → LangGraph Runtime                 ← langgraph_flow.py
  → A2A Collaboration                 ← OpenClaw Stage-1 gate-only
  → Model Gateway (LiteLLM)           ← Stage-2 fallback shipped
  → Circuit Breaker                   ← db_circuit_breaker.py
  → MCP Gateway                       ← ❌ NOT BUILT — bare MCP servers today
  → Approved MCP Server               ← need allowlist + sandbox + audit
  → RAG Layer (LlamaIndex/Haystack)   ← LangChain-Core only today
  → Vector + Search + Graph           ← ✅ Qdrant + ES + Neo4j
  → LLM (Ollama / LiteLLM)            ← ✅ shipped
  → Pydantic AI                       ← ✅ Stage-2 fallback shipped
  → Guardrails AI                     ← ⚠️ Stage-1 fail-OPEN scaffold
  → RAGAS / DeepEval / Promptfoo      ← ⚠️ Stage-1 scaffolds
  → PolicyAI Post-check               ← ❌ post-check not yet split from pre-check
  → Human Approval if risky           ← ⚠️ HITL framework partial
  → Execution
  → Langfuse + OTel + SIEM + Audit Vault   ← ✅ Langfuse + OTel + Jaeger + Prom
                                            ← ❌ SIEM + WORM-Vault not in stack
`}
        </pre>
      </section>

      {/* Brutal-final-recommendation summary */}
      <section
        style={{
          padding: 16,
          border: '2px solid #1f8a4c',
          borderRadius: 4,
          background: '#dff2dd',
          marginBottom: 16,
        }}
      >
        <h3 style={{ marginTop: 0, color: '#1f8a4c' }}>Brutal recommendation — biggest gap to close next</h3>
        <p>
          Per the spec: <strong>MCP security gateway + private MCP registry + tool permission model</strong>.
          Without these, every MCP server in <code>mcp/server_*.py</code> is a potential RCE/data-leak surface
          (especially Filesystem, GitHub, Postgres, Browser, Kubernetes — all rated high/critical risk).
        </p>
        <p>
          <strong>Single highest-leverage iteration:</strong> ship <code>scripts/mcp_gateway.py</code> +
          <code> config/mcp_allowlist.json</code> with PolisAI scope tokens per server. Estimated{' '}
          ~6 hr work; closes <em>3 of the 17 missing items</em> (MCP registry + MCP security gateway +
          partial threat-modeling for the MCP layer).
        </p>
      </section>

      {/* §49 compose footer */}
      <section
        style={{
          padding: 16,
          border: '1px dashed #999',
          borderRadius: 4,
          background: '#f8f8f8',
          fontSize: '0.85rem',
        }}
      >
        <strong>Composes with</strong> (per §49):
        <ul style={{ marginTop: 8 }}>
          <li>
            <Link href="/admin/policy">PolisAI policy</Link> — corresponds to OPA (#2 in
            sequence); Stage-2 OPA + Rego swap pending.
          </li>
          <li>
            <Link href="/admin/paperclip">Paperclip</Link> — corresponds to Paperclip control
            plane (#1); Stage-1 sandbox today, Stage-3 control-plane pending.
          </li>
          <li>
            <Link href="/admin/openclaw">OpenClaw</Link> — corresponds to A2A protocol (#7);
            Stage-1 gate-only, Stage-2 Dispatch RPC pending.
          </li>
          <li>
            <Link href="/admin/adapters">Adapter inventory</Link> — LiteLLM (model gateway,
            #4 missing item), PydanticAI (#6 in sequence), Kafka publisher.
          </li>
          <li>
            <Link href="/admin/eval-harness">Eval harness</Link> — Guardrails AI (#13),
            RAGAS/DeepEval (#14); all Stage-1 scaffolds.
          </li>
          <li>
            <Link href="/admin/tool-evaluation">Tool evaluation</Link> — verdicts for
            CrewAI/AutoGen/Agno/PraisonAI vs LiteLLM/PydanticAI.
          </li>
        </ul>
        <div style={{ marginTop: 8, color: '#666' }}>
          This page is the canonical map between the user's enterprise vision (this commit) and
          our current implementation state. Refresh after each Stage-2/Stage-3 promotion lands —
          drift between this page and reality is the bit-rot the next iteration must fix.
        </div>
      </section>
    </div>
  );
}
