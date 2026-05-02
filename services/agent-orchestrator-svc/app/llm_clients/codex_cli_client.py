"""Codex CLI client — shell-out to local Codex binary.

Reuses local Codex authentication (~/.codex/config.toml). Tier-B fallback
when role=coder and complexity=high (per D1 default).

Negative-assertion contract: missing CLI / timeout / non-zero exit MUST
raise LlmClientUnavailable. Never silent empty string.

Security note: argv built as list; passed to asyncio.create_subprocess_exec
(no shell). Prompt body delivered via stdin so content cannot influence
argv parsing.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any

from .protocol import LlmCallResult, LlmClientUnavailable

_DEFAULT_INPUT_RATE = float(os.environ.get("CODEX_RATE_INPUT_PER_MTOK", "1.0"))
_DEFAULT_OUTPUT_RATE = float(os.environ.get("CODEX_RATE_OUTPUT_PER_MTOK", "4.0"))

_USAGE_RE = re.compile(r"tokens?[:\s]+in=(\d+).*?out=(\d+)", re.IGNORECASE | re.DOTALL)


def _resolve_cli_path() -> str:
    explicit = os.environ.get("CODEX_CLI_PATH")
    if explicit:
        return explicit
    found = shutil.which("codex")
    if found:
        return found
    return "codex"


def _compute_cost_cents(tokens_in: int, tokens_out: int) -> int:
    cost_usd = (tokens_in / 1_000_000.0) * _DEFAULT_INPUT_RATE
    cost_usd += (tokens_out / 1_000_000.0) * _DEFAULT_OUTPUT_RATE
    return max(0, round(cost_usd * 100))


class CodexCliClient:
    backend = "codex_cli"
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
                f"codex CLI not found at {self._cli_path!r}; "
                "set CODEX_CLI_PATH or run `codex login`"
            )

        argv = [self._cli_path, "exec"]
        if model:
            argv.extend(["--model", model])

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError) as fnf:
            raise LlmClientUnavailable(f"codex CLI subprocess failed: {fnf}") from fnf

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except TimeoutError as terr:
            proc.kill()
            await proc.wait()
            raise LlmClientUnavailable(
                f"codex CLI timed out after {timeout_seconds}s on model {model!r}"
            ) from terr

        if proc.returncode != 0:
            err_text = (stderr_b or b"").decode("utf-8", errors="replace").strip()
            raise LlmClientUnavailable(
                f"codex CLI exit {proc.returncode}: {err_text[:500]}"
            )

        text = (stdout_b or b"").decode("utf-8", errors="replace").strip()
        if not text:
            raise LlmClientUnavailable("codex CLI returned empty stdout")

        tokens_in = 0
        tokens_out = 0
        stderr_text = (stderr_b or b"").decode("utf-8", errors="replace")
        match = _USAGE_RE.search(stderr_text)
        if match:
            tokens_in = int(match.group(1))
            tokens_out = int(match.group(2))

        cost_cents = _compute_cost_cents(tokens_in, tokens_out)
        return LlmCallResult(
            text=text,
            model=model,
            tier="tier_b",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd_cents=cost_cents,
            backend=self.backend,
            raw_metadata={"stderr_tail": stderr_text[-200:]},
        )

    async def close(self) -> None:
        return None
