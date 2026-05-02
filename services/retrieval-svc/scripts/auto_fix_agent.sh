#!/bin/bash

echo "🤖 AUTO-FIX AGENT"

echo "1. Run health check"
./scripts/full_system_check.sh

echo "2. Check bugs"
BUG_COUNT=$(python - <<'PY'
import json
from pathlib import Path

p = Path("reports/bugs.json")
if not p.exists():
    print(0)
else:
    print(len(json.load(open(p))))
PY
)

echo "Bugs found: $BUG_COUNT"

if [ "$BUG_COUNT" = "0" ]; then
  echo "✅ No bugs found. Nothing to fix."
  exit 0
fi

echo "3. Create backup"
mkdir -p .loop/backups
BACKUP=".loop/backups/backup_$(date +%Y%m%d_%H%M%S).tar.gz"
tar --exclude='.venv' --exclude='.git' --exclude='reports' -czf "$BACKUP" .
echo "Backup created: $BACKUP"

echo "4. Try safe auto-fixes"
ruff check . --fix || true

echo "5. Re-run health check"
./scripts/full_system_check.sh

echo "6. Verify bugs after fix"
BUG_COUNT_AFTER=$(python - <<'PY'
import json
from pathlib import Path

p = Path("reports/bugs.json")
if not p.exists():
    print(0)
else:
    print(len(json.load(open(p))))
PY
)

if [ "$BUG_COUNT_AFTER" = "0" ]; then
  echo "✅ Auto-fix successful"

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git status --short
    echo "Ready for commit:"
    echo "git add . && git commit -m 'auto-fix: resolve validation issues'"
  fi
else
  echo "⚠️ Auto-fix incomplete. Bugs remaining: $BUG_COUNT_AFTER"
  echo "Backup available: $BACKUP"
fi

echo "✅ AUTO-FIX AGENT DONE"
