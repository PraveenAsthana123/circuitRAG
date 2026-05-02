#!/bin/bash

echo "📦 GIT COMMIT AGENT"

# Check system health
./scripts/full_system_check.sh
if [ $? -ne 0 ]; then
  echo "❌ System unhealthy. Commit blocked."
  exit 1
fi

# Check governance
./scripts/governance_gate.sh
if [ $? -ne 0 ]; then
  echo "❌ Governance failed. Commit blocked."
  exit 1
fi

# Check bugs
BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs present. Commit blocked."
  exit 1
fi

echo "✅ All checks passed → committing"

git add .
git commit -m "🤖 auto-commit: system healthy + governance passed"

echo "🚀 Commit done"
