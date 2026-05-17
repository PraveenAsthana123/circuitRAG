from datetime import datetime
from typing import Dict, Any, List
import uuid


class ReasoningTrace:
    def __init__(self):
        self.steps: List[Dict[str, Any]] = []

    def add_step(
        self,
        trace_id: str,
        agent_name: str,
        action: str,
        reason: str,
        input_summary: str,
        output_summary: str
    ) -> Dict[str, Any]:

        step = {
            "step_id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "agent_name": agent_name,
            "action": action,
            "reason": reason,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.steps.append(step)
        return step

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        return [
            step for step in self.steps
            if step["trace_id"] == trace_id
        ]
