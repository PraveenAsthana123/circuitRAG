"""LLM client backends — uniform Protocol over Ollama / Claude CLI / Codex CLI.

Phase A2: three concrete backends — OllamaHttpClient (Tier A), ClaudeCliClient
(Tier B, claude --print --output-format json), CodexCliClient (Tier B,
codex exec). Existing app/ollama_client.py kept for backward compat.
"""
from .claude_cli_client import ClaudeCliClient
from .codex_cli_client import CodexCliClient
from .ollama_client import OllamaHttpClient
from .protocol import LlmCallResult, LlmClient, LlmClientUnavailable

__all__ = [
    "ClaudeCliClient",
    "CodexCliClient",
    "LlmCallResult",
    "LlmClient",
    "LlmClientUnavailable",
    "OllamaHttpClient",
]
