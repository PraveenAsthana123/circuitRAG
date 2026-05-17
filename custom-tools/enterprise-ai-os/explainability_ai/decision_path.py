from typing import Dict, Any, List


class DecisionPath:
    def build(
        self,
        decisions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:

        if not decisions:
            raise ValueError("Decision path requires at least one decision")

        return {
            "path": [
                {
                    "step": index + 1,
                    "actor": decision.get("actor"),
                    "decision": decision.get("decision"),
                    "reason": decision.get("reason")
                }
                for index, decision in enumerate(decisions)
            ],
            "final_decision": decisions[-1].get("decision")
        }
