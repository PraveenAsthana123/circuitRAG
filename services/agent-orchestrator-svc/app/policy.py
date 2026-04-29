from __future__ import annotations

from typing import Any

from .models import AgenticPolicyView


DESTRUCTIVE_VERBS = ("delete", "remove", "drop", "grant", "revoke", "terminate", "disable", "reset", "update", "create")


def evaluate_approval_reasons(state: dict[str, Any], policy: AgenticPolicyView) -> list[str]:
    reasons: list[str] = []

    if state.get("require_human_approval"):
        reasons.append("explicit human approval required")

    if policy.require_for_high_risk and state.get("risk_level") == "high":
        reasons.append("high-risk task")

    confidence = state.get("confidence")
    if policy.require_for_low_confidence and isinstance(confidence, (int, float)) and confidence < policy.confidence_threshold:
        reasons.append(f"confidence below threshold ({confidence:.2f} < {policy.confidence_threshold:.2f})")

    namespace = (state.get("tool_namespace") or "").strip()
    if namespace and namespace in set(policy.require_for_tool_namespaces):
        reasons.append(f"sensitive tool namespace: {namespace}")

    tool_name = (state.get("tool_name") or "").strip().lower()
    if policy.require_for_destructive_tools and tool_name and any(verb in tool_name for verb in DESTRUCTIVE_VERBS):
        reasons.append(f"destructive or write-capable tool: {tool_name}")

    if policy.require_for_risk_flags:
        for risk in _collect_risks(state):
            reasons.append(f"risk flag: {risk}")

    return _dedupe(reasons)


def _collect_risks(state: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for key in ("worker_risks", "reviewer_risks", "advisor_risks"):
        values = state.get(key) or []
        if isinstance(values, list):
            risks.extend(str(value) for value in values if value)
    return risks


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
