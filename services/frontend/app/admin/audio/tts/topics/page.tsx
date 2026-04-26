'use client';

/**
 * Audio / TTS topics catalog with read-aloud highlighting.
 *
 * Single-source-of-truth catalog covering the 4 categories the user
 * asked for: Scenarios, Architecture, Integration, Monitoring.
 * Each topic has a 🔊 button that uses the browser SpeechSynthesis
 * API to read the text aloud with per-word yellow highlighting.
 */

import Link from 'next/link';
import SpeechReader from '../../../../../components/SpeechReader';

type Topic = {
  name: string;
  blurb: string;
  detail: string;
  href?: string;
};

type Category = {
  heading: string;
  intro: string;
  topics: Topic[];
};

const CATEGORIES: Category[] = [
  {
    heading: 'Scenarios',
    intro: 'When and where audio + TTS earns its weight.',
    topics: [
      {
        name: 'Hear the answer (text-first chatbot)',
        blurb: 'Per-message Hear answer button calls /api/v1/tts and streams audio back.',
        detail: 'A user asks a question in text, gets a text answer, then optionally clicks a Hear answer button on the response. The frontend posts the answer text plus voice settings to /api/v1/tts. The backend returns an audio stream which the browser plays via a mini player. This is the safest first step because it adds audio without changing the chat path.',
      },
      {
        name: 'Voice-first interaction (mic round-trip)',
        blurb: 'Mic captures audio; ASR transcribes; LLM answers; TTS reads response.',
        detail: 'The user holds a mic button in the browser and speaks. The browser uploads audio to /api/v1/voice/chat. The backend runs automatic speech recognition to get a transcript, sends it to the chat service which calls Ollama to generate an answer, then runs the answer text through TTS. The full payload returned is transcript plus answer plus audio stream. Add this only after the text-first TTS path is stable.',
      },
      {
        name: 'Read the document or chunk',
        blurb: 'Read aloud arbitrary retrieved chunks for accessibility or hands-free review.',
        detail: 'On a document detail page or any retrieved chunk, a small audio button reads the chunk aloud. Useful for accessibility, hands-free review, or driving. The browser SpeechSynthesis API handles this for free with no backend cost; for premium voice the same button can fall back to /api/v1/tts.',
      },
      {
        name: 'Audio summary of search results',
        blurb: 'Top-K chunks summarized to a single audio brief.',
        detail: 'After a hybrid retrieval call returns top chunks, a separate summary endpoint produces a short text summary which is then spoken. Useful for end-of-day briefings or dashboard narration.',
      },
      {
        name: 'Read the audit trail or alert briefing',
        blurb: 'Operators on call hear the alert summary while their hands are busy.',
        detail: 'Pages an oncall engineer with a spoken summary instead of a wall of text. Reduces cognitive load during incidents. Latency is critical here so cache aggressively.',
      },
      {
        name: 'Compliance read-back',
        blurb: 'Read back terms or policies the user must acknowledge.',
        detail: 'Some regulated flows require the system to read terms aloud and capture an audio acknowledgement. Pairs with a voice ASR step to record the user saying I agree. Audit chain captures both audio blobs and transcripts.',
      },
    ],
  },
  {
    heading: 'Architecture',
    intro: 'How audio + TTS plug into the existing chatbot stack.',
    topics: [
      {
        name: 'Provider-agnostic TTSClient abstraction',
        blurb: 'libs/py wrapper around Riva / ElevenLabs / OpenAI audio with a stable interface.',
        detail: 'A TTSClient class takes text plus voice plus format and returns an audio stream or blob. The concrete provider is selected at deploy time via config. This keeps the rest of the codebase unchanged when we swap from one provider to another, and lets us run multiple providers per tenant tier.',
      },
      {
        name: 'POST /api/v1/tts endpoint',
        blurb: 'Best first step. Text in, audio out.',
        detail: 'The simplest backend contract. Accepts text plus voice plus format plus timeout. Returns audio as a stream or blob. Frontend calls this from the Hear answer button. No state, no session, fully cacheable on identical inputs.',
      },
      {
        name: 'POST /api/v1/chat/audio endpoint',
        blurb: 'Combined text answer plus read-aloud in one request.',
        detail: 'A chat endpoint that returns the answer text and optionally the audio blob in one response. Useful when the frontend wants to stream both side by side. Slightly tighter coupling than the pure TTS endpoint but reduces round trips.',
      },
      {
        name: 'POST /api/v1/voice/chat endpoint',
        blurb: 'Full mic-to-speaker round trip.',
        detail: 'Accepts audio plus session metadata. Internally chains automatic speech recognition to get a transcript, calls the chat service for an answer, then runs TTS to produce reply audio. Returns transcript plus answer plus audio. Add this only after text-first TTS is stable and observable.',
      },
      {
        name: 'Frontend mini audio player',
        blurb: 'Per-message inline player with play, pause, scrub, mute, speed.',
        detail: 'Lightweight component embedded in each chat message. Minimal controls: play, pause, scrub, mute, speed. Tracks state per message id. Falls back to the browser SpeechSynthesis API if the backend TTS is unavailable so the page is never blocked.',
      },
      {
        name: 'Browser SpeechSynthesis fallback',
        blurb: 'Free read-aloud baseline when backend TTS is down or budget is tight.',
        detail: 'Every modern browser ships a SpeechSynthesis API with built-in voices. We use it as the always-available baseline. Quality is lower than ElevenLabs or Riva but cost is zero and latency is sub-100ms. The same button can swap to backend TTS for premium voices.',
      },
      {
        name: 'Per-word highlight via onboundary',
        blurb: 'Highlights each word as the engine reads it. Accessibility win.',
        detail: 'The SpeechSynthesisUtterance.onboundary event fires per word with a charIndex. We tokenize the text once, map charIndex to a span, and apply a yellow background to the active span. Auto-scroll keeps the active word in view. The same trick works with backend TTS if the API returns word timing information.',
      },
    ],
  },
  {
    heading: 'Integration',
    intro: 'Picking and integrating providers without lock-in.',
    topics: [
      {
        name: 'NVIDIA Riva (private GPU TTS + ASR)',
        blurb: 'Best fit for private GPU-backed speech path. Enterprise, on-prem, GPU.',
        detail: 'Riva is the strongest option for private deployments. Runs on GPU infrastructure we already operate. Good for regulated tenants who cannot send audio to a SaaS endpoint. Higher operational footprint but full data control.',
      },
      {
        name: 'ElevenLabs (premium voice)',
        blurb: 'Easiest path to premium voice quality.',
        detail: 'ElevenLabs offers the most realistic voices on the market. Best for high-touch user-facing tiers where voice quality matters. SaaS only so cannot run in air-gapped environments. Cost per second of audio.',
      },
      {
        name: 'Cartesia (low-latency realtime)',
        blurb: 'Strong if realtime conversational voice UX matters.',
        detail: 'Cartesia is optimized for low-latency streaming TTS. First-byte latency under 100ms makes it suitable for conversational agents where the model talks back interactively.',
      },
      {
        name: 'OpenAI audio (unified managed stack)',
        blurb: 'One API family for ASR plus TTS plus chat.',
        detail: 'OpenAI offers ASR (Whisper API), TTS, and chat under one credential. Lowest integration cost when staying inside the OpenAI ecosystem. Vendor lock is the main tradeoff.',
      },
      {
        name: 'Azure Speech (compliance fit)',
        blurb: 'Good fit when Azure governance and compliance certs matter.',
        detail: 'Azure Speech ships with the broader compliance certifications enterprises require. Plug-and-play if the org is already on Azure. Less competitive on raw voice quality vs ElevenLabs.',
      },
      {
        name: 'Google Cloud TTS (managed cloud)',
        blurb: 'Stable managed cloud voice service.',
        detail: 'Mature managed TTS. Wide language coverage. Good for global products. Voice quality solid but not best-in-class.',
      },
      {
        name: 'Browser-only TTS (zero-dependency baseline)',
        blurb: 'Free, fastest MVP. No backend needed.',
        detail: 'Use the browser SpeechSynthesis API directly. Zero cost, zero backend, sub-100ms latency. Quality varies by browser and OS. Best for accessibility, MVP, and offline scenarios.',
      },
    ],
  },
  {
    heading: 'Monitoring',
    intro: 'What to log and watch in production.',
    topics: [
      {
        name: 'First-byte latency (TTFB) per provider',
        blurb: 'How fast does audio start playing after the user clicks Hear answer?',
        detail: 'Track TTFB per provider per voice. Below 500ms feels instant. Above 1s feels broken. Surface in a dashboard so we can swap providers when one degrades.',
      },
      {
        name: 'Audio cost per second per tenant',
        blurb: 'Budget enforcement. Tied to the Token CB pattern.',
        detail: 'Each provider charges per second of synthesized audio. Track cost per tenant and enforce per-tenant budgets via the same circuit-breaker pattern used for LLM tokens. Block or fall back to browser TTS on hard breach.',
      },
      {
        name: 'Cache hit rate on identical inputs',
        blurb: 'Same answer text? Same audio. Cache aggressively.',
        detail: 'Hash the (text, voice, format, language) tuple and cache the audio blob in object storage with a TTL. Hit rate above 60% on repeated FAQ answers is realistic and meaningfully reduces cost.',
      },
      {
        name: 'Quality sampling and user thumbs',
        blurb: 'Sample 1% of audio outputs for quality review; capture user thumbs on play UI.',
        detail: 'Quality is subjective. Capture thumbs up or down on the audio player UI. Sample 1% of audio for human review. Feed both signals into provider-quality scoring.',
      },
      {
        name: 'Per-provider error rate and breaker state',
        blurb: 'Each provider gets its own circuit breaker. Open on N consecutive failures.',
        detail: 'Riva, ElevenLabs, OpenAI audio each get a transport-level circuit breaker. On N consecutive failures the breaker opens and we fall back to the next provider in the priority list, or finally to the browser SpeechSynthesis baseline.',
      },
      {
        name: 'Audio audit trail per tenant',
        blurb: 'Per-request logging: text, voice, provider, latency, cost, audio hash.',
        detail: 'Hash-chained audit row per audio synthesis call. Captures input text length, voice id, provider, TTFB, total latency, cost, and a hash of the resulting audio blob. Required for compliance and cost-attribution conversations.',
      },
      {
        name: 'PII redaction before synthesis',
        blurb: 'Run Presidio over text before sending to a SaaS TTS provider.',
        detail: 'Audio cannot be redacted post-hoc. Run Presidio over outgoing text and replace masked spans with neutral placeholders before the synthesis call. The audit row records both the original (encrypted) and redacted text.',
      },
    ],
  },
];

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

export default function AudioTtsTopicsPage() {
  const total = CATEGORIES.flatMap((c) => c.topics).length;
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">🔊 Audio / TTS — Topics</h1>
        <p className="design-areas-sub">
          Single-source catalog covering Scenarios, Architecture, Integration, and
          Monitoring for adding audio + TTS to the chatbot. Each topic has a
          <strong> 🔊 Read</strong> button — click it to hear the topic read aloud
          with the active word highlighted in yellow.
        </p>
        <p className="design-areas-sub" style={{ fontStyle: 'italic' }}>
          Engine: browser <code>SpeechSynthesis</code> API (free, offline-capable).
          For premium voice quality see the
          <Link href="/admin/audio/tts" style={{ color: '#1e3a8a' }}> architecture page</Link>{' '}
          for the <code>/api/v1/tts</code> backend contract.
        </p>
        <div style={{ marginTop: 12, fontSize: 14, color: '#000' }}>
          <strong>Total topics:</strong> {total}
        </div>
        <nav className="scen-toc" style={{ marginTop: 16 }}>
          {CATEGORIES.map((c) => (
            <a key={c.heading} href={`#${slugify(c.heading)}`} className="scen-toc-link">
              {c.heading} <span className="scen-toc-count">({c.topics.length})</span>
            </a>
          ))}
        </nav>
      </header>

      {CATEGORIES.map((cat) => (
        <section key={cat.heading} id={slugify(cat.heading)} className="design-areas-group">
          <h2 className="design-areas-group-title">{cat.heading}</h2>
          <p style={{ color: '#000', marginBottom: 12, fontStyle: 'italic' }}>{cat.intro}</p>
          <ul style={{ paddingLeft: 18, color: '#000' }}>
            {cat.topics.map((t) => {
              const fullText = `${t.name}. ${t.blurb} ${t.detail}`;
              return (
                <li key={t.name} style={{ marginBottom: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <strong style={{ color: '#1e3a8a' }}>{t.name}</strong>
                      <div style={{ fontSize: 14, color: '#000', marginTop: 4 }}>{t.blurb}</div>
                    </div>
                    <div style={{ flexShrink: 0 }}>
                      <SpeechReader text={fullText} compact />
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: '#374151', marginTop: 6 }}>{t.detail}</div>
                  <div style={{ marginTop: 8 }}>
                    <SpeechReader text={fullText} />
                  </div>
                  {t.href ? (
                    <div style={{ marginTop: 6 }}>
                      <Link href={t.href} style={{ color: '#1d4ed8', fontSize: 13, fontWeight: 600 }}>
                        Open deeper context →
                      </Link>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
