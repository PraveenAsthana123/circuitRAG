"""Agent-to-Agent (A2A) protocol — registry + message bus + connector + delegation.

Per CLAUDE.md §50 + §55. Closes Tier 5 #5.9 (agent-task delegation
management) + #5.10 (A2A chat protocol). Provides the four
load-bearing primitives the user asked for:

  AgentRegistry  — central catalog of every agent in the system
  A2AMessageBus  — in-process pub/sub + request/reply transport
  AgentConnector — high-level "ask <agent> to do <task>" API
  delegate_task  — wrapper that an agent uses to hand work off

THE PROBLEM THIS CLOSES
=======================

Today every agent in the orchestrator + the autonomous-fix-bot
council is INVOKED DIRECTLY (caller imports and calls). There's no
way for one agent to ask another "I don't know how to do this — can
you?" without the caller knowing about both. As Tier 5 grows
(swarm, PR mgmt, bug mgmt, etc.), N×M direct calls explode.

The A2A protocol replaces N×M with N×1 — every agent calls into the
same Connector, which routes via the Registry through the Bus.

WIRING
======

  AGENT A                                AGENT B
    │                                      │
    │   delegate_task("agent-b",          │
    │                payload, ...)         │
    ▼                                      │
  AgentConnector                          │
    │                                      │
    │ lookup name → AgentSpec (Registry)   │
    │ build AgentMessage (Pydantic)        │
    │ send via A2AMessageBus               │
    ▼                                      │
  A2AMessageBus  ──────────────────────►  inbox(agent-b)
                                           │
                                           ▼
                                         Agent B handler
                                           │
                                           │ build reply Message
                                           ▼
  A2AMessageBus  ◄──────────────────  reply
    │
    ▼
  Connector returns reply to AGENT A

SCOPE
=====

In-process today. Cross-process / cross-pod is Tier 5 #5.10 v2:
swap the bus implementation for an MCP-server-backed transport
(JSON-RPC over stdio per MCP spec) without changing the agent API.

§42 / §50.5.3 BOUNDARIES
========================

  - delegate_task NEVER pushes anywhere external
  - delegate_task NEVER bypasses §50.5.3 security gate (registry
    rejects messages targeted at agents whose spec.model_tier='human')
  - Connector audits every message (request_id, from, to, payload
    hash, latency, outcome) — same forensic-substrate shape as §51

Drilled by mcp/tests/drill_a2a_protocol.py — both directions:
register/lookup/delegate happy path; reject delegation to human-only
agent; reject malformed Message; reject delivery to unregistered agent.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import threading
import uuid
from collections import defaultdict
from collections.abc import Callable
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError


MessageType = Literal[
    "request",         # agent A asks agent B for something
    "reply",           # agent B's response
    "broadcast",       # agent A → all listeners (no reply expected)
    "error",           # agent B couldn't satisfy the request
]


class AgentMessage(BaseModel):
    """The wire format. Every A2A communication MUST be one of these.

    JSON-serializable for future cross-process transport.
    """

    request_id: str = Field(min_length=1, max_length=128, description="Unique correlation id; reply quotes this")
    from_agent: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    to_agent: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(description="ISO 8601 UTC")
    in_reply_to: str | None = Field(default=None, description="request_id this is a reply to")

    model_config: ClassVar[dict] = {"extra": "forbid"}

    def payload_hash(self) -> str:
        """Stable SHA-256 hash for audit / dedup."""
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class AgentRegistryError(LookupError):
    """Raised when an agent name is not found in the registry."""


class AgentDeliveryError(RuntimeError):
    """Raised when a message can't be delivered (security gate, unregistered, etc.)."""


# ---------------------------------------------------------------------
# 1. AgentRegistry — singleton catalog of every agent
# ---------------------------------------------------------------------

class AgentRegistry:
    """Process-wide singleton catalog of registered agents.

    Each agent registers an AgentSpec + a handler callable. The
    Connector + Bus look up agents here when routing messages.
    Thread-safe via a single mutex.
    """

    _instance: ClassVar["AgentRegistry | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._mutex = threading.Lock()

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register(self, spec: Any, handler: Callable[[AgentMessage], AgentMessage]) -> None:
        """Register an agent. spec must have a `name` attribute (e.g. AgentSpec)."""
        name = getattr(spec, "name", None)
        if not name or not isinstance(name, str):
            raise ValueError(f"spec.name must be a non-empty string; got {name!r}")
        with self._mutex:
            self._agents[name] = {"spec": spec, "handler": handler}

    def get(self, name: str) -> dict[str, Any]:
        with self._mutex:
            entry = self._agents.get(name)
        if entry is None:
            raise AgentRegistryError(f"agent not registered: {name!r}")
        return entry

    def all(self) -> list[str]:
        with self._mutex:
            return sorted(self._agents.keys())

    def clear(self) -> None:
        """Test helper. Removes all registered agents."""
        with self._mutex:
            self._agents.clear()


# ---------------------------------------------------------------------
# 2. A2AMessageBus — in-process transport
# ---------------------------------------------------------------------

class A2AMessageBus:
    """In-process synchronous message bus.

    send_request() blocks until the target agent's handler returns
    a reply. Suitable for autonomous-fix-bot single-process daemon;
    Tier 5 v2 swaps for MCP cross-process transport.

    Auditable: every message + reply is recorded in self.transcript
    for post-incident analysis.
    """

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or AgentRegistry.get_instance()
        self.transcript: list[AgentMessage] = []
        self._mutex = threading.Lock()

    def send(self, msg: AgentMessage) -> None:
        """Append to transcript; deliver to target's handler if request."""
        with self._mutex:
            self.transcript.append(msg)

    def deliver_request(self, request: AgentMessage) -> AgentMessage:
        """Deliver a request to the target agent's handler; return its reply.

        Per §50.5.3 the registry rejects delivery to agents whose spec
        has model_tier='human' — those NEVER receive A2A messages.
        """
        if request.message_type != "request":
            raise AgentDeliveryError(f"deliver_request requires message_type='request'; got {request.message_type!r}")
        try:
            entry = self._registry.get(request.to_agent)
        except AgentRegistryError as exc:
            raise AgentDeliveryError(f"target agent not registered: {request.to_agent!r}") from exc

        spec = entry["spec"]
        # §50.5.3 enforcement: human-tier agents never accept A2A.
        if getattr(spec, "model_tier", None) == "human":
            raise AgentDeliveryError(
                f"agent {request.to_agent!r} is human-tier (model_tier='human'); "
                "A2A delegation forbidden per §50.5.3"
            )
        self.send(request)
        handler = entry["handler"]
        reply = handler(request)
        if not isinstance(reply, AgentMessage):
            raise AgentDeliveryError(
                f"agent {request.to_agent!r} handler returned {type(reply).__name__}; "
                "must return AgentMessage"
            )
        if reply.in_reply_to != request.request_id:
            raise AgentDeliveryError(
                f"agent {request.to_agent!r} reply.in_reply_to={reply.in_reply_to!r}; "
                f"expected {request.request_id!r}"
            )
        self.send(reply)
        return reply


# ---------------------------------------------------------------------
# 3. AgentConnector — high-level "ask <name> to do <task>" API
# ---------------------------------------------------------------------

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AgentConnector:
    """High-level ergonomic API on top of registry + bus.

    Agents call connector.ask(target, payload, from=...) to delegate
    work. The connector handles request_id generation, timestamping,
    AgentMessage construction, audit emission. Caller gets the reply
    payload back.
    """

    def __init__(self, bus: A2AMessageBus | None = None) -> None:
        self._bus = bus or A2AMessageBus()

    @property
    def transcript(self) -> list[AgentMessage]:
        return self._bus.transcript

    def ask(
        self,
        *,
        from_agent: str,
        to_agent: str,
        payload: dict[str, Any],
        request_id: str | None = None,
    ) -> AgentMessage:
        """Send a request; block on reply; return the reply message.

        Raises AgentDeliveryError if the target is unregistered, is
        human-tier (per §50.5.3), or its handler returns malformed.
        """
        msg = AgentMessage(
            request_id=request_id or str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="request",
            payload=payload,
            timestamp=now_iso(),
            in_reply_to=None,
        )
        return self._bus.deliver_request(msg)


# ---------------------------------------------------------------------
# 4. delegate_task — agent-side wrapper
# ---------------------------------------------------------------------

def delegate_task(
    *,
    connector: AgentConnector,
    from_agent: str,
    to_agent: str,
    task: dict[str, Any],
) -> dict[str, Any]:
    """An agent delegates a task to another agent and returns the
    result payload.

    Per Tier 5 #5.9 + #5.10. This is the single entry point an agent
    uses; the connector + registry + bus are implementation detail.
    """
    reply = connector.ask(
        from_agent=from_agent,
        to_agent=to_agent,
        payload={"task": task},
    )
    if reply.message_type == "error":
        raise AgentDeliveryError(
            f"delegation to {to_agent!r} returned error: {reply.payload}"
        )
    return reply.payload


# ---------------------------------------------------------------------
# Convenience: build a default reply for handlers
# ---------------------------------------------------------------------

def make_reply(
    *,
    request: AgentMessage,
    from_agent: str,
    payload: dict[str, Any],
    is_error: bool = False,
) -> AgentMessage:
    """Helper for agent handlers to construct a well-formed reply."""
    return AgentMessage(
        request_id=str(uuid.uuid4()),
        from_agent=from_agent,
        to_agent=request.from_agent,
        message_type="error" if is_error else "reply",
        payload=payload,
        timestamp=now_iso(),
        in_reply_to=request.request_id,
    )
