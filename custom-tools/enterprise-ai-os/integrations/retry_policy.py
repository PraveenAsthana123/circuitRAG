# Added Iter 24 (2026-05-17) — pure-Python retry helper used to wrap
# integration clients (OpenAI, Qdrant, etc.). Full-jitter exponential
# backoff per AWS Architecture Blog. Mirrors the TS version in
# openclaw-components/07-resilience/retry-policy.ts.
#
# Why a dedicated module vs adding to each client: keeps the retry
# policy testable in isolation + reusable across providers.

import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Tuple, Type, TypeVar

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay_ms: int = 200
    timeout_seconds: float = 30.0
    retry_on: Tuple[Type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
    )

    def execute(self, op: Callable[[], T]) -> T:
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return op()
            except self.retry_on as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                delay_s = self._backoff_seconds(attempt)
                time.sleep(delay_s)
        # Re-raise last seen retryable exception.
        assert last_exc is not None
        raise last_exc

    def _backoff_seconds(self, attempt: int) -> float:
        base_ms = self.base_delay_ms * (2 ** attempt)
        # Full jitter — uniform [base/2, 3*base/2)
        jittered = base_ms * (0.5 + random.random())
        return jittered / 1000.0
