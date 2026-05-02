#!/bin/bash

echo "🛡️ COUNCIL GOVERNANCE GATE"

FAIL=0

echo "1. Run agent monitor"
python scripts/agent_monitor.py || FAIL=1

echo "2. Check Ollama server"
curl -s http://localhost:11434/api/tags >/dev/null || {
  echo "❌ Ollama unavailable"
  FAIL=1
}

echo "3. Check required model"
ollama list | grep -q "qwen2.5" || {
  echo "❌ Required model missing: qwen2.5:latest"
  FAIL=1
}

echo "4. Check validation report"
if grep -q '"status": "FAIL"' reports/final_report.json 2>/dev/null; then
  echo "❌ Validation failure found"
  FAIL=1
fi

echo "5. Check bug report"
BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs found: $BUGS"
  FAIL=1
fi

echo "6. Block partial council runs if present in logs"
if grep -E "outcome=partial|agent_board_author_failed|reviews_failed=[1-9]|authors_failed=[1-9]" logs/*.log reports/*.json 2>/dev/null; then
  echo "❌ Council failure or partial outcome detected"
  FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
  echo "🚫 COUNCIL GOVERNANCE BLOCKED"
  exit 1
fi

echo "✅ Council governance passed"
