import Link from 'next/link';
import { TOOLS, type Tool } from '../../lib/tools';

/**
 * /tools index — groups every tool by category and renders a card grid.
 * Each card links to /tools/[slug]. The sidebar on the tool-detail page
 * will serve as the primary "pick another tool" affordance; this index
 * exists for an overview + direct deep-links from docs.
 */
const CATEGORY_ORDER: Array<{ key: Tool['category']; label: string; blurb: string }> = [
  { key: 'data-store', label: 'Data Stores', blurb: 'Where state actually lives — relational, vector, graph, cache, log.' },
  { key: 'ai', label: 'AI / Inference', blurb: 'LLMs, embeddings, the model serving layer.' },
  { key: 'networking', label: 'Networking & Mesh', blurb: 'Service-to-service traffic, ingress, mTLS, policy.' },
  { key: 'service', label: 'Services', blurb: 'First-party microservices we own end-to-end.' },
  { key: 'reliability', label: 'Reliability', blurb: 'Circuit breakers and failure-boundary enforcement.' },
  { key: 'observability', label: 'Observability', blurb: 'Logs, metrics, traces — and knowing when it breaks.' },
  { key: 'framework', label: 'Frameworks', blurb: 'Libraries and patterns that shape the code.' },
];

export const metadata = { title: 'Tools — DocuMind' };

export default function ToolsIndex() {
  return (
    <div className="tools-index">
      <h1 className="section-title">Tool Inventory</h1>
      <p className="tools-index-sub">
        Every piece of load-bearing infrastructure in DocuMind. Click any tool for a 6-tab
        deep-dive: dashboard state, features, benefits &amp; monitoring, integration I/O,
        system design, and an interview-ready talking point.
      </p>
      <div className="tools-overviews">
        <Link href="/tools/system-design" className="sysdesign-cta">
          <span className="sysdesign-cta-title">📐 System Design (13 diagrams)</span>
          <span className="sysdesign-cta-sub">Inline Mermaid for every tool.</span>
        </Link>
        <Link href="/tools/design-areas" className="sysdesign-cta">
          <span className="sysdesign-cta-title">🧭 74 Design Features</span>
          <span className="sysdesign-cta-sub">67 core + CCB + 6 AI-governance extras, with status.</span>
        </Link>
        <Link href="/tools/circuit-breakers-list" className="sysdesign-cta">
          <span className="sysdesign-cta-title">🔌 Circuit Breakers</span>
          <span className="sysdesign-cta-sub">5 specialized + CCB, with weblinks + code paths.</span>
        </Link>
        <Link href="/tools/microservice-scenarios" className="sysdesign-cta">
          <span className="sysdesign-cta-title">🧩 Microservice Scenarios</span>
          <span className="sysdesign-cta-sub">12 patterns with DocuMind examples + references.</span>
        </Link>
        <Link href="/tools/methodologies" className="sysdesign-cta">
          <span className="sysdesign-cta-title">🧪 Methodologies</span>
          <span className="sysdesign-cta-sub">TDD / BDD / MDD / DDD / Agent-DD — 8 in total.</span>
        </Link>
        <Link href="/tools/code-governance" className="sysdesign-cta">
          <span className="sysdesign-cta-title">🛡️ Code Governance</span>
          <span className="sysdesign-cta-sub">
            Standards, review, audit, debuggability — with per-design-area checklists.
          </span>
        </Link>
      </div>
      {CATEGORY_ORDER.map((cat) => {
        const tools = TOOLS.filter((t) => t.category === cat.key);
        if (tools.length === 0) return null;
        return (
          <section key={cat.key} className="tools-category">
            <h2 className="tools-category-title">{cat.label}</h2>
            <p className="tools-category-blurb">{cat.blurb}</p>
            <div className="tools-grid">
              {tools.map((t) => (
                <div key={t.slug} className="tool-card">
                  <Link href={`/tools/${t.slug}`} className="tool-card-main">
                    <div className="tool-card-title">{t.name}</div>
                    <p className="tool-card-one-line">{t.oneLine}</p>
                    <div className="tool-card-scores">
                      <ScorePill label="maturity" value={t.scoring.maturity} />
                      <ScorePill label="ops load" value={t.scoring.operational} invert />
                      <ScorePill label="benefit" value={t.scoring.benefit} />
                    </div>
                  </Link>
                  <a
                    href={t.weblink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="tool-card-weblink"
                  >
                    official docs ↗
                  </a>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function ScorePill({ label, value, invert = false }: { label: string; value: number; invert?: boolean }) {
  // invert=true: higher is worse (e.g. ops load).
  const effective = invert ? 10 - value : value;
  const tier =
    effective >= 8 ? 'score-hi' : effective >= 5 ? 'score-md' : 'score-lo';
  return (
    <span className={`score-pill ${tier}`}>
      <span className="score-pill-label">{label}</span>
      <span className="score-pill-value">{value}</span>
    </span>
  );
}
