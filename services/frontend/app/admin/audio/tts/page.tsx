import Link from 'next/link';
import Mermaid from '../../../../components/Mermaid';
import AnswerAudioPanel from '../../../../components/AnswerAudioPanel';
import SpeechReader from '../../../../components/SpeechReader';

export const metadata = { title: 'Audio / TTS for chatbot — DocuMind' };

const PROVIDERS = [
  ['Ollama', 'LLM text generation', 'local or on-prem text generation'],
  ['Kokoro ONNX', 'local neural TTS', 'you want higher-quality open-source local voice'],
  ['Piper (open source)', 'local or self-hosted TTS', 'you want open-source voice without paid APIs'],
  ['NVIDIA Riva', 'TTS and ASR', 'enterprise, GPU-backed, private deployment'],
  ['ElevenLabs', 'high-quality TTS', 'premium voice quality matters most'],
  ['Cartesia', 'realtime TTS', 'low-latency conversational audio matters'],
  ['OpenAI audio', 'unified managed audio stack', 'one API family is preferred'],
  ['Azure Speech', 'enterprise speech platform', 'Azure/compliance/governance fit matters'],
  ['Google Cloud TTS', 'managed cloud TTS', 'stable managed cloud voice service'],
] as const;

const REPO_FIT = [
  ['Kokoro ONNX', 'very high', 'best current local neural voice quality in this repo'],
  ['Piper', 'high', 'best current open-source fit for local or self-hosted backend speech'],
  ['NVIDIA Riva', 'high', 'strongest fit for private GPU-backed speech path'],
  ['ElevenLabs', 'high', 'easiest way to get premium voice quality'],
  ['Cartesia', 'medium-high', 'strong if realtime voice UX matters'],
  ['OpenAI audio', 'medium-high', 'good unified managed API path'],
  ['browser TTS only', 'medium', 'fastest MVP, weakest control/quality'],
] as const;

const FLOW = `flowchart TD
  U[User text or voice] --> A[API]
  A --> L[LLM generates answer text]
  L --> T[TTS converts answer to audio]
  T --> B[Browser plays audio]`;

const VOICE_FLOW = `flowchart TD
  M[Mic audio] --> S[ASR]
  S --> L[LLM]
  L --> T[TTS]
  T --> P[Speaker / browser player]`;

const API_FLOW = `flowchart TD
  U[User clicks Hear answer] --> F[Frontend mini-player]
  F --> A[/api/v1/tts]
  A --> C[TTSClient abstraction]
  C --> P[TTS provider]
  P --> R[Audio stream or blob]
  R --> B[Browser audio playback]`;

const FULL_VOICE_SEQUENCE = `sequenceDiagram
  autonumber
  participant B as Browser
  participant V as Voice API
  participant A as ASR
  participant C as Chat service
  participant O as Ollama
  participant T as TTS
  B->>V: mic audio / session metadata
  V->>A: transcribe audio
  A-->>V: transcript
  V->>C: transcript + session context
  C->>O: generate answer text
  O-->>C: answer
  C-->>V: answer text
  V->>T: synthesize speech
  T-->>V: audio stream
  V-->>B: transcript + answer + audio`;

const LIVE_READER_TEXT = [
  'Audio and TTS for chatbot.',
  'Keep Ollama for answer generation.',
  'Use Kokoro O N N X for a higher quality open source local text to speech path.',
  'Use Piper for an open source local text to speech path.',
  'Use a dedicated speech engine such as NVIDIA Riva, ElevenLabs, Cartesia, or OpenAI audio for text to speech.',
  'Start with a text-first Hear answer action.',
  'Expose POST slash api slash v1 slash tts.',
  'Use browser speech synthesis as the zero-cost fallback.',
  'For full voice, add ASR to chat to TTS orchestration with breaker, timeout, and fallback.',
].join(' ');

const MISSING_ITEMS = [
  ['Provider-specific adapters', 'The live backend now supports Piper and OpenAI ordering, but dedicated adapters for Riva, ElevenLabs, or Cartesia are still missing.'],
  ['Word timing from backend TTS', 'Browser highlighting works now; premium providers need word timestamps for exact sync.'],
  ['Per-user audio preferences', 'Voice, provider, and playback settings persist locally, not yet per authenticated user or tenant.'],
  ['Provider fallback chain tuning', 'The backend supports ordered fallback now, but provider health weighting and circuit-breaker integration are still missing.'],
  ['Audio cache + audit', 'Need caching, cost tracking, and hash-chained audit records for enterprise use.'],
] as const;

export default function AudioTtsPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Audio / TTS for chatbot</h1>
          <p className="page-subtitle">
            Provider comparison, architecture choices, and the best integration path
            for adding speech output to the current chatbot stack.
          </p>
        </div>
      </div>

      <div className="card">
        <strong>Related</strong>
        <p style={{ marginTop: 8 }}>
          <Link href="/admin/audio/tts/topics" style={{ color: '#1e3a8a' }}>
            /admin/audio/tts/topics
          </Link>
          {' · '}
          <Link href="/admin/system-design/chatbot" style={{ color: '#1e3a8a' }}>
            /admin/system-design/chatbot
          </Link>
          {' · '}
          <Link href="/tools/ollama-vllm" style={{ color: '#1e3a8a' }}>
            /tools/ollama-vllm
          </Link>
          {' · '}
          <Link href="/admin/lang-family/rag" style={{ color: '#1e3a8a' }}>
            /admin/lang-family/rag
          </Link>
        </p>
      </div>

      <div className="card">
        <strong>Advanced live read-aloud</strong>
        <p style={{ marginTop: 8 }}>
          This page now mounts the same advanced reader used on the topic catalog:
          browser speech synthesis, selectable voices, speed control, pause/resume,
          and per-word yellow highlighting while text is read.
        </p>
        <div style={{ marginTop: 12, marginBottom: 10 }}>
          <SpeechReader text={LIVE_READER_TEXT} compact />
        </div>
        <SpeechReader text={LIVE_READER_TEXT} />
        <div style={{ marginTop: 16 }}>
          <AnswerAudioPanel text={LIVE_READER_TEXT} />
        </div>
      </div>

      <div className="card">
        <strong>Core flow</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={FLOW} />
        </div>
      </div>

      <div className="card">
        <strong>Voice round-trip flow</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={VOICE_FLOW} />
        </div>
      </div>

      <div className="card">
        <strong>Backend API contract</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={API_FLOW} />
        </div>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Endpoint</th>
              <th style={{ width: 220 }}>Purpose</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <code>POST /api/v1/tts</code>
              </td>
              <td>text -&gt; speech</td>
              <td>Best first step. Return audio stream or blob with voice, format, and timeout controls.</td>
            </tr>
            <tr>
              <td>
                <code>POST /api/v1/chat/audio</code>
              </td>
              <td>text chat + read-aloud</td>
              <td>Good if answer text and audio should come from one request path.</td>
            </tr>
            <tr>
              <td>
                <code>POST /api/v1/voice/chat</code>
              </td>
              <td>full microphone round-trip</td>
              <td>ASR -&gt; chat -&gt; TTS. Add only after the text-first TTS path is stable.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Provider roles</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Provider</th>
              <th style={{ width: 220 }}>Best role</th>
              <th>Best when</th>
            </tr>
          </thead>
          <tbody>
            {PROVIDERS.map(([name, role, when]) => (
              <tr key={name}>
                <td>
                  <code style={{ color: '#b91c1c', fontWeight: 700 }}>{name}</code>
                </td>
                <td>{role}</td>
                <td>{when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Best fit for this repo</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 180 }}>Option</th>
              <th style={{ width: 120 }}>Fit</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {REPO_FIT.map(([option, fit, why]) => (
              <tr key={option}>
                <td>{option}</td>
                <td>{fit}</td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Recommended implementation path</strong>
        <ol style={{ paddingLeft: 18, marginTop: 12, marginBottom: 0 }}>
          <li>Keep Ollama for answer generation.</li>
          <li>Add a backend `TTSClient` abstraction.</li>
          <li>Implement one provider first: Riva or ElevenLabs.</li>
          <li>Add `/api/v1/tts` endpoint.</li>
          <li>Return audio stream or blob to the frontend.</li>
          <li>Add browser audio controls.</li>
          <li>Add observability for latency, failures, and cost.</li>
          <li>Add ASR later only if microphone input is needed.</li>
        </ol>
      </div>

      <div className="card">
        <strong>Open-source setup</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>Mode</th>
              <th style={{ width: 280 }}>Environment variables</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Kokoro local</td>
              <td>
                auto-detected from <code>.runtime/kokoro</code> and <code>.venv-tts</code>
              </td>
              <td>
                Backend runs <code>kokoro-onnx</code> through the local Python runtime and returns audio directly.
              </td>
            </tr>
            <tr>
              <td>Piper via local CLI</td>
              <td>
                <code>PIPER_MODEL_PATH</code>, <code>PIPER_TTS_BIN</code>
              </td>
              <td>
                Lightweight OSS fallback if Kokoro is unavailable.
              </td>
            </tr>
            <tr>
              <td>Piper via self-hosted HTTP</td>
              <td>
                <code>PIPER_TTS_URL</code>
              </td>
              <td>
                Best when speech runs in a separate container or GPU node.
              </td>
            </tr>
            <tr>
              <td>Hosted fallback</td>
              <td>
                <code>OPENAI_API_KEY</code>
              </td>
              <td>
                Used only if the open-source providers are absent or fail and OpenAI is configured.
              </td>
            </tr>
            <tr>
              <td>Provider order</td>
              <td>
                <code>TTS_PROVIDER_ORDER</code>
              </td>
              <td>
                Example: <code>kokoro_local,piper_http,piper_local,openai,browser_speech_synthesis</code>.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>Frontend audio-player UI</strong>
        <p style={{ marginTop: 8 }}>
          The frontend should stay text-first. Audio is an optional enhancement per
          assistant message, not a blocking dependency for the primary answer path.
        </p>
        <ul style={{ paddingLeft: 18, marginTop: 12, marginBottom: 0 }}>
          <li>Add a <code>Hear answer</code> action on each assistant message.</li>
          <li>Show a mini-player with play, pause, stop, replay, and speed controls.</li>
          <li>Expose global voice settings separately from the message timeline.</li>
          <li>Show clear states: idle, preparing audio, playing, paused, failed.</li>
          <li>Cache audio by message hash and voice options where it saves cost.</li>
        </ul>
      </div>

      <div className="card">
        <strong>What is still missing for production-grade audio</strong>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th style={{ width: 260 }}>Missing piece</th>
              <th>Why it matters</th>
            </tr>
          </thead>
          <tbody>
            {MISSING_ITEMS.map(([item, why]) => (
              <tr key={item}>
                <td>
                  <strong>{item}</strong>
                </td>
                <td>{why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <strong>ASR -&gt; Ollama -&gt; TTS sequence</strong>
        <div style={{ marginTop: 12 }}>
          <Mermaid chart={FULL_VOICE_SEQUENCE} />
        </div>
        <p style={{ marginTop: 12, marginBottom: 0 }}>
          Production rule: if TTS fails, fall back to text. If ASR confidence is low,
          show the transcript for confirmation before sending it deeper into the chat path.
        </p>
      </div>

      <div className="card" style={{ backgroundColor: '#f3f4f6' }}>
        <strong>Brutal rule</strong>
        <p style={{ marginTop: 8 }}>
          Do not treat Ollama as your primary TTS platform. Use Ollama for text
          generation and a dedicated speech engine for audio output.
        </p>
      </div>
    </>
  );
}
