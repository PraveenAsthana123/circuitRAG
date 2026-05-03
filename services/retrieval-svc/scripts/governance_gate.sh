#!/bin/bash

echo "🛡️ GOVERNANCE GATE"

FAIL=0

echo "1. Check drill freshness"
if grep -q "drill status stale" reports/final_report.json 2>/dev/null; then
  echo "❌ Drill status stale"
  FAIL=1
fi

echo "2. Check testing agent report"
if grep -q '"status": "FAIL"' reports/final_report.json 2>/dev/null; then
  echo "❌ Validation failure detected"
  FAIL=1
fi

echo "3. Check bugs"
BUGS=$(python - <<'PY'
import json
from pathlib import Path

p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs detected: $BUGS"
  FAIL=1
fi


echo "4. Council agent decision"
python scripts/regression_score.py || FAIL=1
python scripts/council_agent.py || FAIL=1

if [ "$FAIL" -eq 1 ]; then
  echo "🚫 GOVERNANCE BLOCKED"
  exit 1
fi

echo "✅ Governance checks passed"
