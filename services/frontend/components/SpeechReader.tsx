'use client';

/**
 * SpeechReader — click 🔊 to read text aloud with per-word highlighting.
 *
 * Uses the browser's SpeechSynthesis API (free, no backend dependency).
 * The onboundary event fires per word; we map event.charIndex back to
 * the originating word span and apply a yellow highlight that
 * auto-scrolls into view.
 *
 * Why this and not a backend TTS roundtrip:
 * - Zero cost (no API calls)
 * - Zero latency to first audio
 * - Works offline / in air-gapped environments
 * - Same word-highlight UX users expect from accessibility tools
 *
 * For premium voice quality on a specific message, a separate "Hear
 * answer (premium)" button would call /api/v1/tts and stream back
 * audio — that's the architecture documented at /admin/audio/tts.
 * This component is the always-available baseline.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Props = {
  text: string;
  rate?: number;
  lang?: string;
  compact?: boolean;
};

type Span = { word: string; start: number; end: number };

function tokenize(text: string): Span[] {
  const out: Span[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  }
  return out;
}

function cssId(text: string): string {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return Math.abs(h).toString(16).slice(0, 8);
}

function btnStyle(color: string): React.CSSProperties {
  return {
    padding: '4px 10px',
    background: '#fff',
    color,
    border: `1px solid ${color}`,
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
  };
}

export default function SpeechReader({ text, rate = 1.0, lang = 'en-US', compact = false }: Props) {
  const spans = useMemo(() => tokenize(text), [text]);
  const [activeIdx, setActiveIdx] = useState<number>(-1);
  const [state, setState] = useState<'idle' | 'speaking' | 'paused'>('idle');
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);
  // Delay until client mount to avoid hydration mismatch (window-dependent
  // branch differs between SSR and client). On SSR/first render: null.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const findSpanByCharIndex = useCallback((charIndex: number): number => {
    for (let i = 0; i < spans.length; i++) {
      if (charIndex < spans[i].end) return i;
    }
    return spans.length - 1;
  }, [spans]);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setActiveIdx(-1);
    setState('idle');
  }, [supported]);

  const speak = useCallback(() => {
    if (!supported || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = rate;
    utter.lang = lang;
    utter.onboundary = (e) => {
      if (e.name && e.name !== 'word') return;
      const idx = findSpanByCharIndex(e.charIndex);
      setActiveIdx(idx);
    };
    utter.onstart = () => setState('speaking');
    utter.onpause = () => setState('paused');
    utter.onresume = () => setState('speaking');
    utter.onend = () => {
      setActiveIdx(-1);
      setState('idle');
    };
    utter.onerror = () => {
      setActiveIdx(-1);
      setState('idle');
    };
    utterRef.current = utter;
    window.speechSynthesis.speak(utter);
  }, [supported, text, rate, lang, findSpanByCharIndex]);

  const pauseFn = useCallback(() => {
    if (!supported) return;
    if (state === 'speaking') window.speechSynthesis.pause();
  }, [supported, state]);

  const resumeFn = useCallback(() => {
    if (!supported) return;
    if (state === 'paused') window.speechSynthesis.resume();
  }, [supported, state]);

  useEffect(() => {
    if (activeIdx < 0) return;
    const el = document.getElementById(`speech-w-${cssId(text)}-${activeIdx}`);
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIdx, text]);

  useEffect(() => () => stop(), [stop]);

  if (!mounted) return null;

  if (!supported) {
    return (
      <span title="Browser does not support SpeechSynthesis" style={{ color: '#9ca3af', fontSize: 13 }}>
        🔇
      </span>
    );
  }

  const idText = cssId(text);

  return (
    <div style={{ display: compact ? 'inline-flex' : 'block', alignItems: 'center', gap: 8 }}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        {state === 'idle' && (
          <button type="button" onClick={speak} title="Read aloud" style={btnStyle('#1e3a8a')} aria-label="Read aloud">
            🔊 {compact ? '' : 'Read'}
          </button>
        )}
        {state === 'speaking' && (
          <>
            <button type="button" onClick={pauseFn} title="Pause" style={btnStyle('#b45309')}>
              ⏸ Pause
            </button>
            <button type="button" onClick={stop} title="Stop" style={btnStyle('#991b1b')}>
              ⏹ Stop
            </button>
          </>
        )}
        {state === 'paused' && (
          <>
            <button type="button" onClick={resumeFn} title="Resume" style={btnStyle('#16a34a')}>
              ▶ Resume
            </button>
            <button type="button" onClick={stop} title="Stop" style={btnStyle('#991b1b')}>
              ⏹ Stop
            </button>
          </>
        )}
      </div>
      {!compact && (
        <div
          aria-live="polite"
          style={{
            marginTop: 8,
            padding: 10,
            background: '#fafaf9',
            borderLeft: '3px solid #1e3a8a',
            borderRadius: 4,
            color: '#000',
            fontSize: 14,
            lineHeight: 1.7,
            maxHeight: 220,
            overflowY: 'auto',
          }}
        >
          {spans.map((s, i) => {
            const active = i === activeIdx;
            return (
              <span
                key={i}
                id={`speech-w-${idText}-${i}`}
                style={{
                  background: active ? '#fef08a' : 'transparent',
                  fontWeight: active ? 700 : 400,
                  borderRadius: 2,
                  padding: active ? '1px 2px' : 0,
                  transition: 'background 80ms linear',
                }}
              >
                {s.word}
                {' '}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
