import Link from 'next/link';
import { SCENARIO_CATEGORIES } from '../../../lib/all-scenarios';

export const metadata = { title: 'All Scenarios Catalog — DocuMind' };

/**
 * Mega-catalog: one card per scenario, grouped by category. Every category
 * carries a canonical reference link that appears on every card in that
 * category. Readers can scan ~100 scenarios in one scroll.
 */
export default function AllScenarios() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">All Scenarios Catalog</h1>
        <p className="design-areas-sub">
          Every scenario category in DocuMind — observability, API design, chunking, embedding, pre/post
          retrieval, output evaluation, PII, auth/SSO/LDAP, Istio, circuit-breaker types, API gateway,
          load balancer, CDN. Every card links to the canonical reference for the category.
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
