# WebLLM — privacy-first in-browser inference runbook

> A new lane in circuitRAG: 100% in-browser LLM inference via
> WebGPU. The model + tokens + state never leave the user's
> device. Locked by `mcp/tests/drill_private_chat_webllm_page.py`
> (8 steps, 5 negative).

## What WebLLM adds

| Concern | Existing inference path | WebLLM (this) |
| --- | --- | --- |
| Where inference runs | `inference-svc` (server-side) | User's browser (WebGPU) |
| Network cost | every request hits backend | zero per-inference round-trip |
| Privacy posture | TLS-protected but server sees content | content never leaves device |
| Latency to first token | ~retrieve + rerank + LLM | ~initial model load (750 MB), then local |
| Use cases | core RAG, multi-tenant, audit-required | PII-safe summarization, air-gapped demos, edge AI, internal copilots |
| Quality | full-size models | small (1B-3B params, 4-bit quantized) |

Both lanes co-exist. Most circuitRAG flows still go through
`inference-svc`. WebLLM is for **privacy-required** scenarios where
sending content to a server is a non-starter (HIPAA, GDPR, FINRA,
classified, contractor environments).

## URL

```
http://localhost:3000/admin/private-chat
```

## How it works

1. User opens `/admin/private-chat`
2. Page detects WebGPU support (Chrome 113+, Edge 113+, Safari 18+
   on a machine with a supported GPU)
3. User clicks **Load model** — explicit opt-in. ~750 MB Llama-3.2-1B
   downloads from HuggingFace via the MLC-AI CDN, then compiles to
   WebGPU shaders. Cached in IndexedDB, so subsequent visits skip
   the download.
4. User types a message → engine streams tokens back into the chat
   UI. **No fetch to any backend.** Drilled.
5. Reset button clears messages without re-downloading the model.

## Privacy contract (drilled — code-review-time enforcement)

The drill `mcp/tests/drill_private_chat_webllm_page.py` enforces
five negatives at code-review time:

| Rule | Drill step | What it forbids in the source |
| --- | --- | --- |
| Zero backend HTTP | 4 | `fetch(`, `XMLHttpRequest`, `axios`, `/api/v1/`, `/api/v2/` |
| User-gated model load | 5 | `CreateMLCEngine` inside `useEffect(..., [])` (auto-load on mount) |
| No telemetry | 6 | `console.log`, `console.info`, `console.warn`, `console.error`, `posthog`, `mixpanel`, `Sentry.`, `datadogRum`, `amplitude`, `window.analytics` |
| Lazy SDK import | 7 | static `import ... from '@mlc-ai/web-llm'` for runtime values |
| Privacy banner visible | 8 | "Privacy" + "browser" + "never leave" must appear in JSX |

If any of these regress, the drill fails — preventing a privacy
violation from slipping through review.

## Browser requirements

- **Chrome 113+** (May 2023, WebGPU shipped) — ✅ recommended
- **Edge 113+** — ✅
- **Safari 18+** (Sep 2024) — ✅ on supported hardware
- **Firefox** — Nightly behind flag; stable not yet
- **Mobile** — partial; depends on device GPU

The page detects WebGPU on mount via `'gpu' in navigator` and shows
a clear unsupported-browser banner if missing.

## Model

Default: `Llama-3.2-1B-Instruct-q4f32_1-MLC`
- Meta Llama 3.2, 1B parameters
- 4-bit quantized (q4f32_1)
- ~750 MB on-disk in IndexedDB
- ~1.5 GB GPU memory at runtime
- Decent for chat, summarization, simple Q&A; NOT for code, math,
  or long context (window is 4K)

To swap models, edit `MODEL_ID` in `WebLLMChat.tsx`. Other options
include Phi-3.5-mini, Qwen2.5-0.5B, Llama-3.2-3B (heavier).

## Cost

- **Per inference:** $0 (runs locally)
- **Per load:** ~750 MB egress from MLC-AI CDN, one-time per browser
- **GPU power:** ~5-15 W during generation

## Performance expectations (rough)

| Hardware | Tokens/sec |
| --- | --- |
| M1/M2 Mac (8 GB+) | 20-40 |
| Modern discrete GPU (RTX 30/40 series) | 40-80 |
| Integrated GPU (Intel UHD / older) | 5-15 |
| Mobile (high-end) | 5-20 |
| Mobile (budget) | usually unsupported |

## Composes with (per §49)

- [`services/frontend/app/admin/private-chat/page.tsx`](../../services/frontend/app/admin/private-chat/page.tsx) — page wrapper
- [`services/frontend/app/admin/private-chat/WebLLMChat.tsx`](../../services/frontend/app/admin/private-chat/WebLLMChat.tsx) — component
- [`mcp/tests/drill_private_chat_webllm_page.py`](../../mcp/tests/drill_private_chat_webllm_page.py) — privacy contract
- [`/admin/llmops`](../../services/frontend/app/admin/llmops) — server-side LLM ops surface (sibling lane)
- [`/admin/local-models`](../../services/frontend/app/admin/local-models) — local Ollama lane (sibling)
- [`/admin/explainability/deep`](../../services/frontend/app/admin/explainability/deep) — explainability surface (privacy is part of it)
- §47 architecture (privacy is a first-class lane, not an afterthought)
- §48 explainability (the Privacy lane in the explainability surface)
- §57.1 production-grade-by-default (WebGPU detection + user-gated
  load + lazy SDK import + drilled privacy contract from day-1)

## Brutal rule

> WebLLM is the **privacy lane**, not a replacement for the main
> RAG path. If you find yourself routing audit-required flows
> through this page because it's "easier", you've broken the
> separation: the audit trail can't reconstruct what happened
> in-browser. Use the right lane for the right job — server-side
> for audit + multi-tenant + large models, WebLLM for privacy +
> offline + edge.
