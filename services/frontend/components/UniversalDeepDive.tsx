'use client';

/**
 * Universal interview-grade explanation card for any architecture
 * topic. Follows the user's 20-dimension "universal architecture
 * interview framework":
 *
 *   1.  Core concept
 *   2.  Problem it solves
 *   3.  Why this approach
 *   4.  When to use
 *   5.  When NOT to use
 *   6.  Input → Process → Output
 *   7.  Flowchart (mermaid)
 *   8.  Sequence diagram (mermaid)
 *   9.  Alternatives + tradeoffs
 *   10. Challenges
 *   11. Edge cases + solutions
 *   12. Failure modes
 *   13. Monitoring / runbook
 *   14. Testing strategy
 *   15. Security / governance
 *   16. Scaling / capacity
 *   17. Maturity model (MVP / production / enterprise)
 *   18. Limitations
 *   19. Where it fits in this project
 *   20. Interview line
 *
 * Reusable: passed a `Topic` object with these fields, renders the
 * full deep-dive section. /admin/llmops/deep and /admin/python/deep
 * predate this component — same shape, hand-coded — but new pages
 * (database, MCP, observability, RAG, etc.) should use this.
 */

import Mermaid from './Mermaid';

export interface Topic {
  slug: string;
  title: string;
  status?: 'shipped' | 'partial' | 'open';
  level?: { label: string; tone: string };
  coreConcept: string;
  problem: string;
  whyThisApproach: string;
  whenToUse: string[];
  whenNotToUse: string[];
  input: string;
  process: string[];
  output: string;
  flowchart?: string;
  sequence?: string;
  alternatives: { name: string; tradeoff: string }[];
  challenges: string[];
  edgeCases: { case: string; solution: string }[];
  failureModes: { mode: string; detect: string; recover: string }[];
  monitoring: string[];
  testing: string[];
  security: string[];
  scaling: string[];
  maturity: { mvp: string; production: string; enterprise: string };
  limitations: string[];
  projectFit: string[];
  interviewLine: string;
}

function statusBadgeClass(status?: Topic['status']): string {
  if (status === 'shipped') return 'badge badge-active';
  if (status === 'partial') return 'badge badge-parsing';
  if (status === 'open') return 'badge badge-failed';
  return '';
}

export default function UniversalDeepDive({ t }: { t: Topic }) {
  return (
    <article id={t.slug} className="card" style={{ marginBottom: 32 }}>
      <header style={{ marginBottom: 12 }}>
        <h2 className="section-title" style={{ marginBottom: 6 }}>
          {t.title}{' '}
          {t.status && <span className={statusBadgeClass(t.status)}>{t.status}</span>}
          {t.level && (
            <span
              className="badge"
              style={{
                backgroundColor: t.level.tone,
                color: '#ffffff',
                marginLeft: 6,
              }}
            >
              {t.level.label}
            </span>
          )}
        </h2>
        <p style={{ fontStyle: 'italic', color: '#000000' }}>{t.coreConcept}</p>
      </header>

      {/* Problem + Why */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
          <strong>Problem it solves</strong>
          <p style={{ marginTop: 4 }}>{t.problem}</p>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
          <strong>Why this approach</strong>
          <p style={{ marginTop: 4 }}>{t.whyThisApproach}</p>
        </div>
      </div>

      {/* When-to-use vs when-NOT */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
          <strong>When to use</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.whenToUse.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
          <strong>When NOT to use</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.whenNotToUse.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      </div>

      {/* Input → Process → Output */}
      <div style={{ marginBottom: 12 }}>
        <strong>Input → Process → Output</strong>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 2fr 1fr',
            gap: 12,
            marginTop: 6,
          }}
        >
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Input</div>
            <div>{t.input}</div>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Process</div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {t.process.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <div className="field-help">Output</div>
            <div>{t.output}</div>
          </div>
        </div>
      </div>

      {/* Flowchart */}
      {t.flowchart && (
        <div style={{ marginBottom: 12 }}>
          <strong>Flowchart</strong>
          <Mermaid chart={t.flowchart} />
        </div>
      )}

      {/* Sequence */}
      {t.sequence && (
        <div style={{ marginBottom: 12 }}>
          <strong>Sequence diagram</strong>
          <Mermaid chart={t.sequence} />
        </div>
      )}

      {/* Alternatives + tradeoffs */}
      <div style={{ marginBottom: 12 }}>
        <strong>Alternatives + tradeoffs</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Alternative</th>
              <th>Tradeoff</th>
            </tr>
          </thead>
          <tbody>
            {t.alternatives.map((a, i) => (
              <tr key={i}>
                <td>
                  <code>{a.name}</code>
                </td>
                <td>{a.tradeoff}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Challenges + Edge cases (with per-case solutions) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
          <strong>Challenges</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.challenges.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
          <strong>Edge cases + solutions</strong>
          <table className="table" style={{ marginTop: 6, fontSize: 13 }}>
            <tbody>
              {t.edgeCases.map((ec, i) => (
                <tr key={i}>
                  <td style={{ width: '50%' }}>{ec.case}</td>
                  <td>→ {ec.solution}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Failure modes */}
      <div style={{ marginBottom: 12 }}>
        <strong>Failure modes</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr>
              <th>Mode</th>
              <th>Detect</th>
              <th>Recover</th>
            </tr>
          </thead>
          <tbody>
            {t.failureModes.map((fm, i) => (
              <tr key={i}>
                <td>{fm.mode}</td>
                <td>{fm.detect}</td>
                <td>{fm.recover}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Monitoring + Testing */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#dbeafe' }}>
          <strong>Monitoring / runbook</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.monitoring.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#dbeafe' }}>
          <strong>Testing strategy</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.testing.map((te, i) => <li key={i}>{te}</li>)}
          </ul>
        </div>
      </div>

      {/* Security + Scaling */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div className="card" style={{ padding: 12, backgroundColor: '#ede9fe' }}>
          <strong>Security / governance</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.security.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
        <div className="card" style={{ padding: 12, backgroundColor: '#ecfdf5' }}>
          <strong>Scaling / capacity</strong>
          <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
            {t.scaling.map((sc, i) => <li key={i}>{sc}</li>)}
          </ul>
        </div>
      </div>

      {/* Maturity model */}
      <div style={{ marginBottom: 12 }}>
        <strong>Maturity model</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr>
              <th style={{ width: 130 }}>Stage</th>
              <th>Looks like</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>MVP</strong></td>
              <td>{t.maturity.mvp}</td>
            </tr>
            <tr>
              <td><strong>Production</strong></td>
              <td>{t.maturity.production}</td>
            </tr>
            <tr>
              <td><strong>Enterprise</strong></td>
              <td>{t.maturity.enterprise}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Limitations */}
      <div style={{ marginBottom: 12 }}>
        <strong>Limitations</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {t.limitations.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>

      {/* Project fit */}
      <div style={{ marginBottom: 12 }}>
        <strong>Where it fits in this project</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {t.projectFit.map((p, i) => (
            <li key={i}>
              <code style={{ fontSize: 13 }}>{p}</code>
            </li>
          ))}
        </ul>
      </div>

      {/* Interview line */}
      <div
        className="card"
        style={{ padding: 12, backgroundColor: '#dbeafe', borderColor: '#1e3a8a' }}
      >
        <strong>Interview line</strong>
        <p style={{ margin: '6px 0 0 0', fontStyle: 'italic' }}>
          &ldquo;{t.interviewLine}&rdquo;
        </p>
      </div>
    </article>
  );
}
