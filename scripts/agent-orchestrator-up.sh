#!/bin/bash
# Idempotent boot for agent-orchestrator-svc on port 8050.
case "${1:-}" in
  -h|--help)
    sed -n '2,30p' "$0" | sed 's/^# \?//'
    exit 0 ;;
esac
#
# Why this script exists:
#   The service has a Dockerfile but isn't in docker-compose.yml yet
#   (TODO: ADR-pending). For now it runs as a host-side python process.
#   Without setsid + nohup the process dies whenever the parent shell
#   rotates (pre-commit hooks, agent restarts, terminal close). This
#   has happened repeatedly in autonomous-loop sessions — "B
#   orchestrator up: NO" appears on /admin/agent-readiness even
#   though the operator started the service ~10min ago.
#
#   This script:
#     1. Kills any prior orchestrator on :8050 (idempotent)
#     2. Starts via setsid → fully detached from controlling terminal
#     3. Verifies /health/live ≤30s before returning
#
# Drilled by mcp/tests/drill_agent_orchestrator_up.py.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SVC_DIR="$REPO_ROOT/services/agent-orchestrator-svc"
PORT="${AGENT_ORCHESTRATOR_PORT:-8050}"
LOG_FILE="${AGENT_ORCHESTRATOR_LOG:-/tmp/agent-orchestrator-svc.log}"

# The orchestrator runs from the repo-level py3.12 venv (.venv) which
# has fastapi + uvicorn + all upstream deps installed. .venv311
# (py3.11) exists for compat but lacks fastapi. documind_core is NOT
# installed into the venv as a package — it's added to PYTHONPATH
# below from libs/py/ so source edits take effect immediately.
VENV_PY="${AGENT_ORCHESTRATOR_PYTHON:-$REPO_ROOT/.venv/bin/python}"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python missing at $VENV_PY" >&2
  echo "       Run from repo root:" >&2
  echo "         python3.11 -m venv .venv311 && \\" >&2
  echo "         .venv311/bin/pip install -r services/agent-orchestrator-svc/requirements.txt" >&2
  echo "       Or override via AGENT_ORCHESTRATOR_PYTHON env var." >&2
  exit 1
fi

# Idempotent: kill any stale orchestrator on the target port.
# Using lsof here because pgrep on a uvicorn line is fragile across
# venvs (the cmdline can vary).
if STALE_PID=$(lsof -ti:"$PORT" 2>/dev/null) && [[ -n "$STALE_PID" ]]; then
  echo "Killing stale orchestrator on :$PORT (pid=$STALE_PID)"
  kill "$STALE_PID" 2>/dev/null || true
  sleep 1
  # Force if still alive.
  kill -9 "$STALE_PID" 2>/dev/null || true
fi

# setsid + nohup → fully detached. & is necessary because setsid
# inherits the parent's controlling terminal otherwise; combined
# they daemonize the process.
cd "$SVC_DIR"
# PYTHONPATH must include both:
#   $REPO_ROOT       — for `from scripts.* import ...` style imports
#   $REPO_ROOT/libs/py — where documind_core, mcp_common, etc. live
# Without the libs/py entry, `from documind_core.body_limit import ...`
# fails with ModuleNotFoundError as the service starts.
# DOCUMIND_PROMETHEUS_PORT must be unique across services that use the
# observability scaffold. Defaults collide on :9464 (retrieval-svc).
# Conventional layout: retrieval=9464, inference=9465, orchestrator=9466.
# Override via env if 9466 is also taken.
setsid nohup env \
    PYTHONPATH="$REPO_ROOT:$REPO_ROOT/libs/py" \
    DOCUMIND_PROMETHEUS_PORT="${DOCUMIND_PROMETHEUS_PORT:-9466}" \
    "$VENV_PY" -m uvicorn app.main:app \
    --host 0.0.0.0 --port "$PORT" \
    > "$LOG_FILE" 2>&1 < /dev/null &
PID=$!

echo "Started orchestrator (pid=$PID, port=$PORT, log=$LOG_FILE)"

# Verify reachability ≤30s.
for i in $(seq 1 15); do
  if curl -sf -o /dev/null "http://localhost:${PORT}/health/live" 2>/dev/null; then
    echo "Orchestrator reachable: http://localhost:${PORT}/health/live"
    # Also probe /health/ready for the deeper check (DB breaker etc).
    if READY=$(curl -sf "http://localhost:${PORT}/health/ready" 2>/dev/null); then
      echo "  /health/ready: $READY"
    fi
    exit 0
  fi
  sleep 2
done

echo "ERROR: orchestrator did not become reachable on :$PORT within 30s" >&2
echo "       Last 20 lines of $LOG_FILE:" >&2
tail -20 "$LOG_FILE" >&2 || true
exit 1
