# Audio / TTS For Chatbot Stack

This document explains how to add audio output and speech capabilities to the current chatbot stack.

It focuses on:

- text-to-speech (TTS)
- optional speech-to-text (ASR)
- provider choices
- best fit for this repo

## 1. Core Idea

The clean architecture is:

```text
User text or voice
  -> API
  -> LLM generates answer text
  -> TTS converts answer text to audio
  -> client plays audio
```

If microphone input is added:

```text
Mic audio
  -> ASR
  -> LLM
  -> TTS
  -> speaker
```

## 2. Provider Roles

| Provider | Best role | Best when |
| --- | --- | --- |
| Ollama | LLM text generation | local or on-prem text generation |
| NVIDIA Riva | TTS and ASR | enterprise, GPU-backed, private deployment |
| ElevenLabs | high-quality TTS | premium voice quality matters most |
| Cartesia | realtime TTS | low-latency conversational audio matters |
| OpenAI audio models | unified managed audio stack | one API family is preferred |
| Azure Speech | enterprise speech platform | Azure/compliance/governance fit matters |
| Google Cloud TTS | managed cloud TTS | stable managed cloud voice service |

## 3. Brutal Rule

Do not treat Ollama as your main TTS platform.

Use:
- Ollama for answer generation
- a dedicated TTS engine for speech

## 4. Best Architecture Patterns

### Option A: Simple MVP

```text
Frontend
  -> Chat API
  -> Ollama
  -> browser TTS or lightweight TTS API
```

Best for:
- fast prototype
- basic read-aloud

### Option B: Better production

```text
Frontend
  -> FastAPI
  -> Ollama / vLLM
  -> TTS service
  -> audio stream/blob
  -> browser player
```

Best for:
- higher voice quality
- control over playback
- future ASR expansion

### Option C: Full voice assistant

```text
Mic audio
  -> ASR
  -> LLM
  -> TTS
  -> speaker
```

Best for:
- voice bot
- spoken assistant
- real-time voice workflows

## 5. Recommended Provider Choices

| Goal | Best choice |
| --- | --- |
| best voice quality | ElevenLabs |
| best realtime TTS | Cartesia |
| best enterprise/on-prem speech | NVIDIA Riva |
| best unified managed API stack | OpenAI audio |
| best cloud-enterprise baseline | Azure Speech / Google Cloud TTS |

## 6. Best Fit For This Repo

### Current stack fit

Best immediate path:

1. keep Ollama for answer generation
2. add a backend `/tts` endpoint
3. call a dedicated TTS provider from that endpoint
4. return audio to the frontend
5. later add ASR if microphone input is needed

### Best provider options for this repo

| Option | Fit | Why |
| --- | --- | --- |
| NVIDIA Riva | high | strongest fit for private GPU-backed speech path |
| ElevenLabs | high | easiest way to get premium voice quality |
| Cartesia | medium-high | strong if realtime voice UX matters |
| OpenAI audio | medium-high | good unified managed API path |
| browser TTS only | medium | fastest MVP, weakest control/quality |

## 7. Backend API Contract

### TTS endpoint

```text
POST /api/v1/tts
```

Request:

```json
{
  "text": "Your answer text here",
  "voice": "default",
  "format": "mp3",
  "speed": 1.0,
  "provider": "riva",
  "tenant_id": "tenant_a",
  "correlation_id": "corr-123"
}
```

Response:
- audio stream or binary blob
- `Content-Type: audio/mpeg` or `audio/wav`
- optional headers:
  - `X-Correlation-ID`
  - `X-TTS-Provider`
  - `X-Voice-Name`

Validation rules:
- reject empty `text`
- cap max character or token budget
- enforce tenant and auth context
- require explicit timeout to provider
- log provider latency and failure reason

### Streaming chat + audio endpoint

```text
POST /api/v1/chat/audio
```

Request:

```json
{
  "message": "Explain row level security",
  "session_id": "sess_123",
  "voice": "alloy",
  "audio_format": "mp3",
  "include_text": true
}
```

Response:
- streamed answer text
- final audio URL or audio chunk stream
- citations / metadata if chatbot is RAG-backed

Best use:
- chatbot answer first, audio immediately after answer text is ready
- simplest way to add read-aloud without microphone capture

### Full voice round-trip endpoint pattern

```text
POST /api/v1/voice/chat
```

Request:
- multipart audio upload or streaming audio
- optional session ID
- optional preferred voice
- optional language code

Process:
- ASR -> LLM -> TTS

Response:
- transcript
- answer text
- audio output
- confidence or fallback metadata

### Recommended backend abstractions

```text
ASRClient
TTSClient
VoiceOrchestrator
AudioStorage
```

Responsibilities:
- `ASRClient`: speech-to-text provider adapter
- `TTSClient`: provider-neutral speech synthesis adapter
- `VoiceOrchestrator`: ASR -> LLM -> TTS flow, retries, timeouts, fallback
- `AudioStorage`: optional store for replayable audio blobs

## 8. Frontend Audio-Player UI Design

```text
Chat UI
  -> send text
  -> receive answer text
  -> request audio
  -> play audio
```

Core controls:
- play
- pause
- stop
- replay
- voice selection
- speech speed

Recommended UI states:
- idle
- generating answer
- preparing audio
- playing
- paused
- failed

Recommended components:
- message bubble action: `Hear answer`
- inline mini-player per assistant message
- global voice settings drawer
- loading state for TTS preparation
- error badge when audio generation fails

Good UX rules:
- do not block text answer on audio generation
- let the user read immediately while audio is prepared
- keep audio optional per message
- preserve text-first behavior for accessibility and reliability

### Browser flow

```text
User clicks Hear answer
  -> frontend calls /api/v1/tts
  -> receives stream/blob/url
  -> attaches to HTMLAudioElement
  -> playback controls update state
```

### Caching opportunities

- cache TTS per message hash + voice + speed
- cache signed URL for replay if object storage is used
- avoid regenerating identical audio for repeated playback

## 9. Full Voice Assistant Architecture

### Architecture flow

```text
Mic input
  -> browser recorder
  -> /api/v1/voice/chat
  -> ASR provider
  -> chat / retrieval / Ollama
  -> TTS provider
  -> audio stream back to browser
  -> browser playback
```

### Sequence view

```text
Browser
  -> Voice API
  -> ASR
  -> Chat service
  -> Ollama
  -> TTS
  -> Browser
```

### Production design notes

- ASR and TTS should have separate timeout and breaker policies
- voice flow should degrade to text if TTS fails
- transcript should be shown before audio if low-latency UX matters
- microphone uploads should be size-bounded
- voice sessions should propagate correlation ID end to end

## 10. Step To Implement

1. Add provider abstraction `TTSClient`.
2. Implement one provider first: Riva or ElevenLabs.
3. Add `/api/v1/tts` backend route with timeout, auth, and metrics.
4. Add frontend per-message `Hear answer` control and mini-player.
5. Stream or return buffered audio to the browser.
6. Add caching for repeated speech where it saves cost.
7. Add provider metrics: latency, failures, bytes, cost.
8. Add `/api/v1/chat/audio` if text + audio should return from one route.
9. Add ASR only after TTS path is stable.
10. Add `/api/v1/voice/chat` for full microphone round-trip.

## 11. Interview Answer

Say this:

I would keep the LLM and speech layers separate. Ollama remains the answer generator, and a dedicated TTS system handles speech output. For an enterprise/private deployment I would choose NVIDIA Riva. For best voice quality I would use ElevenLabs. For low-latency conversational speech I would consider Cartesia. I would expose TTS behind a backend abstraction so the frontend only deals with an audio endpoint, not vendor-specific APIs.

## 12. Strong Closing Line

The right audio architecture is not “make the LLM speak directly.” It is “generate text well, then use the best speech engine for the product constraints.”
