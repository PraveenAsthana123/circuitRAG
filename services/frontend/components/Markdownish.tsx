import type { ReactNode } from 'react';
import Mermaid from './Mermaid';

/**
 * Renders the tiny "Markdown-ish" subset used by lib/tools.ts bodies.
 *
 * Why not a full MD renderer? We control every input (static TS), so a
 * focused parser beats pulling in react-markdown + rehype-* and fighting
 * server/client boundary issues.
 *
 * Supports:
 *   - paragraphs separated by blank lines
 *   - **bold**, *italic*, `code` inline
 *   - "- item" and "1. item" lists (contiguous lines)
 *   - fenced code blocks ```lang ... ```
 *   - ```mermaid``` fences render as an actual diagram
 */
export default function Markdownish({ body }: { body: string }) {
  return <div className="md">{renderBlocks(body)}</div>;
}

function renderBlocks(body: string): ReactNode[] {
  const lines = body.split('\n');
  const blocks: ReactNode[] = [];
  let i = 0;
  let counter = 0;
  const nextKey = () => `b${counter++}`;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      const code = codeLines.join('\n');
      if (lang === 'mermaid') {
        blocks.push(<Mermaid key={nextKey()} chart={code} />);
      } else {
        blocks.push(
          <pre key={nextKey()} className="md-pre">
            <code>{code}</code>
          </pre>,
        );
      }
      continue;
    }

    if (line.trim() === '') {
      i++;
      continue;
    }

    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: string[] = [];
      const ordered = /^\s*\d+\.\s+/.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''));
        i++;
      }
      const Tag = ordered ? 'ol' : 'ul';
      blocks.push(
        <Tag key={nextKey()} className="md-list">
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it)}</li>
          ))}
        </Tag>,
      );
      continue;
    }

    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].startsWith('```') &&
      !/^\s*([-*]|\d+\.)\s+/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={nextKey()} className="md-p">
        {renderInline(paraLines.join(' '))}
      </p>,
    );
  }
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  const re = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > cursor) out.push(text.slice(cursor, idx));
    if (m[1] !== undefined) out.push(<code key={key++}>{m[1]}</code>);
    else if (m[2] !== undefined) out.push(<strong key={key++}>{m[2]}</strong>);
    else if (m[3] !== undefined) out.push(<em key={key++}>{m[3]}</em>);
    cursor = idx + m[0].length;
  }
  if (cursor < text.length) out.push(text.slice(cursor));
  return out;
}
