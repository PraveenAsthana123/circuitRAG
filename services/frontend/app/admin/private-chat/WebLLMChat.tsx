'use client';

/**
 * /admin/private-chat — WebLLM chat (100% in-browser inference).
 *
 * Privacy-first AI lane: model + tokens + state ALL stay in the
 * browser. Zero backend round-trip per inference. Useful for:
 *   - PII-safe summarization (HIPAA / GDPR / FINRA)
 *   - Air-gapped / offline / edge demos
 *   - Internal copilots where data must not leave the device
 *
 * Architecture:
 *   1. User clicks "Load model" → WebLLM downloads + WebGPU-compiles
 *      Llama-3.2-1B (~750 MB, cached in IndexedDB on subsequent loads)
 *   2. Engine ready → user sends message → token-stream back to UI
 *   3. Zero HTTP round-trip to any backend. No telemetry. No
 *      logging of user input. Drilled by
 *      drill_private_chat_webllm_page.py.
 *
 * Per CLAUDE.md §47 (architecture is first-class), §48 (this is the
 * Privacy lane in the explainability surface), §49 (compose with
 * /admin/llmops + /admin/local-models), §57.1 (production-grade-by-
 * default: WebGPU detection + user-gated model load + streaming).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

// MLCEngine types — import lazily inside the load callback so the
// page doesn't pay the WebLLM SDK cost on initial render.
type MLCEngineType = Awaited<
  ReturnType<typeof import('@mlc-ai/web-llm').CreateMLCEngine>
>;

type LoadStatus =
  | 'idle' // user hasn't clicked load yet
  | 'unsupported' // WebGPU missing
  | 'loading' // model downloading / compiling
  | 'ready' // engine created, ready to chat
  | 'generating' // mid-stream
  | 'error';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

const MODEL_ID = 'Llama-3.2-1B-Instruct-q4f32_1-MLC';
const MODEL_DESCRIPTION =
  'Meta Llama-3.2-1B Instruct, 4-bit quantized via MLC. ~750 MB. Cached in browser after first load.';

function detectWebGPU(): boolean {
  if (typeof navigator === 'undefined') return false;
  return 'gpu' in navigator;
}

export default function WebLLMChat() {
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [progress, setProgress] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const engineRef = useRef<MLCEngineType | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new content
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Detect WebGPU on mount
  useEffect(() => {
    if (!detectWebGPU()) {
      setStatus('unsupported');
    }
  }, []);

  const handleLoadModel = useCallback(async () => {
    if (status === 'loading' || status === 'ready' || status === 'generating') return;
    if (!detectWebGPU()) {
      setStatus('unsupported');
      return;
    }
    setStatus('loading');
    setProgress('Initializing WebLLM…');
    setError('');
    try {
      // Lazy import — WebLLM SDK is large; only pay the cost when the
      // user explicitly opts in by clicking the load button.
      const { CreateMLCEngine } = await import('@mlc-ai/web-llm');
      const engine = await CreateMLCEngine(MODEL_ID, {
        initProgressCallback: (report) => {
          setProgress(report.text || '');
        },
      });
      engineRef.current = engine;
      setStatus('ready');
      setProgress(`Model loaded: ${MODEL_ID}`);
    } catch (e: unknown) {
      const err = e as Error;
      setError(err.message || 'unknown error');
      setStatus('error');
    }
  }, [status]);

  const handleSend = useCallback(async () => {
    if (status !== 'ready') return;
    const userMsg = input.trim();
    if (!userMsg) return;
    const engine = engineRef.current;
    if (!engine) return;

    setInput('');
    setStatus('generating');
    const next: Message[] = [...messages, { role: 'user', content: userMsg }];
    setMessages([...next, { role: 'assistant', content: '' }]);

    try {
      const stream = await engine.chat.completions.create({
        messages: next.map((m) => ({ role: m.role, content: m.content })),
        stream: true,
        temperature: 0.7,
      });
      let assistantText = '';
      for await (const chunk of stream) {
        const delta = chunk.choices[0]?.delta?.content || '';
        if (!delta) continue;
        assistantText += delta;
        setMessages((prev) => {
          const out = [...prev];
          out[out.length - 1] = { role: 'assistant', content: assistantText };
          return out;
        });
      }
      setStatus('ready');
    } catch (e: unknown) {
      const err = e as Error;
      setError(err.message || 'generation failed');
      setStatus('error');
    }
  }, [input, messages, status]);

  const handleReset = useCallback(() => {
    setMessages([]);
    setError('');
    if (status === 'error' || status === 'generating') {
      setStatus(engineRef.current ? 'ready' : 'idle');
    }
  }, [status]);

  const canSend =
    status === 'ready' && input.trim().length > 0 && messages.every((m) => m.content !== '' || m.role === 'user');

  return (
    <div style={{ maxWidth: 880, margin: '0 auto' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ margin: '0 0 6px 0' }}>Private chat — in-browser inference</h1>
        <p style={{ color: '#555', margin: 0 }}>
          {MODEL_DESCRIPTION}
        </p>
      </div>

      <div
        role="region"
        aria-label="privacy notice"
        style={{
          background: '#e8f3ff',
          border: '1px solid #c4dcfb',
          padding: 12,
          borderRadius: 8,
          marginBottom: 16,
          fontSize: 13,
          lineHeight: 1.5,
        }}
      >
        <strong>Privacy contract:</strong> 100% in-browser inference. The model
        runs in your browser via WebGPU. Your input + the model&rsquo;s replies
        never leave this device. Zero HTTP round-trip to any backend. No
        telemetry. No logging. Locked by{' '}
        <code>mcp/tests/drill_private_chat_webllm_page.py</code>.
      </div>

      {status === 'unsupported' && (
        <div
          style={{
            background: '#fbe0e0',
            border: '1px solid #f0a8a8',
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
          }}
        >
          <strong>WebGPU not available in this browser.</strong> Chrome 113+,
          Edge 113+, or Safari 18+ on a machine with a supported GPU.
        </div>
      )}

      {status === 'idle' && (
        <button
          onClick={handleLoadModel}
          style={{
            padding: '10px 18px',
            fontSize: 14,
            background: '#1a5fb4',
            color: '#fff',
            border: 0,
            borderRadius: 6,
            cursor: 'pointer',
            marginBottom: 16,
          }}
        >
          Load model (~750 MB, one-time download)
        </button>
      )}

      {status === 'loading' && (
        <div
          style={{
            padding: 12,
            background: '#fff7d8',
            border: '1px solid #ead37a',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          <strong>Loading…</strong> {progress}
        </div>
      )}

      {error && (
        <div
          style={{
            padding: 12,
            background: '#fbe0e0',
            border: '1px solid #f0a8a8',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
            color: '#a52424',
          }}
        >
          Error: {error}
        </div>
      )}

      {(status === 'ready' || status === 'generating') && (
        <>
          <div
            ref={scrollRef}
            style={{
              border: '1px solid #e3e3e3',
              borderRadius: 8,
              padding: 12,
              minHeight: 240,
              maxHeight: 480,
              overflowY: 'auto',
              background: '#fff',
              marginBottom: 12,
            }}
          >
            {messages.length === 0 ? (
              <em style={{ color: '#888' }}>
                Send a message to start. Everything stays in your browser.
              </em>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  style={{
                    marginBottom: 12,
                    display: 'flex',
                    flexDirection: 'column',
                  }}
                >
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: m.role === 'user' ? '#1a5fb4' : '#1f7a3a',
                      letterSpacing: 0.5,
                      textTransform: 'uppercase',
                      marginBottom: 2,
                    }}
                  >
                    {m.role}
                  </span>
                  <span style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>
                    {m.content}
                    {status === 'generating' && i === messages.length - 1 && (
                      <span style={{ color: '#666' }}> ▍</span>
                    )}
                  </span>
                </div>
              ))
            )}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Send a message… (Ctrl/⌘+Enter to send)"
              rows={3}
              disabled={status !== 'ready'}
              style={{
                flex: 1,
                padding: 10,
                fontSize: 14,
                fontFamily: 'inherit',
                border: '1px solid #ccc',
                borderRadius: 6,
                resize: 'vertical',
              }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <button
                onClick={() => void handleSend()}
                disabled={!canSend}
                style={{
                  padding: '8px 14px',
                  fontSize: 13,
                  background: canSend ? '#1a5fb4' : '#aaa',
                  color: '#fff',
                  border: 0,
                  borderRadius: 6,
                  cursor: canSend ? 'pointer' : 'not-allowed',
                }}
              >
                Send
              </button>
              <button
                onClick={handleReset}
                disabled={status === 'generating' || messages.length === 0}
                style={{
                  padding: '8px 14px',
                  fontSize: 13,
                  background: '#fff',
                  color: '#333',
                  border: '1px solid #ccc',
                  borderRadius: 6,
                  cursor:
                    status === 'generating' || messages.length === 0
                      ? 'not-allowed'
                      : 'pointer',
                }}
              >
                Reset
              </button>
            </div>
          </div>
        </>
      )}

      <div
        style={{
          marginTop: 24,
          fontSize: 12,
          color: '#666',
          paddingTop: 12,
          borderTop: '1px solid #eee',
        }}
      >
        Composes with: <a href="/admin/llmops">/admin/llmops</a> ·{' '}
        <a href="/admin/local-models">/admin/local-models</a> ·{' '}
        <a href="/admin/explainability/deep">/admin/explainability/deep</a>.
        Runbook: <code>docs/runbooks/webllm.md</code>.
      </div>
    </div>
  );
}
