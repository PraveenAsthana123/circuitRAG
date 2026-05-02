#!/bin/bash

MAX_RETRIES=3
COUNT=0

echo "♻️ SELF-HEALING LOOP START"

while [ $COUNT -lt $MAX_RETRIES ]; do
  echo ""
  echo "🔁 Attempt $((COUNT+1)) / $MAX_RETRIES"

  echo "1. Run system check"
  ./scripts/full_system_check.sh

  BUGS=$(python - <<'PY'
import json
from pathlib import Path
p = Path("reports/bugs.json")
if not p.exists():
    print(0)
else:
    print(len(json.load(open(p))))
PY
)

  echo "Bugs: $BUGS"

  if [ "$BUGS" = "0" ]; then
    echo "✅ SYSTEM RECOVERED"
    exit 0
  fi

  echo "2. Backup before fix"
  mkdir -p .loop/backups
  BACKUP=".loop/backups/backup_$(date +%s).tar.gz"
  tar --exclude='.venv' --exclude='.git' --exclude='reports' -czf "$BACKUP" .

  echo "3. Run auto-fix"
  ./scripts/auto_fix_agent.sh

  COUNT=$((COUNT+1))
done

echo ""
echo "❌ SYSTEM NOT FIXED AFTER $MAX_RETRIES ATTEMPTS"

echo "🔙 Rolling back last backup"
LATEST_BACKUP=$(ls -t .loop/backups/*.tar.gz | head -1)

if [ -f "$LATEST_BACKUP" ]; then
  tar -xzf "$LATEST_BACKUP"
  echo "Rollback complete: $LATEST_BACKUP"
else
  echo "No backup found"
fi

echo "🚨 MANUAL INTERVENTION REQUIRED"
