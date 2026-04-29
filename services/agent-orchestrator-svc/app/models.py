from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    tenant_id: str = Field(min_length=1)
    project_id: str | None = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    use_global_policy: bool = True
    require_human_approval: bool | None = None
    approval_mode: Literal["manual", "plan_once", "policy_auto"] | None = None
    auto_advance: bool | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    approved: bool
    actor_id: str = Field(min_length=1)
    reason: str | None = None


class TaskView(BaseModel):
    task_id: str
    tenant_id: str
    project_id: str | None = None
    goal: str
    status: str
    risk_level: str
    require_human_approval: bool = False
    approval_mode: str = "manual"
    auto_advance: bool = True
    approved: bool | None = None
    confidence: float | None = None
    plan: list[str] = Field(default_factory=list)
    worker_output: str | None = None
    reviewer_notes: list[str] = Field(default_factory=list)
    advisor_summary: str | None = None
    next_action: str | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    approval_reasons: list[str] = Field(default_factory=list)
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


class AgenticPolicyView(BaseModel):
    require_human_approval: bool = False
    approval_mode: Literal["manual", "plan_once", "policy_auto"] = "plan_once"
    auto_advance: bool = True
    require_for_high_risk: bool = True
    require_for_low_confidence: bool = True
    confidence_threshold: float = 0.8
    require_for_risk_flags: bool = True
    require_for_destructive_tools: bool = True
    require_for_tool_namespaces: list[str] = Field(default_factory=lambda: ["identity", "finops", "itsm"])
    updated_by: str | None = None
    updated_at: str | None = None


class AgenticPolicyUpdateRequest(BaseModel):
    require_human_approval: bool
    approval_mode: Literal["manual", "plan_once", "policy_auto"]
    auto_advance: bool
    require_for_high_risk: bool
    require_for_low_confidence: bool
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    require_for_risk_flags: bool
    require_for_destructive_tools: bool
    require_for_tool_namespaces: list[str] = Field(default_factory=list)
    updated_by: str = Field(min_length=1)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4000)
    tenant_id: str = Field(min_length=1)
    use_global_policy: bool = True
    policy_override: AgenticPolicyUpdateRequest | None = None


class ProjectPlanItem(BaseModel):
    step_id: str
    title: str
    goal: str
    suggested_risk: Literal["low", "medium", "high"] = "medium"
    tool_namespace: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = "planned"
    task_id: str | None = None


class ProjectView(BaseModel):
    project_id: str
    tenant_id: str
    name: str
    goal: str
    status: str
    use_global_policy: bool = True
    task_ids: list[str] = Field(default_factory=list)
    planned_tasks: list[ProjectPlanItem] = Field(default_factory=list)
    policy_override: AgenticPolicyView | None = None
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalSimulationRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    goal: str = Field(min_length=1, max_length=4000)
    risk_level: Literal["low", "medium", "high"] = "medium"
    project_id: str | None = None
    use_global_policy: bool = True
    require_human_approval: bool | None = None
    approval_mode: Literal["manual", "plan_once", "policy_auto"] | None = None
    auto_advance: bool | None = None
    tool_namespace: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    predicted_confidence: float = Field(default=0.78, ge=0.0, le=1.0)
    predicted_risks: list[str] = Field(default_factory=list)


class ApprovalSimulationResponse(BaseModel):
    effective_policy: AgenticPolicyView
    approval_reasons: list[str]
    approval_required: bool


class AgentRoleView(BaseModel):
    role_id: str
    role_type: str
    display_name: str
    model: str
    description: str
    source_agent_name: str | None = None
