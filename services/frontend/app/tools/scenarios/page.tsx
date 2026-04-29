import Link from 'next/link';
import C4PageLinks from '../../../components/C4PageLinks';
import DerivedRows from '../../../components/DerivedRows';
import { SCENARIO_CATEGORIES, type ScenarioRow } from '../../../lib/all-scenarios';

export const metadata = { title: 'All Scenarios Catalog — DocuMind' };

/**
 * Mega-catalog. Every scenario card renders:
 *   Problem / Pattern / Example         (hand-authored)
 *   Flowchart / Sequence / Data / Net   (derived via shared component)
 *   Input / Process / Output            (derived from fields)
 *   Pros / Cons / Challenges            (derived from fields)
 *   Comparison (with / without)         (derived from fields)
 *   5W / Edge cases / Limitations       (derived from fields)
 *   Reference link                      (category canonical doc)
 */
export default function AllScenarios() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">All Scenarios Catalog</h1>
        <p className="design-areas-sub">
          Every scenario in DocuMind — now with flowchart, sequence diagram, data flow,
          network flow, Input/Process/Output, Pros/Cons, Challenges, 5W, and a
          with/without comparison per card. One topic per row.
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

      <C4PageLinks
        title="Scenario catalog — C4 view"
        summary="Scenario pages explain failure modes and patterns. C4 gives those patterns a structural frame: which scenarios live at context level, which belong to service containers, and which are component or code-level concerns."
        focus="Level 3 components is the most useful default, with Level 5 to reason about governance-heavy scenarios."
        levels={['containers', 'components', 'code', 'governance', 'observability']}
      />

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

                  <DerivedRows
                    narr={{
                      name: row.name,
                      problem: row.problem,
                      solution: row.solution,
                      example: row.example,
                      category: c.title,
                    }}
                  />

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
