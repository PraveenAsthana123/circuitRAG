# Extra Design Area — Cognitive Circuit Breaker (CCB)

**Status:** Added 2026-04-23 as the 5th specialized breaker alongside Retrieval / Token / Agent-Loop / Observability.
**Origin:** arXiv 2604.13417 — *Cognitive Circuit Breaker: Intrinsic Reliability for Generative Systems*. Concept simplified and adapted for DocuMind's production architecture.
**Where in code:** [`libs/py/documind_core/breakers.py`](../../libs/py/documind_core/breakers.py) — classes `CognitiveCircuitBreaker`, `CognitiveSignal` and subclasses.
**Where wired:** [`services/inference-svc/app/services/rag_inference.py`](../../services/inference-svc/app/services/rag_inference.py) — attached to the streaming generation loop.

---

## Core idea (one paragraph)

Move reliability checks **from after-the-fact to real-time**. Instead of generating a full response and then running guardrails, run cheap checks every ~32 tokens as the model streams its output. When a signal crosses its threshold (degenerate loop, missing citation, PII leak, low logprob confidence), **interrupt mid-generation** and swap in a safe fallback. The user never sees the hallucination.

The base `CircuitBreaker` protects against *the call failing*. The CCB protects against *the call succeeding with bad output*.

---

## The 5 breakers — when to use which

| Breaker | Polarity | Granularity | Opens when… | Fires before / during / after |
|---|---|---|---|---|
| Base `CircuitBreaker` | forward | per-dependency, per-process | N consecutive exceptions | after the call |
| `RetrievalCircuitBreaker` | forward | per-dependency, per-process | rolling avg top_score < threshold OR empty-result rate > 50% | after the call |
| `TokenCircuitBreaker` | forward | per-tenant, per-process (synced from FinOps) | tenant daily/monthly/per-request cap exceeded | **before** the call |
| `AgentLoopCircuitBreaker` | forward | **per agent run** (fresh instance per request) | max_steps, total_timeout, loop detected, tool budget | during the loop |
| `ObservabilityCircuitBreaker` | **inverted** — when OPEN, export is SKIPPED (not raised) | per-exporter, process-wide | N consecutive export failures | inside the exporter wrapper |
| `CognitiveCircuitBreaker` | forward | **per-request** (fresh instance per generation) | any CognitiveSignal returns BLOCK, or warnings exceed threshold | **during** generation streaming |

---

## Architecture placement

```
User query
  │
  ▼
API Gateway  ─(rate limit: RateLimitMiddleware)
  │
  ▼
Inference Service
  │
  ├─ TokenCircuitBreaker.check_or_raise()        ← pre-flight, budget
  │
  ├─ Retrieval call
  │    └─ RetrievalCircuitBreaker.record_quality()  ← post-hoc, quality
  │
  ├─ Prompt construction (versioned template)
  │
  ├─ Ollama.stream()  ───(wrapped by)───►  CognitiveCircuitBreaker.on_tokens()
  │                                          │
  │                                          ├─ RepetitionSignal
  │                                          ├─ CitationDeadlineSignal
  │                                          ├─ ForbiddenPatternSignal
  │                                          └─ LogprobConfidenceSignal
  │                                          │
  │                                          │  (if BLOCK) → CognitiveInterrupt
  │                                          │
  │                                          ▼
  │                                       Fallback response (HITL-routed)
  │
  └─ TokenCircuitBreaker.record_usage()          ← post-hoc, feed FinOps

Observability layer (parallel, out-of-band):
  ObservabilityCircuitBreaker guards every span / metric export —
  when OPEN, exports are silently SKIPPED so a dead collector
  never blocks the request path.
```

---

## Signal catalogue (shipping defaults)

| Signal | What it detects | Cost per check |
|---|---|---|
| `RepetitionSignal` | same n-gram repeated > N times (model degeneracy) | O(tail chars) |
| `CitationDeadlineSignal` | RAG answer without `[Source: ...]` past token N (hallucination) | 1 regex scan |
| `ForbiddenPatternSignal` | regex allow/deny (tenant policy, simple PII) | K regex scans |
| `LogprobConfidenceSignal` | rolling avg logprob < threshold (uncertain model) | O(1) |

Add your own by subclassing `CognitiveSignal`:

```python
from documind_core.breakers import CognitiveSignal, CognitiveReading, CognitiveDecision

class MyDomainSignal(CognitiveSignal):
    name = "my_domain"
    def evaluate(self, partial: str, tokens: int) -> CognitiveReading:
        if "forbidden" in partial:
            return CognitiveReading(CognitiveDecision.BLOCK, 0.0, "bad", self.name)
        return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "ok", self.name)
```

Signals MUST be cheap — anything that calls an LLM defeats the point.

---

## Mapping to the 67 DocuMind design areas

The CCB touches several existing areas — it doesn't replace them, it strengthens them:

| Design area | Impact |
|---|---|
| 4 Failure Boundary | CCB is a new boundary — "bad output" is now a failure mode we can contain |
| 25 Inference Service | Becomes intelligent, not blind — knows when it's generating garbage |
| 33 Output Contract | CCB enforces the contract mid-stream instead of at the end |
| 45 Backpressure | Interrupts bad flows early, freeing capacity |
| 52 Blast Radius Control | A low-confidence answer never reaches the user |
| 57 HITL | CCB interrupts feed the HITL queue (routed to reviewers) |
| 62 Observability | CCB readings are logged as span attributes |
| 56 Policy-as-Code | ForbiddenPatternSignal is policy enforced at generation time |

---

## Honest limitations (directly from the paper)

- **Calibration is hard.** Each signal's threshold needs tuning per corpus; too strict and valid answers get blocked. Calibrate via offline eval: run CCB against your eval dataset, measure block-rate on *correct* answers, lower the threshold until block-rate on bad answers still exceeds block-rate on good answers.
- **Not a replacement.** CCB does NOT solve: data quality, retrieval poisoning, policy governance, multi-agent coordination. It sits alongside those; it doesn't replace them.
- **Vendor dependency.** Some signals (logprobs) need model cooperation. Ollama exposes logprobs inconsistently; in that setup, the Repetition + CitationDeadline signals do most of the lifting.

---

## Test coverage

See [`libs/py/tests/test_breakers.py`](../../libs/py/tests/test_breakers.py) — unit tests for every signal's block path and every breaker's state transitions. All five breakers are exercised.
