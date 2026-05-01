"""LLM client backends — uniform Protocol over Ollama / Claude CLI / Codex CLI.

Phase A1: only the Protocol + result envelope. Concrete backends land in A2.
Existing OllamaGenerateClient (app/ollama_client.py) keeps working unchanged
until A2 adapts it to the new Protocol.
"""
from .protocol import LlmCallResult, LlmClient, LlmClientUnavailable

__all__ = ["LlmCallResult", "LlmClient", "LlmClientUnavailable"]
