/**
 * Unified deep-dive index — one page that links to every interview-grade
 * deep-dive route in the project. Closes the user-reported gap "the
 * deep-dive navigation is incomplete." Operators / interviewers land
 * here and pick the area they want.
 */

import Link from 'next/link';

export const metadata = { title: 'Deep dives — DocuMind' };

interface DeepDiveLink {
  slug: string;
  title: string;
  href: string;
  topics: number;
  blurb: string;
  publicSibling?: { href: string; label: string };
}

const DEEP_DIVES: DeepDiveLink[] = [
  {
    slug: 'audio-tts-chatbot',
    title: 'Audio / TTS for chatbot',
    href: '/admin/audio/tts',
    topics: 5,
    blurb: 'TTS providers, speech architecture, repo fit, and implementation path for adding audio output to the chatbot',
    publicSibling: { href: '/tools/ollama-vllm', label: '/tools/ollama-vllm (LLM serving)' },
  },
  {
    slug: 'compiler-stack-rag',
    title: 'LLVM / MLIR · RAG fit',
    href: '/admin/compiler-stack/rag',
    topics: 6,
    blurb: 'Where compiler infrastructure fits in RAG, when to skip it, and how it compares with vLLM, ONNX Runtime, TensorRT, llama.cpp, and IREE',
    publicSibling: { href: '/tools/ollama-vllm', label: '/tools/ollama-vllm (serving/runtime overview)' },
  },
  {
    slug: 'lang-family-rag',
    title: 'Lang family · RAG map',
    href: '/admin/lang-family/rag',
    topics: 8,
    blurb: 'LangChain · LangGraph · LangSmith · LangServe · Langfuse · LlamaIndex · LlamaParse · LlamaCloud — roles, trade-offs, and MVP vs enterprise fit',
    publicSibling: { href: '/admin/rag/deep', label: '/admin/rag/deep (RAG building blocks)' },
  },
  {
    slug: 'chatbot-system-design',
    title: 'System design · chatbot map',
    href: '/admin/system-design/chatbot',
    topics: 22,
    blurb: 'Requirements · capacity · HLD · APIs · data modeling · stores · cache · retrieval · reliability · security · observability · cost · testing — all anchored on a chatbot example',
    publicSibling: { href: '/tools/system-design', label: '/tools/system-design (tool diagrams overview)' },
  },
  {
    slug: 'python',
    title: 'Python',
    href: '/admin/python/deep',
    topics: 12,
    blurb: 'async/await · decorators · context managers · exceptions · typing/Pydantic · generators · GIL · classes · FastAPI · HTTP+breaker+idempotency · observability · RAG-specific Python',
    publicSibling: { href: '/admin/python', label: '/admin/python (flat catalog, 60 topics)' },
  },
  {
    slug: 'llmops',
    title: 'LLMOps',
    href: '/admin/llmops/deep',
    topics: 10,
    blurb: 'prompt registry · evaluation+regression gate · audit+correlation · draft fallback+HITL · RAG data lifecycle · observability · model management · experiment tracking · deployment+serving · SLM vs LLM routing',
    publicSibling: { href: '/admin/llmops', label: '/admin/llmops (scorecard, 14 categories)' },
  },
  {
    slug: 'database',
    title: 'Database / datastores',
    href: '/admin/database/deep',
    topics: 6,
    blurb: 'Postgres+RLS · Qdrant · Redis · Kafka · ClickHouse · S3-compatible object storage — by ROLE not by technology',
    publicSibling: { href: '/tools/database-scenarios', label: '/tools/database-scenarios (pattern catalog)' },
  },
  {
    slug: 'mcp',
    title: 'MCP (Model Context Protocol)',
    href: '/admin/mcp/deep',
    topics: 2,
    blurb: 'MCP server (per-namespace tool host) · MCP client + breaker + draft fallback',
    publicSibling: { href: '/tools/circuit-breakers-list', label: '/tools/circuit-breakers-list (related)' },
  },
  {
    slug: 'breakers',
    title: 'Circuit breakers',
    href: '/admin/breakers/deep',
    topics: 2,
    blurb: 'Generic CB (state machine) · Transport CB (Qdrant + Neo4j) — fail-fast resilience',
    publicSibling: { href: '/tools/circuit-breakers-list', label: '/tools/circuit-breakers-list' },
  },
  {
    slug: 'rag',
    title: 'RAG',
    href: '/admin/rag/deep',
    topics: 2,
    blurb: 'Chunking strategy · Hybrid retrieval (vector + graph + cache)',
    publicSibling: { href: '/tools/rag-scenarios', label: '/tools/rag-scenarios (36 scenarios)' },
  },
  {
    slug: 'microservices',
    title: 'Microservices',
    href: '/admin/microservices/deep',
    topics: 2,
    blurb: 'Service boundaries (domain decomposition) · REST vs gRPC vs MCP — when each fits',
    publicSibling: { href: '/tools/microservice-scenarios', label: '/tools/microservice-scenarios' },
  },
  {
    slug: 'data',
    title: 'Data preprocessing',
    href: '/admin/data/deep',
    topics: 3,
    blurb: 'CSV/tabular · PDF/DOCX/HTML→text · Image/video/audio multimedia — file-type-by-file-type pipeline',
    publicSibling: { href: '/upload', label: '/upload (try it)' },
  },
];

const ENTRY_PATHS = [
  {
    title: 'Architecture',
    color: '#dbeafe',
    description: 'Start here if learning how the system fits together.',
    order: ['microservices', 'database', 'mcp', 'rag', 'breakers'],
  },
  {
    title: 'Operating the platform',
    color: '#dcfce7',
    description: 'Start here if running on-call or debugging an incident.',
    order: ['breakers', 'database', 'mcp', 'llmops'],
  },
  {
    title: 'Interview prep',
    color: '#ede9fe',
    description: 'Start here if preparing for a senior backend / AI-platform interview.',
    order: ['python', 'llmops', 'database', 'rag', 'microservices'],
  },
];

export default function DeepDivesIndexPage() {
  const bySlug = Object.fromEntries(DEEP_DIVES.map((d) => [d.slug, d]));
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Deep dives — interview-grade architecture explanations</h1>
          <p className="page-subtitle">
            Eight areas, all using the same 20-dimension universal interview
            framework: core concept · problem · why · when/when-not · IPO ·
            flowchart · sequence · alternatives · challenges · edge cases ·
            failure modes · monitoring · testing · security · scaling ·
            maturity · limitations · project fit · interview line.
          </p>
        </div>
      </div>

      {/* Entry paths */}
      <div className="card">
        <strong>Pick an entry path</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          {ENTRY_PATHS.map((p) => (
            <div
              key={p.title}
              className="card"
              style={{ padding: 12, backgroundColor: p.color }}
            >
              <strong>{p.title}</strong>
              <p style={{ marginTop: 6, marginBottom: 8 }}>{p.description}</p>
              <ol style={{ paddingLeft: 18, margin: 0 }}>
                {p.order.map((s) => (
                  <li key={s}>
                    <Link href={bySlug[s].href} style={{ color: '#1e3a8a' }}>
                      {bySlug[s].title}
                    </Link>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </div>

      {/* Full list */}
      <div className="card">
        <strong>All deep dives ({DEEP_DIVES.length})</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Topic</th>
              <th style={{ width: 80 }}>Topics</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {DEEP_DIVES.map((d) => (
              <tr key={d.slug}>
                <td>
                  <Link href={d.href} style={{ color: '#1e3a8a', fontWeight: 600 }}>
                    {d.title} →
                  </Link>
                  {d.publicSibling && (
                    <div className="field-help" style={{ marginTop: 4 }}>
                      sibling:{' '}
                      <Link href={d.publicSibling.href} style={{ color: '#5a5a77' }}>
                        {d.publicSibling.label}
                      </Link>
                    </div>
                  )}
                </td>
                <td>
                  <code>{d.topics}</code>
                </td>
                <td>{d.blurb}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Universal template</strong>
        <p style={{ marginTop: 8 }}>
          Every topic on every deep dive carries the same 20 dimensions.
          The component is{' '}
          <code>services/frontend/components/UniversalDeepDive.tsx</code>;
          adding a new deep-dive is a content task, not a layout task.
        </p>
      </div>
    </>
  );
}
