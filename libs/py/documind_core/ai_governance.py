"""
AI governance primitives — debuggability, explainability, responsibility,
secure-AI, portability, interpretability.

Every class here is a DEFENSIVE or EXPOSITIONAL primitive for the inference
pipeline. They don't replace the CCB or GuardrailChecker — they complement:

* The CCB stops BAD GENERATION mid-flight (intrinsic).
* Guardrails check the FINISHED response (post-hoc).
* These classes add the AI-governance lens:
    - pre-flight input inspection (adversarial + injection)
    - on-the-wire PII scanning
    - explainability + interpretability packaging
    - fairness + responsibility checks

Design note — all classes are cheap (regex + cheap heuristics + cosine).
None call an LLM themselves. An LLM-judge variant can be layered on top
in evaluation-svc where latency budget is relaxed.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .exceptions import PolicyViolationError, ValidationError

log = logging.getLogger(__name__)


# ============================================================================
# 1. PromptInjectionDetector — SECURE AI (input side)
# ============================================================================

class InjectionVerdict(str, Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"   # log + flag, let through
    BLOCK = "block"             # refuse the request


@dataclass
class InjectionFinding:
    pattern_id: str
    excerpt: str
    verdict: InjectionVerdict


# Curated patterns. Order: most specific first. Each pattern is tagged
# with the verdict it triggers — SUSPICIOUS for ambiguous phrases,
# BLOCK for unambiguous jailbreak attempts.
_INJECTION_RULES: list[tuple[str, re.Pattern[str], InjectionVerdict]] = [
    ("ignore_previous",
     re.compile(
         r"\b(ignore|disregard|forget|override)(?:\s+\w+){0,4}\s+"
         r"(instructions?|prompts?|rules?|messages?|context|previous|above|prior)\b",
         re.I,
     ),
     InjectionVerdict.BLOCK),
    ("system_override",
     re.compile(
         r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be|from\s+now\s+on)\b"
         r"[^.]*\b(system|admin|root|dan|jailbreak)\b",
         re.I,
     ),
     InjectionVerdict.BLOCK),
    ("policy_leak",
     re.compile(r"\b(reveal|show|print|output|display)\s+.*?(system\s+prompt|instructions?|policy|ruleset)\b", re.I),
     InjectionVerdict.BLOCK),
    ("role_reassign",
     re.compile(r"###\s*(system|user|assistant)\s*[:\n]", re.I),
     InjectionVerdict.SUSPICIOUS),
    ("delimiter_spoof",
     re.compile(r"(<\|(?:im_start|im_end|system|user|assistant)\|>|\[INST\]|\[/INST\])", re.I),
     InjectionVerdict.BLOCK),
    ("encoding_bypass",
     # Base64-like blobs of suspicious length often hide instructions
     re.compile(r"(?:[A-Za-z0-9+/]{120,}={0,2})"),
     InjectionVerdict.SUSPICIOUS),
    ("exec_command",
     re.compile(r"\b(run|execute|eval)\s+(this|the following|code|command|script)\b", re.I),
     InjectionVerdict.SUSPICIOUS),
    ("credential_exfil",
     re.compile(r"\b(api[\s_-]?key|password|token|credentials?)\s+(is|=|:)\s*", re.I),
     InjectionVerdict.SUSPICIOUS),
]


class PromptInjectionDetector:
    """
    Pre-flight check on the user's raw query (and optionally on retrieved
    chunks — RAG poisoning vector). Returns findings; callers decide
    action based on verdict.

    NOT a replacement for LLM-judge classifiers (Rebuff / Lakera). A cheap
    first line of defense that handles the common cases.
    """

    def __init__(
        self,
        *,
        extra_rules: list[tuple[str, re.Pattern[str], InjectionVerdict]] | None = None,
    ) -> None:
        self._rules = list(_INJECTION_RULES) + list(extra_rules or [])

    def scan(self, text: str) -> list[InjectionFinding]:
        findings: list[InjectionFinding] = []
        if not text:
            return findings
        for rule_id, pat, verdict in self._rules:
            m = pat.search(text)
            if m:
                snippet = text[max(0, m.start() - 20):m.end() + 20]
                findings.append(
                    InjectionFinding(
                        pattern_id=rule_id,
                        excerpt=snippet[:200],
                        verdict=verdict,
                    )
                )
        return findings

    def scan_or_raise(self, text: str) -> list[InjectionFinding]:
        findings = self.scan(text)
        blocks = [f for f in findings if f.verdict is InjectionVerdict.BLOCK]
        if blocks:
            raise PolicyViolationError(
                "prompt injection detected",
                details={
                    "pattern_ids": [f.pattern_id for f in blocks],
                    "count": len(blocks),
                },
            )
        return findings


# ============================================================================
# 2. PIIScanner — SECURE AI (output side)
# ============================================================================

_PII_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card_like",
     re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("email",
     re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone_us",
     re.compile(r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address",
     re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("aws_access_key",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private_key_pem",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("passport_like",
     re.compile(r"\b[A-Z][0-9]{8}\b")),
]


@dataclass
class PIIFinding:
    kind: str
    excerpt: str


class PIIScanner:
    """
    Regex-based PII detector. Cheap, catches obvious. For production,
    layer Microsoft Presidio or a NER model on top for context-aware
    redaction ("John Smith" is PII; "John the Baptist" isn't).
    """

    def __init__(self, *, extra: list[tuple[str, re.Pattern[str]]] | None = None) -> None:
        self._rules = list(_PII_RULES) + list(extra or [])

    def scan(self, text: str) -> list[PIIFinding]:
        findings: list[PIIFinding] = []
        if not text:
            return findings
        for kind, pat in self._rules:
            for m in pat.finditer(text):
                findings.append(PIIFinding(kind=kind, excerpt=m.group(0)[:80]))
                if len(findings) > 20:   # cap
                    break
        return findings

    def redact(self, text: str) -> str:
        """Replace PII with `[REDACTED:{kind}]` placeholders."""
        if not text:
            return text
        redacted = text
        for kind, pat in self._rules:
            redacted = pat.sub(f"[REDACTED:{kind}]", redacted)
        return redacted


# ============================================================================
# 3. AIExplainer — EXPLAINABILITY (post-hoc, user-facing)
# ============================================================================

@dataclass
class ChunkAttribution:
    """Per-chunk metadata that contributed to an answer."""

    chunk_id: str
    document_id: str
    score: float
    source: str                     # vector | graph | hybrid
    page_number: int
    preview: str                    # first 180 chars


@dataclass
class Explanation:
    """User-facing explanation of a RAG answer."""

    question: str
    answer: str
    retrieval_strategy: str
    top_chunks: list[ChunkAttribution]
    prompt_version: str
    model: str
    tokens_prompt: int
    tokens_completion: int
    confidence: float
    guardrail_violations: list[str]
    cognitive_breaker: dict[str, Any]
    why_this_answer: str             # human-readable narrative

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "retrieval_strategy": self.retrieval_strategy,
            "top_chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "score": round(c.score, 4),
                    "source": c.source,
                    "page_number": c.page_number,
                    "preview": c.preview,
                }
                for c in self.top_chunks
            ],
            "prompt_version": self.prompt_version,
            "model": self.model,
            "tokens": {"prompt": self.tokens_prompt, "completion": self.tokens_completion},
            "confidence": self.confidence,
            "guardrail_violations": self.guardrail_violations,
            "cognitive_breaker": self.cognitive_breaker,
            "why_this_answer": self.why_this_answer,
        }


class AIExplainer:
    """
    Packages retrieval + generation metadata into a user-facing explanation.
    This is what powers `?debug=true` and the `/admin/hitl` reviewer UI.

    The `why_this_answer` narrative is generated by TEMPLATE, not LLM — it
    must not itself hallucinate. A separate (evaluation-svc) LLM judge can
    produce richer explanations in the background.
    """

    @staticmethod
    def build(
        *,
        question: str,
        answer: str,
        retrieval_strategy: str,
        retrieved_chunks: list[dict[str, Any]],
        prompt_version: str,
        model: str,
        tokens_prompt: int,
        tokens_completion: int,
        confidence: float,
        guardrail_violations: list[str],
        cognitive_breaker_snapshot: dict[str, Any] | None = None,
    ) -> Explanation:
        top = [
            ChunkAttribution(
                chunk_id=str(c.get("chunk_id") or ""),
                document_id=str(c.get("document_id") or ""),
                score=float(c.get("score", 0.0)),
                source=str(c.get("source", "unknown")),
                page_number=int(c.get("page_number", 0) or 0),
                preview=(c.get("text") or "")[:180],
            )
            for c in retrieved_chunks[:5]
        ]

        narrative = AIExplainer._narrative(
            question=question,
            retrieval_strategy=retrieval_strategy,
            top=top,
            confidence=confidence,
            violations=guardrail_violations,
        )

        return Explanation(
            question=question,
            answer=answer,
            retrieval_strategy=retrieval_strategy,
            top_chunks=top,
            prompt_version=prompt_version,
            model=model,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            confidence=confidence,
            guardrail_violations=guardrail_violations,
            cognitive_breaker=cognitive_breaker_snapshot or {},
            why_this_answer=narrative,
        )

    @staticmethod
    def _narrative(
        *,
        question: str,
        retrieval_strategy: str,
        top: list[ChunkAttribution],
        confidence: float,
        violations: list[str],
    ) -> str:
        if not top:
            return (
                "No relevant chunks were retrieved from the corpus. The answer "
                "(if any) is NOT grounded in indexed content — treat with caution."
            )
        lines = [
            f"The system used {retrieval_strategy} retrieval.",
            f"Top chunk came from document {top[0].document_id} page {top[0].page_number} "
            f"with score {top[0].score:.3f} (source={top[0].source}).",
            f"Estimated confidence: {confidence:.0%} based on citation coverage and "
            f"retrieval score.",
        ]
        if violations:
            lines.append(
                "Guardrails raised: " + ", ".join(violations) +
                " — this answer was flagged for review."
            )
        return " ".join(lines)


# ============================================================================
# 4. ResponsibleAIChecker — fairness + bias + disclosure
# ============================================================================

@dataclass
class FairnessSignal:
    name: str
    score: float                    # 0.0 worst, 1.0 best
    message: str


class ResponsibleAIChecker:
    """
    Lightweight responsibility-lens checks for the generated response.

    Signals implemented here:

    * **Disclosure**: the response should disclose AI origin if asked.
    * **Protected-class language**: generic non-discrimination check
      (biased phrasing around gender/race/age/disability).
    * **Absolute claims without citation**: "always / never / must / all"
      without a `[Source: ...]` tag → lower fairness score.

    Caveats: this IS NOT a bias benchmark. A full fairness evaluation
    requires a curated probe set (e.g. BBQ benchmark) and runs in
    evaluation-svc, not in the hot path.
    """

    _PROTECTED_CLASS_WORDS = re.compile(
        r"\b(all|every|most)\s+(women|men|blacks?|whites?|asians?|muslims?|christians?|jews?|"
        r"elderly|disabled|poor|rich|immigrants?)\s+(are|do|have|must|never|always)\b",
        re.I,
    )
    _ABSOLUTE_CLAIM = re.compile(
        r"\b(always|never|all|none|every|must|cannot\s+(?:possibly|ever))\b", re.I
    )
    _DISCLOSURE_QUESTION = re.compile(
        r"\b(are you (?:an?|the)? (?:ai|bot|assistant|language model)|"
        r"what are you|who (?:built|made|trained) you|"
        r"were you trained on)", re.I
    )

    def check(self, *, question: str, answer: str, has_citations: bool) -> list[FairnessSignal]:
        signals: list[FairnessSignal] = []

        # 1. Protected-class sweeping statements
        pc = self._PROTECTED_CLASS_WORDS.search(answer)
        if pc:
            signals.append(FairnessSignal(
                name="protected_class_generalization",
                score=0.1,
                message=f"possible bias: '{pc.group(0)}'",
            ))

        # 2. Absolute claim without citation
        if self._ABSOLUTE_CLAIM.search(answer) and not has_citations:
            signals.append(FairnessSignal(
                name="unsupported_absolute",
                score=0.4,
                message="absolute claim with no citation",
            ))

        # 3. AI-disclosure asked but not given
        if self._DISCLOSURE_QUESTION.search(question) and "ai" not in answer.lower():
            signals.append(FairnessSignal(
                name="missing_ai_disclosure",
                score=0.3,
                message="user asked about AI origin; response did not disclose",
            ))

        return signals


# ============================================================================
# 5. AdversarialInputFilter — SECURE AI (heuristics)
# ============================================================================

class AdversarialInputFilter:
    """
    Cheap adversarial-input heuristics:

    * Excess length (denial-of-wallet attempt — huge prompt).
    * Repeated tokens (DoS — inflates prompt+completion tokens).
    * Non-printable / zalgo-like content.
    * Too many URLs (potential SSRF in agent tool-use).
    """

    def __init__(
        self,
        *,
        max_chars: int = 10_000,
        max_repeat: int = 50,
        max_urls: int = 5,
    ) -> None:
        self._max_chars = max_chars
        self._max_repeat = max_repeat
        self._max_urls = max_urls

    def inspect(self, text: str) -> list[str]:
        """Return list of reason strings; empty list = clean."""
        reasons: list[str] = []
        if len(text) > self._max_chars:
            reasons.append(f"too_long:{len(text)}>{self._max_chars}")

        # Repeated token run
        words = text.split()
        if words:
            cur = words[0]
            run = 1
            longest = 1
            for w in words[1:]:
                if w == cur:
                    run += 1
                    longest = max(longest, run)
                else:
                    cur, run = w, 1
            if longest > self._max_repeat:
                reasons.append(f"repeated_token_run:{longest}")

        # URL burst
        urls = re.findall(r"https?://\S+", text)
        if len(urls) > self._max_urls:
            reasons.append(f"too_many_urls:{len(urls)}>{self._max_urls}")

        # Non-printable characters (excluding common whitespace)
        bad = sum(1 for ch in text if not (ch.isprintable() or ch in "\n\t\r"))
        if bad > 0 and bad / max(1, len(text)) > 0.02:
            reasons.append(f"non_printable_ratio:{bad / len(text):.3f}")

        return reasons

    def inspect_or_raise(self, text: str) -> None:
        reasons = self.inspect(text)
        if reasons:
            raise ValidationError(
                "adversarial input rejected",
                details={"reasons": reasons, "sample_hash": hashlib.sha256(text[:200].encode()).hexdigest()[:12]},
            )


# ============================================================================
# 6. InterpretabilityTrace — chain-of-reasoning packaging
# ============================================================================

@dataclass
class ReasoningStep:
    step_id: int
    name: str                       # "retrieve" | "rerank" | "prompt" | "generate" | "guardrail"
    input_summary: str
    output_summary: str
    duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class InterpretabilityTrace:
    """
    Records each step of the inference pipeline so callers (admins, HITL
    reviewers, eval-svc) can reconstruct "what happened".

    Distinct from observability traces: this trace is at the BUSINESS-STEP
    level, user-readable, and embedded in the response (gated by debug
    mode or reviewer access).

    Usage::

        trace = InterpretabilityTrace()
        with trace.step("retrieve") as s:
            s.input(query)
            chunks = retrieve(...)
            s.output(f"{len(chunks)} chunks")
    """

    def __init__(self) -> None:
        self._steps: list[ReasoningStep] = []
        self._next_id = 0
        self._start_ms: dict[int, float] = {}

    def step(self, name: str) -> "_StepContext":
        self._next_id += 1
        return _StepContext(self, self._next_id, name)

    def _record(self, step: ReasoningStep) -> None:
        self._steps.append(step)

    @property
    def steps(self) -> list[ReasoningStep]:
        return list(self._steps)

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "step_id": s.step_id,
                "name": s.name,
                "input": s.input_summary,
                "output": s.output_summary,
                "duration_ms": round(s.duration_ms, 2),
                "metadata": s.metadata,
            }
            for s in self._steps
        ]


class _StepContext:
    """Context manager for a pipeline step — records timing + summaries."""

    def __init__(self, trace: InterpretabilityTrace, step_id: int, name: str) -> None:
        import time
        self._trace = trace
        self._id = step_id
        self._name = name
        self._input = ""
        self._output = ""
        self._metadata: dict[str, Any] = {}
        self._start = time.monotonic()
        self._time = time

    def input(self, s: str) -> None:
        self._input = s[:500]

    def output(self, s: str) -> None:
        self._output = s[:500]

    def meta(self, **kv: Any) -> None:
        self._metadata.update(kv)

    def __enter__(self) -> "_StepContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration = (self._time.monotonic() - self._start) * 1000
        self._trace._record(
            ReasoningStep(
                step_id=self._id,
                name=self._name,
                input_summary=self._input,
                output_summary=self._output,
                duration_ms=duration,
                metadata=self._metadata,
            )
        )


__all__ = [
    # Secure AI — input side
    "PromptInjectionDetector",
    "InjectionVerdict",
    "InjectionFinding",
    "AdversarialInputFilter",
    # Secure AI — output side
    "PIIScanner",
    "PIIFinding",
    # Explainability / interpretability
    "AIExplainer",
    "Explanation",
    "ChunkAttribution",
    "InterpretabilityTrace",
    "ReasoningStep",
    # Responsibility
    "ResponsibleAIChecker",
    "FairnessSignal",
]
