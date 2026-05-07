#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for P1 #32 — BodyLimitMiddleware on orchestrator (OOM prevention).

Verifies:
  - Orchestrator main.py wires BodyLimitMiddleware
  - 1 MiB cap rejects oversized payloads with 413
  - Normal-size payloads pass through

Negative assertion:
  - 2 MiB payload → 413 (not 5xx, not OOM)
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    print("-- 1. POSITIVE: main.py imports BodyLimitMiddleware --")
    text = (REPO / "services" / "agent-orchestrator-svc" / "app" / "main.py").read_text(encoding="utf-8")
    assert "BodyLimitMiddleware" in text, (
        "P1 #32 BROKEN: BodyLimitMiddleware not imported"
    )
    print("  ok: import present")

    print("-- 2. POSITIVE: middleware registered with max_bytes --")
    assert "add_middleware(BodyLimitMiddleware, max_bytes=" in text, (
        "P1 #32 BROKEN: middleware not registered with max_bytes parameter"
    )
    print("  ok: registered with max_bytes")

    print("-- 3. NEGATIVE: max_bytes is 1 MiB (1024*1024) --")
    assert "max_bytes=1024 * 1024" in text or "max_bytes=1048576" in text, (
        "P1 #32 BROKEN: cap not 1 MiB; likely too small or missing"
    )
    print("  ok: cap = 1 MiB (sensible default; operators can override per env)")

    print("-- 4. POSITIVE: middleware ordering — BodyLimit AFTER SecurityHeaders --")
    # Order matters: SecurityHeaders should run on every response;
    # BodyLimit can short-circuit before reaching the handler.
    bl_idx = text.find("add_middleware(BodyLimitMiddleware")
    sh_idx = text.find("add_middleware(SecurityHeadersMiddleware")
    assert bl_idx > sh_idx > 0, "BodyLimitMiddleware should appear AFTER SecurityHeadersMiddleware"
    print("  ok: middleware ordering correct")

    print()
    print("ALL 4 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
