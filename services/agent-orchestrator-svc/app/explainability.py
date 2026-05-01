"""§48 explainability — assemble per-task decision audit rows (Phase C4).

Pure functions. Take a TaskView + list of TaskRunView and produce a
single dict matching the §48.4 audit row schema:

  request_id, timestamp, tenant_id, user_id, model_name, model_version,
  prompt_version, input_features, input_hash, prediction, confidence,
  explanation { method, top_features[], counterfactual },
  rules_applied[], guardrails_triggered[], human_override,
  fairness_flag, latency_ms, cost_tokens, feedback

What we CAN populate today (from existing data):
  request_id        ← task_id
  timestamp         ← task created_at
  tenant_id         ← task.tenant_id
  model_name        ← task_runs[*].routing_decision.chosen.model
  model_version     ← same
  prompt_version    ← phase name (each role has its own prompt template)
  input_features    ← task.goal + task.tool_namespace/tool_name/tool_arguments
  prediction        ← task.worker_output (or 'pending')
  confidence        ← task.confidence
  rules_applied     ← task.approval_reasons
  human_override    ← presence of approval row (proxy)
  cost_tokens       ← sum of task_runs[*].tokens_in + tokens_out
  cost_usd_cents    ← sum

What we CANNOT populate yet (placeholders, future phases):
  user_id           — auth not yet plumbed end-to-end
  input_hash        — TODO: hash the canonicalised goal+args
  explanation.method/top_features — needs SHAP/LIME (out of scope today)
  explanation.counterfactual — needs DiCE (out of scope)
  guardrails_triggered — only AdvisorAgent risks today; expand in B6
  fairness_flag     — needs §48.8 fairness gate (out of scope)
  latency_ms        — task_runs.duration_ms is per-phase; sum here
  feedback          — needs UX path (out of scope)

The endpoint exposes ALL fields with explicit None for placeholders so
the §48.4 schema is fully observable; no field is silently absent.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _hash_input(goal: str, tool_namespace: str | None, tool_name: str | None,
                tool_arguments: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"goal": goal, "ns": tool_namespace, "tool": tool_name, "args": tool_arguments},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assemble_explanation(*, task: dict[str, Any], task_runs: list[dict[str, Any]],
                         approvals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the §48.4 audit row dict.

    `task` and `task_runs` are dicts (TaskView.model_dump() and
    TaskRunView.model_dump()) — keeps this module decoupled from
    Pydantic so it's drillable in isolation.
    """
    approvals = approvals or []

    # Aggregate cost across runs.
    total_tokens_in = sum((r.get("tokens_in") or 0) for r in task_runs)
    total_tokens_out = sum((r.get("tokens_out") or 0) for r in task_runs)
    total_cost_cents = sum((r.get("cost_usd_cents") or 0) for r in task_runs)
    total_duration_ms = sum((r.get("duration_ms") or 0) for r in task_runs)

    # Pick the LAST routing_decision as authoritative; the loop may have
    # re-routed (B3 retry). The trail is in audit_events for forensics.
    last_routing = None
    for r in reversed(task_runs):
        rd = r.get("routing_decision")
        if rd:
            last_routing = rd
            break

    chosen_model = None
    chosen_backend = None
    chosen_tier = None
    if last_routing and isinstance(last_routing.get("chosen"), dict):
        chosen_model = last_routing["chosen"].get("model")
        chosen_backend = last_routing["chosen"].get("backend")
        chosen_tier = last_routing["chosen"].get("tier")

    # Input hash for reproducibility.
    input_hash = _hash_input(
        goal=task.get("goal", ""),
        tool_namespace=task.get("tool_namespace"),
        tool_name=task.get("tool_name"),
        tool_arguments=task.get("tool_arguments") or {},
    )

    # Human override = at least one approval recorded (proxy until
    # we have a richer override-event signal in C5+).
    human_override = bool(approvals)

    return {
        # Identity & context
        "request_id": task["task_id"],
        "timestamp": task.get("created_at") or task.get("audit_events", [{}])[0].get("at"),
        "tenant_id": task["tenant_id"],
        "user_id": None,  # placeholder — auth plumbing pending

        # Model identity
        "model_name": chosen_model,
        "model_version": chosen_model,  # same string until we add semver
        "prompt_version": task.get("status"),  # phase = prompt template id today
        "backend": chosen_backend,
        "tier": chosen_tier,

        # Input fingerprint
        "input_features": {
            "goal": task.get("goal"),
            "tool_namespace": task.get("tool_namespace"),
            "tool_name": task.get("tool_name"),
            "tool_arguments": task.get("tool_arguments") or {},
            "risk_level": task.get("risk_level"),
        },
        "input_hash": input_hash,

        # Decision
        "prediction": task.get("worker_output") or "pending",
        "confidence": task.get("confidence"),

        # Explanation (placeholders flagged — §48.10 surface ALL fields)
        "explanation": {
            "method": "routing_trail",  # post-§48.2 we add "shap" / "lime"
            "top_features": None,        # needs SHAP — future phase
            "counterfactual": None,      # needs DiCE — future phase
            "routing_trail": last_routing,
        },

        # Governance
        "rules_applied": task.get("approval_reasons") or [],
        "guardrails_triggered": _extract_guardrails(task),
        "human_override": human_override,
        "fairness_flag": None,  # §48.8 — future phase

        # Performance + cost
        "latency_ms": total_duration_ms,
        "cost_tokens": {
            "in": total_tokens_in,
            "out": total_tokens_out,
        },
        "cost_usd_cents": total_cost_cents,

        # Feedback (future)
        "feedback": None,
    }


def _extract_guardrails(task: dict[str, Any]) -> list[str]:
    """Extract guardrail signals from audit_events. Today: just the
    approval_reasons + any audit event with role='security_advisor' + risk."""
    triggered: list[str] = []
    for evt in task.get("audit_events") or []:
        role = evt.get("role")
        event = evt.get("event")
        if role == "security_advisor" and event:
            triggered.append(f"security_advisor:{event}")
        if evt.get("approval_reasons"):
            triggered.extend(evt["approval_reasons"])
    return list(dict.fromkeys(triggered))  # preserve order, dedupe


# §48.4 schema — every key MUST be present in the response, even if None.
# Drill enforces this.
REQUIRED_AUDIT_FIELDS = (
    "request_id", "timestamp", "tenant_id", "user_id",
    "model_name", "model_version", "prompt_version", "backend", "tier",
    "input_features", "input_hash",
    "prediction", "confidence",
    "explanation",
    "rules_applied", "guardrails_triggered", "human_override", "fairness_flag",
    "latency_ms", "cost_tokens", "cost_usd_cents",
    "feedback",
)
