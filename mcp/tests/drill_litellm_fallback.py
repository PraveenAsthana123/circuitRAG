#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: LiteLLM fallback inside call_ollama() — Stage-2 wiring.

Per CLAUDE.md §43. Locks the contract that:

  - call_ollama tries curl FIRST; falls through to litellm only on
    curl failure (not "preventive" detour)
  - On curl SUCCESS, litellm is NEVER called
  - On curl FAILURE + litellm-not-applicable (flag off / not installed),
    the ORIGINAL curl error is re-raised (operator-readable diagnostic)
  - On curl FAILURE + litellm-applicable, fallback fires + returns
    its (text, tokens) tuple
  - PolisAI gate STILL fires first regardless of which path executes
  - LiteLLM error during fallback re-raises original curl error
    (preserves diagnostic continuity)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _make_failed_curl():
    """Mock proc that mimics a curl failure (returncode != 0)."""
    return CompletedProcess(args=[], returncode=7, stdout="", stderr="curl: (7) Failed to connect to localhost port 11434")


def _make_ok_curl(text: str = "FAKE_OK", tokens: int = 99):
    """Mock proc that mimics a successful Ollama response."""
    import json as _json
    body = {"response": text, "eval_count": tokens}
    return CompletedProcess(args=[], returncode=0, stdout=_json.dumps(body), stderr="")


def main() -> int:
    print("-- 1. POSITIVE: call_ollama source contains the fallback wiring --")
    src = (SCRIPTS / "local_council.py").read_text(encoding="utf-8")
    if "_litellm_fallback" not in src:
        print("x call_ollama must call _litellm_fallback")
        return 1
    if "_LiteLLMNotApplicable" not in src:
        print("x _LiteLLMNotApplicable internal exception must be defined")
        return 1
    if "from litellm_adapter import" not in src:
        print("x _litellm_fallback must import from litellm_adapter")
        return 1
    print("  ok: fallback wiring present")

    print("-- 2. POSITIVE: fallback fires AFTER curl failure, not before --")
    # The fallback must be inside the `if proc.returncode != 0:` branch.
    # A refactor that moves it outside (preventive call) would change
    # semantics. Drill via string-position check.
    curl_run_pos = src.find("subprocess.run(\n        [\"curl\"")
    fallback_pos = src.find("_litellm_fallback(")
    returncode_check = src.find("if proc.returncode != 0:")
    if curl_run_pos == -1 or fallback_pos == -1 or returncode_check == -1:
        print("x cannot locate ordering markers in source")
        return 1
    if not (curl_run_pos < returncode_check < fallback_pos):
        print(f"x ordering wrong — curl run @ {curl_run_pos}, returncode check @ "
              f"{returncode_check}, fallback @ {fallback_pos}")
        return 1
    print("  ok: fallback fires inside the curl-failure branch (post-failure detection)")

    print("-- 3. POSITIVE: curl SUCCESS path does NOT invoke litellm --")
    # Reset env to default no-op
    os.environ.pop("LITELLM_ENABLED", None)
    import local_council
    importlib.reload(local_council)

    fallback_called = {"hit": False}

    def fake_fallback(*args, **kwargs):  # noqa: ARG001
        fallback_called["hit"] = True
        return ("SHOULD_NOT_BE_RETURNED", 0)

    with patch("local_council.subprocess.run", return_value=_make_ok_curl("CURL_OK", 42)), \
         patch("local_council._litellm_fallback", side_effect=fake_fallback):
        text, tokens = local_council.call_ollama(
            model="x", system="x", prompt="x", actor="council:author",
        )
    if fallback_called["hit"]:
        print("x fallback was called even though curl succeeded")
        return 1
    if text != "CURL_OK" or tokens != 42:
        print(f"x curl-success path returned wrong values: text={text!r}, tokens={tokens}")
        return 1
    print("  ok: curl success → fallback NEVER called")

    print("-- 4. NEGATIVE: curl FAILURE + litellm NOT applicable → raise original err --")
    fallback_called["hit"] = False

    class _NotApplicable(Exception):
        pass

    def fake_fallback_unavail(*args, **kwargs):  # noqa: ARG001
        fallback_called["hit"] = True
        raise local_council._LiteLLMNotApplicable()

    with patch("local_council.subprocess.run", return_value=_make_failed_curl()), \
         patch("local_council._litellm_fallback", side_effect=fake_fallback_unavail):
        try:
            local_council.call_ollama(
                model="x", system="x", prompt="x", actor="council:author",
            )
        except RuntimeError as exc:
            # Must cite the ORIGINAL curl error, not "litellm not configured"
            err_msg = str(exc)
            if "ollama curl failed" not in err_msg:
                print(f"x must re-raise original curl error; got: {err_msg!r}")
                return 1
            if "litellm" in err_msg.lower():
                print(f"x error must not mention litellm (operator wants curl diagnostic): {err_msg!r}")
                return 1
        else:
            print("x curl failure + no litellm should have raised RuntimeError")
            return 1
    if not fallback_called["hit"]:
        print("x fallback should have been ATTEMPTED (then raised _LiteLLMNotApplicable)")
        return 1
    print("  ok: curl-fail + no-litellm → original curl err re-raised; litellm noted attempted")

    print("-- 5. POSITIVE: curl FAILURE + litellm applicable → fallback returns its value --")
    def fake_fallback_ok(*args, **kwargs):  # noqa: ARG001
        return ("LITELLM_OK", 77)

    with patch("local_council.subprocess.run", return_value=_make_failed_curl()), \
         patch("local_council._litellm_fallback", side_effect=fake_fallback_ok):
        text, tokens = local_council.call_ollama(
            model="x", system="x", prompt="x", actor="council:author",
        )
    if text != "LITELLM_OK" or tokens != 77:
        print(f"x fallback path returned wrong values: text={text!r}, tokens={tokens}")
        return 1
    print(f"  ok: fallback path returned ('LITELLM_OK', 77)")

    print("-- 6. NEGATIVE: PolisAI gate fires BEFORE both curl + fallback --")
    # Whether curl or fallback handles the call, PolisAI must gate first.
    # A council:unknown actor must default-deny EVEN BEFORE curl runs.
    curl_called = {"hit": False}

    def track_curl(*args, **kwargs):  # noqa: ARG001
        curl_called["hit"] = True
        return _make_ok_curl()

    with patch("local_council.subprocess.run", side_effect=track_curl):
        try:
            local_council.call_ollama(
                model="x", system="x", prompt="x",
                # NO actor → defaults to council:unknown → default-deny
            )
        except local_council.OllamaPolicyDenied:
            pass
        else:
            print("x default actor=council:unknown should have been denied")
            return 1
    if curl_called["hit"]:
        print("x curl should NOT have been called (gate must fire first)")
        return 1
    print("  ok: PolisAI gate fires first; curl never invoked on deny")

    print("-- 7. NEGATIVE: _LiteLLMNotApplicable is internal (not in module __all__) --")
    # The internal exception is implementation detail. It should NOT
    # leak as a public API surface (drill doesn't enforce __all__ but
    # checks the name has the leading underscore convention).
    if not hasattr(local_council, "_LiteLLMNotApplicable"):
        print("x internal exception name must exist")
        return 1
    # Convention: leading underscore = internal
    if "LiteLLMNotApplicable" in local_council.__dict__ and not "_LiteLLMNotApplicable" in local_council.__dict__:
        print("x internal exception must use leading-underscore convention")
        return 1
    print("  ok: _LiteLLMNotApplicable is leading-underscore-internal")

    print("-- 8. POSITIVE: source documents the double-gate tradeoff explicitly --")
    # When fallback fires, both call_ollama and litellm_adapter.complete
    # call PolisAI gate. That's intentional Stage-2 behavior — operator
    # forensics benefit from BOTH audit rows. Drill enforces the
    # tradeoff is DOCUMENTED in source (so a Stage-3 refactor knows
    # the intent before changing the behavior).
    if "double-gate" not in src:
        print("x source must document the double-gate tradeoff explicitly")
        return 1
    if "Stage-3" not in src:
        print("x source must reference Stage-3 cleanup path")
        return 1
    print("  ok: double-gate tradeoff + Stage-3 path documented")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
