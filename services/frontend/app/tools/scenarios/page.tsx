import Link from 'next/link';
import { SCENARIO_CATEGORIES, type ScenarioRow } from '../../../lib/all-scenarios';

export const metadata = { title: 'All Scenarios Catalog — DocuMind' };

/**
 * Mega-catalog. Every scenario card renders:
 *   Problem / Pattern / Example         (hand-authored)
 *   Input / Process / Output            (derived from fields)
 *   Pros / Cons / Challenges            (derived from fields)
 *   Comparison (with / without)         (derived from fields)
 *   Reference link                      (category canonical doc)
 */
export default function AllScenarios() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">All Scenarios Catalog</h1>
        <p className="design-areas-sub">
          Every scenario in DocuMind — now with Input/Process/Output, Pros/Cons, Challenges,
          and a with/without comparison per card. One topic per row.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
        <nav className="scen-toc">
          {SCENARIO_CATEGORIES.map((c) => (
            <a key={c.id} href={`#${c.id}`} className="scen-toc-link">
              {c.title} <span className="scen-toc-count">({c.rows.length})</span>
            </a>
          ))}
        </nav>
      </header>

      {SCENARIO_CATEGORIES.map((c) => (
        <section key={c.id} id={c.id} className="design-areas-group">
          <h2 className="design-areas-group-title">{c.title}</h2>
          <p className="design-areas-sub">{c.blurb}</p>
          {c.docsUrl && (
            <p className="scen-category-ref">
              Canonical reference:{' '}
              <a href={c.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                {c.docsLabel ?? c.docsUrl} ↗
              </a>
            </p>
          )}
          <div className="method-grid">
            {c.rows.map((row) => (
              <article key={row.name} className="method-card">
                <div className="method-card-head">
                  <h3 className="method-name">{row.name}</h3>
                </div>
                <dl className="cb-card-dl">
                  <dt>Problem</dt>
                  <dd>{row.problem}</dd>
                  <dt>Pattern</dt>
                  <dd>{row.solution}</dd>
                  <dt>Example</dt>
                  <dd>{row.example}</dd>

                  <dt>Input</dt>
                  <dd>{row.ipo?.input ?? deriveInput(row)}</dd>
                  <dt>Process</dt>
                  <dd>{row.ipo?.process ?? deriveProcess(row)}</dd>
                  <dt>Output</dt>
                  <dd>{row.ipo?.output ?? deriveOutput(row)}</dd>

                  <dt>Pros</dt>
                  <dd>
                    <ul className="cg-checklist">
                      {(row.pros ?? derivePros(row)).map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </dd>
                  <dt>Cons</dt>
                  <dd>
                    <ul className="cg-checklist">
                      {(row.cons ?? deriveCons(row)).map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </dd>
                  <dt>Challenges</dt>
                  <dd>
                    <ul className="cg-checklist">
                      {(row.challenges ?? deriveChallenges(row)).map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </dd>

                  <dt>Comparison</dt>
                  <dd>
                    <table className="design-areas-table">
                      <thead><tr><th>Scenario</th><th>Behaviour</th></tr></thead>
                      <tbody>
                        {(row.comparison ?? deriveComparison(row)).map((cmp, i) => (
                          <tr key={i}>
                            <td className="da-col-name">{cmp.scenario}</td>
                            <td>{cmp.behavior}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </dd>

                  <dt>Interview talking point</dt>
                  <dd>
                    <p className="da-talk">"{deriveInterview(row, c.title)}"</p>
                  </dd>

                  {c.docsUrl && (
                    <>
                      <dt>Reference</dt>
                      <dd>
                        <a href={c.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                          {c.docsLabel ?? 'docs'} ↗
                        </a>
                      </dd>
                    </>
                  )}
                </dl>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function deriveInterview(r: ScenarioRow, category: string): string {
  return `${r.name} is a ${category.toLowerCase()} pattern that addresses ${r.problem.replace(/\.$/, '').toLowerCase()}. The way we approach it is ${r.solution.replace(/\.$/, '').toLowerCase()}. In DocuMind, ${r.example.replace(/\.$/, '').toLowerCase()}. The trade-off I'd highlight in an interview is that this is a deliberate investment — it pays back the first time the underlying failure mode actually occurs in production.`;
}

/* Derivations ------------------------------------------------------------- */

function deriveInput(r: ScenarioRow): string {
  return `Trigger: ${r.problem}`;
}

function deriveProcess(r: ScenarioRow): string {
  return r.solution;
}

function deriveOutput(r: ScenarioRow): string {
  return `Effect: ${r.example}`;
}

function derivePros(r: ScenarioRow): string[] {
  return [
    `Addresses the failure mode directly (${r.problem.replace(/\.$/, '')}).`,
    'Pattern is well-understood and testable in isolation.',
    'Pairs cleanly with surrounding observability + CB layers.',
  ];
}

function deriveCons(r: ScenarioRow): string[] {
  return [
    'Adds one more concept to onboard new engineers to.',
    'Requires runbook + alert coverage to keep value over time.',
    'Over-applied where the underlying failure mode is unlikely = wasted complexity.',
  ];
}

function deriveChallenges(r: ScenarioRow): string[] {
  return [
    'Tuning thresholds / sizes without production traffic data.',
    'Keeping the pattern consistent across services as the team grows.',
    'Measuring impact separately from the rest of the stack.',
  ];
}

function deriveComparison(r: ScenarioRow): { scenario: string; behavior: string }[] {
  return [
    { scenario: 'With this scenario applied', behavior: r.solution },
    { scenario: 'Without it', behavior: r.problem },
    { scenario: 'DocuMind today', behavior: r.example },
  ];
}
