import json
from datetime import UTC, datetime
from pathlib import Path

report_path = Path("reports/final_report.json")

if not report_path.exists():
    print("❌ final_report.json missing")
    raise SystemExit(1)

with report_path.open() as f:
    report = json.load(f)

checks = report.get("sanitation", report)

def safe_status(key):
    return checks.get(key, {}).get("status", "FAIL")

score = 100

if safe_status("pytest") != "PASS":
    score -= 40

if safe_status("openapi") != "PASS":
    score -= 20

if safe_status("smoke_docs") != "PASS":
    score -= 20

output = {
    "timestamp": datetime.now(UTC).isoformat(),
    "score": score,
    "status": "PASS" if score >= 80 else "FAIL",
    "checks": {
        "pytest": safe_status("pytest"),
        "openapi": safe_status("openapi"),
        "smoke_docs": safe_status("smoke_docs"),
    },
}

Path("reports/regression_score.json").write_text(json.dumps(output, indent=2))

print("📊 Regression Score:", output)
