"""Rebuff detector — Stage-1 runtime PI-defense adapter (per §47.6, §48, §56).

Closes the AI-SECURITY-PLANE gap that 07-ai-governance-extras.md
identified: catalog had Rebuff at status=partial, the existing scaffold
(services/evaluation-svc/app/eval_harness.py LakeraRebuffEngine) is
OFFLINE-eval, and rag_inference's only PI defense was a regex-based
injection_detector. This Stage-1 ships the runtime adapter; Stage-2
wires into rag_inference.ask() before the regex injection_scan as a
defense-in-depth signal that records into the trace + audit row.

WHY REBUFF (vs the existing regex injection_detector):
    Regex catches obvious attacks ("ignore previous instructions")
    but misses semantic / multi-stage attacks. Rebuff combines:
      - heuristic substring match (fast, cheap)
      - LLM-based detection (catches semantic injection)
      - vector DB of known attacks (self-hardening — every blocked
        attack gets stored to detect future variants)
      - canary tokens (detects exfiltration of system prompt)
    Defense in depth: keep the regex layer, ADD Rebuff alongside.

OFFLINE-SAFE: when REBUFF_ENABLED unset OR rebuff package missing
OR API token unset OR detector errors, classify() returns
is_attack=False (fail-OPEN per §47.6 — a misconfigured detector
must NEVER silently block traffic; the audit row carries the error
so ops can see + fix).

OPERATOR OPT-IN:
    REBUFF_ENABLED=1
    REBUFF_API_TOKEN=<token>
    REBUFF_API_URL=https://www.rebuff.ai     # cloud default
    REBUFF_PI_THRESHOLD=0.5                  # is_attack threshold
    # For self-hosted: point REBUFF_API_URL at your own server.

COMPOSES WITH (per §49):
    services/inference-svc/app/services/rag_inference.py — Stage-2 wire
    services/evaluation-svc/app/eval_harness.py — LakeraRebuffEngine offline
    docs/runbooks/rebuff.md — operator runbook
    mcp/tests/drill_rebuff_detector_stage1.py — adapter contract
    mcp/tests/drill_rebuff_in_inference_stage2.py — wire contract
    §47.6 OWASP A11 prompt injection / A12 insecure output
    §48 explainability — guardrails_triggered audit row carries
        rebuff_score + rebuff_layers
"""
from __future__ import annotations

import logging
import os
import sys
import types
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

REBUFF_ENABLED = os.getenv("REBUFF_ENABLED", "").strip() == "1"
REBUFF_API_TOKEN = os.getenv("REBUFF_API_TOKEN", "")
REBUFF_API_URL = os.getenv("REBUFF_API_URL", "https://www.rebuff.ai")


def _coerce_threshold(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.5


REBUFF_PI_THRESHOLD = _coerce_threshold(os.getenv("REBUFF_PI_THRESHOLD", "0.5"))


class RebuffDetectorDisabled(RuntimeError):
    """Raised when require_active() is called but env unset."""


@dataclass
class RebuffResult:
    is_attack: bool
    score: float = 0.0
    raw_score: float = 0.0
    available: bool = True
    error: str | None = None
    detection_layers: dict[str, Any] = field(default_factory=dict)


def prepare_langchain_vectorstore_compat() -> None:
    """Bridge Rebuff 0.1.x to modern LangChain package layout.

    Rebuff 0.1.x imports ``langchain.vectorstores.pinecone`` at module
    import time. LangChain moved that integration to
    ``langchain_community.vectorstores.pinecone``. Installing this alias
    lets Rebuff import without downgrading the rest of the LangChain stack.
    """
    if "langchain.vectorstores.pinecone" in sys.modules:
        return
    try:
        from langchain_community.vectorstores import pinecone as pinecone_mod  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        log.debug("rebuff_langchain_compat_unavailable: %s", exc)
        return
    vectorstores_mod = sys.modules.get("langchain.vectorstores")
    if vectorstores_mod is None:
        vectorstores_mod = types.ModuleType("langchain.vectorstores")
        vectorstores_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["langchain.vectorstores"] = vectorstores_mod
    vectorstores_mod.pinecone = pinecone_mod  # type: ignore[attr-defined]
    sys.modules["langchain.vectorstores.pinecone"] = pinecone_mod


def is_available() -> bool:
    """True only if REBUFF_ENABLED=1 + token set + rebuff installable.

    Three independent checks: env flag, API token presence, package
    importability. Any failure → False, no raise. Caller treats False
    as no-op.
    """
    if not REBUFF_ENABLED or not REBUFF_API_TOKEN:
        return False
    try:
        prepare_langchain_vectorstore_compat()
        import rebuff  # noqa: F401, PLC0415  — lazy + heavy
    except Exception:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator-readable status — never raises.

    Returned shape is locked by drill_rebuff_detector_stage1.py:
      - stage: 1
      - enabled_env: bool
      - available: bool
      - api_url: str
      - threshold: float
      - purpose: str (≥ 30 chars)
      - fail_mode: 'OPEN'    ← critical: detector errors never block
      - offline_safe: True
    """
    out: dict[str, Any] = {
        "stage": 1,
        "enabled_env": REBUFF_ENABLED,
        "available": is_available(),
        "api_url": REBUFF_API_URL,
        "threshold": REBUFF_PI_THRESHOLD,
        "purpose": (
            "Pre-flight prompt-injection detection. Heuristic + LLM "
            "+ vector DB layers. Offline-safe: NO-OP when host unreachable / "
            "token unset / rebuff package missing. Stage-2 wires into "
            "rag_inference.ask() before the regex injection_scan."
        ),
        "fail_mode": "OPEN",
        "offline_safe": True,
    }
    if is_available():
        try:
            prepare_langchain_vectorstore_compat()
            import rebuff  # noqa: PLC0415
            out["rebuff_version"] = getattr(rebuff, "__version__", "unknown")
        except Exception as exc:
            out["rebuff_probe_error"] = str(exc)
    return out


def _get_client() -> Any:
    """Lazy-load Rebuff client; cached on the function attribute.

    Returns None when not available — caller treats as no-op.
    """
    if not is_available():
        return None
    if not hasattr(_get_client, "_cached"):
        try:
            prepare_langchain_vectorstore_compat()
            from rebuff import Rebuff  # noqa: PLC0415
            _get_client._cached = Rebuff(  # type: ignore[attr-defined]
                api_token=REBUFF_API_TOKEN,
                api_url=REBUFF_API_URL,
            )
        except Exception as exc:
            log.warning("rebuff_client_init failed: %s", exc)
            _get_client._cached = None  # type: ignore[attr-defined]
    return _get_client._cached  # type: ignore[attr-defined]


def classify(user_input: str) -> RebuffResult:
    """Detect prompt injection in user_input.

    Offline-safe + fail-OPEN: when disabled / unavailable / detector
    errors, returns is_attack=False with available=False / error set.

    Caller MUST treat is_attack=True as block-worthy. is_attack=False
    with error set means "we don't know — don't block on our
    uncertainty"; callers may still defer to the regex
    injection_detector for the final decision.
    """
    if not user_input or not user_input.strip():
        return RebuffResult(is_attack=False, available=False)
    if not is_available():
        return RebuffResult(is_attack=False, available=False)

    client = _get_client()
    if client is None:
        return RebuffResult(
            is_attack=False, available=False, error="client_init_failed"
        )

    try:
        det = client.detect_injection(user_input)
        # Rebuff's Detection object shape varies by version — be
        # defensive. Prefer attribute access; fall back to dict-style.
        is_attack = bool(getattr(det, "injection_detected", False))
        score = float(getattr(det, "max_heuristic_score", 0.0) or 0.0)
        raw_score = float(getattr(det, "max_model_score", 0.0) or 0.0)
        layers = {
            "heuristic": getattr(det, "heuristic_score", None),
            "model": getattr(det, "model_score", None),
            "vector_store": getattr(det, "vector_score", None),
        }
        return RebuffResult(
            is_attack=is_attack,
            score=score,
            raw_score=raw_score,
            available=True,
            detection_layers=layers,
        )
    except Exception as exc:
        # Fail-OPEN — detector ERROR is NOT an attack signal. Caller
        # sees error set so it can record into the audit row + fix.
        log.warning("rebuff_detect_failed (fail-OPEN): %s", exc)
        return RebuffResult(
            is_attack=False,
            available=False,
            error=str(exc)[:200],
        )


def require_active() -> None:
    """Strict check — raises if Rebuff not available.

    For callers that NEED detection (audit-required code paths). Most
    inference callers should use is_available() + offline-safe no-op
    pattern instead.
    """
    if not is_available():
        raise RebuffDetectorDisabled(
            "Rebuff detector not available. Set REBUFF_ENABLED=1 + "
            "REBUFF_API_TOKEN + ensure the rebuff package is installed."
        )


__all__ = [
    "REBUFF_PI_THRESHOLD",
    "RebuffDetectorDisabled",
    "RebuffResult",
    "classify",
    "is_available",
    "prepare_langchain_vectorstore_compat",
    "require_active",
    "status",
]


if __name__ == "__main__":
    import json
    import sys

    print("libs/py/documind_core/rebuff_detector.py — Stage-1 PI defense")
    print("Stage-1 opt-in via REBUFF_ENABLED=1 + REBUFF_API_TOKEN")
    print("Offline-safe + fail-OPEN: detector errors never block traffic.")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
