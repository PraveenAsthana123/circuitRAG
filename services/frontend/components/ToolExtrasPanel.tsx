import Mermaid from './Mermaid';
import type { ToolExtras } from '../lib/tool-extras';

/**
 * Renders the richer per-tool architecture artifacts as "one topic per row".
 *
 * Each row is a labeled section with one piece of content. No columns stacked
 * on top of each other — readers scan top-to-bottom, one concept at a time.
 */
export default function ToolExtrasPanel({ extras }: { extras: ToolExtras }) {
  const rows: { title: string; body: React.ReactNode }[] = [];

  if (extras.flowchart) {
    rows.push({ title: 'Flowchart', body: <Mermaid chart={extras.flowchart} /> });
  }
  if (extras.sequence) {
    rows.push({ title: 'Sequence Diagram', body: <Mermaid chart={extras.sequence} /> });
  }
  if (extras.networkFlow) {
    rows.push({ title: 'Network Flow', body: <Mermaid chart={extras.networkFlow} /> });
  }

  if (extras.ipo) {
    const { input, process, output } = extras.ipo;
    rows.push({
      title: 'Input',
      body: <ul className="cg-checklist">{input.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
    rows.push({
      title: 'Process',
      body: <ul className="cg-checklist">{process.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
    rows.push({
      title: 'Output',
      body: <ul className="cg-checklist">{output.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
  }

  if (extras.analysis) {
    const { comparison, edgeCases, limitations, challenges, solutions } = extras.analysis;
    rows.push({
      title: 'Comparison',
      body: (
        <table className="design-areas-table">
          <thead><tr><th>Scenario</th><th>Behaviour</th></tr></thead>
          <tbody>
            {comparison.map((c, k) => (
              <tr key={k}><td className="da-col-name">{c.scenario}</td><td>{c.behavior}</td></tr>
            ))}
          </tbody>
        </table>
      ),
    });
    rows.push({
      title: 'Edge Cases',
      body: <ul className="cg-checklist">{edgeCases.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
    rows.push({
      title: 'Limitations',
      body: <ul className="cg-checklist">{limitations.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
    rows.push({
      title: 'Challenges',
      body: <ul className="cg-checklist">{challenges.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
    rows.push({
      title: 'Solutions',
      body: <ul className="cg-checklist">{solutions.map((i, k) => <li key={k}>{i}</li>)}</ul>,
    });
  }

  if (extras.business) {
    const { valueProposition, kpis, roi } = extras.business;
    rows.push({
      title: 'Value Proposition',
      body: <p className="da-talk">{valueProposition}</p>,
    });
    rows.push({
      title: 'KPIs',
      body: (
        <table className="design-areas-table">
          <thead><tr><th>Metric</th><th>Target</th></tr></thead>
          <tbody>
            {kpis.map((k, i) => (
              <tr key={i}><td className="da-col-name">{k.name}</td><td>{k.target}</td></tr>
            ))}
          </tbody>
        </table>
      ),
    });
    rows.push({
      title: 'ROI',
      body: <p className="md-p">{roi}</p>,
    });
  }

  if (extras.audit) {
    const { checklist, qualityMatrix, externalLinks } = extras.audit;
    rows.push({
      title: 'Audit Checklist',
      body: <ul className="cg-checklist">{checklist.map((c, i) => <li key={i}>{c}</li>)}</ul>,
    });
    rows.push({
      title: 'Quality Matrix',
      body: (
        <table className="design-areas-table">
          <thead><tr><th>Dimension</th><th>Score</th><th>Note</th></tr></thead>
          <tbody>
            {qualityMatrix.map((q, i) => (
              <tr key={i}>
                <td className="da-col-name">{q.dimension}</td>
                <td>{q.score}</td>
                <td>{q.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ),
    });
    rows.push({
      title: 'External References',
      body: (
        <ul className="cg-checklist">
          {externalLinks.map((l, i) => (
            <li key={i}>
              <a href={l.url} target="_blank" rel="noopener noreferrer" className="cb-link">
                {l.label} ↗
              </a>
            </li>
          ))}
        </ul>
      ),
    });
  }

  if (extras.interviewTalkingPoint) {
    rows.push({
      title: 'Interview Talking Point (extended)',
      body: <p className="da-talk">"{extras.interviewTalkingPoint}"</p>,
    });
  }

  if (rows.length === 0) return null;

  return (
    <section className="tool-extras">
      <h2 className="tool-code-title">Deep Architecture</h2>
      <p className="tool-code-sub">
        Flowchart, sequence + network diagrams, I/O breakdown, and comparative analysis — one topic per row.
      </p>
      <div className="tool-extras-rows">
        {rows.map((r, k) => (
          <div key={k} className="tool-extras-row">
            <div className="tool-extras-row-title">{r.title}</div>
            <div className="tool-extras-row-body">{r.body}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
