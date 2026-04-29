import Link from 'next/link';
import C4PageLinks from '../../../components/C4PageLinks';
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
        <p className="sysdesign-sub" style={{ marginTop: 8 }}>
          For a topic-first study map anchored on a chatbot example, open{' '}
          <Link href="/admin/system-design/chatbot" style={{ color: '#1e3a8a' }}>
            /admin/system-design/chatbot
          </Link>
          . For framework/runtime choices around RAG, also see{' '}
          <Link href="/admin/lang-family/rag" style={{ color: '#1e3a8a' }}>
            /admin/lang-family/rag
          </Link>
          {' '}and{' '}
          <Link href="/admin/compiler-stack/rag" style={{ color: '#1e3a8a' }}>
            /admin/compiler-stack/rag
          </Link>
          .
        </p>
        <Link href="/tools" className="sysdesign-back">
          ← back to tool index
        </Link>
      </header>

      <C4PageLinks
        title="System-design overview — C4 view"
        summary="This page already shows one architecture diagram per tool. The C4 layer adds the abstraction ladder above those diagrams so you can ask: is this a context question, a container question, a component question, or a code question?"
        focus="Use Level 2 and 3 first here, then drop to Level 4 when a specific tool implementation matters."
        levels={['context', 'containers', 'components', 'code', 'observability']}
      />

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
