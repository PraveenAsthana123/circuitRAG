#!/bin/bash
# One-time setup: point git's hooksPath at scripts/git-hooks/.
# After this, every commit auto-invokes the LoopWatcher advisory.
#
# Reverse: `git config --unset core.hooksPath`
set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

git config core.hooksPath scripts/git-hooks
echo "[ok] core.hooksPath set to scripts/git-hooks/"
echo "[ok] post-commit hook will invoke loop_watcher_hook.py"
echo ""
echo "verdict log: $REPO_ROOT/.loop/watcher.log"
echo "drill status (write this to enable rule 1 enforcement):"
echo "    $REPO_ROOT/.loop/last_drill_outcome.json"
echo "    format: {\"failed_drills\": [...], \"total_drills\": N}"
