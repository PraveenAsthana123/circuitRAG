#!/usr/bin/env python3
"""Paperclip Stage-3 — dispatcher composes propose + openclaw.dispatch.

Per CLAUDE.md §44 + §47. Stage-3 promotion of Paperclip: the
sandbox-only manager (Stage-1 read-only / Stage-2 propose-only)
gains a SEPARATE dispatcher module that routes proposed tasks
through OpenClaw.dispatch().

Why a SEPARATE file: paperclip_manager.py is drill-locked (per
drill_paperclip_stage1.py step 3) to forbid `def dispatch_*` /
`def push_*` etc. in its source. The sandbox contract is non-
negotiable. Stage-3 dispatch lives HERE; paperclip_manager
remains pure read+suggest.

Stage-3 contract:
  - Default DISABLED (PAPERCLIP_DISPATCH_ENABLED=1 opt-in)
  - Calls paperclip_manager.propose_next_task() to get a proposal
  - On allow → routes through openclaw_coordinator.dispatch()
  - Returns merged result: {proposal, dispatch_result}
  - Stage-1 sandbox of paperclip_manager untouched
  - All existing gates fire (PolisAI in OpenClaw + MCP gateway)

Same opt-in pattern as KAFKA_PUBLISH / LITELLM_ENABLED /
PYDANTICAI_ENABLED / AGENT_ROUTER_OLLAMA_ENABLED / MCP_GATEWAY_*.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

# Stage-3 opt-in — same pattern as the other adapter feature flags.
PAPERCLIP_DISPATCH_ENABLED = os.getenv("PAPERCLIP_DISPATCH_ENABLED", "").strip() == "1"


class PaperclipDispatchDisabled(RuntimeError):
    """Stage-3 default — dispatcher not enabled (PAPERCLIP_DISPATCH_ENABLED!=1)."""


@dataclass
class CombinedResult:
    """Stage-3 dispatch result — combines proposal + dispatch outcome."""
    ok: bool
    proposal: dict[str, Any] | None
    dispatch_result: dict[str, Any] | None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Check if dispatch is enabled (feature flag)."""
    return PAPERCLIP_DISPATCH_ENABLED


def dispatch_next_task() -> CombinedResult:
    """Stage-3 — propose + dispatch in one call.

    Flow:
      1. Check feature flag (PAPERCLIP_DISPATCH_ENABLED=1) — raise if off
      2. Get proposal from paperclip_manager.propose_next_task()
      3. If no proposable issue → CombinedResult(ok=False, no dispatch)
      4. Route through openclaw_coordinator.dispatch():
         - actor = "paperclip:manager" (the dispatcher's identity)
         - target = proposal["recommended_actor"]
         - capability = inferred from proposal (e.g., "propose_fix")
      5. Return CombinedResult with both proposal + dispatch_result

    Raises:
      PaperclipDispatchDisabled when feature flag is off

    Stage-3 deliberate scope: this is the COMPOSITION; the actual
    transport is still Stage-2 no-op (per OpenClaw Stage-2). Stage-4
    will land when each agent is exposed as an MCP server and
    OpenClaw's transport becomes real RPC.
    """
    if not is_available():
        raise PaperclipDispatchDisabled(
            "PAPERCLIP_DISPATCH_ENABLED!=1 — Stage-3 dispatch is opt-in. "
            "Set the env var to enable."
        )

    # Lazy imports — match the rest of the adapter pattern
    sys.path.insert(0, str(REPO / "scripts"))
    from openclaw_coordinator import (  # noqa: PLC0415
        CapabilityNotSupportedError,
        UnknownAgentError,
    )
    from openclaw_coordinator import dispatch as oc_dispatch  # noqa: PLC0415
    from paperclip_manager import propose_next_task  # noqa: PLC0415

    proposal_doc = propose_next_task()
    proposal = proposal_doc.get("proposal")
    if proposal is None:
        return CombinedResult(
            ok=False,
            proposal=None,
            dispatch_result=None,
            reason=(
                "no proposable issue (checklist empty or all candidates "
                "rejected); nothing to dispatch"
            ),
        )

    # Map proposal → openclaw dispatch arguments. The proposal's
    # recommended_actor maps to OpenClaw's target_agent. Capability is
    # heuristically derived from the proposal's recommended_lane.
    target = proposal.get("recommended_actor", "operator:human")
    lane = proposal.get("recommended_lane", "human-review")
    capability = (
        "propose_fix" if "council:author" in target
        else "critique_proposal" if "council:reviewer" in target
        else "read_snapshot" if target == "paperclip:manager"
        else "approve"  # operator path
    )

    try:
        dispatch_result = oc_dispatch(
            requesting_agent="paperclip:manager",
            target_agent=target,
            capability=capability,
            scopes_granted=["paperclip:dispatch"],
            payload={
                "proposal": proposal,
                "lane": lane,
                "rationale": proposal.get("rationale", ""),
            },
        )
    except (UnknownAgentError, CapabilityNotSupportedError) as exc:
        return CombinedResult(
            ok=False,
            proposal=proposal,
            dispatch_result=None,
            reason=f"openclaw refused dispatch: {exc.__class__.__name__}: {exc}",
        )

    return CombinedResult(
        ok=dispatch_result.ok,
        proposal=proposal,
        dispatch_result=dispatch_result.to_dict(),
        reason=(
            f"dispatched via openclaw → {target}; capability={capability}; "
            f"openclaw_ok={dispatch_result.ok}"
        ),
    )


def status() -> dict[str, Any]:
    """Operator-readable health/config dump."""
    return {
        "stage": 3,
        "available": is_available(),
        "feature_flag": PAPERCLIP_DISPATCH_ENABLED,
        "note": (
            "Stage-3 — composes paperclip_manager.propose_next_task() + "
            "openclaw_coordinator.dispatch(). Set PAPERCLIP_DISPATCH_ENABLED=1 "
            "to enable. Default disabled. The actual transport is still "
            "Stage-2 no-op (OpenClaw Stage-2 contract); Stage-4 lands real "
            "RPC when agents become MCP servers."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="paperclip_dispatcher")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show dispatcher status")
    sub.add_parser("dispatch", help="Run dispatch_next_task (requires flag)")

    args = parser.parse_args()

    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0

    if args.cmd == "dispatch":
        try:
            result = dispatch_next_task()
        except PaperclipDispatchDisabled as exc:
            print(json.dumps({
                "ok": False,
                "error_code": "PAPERCLIP_DISPATCH_DISABLED",
                "message": str(exc),
            }, indent=2))
            return 2
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0 if result.ok else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
