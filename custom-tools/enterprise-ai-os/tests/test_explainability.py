# Test script from Tool Set 11 §6 — reformatted as a runnable pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from explainability_ai.explainability_engine import ExplainabilityEngine


def test_explainability_engine_assembles_report():
    engine = ExplainabilityEngine()

    trace_id = "trace_001"

    engine.reasoning_trace.add_step(
        trace_id=trace_id,
        agent_name="planner_agent",
        action="created_plan",
        reason="User requested enterprise AI architecture",
        input_summary="User request",
        output_summary="Generated 6-step plan"
    )

    engine.reasoning_trace.add_step(
        trace_id=trace_id,
        agent_name="retriever_agent",
        action="retrieved_context",
        reason="Needed source grounding",
        input_summary="Query about RAG",
        output_summary="Retrieved 2 chunks"
    )

    result = engine.explain(
        trace_id=trace_id,
        answer="RAG combines retrieval and generation using enterprise context.",
        sources=[
            {
                "chunk_id": "chunk_001",
                "source": "rag_design.md",
                "score": 0.91,
                "hybrid_score": 0.88,
                "retriever": "hybrid"
            }
        ],
        confidence_score=0.87,
        evaluation_result={"quality_gate": {"passed": True}},
        responsible_ai_result={"overall_passed": True},
        governance_result={"policy_passed": True},
        decisions=[
            {"actor": "evaluation_agent", "decision": "approve", "reason": "quality score passed"},
            {"actor": "governance_agent", "decision": "approve", "reason": "policy passed"}
        ]
    )

    assert result["trace_id"] == trace_id
    assert result["source_attribution"]["source_count"] == 1
    assert result["confidence_report"]["confidence_level"] == "high"
    assert result["confidence_report"]["recommendation"] == "release"
    assert result["decision_path"]["final_decision"] == "approve"
    assert len(result["reasoning_steps"]) == 2


if __name__ == "__main__":
    test_explainability_engine_assembles_report()
    print("OK")
