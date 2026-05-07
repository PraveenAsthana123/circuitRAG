#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RETRIEVAL_ROOT="$REPO_ROOT/services/retrieval-svc"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python3}"
OLLAMA_BASE="${OLLAMA_BASE_URL:-http://localhost:11434}"
export PYTHONPATH="$REPO_ROOT/libs/py:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$REPO_ROOT/.venv/bin:$PATH"

cd "$REPO_ROOT" || exit 1

echo "AGENT COMMAND CENTER"
echo "===================="
echo "repo: $REPO_ROOT"
echo "time: $(date -Is)"

run_cmd () {
  local label="$1"
  shift

  echo ""
  echo ">> $label"
  if ! "$@"; then
    echo "!! failed/skipped: $label"
  fi
}

run_shell () {
  local label="$1"
  local cmd="$2"

  echo ""
  echo ">> $label"
  if ! bash -lc "$cmd"; then
    echo "!! failed/skipped: $label"
  fi
}

run_in_dir () {
  local label="$1"
  local dir="$2"
  shift 2

  echo ""
  echo ">> $label"
  if ! (cd "$dir" && "$@"); then
    echo "!! failed/skipped: $label"
  fi
}

echo ""
echo "1. ENVIRONMENT"
if [ -x "$REPO_ROOT/scripts/setup_agent_env.sh" ]; then
  run_cmd "Env status" bash "$REPO_ROOT/scripts/setup_agent_env.sh" --status
else
  echo "setup_agent_env.sh: missing"
fi
run_cmd "Python" "$PYTHON_BIN" --version
run_shell "Ollama daemon" "curl -fsS '$OLLAMA_BASE/api/version'"
run_shell "Ollama models" "curl -fsS '$OLLAMA_BASE/api/tags' | $PYTHON_BIN -m json.tool | sed -n '1,80p'"
run_shell "Ollama loaded models" "curl -fsS '$OLLAMA_BASE/api/ps' | $PYTHON_BIN -m json.tool | sed -n '1,80p'"

echo ""
echo "2. TASKS / ISSUES"
run_cmd "Ops worker status" "$PYTHON_BIN" "$REPO_ROOT/ops_worker/worker.py" --status
run_cmd "Agent task board" "$PYTHON_BIN" "$REPO_ROOT/scripts/agent_task_board.py" list
run_cmd "Provider registry" "$PYTHON_BIN" "$REPO_ROOT/scripts/agent_task_registry.py" --json

echo ""
echo "3. CORE PIPELINE"
run_in_dir "Full system check" "$RETRIEVAL_ROOT" bash scripts/full_system_check.sh
run_in_dir "Regression score" "$RETRIEVAL_ROOT" "$PYTHON_BIN" scripts/regression_score.py
run_in_dir "Performance agent" "$RETRIEVAL_ROOT" bash scripts/performance_agent.sh
run_in_dir "Council decision" "$RETRIEVAL_ROOT" "$PYTHON_BIN" scripts/council_agent.py
run_in_dir "Governance gate" "$RETRIEVAL_ROOT" bash scripts/governance_gate.sh

echo ""
echo "4. REPORTS"
run_shell "Final report" "test -f '$RETRIEVAL_ROOT/reports/final_report.json' && cat '$RETRIEVAL_ROOT/reports/final_report.json'"
run_shell "Regression report" "test -f '$RETRIEVAL_ROOT/reports/regression_score.json' && cat '$RETRIEVAL_ROOT/reports/regression_score.json'"
run_shell "Performance report" "test -f '$RETRIEVAL_ROOT/reports/performance_report.json' && cat '$RETRIEVAL_ROOT/reports/performance_report.json'"
run_shell "Council report" "test -f '$RETRIEVAL_ROOT/reports/council_decision.json' && cat '$RETRIEVAL_ROOT/reports/council_decision.json'"
run_shell "Monitoring summary" "cd '$RETRIEVAL_ROOT' && $PYTHON_BIN scripts/monitoring_summary.py && cat reports/monitoring_summary.json"

echo ""
echo "5. PLATFORM SKELETON"
run_cmd "Outcome report" "$PYTHON_BIN" "$REPO_ROOT/scripts/outcome_eval.py" report
run_cmd "Outcome contract" "$PYTHON_BIN" "$REPO_ROOT/scripts/outcome_eval.py" contract
run_cmd "Council warm pool" "$PYTHON_BIN" "$REPO_ROOT/scripts/warm_council_pool.py" status
run_cmd "Tier-B fallback" "$PYTHON_BIN" "$REPO_ROOT/scripts/tier_b_fallback.py" --check

echo ""
echo "6. DRILLS"
run_shell "Drill count" "find '$REPO_ROOT/mcp/tests' -maxdepth 1 -name 'drill_*.py' | wc -l"
run_cmd "Ollama MCP drill" env PYTHONPATH="$PYTHONPATH" "$PYTHON_BIN" "$REPO_ROOT/mcp/tests/drill_server_ollama.py"

echo ""
echo "7. GIT STATE"
run_cmd "Git status" git status --short
run_cmd "Recent commits" git log --oneline -5

echo ""
echo "8. ADVANCED AI STACK"
run_cmd "MLflow tracker" "$PYTHON_BIN" "$RETRIEVAL_ROOT/scripts/mlflow_tracker.py"
run_cmd "RAG eval agent" "$PYTHON_BIN" "$RETRIEVAL_ROOT/scripts/rag_eval_agent.py"

echo ""
echo "COMMAND CENTER COMPLETE"
