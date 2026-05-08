#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Rebuff Stage-2 wire into rag_inference.ask (per §43 + §47.6 + §48 + §56).

Locks the offline-safe Rebuff wire that emits a rebuff_check step on
every /api/v1/ask request. Stage-2 records signal into the trace +
audit row but does NOT block — defense-in-depth alongside the
existing regex injection_detector. Promotion to a blocking signal is
a future Stage-3 iteration once the false-positive baseline is
calibrated against the eval harness.

Eight steps. Five negative.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAG_INFER = (
    REPO
    / "services"
    / "inference-svc"
    / "app"
    / "services"
    / "rag_inference.py"
)
ADAPTER = REPO / "libs" / "py" / "documind_core" / "rebuff_detector.py"


def main() -> int:
    print("-- 1. POSITIVE: rag_inference references rebuff_detector --")
    if not RAG_INFER.exists():
        print(f"x {RAG_INFER} missing")
        return 1
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing — Stage-1 must land first")
        return 1
    src = RAG_INFER.read_text(encoding="utf-8")
    if "rebuff_detector" not in src:
        print("x rag_inference must reference rebuff_detector (Stage-2 wire)")
        return 1
    print("  ok: rag_inference wired to rebuff_detector")

    print(
        "-- 2. NEGATIVE: rebuff_detector source UNCHANGED by Stage-2 (no "
        "reverse import — adapter never imports inference) --"
    )
    adapter_src = ADAPTER.read_text(encoding="utf-8")
    if re.search(
        r"^\s*(from\s+.*rag_inference|import\s+.*rag_inference|"
        r"from\s+app\.|import\s+app\.|from\s+services\.|import\s+services\.)",
        adapter_src,
        re.MULTILINE,
    ):
        print("x adapter imports inference modules — clean-layering broken")
        return 1
    print("  ok: adapter doesn't reverse-import inference (clean layering)")

    print(
        "-- 3. NEGATIVE: wire is INSIDE a trace.step('rebuff_check') block "
        "so the audit row carries the signal --"
    )
    if 'trace.step("rebuff_check")' not in src and "trace.step('rebuff_check')" not in src:
        print(
            "x wire missing trace.step('rebuff_check') — audit row won't carry "
            "rebuff signal"
        )
        return 1
    print("  ok: wire is inside trace.step('rebuff_check')")

    print(
        "-- 4. NEGATIVE: lazy import of rebuff_detector — NOT at module "
        "top, only inside ask() --"
    )
    top = "\n".join(src.splitlines()[:80])
    if re.search(
        r"^\s*(from\s+documind_core\.rebuff_detector|import\s+documind_core\.rebuff_detector)",
        top,
        re.MULTILINE,
    ):
        print(
            "x rebuff_detector imported at module top — must be lazy "
            "(inside ask) so module-load doesn't pay the cost"
        )
        return 1
    print("  ok: rebuff_detector lazy-imported inside ask()")

    print(
        "-- 5. NEGATIVE: wire FAILS SAFE — try/except wraps the "
        "rebuff classify() call (fail-OPEN) --"
    )
    # The wire block should contain both 'try:' and 'except' near the
    # rebuff_check step.
    rb_block_match = re.search(
        r'trace\.step\(["\']rebuff_check["\']\).*?(?=trace\.step|$)',
        src,
        re.DOTALL,
    )
    if not rb_block_match:
        print("x cannot locate rebuff_check block")
        return 1
    rb_block = rb_block_match.group(0)
    if "try:" not in rb_block or "except" not in rb_block:
        print(
            "x wire missing try/except — detector errors would propagate "
            "and break the request path (violates §47.6 fail-OPEN)"
        )
        return 1
    print("  ok: wire has try/except — fail-OPEN preserved")

    print(
        "-- 6. NEGATIVE: wire emits rebuff_is_attack + rebuff_score "
        "into trace.meta (forensic substrate per §51) --"
    )
    if "rebuff_is_attack" not in rb_block:
        print("x wire doesn't emit rebuff_is_attack to trace.meta")
        return 1
    if "rebuff_score" not in rb_block:
        print("x wire doesn't emit rebuff_score to trace.meta")
        return 1
    print("  ok: rebuff_is_attack + rebuff_score recorded in trace.meta")

    print(
        "-- 7. POSITIVE: wire fires BEFORE injection_scan (defense-in-depth "
        "ordering — Rebuff signal lands BEFORE regex gate) --"
    )
    rb_idx = src.find("rebuff_check")
    inj_idx = src.find("injection_scan")
    if rb_idx < 0:
        print("x rebuff_check not found")
        return 1
    if inj_idx < 0:
        print("x injection_scan removed — defense in depth requires keeping it")
        return 1
    if rb_idx > inj_idx:
        print(
            f"x rebuff_check at {rb_idx} comes AFTER injection_scan at "
            f"{inj_idx} — Rebuff signal must land before regex gate"
        )
        return 1
    print(f"  ok: rebuff_check fires before injection_scan (defense in depth)")

    print(
        "-- 8. NEGATIVE: Stage-2 does NOT block on rebuff is_attack=True "
        "(promotion to block is a deliberate Stage-3 decision) --"
    )
    # The Stage-2 wire records to trace + audit; it must NOT raise
    # PolicyViolation / HTTPException / similar based on _rb.is_attack.
    # We check that the rebuff_check block doesn't contain a `raise`
    # keyed off the rebuff result.
    if re.search(r'_rb\.is_attack[^\n]*raise|raise[^\n]*_rb\.is_attack', rb_block):
        print(
            "x Stage-2 wire raises on _rb.is_attack — promotion to block "
            "is Stage-3 (file an ADR + update this drill before flipping)"
        )
        return 1
    print(
        "  ok: Stage-2 records signal only — no premature promotion to block"
    )

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
