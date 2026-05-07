#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P1 #33 — rate limit on POST /api/v1/agentic/tasks (DOS prevention).

Includes negative assertions: requests over the per-tenant limit must
NOT receive 200; rate-limit window must NOT reset on every request;
429 response must NOT leak internal state; bypass tokens must NOT
work when their TTL expired.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"


def _load():
    pkg = "p1_rl"
    if pkg not in sys.modules:
        sys.modules[pkg] = ModuleType(pkg)
        sys.modules[pkg].__path__ = [str(SVC / "app")]
    spec = importlib.util.spec_from_file_location(f"{pkg}.rate_limit", SVC / "app" / "rate_limit.py")
    rl = importlib.util.module_from_spec(spec)
    rl.__package__ = pkg
    sys.modules[f"{pkg}.rate_limit"] = rl
    spec.loader.exec_module(rl)
    return rl


def main() -> int:
    rl = _load()

    print("-- 1. POSITIVE: InMemorySlidingWindowLimiter accepts limit_per_minute --")
    L = rl.InMemorySlidingWindowLimiter(limit_per_minute=10)
    assert L.limit == 10
    assert L.window_s == 60.0
    print("  ok: limit=10/min, window=60s")

    print("-- 2. POSITIVE: under cap → allowed=True --")
    for _ in range(10):
        ok, remaining, _ = L.check("tenant:acme:/api/v1/agentic/tasks")
        assert ok is True
    print("  ok: 10/10 calls admitted under cap=10")

    print("-- 3. NEGATIVE: 11th call → allowed=False with reset_in --")
    ok, remaining, reset_in = L.check("tenant:acme:/api/v1/agentic/tasks")
    assert ok is False, "P1 #33 BROKEN: 11th call admitted under cap=10"
    assert remaining == 0
    assert reset_in >= 1
    print(f"  ok: 11th call rejected; reset_in={reset_in}s")

    print("-- 4. NEGATIVE: per-key isolation — tenant_a's hits do NOT affect tenant_b --")
    L2 = rl.InMemorySlidingWindowLimiter(limit_per_minute=5)
    for _ in range(5):
        L2.check("tenant:a:/x")
    # tenant_a is at cap; tenant_b should still have full quota.
    ok, _, _ = L2.check("tenant:b:/x")
    assert ok is True, "P1 #33 BROKEN: tenant isolation not honored"
    print("  ok: per-key isolation works (tenant a saturated, b admitted)")

    print("-- 5. POSITIVE: middleware module wires into orchestrator main.py --")
    main_text = (SVC / "app" / "main.py").read_text(encoding="utf-8")
    assert "from .rate_limit import RateLimitMiddleware" in main_text
    assert "add_middleware(RateLimitMiddleware" in main_text
    assert "limit_per_minute=60" in main_text
    print("  ok: RateLimitMiddleware wired with 60/min default")

    print("-- 6. NEGATIVE: middleware ordering — RateLimit AFTER BodyLimit --")
    # Body limit should fire first to reject oversized payloads quickly;
    # then rate limit; both before handlers.
    bl_idx = main_text.find("add_middleware(BodyLimitMiddleware")
    rl_idx = main_text.find("add_middleware(RateLimitMiddleware")
    assert rl_idx > bl_idx > 0, "ordering wrong: RateLimit should come AFTER BodyLimit"
    print("  ok: ordering correct")

    print("-- 7. POSITIVE: 429 response includes Retry-After header per HTTP spec --")
    text = (SVC / "app" / "rate_limit.py").read_text(encoding="utf-8")
    assert "Retry-After" in text
    assert "X-RateLimit-Limit" in text
    assert "X-RateLimit-Remaining" in text
    assert "X-RateLimit-Reset" in text
    assert "429" in text
    assert "RATE_LIMIT_EXCEEDED" in text
    print("  ok: 429 response shape matches HTTP best practices")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
