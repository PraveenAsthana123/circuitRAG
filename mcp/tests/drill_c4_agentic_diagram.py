#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: C4-agentic diagram contract.

Locks docs/architecture/C4-agentic.md as the canonical structural
surface for the agentic control plane. The existing C4-context.md +
C4-container.md don't mention orchestrator / sidecar / MCP / council
(verified 0 hits at authoring time); this drill prevents the agentic
C4 file from silently drifting empty or losing its structural
sections.

Negative assertions cover: file absent; L1/L2/L3 sections missing;
Mermaid graph blocks missing or wrong count; canonical containers
not cited; trust-boundary section missing; cross-reference table
to deep-dive pages stripped.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
C4 = REPO / "docs" / "architecture" / "C4-agentic.md"
EXISTING_C4 = [
    REPO / "docs" / "architecture" / "C4-context.md",
    REPO / "docs" / "architecture" / "C4-container.md",
]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle!r}")


def main() -> int:
    print("-- 1. POSITIVE: C4-agentic.md exists --")
    if not C4.exists():
        raise AssertionError(f"missing file: {C4.relative_to(REPO)}")
    text = C4.read_text(encoding="utf-8")
    print("  ok: C4-agentic.md present")

    print("-- 2. POSITIVE: L1, L2, L3 section headers all present --")
    require(text, "## L1 — Agentic system context", "L1 section header")
    require(text, "## L2 — Agentic containers", "L2 section header")
    require(text, "## L3 —", "L3 section header (any)")
    print("  ok: L1 + L2 + L3 sections all present")

    print("-- 3. POSITIVE: 3 Mermaid graph blocks (one per level) --")
    mermaid_blocks = re.findall(r"```mermaid\s+graph", text)
    if len(mermaid_blocks) < 3:
        raise AssertionError(
            f"expected 3 Mermaid graph blocks (L1+L2+L3); got {len(mermaid_blocks)}"
        )
    print(f"  ok: {len(mermaid_blocks)} Mermaid graph blocks (>= 3)")

    print("-- 4. POSITIVE: canonical agentic containers all cited --")
    for needle, label in [
        ("agent-orchestrator-svc", "orchestrator container"),
        ("sidecar-advisor", "sidecar container"),
        ("server_drills", "MCP drills server"),
        ("server_hr", "MCP HR server"),
        ("server_itsm", "MCP ITSM server"),
        ("Next.js BFF", "BFF container"),
    ]:
        require(text, needle, label)
    print("  ok: 6 canonical containers cited")

    print("-- 5. POSITIVE: actor + dependency tables present --")
    require(text, "### Actors", "actors table heading")
    require(text, "### External dependencies", "external dependencies heading")
    require(text, "### Containers", "containers table heading")
    print("  ok: actor + dependency + container tables all present")

    print("-- 6. NEGATIVE: trust boundary section must be present --")
    # Without trust-boundary explicit, the diagram doesn't answer
    # "where does external trust end" — the most-load-bearing C4 question
    # for a regulated AI surface.
    require(text, "### Trust boundary", "trust boundary section")
    print("  ok: trust boundary section present")

    print("-- 7. NEGATIVE: cross-reference table to deep-dives must be present --")
    # Per §49 compose-pattern, structural docs must point to the deep-dives
    # they compose with. Without this, C4-agentic floats free of the
    # deep-dive catalog.
    require(text, "## Cross-references", "cross-reference section")
    for ref in [
        "/admin/agent-registry/deep",
        "/admin/sidecar/deep",
        "/admin/memory/deep",
        "/admin/mcp/deep",
        "/admin/api-gateway/deep",
    ]:
        require(text, ref, f"deep-dive ref: {ref}")
    print("  ok: cross-reference table cites 5 deep-dive pages")

    print("-- 8. NEGATIVE: file must NOT carry placeholder language --")
    for forbidden in ["TODO", "TBD", "FIXME", "Lorem ipsum"]:
        if forbidden in text:
            raise AssertionError(f"forbidden placeholder in C4-agentic.md: {forbidden}")
    print("  ok: no placeholder language remains")

    print("-- 9. NEGATIVE: existing C4 docs still don't mention agentic (regression check) --")
    # If existing C4-context / C4-container start mentioning agentic,
    # this file's reason for existing weakens. Either:
    #   (a) merge agentic into the existing C4 docs and delete this one
    #   (b) leave separate and accept duplication
    # Drill flags case (a) so an explicit decision is made, not drift.
    for f in EXISTING_C4:
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        agentic_count = content.lower().count("agentic")
        orch_count = content.lower().count("orchestrator")
        if agentic_count > 5 or orch_count > 5:
            raise AssertionError(
                f"{f.relative_to(REPO)} now mentions agentic ({agentic_count}x) / "
                f"orchestrator ({orch_count}x); decide whether to merge C4-agentic.md "
                f"into it OR keep separate — but make the decision explicit"
            )
    print("  ok: existing C4 docs still defer agentic surface to C4-agentic.md")

    print("-- 10. NEGATIVE: ADR-008 + ADR-022 cross-references must be present --")
    # ADR-008 = transport breakers (the contract this surface depends on)
    # ADR-022 = convergent-work pattern (operationally relevant for this
    # surface where parallel-tool + autonomous-loop both touch agentic)
    require(text, "ADR-008", "ADR-008 transport-breakers reference")
    require(text, "ADR-022", "ADR-022 convergent-work reference")
    print("  ok: ADR-008 + ADR-022 cited")

    print("\nALL 10 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
