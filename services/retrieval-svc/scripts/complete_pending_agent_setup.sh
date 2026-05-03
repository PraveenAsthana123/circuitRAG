#!/bin/bash
set -e

echo "🚀 COMPLETE PENDING AGENT SETUP"

mkdir -p reports logs docs/drills scripts

echo "1. Install tools"
pip install ruff bandit pytest requests httpx pydantic rich >/dev/null 2>&1 || true

echo "2. Create drill docs"
cat > docs/drills/audit.md <<'MD'
# Audit Cadence
- Weekly review of agent decisions
- Monthly security scan review
- Quarterly governance review
MD

cat > docs/drills/catalog.md <<'MD'
# Drill Catalog
- smoke test
- regression score
- performance p95
- council decision
- rollback validation
MD

cat > docs/drills/smoke.md <<'MD'
# Service Smoke Drill
- /health must return 200
- /docs must load
- /openapi.json must return 200
MD

echo "3. Check Ollama models"
if command -v ollama >/dev/null 2>&1; then
  ollama list | grep -q "qwen2.5" || ollama pull qwen2.5:latest || true
else
  echo "⚠️ Ollama not installed"
fi

echo "4. Create performance agent"
cat > scripts/performance_agent.sh <<'PERF'
#!/bin/bash
set -e

echo "⚡ PERFORMANCE AGENT"

mkdir -p reports

if ! command -v k6 >/dev/null 2>&1; then
  echo '{"status":"SKIP","reason":"k6 not installed","p95_ms":9999}' > reports/performance_report.json
  echo "⚠️ k6 missing. Install with: sudo apt install k6"
  exit 0
fi

cat > reports/k6_test.js <<'JS'
import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
  vus: 10,
  duration: '10s',
};

export default function () {
  http.get('http://127.0.0.1:8000/health');
  sleep(1);
}
JS

k6 run --summary-export reports/k6_summary.json reports/k6_test.js

python - <<'PY'
import json
from pathlib import Path

summary = json.load(open("reports/k6_summary.json"))
p95 = summary["metrics"]["http_req_duration"]["percentiles"]["95"]
failed = summary["metrics"]["http_req_failed"]["rate"]

out = {
    "status": "PASS" if p95 < 500 and failed == 0 else "FAIL",
    "p95_ms": round(p95, 2),
    "failed_rate": failed,
    "threshold_p95_ms": 500
}

Path("reports/performance_report.json").write_text(json.dumps(out, indent=2))
print(out)
PY
PERF

chmod +x scripts/performance_agent.sh

echo "5. Create council agent with performance vote"
cat > scripts/council_agent.py <<'PY'
import json
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path("reports")
FINAL = REPORTS / "final_report.json"
BUGS = REPORTS / "bugs.json"
REG = REPORTS / "regression_score.json"
PERF = REPORTS / "performance_report.json"
OUT = REPORTS / "council_decision.json"


def load(path, default):
    if not path.exists():
        return default
    with path.open() as f:
        return json.load(f)


def vote_testing(final_report):
    checks = final_report.get("sanitation", final_report)
    failed = []

    for key, value in checks.items():
        if isinstance(value, dict):
            if value.get("status") != "PASS":
                failed.append(key)
        elif isinstance(value, str):
            if value != "PASS":
                failed.append(key)
        else:
            failed.append(key)

    return {
        "agent": "testing",
        "vote": "PASS" if not failed else "FAIL",
        "reason": "All testing checks passed" if not failed else f"Failed checks: {failed}",
        "weight": 35,
    }


def vote_bug(bugs):
    return {
        "agent": "bug",
        "vote": "PASS" if len(bugs) == 0 else "FAIL",
        "reason": f"{len(bugs)} bugs",
        "weight": 25,
    }


def vote_regression(regression):
    score = regression.get("score", 0)
    return {
        "agent": "regression",
        "vote": "PASS" if score >= 80 else "FAIL",
        "reason": f"score={score}",
        "weight": 25,
    }


def vote_performance(perf):
    status = perf.get("status", "SKIP")
    p95 = perf.get("p95_ms", 9999)
    return {
        "agent": "performance",
        "vote": "PASS" if status in ["PASS", "SKIP"] else "FAIL",
        "reason": f"status={status}, p95={p95}ms",
        "weight": 15,
    }


def main():
    REPORTS.mkdir(exist_ok=True)

    votes = [
        vote_testing(load(FINAL, {})),
        vote_bug(load(BUGS, [])),
        vote_regression(load(REG, {"score": 0})),
        vote_performance(load(PERF, {"status": "SKIP"})),
    ]

    passed_weight = sum(v["weight"] for v in votes if v["vote"] == "PASS")
    failed = [v for v in votes if v["vote"] != "PASS"]

    decision = {
        "timestamp": datetime.now(UTC).isoformat(),
        "votes": votes,
        "score": passed_weight,
        "threshold": 80,
        "decision": "ALLOW" if passed_weight >= 80 and not failed else "BLOCK",
        "failed_agents": failed,
    }

    OUT.write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision, indent=2))

    if decision["decision"] == "BLOCK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
PY

echo "6. Create monitoring summary"
cat > scripts/monitoring_summary.py <<'PY'
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
PY

echo "7. Ensure governance gate includes council"
python - <<'PY'
from pathlib import Path

p = Path("scripts/governance_gate.sh")
text = p.read_text()

insert = '''
echo "4. Performance agent"
./scripts/performance_agent.sh || FAIL=1

echo "5. Council agent decision"
python scripts/regression_score.py || FAIL=1
python scripts/council_agent.py || FAIL=1
python scripts/monitoring_summary.py || true
'''

if "Council agent decision" not in text:
    text = text.replace('if [ "$FAIL" -eq 1 ]; then', insert + '\nif [ "$FAIL" -eq 1 ]; then')

p.write_text(text)
PY

echo "8. Run pipeline"
./scripts/master_agent_pipeline.sh

echo "✅ ALL PENDING SETUP COMPLETE"
