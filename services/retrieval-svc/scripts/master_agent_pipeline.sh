#!/bin/bash

echo "🧠 MASTER AGENT PIPELINE"

echo "1. Full system check"
./scripts/full_system_check.sh || exit 1

echo "2. Auto-fix agent"
./scripts/auto_fix_agent.sh || exit 1

echo "3. Self-heal loop"
./scripts/self_heal_loop.sh || exit 1

echo "4. Governance gate"
./scripts/governance_gate.sh || exit 1

echo "5. Pending task report"
./scripts/pending_tasks_report.sh || true

echo "6. Git status"
git status --short

echo "✅ MASTER PIPELINE COMPLETE"
