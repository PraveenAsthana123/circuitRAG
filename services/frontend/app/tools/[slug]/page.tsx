import Link from 'next/link';
import { notFound } from 'next/navigation';
import ToolTabs from '../../../components/ToolTabs';
import { TOOLS, getToolBySlug, type Tool } from '../../../lib/tools';

export async function generateStaticParams() {
  return TOOLS.map((t) => ({ slug: t.slug }));
}

type Props = { params: { slug: string } };

export function generateMetadata({ params }: Props) {
  const tool = getToolBySlug(params.slug);
  if (!tool) return { title: 'Tool not found — DocuMind' };
  return { title: `${tool.name} — DocuMind` };
}

export default function ToolDetail({ params }: Props) {
  const tool = getToolBySlug(params.slug);
  if (!tool) notFound();

  const siblings = TOOLS.filter((t) => t.category === tool.category && t.slug !== tool.slug);

  return (
    <div className="tool-page">
      <nav className="tool-breadcrumb">
        <Link href="/tools">← all tools</Link>
        <span className="tool-breadcrumb-sep">/</span>
        <span className="tool-breadcrumb-cat">{tool.category}</span>
      </nav>

      <header className="tool-header">
        <div>
          <h1 className="tool-name">{tool.name}</h1>
          <p className="tool-one-line">{tool.oneLine}</p>
          <a
            className="tool-weblink"
            href={tool.weblink}
            target="_blank"
            rel="noopener noreferrer"
          >
            {tool.weblink} ↗
          </a>
        </div>
        <div className="tool-header-scores">
          <ScoreBlock label="Maturity" value={tool.scoring.maturity} />
          <ScoreBlock label="Ops Load" value={tool.scoring.operational} invert />
          <ScoreBlock label="Benefit" value={tool.scoring.benefit} />
        </div>
      </header>

      <ToolTabs tool={tool} />

      {siblings.length > 0 && (
        <aside className="tool-related">
          <h4 className="tool-related-title">Other {labelFor(tool.category)}</h4>
          <ul className="tool-related-list">
            {siblings.map((s) => (
              <li key={s.slug}>
                <Link href={`/tools/${s.slug}`}>{s.name}</Link>
                <span className="tool-related-one-line"> — {s.oneLine}</span>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}

function labelFor(cat: Tool['category']): string {
  return (
    {
      'data-store': 'Data Stores',
      ai: 'AI / Inference',
      networking: 'Networking & Mesh',
      service: 'Services',
      reliability: 'Reliability',
      observability: 'Observability',
      framework: 'Frameworks',
    } as const
  )[cat];
}

function ScoreBlock({ label, value, invert = false }: { label: string; value: number; invert?: boolean }) {
  const effective = invert ? 10 - value : value;
  const tier = effective >= 8 ? 'score-hi' : effective >= 5 ? 'score-md' : 'score-lo';
  return (
    <div className={`score-block ${tier}`}>
      <div className="score-block-label">{label}</div>
      <div className="score-block-value">{value}<span className="score-block-max">/10</span></div>
    </div>
  );
}
