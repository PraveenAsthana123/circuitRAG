import Link from 'next/link';

export const metadata = { title: 'Design Methodologies — DocuMind' };

type Methodology = {
  acronym: string;
  name: string;
  tagline: string;
  scenario: string;
  whenToUse: string;
  docsUrl: string;
  docsLabel: string;
};

const METHODOLOGIES: Methodology[] = [
  {
    acronym: 'TDD',
    name: 'Test-Driven Development',
    tagline: 'Write the failing test first. Then make it pass. Refactor.',
    scenario:
      "Every chunker/embedder/retriever in DocuMind has red-green-refactor history. The RLS fix was written as a failing test first — without FORCE + role separation the test actually read tenant B's data. That's what made the bug undeniable.",
    whenToUse: 'Stable behaviour specs, high-stakes correctness, security-critical primitives.',
    docsUrl: 'https://martinfowler.com/bliki/TestDrivenDevelopment.html',
    docsLabel: 'Martin Fowler — TDD',
  },
  {
    acronym: 'BDD',
    name: 'Behaviour-Driven Development',
    tagline: 'Given-When-Then. Scenarios talk to non-engineers.',
    scenario:
      '"Given a tenant over their token budget, when they submit a query, then the Token CB returns 429 with a Retry-After header." BDD scenarios sit beside Finops + HITL acceptance tests.',
    whenToUse: 'Product-owner acceptance, compliance sign-off, cross-team contracts.',
    docsUrl: 'https://cucumber.io/docs/bdd/',
    docsLabel: 'Cucumber — BDD guide',
  },
  {
    acronym: 'MDD',
    name: 'Model-Driven Development',
    tagline: 'Protos/schemas are the source of truth; code is generated from them.',
    scenario:
      "DocuMind's `proto/` tree drives gRPC stubs for every internal service. Event schemas under `schemas/events/*.json` generate both producer and consumer validation. Change the proto, everything downstream follows.",
    whenToUse: 'Multi-language service meshes, strict contract evolution, multi-team APIs.',
    docsUrl: 'https://protobuf.dev/overview/',
    docsLabel: 'Protobuf overview',
  },
  {
    acronym: 'DDD',
    name: 'Domain-Driven Design',
    tagline: 'Bounded contexts + ubiquitous language.',
    scenario:
      'One schema per service — `identity`, `ingestion`, `governance`, `finops`, `eval`, `observability`. No cross-schema joins. Aggregate roots: `Document`, `Saga`, `AuditLogEntry`, `EvalRun`. The language in the code matches the language in the runbooks.',
    whenToUse: 'Systems with complex domain rules; team autonomy matters; long lifespan.',
    docsUrl: 'https://martinfowler.com/bliki/DomainDrivenDesign.html',
    docsLabel: 'Martin Fowler — DDD',
  },
  {
    acronym: 'BusDD',
    name: 'Business-Driven Design',
    tagline: 'Every component maps to a business KPI.',
    scenario:
      'Each SLO row in `observability.slo_targets` exists because a business KPI said so — query latency p95, answer faithfulness, availability. If a feature does not move a KPI, it does not ship. FinOps budgets also trace back to revenue models.',
    whenToUse: 'Commercial software with explicit revenue ties; cost-sensitive infra.',
    docsUrl: 'https://www.thoughtworks.com/radar/techniques/domain-driven-product-thinking',
    docsLabel: 'ThoughtWorks — domain-driven product thinking',
  },
  {
    acronym: 'OutDD',
    name: 'Output-Driven Design',
    tagline: 'Start from the output contract. Reverse-derive the pipeline.',
    scenario:
      'The `AnswerWithCitations` response schema is frozen first. Every upstream component is derived from what that contract requires: retrieval must return chunk IDs, CCB must emit confidence, governance must attach an explanation record.',
    whenToUse: 'LLM outputs; analytical reports; anywhere the consumer contract is load-bearing.',
    docsUrl: 'https://www.oreilly.com/library/view/designing-data-intensive-applications/9781491903063/',
    docsLabel: 'Kleppmann — contract-first (DDIA)',
  },
  {
    acronym: 'MCP-DD',
    name: 'Model-Context-Protocol-Driven Design',
    tagline: 'Tools and resources are first-class MCP contracts.',
    scenario:
      'Agents in DocuMind reach external state through MCP tool contracts. Each tool has declared permissions, arg validation, and an idempotency key. This is how we keep agent autonomy bounded without writing an ad-hoc permission matrix per integration.',
    whenToUse: 'Agent-integrated systems; multi-tool orchestration; enterprise agent governance.',
    docsUrl: 'https://modelcontextprotocol.io',
    docsLabel: 'Model Context Protocol spec',
  },
  {
    acronym: 'Agent-DD',
    name: 'Agent-Driven Design',
    tagline: 'Design the loop, the stop condition, and the human escape hatch.',
    scenario:
      'Every agent flow in DocuMind has a bounded loop (Agent-Loop CB), a cognitive breaker on the token stream (CCB), explicit HITL escalation rules in governance, and a kill-switch feature flag. No agent ships without all four.',
    whenToUse: 'Any production agent. Never ship an unbounded loop.',
    docsUrl: 'https://www.anthropic.com/engineering/building-effective-agents',
    docsLabel: 'Anthropic — Building effective agents',
  },
];

export default function MethodologiesPage() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Design Methodologies — Scenarios</h1>
        <p className="design-areas-sub">
          Eight methodologies, each with a concrete DocuMind scenario showing how it actually applies.
          No abstract lectures — the scenarios are the point.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
      </header>

      <div className="method-grid">
        {METHODOLOGIES.map((m) => (
          <article key={m.acronym} className="method-card">
            <div className="method-card-head">
              <span className="method-acronym">{m.acronym}</span>
              <h3 className="method-name">{m.name}</h3>
            </div>
            <p className="method-tagline">{m.tagline}</p>
            <dl className="cb-card-dl">
              <dt>DocuMind scenario</dt>
              <dd>{m.scenario}</dd>
              <dt>When to pick it</dt>
              <dd>{m.whenToUse}</dd>
              <dt>Reference</dt>
              <dd>
                <a href={m.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                  {m.docsLabel} ↗
                </a>
              </dd>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
