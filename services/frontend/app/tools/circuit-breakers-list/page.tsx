import Link from 'next/link';
import CodeBlock from '../../../components/CodeBlock';
import Mermaid from '../../../components/Mermaid';
import { readRepoFile } from '../../../lib/read-code';

export const metadata = { title: 'Circuit Breakers — DocuMind' };

type Breaker = {
  name: string;
  guards: string;
  signals: string;
  codePath: string;
  docsUrl: string;
  docsLabel: string;
  paperUrl?: string;
  paperLabel?: string;
};

function breakerKind(name: string): 'stateful' | 'stream' | 'budget' {
  if (name === 'Token CB') return 'budget';
  if (
    name === 'Citation-Deadline Signal' ||
    name === 'Forbidden-Pattern Signal' ||
    name === 'Cognitive Circuit Breaker (CCB)'
  ) {
    return 'stream';
  }
  return 'stateful';
}

function breakerFlowchart(b: Breaker): string {
  const kind = breakerKind(b.name);
  if (kind === 'stateful') {
    return `flowchart LR
  req[Caller requests protected operation] --> allow{Breaker state?}
  allow -->|closed| call[Call dependency]
  allow -->|open| fast[Fail fast / degraded path]
  allow -->|half_open| probe[Single probe call]
  call --> ok{Result}
  probe --> probeOk{Probe result}
  ok -->|success| closed[Record success; stay closed]
  ok -->|failure| fail[Record failure; maybe open]
  probeOk -->|success| reset[Close breaker]
  probeOk -->|failure| reopen[Re-open breaker]
  fast --> out[Return error envelope or fallback]
  closed --> out
  fail --> out
  reset --> out
  reopen --> out`;
  }
  if (kind === 'budget') {
    return `flowchart LR
  usage[Token usage sample] --> check{Within tenant budget?}
  check -->|yes| allow[Allow model call]
  check -->|soft breach| throttle[Throttle / cheaper model / shorter context]
  check -->|hard breach| block[Block request]
  allow --> out[Decision returned]
  throttle --> out
  block --> out`;
  }
  return `flowchart LR
  stream[Streaming tokens] --> inspect[Inspect stream signal]
  inspect --> rule{Rule tripped?}
  rule -->|no| cont[Continue stream]
  rule -->|yes| stop[Interrupt / block / audit]
  cont --> stream
  stop --> out[Return governed failure path]`;
}

function breakerSequence(b: Breaker): string {
  const kind = breakerKind(b.name);
  if (kind === 'stateful') {
    return `sequenceDiagram
  autonumber
  participant C as Caller
  participant B as ${b.name}
  participant D as Dependency
  C->>B: allow()?
  alt state = closed
    B-->>C: proceed
    C->>D: protected call
    D-->>C: success or failure
    C->>B: record_success() / record_failure()
    B-->>C: state updated
  else state = open
    B-->>C: reject immediately
    C-->>C: fallback or error envelope
  else state = half_open
    B-->>C: allow probe
    C->>D: single probe call
    D-->>C: probe result
    C->>B: record probe outcome
  end`;
  }
  if (kind === 'budget') {
    return `sequenceDiagram
  autonumber
  participant T as Tenant request
  participant B as ${b.name}
  participant M as Model runtime
  T->>B: budget decision needed
  B->>B: compare running usage vs budget
  alt within budget
    B-->>T: allow
    T->>M: proceed with call
  else soft breach
    B-->>T: throttle / degrade
  else hard breach
    B-->>T: block
  end`;
  }
  return `sequenceDiagram
  autonumber
  participant A as Answer stream
  participant B as ${b.name}
  participant O as Operator / audit
  A->>B: next token / chunk
  B->>B: evaluate ${b.signals}
  alt rule clean
    B-->>A: continue
  else rule tripped
    B-->>A: interrupt / block
    B->>O: emit audit / signal
  end`;
}

function breakerInput(b: Breaker): string {
  if (breakerKind(b.name) === 'budget') return 'Tenant request + running token usage + policy budget.';
  if (breakerKind(b.name) === 'stream') return 'Streaming tokens or partial output chunks from the model path.';
  return 'Protected dependency call with breaker state, thresholds, and timeout budget.';
}

function breakerProcess(b: Breaker): string[] {
  if (breakerKind(b.name) === 'budget') {
    return [
      'Read current usage window for the tenant.',
      'Compare usage against configured budget thresholds.',
      'Return allow / throttle / block decision.',
      'Emit metrics for cost-control and operator visibility.',
    ];
  }
  if (breakerKind(b.name) === 'stream') {
    return [
      'Inspect each streamed token or chunk against the configured signal.',
      'Allow clean output to continue flowing.',
      'Interrupt immediately when the guard condition trips.',
      'Emit audit or monitoring evidence for the interruption.',
    ];
  }
  return [
    'Check breaker state before the dependency call.',
    'Allow call only when closed or half-open probe is permitted.',
    'Record success or failure outcome after the call.',
    'Transition state machine when thresholds or recovery timeout are crossed.',
  ];
}

function breakerOutput(b: Breaker): string {
  if (breakerKind(b.name) === 'budget') return 'A cost-control decision: allow, throttle/degrade, or block.';
  if (breakerKind(b.name) === 'stream') return 'A governed streaming outcome: continue, interrupt, or block with audit evidence.';
  return 'A fast-fail or allow decision plus an updated breaker state that operators can observe.';
}

function breakerChallenges(b: Breaker): string[] {
  if (breakerKind(b.name) === 'budget') {
    return [
      'Budget thresholds must match real tenant usage patterns.',
      'Soft-throttle paths need to be honest and predictable.',
      'Cost controls must not silently corrupt answer quality.',
    ];
  }
  if (breakerKind(b.name) === 'stream') {
    return [
      'Signal tuning is hard without real production samples.',
      'False positives can interrupt valid output.',
      'Signals must be fast enough not to slow the token path.',
    ];
  }
  return [
    'Threshold tuning without production traffic data is hard.',
    'Per-process state can diverge across replicas.',
    'Retries and breakers must work together instead of fighting each other.',
  ];
}

function breakerEdgeCases(b: Breaker): string[] {
  if (breakerKind(b.name) === 'budget') {
    return [
      'Burst traffic from one tenant may require tier-aware thresholds instead of one global budget.',
      'Usage windows must survive process restarts or the breaker becomes too permissive.',
    ];
  }
  if (breakerKind(b.name) === 'stream') {
    return [
      'A harmless repetition burst can look like drift unless the signal is tuned carefully.',
      'Regex-based pattern signals can over-trigger on quoted or cited content.',
    ];
  }
  return [
    'Slow-but-not-failing dependencies still need explicit timeouts or the breaker never opens.',
    'One unhealthy replica can open locally while others stay closed; operators need per-instance visibility.',
  ];
}

function breakerLimitations(b: Breaker): string[] {
  if (breakerKind(b.name) === 'budget') {
    return [
      'Cost control does not by itself optimize model routing quality.',
      'Budgets help protect spend, not guarantee business value.',
    ];
  }
  if (breakerKind(b.name) === 'stream') {
    return [
      'Signal-based interruption is heuristic, not semantic proof.',
      'Stream guards reduce risk but do not replace offline evaluation.',
    ];
  }
  return [
    'Current breaker state is local to the process unless externalized.',
    'A breaker mitigates dependency failure but does not replace capacity planning or root-cause fixes.',
  ];
}

const BREAKERS: Breaker[] = [
  {
    name: 'Generic Circuit Breaker',
    guards: 'Any external dependency (Qdrant, Neo4j, Ollama, HTTP APIs, databases)',
    signals: 'Consecutive failure count vs threshold; recovery timeout; HALF_OPEN probe',
    codePath: 'libs/py/documind_core/circuit_breaker.py',
    docsUrl: 'https://martinfowler.com/bliki/CircuitBreaker.html',
    docsLabel: 'Martin Fowler — Circuit Breaker',
  },
  {
    name: 'Retrieval CB',
    guards: 'Qdrant vector search + Neo4j graph traversal',
    signals: 'Timeouts > 1s; ANN engine 5xx; graph deadlocks',
    codePath: 'libs/py/documind_core/breakers.py (RetrievalCircuitBreaker)',
    docsUrl: 'https://qdrant.tech/documentation/tutorials/retrieval-quality/',
    docsLabel: 'Qdrant retrieval reliability',
  },
  {
    name: 'Token CB',
    guards: 'LLM token spend per tenant per minute (FinOps budget)',
    signals: 'Running token count vs tenant budget; decisions: allow / throttle / block',
    codePath: 'libs/py/documind_core/breakers.py (TokenCircuitBreaker, TokenBreakerDecision)',
    docsUrl: 'https://cloud.google.com/architecture/ai-ml/cost-optimization-generative-ai',
    docsLabel: 'Google Cloud — GenAI cost controls',
  },
  {
    name: 'Agent-Loop CB',
    guards: 'Agentic recursion: tool-calling depth + wall-clock + step count',
    signals: 'Depth > max; wall-clock > budget; repeated identical tool calls',
    codePath: 'libs/py/documind_core/breakers.py (AgentLoopCircuitBreaker)',
    docsUrl: 'https://www.anthropic.com/research/swe-bench-sonnet',
    docsLabel: 'Anthropic — agent loop termination',
  },
  {
    name: 'Observability CB',
    guards: 'OTel span exporter + Prometheus pushgateway (inverted-polarity)',
    signals: 'Export timeout; collector 503. On open → skip export silently so dead telemetry never blocks user requests',
    codePath: 'libs/py/documind_core/breakers.py (ObservabilityCircuitBreaker)',
    docsUrl: 'https://opentelemetry.io/docs/specs/otel/common/',
    docsLabel: 'OTel best-effort exporters',
  },
  {
    name: 'Citation-Deadline Signal',
    guards: 'Streaming output must emit a citation before token N',
    signals: 'Watchdog on token stream; miss → BLOCK',
    codePath: 'libs/py/documind_core/breakers.py (CitationDeadlineSignal)',
    docsUrl: 'https://arxiv.org/abs/2305.11675',
    docsLabel: 'Papers With Code — citation faithfulness',
  },
  {
    name: 'Forbidden-Pattern Signal',
    guards: 'Output regex guardrails (jailbreak leakage, PII exfil shape)',
    signals: 'Match on token stream → immediate BLOCK + audit',
    codePath: 'libs/py/documind_core/breakers.py (ForbiddenPatternSignal)',
    docsUrl: 'https://owasp.org/www-project-top-10-for-large-language-model-applications/',
    docsLabel: 'OWASP Top 10 for LLMs',
  },
  {
    name: 'Cognitive Circuit Breaker (CCB)',
    guards: 'LLM stream-level cognitive failure: repetition / drift / rule-breach',
    signals: 'RepetitionSignal (n-gram overlap), DriftSignal (embedding distance from initial context), RuleBreach (regex)',
    codePath: 'libs/py/documind_core/ccb.py + breakers.py (CognitiveCircuitBreaker, CognitiveInterrupt)',
    docsUrl: 'https://arxiv.org/abs/2604.13417',
    docsLabel: 'arXiv:2604.13417 — Cognitive Circuit Breakers',
    paperUrl: 'https://arxiv.org/abs/2604.13417',
    paperLabel: 'Original paper',
  },
];

export default function CircuitBreakersList() {
  return (
    <div className="cb-list-page">
      <header className="design-areas-header">
        <h1 className="section-title">Circuit Breakers</h1>
        <p className="design-areas-sub">
          Every breaker protecting DocuMind, from generic failure-count to stream-level
          cognitive failure. Each entry links to the source code and the canonical
          external reference so you can verify the pattern, not just take our word for it.
        </p>
        <p className="design-areas-sub">
          Need the interview-grade explanation layer? Use the breakers deep dive for state
          machines, transport breakers, failure modes, monitoring, and scaling tradeoffs.
        </p>
        <div className="page-actions">
          <Link href="/admin/breakers/deep" className="btn btn-primary">
            Open Breakers Deep Dive
          </Link>
        </div>
        <Link href="/tools/circuit-breakers" className="sysdesign-back">
          ← Circuit Breakers tool deep-dive (6-tab)
        </Link>
      </header>

      <div className="cb-grid">
        {BREAKERS.map((b) => {
          // Map each breaker to its anchor on /admin/breakers/deep.
          // Retrieval CB is the canonical transport-CB example; the
          // rest of the stateful family points at generic-cb (state
          // machine fundamentals). Stream/budget breakers don't have
          // a dedicated anchor yet — they fall through.
          const n = b.name.toLowerCase();
          const deepSlug = (() => {
            if (n.includes('retrieval')) return 'transport-cb';
            if (
              breakerKind(b.name) === 'stateful' ||
              n.includes('generic') ||
              n.includes('observability')
            )
              return 'generic-cb';
            return null;
          })();
          return (
          <article key={b.name} className="cb-card">
            <div className="method-card-head" style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <h3 className="cb-card-name" style={{ margin: 0 }}>{b.name}</h3>
              {deepSlug && (
                <Link
                  href={`/admin/breakers/deep#${deepSlug}`}
                  style={{ fontSize: 13, color: '#1e3a8a', textDecoration: 'underline' }}
                >
                  Deep dive →
                </Link>
              )}
            </div>
            <dl className="cb-card-dl">
              {deepSlug && (
                <>
                  <dt>Interview deep dive</dt>
                  <dd>
                    <Link href={`/admin/breakers/deep#${deepSlug}`} style={{ color: '#1e3a8a' }}>
                      Open the 20-dimension interview view for{' '}
                      <code>{deepSlug}</code> →
                    </Link>
                  </dd>
                </>
              )}
              <dt>Guards</dt>
              <dd>{b.guards}</dd>
              <dt>Signals</dt>
              <dd>{b.signals}</dd>
              <dt>Code</dt>
              <dd><code>{b.codePath}</code></dd>
              <dt>Flowchart</dt>
              <dd><Mermaid chart={breakerFlowchart(b)} /></dd>
              <dt>Sequence diagram</dt>
              <dd><Mermaid chart={breakerSequence(b)} /></dd>
              <dt>Input</dt>
              <dd>{breakerInput(b)}</dd>
              <dt>Process</dt>
              <dd>
                <ul className="cg-checklist">
                  {breakerProcess(b).map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
              </dd>
              <dt>Output</dt>
              <dd>{breakerOutput(b)}</dd>
              <dt>Challenges</dt>
              <dd>
                <ul className="cg-checklist">
                  {breakerChallenges(b).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </dd>
              <dt>Edge cases</dt>
              <dd>
                <ul className="cg-checklist">
                  {breakerEdgeCases(b).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </dd>
              <dt>Limitations</dt>
              <dd>
                <ul className="cg-checklist">
                  {breakerLimitations(b).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </dd>
              {(() => {
                // Extract first path from codePath (some entries use "path + note" format).
                const m = b.codePath.match(/^([\w./\-]+\.py)/);
                if (!m) return null;
                return (
                  <>
                    <dt>Real code</dt>
                    <dd><CodeBlock path={m[1]} code={readRepoFile(m[1], 80)} /></dd>
                  </>
                );
              })()}
              <dt>Reference</dt>
              <dd>
                <a href={b.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                  {b.docsLabel} ↗
                </a>
                {b.paperUrl && (
                  <>
                    <br />
                    <a href={b.paperUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                      {b.paperLabel} ↗
                    </a>
                  </>
                )}
              </dd>
            </dl>
          </article>
          );
        })}
      </div>
    </div>
  );
}
