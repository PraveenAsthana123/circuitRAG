import Link from 'next/link';
import Mermaid from '../../../../components/Mermaid';

export const metadata = { title: 'Chatbot system design — DocuMind' };

interface TopicRow {
  topic: string;
  subtopics: string[];
  chatbotReference: string[];
  interviewFocus: string;
}

const TOPICS: TopicRow[] = [
  {
    topic: 'Requirements',
    subtopics: ['functional', 'non-functional', 'constraints', 'KPIs'],
    chatbotReference: ['streaming answers', 'grounded responses', 'tenant isolation', 'latency target'],
    interviewFocus: 'Define what the chatbot must do and how success is measured.',
  },
  {
    topic: 'Capacity',
    subtopics: ['QPS', 'concurrency', 'storage growth', 'token volume'],
    chatbotReference: ['active sessions', 'vector index growth', 'Redis memory', 'tokens/day'],
    interviewFocus: 'Show that chatbot scale includes streams, embeddings, and token economics.',
  },
  {
    topic: 'HLD',
    subtopics: ['client', 'gateway', 'chat service', 'stores', 'workers'],
    chatbotReference: ['browser -> gateway -> chat service -> Redis/vector DB/LLM'],
    interviewFocus: 'Explain the system shape before diving into components.',
  },
  {
    topic: 'API design',
    subtopics: ['streaming APIs', 'contracts', 'auth', 'error envelopes'],
    chatbotReference: ['POST /chat', 'GET /chat/stream', 'JWT', 'citations + degraded flags'],
    interviewFocus: 'Tie API design to streaming UX and structured answer metadata.',
  },
  {
    topic: 'Data modeling',
    subtopics: ['entities', 'metadata', 'lineage', 'versioning'],
    chatbotReference: ['sessions', 'messages', 'documents', 'chunks', 'embeddings', 'prompt versions'],
    interviewFocus: 'Metadata quality drives retrieval, safety, and auditability.',
  },
  {
    topic: 'Database design',
    subtopics: ['OLTP', 'vector store', 'cache', 'object store'],
    chatbotReference: ['Postgres', 'Qdrant', 'Redis', 'S3/MinIO'],
    interviewFocus: 'Choose stores by role rather than product familiarity.',
  },
  {
    topic: 'Caching',
    subtopics: ['response cache', 'semantic cache', 'TTL', 'invalidation'],
    chatbotReference: ['repeated answers', 'embedding cache', 'session cache', 'doc-change invalidation'],
    interviewFocus: 'Caching improves latency and cost, but freshness and isolation are the hard parts.',
  },
  {
    topic: 'Async processing',
    subtopics: ['queues', 'workers', 'retries', 'DLQ'],
    chatbotReference: ['ingestion jobs', 'reindex', 'feedback labeling'],
    interviewFocus: 'Keep heavy work off the request path.',
  },
  {
    topic: 'Retrieval',
    subtopics: ['chunking', 'hybrid search', 'filters', 'rerank', 'context packing'],
    chatbotReference: ['vector + lexical + metadata filter + token-budget packing'],
    interviewFocus: 'Retrieval quality is the main quality engine of the chatbot.',
  },
  {
    topic: 'Session state',
    subtopics: ['bounded memory', 'summarization', 'durable history'],
    chatbotReference: ['Redis last N turns', 'summary snapshots', 'Postgres history'],
    interviewFocus: 'Separate short-term context from durable truth.',
  },
  {
    topic: 'Scaling',
    subtopics: ['horizontal scale', 'pooling', 'stream limits', 'backpressure'],
    chatbotReference: ['chat-service pods', 'pooled clients', 'bounded live streams'],
    interviewFocus: 'Protect dependencies, not just stateless pods.',
  },
  {
    topic: 'Reliability',
    subtopics: ['timeout', 'retry', 'breaker', 'fallback'],
    chatbotReference: ['LLM breaker', 'secondary model', 'degraded answer'],
    interviewFocus: 'Explain how the chatbot fails predictably under dependency impairment.',
  },
  {
    topic: 'Security',
    subtopics: ['authn', 'authz', 'tenant isolation', 'guardrails'],
    chatbotReference: ['JWT', 'tenant filters', 'prompt injection defense'],
    interviewFocus: 'Security includes classic API controls plus LLM-specific threats.',
  },
  {
    topic: 'Privacy',
    subtopics: ['PII', 'retention', 'audit', 'deletion'],
    chatbotReference: ['redacted logs', 'retained chat history', 'audited overrides'],
    interviewFocus: 'Sensitive data handling must be designed, not added later.',
  },
  {
    topic: 'Observability',
    subtopics: ['logs', 'traces', 'metrics', 'alerts'],
    chatbotReference: ['TTFT', 'retrieval latency', 'token usage', 'correlation ID'],
    interviewFocus: 'Break the pipeline into diagnosable stages.',
  },
  {
    topic: 'Performance',
    subtopics: ['latency budget', 'streaming', 'batching', 'payload minimization'],
    chatbotReference: ['top-K caps', 'early token streaming', 'batched embeddings'],
    interviewFocus: 'Every stage consumes latency budget; optimize where it matters.',
  },
  {
    topic: 'Cost',
    subtopics: ['token cost', 'routing', 'quotas', 'attribution'],
    chatbotReference: ['cheap model for simple queries', 'tenant budgets', 'cache savings'],
    interviewFocus: 'Economics is part of system design, not finance cleanup.',
  },
  {
    topic: 'Evaluation',
    subtopics: ['golden set', 'adversarial set', 'offline eval', 'regression'],
    chatbotReference: ['grounded-answer benchmark', 'jailbreak corpus', 'candidate vs baseline'],
    interviewFocus: 'A quality loop is required to evolve the chatbot safely.',
  },
  {
    topic: 'Deployment',
    subtopics: ['canary', 'rollback', 'flags', 'config versioning'],
    chatbotReference: ['prompt/model/reranker canary', 'retrieval-config rollback'],
    interviewFocus: 'Behavior-changing releases need controlled rollout.',
  },
  {
    topic: 'Failure modes',
    subtopics: ['outage', 'stale data', 'wrong cache', 'tenant leak', 'overload'],
    chatbotReference: ['LLM down', 'stale index', 'Redis outage', 'bad filter'],
    interviewFocus: 'Name concrete failures and the control that contains each one.',
  },
  {
    topic: 'Trade-offs',
    subtopics: ['recall vs precision', 'quality vs latency', 'quality vs cost'],
    chatbotReference: ['more chunks help recall but hurt latency and cost'],
    interviewFocus: 'A strong answer includes deliberate trade-offs, not just components.',
  },
  {
    topic: 'Testing',
    subtopics: ['unit', 'integration', 'load', 'chaos', 'security', 'eval'],
    chatbotReference: ['retrieval filter tests', 'stream concurrency', 'timeout drills'],
    interviewFocus: 'Testing spans software correctness, retrieval quality, safety, and latency.',
  },
];

const FLOWCHART = `flowchart TD
  U[User asks question] --> G[API Gateway]
  G --> A[JWT + rate limit + correlation ID]
  A --> C[Chat Service]
  C --> M[Load session memory]
  C --> R[Hybrid retrieval]
  R --> RR[Rerank + filter]
  RR --> P[Prompt builder]
  P --> L[LLM generate stream]
  L --> O[Guardrails + citations]
  O --> S[Stream answer back]
  S --> X[Logs + traces + metrics + audit]`;

const SEQUENCE = `sequenceDiagram
  autonumber
  participant U as User
  participant G as Gateway
  participant C as Chat Service
  participant M as Redis Memory
  participant V as Vector DB
  participant L as LLM

  U->>G: chat message
  G->>C: validated request + tenant context
  C->>M: load recent messages
  M-->>C: bounded history
  C->>V: hybrid retrieval + tenant filters
  V-->>C: candidate chunks
  C->>C: rerank + pack + build prompt
  C->>L: generate(stream=true)
  L-->>C: token stream
  C-->>U: streamed answer + citations`;

const IMPLEMENT = `flowchart TD
  A[1. Define BRD + KPIs] --> B[2. Build gateway + auth + rate limit]
  B --> C[3. Add chat service + streaming]
  C --> D[4. Add Redis session memory]
  D --> E[5. Build ingestion: parse -> chunk -> embed -> index]
  E --> F[6. Add hybrid retrieval + tenant filters]
  F --> G[7. Add rerank + context packing + prompt builder]
  G --> H[8. Integrate LLM + timeout + retry + breaker + fallback]
  H --> I[9. Add guardrails + PII + audit]
  I --> J[10. Add logs + traces + metrics + cost]
  J --> K[11. Build evaluation datasets]
  K --> L[12. Add canary + rollback + alerts]`;

export default function ChatbotSystemDesignPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">System design topics with chatbot reference</h1>
          <p className="page-subtitle">
            A reusable system-design study page anchored on a production-grade chatbot:
            requirements, HLD, storage, retrieval, reliability, security, observability,
            cost, testing, and interview framing.
          </p>
        </div>
      </div>

      <div className="card">
        <strong>Related</strong>
        <p style={{ marginTop: 8 }}>
          <Link href="/tools/system-design" style={{ color: '#1e3a8a' }}>
            /tools/system-design
          </Link>
          {' · '}
          <Link href="/admin/deep-dives" style={{ color: '#1e3a8a' }}>
            /admin/deep-dives
          </Link>
          {' · '}
          <Link href="/admin/python/syllabus" style={{ color: '#1e3a8a' }}>
            /admin/python/syllabus
          </Link>
        </p>
      </div>

      <div className="card">
        <strong>Anchor flowchart</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={FLOWCHART} />
        </div>
      </div>

      <div className="card">
        <strong>Anchor sequence diagram</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={SEQUENCE} />
        </div>
      </div>

      <div className="card">
        <strong>Network flow</strong>
        <pre className="md-pre" style={{ marginTop: 12 }}>
{`Browser / Mobile
  -> HTTPS / WSS
Load balancer / edge
  -> API Gateway
  -> Chat Service
     -> Redis
     -> Postgres
     -> Vector DB
     -> Model backend
     -> Observability exporters

Control planes:
- ingestion workers
- evaluation jobs
- admin / audit surfaces`}
        </pre>
      </div>

      <div className="card">
        <strong>Sequential steps to implement</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={IMPLEMENT} />
        </div>
      </div>

      <div className="card">
        <strong>Topic matrix</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Topic</th>
              <th style={{ width: 300 }}>Subtopics</th>
              <th style={{ width: 320 }}>Chatbot reference</th>
              <th>Interview focus</th>
            </tr>
          </thead>
          <tbody>
            {TOPICS.map((row) => (
              <tr key={row.topic}>
                <td>
                  <code style={{ color: '#b91c1c', fontWeight: 700 }}>{row.topic}</code>
                </td>
                <td>{row.subtopics.join(' · ')}</td>
                <td>{row.chatbotReference.join(' · ')}</td>
                <td>{row.interviewFocus}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Detail by topic</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          {TOPICS.map((row) => (
            <div key={row.topic} className="card" style={{ padding: 12 }}>
              <div style={{ color: '#b91c1c', fontWeight: 700 }}>{row.topic}</div>
              <div className="field-help" style={{ marginTop: 6 }}>
                Subtopics
              </div>
              <p style={{ marginTop: 4 }}>{row.subtopics.join(', ')}</p>
              <div className="field-help">Chatbot reference</div>
              <p style={{ marginTop: 4 }}>{row.chatbotReference.join(', ')}</p>
              <div className="field-help">What to explain in interview</div>
              <p style={{ marginTop: 4, marginBottom: 0 }}>{row.interviewFocus}</p>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
