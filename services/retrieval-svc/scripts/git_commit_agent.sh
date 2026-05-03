#!/bin/bash

echo "📦 GIT COMMIT AGENT"

./scripts/full_system_check.sh || exit 1
./scripts/governance_gate.sh || exit 1

BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs present → block commit"
  exit 1
fi

echo "✅ All checks passed → committing"

git add .
git commit -m "🤖 auto-commit: system healthy"

echo "🚀 Commit complete"
