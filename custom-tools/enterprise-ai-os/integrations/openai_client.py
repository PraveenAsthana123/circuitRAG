# ✅ Iter 24 (2026-05-17): OpenAIClient wrapped with retry + timeout.
#     Pre-fix: no retry on transient 5xx / connection blip, no
#     per-request timeout — a stuck OpenAI request would block the
#     whole FastAPI worker indefinitely.
#
#     Now: each chat() call goes through RetryPolicy.execute() and
#     the OpenAI SDK is constructed with an explicit timeout (the
#     SDK respects the timeout kwarg and aborts the underlying HTTP
#     request). Default: 30s timeout, 3 retries on connection /
#     timeout errors with full-jitter backoff.

import os
from typing import Dict, Any, List

from openai import OpenAI
from openai import APIConnectionError, APITimeoutError, InternalServerError

from integrations.retry_policy import RetryPolicy


_DEFAULT_TIMEOUT_SECONDS = 30.0


class OpenAIClient:
    def __init__(
        self,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        retry_policy: RetryPolicy | None = None,
    ):
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout_seconds,
        )
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.retry_policy = retry_policy or RetryPolicy(
            max_retries=3,
            base_delay_ms=200,
            timeout_seconds=timeout_seconds,
            retry_on=(
                ConnectionError,
                TimeoutError,
                APIConnectionError,
                APITimeoutError,
                InternalServerError,  # retry on 5xx
            ),
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        def _call():
            response = self.client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                temperature=temperature,
            )
            return {
                "provider": "openai",
                "model": model or self.default_model,
                "text": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return self.retry_policy.execute(_call)
