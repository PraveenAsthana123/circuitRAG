"""OPA client for approval_agent — shells out to ``opa eval``.

Engaged when ``DOCUMIND_APPROVAL_ENGINE=opa`` is set (default: ``inline``).
Same input shape as the Python ``decide()`` function; same decision values
(AUTO_APPROVED / HUMAN_REQUIRED / DENY / REVISION_REQUIRED).

Why shell + ``opa eval`` over a Python rego library:
- Zero new third-party deps; OPA binary is already on PATH (0.68+).
- The Python rego ports lag upstream (no rego.v1, no `in` keyword, etc.).
- Drill verifies parity with the inline engine — wrong evaluator surfaces
  immediately.

Composes with: approval_agent.agent.decide (env-flag dispatch).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLICY_PATH = Path(__file__).resolve().parent / "policy.rego"
OPA_BINARY = os.getenv("DOCUMIND_OPA_BIN", "opa")
EVAL_QUERY = "data.approval_agent.decision"


class OpaError(RuntimeError):
    pass


@dataclass
class OpaDecision:
    decision: str
    raw: dict[str, Any]


def opa_available() -> bool:
    """True when the binary is on PATH AND the policy file exists."""
    return shutil.which(OPA_BINARY) is not None and POLICY_PATH.exists()


def evaluate(*,
    task: dict[str, Any],
    test_result: str = "PASS",
    governance_result: str = "ALLOW",
    reviewer_decision: str = "APPROVED",
    confidence: float = 0.85,
    timeout_s: int = 5,
) -> OpaDecision:
    """Run ``opa eval`` against policy.rego with the given input.

    Raises ``OpaError`` on any failure (binary missing, non-zero exit,
    malformed result). Caller (agent.decide) catches and falls back.
    """
    if not opa_available():
        raise OpaError(f"opa binary not on PATH or policy missing at {POLICY_PATH}")

    payload = {
        "task": task,
        "test_result": test_result,
        "governance_result": governance_result,
        "reviewer_decision": reviewer_decision,
        "confidence": confidence,
    }
    try:
        proc = subprocess.run(  # noqa: S603 - fixed OPA CLI invocation, payload via stdin
            [
                OPA_BINARY, "eval",
                "--format", "json",
                "--data", str(POLICY_PATH),
                "--stdin-input",
                EVAL_QUERY,
            ],
            input=json.dumps(payload),
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise OpaError(f"opa eval timed out after {timeout_s}s") from e
    if proc.returncode != 0:
        raise OpaError(
            f"opa eval exit={proc.returncode}; "
            f"stderr={proc.stderr[:300]!r}; stdout={proc.stdout[:300]!r}"
        )

    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise OpaError(f"opa eval returned non-JSON: {proc.stdout[:300]!r}") from e

    # Format: {"result":[{"expressions":[{"value": "AUTO_APPROVED", ...}]}]}
    try:
        result_list = body.get("result") or []
        if not result_list:
            # Empty result = no rule fired (default-deny in rego semantics)
            return OpaDecision(decision="DENY", raw=body)
        value = result_list[0]["expressions"][0]["value"]
    except (KeyError, IndexError) as e:
        raise OpaError(f"opa eval result shape unexpected: {body}") from e

    if not isinstance(value, str):
        raise OpaError(f"opa eval value is not a string: {value!r}")
    return OpaDecision(decision=value, raw=body)


__all__ = ["OpaDecision", "OpaError", "evaluate", "opa_available"]
