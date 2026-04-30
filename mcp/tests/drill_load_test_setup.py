#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: k6 load-test setup contract.

Locks the 5-phase load-test infrastructure shipped in this iteration.
Without this drill, a future commit could:
  - silently drop a phase (e.g. delete soak from STAGES)
  - relax SLO thresholds (raise p95 cap from 500ms to 2000ms)
  - point BASE_URL at a hardcoded prod URL (security + ops hazard)
  - lose the wrapper script's profile argument validation

Negative assertions cover: k6 baseline absent; missing phase from
STAGES; SLO threshold loosened; wrapper script not executable; STATUS
doc absent or stripped of testing strategy section.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
K6 = REPO / "infra" / "load-test" / "k6" / "baseline.js"
WRAPPER = REPO / "scripts" / "load-test.sh"
RUNBOOK = REPO / "infra" / "load-test" / "README.md"
STATUS = REPO / "docs" / "STATUS.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: all 4 load-test files exist --")
    for p in (K6, WRAPPER, RUNBOOK, STATUS):
        if not p.exists():
            raise AssertionError(f"missing {p.relative_to(REPO)}")
    k6 = K6.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    print("  ok: k6 baseline + wrapper + runbook + STATUS all present")

    print("-- 2. POSITIVE: k6 baseline has all 5 phases in STAGES --")
    require(k6, "STAGES = {", "STAGES dict")
    for phase in ("smoke:", "load:", "stress:", "soak:", "spike:"):
        require(k6, phase, f"STAGES.{phase[:-1]}")
    print("  ok: 5 phases (smoke + load + stress + soak + spike)")

    print("-- 3. POSITIVE: SLO thresholds enforced --")
    require(k6, "thresholds:", "thresholds block")
    require(k6, "p(95)<100", "/healthz p95<100ms")
    require(k6, "p(95)<500", "/api/* p95<500ms")
    require(k6, "rate<0.01", "error rate <1%")
    print("  ok: 3 canonical SLO thresholds")

    print("-- 4. NEGATIVE: SLO thresholds MUST NOT be loosened --")
    # Catch attempts to relax limits without an explicit ratchet decision.
    forbidden_relaxations = [
        "p(95)<2000",   # 4x slower than current
        "p(95)<5000",   # 10x slower
        "rate<0.10",    # 10% error rate
        "rate<0.50",
    ]
    for f in forbidden_relaxations:
        if f in k6:
            raise AssertionError(
                f"forbidden SLO relaxation in baseline.js: {f!r}; "
                f"if intentional, document the ratchet move per ADR-015"
            )
    print("  ok: no SLO relaxations detected")

    print("-- 5. POSITIVE: stress phase ramps to >= 1000 VUs --")
    # Stress phase must actually find the breakpoint. If ramp tops at
    # 100, it's just another load run.
    stress_match = re.search(r"stress:\s*\[(.*?)\]", k6, re.DOTALL)
    if not stress_match:
        raise AssertionError("stress stage block not found")
    stress_block = stress_match.group(1)
    if not re.search(r"target:\s*1000", stress_block):
        raise AssertionError(
            "stress phase doesn't ramp to 1000 VUs; can't find breakpoint"
        )
    print("  ok: stress ramps to 1000 VU")

    print("-- 6. POSITIVE: spike phase ramps to >= 2000 VUs --")
    spike_match = re.search(r"spike:\s*\[(.*?)\]", k6, re.DOTALL)
    if not spike_match:
        raise AssertionError("spike stage block not found")
    spike_block = spike_match.group(1)
    if not re.search(r"target:\s*2000", spike_block):
        raise AssertionError(
            "spike phase doesn't ramp to 2000 VUs; recovery test trivial"
        )
    print("  ok: spike ramps to 2000 VU")

    print("-- 7. NEGATIVE: BASE_URL MUST be env-overrideable (no hardcode) --")
    # If a future commit hardcodes BASE_URL to a prod host, dev runs
    # would accidentally hit prod. Drill enforces env override.
    if re.search(r"BASE_URL\s*=\s*['\"]https?://(?!localhost)", k6):
        # Allow localhost defaults; reject any other hardcoded URL.
        # Check this is a default-only assignment to localhost.
        m = re.search(r"const\s+BASE_URL\s*=\s*__ENV\.BASE_URL\s*\|\|\s*['\"](.*?)['\"]", k6)
        if not m or "localhost" not in m.group(1):
            raise AssertionError(
                "BASE_URL not env-overrideable with localhost default"
            )
    print("  ok: BASE_URL env-overrideable with localhost default")

    print("-- 8. POSITIVE: wrapper script is executable --")
    st = os.stat(WRAPPER)
    if not (st.st_mode & 0o111):
        raise AssertionError(f"{WRAPPER.relative_to(REPO)} is not executable")
    print("  ok: wrapper has +x")

    print("-- 9. POSITIVE: wrapper accepts all 6 profiles --")
    for profile in ("smoke", "load", "stress", "soak", "spike", "full"):
        require(wrapper, profile, f"wrapper handles {profile}")
    print("  ok: 6 profiles handled (smoke + load + stress + soak + spike + full)")

    print("-- 10. NEGATIVE: wrapper MUST validate unknown profile --")
    require(wrapper, "unknown profile", "unknown profile guard")
    require(wrapper, "exit 2", "exit 2 on bad profile")
    print("  ok: wrapper rejects unknown profiles")

    print("-- 11. POSITIVE: STATUS doc has Testing strategy section --")
    require(status, "## Testing strategy", "Testing strategy section")
    require(status, "k6", "k6 reference in STATUS")
    require(status, "5 phases", "5-phase reference in STATUS")
    print("  ok: STATUS doc cites k6 + 5-phase")

    print("-- 12. NEGATIVE: STATUS doc MUST NOT carry placeholder language --")
    for forbidden in ("TODO", "TBD", "FIXME", "Lorem ipsum"):
        if forbidden in status:
            raise AssertionError(f"forbidden placeholder in STATUS.md: {forbidden}")
    print("  ok: no placeholder language in STATUS.md")

    print("\nALL 12 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
