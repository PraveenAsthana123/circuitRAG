import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  DESIGN_AREAS,
  STATUS_META,
  type DesignArea,
} from '../../../../lib/design-areas';

export async function generateStaticParams() {
  return DESIGN_AREAS.map((d) => ({ id: d.id }));
}

type Props = { params: { id: string } };

export function generateMetadata({ params }: Props) {
  const da = DESIGN_AREAS.find((d) => d.id === params.id);
  if (!da) return { title: 'Design area not found — DocuMind' };
  return { title: `${da.name} — Design Area ${da.id}` };
}

/**
 * Per-area interview-ready detail template.
 *
 * Composes the area's hand-written why/how/risk with the universally-applicable
 * sections every design area should answer: 5W, pros/cons, challenges, edge
 * cases, input/process/output, monitoring + scoring + tracing + logging, and
 * an interview talking-point. Generic scaffolding is derived from the area's
 * status + group; area-specific content lives in lib/design-areas.ts.
 */
export default function DesignAreaDetail({ params }: Props) {
  const da = DESIGN_AREAS.find((d) => d.id === params.id);
  if (!da) notFound();

  const meta = STATUS_META[da.status];
  const neighbors = DESIGN_AREAS.filter((d) => d.group === da.group && d.id !== da.id);

  return (
    <div className="da-detail-page">
      <nav className="tool-breadcrumb">
        <Link href="/tools/design-areas">← all design areas</Link>
        <span className="tool-breadcrumb-sep">/</span>
        <span className="tool-breadcrumb-cat">{da.group}</span>
      </nav>

      <header className="da-detail-header">
        <div className="da-detail-title">
          <span className="da-detail-id">{da.id}</span>
          <h1 className="tool-name">{da.name}</h1>
        </div>
        <span className={`status-pill ${meta.cssClass}`}>
          {meta.emoji} {meta.label}
        </span>
      </header>

      <Section title="Summary — why / how / risk">
        <FieldRow label="Why it matters" value={da.why} />
        <FieldRow label="How DocuMind does it" value={da.how} />
        <FieldRow label="Risk if missing" value={da.risk} highlight />
        <FieldRow label="Primary code" value={<code>{da.classRef}</code>} />
      </Section>

      <Section title="Interview talking point">
        <p className="da-talk">
          "{buildInterviewTalk(da)}"
        </p>
      </Section>

      <Section title="5W — Who / What / When / Where / Why">
        <WTable data={buildFiveW(da)} />
      </Section>

      <Section title="Feature type + Capabilities">
        <FieldRow label="Feature type" value={classifyType(da)} />
        <FieldRow label="Primary capability" value={`${da.group.toLowerCase()} — ${da.name.toLowerCase()}`} />
      </Section>

      <Section title="Pros + Cons">
        <TwoColList left={{ title: 'Pros', items: buildPros(da) }} right={{ title: 'Cons', items: buildCons(da) }} />
      </Section>

      <Section title="Challenges + Edge Cases">
        <TwoColList left={{ title: 'Challenges', items: buildChallenges(da) }} right={{ title: 'Edge cases', items: buildEdgeCases(da) }} />
      </Section>

      <Section title="Input → Process → Output">
        <IPOFlow ipo={buildIPO(da)} />
      </Section>

      <Section title="Monitoring · Scoring · Tracing · Logging">
        <MSTLTable data={buildMSTL(da)} />
      </Section>

      <Section title="Comparison — with / without / alternatives">
        <ComparisonTable area={da} />
      </Section>

      {neighbors.length > 0 && (
        <Section title={`Related in ${da.group}`}>
          <ul className="tool-related-list">
            {neighbors.map((n) => (
              <li key={n.id}>
                <Link href={`/tools/design-areas/${n.id}`}>
                  {n.id}. {n.name}
                </Link>
                <span className="tool-related-one-line"> — {n.why}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

/* ========================================================================
   Generic section primitives
   ======================================================================== */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="da-detail-section">
      <h2 className="da-detail-section-title">{title}</h2>
      {children}
    </section>
  );
}

function FieldRow({ label, value, highlight = false }: { label: string; value: React.ReactNode; highlight?: boolean }) {
  return (
    <div className={`da-field ${highlight ? 'da-field-highlight' : ''}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TwoColList({
  left,
  right,
}: {
  left: { title: string; items: string[] };
  right: { title: string; items: string[] };
}) {
  return (
    <div className="da-two-col">
      <div>
        <h4 className="da-two-col-title">{left.title}</h4>
        <ul className="cg-checklist">
          {left.items.map((i, idx) => <li key={idx}>{i}</li>)}
        </ul>
      </div>
      <div>
        <h4 className="da-two-col-title">{right.title}</h4>
        <ul className="cg-checklist">
          {right.items.map((i, idx) => <li key={idx}>{i}</li>)}
        </ul>
      </div>
    </div>
  );
}

function WTable({ data }: { data: { who: string; what: string; when: string; where: string; why: string } }) {
  return (
    <table className="design-areas-table">
      <tbody>
        <tr><td className="da-col-name">Who</td><td>{data.who}</td></tr>
        <tr><td className="da-col-name">What</td><td>{data.what}</td></tr>
        <tr><td className="da-col-name">When</td><td>{data.when}</td></tr>
        <tr><td className="da-col-name">Where</td><td>{data.where}</td></tr>
        <tr><td className="da-col-name">Why</td><td>{data.why}</td></tr>
      </tbody>
    </table>
  );
}

function IPOFlow({ ipo }: { ipo: { input: string[]; process: string[]; output: string[] } }) {
  return (
    <div className="da-ipo">
      {([
        ['Input', ipo.input, '→'],
        ['Process', ipo.process, '→'],
        ['Output', ipo.output, ''],
      ] as const).map(([label, items, arrow], idx) => (
        <div key={idx} className="da-ipo-col">
          <h4 className="da-ipo-label">{label}</h4>
          <ul className="cg-checklist">{items.map((i, k) => <li key={k}>{i}</li>)}</ul>
          {arrow && <span className="da-ipo-arrow" aria-hidden>{arrow}</span>}
        </div>
      ))}
    </div>
  );
}

function MSTLTable({ data }: { data: { monitoring: string; scoring: string; tracing: string; logging: string } }) {
  return (
    <table className="design-areas-table">
      <thead>
        <tr><th>Signal</th><th>What we do</th></tr>
      </thead>
      <tbody>
        <tr><td className="da-col-name">Monitoring</td><td>{data.monitoring}</td></tr>
        <tr><td className="da-col-name">Scoring</td><td>{data.scoring}</td></tr>
        <tr><td className="da-col-name">Tracing</td><td>{data.tracing}</td></tr>
        <tr><td className="da-col-name">Logging</td><td>{data.logging}</td></tr>
      </tbody>
    </table>
  );
}

function ComparisonTable({ area }: { area: DesignArea }) {
  return (
    <table className="design-areas-table">
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Behaviour</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td className="da-col-name">With this area (DocuMind)</td>
          <td>{area.how}</td>
        </tr>
        <tr>
          <td className="da-col-name">Without this area</td>
          <td>{area.risk}</td>
        </tr>
        <tr>
          <td className="da-col-name">Alternatives</td>
          <td>{buildAlternatives(area)}</td>
        </tr>
      </tbody>
    </table>
  );
}

/* ========================================================================
   Content builders — derive repeatable sections from the area's group/status
   without hand-authoring 74 × 9 fields. Every function returns plain strings;
   the area-specific nuance lives in why/how/risk, authored in design-areas.ts.
   ======================================================================== */

function buildInterviewTalk(da: DesignArea): string {
  return `${da.name} is a ${da.group.toLowerCase()} concern. ${da.why} In DocuMind, ${da.how} If we hadn’t done this, ${da.risk} Status today: ${STATUS_META[da.status].label.toLowerCase()}, implemented at ${da.classRef}.`;
}

function buildFiveW(da: DesignArea) {
  return {
    who: `Owned by the ${da.group.toLowerCase()} working group; on-call via the service that hosts the implementation.`,
    what: da.why,
    when: da.status === 'implemented'
      ? 'Active in production and covered by CI.'
      : da.status === 'partial'
        ? 'Scaffolded; parts active, remainder scheduled.'
        : 'Designed in the spec, not yet built.',
    where: `Lives in ${da.classRef}. Exposed indirectly via every service that depends on ${da.group.toLowerCase()}.`,
    why: da.risk,
  };
}

function classifyType(da: DesignArea): string {
  switch (da.group) {
    case 'System & Boundaries': return 'Structural — defines a system surface or boundary';
    case 'State & Async': return 'Behavioral — governs how state and time interact';
    case 'Services': return 'Organizational — a deployable unit with clear ownership';
    case 'Contracts & Retrieval': return 'Interface — a versioned contract between components';
    case 'Capacity & Release': return 'Operational — scale, availability, and release safety';
    case 'Policy & Eval': return 'Governance — observability, auditability, policy';
    case 'AI Governance (Extras)': return 'AI-specific — trust, safety, explainability, interpretability';
    default: return 'Design concern';
  }
}

function buildPros(da: DesignArea): string[] {
  const base = [
    da.why,
    'Reduces blast radius when upstream failures occur.',
    'Improves debuggability via clear ownership and explicit contracts.',
  ];
  if (da.status === 'implemented') base.push('Already verified by unit/integration tests in CI.');
  return base;
}

function buildCons(da: DesignArea): string[] {
  return [
    'Adds one more abstraction to reason about when onboarding.',
    'Requires ongoing investment — runbooks, dashboards, alerts.',
    'Over-engineered without the underlying failure mode actually occurring at your scale.',
  ];
}

function buildChallenges(da: DesignArea): string[] {
  const generic = [
    'Choosing thresholds without production data (start conservative; tighten with evidence).',
    'Keeping configuration in sync across environments (dev / staging / prod).',
    'Onboarding new engineers to the specific invariant this area enforces.',
  ];
  if (da.group === 'AI Governance (Extras)') {
    generic.unshift('Balancing safety (fail-closed) with user experience (fail-open).');
  }
  if (da.group === 'Capacity & Release') {
    generic.unshift('Forecasting capacity before traffic patterns are observable.');
  }
  return generic;
}

function buildEdgeCases(da: DesignArea): string[] {
  const generic = [
    'Very large tenants that exceed design assumptions (size, QPS, concurrent users).',
    'Very small tenants where fixed overhead dominates marginal cost.',
    'Partial failure — half the system is healthy, half is not.',
    'Network partition scenarios where consistency guarantees become visible.',
  ];
  if (da.group === 'State & Async') {
    generic.push('Clock skew and reorder between event producers and consumers.');
  }
  return generic;
}

function buildIPO(da: DesignArea): { input: string[]; process: string[]; output: string[] } {
  // Generic flow scaffolded by group, enriched with area's own how.
  switch (da.group) {
    case 'System & Boundaries':
      return {
        input: ['User request + auth context', 'Tenant identifier (JWT claim)'],
        process: [da.how, 'Validation and policy check at the boundary'],
        output: ['Authorized request propagated with correlation-id', 'Rejections emitted with error envelope'],
      };
    case 'State & Async':
      return {
        input: ['Domain event or API command', 'Current state + tenant scope'],
        process: [da.how, 'Transition validation + persistence'],
        output: ['New state + derived events', 'Audit + observability signals'],
      };
    case 'Services':
      return {
        input: ['API / gRPC / event inbound'],
        process: ['Service-owned business logic', da.how],
        output: ['Response body + side-effect events + metrics'],
      };
    case 'Contracts & Retrieval':
      return {
        input: ['Consumer request honouring the contract'],
        process: [da.how, 'Schema validation + version negotiation'],
        output: ['Contract-conformant response or typed error'],
      };
    case 'Capacity & Release':
      return {
        input: ['Traffic, configuration, deployment event'],
        process: [da.how, 'Admission control + scale decision'],
        output: ['Admitted workload or shed / queued request', 'Scale events to orchestrator'],
      };
    case 'Policy & Eval':
      return {
        input: ['Decision / prediction / action requiring governance'],
        process: [da.how, 'Policy evaluation + evidence capture'],
        output: ['Allow / review / deny + audit record'],
      };
    case 'AI Governance (Extras)':
      return {
        input: ['Model input + output + context window'],
        process: [da.how, 'Safety / explainability / interpretability checks'],
        output: ['Safe response + decision record + HITL escalation if needed'],
      };
    default:
      return { input: ['…'], process: [da.how], output: ['…'] };
  }
}

function buildMSTL(da: DesignArea): { monitoring: string; scoring: string; tracing: string; logging: string } {
  return {
    monitoring: 'Prometheus counters for invocations, successes, failures; gauges for state (open/closed); histograms for latency. Grafana dashboard per service.',
    scoring: `Status today: ${STATUS_META[da.status].label}. Maturity reflects the area's coverage in CI + integration tests. See docs/design-areas/table for the canonical table.`,
    tracing: 'Every request carries a correlation-id; OTel spans mark entry/exit of this area; spans include tenant_id (as attribute, not label) for filterability in Jaeger.',
    logging: 'Structured JSON logs via structlog. Event key includes area name, outcome, and elapsed_ms. Logs are searchable in Kibana; correlation-id links across services.',
  };
}

function buildAlternatives(da: DesignArea): string {
  switch (da.group) {
    case 'System & Boundaries':
      return 'API Gateway-only, no service mesh — simpler ops but weaker mTLS story. Or per-service edge proxies — more flexible, more ops.';
    case 'State & Async':
      return 'Synchronous RPC only — simpler but brittle under load. Or pure event-sourcing — more auditable, steeper learning curve.';
    case 'Services':
      return 'Modular monolith — less ops, tighter coupling. Or function-as-a-service — cheaper idle, cold-start trade-off.';
    case 'Contracts & Retrieval':
      return 'GraphQL federation — richer queries, more upfront schema work. Or REST-only — simpler, fewer capabilities.';
    case 'Capacity & Release':
      return 'Manual scaling + blue/green — less risky cutover, more operator effort. Or serverless auto-scale — no capacity thinking, cold-start risk.';
    case 'Policy & Eval':
      return 'External policy engine (OPA) — reusable across products, another dep. Or hard-coded rules — simple, impossible to audit/change.';
    case 'AI Governance (Extras)':
      return 'Bolt-on safety layer — fast to add, easy to bypass. Or upstream model-level alignment — slow, high ceiling.';
    default:
      return 'See the area discussion in docs/design-areas/table.';
  }
}
