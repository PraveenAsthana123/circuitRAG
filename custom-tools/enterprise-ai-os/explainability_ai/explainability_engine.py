from typing import Dict, Any, List
from explainability_ai.reasoning_trace import ReasoningTrace
from explainability_ai.source_attribution import SourceAttribution
from explainability_ai.confidence_report import ConfidenceReport
from explainability_ai.decision_path import DecisionPath


class ExplainabilityEngine:
    def __init__(self):
        self.reasoning_trace = ReasoningTrace()
        self.source_attribution = SourceAttribution()
        self.confidence_report = ConfidenceReport()
        self.decision_path = DecisionPath()

    def explain(
        self,
        trace_id: str,
        answer: str,
        sources: List[Dict[str, Any]],
        confidence_score: float,
        evaluation_result: Dict[str, Any],
        responsible_ai_result: Dict[str, Any],
        governance_result: Dict[str, Any],
        decisions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        return {
            "trace_id": trace_id,
            "source_attribution": self.source_attribution.attribute(answer, sources),
            "confidence_report": self.confidence_report.generate(
                confidence_score,
                evaluation_result,
                responsible_ai_result,
                governance_result
            ),
            "decision_path": self.decision_path.build(decisions),
            "reasoning_steps": self.reasoning_trace.get_trace(trace_id)
        }
