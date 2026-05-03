import json
from pathlib import Path

files = [
    "reports/final_report.json",
    "reports/bugs.json",
    "reports/regression_score.json",
    "reports/performance_report.json",
    "reports/council_decision.json",
]

summary = {}
for f in files:
    p = Path(f)
    summary[f] = json.loads(p.read_text()) if p.exists() else "MISSING"

Path("reports/monitoring_summary.json").write_text(json.dumps(summary, indent=2))
print("✅ Monitoring summary: reports/monitoring_summary.json")
