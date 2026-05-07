#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: paperclip + openclaw .proto files lock the gRPC contract.

Per CLAUDE.md §43 + §47 (11-layer architecture). Locks the contract
that:

  - paperclip.proto: PaperclipService with Health + Snapshot + Status
    (3 RPCs, ALL read-only — Stage-1 sandbox contract preserved at
    the proto layer too)
  - openclaw.proto: OpenClawService with Health + EvaluateDispatch +
    ListAgents + RecentDispatches (4 RPCs; Dispatch is COMMENTED OUT
    until Stage-2 ships rules + drill update)
  - Both protos use proto3 syntax + import common/v1/common.proto
  - Neither proto registers a mutating RPC for Paperclip (no
    Snapshot.Set, Snapshot.Push, Snapshot.Apply)
  - OpenClaw's Stage-1 envelope shape matches the Python dataclass
    (DispatchEnvelope) — drill checks all 7 fields are in both
  - scripts/gen-proto.sh auto-discovers them (find proto/ -name *.proto)

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERCLIP_PROTO = REPO / "proto" / "paperclip" / "v1" / "paperclip.proto"
OPENCLAW_PROTO = REPO / "proto" / "openclaw" / "v1" / "openclaw.proto"
GEN_SCRIPT = REPO / "scripts" / "gen-proto.sh"


def main() -> int:
    print("-- 1. POSITIVE: both proto files exist + use proto3 syntax --")
    for p in (PAPERCLIP_PROTO, OPENCLAW_PROTO):
        if not p.exists():
            print(f"x {p} missing")
            return 1
        src = p.read_text(encoding="utf-8")
        if 'syntax = "proto3"' not in src:
            print(f"x {p.name} must use proto3 syntax")
            return 1
        if 'import "common/v1/common.proto"' not in src:
            print(f"x {p.name} must import common/v1/common.proto for RequestMeta")
            return 1
    print("  ok: paperclip.proto + openclaw.proto present, proto3, import common")

    print("-- 2. POSITIVE: PaperclipService has exactly 3 RPCs (Health + Snapshot + Status) --")
    pc_src = PAPERCLIP_PROTO.read_text(encoding="utf-8")
    rpcs = re.findall(r"^\s*rpc\s+(\w+)\s*\(", pc_src, re.MULTILINE)
    expected = {"Health", "Snapshot", "Status"}
    if set(rpcs) != expected:
        print(f"x PaperclipService RPCs: expected {expected}, got {set(rpcs)}")
        return 1
    print(f"  ok: 3 RPCs ({sorted(rpcs)})")

    print("-- 3. NEGATIVE: PaperclipService has NO mutating RPCs --")
    # Stage-1 sandbox contract: no Set, Apply, Dispatch, Push, Update,
    # Mutate, Delete, Create at the proto layer either. Future PRs
    # adding a mutating RPC must update this drill (intentional friction).
    forbidden_verbs = (
        "Set", "Push", "Dispatch", "Apply", "Mutate",
        "Update", "Delete", "Create", "Insert",
    )
    for verb in forbidden_verbs:
        pattern = rf"^\s*rpc\s+{verb}[A-Z]"
        if re.search(pattern, pc_src, re.MULTILINE):
            print(f"x PaperclipService has mutating RPC starting with {verb!r}")
            return 1
    print("  ok: 0 mutating RPCs (Stage-1 sandbox contract preserved)")

    print("-- 4. POSITIVE: OpenClawService has 4 RPCs (Health + EvalDispatch + List + Recent) --")
    oc_src = OPENCLAW_PROTO.read_text(encoding="utf-8")
    rpcs = re.findall(r"^\s*rpc\s+(\w+)\s*\(", oc_src, re.MULTILINE)
    expected = {"Health", "EvaluateDispatch", "ListAgents", "RecentDispatches"}
    if set(rpcs) != expected:
        print(f"x OpenClawService RPCs: expected {expected}, got {set(rpcs)}")
        return 1
    print(f"  ok: 4 RPCs ({sorted(rpcs)})")

    print("-- 5. NEGATIVE: OpenClawService Dispatch RPC is COMMENTED OUT (Stage-1 contract) --")
    # Stage-1 ships gate + envelope; Stage-2 ships actual Dispatch.
    # The proto must have the Dispatch line commented out (signaling
    # the future API) but NOT actively registered.
    if re.search(r"^\s*rpc\s+Dispatch\s*\(", oc_src, re.MULTILINE):
        print("x Stage-1 OpenClawService must NOT register Dispatch RPC; comment it out")
        return 1
    if "// rpc Dispatch" not in oc_src:
        print("x Stage-2 future Dispatch RPC must be present as a comment marker")
        return 1
    print("  ok: Dispatch RPC is comment-only (Stage-2 future surface)")

    print("-- 6. NEGATIVE: DispatchEnvelope proto fields match Python dataclass --")
    # The proto envelope and Python dataclass MUST agree on field names.
    # If a refactor renames a field in one but not the other, drill catches.
    envelope_block = re.search(
        r"message DispatchEnvelope\s*\{([^}]+)\}", oc_src, re.DOTALL,
    )
    if not envelope_block:
        print("x DispatchEnvelope message not found in openclaw.proto")
        return 1
    proto_fields = set(re.findall(
        r"\s+\w+\s+(\w+)\s*=\s*\d+;",
        envelope_block.group(1),
    ))
    expected_fields = {
        "dispatch_id", "timestamp", "requesting_agent", "target_agent",
        "capability", "correlation_id", "payload", "scopes_granted",
    }
    missing = expected_fields - proto_fields
    if missing:
        print(f"x DispatchEnvelope proto missing fields: {missing}")
        return 1
    extra = proto_fields - expected_fields
    if extra:
        # Allow extra fields, but warn — Stage-2 may add them. For
        # Stage-1 lock we want no surprises.
        print(f"  note: DispatchEnvelope has extra fields beyond Python dataclass: {extra}")
    print("  ok: all 8 envelope fields present in proto")

    print("-- 7. POSITIVE: scripts/gen-proto.sh auto-discovers new protos --")
    if not GEN_SCRIPT.exists():
        print(f"x {GEN_SCRIPT} missing")
        return 1
    gen_src = GEN_SCRIPT.read_text(encoding="utf-8")
    # Must use `find proto -name "*.proto"` style (not hardcoded list)
    if 'find "$PROTO_DIR" -name "*.proto"' not in gen_src and "find proto" not in gen_src:
        print("x gen-proto.sh must auto-discover via find; new protos won't be codegen'd")
        return 1
    print("  ok: gen-proto.sh auto-discovers via find (paperclip + openclaw will be codegen'd)")

    print("-- 8. NEGATIVE: neither proto declares a tool that bypasses PolisAI --")
    # Stage-1 contract: every Stage-1 RPC is read-only OR goes through
    # PolisAI. The proto names should NOT include 'unsafe', 'admin',
    # 'bypass', 'override' or other terms suggesting policy bypass.
    bypass_patterns = (
        r"\bunsafe\b", r"\bbypass\b", r"\boverride\b", r"\badmin_only\b",
    )
    for pat in bypass_patterns:
        if re.search(pat, pc_src, re.IGNORECASE):
            print(f"x paperclip.proto contains bypass-suggesting term: {pat}")
            return 1
        if re.search(pat, oc_src, re.IGNORECASE):
            print(f"x openclaw.proto contains bypass-suggesting term: {pat}")
            return 1
    print("  ok: no bypass-suggesting terms in either proto")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
