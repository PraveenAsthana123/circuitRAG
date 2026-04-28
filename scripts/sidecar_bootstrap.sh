#!/bin/bash
# Sidecar Advisor — one-command bootstrap for first-time setup.
#
# Brings the autonomous loop from "shipped but dormant" to "live on
# your machine":
#
#   1. Verify prerequisites (git, python3, pyyaml installed)
#   2. Initialize advisor.db (run migrations 001 + 002)
#   3. Install the post-commit hook (git config core.hooksPath)
#   4. Run the drill suite once to populate .loop/last_drill_outcome.json
#      so LoopWatcher rule 1 has real input on the first commit
#   5. Render the initial dashboard
#   6. Print quick-start summary
#
# Idempotent: safe to re-run. Each step checks if it's already done
# and skips if so.
#
# Per docs/runbooks/ai-cache-migration.md and ADR-014.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null \
            || echo "/mnt/deepa/rag")"
cd "$REPO_ROOT"

ADVISOR_DB="$REPO_ROOT/advisor.db"
LOOP_DIR="$REPO_ROOT/.loop"
HOOK_DIR="$REPO_ROOT/scripts/git-hooks"
DASHBOARD="$LOOP_DIR/dashboard.html"
DRILL_STATUS="$LOOP_DIR/last_drill_outcome.json"

GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BOLD="\033[1m"
NC="\033[0m"

ok()    { printf "${GREEN}✓ %s${NC}\n" "$1"; }
warn()  { printf "${YELLOW}! %s${NC}\n" "$1"; }
fail()  { printf "${RED}✗ %s${NC}\n" "$1" >&2; exit 1; }
step()  { printf "\n${BOLD}── %s ──${NC}\n" "$1"; }

# ── Step 1: prerequisites ────────────────────────────────────────
step "1. Prerequisites"
command -v git >/dev/null   || fail "git not on PATH"
command -v python3 >/dev/null || fail "python3 not on PATH"
ok "git: $(git --version | head -1)"
ok "python3: $(python3 --version)"

if ! python3 -c "import yaml" 2>/dev/null; then
    warn "pyyaml not installed (needed for policy parsing)"
    if command -v pip >/dev/null; then
        echo "  Installing pyyaml..."
        pip install --user --quiet --break-system-packages pyyaml \
            || pip install --user --quiet pyyaml \
            || fail "pyyaml install failed"
        ok "pyyaml installed"
    else
        fail "pip not on PATH; install pyyaml manually"
    fi
else
    ok "pyyaml: $(python3 -c 'import yaml; print(yaml.__version__)')"
fi

# ── Step 2: advisor.db ──────────────────────────────────────────
step "2. Advisor DB"
if [ -f "$ADVISOR_DB" ]; then
    EVENT_COUNT=$(sqlite3 "$ADVISOR_DB" \
        "SELECT COUNT(*) FROM advisor_events" 2>/dev/null || echo "?")
    ok "advisor.db exists ($EVENT_COUNT events)"
else
    echo "  Initializing fresh advisor.db..."
    python3 -c "
import sys
sys.path.insert(0, 'services/sidecar-advisor')
import importlib.util
spec = importlib.util.spec_from_file_location(
    'mem_init', 'services/sidecar-advisor/memory.py')
mem = importlib.util.module_from_spec(spec)
sys.modules['mem_init'] = mem
spec.loader.exec_module(mem)
m = mem.AdvisorMemory('$ADVISOR_DB')
print('schema initialized')
"
    ok "advisor.db created (migrations 001 + 002 applied)"
fi

# ── Step 3: post-commit hook ─────────────────────────────────────
step "3. Git hook installation"
CURRENT_HOOKS=$(git config --get core.hooksPath 2>/dev/null || echo "")
if [ "$CURRENT_HOOKS" = "scripts/git-hooks" ]; then
    ok "core.hooksPath already set to scripts/git-hooks"
elif [ -n "$CURRENT_HOOKS" ]; then
    warn "core.hooksPath currently set to: $CURRENT_HOOKS"
    warn "  NOT overwriting; remove with: git config --unset core.hooksPath"
    warn "  Then re-run this script."
else
    echo "  Setting core.hooksPath = scripts/git-hooks ..."
    git config core.hooksPath scripts/git-hooks
    ok "core.hooksPath set; post-commit hook is now live"
fi

if [ -x "$HOOK_DIR/post-commit" ]; then
    ok "post-commit hook is executable"
else
    chmod +x "$HOOK_DIR/post-commit"
    ok "made post-commit hook executable"
fi

# ── Step 4: drill status ─────────────────────────────────────────
step "4. Drill status (rule-1 input)"
mkdir -p "$LOOP_DIR"
if [ -f "$DRILL_STATUS" ]; then
    AGE_SECS=$(( $(date +%s) - $(stat -c %Y "$DRILL_STATUS") ))
    if [ "$AGE_SECS" -lt 3600 ]; then
        ok "drill status fresh (age: ${AGE_SECS}s)"
    else
        warn "drill status stale (age: ${AGE_SECS}s); refreshing..."
        python3 scripts/write_drill_status.py --only-readonly \
            --status-path "$DRILL_STATUS" >/dev/null 2>&1 \
            && ok "drill status refreshed" \
            || warn "drill refresh failed; LoopWatcher rule 1 will see stale data"
    fi
else
    echo "  Running drill suite (one-time) to seed status..."
    python3 scripts/write_drill_status.py --only-readonly \
        --status-path "$DRILL_STATUS" >/dev/null 2>&1 \
        && ok "drill status written ($(jq '.total_drills' "$DRILL_STATUS" 2>/dev/null || echo "?") drills)" \
        || warn "drill suite has failures; LoopWatcher will REJECT next commit (correct)"
fi

# ── Step 5: dashboard ────────────────────────────────────────────
step "5. Initial dashboard"
python3 scripts/render_dashboard.py > "$DASHBOARD" 2>/dev/null \
    && ok "dashboard rendered: $DASHBOARD" \
    || warn "dashboard render failed (non-fatal; will work on next commit)"

# ── Step 6: summary ──────────────────────────────────────────────
step "6. Quick-start summary"
cat << EOF

  $(printf "${BOLD}The Sidecar Advisor loop is now live.${NC}")

  Make a commit. The post-commit hook will:
    - run the LoopWatcher (advisory verdict; appends to .loop/watcher.log)
    - capture the diff + run the council if Ollama is up
    - write the council outcome to .loop/council_runs.log

  Inspect:
    Dashboard:  open $DASHBOARD in a browser
    Verdicts:   tail $LOOP_DIR/watcher.log
    Council:    tail $LOOP_DIR/council_runs.log

  Operate:
    Refresh dashboard:        python3 scripts/render_dashboard.py > $DASHBOARD
    Replay rejected commits:  python3 scripts/replay_verdict_log.py
    Drain --no-council backlog: python3 scripts/replay_council_against_events.py
    Prune old council runs:   python3 scripts/prune_council_runs.py

  If you want to disable the post-commit hook:
    git config --unset core.hooksPath

EOF
ok "Bootstrap complete."
