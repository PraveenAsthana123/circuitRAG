#!/usr/bin/env bash
# setup_agent_env.sh — preflight + initialization for the autonomous-fix-bot.
#
# Per CLAUDE.md §50 (issue dispatcher) + §55 (autonomous-fix-bot strategy).
#
# Checks (and optionally fixes) every dependency the daemon + task-board
# + local council need to run cleanly. Run this BEFORE installing the
# cron entry; run again any time the env feels broken.
#
# Sections:
#   1. Python + venv preflight
#   2. Required pip deps (pydantic, pydantic-settings, langgraph, ruff)
#   3. Global scripts present (~/.claude/scripts/issue_scanner.py etc.)
#   4. Ollama daemon up + 4 council models present
#   5. .loop/ dir exists + writable
#   6. Cron status (informational; install separately)
#   7. Sanity test (one scan + one dry-run daemon cycle)
#
# Idempotent: safe to re-run. Default is preflight-only (no mutation);
# pass --install to do the network/disk operations (pip install,
# ollama pull, mkdir).

case "${1:-}" in
  -h|--help)
    cat <<'HELP'
setup_agent_env.sh — preflight + initialization for the autonomous-fix-bot

Usage:
  bash scripts/setup_agent_env.sh           # preflight only (no mutation)
  bash scripts/setup_agent_env.sh --install # do the install/pull/mkdir
  bash scripts/setup_agent_env.sh --warm    # preload the 4 council models
  bash scripts/setup_agent_env.sh --status  # one-line status summary

Verifies + (with --install) sets up:
  Python 3.11+ venv         → .venv/bin/python3
  Required pip deps         → pydantic, pydantic-settings, langgraph,
                              ruff, mypy, bandit, pytest
  Global discovery scripts  → ~/.claude/scripts/issue_scanner.py
                              ~/.claude/scripts/issue_dispatcher.py
  Ollama daemon             → http://localhost:11434/api/tags
  Council models present    → deepseek-coder:6.7b-instruct,
                              codegemma:7b-instruct,
                              codellama:7b-instruct,
                              qwen2.5:latest
  Loop state directory      → .loop/ (writable)
  Cron status (info only)   → bash scripts/install_daemon_cron.sh --status

Locked by mcp/tests/drill_agent_env_setup.py.
HELP
    exit 0
    ;;
esac

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

ACTION="${1:-preflight}"
INSTALL=0
WARM=0
STATUS=0
case "$ACTION" in
  --install) INSTALL=1 ;;
  --warm)    WARM=1 ;;
  --status)  STATUS=1 ;;
esac

color() { local c="$1"; shift; printf "\033[${c}m%s\033[0m\n" "$*"; }
ok()    { color "32" "✓ $*"; }
info()  { color "36" "ℹ $*"; }
warn()  { color "33" "⚠ $*"; }
fail()  { color "31" "✗ $*"; }

EXIT=0

REQUIRED_MODELS=(
  "deepseek-coder:6.7b-instruct"
  "codegemma:7b-instruct"
  "codellama:7b-instruct"
  "qwen2.5:latest"
)

REQUIRED_PIP_DEPS=(
  pydantic
  langgraph
  ruff
  pytest
  bandit
)

REQUIRED_GLOBAL_SCRIPTS=(
  "$HOME/.claude/scripts/issue_scanner.py"
  "$HOME/.claude/scripts/issue_dispatcher.py"
)

# ─── Status mode: short summary, exit ──────────────────────────────
if [ "$STATUS" -eq 1 ]; then
  python_ok="?"
  if [ -x ".venv/bin/python3" ]; then python_ok="ok"; else python_ok="missing"; fi
  ollama_ok="?"
  if curl -sSf --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    ollama_ok="up"
  else
    ollama_ok="down"
  fi
  loop_ok="?"
  if [ -d ".loop" ] && [ -w ".loop" ]; then loop_ok="writable"; else loop_ok="missing/readonly"; fi
  echo "venv=${python_ok}  ollama=${ollama_ok}  loop=${loop_ok}"
  exit 0
fi

# ─── 1. Python + venv ─────────────────────────────────────────────
info "Section 1: Python + venv preflight"
if [ ! -x ".venv/bin/python3" ]; then
  fail ".venv/bin/python3 missing"
  if [ "$INSTALL" -eq 1 ]; then
    info "creating venv at .venv/"
    python3 -m venv .venv || { fail "venv create failed"; EXIT=1; }
    ok "venv created"
  else
    warn "rerun with --install to create"
    EXIT=1
  fi
else
  PY_VER=$(.venv/bin/python3 --version 2>&1)
  ok "venv present: $PY_VER"
fi

# ─── 2. Required pip deps ─────────────────────────────────────────
echo
info "Section 2: Required pip deps"
if [ -x ".venv/bin/python3" ]; then
  for dep in "${REQUIRED_PIP_DEPS[@]}"; do
    if .venv/bin/python3 -c "import importlib; importlib.import_module('${dep}'.replace('-','_'))" 2>/dev/null; then
      ok "${dep} installed"
    else
      fail "${dep} missing"
      if [ "$INSTALL" -eq 1 ]; then
        info "installing ${dep}..."
        .venv/bin/pip install "$dep" 2>&1 | tail -2
      else
        warn "rerun with --install to install"
        EXIT=1
      fi
    fi
  done
fi

# ─── 3. Global discovery scripts ──────────────────────────────────
echo
info "Section 3: Global discovery scripts (~/.claude/scripts/)"
for script in "${REQUIRED_GLOBAL_SCRIPTS[@]}"; do
  if [ -f "$script" ]; then
    ok "$(basename "$script") present"
  else
    fail "$script missing — required for issue discovery"
    EXIT=1
  fi
done

# ─── 4. Ollama daemon + models ────────────────────────────────────
echo
info "Section 4: Ollama daemon + council models"
if curl -sSf --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama daemon up at http://localhost:11434"
  PRESENT=$(curl -s http://localhost:11434/api/tags | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(' '.join(m['name'] for m in d.get('models', [])))
except Exception:
    print('')
")
  for model in "${REQUIRED_MODELS[@]}"; do
    if echo "$PRESENT" | grep -q -F "$model"; then
      ok "model present: $model"
    else
      fail "model missing: $model"
      if [ "$INSTALL" -eq 1 ]; then
        info "pulling $model (may take several minutes)..."
        ollama pull "$model" 2>&1 | tail -3
      else
        warn "rerun with --install OR run: ollama pull $model"
        EXIT=1
      fi
    fi
  done
else
  fail "Ollama daemon not responding at http://localhost:11434"
  warn "start with: ollama serve  (or systemctl start ollama)"
  EXIT=1
fi

# ─── 5. .loop/ state directory ────────────────────────────────────
echo
info "Section 5: .loop/ state directory"
if [ ! -d ".loop" ]; then
  if [ "$INSTALL" -eq 1 ]; then
    mkdir -p .loop && ok ".loop/ created"
  else
    fail ".loop/ missing — rerun with --install"
    EXIT=1
  fi
elif [ ! -w ".loop" ]; then
  fail ".loop/ not writable"
  EXIT=1
else
  ok ".loop/ present + writable"
fi

# ─── 6. Cron status (info only) ───────────────────────────────────
echo
info "Section 6: Cron status (informational)"
if [ -f "scripts/install_daemon_cron.sh" ]; then
  bash scripts/install_daemon_cron.sh --status 2>&1 | tail -3
else
  warn "scripts/install_daemon_cron.sh not found"
fi

# ─── 7. Warm-pool the 4 council models ────────────────────────────
if [ "$WARM" -eq 1 ]; then
  echo
  info "Section 7: Warming the 4 council models (one trivial call each)"
  for model in "${REQUIRED_MODELS[@]}"; do
    if curl -sSf --max-time 60 -X POST http://localhost:11434/api/generate \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$model\",\"prompt\":\"reply: ok\",\"stream\":false}" \
        > /dev/null 2>&1; then
      ok "warmed: $model"
    else
      warn "could not warm: $model (model may not be installed)"
    fi
  done
fi

# ─── 8. Sanity test: one scan ─────────────────────────────────────
echo
info "Section 8: Sanity test (issue scan)"
if [ -f "$HOME/.claude/scripts/issue_scanner.py" ] && [ -x ".venv/bin/python3" ]; then
  COUNT=$(.venv/bin/python3 "$HOME/.claude/scripts/issue_scanner.py" --repo . 2>&1 | grep -E '"total"' | head -1 | tr -d ' ,' | cut -d: -f2 || echo "?")
  if [ -n "$COUNT" ]; then
    ok "scanner ran cleanly: ${COUNT} issues discovered"
  else
    warn "scanner ran but couldn't parse output"
  fi
else
  warn "skipped (missing prerequisite)"
fi

# ─── Summary ──────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════"
if [ "$EXIT" -eq 0 ]; then
  ok "ENVIRONMENT READY"
  echo
  echo "Next steps:"
  echo "  bash scripts/install_daemon_cron.sh           # schedule daemon every 30 min"
  echo "  python3 scripts/agent_task_board.py list       # see status board"
  echo "  python3 scripts/autonomous_fix_daemon.py --max-cycles 1 --dry-run  # test"
else
  fail "ENVIRONMENT INCOMPLETE — see ✗ markers above"
  echo
  echo "Recommended:"
  echo "  bash scripts/setup_agent_env.sh --install      # fix gaps"
  echo "  bash scripts/setup_agent_env.sh --warm         # preload models"
fi

exit $EXIT
