import json
from typing import Dict, Any, List


class AuditExporter:
    def export_json(
        self,
        records: List[Dict[str, Any]]
    ) -> str:
        return json.dumps(records, indent=2)

    def export_by_trace(
        self,
        trace_id: str,
        records: List[Dict[str, Any]]
    ) -> str:
        filtered = [
            record for record in records
            if record["payload"]["trace_id"] == trace_id
        ]

        return json.dumps(filtered, indent=2)
