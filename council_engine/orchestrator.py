"""Council orchestrator — runs Phase 1 (independent answers) + Phase 2 (judge).

Phases 3-5 (cross-critique, revision, evidence-check) are scaffolded as
stubs in this file but not wired — keeping the MVP scope honest. The
``CouncilDecision`` schema is the locked contract.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from agent_cli.schemas import CouncilDecision
from council_engine.agents.roles import AgentResponse, run_role
from council_engine.judge import judge
from council_engine.rounds import (
    aggregate_confidence,
    check_evidence,
    cross_critique,
    detect_dissent,
    revise_round,
)
from risk_classifier import classify_task
from safety_store import save_history

DEFAULT_ROLES = ["primary_expert", "opponent", "research"]


def _selector(task: dict) -> bool:
    """when_to_council() — true if this task warrants the council overhead."""
    risk = (task.get("risk") or "").lower()
    if risk in {"high", "critical", "medium"}:
        return True
    return (task.get("type") or "").lower() in {
        "production_deploy", "policy_change", "secret_change",
        "infrastructure_change",
    }


@dataclass
class CouncilRun:
    council_id: str
    user_input: str
    responses: list[AgentResponse]
    decision: CouncilDecision
    history_id: str
    wall_time_ms: int


def run_council(
    *,
    task: dict,
    user_input: str,
    actor: str = "council_engine",
    roles: list[str] | None = None,
    parallel: bool = True,
    deep: bool = False,
) -> CouncilRun:
    """Run the council pipeline.

    ``deep=False`` (default): Phase 1 (independent) + Phase 2 (judge).
    ``deep=True``: also runs Phase 3 (cross-critique) + Phase 4 (revise)
    + Phase 5 (evidence check), applies the Q1/Q2/Q3 picks documented in
    rounds.py, and surfaces dissent in the recommendation when found.

    Cost: ``deep=True`` runs 2N + 1 extra Ollama calls (critique + revise
    per agent). For 3 agents that's ~7 extra calls — only invoke for
    high-stakes tasks.
    """
    chosen_roles = roles or DEFAULT_ROLES
    council_id = f"C_{uuid.uuid4().hex[:10]}"
    # Risk currently informational — selector() is the gate. Future:
    # auto-promote to deep=True when risk is critical.
    _ = classify_task(task)
    started = time.time()

    # Phase 1: independent responses
    if parallel:
        with ThreadPoolExecutor(max_workers=len(chosen_roles)) as pool:
            futs = [pool.submit(run_role, r, user_input) for r in chosen_roles]
            responses = [f.result() for f in futs]
    else:
        responses = [run_role(r, user_input) for r in chosen_roles]

    rounds_run = 1
    final_responses = responses
    dissent = None
    evidence_demote = 0.0
    evidence_uncited = 0

    if deep:
        # Phase 3: cross-critique
        critiques = cross_critique(responses)
        # Phase 4: revise
        final_responses = revise_round(responses, critiques)
        rounds_run = 3

        # Phase 5: evidence check on each revised answer (Q2: demote)
        ev_total = 0.0
        for r in final_responses:
            v = check_evidence(r.content)
            ev_total = max(ev_total, v.demote_amount)
            evidence_uncited += v.uncited_count
        evidence_demote = ev_total

        # Q3: dissent detection on final (revised) answers
        dissent = detect_dissent(final_responses)

    # Phase 2: judge synthesizes the FINAL set
    j = judge(user_input=user_input, agent_responses=final_responses)

    # Q1: re-aggregate the confidence using trimmed_mean by default.
    # The judge's own confidence is treated as ONE input; agent
    # response presence (proxy: latency_ms > 0) provides per-agent
    # confidence proxies. Real per-agent confidence is a Phase-6 add.
    raw_confidences = [j.confidence] + [
        min(1.0, max(0.0, len(r.content) / 1500.0))
        for r in final_responses
    ]
    aggregated_confidence = aggregate_confidence(raw_confidences)

    # Apply Q2 demotion to evidence dimension if deep mode found gaps
    scores = dict(j.scores_pct)
    if deep and evidence_demote > 0:
        # Demote in the WEIGHTED scale (scores_pct max for evidence = 20)
        scores["evidence"] = max(0.0, scores.get("evidence", 0.0) - evidence_demote * 20.0)

    # Q3: surface dissent in recommended_action when found
    recommendation = j.recommended_action
    if deep and dissent and dissent.has_dissent:
        recommendation = (
            f"{recommendation}\n\n"
            f"⚠️ MINORITY VIEW: agents {dissent.dissenting_roles} diverged "
            f"from the consensus (jaccard similarities: {dissent.similarities}). "
            f"Surface their alternative below before committing."
        )

    decision = CouncilDecision(
        council_id=council_id,
        task_id=str(task.get("id", "unknown")),
        agents=chosen_roles,
        debate_rounds=rounds_run,
        final_decision=j.final_decision,  # type: ignore[arg-type]
        confidence=aggregated_confidence,
        risks=j.risks + (
            [f"evidence_uncited_claims={evidence_uncited}"] if evidence_uncited else []
        ),
        recommended_action=recommendation,
        scores=scores,
    )

    rec = save_history(
        entity_type="council_run", entity_id=council_id,
        action="council_decision",
        old_value={"task_id": decision.task_id, "user_input": user_input},
        new_value=decision.model_dump(),
        actor=actor,
        reason=f"council with roles={chosen_roles} decision={j.final_decision}",
        approved_by="council_engine",
    )

    return CouncilRun(
        council_id=council_id, user_input=user_input,
        responses=responses, decision=decision,
        history_id=rec.history_id,
        wall_time_ms=int((time.time() - started) * 1000),
    )


def when_to_council(task: dict) -> bool:
    """Public selector — keep the same name as the user's spec."""
    return _selector(task)


__all__ = ["CouncilRun", "DEFAULT_ROLES", "run_council", "when_to_council"]
