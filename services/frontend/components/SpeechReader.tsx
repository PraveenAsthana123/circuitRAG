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

function getSelectedText(): string {
  if (typeof window === 'undefined') return '';
  const selected = window.getSelection?.()?.toString() || '';
  return selected.replace(/\s+/g, ' ').trim();
}

function clampVolume(value: number): number {
  if (Number.isNaN(value)) return 1.0;
  if (value <= 0) return 1.0;
  return Math.min(1.0, Math.max(0.1, value));
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
  const [state, setState] = useState<'idle' | 'speaking' | 'paused' | 'server_loading'>('idle');
  const [playbackMode, setPlaybackMode] = useState<'browser' | 'server' | null>(null);
  const [activeAction, setActiveAction] = useState<'read' | 'selected' | 'full' | 'server' | null>(null);
  const [serverAvailable, setServerAvailable] = useState(false);
  const [serverVoice, setServerVoice] = useState<string>('');
  const [serverError, setServerError] = useState<string>('');
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceName, setVoiceName] = useState<string>('');
  const [rate, setRate] = useState<number>(rateProp);
  const [pitch, setPitch] = useState<number>(1.0);
  const [volume, setVolume] = useState<number>(1.0);
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const compactMenuRef = useRef<HTMLDetailsElement | null>(null);
  const startSpanRef = useRef<number>(0);
  // Cancel hook for the in-flight server-TTS chunk queue. stop() calls
  // this so a queued chunk doesn't keep playing after the user clicked ⏹.
  const serverChunkCancelRef = useRef<(() => void) | null>(null);
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
      if (!Number.isNaN(parsed)) setVolume(clampVolume(parsed));
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    fetch('/api/v1/tts')
      .then(async (resp) => {
        if (!resp.ok) return null;
        return resp.json() as Promise<{ available?: boolean; voice?: string }>;
      })
      .then((data) => {
        if (!mounted || !data) return;
        setServerAvailable(Boolean(data.available));
        setServerVoice(data.voice || '');
      })
      .catch(() => {
        if (!mounted) return;
        setServerAvailable(false);
      });
    return () => {
      mounted = false;
    };
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
    const normalized = clampVolume(volume);
    if (normalized !== volume) {
      setVolume(normalized);
      return;
    }
    window.localStorage.setItem(LS_KEYS.volume, String(normalized));
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
    if (supported) window.speechSynthesis.cancel();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    // Abort any in-flight server-TTS chunk queue so subsequent chunks
    // don't continue playing after the user clicked ⏹.
    if (serverChunkCancelRef.current) {
      serverChunkCancelRef.current();
      serverChunkCancelRef.current = null;
    }
    setActiveIdx(-1);
    setPlaybackMode(null);
    setActiveAction(null);
    setServerError('');
    setState('idle');
  }, [supported]);

  const closeCompactMenu = useCallback(() => {
    compactMenuRef.current?.removeAttribute('open');
  }, []);

  // Chunk text on sentence/paragraph boundaries so each piece is
  // ≤ MAX_CHARS. Keeps the synthesizer from choking on long pages —
  // the backend /api/v1/tts caps payload at 4000 chars; browser TTS
  // chokes around 15 000 in some implementations. Chunks are queued
  // and played sequentially via one shared <audio> element.
  const chunkText = useCallback((source: string, maxChars: number = 3800): string[] => {
    const trimmed = source.trim();
    if (trimmed.length <= maxChars) return [trimmed];
    const chunks: string[] = [];
    // Split on sentence boundaries first
    const sentences = trimmed.split(/(?<=[.!?])\s+/);
    let buf = '';
    for (const s of sentences) {
      if (s.length > maxChars) {
        // Single sentence too long — split on whitespace
        if (buf) { chunks.push(buf); buf = ''; }
        const words = s.split(/\s+/);
        let wbuf = '';
        for (const w of words) {
          if ((wbuf + ' ' + w).length > maxChars) {
            if (wbuf) chunks.push(wbuf);
            wbuf = w;
          } else {
            wbuf = wbuf ? `${wbuf} ${w}` : w;
          }
        }
        if (wbuf) buf = wbuf;
        continue;
      }
      if ((buf + ' ' + s).length > maxChars) {
        if (buf) chunks.push(buf);
        buf = s;
      } else {
        buf = buf ? `${buf} ${s}` : s;
      }
    }
    if (buf) chunks.push(buf);
    return chunks;
  }, []);

  const speakViaServer = useCallback(async (customText?: string) => {
    const sourceText = (customText ?? text).trim();
    if (!sourceText) return;
    setState('server_loading');
    setPlaybackMode('server');
    setActiveIdx(-1);
    setServerError('');

    const chunks = chunkText(sourceText, 3800);

    // Single shared <audio> element; sequentially load + play each chunk.
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    const audio = audioRef.current;
    audio.volume = clampVolume(volume);

    let cancelled = false;
    const cancelAtChunk = () => { cancelled = true; };
    serverChunkCancelRef.current = cancelAtChunk;

    try {
      for (let i = 0; i < chunks.length; i++) {
        if (cancelled) break;
        const piece = chunks[i];
        const resp = await fetch('/api/v1/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: piece, format: 'mp3' }),
        });
        if (!resp.ok) {
          let detail = `TTS chunk ${i + 1}/${chunks.length} failed with status ${resp.status}`;
          try {
            const payload = await resp.json();
            detail = payload?.detail || detail;
          } catch {
            // keep generic
          }
          throw new Error(detail);
        }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);

        await new Promise<void>((resolve, reject) => {
          audio.onplay = () => {
            setPlaybackMode('server');
            setState('speaking');
          };
          audio.onpause = () => setState((current) => (current === 'idle' ? current : 'paused'));
          audio.onended = () => {
            URL.revokeObjectURL(url);
            resolve();
          };
          audio.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error('Server audio could not be played by this browser.'));
          };
          audio.src = url;
          audio.load();
          audio.play().catch(reject);
        });
        if (cancelled) {
          audio.pause();
          break;
        }
      }
      setPlaybackMode(null);
      setState('idle');
      return true;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      if (/NotAllowedError|play\(\) failed/i.test(detail)) {
        setServerError('Browser blocked autoplay. Click the speaker again after interacting with the page.');
      } else {
        setServerError(detail);
      }
      setPlaybackMode(null);
      setState('idle');
      return false;
    } finally {
      serverChunkCancelRef.current = null;
    }
  }, [text, volume, chunkText]);

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

    // Chrome has a silent ~15k-char cap on a single utterance — long
    // pages get cut off mid-read with no error. Chunk the spoken text
    // and queue utterances so the synthesizer reads the full page.
    // Each chunk gets its own utterance with the same voice/rate/pitch.
    // The first utterance fires immediately so playback starts fast;
    // subsequent ones queue automatically (speechSynthesis maintains
    // a FIFO queue when speak() is called multiple times without
    // cancel()).
    const pieces = chunkText(spoken, 4000);

    setPlaybackMode('browser');
    let cumulativeOffset = 0;
    pieces.forEach((piece, idx) => {
      const utter = new SpeechSynthesisUtterance(piece);
      utter.rate = rate;
      utter.pitch = pitch;
      utter.volume = clampVolume(volume);
      utter.lang = lang;
      if (voiceName) {
        const v = voices.find((x) => x.name === voiceName);
        if (v) utter.voice = v;
      }
      const pieceStartInSpoken = cumulativeOffset;
      utter.onboundary = (e) => {
        if (e.name && e.name !== 'word') return;
        // charIndex is into THIS piece; add piece's start offset for
        // mapping back to original spans[].
        const targetCharInSlice = pieceStartInSpoken + e.charIndex;
        let bestIdx = startSpanRef.current;
        for (let i = startSpanRef.current; i < spans.length; i++) {
          if ((spans[i].start - offset) <= targetCharInSlice) bestIdx = i;
          else break;
        }
        setActiveIdx(bestIdx);
      };
      // Only fire start/end hooks on first/last piece so the state
      // machine doesn't churn between chunks.
      if (idx === 0) {
        utter.onstart = () => {
          setPlaybackMode('browser');
          setState('speaking');
        };
      }
      utter.onpause = () => setState('paused');
      utter.onresume = () => setState('speaking');
      if (idx === pieces.length - 1) {
        utter.onend = () => {
          setActiveIdx(-1);
          setPlaybackMode(null);
          setState('idle');
        };
      }
      utter.onerror = () => {
        // Don't reset state on a single piece's error mid-queue —
        // the next piece may still play. Only the LAST piece's
        // error path resets to idle.
        if (idx === pieces.length - 1) {
          setActiveIdx(-1);
          setPlaybackMode(null);
          setState('idle');
        }
      };
      if (idx === pieces.length - 1) utterRef.current = utter;
      window.speechSynthesis.speak(utter);
      cumulativeOffset += piece.length + 1; // +1 for chunkText join space
    });
  }, [supported, text, rate, pitch, volume, lang, voiceName, voices, spans, chunkText]);

  // Detect platform-specific install hint for missing voices.
  const noVoiceHint = useMemo(() => {
    if (typeof navigator === 'undefined') return '';
    const ua = navigator.userAgent.toLowerCase();
    if (/linux/.test(ua) && !/android/.test(ua)) {
      return 'Linux: install speech-dispatcher + espeak-ng (sudo apt install speech-dispatcher espeak-ng), then restart the browser.';
    }
    if (/android/.test(ua)) {
      return 'Android: enable a TTS engine in Settings → Accessibility → Text-to-speech output.';
    }
    if (/iphone|ipad|ipod/.test(ua)) {
      return 'iOS: voices should be pre-installed. Try a different browser (Safari is most reliable).';
    }
    return 'Windows/macOS: voices are usually pre-installed. Try a different browser if Chrome shows zero voices.';
  }, []);

  const speak = useCallback(() => {
    closeCompactMenu();
    const selectedText = getSelectedText();
    setActiveAction('read');
    if (supported && voices.length > 0) {
      // Browser path — fires word-boundary highlights + pill updates.
      speakFrom(0, selectedText || undefined);
      return;
    }
    if (supported && voices.length === 0) {
      // Loud, actionable error — silent failure was the user's main pain.
      // Skip server-TTS attempt entirely (it would clobber this message
      // and likely 404 anyway); user needs to fix the root cause.
      setServerError(
        `No browser text-to-speech voices detected (voices.length = 0). ` +
        `Click 🔊 cannot produce sound until voices are installed. ` +
        noVoiceHint +
        ' Word-by-word highlight + the "currently reading" pill require browser TTS — they cannot work without browser-side voices, since server TTS does not expose per-word timing.',
      );
      return;
    }
    void speakViaServer(selectedText || undefined);
  }, [closeCompactMenu, speakFrom, speakViaServer, supported, voices.length, noVoiceHint]);

  const speakSelected = useCallback(() => {
    closeCompactMenu();
    const selectedText = getSelectedText();
    if (!selectedText) {
      setServerError('No text is selected.');
      return;
    }
    setActiveAction('selected');
    setServerError('');
    if (supported && voices.length > 0) {
      speakFrom(0, selectedText);
    } else {
      void speakViaServer(selectedText);
    }
  }, [closeCompactMenu, speakFrom, speakViaServer, supported, voices.length]);

  const speakFull = useCallback(() => {
    closeCompactMenu();
    setActiveAction('full');
    if (supported && voices.length > 0) {
      speakFrom(0);
    } else {
      void speakViaServer();
    }
  }, [closeCompactMenu, speakFrom, speakViaServer, supported, voices.length]);

  const speakServerOnly = useCallback(() => {
    closeCompactMenu();
    const selectedText = getSelectedText();
    setActiveAction('server');
    void speakViaServer(selectedText || undefined);
  }, [closeCompactMenu, speakViaServer]);

  const pauseFn = useCallback(() => {
    if (state !== 'speaking') return;
    if (playbackMode === 'browser' && supported) window.speechSynthesis.pause();
    if (playbackMode === 'server') audioRef.current?.pause();
  }, [playbackMode, supported, state]);

  const resumeFn = useCallback(() => {
    if (state !== 'paused') return;
    if (playbackMode === 'browser' && supported) window.speechSynthesis.resume();
    if (playbackMode === 'server') void audioRef.current?.play();
  }, [playbackMode, supported, state]);

  useEffect(() => {
    if (activeIdx < 0) return;
    const el = document.getElementById(`speech-w-${cssId(text)}-${activeIdx}`);
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIdx, text]);

  useEffect(() => () => stop(), [stop]);

  useEffect(() => {
    if (!compact || typeof document === 'undefined') return;
    const handlePointerDown = (event: MouseEvent) => {
      const menu = compactMenuRef.current;
      if (!menu?.hasAttribute('open')) return;
      const target = event.target as Node | null;
      if (target && menu.contains(target)) return;
      menu.removeAttribute('open');
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [compact]);

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
        if (playbackMode === 'browser') {
          if (state === 'speaking') window.speechSynthesis.pause();
          else if (state === 'paused') window.speechSynthesis.resume();
        } else if (playbackMode === 'server') {
          if (state === 'speaking') audioRef.current?.pause();
          else if (state === 'paused') void audioRef.current?.play();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        stop();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [playbackMode, state, stop, supported]);

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

  if (!mounted) return null;

  if (!supported && !compact) {
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
  const actionColor = (action: 'read' | 'selected' | 'full' | 'server'): string => {
    if (action === 'read') return '#1e3a8a';
    if (action === 'selected') return '#7c3aed';
    if (action === 'full') return '#4338ca';
    return '#0f766e';
  };
  const actionLabel = (action: 'read' | 'selected' | 'full' | 'server' | null): string => {
    if (action === 'selected') return 'Selected read';
    if (action === 'full') return 'Full read';
    if (action === 'server') return 'Server audio';
    return 'Read + highlight';
  };
  const statusLabel =
    state === 'server_loading'
      ? `Preparing ${actionLabel(activeAction)}`
      : state === 'speaking'
        ? `${actionLabel(activeAction)} active`
        : state === 'paused'
          ? `${actionLabel(activeAction)} paused`
          : null;
  const isActionActive = (action: 'read' | 'selected' | 'full' | 'server') =>
    activeAction === action && state !== 'idle';
  const actionBtnStyle = (action: 'read' | 'selected' | 'full' | 'server'): React.CSSProperties =>
    isActionActive(action) ? filledBtn(actionColor(action)) : btnStyle(actionColor(action));
  const compactActionBtnStyle = (action: 'read' | 'selected' | 'full' | 'server'): React.CSSProperties => ({
    ...(isActionActive(action) ? filledBtn(actionColor(action)) : btnStyle(actionColor(action))),
    minWidth: 30,
    width: 30,
    height: 30,
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 14,
    lineHeight: 1,
  });
  const compactControlBtnStyle = (color: string): React.CSSProperties => ({
    ...btnStyle(color),
    minWidth: 30,
    width: 30,
    height: 30,
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 14,
    lineHeight: 1,
  });

  return (
    <div style={{ display: compact ? 'inline-block' : 'block', alignItems: 'center', gap: 8, position: 'relative' }}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {state !== 'speaking' && state !== 'paused' && (
          <>
            <button type="button" onClick={speak} title="Read aloud with highlight" style={compact ? compactActionBtnStyle('read') : actionBtnStyle('read')} aria-label="Read aloud with highlight">
              🔊 {compact ? '' : 'Read + highlight'}
            </button>
            <button type="button" onClick={speakFull} title="Read full content" style={compact ? compactActionBtnStyle('full') : actionBtnStyle('full')} aria-label="Read full content">
              📖 {compact ? '' : 'Full read'}
            </button>
            {!compact && (
              <>
                <button type="button" onClick={speakSelected} title="Read selected text" style={actionBtnStyle('selected')} aria-label="Read selected text">
                  📝 Selected read
                </button>
                {serverAvailable && (
                  <button type="button" onClick={speakServerOnly} title="Play server audio" style={actionBtnStyle('server')} aria-label="Play server audio">
                    🎧 Server audio
                  </button>
                )}
              </>
            )}
          </>
        )}
        {state === 'server_loading' && (
          <>
            {!compact && (
              <span style={{ fontSize: 12, color: '#1d4ed8', fontWeight: 700 }}>
                Preparing {actionLabel(activeAction)}...
              </span>
            )}
            <button type="button" onClick={stop} title="Stop" style={compact ? compactControlBtnStyle('#991b1b') : btnStyle('#991b1b')}>⏹</button>
          </>
        )}
        {state === 'speaking' && (
          <>
            <button type="button" onClick={pauseFn} title="Pause (currently speaking)" style={filledBtn(actionColor(activeAction || 'read'))} aria-label="Speaking — click to pause">
              {compact ? '⏸' : `${actionLabel(activeAction)} · ⏸`}
            </button>
            <button type="button" onClick={stop} title="Stop" style={compact ? compactControlBtnStyle('#991b1b') : btnStyle('#991b1b')}>⏹</button>
          </>
        )}
        {state === 'paused' && (
          <>
            <button type="button" onClick={resumeFn} title="Resume" style={filledBtn(actionColor(activeAction || 'read'))}>{compact ? '▶' : `${actionLabel(activeAction)} · ▶ Resume`}</button>
            <button type="button" onClick={stop} title="Stop" style={compact ? compactControlBtnStyle('#991b1b') : btnStyle('#991b1b')}>⏹</button>
          </>
        )}
        {/* Live "reading word" pill — shows the active word as text so the
            user knows EXACTLY which word is being read RIGHT NOW. Works
            even on browsers without CSS Highlight API support. */}
        {(state === 'speaking' || state === 'paused') && activeIdx >= 0 && spans[activeIdx] && (
          <span
            aria-live="polite"
            title="Currently reading"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 10px',
              borderRadius: 999,
              background: '#facc15',
              color: '#000',
              border: '1px solid #ca8a04',
              fontSize: 13,
              fontWeight: 700,
              maxWidth: compact ? 200 : 360,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              boxShadow: '0 0 0 2px rgba(250, 204, 21, 0.35)',
            }}
          >
            🟡 {spans[activeIdx].word}
          </span>
        )}
        {compact && (
          <details ref={compactMenuRef} style={{ position: 'relative' }}>
            <summary
              title="Audio options"
              style={{
                ...compactControlBtnStyle('#6b7280'),
                listStyle: 'none',
                userSelect: 'none',
                cursor: 'pointer',
              }}
            >
              ⚙
            </summary>
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: 34,
                zIndex: 50,
                minWidth: 220,
                padding: 10,
                borderRadius: 10,
                background: '#fff',
                border: '1px solid #d1d5db',
                boxShadow: '0 10px 24px rgba(0,0,0,0.14)',
                display: 'grid',
                gap: 8,
              }}
            >
              <button type="button" onClick={speakSelected} title="Read selected text" style={btnStyle('#7c3aed')} aria-label="Read selected text">
                📝 Selected read
              </button>
              {serverAvailable && (
                <button type="button" onClick={speakServerOnly} title="Play server audio" style={btnStyle('#0f766e')} aria-label="Play server audio">
                  🎧 Server audio
                </button>
              )}
              {englishVoices.length > 1 && (
                <select
                  value={voiceName}
                  onChange={(e) => setVoiceName(e.target.value)}
                  style={{ ...selectStyle(), maxWidth: '100%' }}
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
              <select
                value={String(rate)}
                onChange={(e) => {
                  setRate(Number(e.target.value));
                  closeCompactMenu();
                }}
                style={{ ...selectStyle(), maxWidth: '100%' }}
                title="Speech rate (Shift+Space when speaking)"
              >
                <option value="0.5">0.5×</option>
                <option value="0.75">0.75×</option>
                <option value="1">1×</option>
                <option value="1.5">1.5×</option>
                <option value="2">2×</option>
              </select>
            </div>
          </details>
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
      {compact && (
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {statusLabel ? (
            <div
              aria-live="polite"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 8px',
                borderRadius: 999,
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
                color: '#1d4ed8',
                fontSize: 11,
                fontWeight: 700,
                maxWidth: 220,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: state === 'paused' ? '#f59e0b' : '#2563eb',
                  boxShadow: state === 'paused' ? '0 0 0 0 rgba(245, 158, 11, 0.45)' : '0 0 0 0 rgba(37, 99, 235, 0.45)',
                  animation: state === 'paused' ? 'documind-audio-pulse 1.4s ease-out infinite' : 'documind-audio-pulse 1.2s ease-out infinite',
                }}
              />
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{statusLabel}</span>
            </div>
          ) : serverAvailable ? (
            <div style={{ fontSize: 11, color: '#6b7280', maxWidth: 220 }}>
              Server voice ready{serverVoice ? `: ${serverVoice}` : ''}.
            </div>
          ) : null}
        </div>
      )}
      {!compact && (
        <>
        {statusLabel && (
          <div
            aria-live="polite"
            style={{
              marginTop: 8,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '4px 10px',
              borderRadius: 999,
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              color: '#1d4ed8',
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: state === 'paused' ? '#f59e0b' : '#2563eb',
                boxShadow: state === 'paused' ? '0 0 0 0 rgba(245, 158, 11, 0.45)' : '0 0 0 0 rgba(37, 99, 235, 0.45)',
                animation: state === 'paused' ? 'documind-audio-pulse 1.4s ease-out infinite' : 'documind-audio-pulse 1.2s ease-out infinite',
              }}
            />
            <span>{statusLabel}</span>
          </div>
        )}
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
            padding: 8,
            background: '#fafaf9',
            borderLeft: '3px solid #1e3a8a',
            borderRadius: 4,
            color: '#000',
            fontSize: 12,
            lineHeight: 1.55,
            maxHeight: 120,
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
      {serverError ? (
        <div
          role="alert"
          style={{
            marginTop: 8,
            padding: '10px 12px',
            background: '#fef2f2',
            border: '2px solid #dc2626',
            borderRadius: 8,
            fontSize: 13,
            lineHeight: 1.5,
            color: '#7f1d1d',
            fontWeight: 500,
            maxWidth: compact ? 360 : 'none',
            boxShadow: '0 2px 4px rgba(220, 38, 38, 0.15)',
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>⚠ Speaker error</div>
          {serverError}
        </div>
      ) : null}
      {/* CSS Highlight rules — applied to the actual page text via
          Range objects registered in the activeIdx effect. No DOM
          mutation, no floating overlay. */}
      <style>{`
        @keyframes documind-audio-pulse {
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.45); }
          70% { transform: scale(1.08); box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
        }
        ::highlight(speech-active) {
          background-color: #facc15;
          color: #000;
          font-weight: 700;
          text-shadow: 0 0 0.5px #000;
        }
        ::highlight(speech-sentence) {
          text-decoration: underline 2px #f59e0b;
          text-underline-offset: 3px;
        }
      `}</style>
    </div>
  );
}
