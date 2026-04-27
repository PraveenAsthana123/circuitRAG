'use client';

/**
 * Compose-footer for deep-dive pages.
 *
 * Renders a small "Composes with" panel of links to other deep-dive
 * pages or features that this page directly relies on or extends.
 * Per ~/.claude/CLAUDE.md §49 — every deep-dive should declare its
 * compose surface explicitly so reviewers / new hires / auditors can
 * walk the dependency graph instead of inferring it.
 *
 * Usage:
 *   <DeepDiveCrossRefs
 *     refs={[
 *       { href: '/admin/tracing/deep', label: 'Baggage propagation', why: 'every retry hop carries request_id' },
 *       { href: '/admin/checklist/deep', label: 'Hard-stop gate', why: 'no rollback = block release' },
 *     ]}
 *   />
 */

import Link from 'next/link';

export type CrossRef = {
  href: string;
  label: string;
  why?: string;
};

export default function DeepDiveCrossRefs({ refs }: { refs: CrossRef[] }) {
  if (!refs || refs.length === 0) return null;
  return (
    <section
      style={{
        marginTop: 24,
        marginBottom: 8,
        padding: 16,
        borderLeft: '4px solid #2563eb',
        background: '#f1f5f9',
        borderRadius: 4,
      }}
      data-speech-skip="1"
      aria-label="This page composes with other deep-dives"
    >
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: '#1e3a8a',
          marginBottom: 8,
          letterSpacing: 0.3,
          textTransform: 'uppercase',
        }}
      >
        Composes with
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, color: '#0f172a' }}>
        {refs.map((r) => (
          <li key={r.href} style={{ marginBottom: 4, lineHeight: 1.5 }}>
            <Link
              href={r.href}
              style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 500 }}
            >
              {r.label}
            </Link>
            {r.why ? (
              <span style={{ color: '#475569' }}> — {r.why}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
