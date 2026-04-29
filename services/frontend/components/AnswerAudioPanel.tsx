'use client';

import { useEffect, useRef, useState } from 'react';
import SpeechReader from './SpeechReader';

type Props = {
  text: string;
};

type TtsCapabilities = {
  available: boolean;
  provider: string;
  fallback: string;
  model: string;
  voice: string;
  providers?: string[];
  failover_chain?: string[];
  voices?: string[];
}

type TtsAudit = {
  auditId?: string;
  correlationId: string;
  provider: string;
  model: string;
  voice: string;
  chars: number;
  failover: string;
  status: 'browser_only' | 'premium_ready' | 'premium_generated';
};

const VOICE_KEY = 'documind.server_tts.voice';
const VOICE_PREVIEW_TEXT = 'Hello from DocuMind. This is a voice preview.';

const VOICE_FAMILY_LABELS: Record<string, string> = {
  af: 'American Female',
  am: 'American Male',
  bf: 'British Female',
  bm: 'British Male',
  ef: 'Spanish Female',
  em: 'Spanish Male',
  ff: 'French Female',
  hf: 'Hindi Female',
  hm: 'Hindi Male',
  if: 'Italian Female',
  im: 'Italian Male',
  jf: 'Japanese Female',
  jm: 'Japanese Male',
  pf: 'Portuguese Female',
  pm: 'Portuguese Male',
  zf: 'Chinese Female',
  zm: 'Chinese Male',
};

function groupedVoices(voices: string[]) {
  const grouped = new Map<string, string[]>();
  for (const voice of voices) {
    const family = voice.split('_')[0] || 'other';
    const bucket = grouped.get(family) || [];
    bucket.push(voice);
    grouped.set(family, bucket);
  }
  return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
}

export default function AnswerAudioPanel({ text }: Props) {
  const [caps, setCaps] = useState<TtsCapabilities | null>(null);
  const [selectedVoice, setSelectedVoice] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audit, setAudit] = useState<TtsAudit | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const voiceGroups = caps?.voices?.length ? groupedVoices(caps.voices) : [];

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const saved = window.localStorage.getItem(VOICE_KEY);
    if (saved) setSelectedVoice(saved);
  }, []);

  useEffect(() => {
    let mounted = true;
    fetch('/api/v1/tts')
      .then(async (resp) => {
        if (!resp.ok) return null;
        return (await resp.json()) as TtsCapabilities;
      })
      .then((data) => {
        if (mounted && data) {
          setCaps(data);
          setSelectedVoice((current) => current || data.voice || '');
          setAudit({
            correlationId: '',
            provider: data.provider,
            model: data.model,
            voice: data.voice,
            chars: text.length,
            failover: data.fallback,
            status: data.available ? 'premium_ready' : 'browser_only',
          });
        }
      })
      .catch(() => {
        // Leave capabilities unset; browser reader still works.
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !selectedVoice) return;
    window.localStorage.setItem(VOICE_KEY, selectedVoice);
  }, [selectedVoice]);

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  async function synthesizeAudio(kind: 'answer' | 'preview') {
    const sourceText = kind === 'preview' ? VOICE_PREVIEW_TEXT : text;
    if (!sourceText.trim()) return;
    if (kind === 'preview') setPreviewLoading(true);
    else setLoading(true);
    setError(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    try {
      const resp = await fetch('/api/v1/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sourceText, format: 'mp3', voice: selectedVoice || caps?.voice || undefined }),
      });
      if (!resp.ok) {
        let detail = `TTS request failed with status ${resp.status}.`;
        try {
          const envelope = await resp.json();
          detail = envelope.detail || detail;
        } catch {
          // Keep generic detail.
        }
        throw new Error(detail);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
      setAudit({
        auditId: resp.headers.get('X-TTS-Audit-Id') || '',
        correlationId: resp.headers.get('X-Correlation-ID') || '',
        provider: resp.headers.get('X-TTS-Provider') || caps?.provider || 'openai',
        model: resp.headers.get('X-TTS-Model') || caps?.model || '',
        voice: resp.headers.get('X-TTS-Voice') || caps?.voice || '',
        chars: Number(resp.headers.get('X-TTS-Input-Chars') || sourceText.length),
        failover: resp.headers.get('X-TTS-Failover-Chain') || caps?.fallback || 'browser_speech_synthesis',
        status: 'premium_generated',
      });
      queueMicrotask(() => {
        audioRef.current?.play().catch(() => {
          // User can click play manually.
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (kind === 'preview') setPreviewLoading(false);
      else setLoading(false);
    }
  }

  async function synthesizePremium() {
    return synthesizeAudio('answer');
  }

  async function previewVoice() {
    return synthesizeAudio('preview');
  }

  return (
    <div className="surface-muted" style={{ marginTop: 12 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <strong>Read answer</strong>
          <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', marginTop: 4 }}>
            Browser read-aloud gives word highlighting now. Server audio playback appears when an open-source or hosted TTS provider is configured.
          </div>
          {typeof window !== 'undefined' ? (
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', marginTop: 4 }}>
              Saved settings auto-restore across pages.
            </div>
          ) : null}
          {caps?.failover_chain?.length ? (
            <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)', marginTop: 4 }}>
              Failover chain: {caps.failover_chain.join(' -> ')}
            </div>
          ) : null}
          {!caps?.available ? (
            <div style={{ fontSize: 'var(--font-size-sm)', color: '#991b1b', marginTop: 4 }}>
              Server audio is currently disabled in this environment. Configure Piper or another provider to enable backend-generated audio.
            </div>
          ) : null}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <SpeechReader text={text} compact />
          {caps?.available && caps.voices?.length ? (
            <select
              value={selectedVoice || caps.voice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              style={{
                padding: '6px 10px',
                borderRadius: 8,
                border: '1px solid var(--border-color)',
                background: '#fff',
                color: 'var(--text-primary)',
                minWidth: 170,
              }}
              title="Server TTS voice"
            >
              {voiceGroups.map(([family, voices]) => (
                <optgroup
                  key={family}
                  label={VOICE_FAMILY_LABELS[family] || family.toUpperCase()}
                >
                  {voices.map((voice) => (
                    <option key={voice} value={voice}>
                      {voice}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          ) : null}
          {caps?.available && caps.voices?.length ? (
            <button
              type="button"
              className="btn"
              onClick={previewVoice}
              disabled={previewLoading || loading}
              title={`Preview voice ${selectedVoice || caps.voice}`}
            >
              {previewLoading ? 'Previewing...' : 'Preview voice'}
            </button>
          ) : null}
          {caps?.available ? (
            <button
              type="button"
              className="btn"
              onClick={synthesizePremium}
              disabled={loading}
              title={`Generate premium audio via ${caps.provider}`}
            >
              {loading ? 'Generating audio...' : `Server audio${caps.provider ? ` (${caps.provider})` : ''}`}
            </button>
          ) : (
            <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
              Premium TTS unavailable
            </span>
          )}
        </div>
      </div>

      {audioUrl ? (
        <div style={{ marginTop: 12 }}>
          <audio ref={audioRef} controls src={audioUrl} style={{ width: '100%' }} />
        </div>
      ) : null}

      {audit ? (
        <details style={{ marginTop: 12, fontSize: 'var(--font-size-sm)' }}>
          <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Audio telemetry</summary>
          <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>
            provider {audit.provider} · model {audit.model || 'n/a'} · voice {audit.voice || 'n/a'} · chars {audit.chars} · mode {audit.status}
            {audit.correlationId ? ` · correlation ${audit.correlationId}` : ''}
            {audit.auditId ? ` · audit ${audit.auditId}` : ''}
          </div>
        </details>
      ) : null}

      {error ? (
        <div className="error" style={{ marginTop: 12 }}>
          {error}
        </div>
      ) : null}
    </div>
  );
}
