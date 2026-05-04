#!/usr/bin/env bash
# run.sh — single-script entry point to the autonomous-fix-bot.
#
# Per CLAUDE.md §50 + §55. The session shipped 50+ CLI commands across
# 15+ scripts; this is the launcher that makes the system usable from
# memory. Pick a verb; sane defaults; § 42 boundaries preserved.
#
# Usage:
#   bash scripts/run.sh                # default: status (read-only)
#   bash scripts/run.sh status         # full task-board snapshot
#   bash scripts/run.sh check          # env preflight (no mutations)
#   bash scripts/run.sh warm           # warm Ollama council models
#   bash scripts/run.sh scan           # discover issues
#   bash scripts/run.sh fix             # daemon: 1 cycle (mutates working tree)
#   bash scripts/run.sh fix-dry         # daemon: 1 cycle, no mutations
#   bash scripts/run.sh metrics         # apply rate / regressions / cost
#   bash scripts/run.sh review          # operator HITL queue
#   bash scripts/run.sh frontend        # start Next.js admin (port 3000)
#   bash scripts/run.sh orchestrator    # start FastAPI orchestrator (port 8082)
#   bash scripts/run.sh push            # §42-confirm git push
#   bash scripts/run.sh paperclip       # PolisAI/Paperclip sandbox snapshot
#   bash scripts/run.sh policy          # PolisAI rules + recent decisions
#
# §42 SAFETY:
#   - 'fix' mutates the working tree but ALWAYS rolls back on gate failure
#   - 'push' requires GIT_PUSH_CONFIRM=1 in environment OR --confirm flag
#   - Never force-pushes; never deletes branches; never runs gh CLI without --confirm

case "${1:-}" in
  -h|--help)
    sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
    exit 0
    ;;
esac

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

VERB="${1:-status}"

color()  { local c="$1"; shift; printf "\033[${c}m%s\033[0m\n" "$*"; }
ok()     { color "32" "✓ $*"; }
info()   { color "36" "ℹ $*"; }
warn()   { color "33" "⚠ $*"; }
err()    { color "31" "✗ $*"; }
hdr()    { color "1;34" "==[ $* ]=="; }

case "$VERB" in
  status|"")
    hdr "1. ENV"
    bash scripts/setup_agent_env.sh --status
    echo
    hdr "2. TASK BOARD"
    .venv/bin/python3 scripts/agent_task_board.py list 2>&1 | head -40
    echo
    hdr "3. OUTCOME METRICS"
    .venv/bin/python3 scripts/outcome_eval.py report 2>&1 | head -10
    echo
    hdr "4. UNPUSHED"
    n=$(git log --oneline origin/main..HEAD 2>/dev/null | wc -l | tr -d ' ')
    if [ "$n" -gt 0 ]; then
      warn "$n commits unpushed (run 'bash scripts/run.sh push' to ship)"
    else
      ok "in sync with origin/main"
    fi
    ;;

  check)
    hdr "ENV PREFLIGHT"
    bash scripts/setup_agent_env.sh
    ;;

  warm)
    hdr "WARM OLLAMA COUNCIL POOL"
    .venv/bin/python3 scripts/warm_council_pool.py
    ;;

  scan)
    hdr "ISSUE SCAN (ruff + mypy + bandit + eslint)"
    .venv/bin/python3 ~/.claude/scripts/issue_scanner.py \
      --repo . --include-mypy --include-bandit --include-eslint 2>&1 | tail -10
    echo
    info "Pending issues written to .loop/issue_checklist.jsonl"
    ;;

  fix)
    hdr "DAEMON — 1 cycle (mutates working tree; drill-gated)"
    warn "This will run Ollama council on the first eligible pending issue"
    warn "Apply gate: ruff + mypy + pytest + perf — rollback on any failure"
    .venv/bin/python3 scripts/autonomous_fix_daemon.py --max-cycles 1
    ;;

  fix-dry)
    hdr "DAEMON DRY-RUN — 1 cycle (no mutations)"
    .venv/bin/python3 scripts/autonomous_fix_daemon.py --max-cycles 1 --dry-run
    ;;

  metrics)
    hdr "OUTCOME METRICS (§55.3 contract)"
    .venv/bin/python3 scripts/outcome_eval.py report
    echo
    hdr "§55.3 CONTRACT CHECK ON LAST COMMIT"
    .venv/bin/python3 scripts/outcome_eval.py contract
    ;;

  review)
    hdr "HITL — pending operator-rating queue"
    .venv/bin/python3 scripts/hitl_framework.py review
    echo
    hdr "SCORECARD BY MODEL"
    .venv/bin/python3 scripts/hitl_framework.py scorecard --by model
    ;;

  frontend)
    hdr "FRONTEND DEV SERVER → http://localhost:3000/admin"
    if ! command -v pnpm >/dev/null 2>&1; then
      err "pnpm not on PATH; install via: npm install -g pnpm"
      exit 1
    fi
    cd services/frontend && exec pnpm dev
    ;;

  orchestrator)
    hdr "FASTAPI ORCHESTRATOR → http://localhost:8082"
    cd services/agent-orchestrator-svc
    PYTHONPATH=../../libs/py:. \
      exec ../../.venv/bin/python3 -m uvicorn app.main:app \
        --host 127.0.0.1 --port 8082
    ;;

  pr-preview)
    hdr "PR PREVIEW (dry-run; safe)"
    .venv/bin/python3 scripts/pr_management.py preview
    ;;

  push)
    hdr "PUSH 103 COMMITS TO ORIGIN/MAIN — §42 GATED"
    if [ "${GIT_PUSH_CONFIRM:-}" != "1" ] && [ "${2:-}" != "--confirm" ]; then
      warn "Refusing without explicit confirmation."
      warn "Re-run as: bash scripts/run.sh push --confirm"
      warn "       OR: GIT_PUSH_CONFIRM=1 bash scripts/run.sh push"
      exit 2
    fi
    info "pushing..."
    git push origin HEAD
    ;;

  drills)
    hdr "FULL DRILL SUITE"
    if [ -x ".venv/bin/python3" ]; then
      .venv/bin/python3 scripts/run_drills.py 2>/dev/null || {
        warn "scripts/run_drills.py not found; running session drills individually"
        for d in mcp/tests/drill_*.py; do
          name=$(basename "$d" .py)
          result=$(.venv/bin/python3 "$d" 2>&1 | tail -1)
          if echo "$result" | grep -q "PASSED"; then
            ok "$name"
          else
            err "$name: $result"
          fi
        done
      }
    fi
    ;;

  ollama-mcp)
    hdr "START OLLAMA MCP SERVER → http://localhost:8098"
    MCP_OLLAMA_PORT=8098 exec .venv/bin/python3 mcp/server_ollama.py
    ;;

  paperclip)
    hdr "PAPERCLIP — sandbox manager-layer snapshot (Stage-1 read-only)"
    .venv/bin/python3 scripts/paperclip_manager.py snapshot --pretty
    ;;

  policy)
    hdr "POLICY — PolisAI rule list + recent decisions"
    .venv/bin/python3 scripts/policy_check.py rules
    echo
    if [ -f .loop/policy_audit.jsonl ]; then
      n=$(wc -l < .loop/policy_audit.jsonl | tr -d ' ')
      info "$n decisions logged in .loop/policy_audit.jsonl"
      tail -5 .loop/policy_audit.jsonl 2>/dev/null | python3 -c "import json,sys
for line in sys.stdin:
    d=json.loads(line)
    mark = '✓' if d.get('allow') else '✗'
    print(f\"  {mark} actor={d.get('actor')} tool={d.get('tool')} rule={d.get('rule_matched')}\")"
    else
      info "no policy audit log yet"
    fi
    ;;

  *)
    err "unknown verb: $VERB"
    echo "valid: status / check / warm / scan / fix / fix-dry / metrics /"
    echo "       review / frontend / orchestrator / pr-preview / push /"
    echo "       drills / ollama-mcp / paperclip / policy"
    echo "Run 'bash scripts/run.sh --help' for full doc."
    exit 1
    ;;
esac
