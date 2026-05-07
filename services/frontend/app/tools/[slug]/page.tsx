import Link from 'next/link';
import { notFound } from 'next/navigation';
import C4PageLinks from '../../../components/C4PageLinks';
import SpeechReader from '../../../components/SpeechReader';
import CodeBlock from '../../../components/CodeBlock';
import ToolExtrasPanel from '../../../components/ToolExtrasPanel';
import ToolTabs from '../../../components/ToolTabs';
import { readRepoFile } from '../../../lib/read-code';
import { TOOL_CODE_REFS } from '../../../lib/tool-code-refs';
import { TOOL_EXTRAS } from '../../../lib/tool-extras';
import { TOOLS, getToolBySlug, type Tool } from '../../../lib/tools';

export async function generateStaticParams() {
  return TOOLS.map((t) => ({ slug: t.slug }));
}

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const tool = getToolBySlug(slug);
  if (!tool) return { title: 'Tool not found — DocuMind' };
  return { title: `${tool.name} — DocuMind` };
}

export default async function ToolDetail({ params }: Props) {
  const { slug } = await params;
  const tool = getToolBySlug(slug);
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
          <div style={{ marginTop: 10 }}>
            <SpeechReader
              text={`${tool.name}. ${tool.oneLine}. Category ${tool.category}. Maturity ${tool.scoring.maturity} out of 10. Benefit ${tool.scoring.benefit} out of 10.`}
              compact
            />
          </div>
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

      <C4PageLinks
        title={`${tool.name} — C4 view`}
        summary={`Use the C4 model to place ${tool.name} in the broader system, then zoom into the deployable container, the internal component that owns it, and the code-level integration points that make it real in DocuMind.`}
        focus="For tool pages, Level 3 components is usually the best starting point, then Level 4 code for the concrete integration."
        levels={['containers', 'components', 'code', 'observability']}
      />

      <ToolTabs tool={tool} />

      {TOOL_EXTRAS[tool.slug] && <ToolExtrasPanel extras={TOOL_EXTRAS[tool.slug]} />}

      {(TOOL_CODE_REFS[tool.slug] ?? []).length > 0 && (
        <section className="tool-code-section">
          <h2 className="tool-code-title">Source code</h2>
          <p className="tool-code-sub">
            The actual files that implement this tool — rendered at build time from the repo.
          </p>
          {(TOOL_CODE_REFS[tool.slug] ?? []).map((ref) => (
            <CodeBlock
              key={ref.path + ref.label}
              label={ref.label}
              path={ref.path}
              code={readRepoFile(ref.path, ref.maxLines)}
            />
          ))}
        </section>
      )}

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
