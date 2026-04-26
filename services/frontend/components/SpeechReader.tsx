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
  showSettingsHint?: boolean;
};

type Span = { word: string; start: number; end: number; sentenceIdx: number };

// Pronunciation dictionary — replaces tricky terms with phonetic-friendly
// forms before synthesis. Keys are word-boundary matched (case-insensitive).
// Browser TTS otherwise butchers acronyms and proper nouns.
const PRONUNCIATIONS: Record<string, string> = {
  RAG: 'R A G',
  MCP: 'M C P',
  JWT: 'J W T',
  PDF: 'P D F',
  ASR: 'A S R',
  TTS: 'T T S',
  HLD: 'H L D',
  LLD: 'L L D',
  SAD: 'system architecture document',
  ADR: 'A D R',
  BRD: 'business requirement document',
  RLS: 'R L S',
  CCB: 'cognitive circuit breaker',
  RBAC: 'arr-back',
  ABAC: 'ay-back',
  LLM: 'L L M',
  SLM: 'S L M',
  OTel: 'open telemetry',
  OPA: 'open policy agent',
  PII: 'P I I',
  RLAIF: 'R-L-A-I-F',
  RLHF: 'R-L-H-F',
  DPO: 'D P O',
  ORPO: 'O R P O',
  KTO: 'K T O',
  PEFT: 'peft',
  LoRA: 'lora',
  QLoRA: 'Q lora',
  DoRA: 'dora',
  RAFT: 'raft',
  LDAP: 'L-DAP',
  SSO: 'S S O',
  SAML: 'sammel',
  OIDC: 'O I D C',
  TLS: 'T L S',
  MLflow: 'M-L-flow',
  GPU: 'G P U',
  CPU: 'C P U',
  YAML: 'yammel',
  SQL: 'sequel',
  NoSQL: 'no sequel',
  GIL: 'gill',
};

function applyPronunciations(text: string): string {
  let out = text;
  for (const [from, to] of Object.entries(PRONUNCIATIONS)) {
    // Word-boundary, case-sensitive. Capture optional plural "s" so
    // "ADRs" / "PDFs" / "LLMs" still get rewritten and keep the suffix.
    out = out.replace(new RegExp(`\\b${from}(s?)\\b`, 'g'), (_m, s) => `${to}${s}`);
  }
  return out;
}

function tokenize(text: string): Span[] {
  const out: Span[] = [];
  // Split into sentences by .!? followed by whitespace
  const sentBreaks = new Set<number>();
  const sentRe = /[.!?]+\s+/g;
  let sm: RegExpExecArray | null;
  while ((sm = sentRe.exec(text)) !== null) {
    sentBreaks.add(sm.index + sm[0].length);
  }
  let sentenceIdx = 0;
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (sentBreaks.has(m.index)) sentenceIdx += 1;
    out.push({ word: m[0], start: m.index, end: m.index + m[0].length, sentenceIdx });
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

const LS_KEYS = {
  voice: 'documind.speech.voice',
  rate: 'documind.speech.rate',
  pitch: 'documind.speech.pitch',
  volume: 'documind.speech.volume',
} as const;

export default function SpeechReader({ text, rate: rateProp = 1.0, lang = 'en-US', compact = false, showSettingsHint = false }: Props) {
  const spans = useMemo(() => tokenize(text), [text]);
  const [activeIdx, setActiveIdx] = useState<number>(-1);
  const [state, setState] = useState<'idle' | 'speaking' | 'paused'>('idle');
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceName, setVoiceName] = useState<string>('');
  const [rate, setRate] = useState<number>(rateProp);
  const [pitch, setPitch] = useState<number>(1.0);
  const [volume, setVolume] = useState<number>(1.0);
  const [selectionText, setSelectionText] = useState<string>('');
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);
  const startSpanRef = useRef<number>(0);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const savedVoice = window.localStorage.getItem(LS_KEYS.voice);
    const savedRate = window.localStorage.getItem(LS_KEYS.rate);
    const savedPitch = window.localStorage.getItem(LS_KEYS.pitch);
    const savedVolume = window.localStorage.getItem(LS_KEYS.volume);
    if (savedVoice) setVoiceName(savedVoice);
    if (savedRate) {
      const parsed = Number(savedRate);
      if (!Number.isNaN(parsed)) setRate(parsed);
    }
    if (savedPitch) {
      const parsed = Number(savedPitch);
      if (!Number.isNaN(parsed)) setPitch(parsed);
    }
    if (savedVolume) {
      const parsed = Number(savedVolume);
      if (!Number.isNaN(parsed)) setVolume(parsed);
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !voiceName) return;
    window.localStorage.setItem(LS_KEYS.voice, voiceName);
  }, [voiceName]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(LS_KEYS.rate, String(rate));
  }, [rate]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(LS_KEYS.pitch, String(pitch));
  }, [pitch]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(LS_KEYS.volume, String(volume));
  }, [volume]);

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

  const speakFrom = useCallback((startIdx: number, customText?: string) => {
    if (!supported) return;
    const sourceText = customText !== undefined ? customText : text;
    if (!sourceText) return;
    window.speechSynthesis.cancel();
    // If startIdx > 0, slice the text to start from that word.
    const offset = customText !== undefined ? 0 : (spans[startIdx]?.start ?? 0);
    startSpanRef.current = startIdx;
    const sliced = sourceText.slice(offset);
    // Apply pronunciation dictionary for cleaner acronym readout
    const spoken = applyPronunciations(sliced);
    const utter = new SpeechSynthesisUtterance(spoken);
    utter.rate = rate;
    utter.pitch = pitch;
    utter.volume = volume;
    utter.lang = lang;
    if (voiceName) {
      const v = voices.find((x) => x.name === voiceName);
      if (v) utter.voice = v;
    }
    utter.onboundary = (e) => {
      if (e.name && e.name !== 'word') return;
      // boundary charIndex is into `spoken`. Map back: pronunciations expand
      // text length, so use spans[] proportional offset as approximation.
      // For accuracy we walk spans starting from startSpanRef.
      const targetCharInSlice = e.charIndex;
      let bestIdx = startSpanRef.current;
      for (let i = startSpanRef.current; i < spans.length; i++) {
        if ((spans[i].start - offset) <= targetCharInSlice) bestIdx = i;
        else break;
      }
      setActiveIdx(bestIdx);
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
  }, [supported, text, rate, pitch, volume, lang, voiceName, voices, spans]);

  const speak = useCallback(() => speakFrom(0), [speakFrom]);
  const speakSelection = useCallback(() => {
    if (selectionText) speakFrom(0, selectionText);
  }, [speakFrom, selectionText]);

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

  // Keyboard shortcuts: Space = pause/resume, Esc = stop. Bound to
  // document (window-level listeners can be missed if focus is in an
  // iframe-like region). Esc always calls stop() regardless of perceived
  // React state — synthesis-end events can race with key events and
  // leave the closure thinking we're 'idle' when the queue is still hot.
  useEffect(() => {
    if (!supported) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/i.test(target.tagName)) return;
      if (e.code === 'Space' && (state === 'speaking' || state === 'paused')) {
        e.preventDefault();
        if (state === 'speaking') window.speechSynthesis.pause();
        else if (state === 'paused') window.speechSynthesis.resume();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        stop();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [supported, state, stop]);

  // In-place highlighting on the actual page content via the CSS
  // Highlight API. Walking <main>'s text nodes and building Range
  // objects keyed by word index; activeIdx selects which range is
  // currently registered as the ::highlight(speech-active) target.
  // No DOM mutation — Range + CSS::highlight is non-invasive.
  const domRangesRef = useRef<Range[]>([]);
  const buildDomRanges = useCallback((): Range[] => {
    if (typeof document === 'undefined') return [];
    const root =
      (document.querySelector('main') as HTMLElement | null) ||
      (document.querySelector('article') as HTMLElement | null) ||
      document.body;
    if (!root) return [];
    const ranges: Range[] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      // Skip text inside controls (the toolbar speaks the page, not itself).
      let p: Node | null = node.parentNode;
      let inControl = false;
      while (p && p !== root) {
        const el = p as HTMLElement;
        const tag = el.tagName;
        if (tag && /^(BUTTON|SELECT|INPUT|TEXTAREA|LABEL|OPTION)$/i.test(tag)) {
          inControl = true;
          break;
        }
        if (el.dataset && el.dataset.speechSkip === '1') {
          inControl = true;
          break;
        }
        p = p.parentNode;
      }
      if (inControl) continue;
      const t = (node as Text).nodeValue || '';
      const re = /\S+/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(t)) !== null) {
        const r = document.createRange();
        r.setStart(node, m.index);
        r.setEnd(node, m.index + m[0].length);
        ranges.push(r);
      }
    }
    return ranges;
  }, []);

  // Update the CSS Highlight registration whenever activeIdx changes.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    // CSS.highlights is the standard API (Chrome 105+, Safari 17.2+,
    // Firefox 140+). If unavailable, fall back to no-op (still speaks).
    const ANY_CSS = (window as unknown as { CSS?: { highlights?: Map<string, unknown> } }).CSS;
    const reg = ANY_CSS?.highlights;
    if (!reg) return;
    if (activeIdx < 0) {
      reg.delete?.('speech-active');
      reg.delete?.('speech-sentence');
      return;
    }
    const ranges = domRangesRef.current;
    const target = ranges[activeIdx];
    if (!target) return;
    // Active word
    const ActiveCtor = (window as unknown as { Highlight?: new (...r: Range[]) => unknown }).Highlight;
    if (ActiveCtor) {
      reg.set?.('speech-active', new ActiveCtor(target));
      // Sentence highlight: collect siblings sharing sentenceIdx
      const sIdx = spans[activeIdx]?.sentenceIdx;
      if (sIdx !== undefined) {
        const sentenceRanges = spans
          .map((s, i) => (s.sentenceIdx === sIdx && i !== activeIdx ? ranges[i] : null))
          .filter((r): r is Range => !!r);
        if (sentenceRanges.length) {
          reg.set?.('speech-sentence', new ActiveCtor(...sentenceRanges));
        } else {
          reg.delete?.('speech-sentence');
        }
      }
    }
    // Scroll into view
    try {
      const rect = target.getBoundingClientRect();
      if (rect.top < 80 || rect.bottom > window.innerHeight - 60) {
        target.startContainer.parentElement?.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    } catch (_e) {
      // ignore
    }
  }, [activeIdx, spans]);

  // (Re)build DOM ranges whenever speech becomes active.
  useEffect(() => {
    if (state === 'speaking' && domRangesRef.current.length === 0) {
      domRangesRef.current = buildDomRanges();
    }
    if (state === 'idle') {
      domRangesRef.current = [];
    }
  }, [state, buildDomRanges]);

  // Watch for text selection — but DON'T pop up a giant panel. Just
  // keep the trimmed selection text in state so the toolbar can show
  // a small "Read selection" button only when ≥3 words are selected.
  useEffect(() => {
    if (!compact) return;
    const handler = () => {
      const sel = typeof window !== 'undefined' ? window.getSelection() : null;
      const txt = sel ? sel.toString().trim() : '';
      if (txt.split(/\s+/).length >= 3 && txt.length < 5000) {
        setSelectionText(txt);
      } else {
        setSelectionText('');
      }
    };
    document.addEventListener('selectionchange', handler);
    return () => document.removeEventListener('selectionchange', handler);
  }, [compact]);

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
  const hasLoadedVoices = voices.length > 0;
  const hasEnglishVoices = englishVoices.length > 0;
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
            title="Speech rate (Shift+Space when speaking)"
          >
            <option value="0.5">0.5×</option>
            <option value="0.75">0.75×</option>
            <option value="1">1×</option>
            <option value="1.5">1.5×</option>
            <option value="2">2×</option>
          </select>
        )}
        {compact && state === 'idle' && selectionText && (
          <button
            type="button"
            onClick={speakSelection}
            title={`Read selected text (${selectionText.split(/\s+/).length} words)`}
            style={{ ...btnStyle('#0ea5e9'), fontSize: 12 }}
          >
            🎯 Read selection
          </button>
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
      {!hasLoadedVoices && (
        <div
          style={{
            marginTop: compact ? 0 : 8,
            fontSize: 12,
            color: '#991b1b',
            maxWidth: compact ? 280 : 'none',
          }}
        >
          No browser speech voices were detected. Read-aloud may stay silent until browser or OS voices are installed and available.
        </div>
      )}
      {hasLoadedVoices && !hasEnglishVoices && (
        <div
          style={{
            marginTop: compact ? 0 : 8,
            fontSize: 12,
            color: '#92400e',
            maxWidth: compact ? 280 : 'none',
          }}
        >
          Browser speech is available, but no English voice was detected.
        </div>
      )}
      {!compact && (
        <>
        <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
          Browser speech status: {supported ? 'supported' : 'unsupported'} · voices loaded {voices.length} · English voices {englishVoices.length}
        </div>
        {showSettingsHint && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
            Current settings: {voiceName || 'default voice'} · {rate}x · pitch {pitch} · volume {volume}
          </div>
        )}
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
        </>
      )}
      {/* CSS Highlight rules — applied to the actual page text via
          Range objects registered in the activeIdx effect. No DOM
          mutation, no floating overlay. */}
      <style>{`
        ::highlight(speech-active) {
          background-color: #fef08a;
          color: #000;
        }
        ::highlight(speech-sentence) {
          text-decoration: underline 2px #fbbf24;
          text-underline-offset: 3px;
        }
      `}</style>
    </div>
  );
}
