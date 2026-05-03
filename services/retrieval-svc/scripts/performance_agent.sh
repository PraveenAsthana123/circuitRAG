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

metrics = summary.get("metrics", {})
duration = metrics.get("http_req_duration", {})
values = duration.get("values", {})
p95 = values.get("p(95)", 9999)

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
