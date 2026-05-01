"""Claude CLI client — shell-out to local Claude Code binary in JSON mode.

Reuses local Claude Code authentication; no API key in env.
Tier-B (cloud frontier, ~$0.30-2/run).

Cost model: parses `usage` from JSON output. Token rates per current
Anthropic pricing (claude-sonnet-4-6: $3/MTok input, $15/MTok output).
Override via CLAUDE_RATE_INPUT_PER_MTOK / CLAUDE_RATE_OUTPUT_PER_MTOK.

Negative-assertion contract (drilled): missing `claude` binary or
subprocess timeout MUST raise LlmClientUnavailable, never return "".

Security note: argv is built as a list and passed to
asyncio.create_subprocess_exec (no shell). Prompt body is delivered
via stdin, not argv, so prompt content cannot influence argv parsing.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any

from .protocol import LlmCallResult, LlmClientUnavailable


_DEFAULT_INPUT_RATE = float(os.environ.get("CLAUDE_RATE_INPUT_PER_MTOK", "3.0"))
_DEFAULT_OUTPUT_RATE = float(os.environ.get("CLAUDE_RATE_OUTPUT_PER_MTOK", "15.0"))


def _resolve_cli_path() -> str:
    explicit = os.environ.get("CLAUDE_CLI_PATH")
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    fallback = "/home/praveen/.local/bin/claude"
    if os.path.exists(fallback):
        return fallback
    return "claude"


def _compute_cost_cents(tokens_in: int, tokens_out: int) -> int:
    cost_usd = (tokens_in / 1_000_000.0) * _DEFAULT_INPUT_RATE
    cost_usd += (tokens_out / 1_000_000.0) * _DEFAULT_OUTPUT_RATE
    return max(0, round(cost_usd * 100))


class ClaudeCliClient:
    backend = "claude_cli"
    tier = "tier_b"

    def __init__(self, *, cli_path: str | None = None, default_timeout_seconds: float = 180.0) -> None:
        self._cli_path = cli_path or _resolve_cli_path()
        self._default_timeout = default_timeout_seconds

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        timeout_seconds: float = 180.0,
        metadata: dict[str, Any] | None = None,
    ) -> LlmCallResult:
        if not os.path.exists(self._cli_path) and not shutil.which(self._cli_path):
            raise LlmClientUnavailable(
                f"claude CLI not found at {self._cli_path!r}; "
                "set CLAUDE_CLI_PATH or install Claude Code"
            )

        argv = [
            self._cli_path,
            "--print",
            "--model", model,
            "--output-format", "json",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError) as fnf:
            raise LlmClientUnavailable(f"claude CLI subprocess failed: {fnf}") from fnf

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as terr:
            proc.kill()
            await proc.wait()
            raise LlmClientUnavailable(
                f"claude CLI timed out after {timeout_seconds}s on model {model!r}"
            ) from terr

        if proc.returncode != 0:
            err_text = (stderr_b or b"").decode("utf-8", errors="replace").strip()
            raise LlmClientUnavailable(
                f"claude CLI exit {proc.returncode}: {err_text[:500]}"
            )

        raw = (stdout_b or b"").decode("utf-8", errors="replace").strip()
        if not raw:
            raise LlmClientUnavailable("claude CLI returned empty stdout")

        text = ""
        tokens_in = 0
        tokens_out = 0
        try:
            payload = json.loads(raw)
            text = str(payload.get("result") or payload.get("text") or "").strip()
            usage = payload.get("usage") or {}
            tokens_in = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            tokens_out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
            metadata_out: dict[str, Any] = {"raw_payload_keys": list(payload.keys())}
        except json.JSONDecodeError:
            lines = [ln for ln in raw.splitlines() if ln.strip()]
            for line in reversed(lines):
                try:
                    payload = json.loads(line)
                    text = str(payload.get("result") or payload.get("text") or "").strip()
                    usage = payload.get("usage") or {}
                    tokens_in = int(usage.get("input_tokens") or 0)
                    tokens_out = int(usage.get("output_tokens") or 0)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                text = raw
            metadata_out = {"parsed_format": "ndjson_or_text"}

        if not text:
            raise LlmClientUnavailable(
                "claude CLI produced no result text (parse succeeded, empty content)"
            )

        cost_cents = _compute_cost_cents(tokens_in, tokens_out)
        return LlmCallResult(
            text=text,
            model=model,
            tier="tier_b",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd_cents=cost_cents,
            backend=self.backend,
            raw_metadata=metadata_out,
        )

    async def close(self) -> None:
        return None
