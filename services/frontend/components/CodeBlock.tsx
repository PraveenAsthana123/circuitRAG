/**
 * Renders a pre/code block with a filename header and a line count.
 *
 * Kept as a server component — it only renders the content it's given.
 * No syntax highlighting yet (would pull in a large highlighter); the
 * existing .md-pre CSS gives us mono font, dark bg, scroll.
 */
export default function CodeBlock({
  path,
  code,
  label,
}: {
  path: string;
  code: string;
  label?: string;
}) {
  const lineCount = code.split('\n').length;
  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-label">{label ?? path}</span>
        <span className="code-block-meta">
          <code>{path}</code> · {lineCount} lines
        </span>
      </div>
      <pre className="md-pre code-block-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
