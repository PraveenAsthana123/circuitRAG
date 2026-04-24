import Link from 'next/link';
import Mermaid from '../../../components/Mermaid';
import { TOOLS } from '../../../lib/tools';

export const metadata = { title: 'System Design — DocuMind' };

/**
 * One-scroll view of every tool's system-design diagram.
 *
 * Why a dedicated page? Individual tool pages hide the diagram behind the
 * "System Design" tab — great for depth, bad for overview. This page renders
 * all 13 diagrams inline so you can scan the full architecture in one scroll
 * without clicking anywhere.
 */
function extractMermaid(body: string): string | null {
  const fence = /```mermaid\n([\s\S]*?)```/;
  const m = body.match(fence);
  return m ? m[1].trim() : null;
}

export default function SystemDesignOverview() {
  return (
    <div className="sysdesign-page">
      <header className="sysdesign-header">
        <h1 className="section-title">System Design — all tools</h1>
        <p className="sysdesign-sub">
          One diagram per tool. Click any heading to open the full 6-tab deep-dive.
          Hover any node to read its role — diagrams render from{' '}
          <code>lib/tools.ts</code> via Mermaid.
        </p>
        <Link href="/tools" className="sysdesign-back">
          ← back to tool index
        </Link>
      </header>

      {TOOLS.map((tool) => {
        const diagram = extractMermaid(tool.tabs.visualization.body);
        return (
          <section key={tool.slug} className="sysdesign-tool" id={tool.slug}>
            <div className="sysdesign-tool-head">
              <div>
                <h2 className="sysdesign-tool-name">
                  <Link href={`/tools/${tool.slug}`}>{tool.name}</Link>
                </h2>
                <p className="sysdesign-tool-one-line">{tool.oneLine}</p>
              </div>
              <div className="sysdesign-tool-links">
                <a href={tool.weblink} target="_blank" rel="noopener noreferrer" className="sysdesign-extlink">
                  docs ↗
                </a>
                <Link href={`/tools/${tool.slug}`} className="sysdesign-detaillink">
                  deep-dive →
                </Link>
              </div>
            </div>
            {diagram ? (
              <Mermaid chart={diagram} />
            ) : (
              <p className="sysdesign-nodiagram">No mermaid diagram for this tool yet.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
