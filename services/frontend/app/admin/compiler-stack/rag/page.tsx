import Link from 'next/link';
import Mermaid from '../../../../components/Mermaid';

export const metadata = { title: 'LLVM / MLIR in RAG — DocuMind' };

const FIT_MATRIX = [
  ['Simple chatbot RAG', 'No', 'stay at API, retrieval, and serving-runtime level'],
  ['Enterprise RAG with vector DB', 'Mostly no', 'use runtime and serving optimizations first'],
  ['Custom embedding acceleration', 'Maybe', 'only when embedding inference is the actual bottleneck'],
  ['Custom GPU/CPU optimization', 'Yes', 'low-level execution tuning'],
  ['Edge / on-device RAG', 'Yes', 'resource-constrained deployment path'],
  ['Model compiler / inference engine', 'Yes', 'compiler/runtime layer is the product'],
  ['HPC-scale RAG', 'Yes', 'hardware utilization at scale'],
  ['Custom vector search kernels', 'Advanced only', 'specialized low-level optimization work'],
] as const;

const TOOL_COMPARE = [
  ['vLLM', 'Serving runtime', 'High-throughput LLM serving', 'Production hosted inference'],
  ['ONNX Runtime', 'Inference runtime', 'Portable optimized inference', 'Embeddings, smaller model serving'],
  ['TensorRT', 'Inference optimization', 'NVIDIA GPU performance', 'High-performance GPU inference'],
  ['llama.cpp', 'Local runtime', 'Local / edge inference', 'Lightweight local LLMs'],
  ['IREE', 'MLIR compiler/runtime', 'Edge, mobile, accelerator-oriented deployment', 'Advanced edge/on-device AI'],
  ['LLVM / MLIR directly', 'Compiler infrastructure', 'Compiler/runtime research and deep optimization', 'Only advanced/custom systems'],
] as const;

const DECISION_FLOW = `flowchart TD
  S[Start] --> Q1{Building a normal API + retriever + vector DB + LLM app?}
  Q1 -->|yes| N[Skip LLVM / MLIR]
  Q1 -->|no| Q2{Runtime bottleneck in inference or kernels?}

  N --> A[Use FastAPI + vector DB + vLLM / API]
  Q2 -->|no| B[Optimize retrieval, batching, caching, routing first]
  Q2 -->|yes| Q3{Need optimized inference runtime only?}

  Q3 -->|yes| C[Use vLLM / ONNX Runtime / TensorRT / llama.cpp]
  Q3 -->|no| Q4{Building edge / custom accelerator / compiler path?}

  Q4 -->|yes| D[Consider IREE / MLIR / LLVM]
  Q4 -->|no| E[Stay at runtime layer, not compiler layer]`;

const NORMAL_SEQ = `sequenceDiagram
  autonumber
  participant U as User
  participant A as API
  participant R as Retriever
  participant V as Vector DB
  participant L as LLM runtime

  U->>A: query
  A->>R: retrieve
  R->>V: similarity search
  V-->>R: chunks
  R-->>A: context
  A->>L: prompt + generate
  L-->>A: answer
  A-->>U: response`;

const COMPILER_SEQ = `sequenceDiagram
  autonumber
  participant M as Model graph
  participant IR as MLIR
  participant O as Optimization passes
  participant B as LLVM / backend
  participant H as CPU/GPU/NPU runtime

  M->>IR: import model
  IR->>O: transform + lower ops
  O->>B: emit target-specific code
  B->>H: compiled runtime artifacts
  H-->>H: execute optimized inference`;

const EDGE_FLOW = `flowchart TD
  D[Device / appliance] --> A[Local API / embedded app]
  A --> M[Local embedding or compact LLM runtime]
  M --> V[Local vector store / compact index]
  M --> C[Compiled runtime]
  C --> H[CPU / GPU / NPU / accelerator]`;

const DOCUMIND_POSITION = [
  ['Current zone', 'Normal enterprise RAG, not compiler-stack RAG'],
  ['Current strengths', 'FastAPI orchestration, retrieval, policy, breaker, audit, observability'],
  ['Likely next optimizations', 'retrieval quality, serving/runtime choice, batching, caching, routing'],
  ['Not the next step', 'deep LLVM/MLIR/compiler work'],
  ['More realistic intermediate step', 'vLLM, ONNX Runtime, TensorRT, llama.cpp'],
] as const;

const QA = [
  ['Do most RAG engineers need LLVM or MLIR?', 'No. Most need better retrieval, serving, batching, caching, and observability first.'],
  ['When does LLVM/MLIR become worth learning?', 'When you work on inference runtimes, model compilers, edge deployment, or accelerator-specific optimization.'],
  ['Why not jump straight to MLIR?', 'Because most product bottlenecks are still data quality, retrieval, runtime serving, or cost control.'],
  ['What should come before LLVM/MLIR in a RAG stack?', 'vLLM, ONNX Runtime, TensorRT, llama.cpp, quantization, batching, routing, and cache optimization.'],
  ['Where does IREE fit?', 'IREE bridges MLIR-level compilation and practical deployment, especially for edge/mobile/accelerator-oriented systems.'],
  ['What is the most common mistake?', 'Discussing compiler-level optimization before proving application and runtime bottlenecks are already solved.'],
] as const;

export default function CompilerStackRagPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">LLVM / MLIR in RAG projects</h1>
          <p className="page-subtitle">
            Where compiler infrastructure fits in RAG systems, where it does not,
            and how to choose between runtime-level optimization and deeper compiler work.
          </p>
        </div>
      </div>

      <div className="card">
        <strong>Related</strong>
        <p style={{ marginTop: 8 }}>
          <Link href="/admin/lang-family/rag" style={{ color: '#1e3a8a' }}>
            /admin/lang-family/rag
          </Link>
          {' · '}
          <Link href="/admin/rag/deep" style={{ color: '#1e3a8a' }}>
            /admin/rag/deep
          </Link>
          {' · '}
          <Link href="/tools/ollama-vllm" style={{ color: '#1e3a8a' }}>
            /tools/ollama-vllm
          </Link>
        </p>
      </div>

      <div className="card">
        <strong>Simple meaning</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 120 }}>Term</th>
              <th style={{ width: 240 }}>Meaning</th>
              <th>In a RAG project</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code style={{ color: '#b91c1c', fontWeight: 700 }}>LLVM</code></td>
              <td>Compiler infrastructure and backend technologies</td>
              <td>Low-level execution optimization</td>
            </tr>
            <tr>
              <td><code style={{ color: '#b91c1c', fontWeight: 700 }}>MLIR</code></td>
              <td>Multi-level compiler IR and transformation framework</td>
              <td>Model graph and tensor optimization</td>
            </tr>
            <tr>
              <td><code style={{ color: '#b91c1c', fontWeight: 700 }}>RAG</code></td>
              <td>Retrieval-augmented generation</td>
              <td>Retrieval + ranking + LLM generation</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Decision flow</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={DECISION_FLOW} />
        </div>
      </div>

      <div className="card">
        <strong>Normal RAG vs compiler/runtime layer</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
            gap: 12,
            marginTop: 12,
          }}
        >
          <div className="card" style={{ padding: 12 }}>
            <strong>Normal RAG sequence</strong>
            <div style={{ marginTop: 12 }}>
              <Mermaid chart={NORMAL_SEQ} />
            </div>
          </div>
          <div className="card" style={{ padding: 12 }}>
            <strong>Compiler/runtime sequence</strong>
            <div style={{ marginTop: 12 }}>
              <Mermaid chart={COMPILER_SEQ} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <strong>When LLVM / MLIR is useful</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Scenario</th>
              <th style={{ width: 160 }}>LLVM / MLIR useful?</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {FIT_MATRIX.map(([scenario, useful, why]) => (
              <tr key={scenario}>
                <td>{scenario}</td>
                <td>{useful}</td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Runtime / compiler comparison matrix</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Tool</th>
              <th style={{ width: 180 }}>Layer</th>
              <th style={{ width: 260 }}>Best for</th>
              <th>Typical RAG use</th>
            </tr>
          </thead>
          <tbody>
            {TOOL_COMPARE.map(([tool, layer, bestFor, ragUse]) => (
              <tr key={tool}>
                <td>
                  <code style={{ color: '#b91c1c', fontWeight: 700 }}>{tool}</code>
                </td>
                <td>{layer}</td>
                <td>{bestFor}</td>
                <td>{ragUse}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Recommendation ladder</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Project type</th>
              <th>Recommendation</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>MVP RAG</td>
              <td>Skip LLVM/MLIR. Use FastAPI + vector DB + vLLM/API + observability.</td>
            </tr>
            <tr>
              <td>Enterprise RAG</td>
              <td>Try vLLM, ONNX Runtime, TensorRT, llama.cpp, batching, caching, and routing first.</td>
            </tr>
            <tr>
              <td>Edge / HPC RAG</td>
              <td>Then consider IREE, TVM, Triton, custom compiled runtimes, and deeper MLIR/LLVM work.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Where DocuMind currently sits</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Dimension</th>
              <th>Current position</th>
            </tr>
          </thead>
          <tbody>
            {DOCUMIND_POSITION.map(([dimension, position]) => (
              <tr key={dimension}>
                <td>{dimension}</td>
                <td>{position}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Edge / on-device RAG architecture</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={EDGE_FLOW} />
        </div>
        <p style={{ marginTop: 12, marginBottom: 0 }}>
          This is the zone where compiler/runtime concerns become much more
          relevant: smaller binaries, tighter memory budgets, lower power use,
          and accelerator-specific optimization.
        </p>
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
          If you are building a RAG application, LLVM/MLIR is usually irrelevant.
          If you are building the inference engine or hardware-optimized runtime under
          that RAG application, LLVM/MLIR becomes relevant.
        </p>
      </div>
    </>
  );
}
