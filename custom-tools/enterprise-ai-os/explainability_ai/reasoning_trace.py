from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid


class ReasoningTrace:
    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self._steps_by_trace: Dict[str, List[Dict[str, Any]]] = {}

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
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        self.steps.append(step)
        self._steps_by_trace.setdefault(trace_id, []).append(step)
        return deepcopy(step)

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        return deepcopy(self._steps_by_trace.get(trace_id, []))
