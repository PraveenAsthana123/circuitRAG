import Link from 'next/link';
import CodeBlock from '../../../components/CodeBlock';
import DerivedRows from '../../../components/DerivedRows';
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
        <Link href="/tools/circuit-breakers" className="sysdesign-back">
          ← Circuit Breakers tool deep-dive (6-tab)
        </Link>
      </header>

      <div className="cb-grid">
        {BREAKERS.map((b) => (
          <article key={b.name} className="cb-card">
            <h3 className="cb-card-name">{b.name}</h3>
            <dl className="cb-card-dl">
              <dt>Guards</dt>
              <dd>{b.guards}</dd>
              <dt>Signals</dt>
              <dd>{b.signals}</dd>
              <dt>Code</dt>
              <dd><code>{b.codePath}</code></dd>
              <DerivedRows narr={{ name: b.name, problem: `Cascading failure when ${b.guards.toLowerCase()} misbehaves.`, solution: b.signals, example: `Implemented in ${b.codePath}.`, category: 'circuit breaker' }} />
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
        ))}
      </div>
    </div>
  );
}
