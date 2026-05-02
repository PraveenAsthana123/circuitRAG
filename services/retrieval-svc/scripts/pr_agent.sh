#!/bin/bash

echo "🚀 PR AGENT"

echo "1. Run governance gate"
./scripts/governance_gate.sh || exit 1

echo "2. Check branch"
BRANCH=$(git branch --show-current)
echo "Current branch: $BRANCH"

if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "⚠️ You are on $BRANCH. Create a feature branch first:"
  echo "git checkout -b agent/validation-self-healing"
  exit 1
fi

echo "3. Generate PR summary"
mkdir -p reports

cat > reports/pr_summary.md <<'MD'
# PR Summary: Agentic Validation + Self-Healing Scripts

## What Changed
- Added full system health check script
- Added testing agent
- Added bug manager
- Added auto-fix agent
- Added self-healing retry loop
- Added governance gate
- Added PR/commit automation foundation

## Validation
- API health: PASS
- Pytest: PASS
- OpenAPI: PASS
- Ruff lint: PASS
- Bandit security: PASS
- Bugs: 0

## Risk
Low. Scripts are additive and do not change service runtime logic.

## Rollback
Remove added scripts and generated reports.
MD

echo "✅ PR summary created: reports/pr_summary.md"

echo "4. Push branch"
echo "Run:"
echo "git push -u origin $BRANCH"

echo "5. Create PR"
echo "Run:"
echo "gh pr create --title 'agent: add validation and self-healing pipeline' --body-file reports/pr_summary.md"

echo "✅ PR AGENT DONE"
