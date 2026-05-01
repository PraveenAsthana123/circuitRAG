from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRoleSpec:
    role_id: str
    role_type: str
    display_name: str
    model: str
    description: str
    prompt_template: str
    source_agent_name: str | None = None


DEFAULT_AGENT_SPECS: tuple[AgentRoleSpec, ...] = (
    AgentRoleSpec(
        role_id="researcher",
        role_type="researcher",
        display_name="Researcher",
        model="qwen2.5:latest",
        description="Synthesises sources and suggests approach for novel topics.",
        source_agent_name="researcher",
        prompt_template=(
            "You are the Researcher for an agentic SDLC pipeline.\n"
            "Investigate the topic. Cite ≥3 sources. Identify risks.\n"
            "Suggest a concrete implementation approach.\n"
            "\n"
            "Topic / goal:\n{goal}\n"
            "\n"
            "Respond with ONLY a JSON object on one line:\n"
            "{{\"summary\":\"<one paragraph>\",\"sources\":[{{\"title\":\"<t>\","
            "\"url\":\"<u>\",\"relevance\":\"<why>\"}}],"
            "\"suggested_approach\":\"<actionable steps>\","
            "\"risks\":[\"<risk1>\",\"<risk2>\"]}}\n"
        ),
    ),
    AgentRoleSpec(
        role_id="strategist",
        role_type="planner",
        display_name="Strategist",
        model="qwen2.5:latest",
        description="Classifies the task into per-step complexity/novelty; sets routing tier for downstream nodes.",
        source_agent_name="strategist",
        prompt_template=(
            "You are the Strategist for an agentic SDLC pipeline.\n"
            "Classify the task into a sequence of pipeline steps.\n"
            "For EACH step, decide:\n"
            "  - complexity: trivial | medium | high\n"
            "  - novelty: routine | novel\n"
            "  - needs_research: true | false (true if topic is unfamiliar)\n"
            "\n"
            "STRICT RULES:\n"
            "  1. deploy steps MUST be complexity=high (never trivial)\n"
            "  2. anything touching auth/secrets MUST be novelty=novel\n"
            "  3. routine bugfix → mark needs_research=false\n"
            "\n"
            "Goal:\n{goal}\n"
            "\n"
            "Respond with ONLY a JSON object on one line:\n"
            "{{\"steps\":[{{\"step_id\":\"<id>\",\"complexity\":\"<level>\","
            "\"novelty\":\"<level>\",\"needs_research\":<bool>}}],"
            "\"overall_complexity\":\"<level>\",\"overall_novelty\":\"<level>\","
            "\"needs_research\":<bool>,\"summary\":\"<one-sentence>\"}}\n"
        ),
    ),
    AgentRoleSpec(
        role_id="coder_executor",
        role_type="coder",
        display_name="Coder executor",
        model="deepseek-coder:6.7b-instruct",
        description="Primary implementation agent for bounded code and task execution work.",
        source_agent_name="code_reviewer",
        prompt_template=(
            "You are the Coder Executor for an agentic software-delivery workflow.\n"
            "Produce a concrete, bounded execution result for the goal below.\n"
            "Be explicit about assumptions, implementation steps, risks, and next actions.\n"
            "When code changes are implied, describe the intended patch at a high level.\n\n"
            "Tenant: {tenant_id}\n"
            "Goal:\n{goal}\n\n"
            "Tool context:\n{tool_context}\n\n"
            "Reply with:\n"
            "1. short execution summary\n"
            "2. proposed implementation/result\n"
            "3. risks\n"
            "4. next action\n"
        ),
    ),
    AgentRoleSpec(
        role_id="reviewer",
        role_type="reviewer",
        display_name="Reviewer",
        model="starcoder2:7b",
        description="Checks output quality, relevance, and actionability before handoff.",
        source_agent_name="consistency_check",
        prompt_template=(
            "You are the Reviewer in an agentic workflow.\n"
            "Review the worker output for correctness, completeness, clarity, and actionability.\n"
            "Call out concrete issues, not style trivia.\n\n"
            "Goal:\n{goal}\n\n"
            "Worker output:\n{worker_output}\n\n"
            "Reply with a concise review and end with 'SCORE: <0-10>'."
        ),
    ),
    AgentRoleSpec(
        role_id="advisor",
        role_type="advisor",
        display_name="Advisor",
        model="kimi-k2:1t-cloud",
        description="Synthesizes execution and review results into a risk-aware recommendation.",
        source_agent_name="chair",
        prompt_template=(
            "You are the Advisory Board Chair for an agentic workflow.\n"
            "Synthesize the goal, worker output, and reviewer notes into an operator-facing recommendation.\n"
            "Call out risk level, notable concerns, and the best next action.\n\n"
            "Goal:\n{goal}\n\n"
            "Worker output:\n{worker_output}\n\n"
            "Reviewer notes:\n{reviewer_notes}\n\n"
            "Reply with 3 short sections:\n"
            "- Summary\n"
            "- Risks\n"
            "- Recommendation"
        ),
    ),
    AgentRoleSpec(
        role_id="security_advisor",
        role_type="advisor",
        display_name="Security advisor",
        model="codellama:7b-instruct",
        description="Security-focused advisory pass for risky or tool-writing tasks.",
        source_agent_name="security_auditor",
        prompt_template=(
            "You are the Security Advisor in an agentic workflow.\n"
            "Review the goal and worker output only for security, authorization, secret-handling, or unsafe-tool risks.\n\n"
            "Goal:\n{goal}\n\n"
            "Worker output:\n{worker_output}\n\n"
            "Reply with:\n"
            "- Security summary\n"
            "- Blocking issues (if any)\n"
            "- Required controls"
        ),
    ),
)


def build_agent_specs(
    *,
    coder_model: str,
    reviewer_model: str,
    advisor_model: str,
    security_advisor_model: str,
    strategist_model: str | None = None,
) -> tuple[AgentRoleSpec, ...]:
    override_map = {
        "coder_executor": coder_model,
        "reviewer": reviewer_model,
        "advisor": advisor_model,
        "security_advisor": security_advisor_model,
    }
    if strategist_model:
        override_map["strategist"] = strategist_model
    return tuple(
        AgentRoleSpec(
            role_id=spec.role_id,
            role_type=spec.role_type,
            display_name=spec.display_name,
            model=override_map.get(spec.role_id, spec.model),
            description=spec.description,
            prompt_template=spec.prompt_template,
            source_agent_name=spec.source_agent_name,
        )
        for spec in DEFAULT_AGENT_SPECS
    )
