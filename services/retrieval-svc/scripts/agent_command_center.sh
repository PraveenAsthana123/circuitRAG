#!/bin/bash

echo "🧠 AGENT COMMAND CENTER"
echo "=============================="

run_if_exists () {
  LABEL="$1"
  CMD="$2"

  echo ""
  echo "▶️ $LABEL"
  eval "$CMD" || echo "⚠️ skipped/failed: $LABEL"
}

echo "1. ENVIRONMENT"
run_if_exists "Env status" "bash scripts/setup_agent_env.sh --status"
run_if_exists "Python" "python --version"
run_if_exists "Ollama models" "ollama list | head"

echo ""
echo "2. CORE PIPELINE"
run_if_exists "Full system check" "./scripts/full_system_check.sh"
run_if_exists "Regression score" "python scripts/regression_score.py"
run_if_exists "Performance agent" "./scripts/performance_agent.sh"
run_if_exists "Council decision" "python scripts/council_agent.py"
run_if_exists "Governance gate" "./scripts/governance_gate.sh"

echo ""
echo "3. REPORTS"
run_if_exists "Final report" "cat reports/final_report.json"
run_if_exists "Regression report" "cat reports/regression_score.json"
run_if_exists "Performance report" "cat reports/performance_report.json"
run_if_exists "Council report" "cat reports/council_decision.json"
run_if_exists "Monitoring summary" "python scripts/monitoring_summary.py && cat reports/monitoring_summary.json"

echo ""
echo "4. PLATFORM SKELETON"
run_if_exists "Task board" "python scripts/agent_task_board.py list"
run_if_exists "Outcome report" "python scripts/outcome_eval.py report"
run_if_exists "Outcome contract" "python scripts/outcome_eval.py contract"
run_if_exists "Council warm pool" "python scripts/warm_council_pool.py status"
run_if_exists "Tier-B fallback" "python scripts/tier_b_fallback.py --check"

echo ""
echo "5. DRILLS"
run_if_exists "Drill count" "ls mcp/tests/drill_*.py 2>/dev/null | wc -l"
run_if_exists "Drill docs" "ls docs/drills 2>/dev/null"

echo ""
echo "6. GIT STATE"
run_if_exists "Git status" "git status --short"
run_if_exists "Recent commits" "git log --oneline -5"

echo ""
echo "✅ COMMAND CENTER COMPLETE"
