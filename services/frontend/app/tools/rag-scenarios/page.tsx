import Link from 'next/link';
import DerivedRows from '../../../components/DerivedRows';
import { LAYER_ORDER, RAG_SCENARIOS } from '../../../lib/rag-scenarios';

export const metadata = { title: '36 RAG Scenarios — DocuMind' };

/**
 * 36 RAG-specific production scenarios, grouped into 10 architectural
 * layers. Each scenario card carries 10+ one-topic-per-row sections
 * via DerivedRows (flowchart / sequence / data-flow / network / IPO /
 * pros / cons / challenges / comparison / 5W / edge cases /
 * limitations / recommendations / best practices / interview).
 */
export default function RagScenariosPage() {
  const layerCounts = LAYER_ORDER.map((layer) => ({
    layer,
    count: RAG_SCENARIOS.filter((s) => s.layer === layer).length,
  }));

  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">36 RAG Scenarios</h1>
        <p className="design-areas-sub">
          Production scenarios specific to a multi-tenant RAG + MCP + Istio system — grouped into
          10 architectural layers. Each card expands into full detail: diagrams, I/O, pros/cons,
          comparison, interview talking point, reference link.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>

        <nav className="scen-toc">
          {layerCounts.map(({ layer, count }) => (
            <a key={layer} href={`#${slug(layer)}`} className="scen-toc-link">
              {layer} <span className="scen-toc-count">({count})</span>
            </a>
          ))}
        </nav>
      </header>

      {LAYER_ORDER.map((layer) => {
        const rows = RAG_SCENARIOS.filter((s) => s.layer === layer);
        if (rows.length === 0) return null;
        return (
          <section key={layer} id={slug(layer)} className="design-areas-group">
            <h2 className="design-areas-group-title">{layer}</h2>
            <div className="method-grid">
              {rows.map((s) => (
                <article key={s.id} className="method-card">
                  <div className="method-card-head">
                    <span className="method-acronym">#{s.id}</span>
                    <h3 className="method-name">{s.name}</h3>
                  </div>
                  <dl className="cb-card-dl">
                    <dt>Problem</dt>
                    <dd>{s.problem}</dd>
                    <dt>Pattern</dt>
                    <dd>{s.solution}</dd>
                    <dt>DocuMind example</dt>
                    <dd>{s.example}</dd>
                    <DerivedRows narr={{ name: s.name, problem: s.problem, solution: s.solution, example: s.example, category: layer }} />
                    {s.docsUrl && (
                      <>
                        <dt>Reference</dt>
                        <dd>
                          <a href={s.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                            canonical ↗
                          </a>
                        </dd>
                      </>
                    )}
                  </dl>
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
