import Link from 'next/link';
import Mermaid from '../../../../components/Mermaid';

export const metadata = { title: 'Lang family for RAG — DocuMind' };

interface ToolRow {
  tool: string;
  category: string;
  role: string;
  useWhen: string;
  avoidWhen: string;
  pros: string[];
  cons: string[];
}

const TOOLS: ToolRow[] = [
  {
    tool: 'LangChain',
    category: 'Application framework',
    role: 'Integrations, prompt chains, retrievers, tool-calling, higher-level agent abstractions',
    useWhen: 'General RAG app building and broad integration work',
    avoidWhen: 'You already have clear FastAPI orchestration and want minimal framework coupling',
    pros: ['broad ecosystem', 'quick integration path', 'good general-purpose app layer'],
    cons: ['abstraction sprawl', 'can become opaque in production'],
  },
  {
    tool: 'LangGraph',
    category: 'Orchestration/runtime',
    role: 'Stateful, long-running, multi-step, human-in-the-loop workflows',
    useWhen: 'Agentic RAG and complex control flow',
    avoidWhen: 'Your flow is mostly single-shot retrieval + generation',
    pros: ['explicit state', 'durable execution', 'strong fit for real agents'],
    cons: ['more engineering work', 'overkill for simple RAG'],
  },
  {
    tool: 'LangSmith',
    category: 'Observability/eval/deploy',
    role: 'Trace, debug, test, evaluate, and deploy LLM apps',
    useWhen: 'Managed LangChain-native QA/debugging/ops',
    avoidWhen: 'You want OSS/self-hosted observability or are not LangChain-centric',
    pros: ['strong managed tracing/eval/deploy workflow', 'tight fit with LangChain/LangGraph'],
    cons: ['vendor coupling', 'not the OSS-first path'],
  },
  {
    tool: 'LangServe',
    category: 'Serving layer',
    role: 'Expose LangChain runnables/chains as APIs',
    useWhen: 'Quick serving for LangChain-native apps',
    avoidWhen: 'You already have a stable FastAPI serving layer and need custom contracts',
    pros: ['quick API exposure'],
    cons: ['optional if FastAPI already exists', 'narrow role'],
  },
  {
    tool: 'Langfuse',
    category: 'OSS observability/eval',
    role: 'Traces, prompts, datasets, scores, experiments, dashboards',
    useWhen: 'OSS/self-hosted LLM observability',
    avoidWhen: 'You only need basic logs/metrics and are not ready for AI-specific tracing',
    pros: ['open source', 'self-hostable', 'strong prompt/dataset/score support'],
    cons: ['not an orchestration framework', 'separate choice from app/runtime layer'],
  },
  {
    tool: 'LlamaIndex',
    category: 'Data/RAG framework',
    role: 'Ingestion, indexing, retrieval, query engines',
    useWhen: 'Document-heavy RAG',
    avoidWhen: 'Your retrieval path is simple and already maintainable in direct code',
    pros: ['strong retrieval/document focus', 'useful ingestion/query abstractions'],
    cons: ['not the main answer for complex stateful agent control'],
  },
  {
    tool: 'LlamaParse',
    category: 'Document parsing',
    role: 'Parse PDFs, tables, layout-heavy docs',
    useWhen: 'Difficult enterprise documents are the quality bottleneck',
    avoidWhen: 'Your data is already clean text or parsing is not the bottleneck',
    pros: ['high-value for hard document parsing'],
    cons: ['narrow scope', 'not a full framework by itself'],
  },
  {
    tool: 'LlamaCloud',
    category: 'Managed data platform',
    role: 'Managed parsing, ingestion/retrieval APIs, eval/observability',
    useWhen: 'Faster managed production setup',
    avoidWhen: 'You want full in-house control over ingestion and retrieval',
    pros: ['faster managed production path', 'strong fit for data-heavy enterprise RAG'],
    cons: ['managed-service dependency'],
  },
];

const DOCUMIND_FIT = [
  ['Langfuse', 'high', 'Strongest near-term fit for AI-specific tracing/eval on top of current OTel and metrics'],
  ['LlamaParse', 'medium', 'Useful if document parsing quality becomes the main retrieval bottleneck'],
  ['LlamaIndex', 'medium', 'Useful if retrieval abstractions become harder to maintain internally'],
  ['LangGraph', 'medium', 'Only if stateful agent workflows become central'],
  ['LangSmith', 'low-medium', 'More compelling if the stack becomes LangChain/LangGraph-centric'],
  ['LangChain', 'low-medium', 'Useful for integrations, but current design prefers direct control'],
  ['LangServe', 'low', 'Current FastAPI service model already covers serving'],
  ['LlamaCloud', 'low-medium', 'Only if managed ingestion/retrieval becomes strategically preferable'],
] as const;

const ARCH_COMPARE = [
  ['Raw FastAPI + custom retrieval', 'Maximum control and explicit service contracts', 'clear ownership · strong breaker/audit/policy control', 'more code to maintain'],
  ['LangChain + FastAPI', 'Broad integrations quickly', 'fast composition · many integrations', 'abstraction sprawl · opaque runtime behavior'],
  ['LlamaIndex + FastAPI', 'Document/retrieval quality is the hard problem', 'stronger ingestion/query abstractions', 'less focused on stateful agent control'],
  ['LangGraph + LangChain components', 'Workflow/state complexity is the hard problem', 'durable state · branching · HITL · checkpoints', 'more operational complexity'],
] as const;

const STACK_FLOW = `flowchart TD
  U[User query] --> A[App / API layer]
  A --> W{Workflow complexity?}
  W -->|simple| LC[LangChain or plain FastAPI]
  W -->|stateful agentic| LG[LangGraph]

  D[Documents] --> P{Parsing hard?}
  P -->|yes| LP[LlamaParse]
  P -->|no| LI[LlamaIndex or native pipeline]
  LP --> LI

  LI --> V[Vector DB / retrieval backend]
  LC --> R[Retrieval + generation path]
  LG --> R
  V --> R

  R --> O{Observability choice}
  O -->|managed| LS[LangSmith]
  O -->|OSS/self-hosted| LF[Langfuse]

  R --> S{Serving choice}
  S -->|LangChain-native quick serve| LSV[LangServe]
  S -->|custom service| F[FastAPI]`;

const MVP_ENTERPRISE = `flowchart TD
  S[Start] --> Q1{Mostly a document retrieval problem?}
  Q1 -->|yes| LI[LlamaIndex]
  Q1 -->|no| LC[LangChain or plain FastAPI]

  LI --> Q2{Hard PDFs / tables / layouts?}
  LC --> Q2
  Q2 -->|yes| LP[LlamaParse]
  Q2 -->|no| Q3{Need stateful agent workflow?}
  LP --> Q3

  Q3 -->|yes| LG[Add LangGraph]
  Q3 -->|no| Q4{Need managed LangChain-native tracing/eval?}
  LG --> Q4

  Q4 -->|yes| LS[LangSmith]
  Q4 -->|no| LF[Langfuse]

  LS --> Q5{Need quick LangChain-native serving?}
  LF --> Q5
  Q5 -->|yes| LSV[LangServe]
  Q5 -->|no| F[FastAPI]`;

const RAW_SEQ = `sequenceDiagram
  autonumber
  participant U as User
  participant A as FastAPI service
  participant R as Retrieval layer
  participant L as LLM

  U->>A: chat request
  A->>R: retrieve tenant-safe chunks
  R-->>A: ranked context
  A->>A: build prompt + apply policy
  A->>L: generate
  L-->>A: answer
  A-->>U: response`;

const LANGCHAIN_SEQ = `sequenceDiagram
  autonumber
  participant U as User
  participant A as FastAPI service
  participant C as LangChain chain
  participant R as Retriever
  participant L as LLM

  U->>A: chat request
  A->>C: invoke chain
  C->>R: retrieve context
  R-->>C: chunks
  C->>L: prompt + generate
  L-->>C: answer
  C-->>A: structured result
  A-->>U: response`;

const LANGGRAPH_SEQ = `sequenceDiagram
  autonumber
  participant U as User
  participant A as API / agent entry
  participant G as LangGraph runtime
  participant R as Retrieval node
  participant T as Tool / policy node
  participant L as LLM node

  U->>A: task request
  A->>G: start graph with state
  G->>R: retrieve / rewrite / rerank
  R-->>G: context state update
  G->>T: apply policy / branch decision
  T-->>G: next edge
  G->>L: generate / tool call loop
  L-->>G: output + updated state
  G-->>A: final state / answer
  A-->>U: response`;

const COST_COMPARE = [
  ['Raw FastAPI + custom retrieval', 'medium-high', 'low-medium', 'medium', 'more in-house engineering time'],
  ['LangChain + FastAPI', 'low-medium', 'medium', 'medium', 'abstraction/debug overhead'],
  ['LlamaIndex + FastAPI', 'medium', 'medium', 'medium', 'additional framework surface for retrieval layer'],
  ['LangGraph + LangChain components', 'high', 'medium-high', 'high', 'stateful workflow complexity'],
  ['LangSmith', 'low build, paid platform', 'recurring managed cost', 'lower internal ops', 'vendor coupling'],
  ['Langfuse', 'medium setup', 'lower license cost, infra cost if self-hosted', 'medium', 'self-hosting complexity'],
  ['LlamaParse / LlamaCloud', 'low build for parsing/managed path', 'recurring service cost', 'lower pipeline ops', 'managed dependency'],
] as const;

const QA = [
  ['Why not just use LangChain for everything?', 'Because LangChain is an app framework, not the answer to every layer. Retrieval, stateful orchestration, and observability are separate concerns.'],
  ['When would you pick LangGraph over LangChain agents?', 'When you need explicit state, branching, retries, checkpoints, durable execution, or HITL.'],
  ['When is LlamaIndex better than LangChain?', 'When the hard problem is document ingestion and retrieval quality rather than general app composition.'],
  ['Why might Langfuse fit before LangSmith?', 'If the current stack is not deeply LangChain-native and OSS/self-hosted observability is preferred.'],
  ['Why not always use LlamaParse?', 'Because parsing is only worth paying for when document quality is the actual retrieval bottleneck.'],
  ['Why keep raw FastAPI at all?', 'Because explicit orchestration can be easier to govern, debug, audit, and integrate with custom policy and breaker patterns.'],
  ['What is the most common mistake?', 'Using multiple frameworks at once without a clear bottleneck, which increases complexity faster than quality.'],
] as const;

export default function LangFamilyRagPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Lang family around RAG</h1>
          <p className="page-subtitle">
            A clear map of LangChain, LangGraph, LangSmith, LangServe, Langfuse,
            LlamaIndex, LlamaParse, and LlamaCloud: what each does, where it fits,
            and what is actually needed for MVP versus enterprise.
          </p>
        </div>
      </div>

      <div className="card">
        <strong>Related</strong>
        <p style={{ marginTop: 8 }}>
          <Link href="/admin/deep-dives" style={{ color: '#1e3a8a' }}>
            /admin/deep-dives
          </Link>
          {' · '}
          <Link href="/admin/rag/deep" style={{ color: '#1e3a8a' }}>
            /admin/rag/deep
          </Link>
          {' · '}
          <Link href="/admin/llmops/deep" style={{ color: '#1e3a8a' }}>
            /admin/llmops/deep
          </Link>
        </p>
      </div>

      <div className="card">
        <strong>Stack flow</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={STACK_FLOW} />
        </div>
      </div>

      <div className="card">
        <strong>MVP vs enterprise decision flow</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={MVP_ENTERPRISE} />
        </div>
      </div>

      <div className="card">
        <strong>Tool map</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 150 }}>Tool</th>
              <th style={{ width: 180 }}>Category</th>
              <th style={{ width: 340 }}>Main role</th>
              <th>Use when</th>
            </tr>
          </thead>
          <tbody>
            {TOOLS.map((row) => (
              <tr key={row.tool}>
                <td>
                  <code style={{ color: '#b91c1c', fontWeight: 700 }}>{row.tool}</code>
                </td>
                <td>{row.category}</td>
                <td>{row.role}</td>
                <td>{row.useWhen}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Pros and cons</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          {TOOLS.map((row) => (
            <div key={row.tool} className="card" style={{ padding: 12 }}>
              <div style={{ color: '#b91c1c', fontWeight: 700 }}>{row.tool}</div>
              <div className="field-help" style={{ marginTop: 6 }}>
                Pros
              </div>
              <p style={{ marginTop: 4 }}>{row.pros.join(' · ')}</p>
              <div className="field-help">Cons</div>
              <p style={{ marginTop: 4, marginBottom: 0 }}>{row.cons.join(' · ')}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <strong>Recommended stacks</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Project type</th>
              <th>Recommended stack</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Simple RAG</td>
              <td>LangChain or LlamaIndex + Qdrant + Langfuse</td>
            </tr>
            <tr>
              <td>Document-heavy RAG</td>
              <td>LlamaIndex + LlamaParse + Qdrant</td>
            </tr>
            <tr>
              <td>Agentic RAG</td>
              <td>LangGraph + LangChain components + LangSmith or Langfuse</td>
            </tr>
            <tr>
              <td>Enterprise OSS RAG</td>
              <td>LlamaIndex + LangGraph + Langfuse + Prometheus</td>
            </tr>
            <tr>
              <td>Managed enterprise RAG</td>
              <td>LlamaCloud + LangGraph + LangSmith</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Lang family vs DocuMind current stack</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 160 }}>Tool</th>
              <th style={{ width: 120 }}>Fit</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {DOCUMIND_FIT.map(([tool, fit, why]) => (
              <tr key={tool}>
                <td>
                  <code style={{ color: '#b91c1c', fontWeight: 700 }}>{tool}</code>
                </td>
                <td>{fit}</td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>When not to use</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          {TOOLS.map((row) => (
            <div key={`${row.tool}-avoid`} className="card" style={{ padding: 12 }}>
              <div style={{ color: '#b91c1c', fontWeight: 700 }}>{row.tool}</div>
              <p style={{ marginTop: 8, marginBottom: 0 }}>{row.avoidWhen}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <strong>Architecture comparison</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Approach</th>
              <th style={{ width: 220 }}>Best when</th>
              <th style={{ width: 260 }}>Pros</th>
              <th>Cons</th>
            </tr>
          </thead>
          <tbody>
            {ARCH_COMPARE.map(([approach, bestWhen, pros, cons]) => (
              <tr key={approach}>
                <td>{approach}</td>
                <td>{bestWhen}</td>
                <td>{pros}</td>
                <td>{cons}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Sequence diagrams by approach</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          <div className="card" style={{ padding: 12 }}>
            <strong>Raw FastAPI + custom retrieval</strong>
            <div style={{ marginTop: 12 }}>
              <Mermaid chart={RAW_SEQ} />
            </div>
          </div>
          <div className="card" style={{ padding: 12 }}>
            <strong>LangChain + FastAPI</strong>
            <div style={{ marginTop: 12 }}>
              <Mermaid chart={LANGCHAIN_SEQ} />
            </div>
          </div>
          <div className="card" style={{ padding: 12 }}>
            <strong>LangGraph + LangChain components</strong>
            <div style={{ marginTop: 12 }}>
              <Mermaid chart={LANGGRAPH_SEQ} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <strong>Cost comparison</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Approach</th>
              <th style={{ width: 180 }}>Build cost</th>
              <th style={{ width: 180 }}>Runtime cost</th>
              <th style={{ width: 140 }}>Ops cost</th>
              <th>Hidden cost</th>
            </tr>
          </thead>
          <tbody>
            {COST_COMPARE.map(([approach, build, runtime, ops, hidden]) => (
              <tr key={approach}>
                <td>{approach}</td>
                <td>{build}</td>
                <td>{runtime}</td>
                <td>{ops}</td>
                <td>{hidden}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Interview Q&amp;A</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          {QA.map(([question, answer]) => (
            <div key={question} className="card" style={{ padding: 12 }}>
              <div style={{ color: '#b91c1c', fontWeight: 700 }}>{question}</div>
              <p style={{ marginTop: 8, marginBottom: 0 }}>{answer}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Brutal decision rule</strong>
        <p style={{ marginTop: 8 }}>
          Use <code>LangChain</code> when application composition matters. Use{' '}
          <code>LlamaIndex</code> when retrieval quality matters. Use{' '}
          <code>LangGraph</code> when state and control flow matter. Use{' '}
          <code>Langfuse</code> for OSS observability. Use <code>LangSmith</code>{' '}
          for managed LangChain-native debugging and evaluation.
        </p>
      </div>
    </>
  );
}
