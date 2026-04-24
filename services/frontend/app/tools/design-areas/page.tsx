import Link from 'next/link';
import CodeBlock from '../../../components/CodeBlock';
import DerivedRows from '../../../components/DerivedRows';
import { parseClassRef } from '../../../lib/classref-parser';
import {
  DESIGN_AREAS,
  GROUP_ORDER,
  STATUS_META,
  type DAStatus,
} from '../../../lib/design-areas';
import { readRepoFile } from '../../../lib/read-code';

export const metadata = { title: '74 Design Features — DocuMind' };

/**
 * One row per area. Each row carries every field the admin/architect needs:
 *   id | name | status | why | how | risk | code pointer | detail link
 *
 * The detail link opens /tools/design-areas/[id] where the template adds
 * 5W, pros/cons, edge cases, I/O, monitoring — the interview-ready deep dive.
 */
export default function DesignAreasPage() {
  const counts: Record<DAStatus, number> = { implemented: 0, partial: 0, designed: 0 };
  for (const da of DESIGN_AREAS) counts[da.status]++;

  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">74 System-Design Features</h1>
        <p className="design-areas-sub">
          Every load-bearing design decision — 67 core areas + the Cognitive Circuit Breaker + 6 AI-governance
          extras. Each row explains <strong>why it matters</strong>, <strong>how DocuMind implements it</strong>, and{' '}
          <strong>what goes wrong if you skip it</strong>. Click any row for the interview deep-dive: 5W, pros/cons,
          challenges, edge cases, input/process/output, monitoring + tracing.
        </p>
        <div className="design-areas-counts">
          {(['implemented', 'partial', 'designed'] as const).map((s) => (
            <span key={s} className={`status-pill ${STATUS_META[s].cssClass}`}>
              {STATUS_META[s].emoji} {STATUS_META[s].label}: <strong>{counts[s]}</strong>
            </span>
          ))}
          <span className="design-areas-total">
            Total: <strong>{DESIGN_AREAS.length}</strong>
          </span>
        </div>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
      </header>

      {GROUP_ORDER.map((group) => {
        const areas = DESIGN_AREAS.filter((d) => d.group === group);
        if (areas.length === 0) return null;
        return (
          <section key={group} className="design-areas-group">
            <h2 className="design-areas-group-title">{group}</h2>
            <div className="da-rows">
              {areas.map((da) => {
                const meta = STATUS_META[da.status];
                return (
                  <article key={da.id} className="da-row-card">
                    <div className="da-row-header">
                      <div className="da-row-ident">
                        <span className="da-row-id">{da.id}</span>
                        <h3 className="da-row-name">{da.name}</h3>
                      </div>
                      <div className="da-row-actions">
                        <span className={`status-pill ${meta.cssClass}`}>
                          {meta.emoji} {meta.label}
                        </span>
                        <Link href={`/tools/design-areas/${da.id}`} className="da-row-detaillink">
                          detail →
                        </Link>
                      </div>
                    </div>
                    <dl className="da-row-fields">
                      <div className="da-row-field">
                        <dt>Why it matters</dt>
                        <dd>{da.why}</dd>
                      </div>
                      <div className="da-row-field">
                        <dt>How DocuMind does it</dt>
                        <dd>{da.how}</dd>
                      </div>
                      <div className="da-row-field da-row-risk">
                        <dt>Risk if missing</dt>
                        <dd>{da.risk}</dd>
                      </div>
                      <div className="da-row-field da-row-classref">
                        <dt>Code</dt>
                        <dd><code>{da.classRef}</code></dd>
                      </div>
                    </dl>
                    <dl className="cb-card-dl da-row-derived">
                      <DerivedRows narr={{ name: da.name, problem: da.why, solution: da.how, example: da.risk, category: da.group }} />
                    </dl>
                    {(() => {
                      const paths = parseClassRef(da.classRef).slice(0, 2);
                      if (paths.length === 0) return null;
                      return (
                        <div className="da-row-code">
                          <div className="code-section-heading">Real code</div>
                          {paths.map((p) => (
                            <CodeBlock key={p} path={p} code={readRepoFile(p, 60)} />
                          ))}
                        </div>
                      );
                    })()}
                  </article>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
