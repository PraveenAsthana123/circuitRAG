#!/bin/bash

echo "🌿 GIT COMMIT AGENT"

echo "1. Run final health check"
./scripts/full_system_check.sh

BUGS=$(python - <<'PY'
import json
from pathlib import Path

p = Path("reports/bugs.json")
print(len(json.load(open(p))) if p.exists() else 0)
PY
)

if [ "$BUGS" != "0" ]; then
  echo "❌ Bugs found: $BUGS"
  echo "Commit blocked."
  exit 1
fi

echo "2. Check git status"
git status --short

if [ -z "$(git status --short)" ]; then
  echo "✅ No changes to commit."
  exit 0
fi

echo "3. Stage changes"
git add scripts reports

echo "4. Commit"
git commit -m "agent: add validation and self-healing scripts"

echo "✅ Commit complete"
