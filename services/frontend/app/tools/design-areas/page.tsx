import Link from 'next/link';
import {
  DESIGN_AREAS,
  GROUP_ORDER,
  STATUS_META,
  type DAStatus,
} from '../../../lib/design-areas';

export const metadata = { title: '74 Design Areas — DocuMind' };

/**
 * 67 core design areas + CCB (E1) + 6 AI-governance extras (E2–E7).
 *
 * Sourced from `docs/design-areas/table/00-INDEX.md`. Status reflects the
 * honest post-remediation snapshot — "implemented" means class + tests +
 * unit-run green, not full live-infra smoke.
 */
export default function DesignAreasPage() {
  const counts: Record<DAStatus, number> = { implemented: 0, partial: 0, designed: 0 };
  for (const da of DESIGN_AREAS) counts[da.status]++;

  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">74 System-Design Features</h1>
        <p className="design-areas-sub">
          Every load-bearing design decision in DocuMind, grouped and status-tagged.
          Each row points at the primary class or file that implements the area.
        </p>
        <div className="design-areas-counts">
          {(['implemented', 'partial', 'designed'] as const).map((s) => (
            <span key={s} className={`status-pill ${STATUS_META[s].cssClass}`}>
              {STATUS_META[s].emoji} {STATUS_META[s].label}:{' '}
              <strong>{counts[s]}</strong>
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
            <table className="design-areas-table">
              <thead>
                <tr>
                  <th className="da-col-id">#</th>
                  <th className="da-col-name">Area</th>
                  <th className="da-col-status">Status</th>
                  <th className="da-col-ref">Primary class / file</th>
                </tr>
              </thead>
              <tbody>
                {areas.map((da) => {
                  const meta = STATUS_META[da.status];
                  return (
                    <tr key={da.id} className={`da-row ${meta.cssClass}`}>
                      <td className="da-col-id">{da.id}</td>
                      <td className="da-col-name">{da.name}</td>
                      <td className="da-col-status">
                        <span className={`status-pill ${meta.cssClass}`}>
                          {meta.emoji} {meta.label}
                        </span>
                      </td>
                      <td className="da-col-ref"><code>{da.classRef}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        );
      })}
    </div>
  );
}
