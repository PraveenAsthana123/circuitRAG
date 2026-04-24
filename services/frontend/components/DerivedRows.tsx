import Mermaid from './Mermaid';

/**
 * Shared renderer for all derived one-topic-per-row sections on the catalog
 * pages. Accepts a minimal narrative triple and expands it into Flowchart,
 * Sequence, Data Flow, Network Flow, IPO, Pros/Cons, Challenges, 5W, Edge
 * cases, Limitations, Recommendations, Best practices, Comparison,
 * Interview talking point.
 */

export type Narrative = {
  name: string;
  problem: string;
  solution: string;
  example: string;
  category?: string;
};

/** Sanitize a short label for safe use in mermaid node text. */
function safe(s: string, maxLen = 60): string {
  return s
    .replace(/\.$/, '')
    .replace(/[\n\r]/g, ' ')
    .replace(/["`]/g, "'")
    .replace(/[<>{}]/g, '')
    .slice(0, maxLen);
}

function buildFlowchart(n: Narrative): string {
  const name = safe(n.name, 40);
  const problem = safe(n.problem, 80);
  const solution = safe(n.solution, 80);
  const example = safe(n.example, 80);
  return `flowchart LR
  t[Trigger: ${problem}] --> g{${name} applies?}
  g -->|yes| a[Apply pattern: ${solution}]
  g -->|no| b[Bypass / fallback path]
  a --> o[Effect: ${example}]
  b --> o`;
}

function buildSequence(n: Narrative): string {
  const name = safe(n.name, 30);
  const solution = safe(n.solution, 80);
  const example = safe(n.example, 80);
  return `sequenceDiagram
  autonumber
  participant C as Caller
  participant P as ${name}
  participant D as Dependency
  C->>P: request (context + tenant)
  P->>P: guard — is pattern applicable?
  alt applicable
    P->>D: ${solution}
    D-->>P: result
    P-->>C: response (shaped per contract)
  else not applicable
    P-->>C: fallback / error envelope
  end
  Note over P: Effect: ${example}`;
}

function buildDataFlow(n: Narrative): string {
  const problem = safe(n.problem, 60);
  const solution = safe(n.solution, 60);
  const example = safe(n.example, 60);
  return `flowchart LR
  src([Input data: ${problem}]) --> proc[Process: ${solution}]
  proc --> store[(Persist / emit event)]
  proc --> out([Output: ${example}])
  store -.audit.-> audit[(audit log)]
  proc -.metrics + traces.-> obs[(OTel stack)]`;
}

function buildNetworkFlow(n: Narrative): string {
  const name = safe(n.name, 30);
  return `flowchart TB
  subgraph edge [Edge]
    lb[LB / NGINX]
  end
  subgraph gw [Gateway tier]
    g[api-gateway]
  end
  subgraph mesh [Istio mesh]
    s1[service owning ${name}]
    s2[peer services]
  end
  subgraph data [Data tier]
    pg[(Postgres)]
    cache[(Redis)]
    log[(ELK)]
  end
  client([client]) --> lb --> g
  g -->|mTLS| s1
  s1 <-->|mTLS| s2
  s1 --> pg
  s1 --> cache
  s1 -.logs.-> log`;
}

export default function DerivedRows({ narr }: { narr: Narrative }) {
  return (
    <>
      <dt>Flowchart</dt>
      <dd><Mermaid chart={buildFlowchart(narr)} /></dd>
      <dt>Sequence diagram</dt>
      <dd><Mermaid chart={buildSequence(narr)} /></dd>
      <dt>Data flow</dt>
      <dd><Mermaid chart={buildDataFlow(narr)} /></dd>
      <dt>Network flow</dt>
      <dd><Mermaid chart={buildNetworkFlow(narr)} /></dd>

      <dt>Input</dt>
      <dd>Trigger: {narr.problem}</dd>
      <dt>Process</dt>
      <dd>{narr.solution}</dd>
      <dt>Output</dt>
      <dd>Effect: {narr.example}</dd>

      <dt>Pros</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Addresses the failure mode directly ({narr.problem.replace(/\.$/, '')}).</li>
          <li>Pattern is well-understood and testable in isolation.</li>
          <li>Pairs cleanly with surrounding observability + CB layers.</li>
        </ul>
      </dd>
      <dt>Cons</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Adds one more concept to onboard new engineers to.</li>
          <li>Requires runbook + alert coverage to keep value over time.</li>
          <li>Over-applied where the failure mode is unlikely = wasted complexity.</li>
        </ul>
      </dd>
      <dt>Challenges</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Tuning thresholds / sizes without production traffic data.</li>
          <li>Keeping the pattern consistent across services as the team grows.</li>
          <li>Measuring impact separately from the rest of the stack.</li>
        </ul>
      </dd>

      <dt>Comparison</dt>
      <dd>
        <table className="design-areas-table">
          <thead><tr><th>Scenario</th><th>Behaviour</th></tr></thead>
          <tbody>
            <tr><td className="da-col-name">With this applied</td><td>{narr.solution}</td></tr>
            <tr><td className="da-col-name">Without it</td><td>{narr.problem}</td></tr>
            <tr><td className="da-col-name">DocuMind today</td><td>{narr.example}</td></tr>
          </tbody>
        </table>
      </dd>

      <dt>5W</dt>
      <dd>
        <table className="design-areas-table">
          <tbody>
            <tr><td className="da-col-name">Who</td><td>Owned by the team responsible for this surface; on-call runs the associated runbook.</td></tr>
            <tr><td className="da-col-name">What</td><td>{narr.solution}</td></tr>
            <tr><td className="da-col-name">When</td><td>Active whenever the failure mode it prevents is possible.</td></tr>
            <tr><td className="da-col-name">Where</td><td>Applies at the boundary described in the example; metrics/logs/traces emit from here.</td></tr>
            <tr><td className="da-col-name">Why</td><td>{narr.problem}</td></tr>
          </tbody>
        </table>
      </dd>

      <dt>Edge cases &amp; solutions</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Cold start / empty state: pre-seed or apply only on N-th occurrence to avoid day-one flapping.</li>
          <li>Very large tenant: tune thresholds per tenant tier rather than global.</li>
          <li>Clock skew across pods: rely on monotonic time; never wall-clock differences for timeouts.</li>
          <li>Dependency transient failure: the pattern should distinguish transient vs persistent — log every transition.</li>
        </ul>
      </dd>

      <dt>Limitations</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Does not substitute for capacity planning — it mitigates, not prevents.</li>
          <li>Per-process state is local; multi-instance views need external aggregation.</li>
          <li>Requires accompanying observability to be trusted.</li>
        </ul>
      </dd>

      <dt>Recommendations</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Start with conservative defaults; tighten on real traffic data.</li>
          <li>Wire metrics + alerts before enabling in production.</li>
          <li>Document the decision in an ADR so future maintainers understand the "why".</li>
          <li>Review quarterly with a chaos drill that forces the failure mode.</li>
        </ul>
      </dd>

      <dt>Best practices</dt>
      <dd>
        <ul className="cg-checklist">
          <li>Codify defaults in a shared library so every service opts in by construction, not by copy-paste.</li>
          <li>Name the primitive clearly in code (e.g. a class / function) so reviewers can spot its absence.</li>
          <li>Cover it in CI via a test that fails when the pattern is bypassed.</li>
          <li>Add a dashboard + alert before rollout.</li>
        </ul>
      </dd>

      <dt>Interview talking point</dt>
      <dd>
        <p className="da-talk">
          "{narr.name} is {narr.category ? `a ${narr.category.toLowerCase()} ` : 'a '}
          pattern that addresses {narr.problem.replace(/\.$/, '').toLowerCase()}.
          The way we approach it is {narr.solution.replace(/\.$/, '').toLowerCase()}.
          In DocuMind, {narr.example.replace(/\.$/, '').toLowerCase()}.
          The trade-off I'd highlight in an interview is that this is a deliberate
          investment — it pays back the first time the underlying failure mode
          actually occurs in production."
        </p>
      </dd>
    </>
  );
}
