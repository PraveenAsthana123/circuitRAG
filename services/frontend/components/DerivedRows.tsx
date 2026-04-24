/**
 * Shared renderer for the 6 derived one-topic-per-row sections.
 * Used on scenarios, database-scenarios, microservice-scenarios,
 * circuit-breakers-list, and the design-areas index.
 *
 * Accepts a minimal "narrative triple" — what-problem / pattern / example —
 * and derives IPO, pros, cons, challenges, comparison, interview.
 */

export type Narrative = {
  name: string;
  problem: string;
  solution: string;
  example: string;
  category?: string;
};

export default function DerivedRows({ narr }: { narr: Narrative }) {
  return (
    <>
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
