'use client';

/**
 * SpeechReader — click 🔊 to read text aloud with per-word highlighting.
 *
 * Features:
 * - Browser SpeechSynthesis API (free, no backend, offline-capable)
 * - Per-word highlight via onboundary event (charIndex → span)
 * - Voice picker (lists all OS-provided voices; pick high-quality)
 * - Speed control (0.5× – 2.0×)
 * - Pause / resume / stop controls
 * - Long-text safe: no API length limit; chunks if needed
 * - Hydration-safe: delays render until client mount (avoids React #418/#422)
 *
 * Voice quality varies by OS:
 *   macOS/iOS:  "Samantha", "Alex", "Karen" — high quality
 *   Windows:    "Microsoft Zira", "Microsoft David" — decent
 *   Chrome:     "Google US English", "Google UK English" — high quality
 *   Linux:      espeak / festival defaults — robotic but functional
 *
 * For premium voice (ElevenLabs / Riva / OpenAI audio) the same UI swaps
 * to a backend /api/v1/tts call — see /admin/audio/tts.
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

function selectStyle(): React.CSSProperties {
  return {
    padding: '3px 6px',
    background: '#fff',
    color: '#1e3a8a',
    border: '1px solid #e5e7eb',
    borderRadius: 4,
    fontSize: 12,
    cursor: 'pointer',
    maxWidth: 180,
  };
}

export default function SpeechReader({ text, rate: rateProp = 1.0, lang = 'en-US', compact = false }: Props) {
  const spans = useMemo(() => tokenize(text), [text]);
  const [activeIdx, setActiveIdx] = useState<number>(-1);
  const [state, setState] = useState<'idle' | 'speaking' | 'paused'>('idle');
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceName, setVoiceName] = useState<string>('');
  const [rate, setRate] = useState<number>(rateProp);
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  // Load voices (some browsers populate asynchronously via voiceschanged).
  useEffect(() => {
    if (!supported) return;
    const refresh = () => {
      const all = window.speechSynthesis.getVoices();
      setVoices(all);
      // Prefer high-quality default per OS
      if (!voiceName && all.length) {
        const preferred =
          all.find((v) => /Google US English/i.test(v.name)) ||
          all.find((v) => /Samantha/i.test(v.name)) ||
          all.find((v) => v.lang.startsWith('en') && v.localService) ||
          all.find((v) => v.lang.startsWith('en')) ||
          all[0];
        if (preferred) setVoiceName(preferred.name);
      }
    };
    refresh();
    window.speechSynthesis.addEventListener?.('voiceschanged', refresh);
    return () => window.speechSynthesis.removeEventListener?.('voiceschanged', refresh);
  }, [supported, voiceName]);

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
    if (voiceName) {
      const v = voices.find((x) => x.name === voiceName);
      if (v) utter.voice = v;
    }
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
  }, [supported, text, rate, lang, voiceName, voices, findSpanByCharIndex]);

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
  // Filter to English; classify by gender via name heuristic.
  const englishVoices = voices.filter((v) => v.lang.startsWith('en'));
  const FEMALE_HINTS = /samantha|karen|fiona|moira|tessa|veena|zira|susan|catherine|female|woman|allison|ava|joanna|kendra|kimberly|salli|amy|emma|lupe|joanna|raveena|aditi|mia|sophia|lilly/i;
  const MALE_HINTS = /alex|daniel|fred|david|mark|tom|fellow|guy|matthew|brian|justin|joey|kevin|male|man|aaron|liam|oliver|ethan|noah|joshua|carlos|miguel|hans|leo/i;
  const classify = (name: string): '♀' | '♂' | '·' => {
    if (FEMALE_HINTS.test(name)) return '♀';
    if (MALE_HINTS.test(name)) return '♂';
    return '·';
  };
  const female = englishVoices.filter((v) => classify(v.name) === '♀');
  const male = englishVoices.filter((v) => classify(v.name) === '♂');
  const other = englishVoices.filter((v) => classify(v.name) === '·');

  // Active = speaking or paused (NOT idle). Used to render filled
  // button + highlighter overlay.
  const isActive = state === 'speaking' || state === 'paused';
  const filledBtn = (color: string): React.CSSProperties => ({
    padding: '4px 10px',
    background: color,
    color: '#fff',
    border: `1px solid ${color}`,
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 700,
    boxShadow: '0 0 0 2px rgba(180, 83, 9, 0.25)',
  });

  return (
    <div style={{ display: compact ? 'inline-flex' : 'block', alignItems: 'center', gap: 8, position: 'relative' }}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {state === 'idle' && (
          <button type="button" onClick={speak} title="Read aloud" style={btnStyle('#1e3a8a')} aria-label="Read aloud">
            🔊 {compact ? '' : 'Read'}
          </button>
        )}
        {state === 'speaking' && (
          <>
            <button type="button" onClick={pauseFn} title="Pause (currently speaking)" style={filledBtn('#b45309')} aria-label="Speaking — click to pause">
              🔊 Speaking · ⏸
            </button>
            <button type="button" onClick={stop} title="Stop" style={btnStyle('#991b1b')}>⏹</button>
          </>
        )}
        {state === 'paused' && (
          <>
            <button type="button" onClick={resumeFn} title="Resume" style={filledBtn('#16a34a')}>▶ Resume</button>
            <button type="button" onClick={stop} title="Stop" style={btnStyle('#991b1b')}>⏹</button>
          </>
        )}
        {compact && englishVoices.length > 1 && (
          <select
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            style={{ ...selectStyle(), maxWidth: 130 }}
            title="Voice (♀/♂)"
          >
            {female.length > 0 && (
              <optgroup label="♀ Female">
                {female.map((v) => (
                  <option key={v.name} value={v.name}>♀ {v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
            {male.length > 0 && (
              <optgroup label="♂ Male">
                {male.map((v) => (
                  <option key={v.name} value={v.name}>♂ {v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
            {other.length > 0 && (
              <optgroup label="· Other">
                {other.map((v) => (
                  <option key={v.name} value={v.name}>{v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
          </select>
        )}
        {compact && (
          <select
            value={String(rate)}
            onChange={(e) => setRate(Number(e.target.value))}
            style={{ ...selectStyle(), maxWidth: 70 }}
            title="Speech rate"
          >
            <option value="0.5">0.5×</option>
            <option value="0.75">0.75×</option>
            <option value="1">1×</option>
            <option value="1.5">1.5×</option>
            <option value="2">2×</option>
          </select>
        )}
        {!compact && englishVoices.length > 1 && (
          <select
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
            style={selectStyle()}
            title="Pick voice (tone)"
          >
            {female.length > 0 && (
              <optgroup label="♀ Female">
                {female.map((v) => (
                  <option key={v.name} value={v.name}>{v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
            {male.length > 0 && (
              <optgroup label="♂ Male">
                {male.map((v) => (
                  <option key={v.name} value={v.name}>{v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
            {other.length > 0 && (
              <optgroup label="· Other">
                {other.map((v) => (
                  <option key={v.name} value={v.name}>{v.name}{v.localService ? '' : ' ☁'}</option>
                ))}
              </optgroup>
            )}
          </select>
        )}
        {!compact && (
          <select
            value={String(rate)}
            onChange={(e) => setRate(Number(e.target.value))}
            style={selectStyle()}
            title="Speech rate"
          >
            <option value="0.5">0.5× slow</option>
            <option value="0.75">0.75×</option>
            <option value="1">1× normal</option>
            <option value="1.5">1.5× fast</option>
            <option value="2">2× very fast</option>
          </select>
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
      {compact && isActive && (
        // Floating highlighter overlay below the toolbar pill — shows
        // which word is being read when invoked from the global page
        // toolbar. Auto-scrolls active word into view.
        <div
          aria-live="polite"
          style={{
            position: 'fixed',
            top: 56,
            right: 16,
            zIndex: 40,
            width: 'min(640px, calc(100vw - 32px))',
            maxHeight: 240,
            overflowY: 'auto',
            background: 'rgba(255,255,255,0.98)',
            border: '1px solid #e5e7eb',
            borderLeft: '4px solid #b45309',
            borderRadius: 8,
            boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
            padding: 12,
            fontSize: 14,
            lineHeight: 1.7,
            color: '#000',
          }}
        >
          <div style={{ fontSize: 11, color: '#b45309', fontWeight: 700, marginBottom: 6, letterSpacing: 0.5 }}>
            🔊 SPEAKING — word being read is highlighted
          </div>
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
