"""Risk classifier — pure function over (action, type, description).

Replaces the manual ``risk`` field on a task with a server-side
classification. Operators can still override with an explicit
``risk_override`` value, but the audit trail records BOTH (override +
classified) so a regulator can see when humans disagreed with the model.

Design:
- KEYWORD-based, deterministic, drillable
- 4-tier output: low / medium / high / critical
- Stage-2 (later): LLM fallback when keywords are ambiguous

Composes with §38 governance + §47 architecture.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

RiskLevel = Literal["low", "medium", "high", "critical"]


# Order matters — most-severe first. First match wins.
CRITICAL_PATTERNS = [
    re.compile(r"\b(rm\s+-rf|drop\s+(database|table)|truncate\s+table)\b", re.I),
    re.compile(r"\b(force.?push.+main|delete.+(production|prod))\b", re.I),
    re.compile(r"\b(modify\s+security|delete\s+(history|audit))\b", re.I),
]

HIGH_PATTERNS = [
    re.compile(r"\b(deploy.+(prod|production)|production\s+deploy)\b", re.I),
    re.compile(r"\b(delete\s+(file|data)|access\s+secret)\b", re.I),
    re.compile(r"\b(infra(structure)?\s+change|policy\s+change)\b", re.I),
    re.compile(r"\b(send.+external|external\s+(email|api))\b", re.I),
    re.compile(r"\b(billing|payment|invoice)\b", re.I),
]

MEDIUM_PATTERNS = [
    re.compile(r"\b(refactor|migration|schema\s+change)\b", re.I),
    re.compile(r"\b(file\s+write|code\s+merge|new\s+endpoint)\b", re.I),
    re.compile(r"\b(modif(y|ying)|chang(e|ing)|updat(e|ing))\b", re.I),
    re.compile(r"\b(rewrite|restructur)\b", re.I),
]

# Action → minimum-risk floor. The classifier picks the MAX of
# (keyword-derived risk, action-floor).
ACTION_FLOORS: dict[str, RiskLevel] = {
    "delete_system_file": "critical",
    "delete_history": "critical",
    "delete_audit": "critical",
    "modify_os_config": "critical",
    "force_push_main": "critical",
    "run_destructive_command": "critical",
    "modify_security_policy_without_approval": "critical",

    "code_merge": "high",
    "deploy_production": "high",
    "delete_file": "high",
    "delete_data": "high",
    "modify_security_policy": "high",
    "infrastructure_change": "high",
    "permission_change": "high",
    "access_secret": "high",
    "send_external_email": "high",
    "modify_billing": "high",
    "file_write": "medium",

    "recommendation": "low",
    "research": "low",
    "documentation": "low",
}

TYPE_FLOORS: dict[str, RiskLevel] = {
    "production_deploy": "critical",
    "secret_change": "high",
    "policy_change": "high",
    "external_communication": "high",
    "code_merge": "high",
    "delete_file": "high",
    "infrastructure_change": "high",

    "documentation_update": "low",
    "plan_creation": "low",
    "research_summary": "low",
    "test_report": "low",
    "dashboard_update": "low",
    "recommendation": "low",
    "code_suggestion": "low",
}

_RANK: dict[RiskLevel, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_LEVEL_BY_RANK: dict[int, RiskLevel] = {v: k for k, v in _RANK.items()}


@dataclass
class RiskAssessment:
    level: RiskLevel
    score: int  # 1-4 (= rank)
    triggers: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)


def _max_level(*levels: RiskLevel) -> RiskLevel:
    n = max((_RANK[lvl] for lvl in levels), default=1)
    return _LEVEL_BY_RANK[n]


def _scan_patterns(text: str) -> tuple[RiskLevel, list[str]]:
    triggers: list[str] = []
    if not text:
        return "low", triggers
    for p in CRITICAL_PATTERNS:
        if p.search(text):
            triggers.append(f"critical_pattern:{p.pattern[:40]}")
            return "critical", triggers
    highest: RiskLevel = "low"
    for p in HIGH_PATTERNS:
        if p.search(text):
            triggers.append(f"high_pattern:{p.pattern[:40]}")
            highest = _max_level(highest, "high")
    for p in MEDIUM_PATTERNS:
        if p.search(text):
            triggers.append(f"medium_pattern:{p.pattern[:40]}")
            highest = _max_level(highest, "medium")
    return highest, triggers


def classify(
    *,
    action: str | None = None,
    task_type: str | None = None,
    description: str | None = None,
    title: str | None = None,
) -> RiskAssessment:
    """Classify risk from any subset of (action, task_type, text).

    Returns the MAXIMUM of:
      - action floor (if action is in ACTION_FLOORS)
      - type floor (if task_type is in TYPE_FLOORS)
      - keyword scan over description + title

    Default: ``low`` when no signal matches.
    """
    triggers: list[str] = []
    levels: list[RiskLevel] = ["low"]

    if action:
        a = action.lower().strip()
        if a in ACTION_FLOORS:
            levels.append(ACTION_FLOORS[a])
            triggers.append(f"action_floor:{a}={ACTION_FLOORS[a]}")

    if task_type:
        t = task_type.lower().strip()
        if t in TYPE_FLOORS:
            levels.append(TYPE_FLOORS[t])
            triggers.append(f"type_floor:{t}={TYPE_FLOORS[t]}")

    text = " ".join(s for s in (title, description) if s)
    text_level, text_trig = _scan_patterns(text)
    levels.append(text_level)
    triggers.extend(text_trig)

    final = _max_level(*levels)
    return RiskAssessment(
        level=final,
        score=_RANK[final],
        triggers=triggers,
        inputs={"action": action, "type": task_type,
                "description_chars": len(description or ""),
                "title_chars": len(title or "")},
    )


def classify_task(task: dict[str, Any]) -> RiskAssessment:
    """Convenience wrapper for the dict-shape used by ops_worker / cli."""
    return classify(
        action=task.get("action"),
        task_type=task.get("type"),
        description=task.get("description"),
        title=task.get("title"),
    )


__all__ = [
    "ACTION_FLOORS",
    "RiskAssessment",
    "RiskLevel",
    "TYPE_FLOORS",
    "classify",
    "classify_task",
]
