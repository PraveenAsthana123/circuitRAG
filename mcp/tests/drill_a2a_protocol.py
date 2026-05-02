#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: A2A protocol — registry + bus + connector + delegation.

Per CLAUDE.md §43 + §55. Locks the contract for Tier 5 #5.9 + #5.10:
the four primitives (AgentRegistry / A2AMessageBus / AgentConnector
/ delegate_task) compose end-to-end with both directions:

  - happy path: register two agents → A delegates to B → reply received
  - reject path: delegation to unregistered agent
  - reject path: delegation to human-tier agent (§50.5.3)
  - reject path: handler returns non-AgentMessage
  - reject path: handler reply.in_reply_to mismatched
  - schema:    extra fields rejected; bad name pattern rejected

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / "libs" / "py" / "documind_core" / "a2a_protocol.py"


def _load():
    spec = importlib.util.spec_from_file_location("a2a_protocol", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["a2a_protocol"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: a2a_protocol imports + 8 exports --")
    a2a = _load()
    for name in ("AgentMessage", "AgentRegistry", "A2AMessageBus",
                 "AgentConnector", "AgentRegistryError",
                 "AgentDeliveryError", "delegate_task", "make_reply"):
        if not hasattr(a2a, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: 8 exports present")

    # Build a fresh registry + bus + connector for the drill.
    registry = a2a.AgentRegistry()
    bus = a2a.A2AMessageBus(registry=registry)
    connector = a2a.AgentConnector(bus=bus)

    # Two stub specs + handlers.
    class StubSpec:
        def __init__(self, name: str, model_tier: str = "default"):
            self.name = name
            self.model_tier = model_tier

    def echo_handler(request: a2a.AgentMessage) -> a2a.AgentMessage:
        return a2a.make_reply(
            request=request,
            from_agent=request.to_agent,
            payload={"echoed": request.payload},
        )

    print("-- 2. POSITIVE: register + delegate happy path round-trip --")
    registry.register(StubSpec("agent-a"), echo_handler)
    registry.register(StubSpec("agent-b"), echo_handler)
    if registry.all() != ["agent-a", "agent-b"]:
        print(f"x step 2: registry.all() unexpected: {registry.all()}")
        return 1
    result = a2a.delegate_task(
        connector=connector,
        from_agent="agent-a",
        to_agent="agent-b",
        task={"do": "process", "value": 42},
    )
    if result.get("echoed", {}).get("task", {}).get("value") != 42:
        print(f"x step 2: delegated payload not echoed: {result}")
        return 1
    print(f"  ok: delegate_task round-trip; transcript len={len(connector.transcript)}")

    print("-- 3. NEGATIVE: delegation to unregistered agent → AgentDeliveryError --")
    try:
        a2a.delegate_task(
            connector=connector,
            from_agent="agent-a",
            to_agent="agent-zzz-nonexistent",
            task={},
        )
    except a2a.AgentDeliveryError:
        print("  ok: unregistered target rejected at delivery time")
    else:
        print("x step 3: delegation to unregistered agent succeeded")
        return 1

    print("-- 4. NEGATIVE: delegation to human-tier agent → AgentDeliveryError (§50.5.3) --")
    registry.register(StubSpec("agent-human", model_tier="human"), echo_handler)
    try:
        a2a.delegate_task(
            connector=connector,
            from_agent="agent-a",
            to_agent="agent-human",
            task={},
        )
    except a2a.AgentDeliveryError as e:
        if "§50.5.3" not in str(e) and "human" not in str(e).lower():
            print(f"x step 4: error message should cite §50.5.3 or 'human': {e}")
            return 1
        print("  ok: human-tier target rejected; §50.5.3 enforced")
    else:
        print("x step 4: delegation to human-tier agent succeeded (§50.5.3 violation)")
        return 1

    print("-- 5. NEGATIVE: handler returning non-AgentMessage → AgentDeliveryError --")
    def bad_handler(request: a2a.AgentMessage) -> str:  # type: ignore[return-value]
        return "not a Message"
    registry.register(StubSpec("agent-bad-return"), bad_handler)
    try:
        a2a.delegate_task(
            connector=connector,
            from_agent="agent-a",
            to_agent="agent-bad-return",
            task={},
        )
    except a2a.AgentDeliveryError as e:
        if "AgentMessage" not in str(e):
            print(f"x step 5: error should mention AgentMessage; got: {e}")
            return 1
        print("  ok: non-AgentMessage handler return rejected")
    else:
        print("x step 5: bad handler return-type slipped through")
        return 1

    print("-- 6. NEGATIVE: handler returning wrong in_reply_to → AgentDeliveryError --")
    def wrong_reply_handler(request: a2a.AgentMessage) -> a2a.AgentMessage:
        return a2a.AgentMessage(
            request_id=str(__import__("uuid").uuid4()),
            from_agent=request.to_agent,
            to_agent=request.from_agent,
            message_type="reply",
            payload={},
            timestamp=a2a.now_iso(),
            in_reply_to="wrong-correlation-id",  # mismatched
        )
    registry.register(StubSpec("agent-wrong-reply"), wrong_reply_handler)
    try:
        a2a.delegate_task(
            connector=connector,
            from_agent="agent-a",
            to_agent="agent-wrong-reply",
            task={},
        )
    except a2a.AgentDeliveryError as e:
        if "in_reply_to" not in str(e):
            print(f"x step 6: error should mention in_reply_to: {e}")
            return 1
        print("  ok: mismatched in_reply_to rejected (correlation broken)")
    else:
        print("x step 6: mismatched correlation slipped through")
        return 1

    print("-- 7. NEGATIVE: AgentMessage with extra field → ValidationError --")
    try:
        a2a.AgentMessage.model_validate({
            "request_id": "x",
            "from_agent": "agent-a",
            "to_agent": "agent-b",
            "message_type": "request",
            "payload": {},
            "timestamp": a2a.now_iso(),
            "operator_pii": "praveen@example.com",  # extra field
        })
    except Exception:
        print("  ok: extra field rejected; PII contamination blocked")
    else:
        print("x step 7: extra field accepted")
        return 1

    print("-- 8. NEGATIVE: AgentMessage with bad name pattern → ValidationError --")
    try:
        a2a.AgentMessage.model_validate({
            "request_id": "x",
            "from_agent": "AGENT_A",  # uppercase rejected
            "to_agent": "agent-b",
            "message_type": "request",
            "payload": {},
            "timestamp": a2a.now_iso(),
        })
    except Exception:
        print("  ok: 'AGENT_A' (uppercase) rejected by name pattern")
    else:
        print("x step 8: invalid name accepted")
        return 1

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
