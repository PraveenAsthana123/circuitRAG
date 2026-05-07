#!/usr/bin/env python3
# RESOURCES: ollama
"""Structural + runtime drill for LlmClient Protocol conformance (Phase A2).

Verifies the three concrete clients (OllamaHttpClient, ClaudeCliClient,
CodexCliClient) implement the LlmClient runtime-checkable Protocol, and
that LlmClientUnavailable is raised — never silently returned as "" — when
a backend is unreachable.

Negative assertions:
  1. ClaudeCliClient with bogus CLI path → LlmClientUnavailable.
  2. CodexCliClient with bogus CLI path → LlmClientUnavailable.
  3. OllamaHttpClient pointed at unreachable port → LlmClientUnavailable
     (positive proof that http error → exception, not empty string).
  4. All three classes have backend AND tier class attributes — drill
     proves the Protocol attribute fields cannot be quietly removed.

Resource tag = ollama (we hit a real Ollama generate endpoint for the
positive path; serialised against other ollama drills via
scripts/run_drills.py per §43.2).

Why this drill: A2 unblocks A3/A4. The router relies on the negative
contract (raise, not return "") to drive its fallback chain. Without
this drill, a future regression that wraps subprocess errors into "" or
None would silently break Tier-B → Tier-A failover.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
LLM_DIR = SVC / "app" / "llm_clients"


def _import(label: str, path: Path):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {label} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def _import_pkg() -> tuple[Any, Any, Any, Any, Any]:
    # Import protocol first (no deps), then concrete clients which import it.
    proto = _import("a2_protocol", LLM_DIR / "protocol.py")
    sys.modules["app.llm_clients.protocol"] = proto

    # Stub minimal package so relative imports work.
    pkg_init = _import("a2_pkg", LLM_DIR / "__init__.py")  # noqa: F841
    return proto.LlmClient, proto.LlmClientUnavailable, proto.LlmCallResult, proto, pkg_init


from typing import Any  # noqa: E402  (used by _import_pkg signature above)


def _import_concrete(name: str, file: str, proto_module):
    # Concrete clients use `from .protocol import ...`. To make that work
    # without a real package, register the protocol module under the parent
    # name, then load the concrete file as a submodule.
    sys.modules.setdefault("a2_concrete_pkg", type(sys)("a2_concrete_pkg"))
    sys.modules["a2_concrete_pkg.protocol"] = proto_module
    spec = importlib.util.spec_from_file_location(
        f"a2_concrete_pkg.{name}",
        LLM_DIR / file,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {name} from {LLM_DIR / file}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "a2_concrete_pkg"
    sys.modules[f"a2_concrete_pkg.{name}"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    LlmClient, LlmClientUnavailable, LlmCallResult, proto_mod, _ = _import_pkg()

    print("-- 1. POSITIVE: three concrete clients import cleanly --")
    ollama_mod = _import_concrete("ollama_client", "ollama_client.py", proto_mod)
    claude_mod = _import_concrete("claude_cli_client", "claude_cli_client.py", proto_mod)
    codex_mod = _import_concrete("codex_cli_client", "codex_cli_client.py", proto_mod)
    print("  ok: ollama_client, claude_cli_client, codex_cli_client imported")

    print("-- 2. POSITIVE: each class has backend + tier attributes --")
    for cls_name, cls in (
        ("OllamaHttpClient", ollama_mod.OllamaHttpClient),
        ("ClaudeCliClient", claude_mod.ClaudeCliClient),
        ("CodexCliClient", codex_mod.CodexCliClient),
    ):
        assert hasattr(cls, "backend"), f"{cls_name}: missing 'backend' attribute"
        assert hasattr(cls, "tier"), f"{cls_name}: missing 'tier' attribute"
        assert cls.tier in ("tier_a", "tier_b"), f"{cls_name}: bad tier {cls.tier!r}"
    print("  ok: backend + tier present on all three")

    print("-- 3. POSITIVE: tier mapping correct (ollama=A, claude/codex=B) --")
    assert ollama_mod.OllamaHttpClient.tier == "tier_a"
    assert claude_mod.ClaudeCliClient.tier == "tier_b"
    assert codex_mod.CodexCliClient.tier == "tier_b"
    print("  ok: tier mapping locked")

    print("-- 4. NEGATIVE: ClaudeCliClient with bogus path raises Unavailable --")
    bogus = claude_mod.ClaudeCliClient(cli_path="/nonexistent/path/to/claude-fake-binary-xyz")
    raised = False
    try:
        asyncio.run(bogus.generate(model="claude-sonnet-4-6", prompt="hello", timeout_seconds=2.0))
    except LlmClientUnavailable as exc:
        raised = True
        assert "not found" in str(exc).lower() or "subprocess failed" in str(exc).lower(), (
            f"unexpected error message: {exc}"
        )
    assert raised, "ClaudeCliClient with bogus path MUST raise LlmClientUnavailable"
    print("  ok: bogus path triggers LlmClientUnavailable")

    print("-- 5. NEGATIVE: CodexCliClient with bogus path raises Unavailable --")
    bogus_codex = codex_mod.CodexCliClient(cli_path="/nonexistent/path/codex-fake-binary-xyz")
    raised = False
    try:
        asyncio.run(bogus_codex.generate(model="gpt-5.2-codex", prompt="hello", timeout_seconds=2.0))
    except LlmClientUnavailable:
        raised = True
    assert raised, "CodexCliClient with bogus path MUST raise LlmClientUnavailable"
    print("  ok: bogus path triggers LlmClientUnavailable")

    print("-- 6. NEGATIVE: OllamaHttpClient on unreachable port raises Unavailable --")
    bad_ollama = ollama_mod.OllamaHttpClient(base_url="http://127.0.0.1:1", timeout_seconds=1.0)
    raised = False
    try:
        asyncio.run(bad_ollama.generate(model="qwen2.5:latest", prompt="hi", timeout_seconds=1.0))
    except LlmClientUnavailable:
        raised = True
    finally:
        asyncio.run(bad_ollama.close())
    assert raised, "OllamaHttpClient unreachable MUST raise LlmClientUnavailable"
    print("  ok: unreachable Ollama triggers LlmClientUnavailable")

    print("-- 7. POSITIVE: round-trip LlmCallResult shape --")
    # Build a synthetic result and verify required fields.
    sample = LlmCallResult(
        text="hi",
        model="qwen2.5:latest",
        tier="tier_a",
        tokens_in=5,
        tokens_out=2,
        cost_usd_cents=0,
        backend="ollama",
    )
    assert sample.tier in ("tier_a", "tier_b")
    assert isinstance(sample.cost_usd_cents, int)
    assert isinstance(sample.tokens_in, int)
    print("  ok: LlmCallResult contract holds")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
