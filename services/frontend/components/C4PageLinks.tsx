import Link from 'next/link';

const C4_BASE = '/admin/c4-model/deep';

type C4LevelKey =
  | 'context'
  | 'containers'
  | 'components'
  | 'code'
  | 'governance'
  | 'observability'
  | 'lifecycle';

const C4_LEVELS: Record<C4LevelKey, { label: string; href: string }> = {
  context: { label: 'Level 1 · System context', href: `${C4_BASE}#level-1-system-context` },
  containers: { label: 'Level 2 · Containers', href: `${C4_BASE}#level-2-containers` },
  components: { label: 'Level 3 · Components', href: `${C4_BASE}#level-3-components` },
  code: { label: 'Level 4 · Code', href: `${C4_BASE}#level-4-code` },
  governance: { label: 'Level 5 · Governance', href: `${C4_BASE}#level-5-governance` },
  observability: { label: 'Level 6 · Observability', href: `${C4_BASE}#level-6-observability` },
  lifecycle: { label: 'Level 7 · Lifecycle', href: `${C4_BASE}#level-7-lifecycle` },
};

export default function C4PageLinks({
  title,
  summary,
  focus,
  levels,
}: {
  title: string;
  summary: string;
  focus: string;
  levels: C4LevelKey[];
}) {
  return (
    <section className="c4-panel" aria-label={`${title} C4 modeling`}>
      <div className="c4-panel-head">
        <div>
          <div className="c4-panel-kicker">C4 modeling</div>
          <h2 className="c4-panel-title">{title}</h2>
        </div>
        <Link href={C4_BASE} className="c4-panel-master">
          Open full 7-level C4 deep dive →
        </Link>
      </div>

      <p className="c4-panel-summary">{summary}</p>
      <div className="c4-panel-focus">
        <span className="c4-panel-focus-label">Best lens for this page</span>
        <span className="c4-panel-focus-value">{focus}</span>
      </div>

      <div className="c4-panel-links">
        {levels.map((level) => (
          <Link key={level} href={C4_LEVELS[level].href} className="c4-panel-link">
            {C4_LEVELS[level].label}
          </Link>
        ))}
      </div>
    </section>
  );
}
