#!/bin/bash

echo "🚀 FIXING PERFORMANCE AGENT"

python - <<'PY'
from pathlib import Path

p = Path("scripts/performance_agent.sh")
text = p.read_text()

# Replace wrong parsing
text = text.replace(
    '["percentiles"]["95"]',
    '["values"]["p(95)"]'
)

# Add safe fallback handling
text = text.replace(
    'p95 = summary["metrics"]["http_req_duration"]["values"]["p(95)"]',
    '''
metrics = summary.get("metrics", {})
duration = metrics.get("http_req_duration", {})
values = duration.get("values", {})
p95 = values.get("p(95)", 9999)
'''
)

p.write_text(text)
print("✅ Fixed performance parsing + added fallback")
PY

echo "▶️ Re-running performance agent"
./scripts/performance_agent.sh

echo ""
echo "📊 Performance Report:"
cat reports/performance_report.json || echo "❌ Still missing"

echo ""
echo "🧠 Updating council decision"
python scripts/council_agent.py

echo ""
echo "🎯 Final pipeline run"
./scripts/master_agent_pipeline.sh

echo ""
echo "✅ PERFORMANCE FIX COMPLETE"
