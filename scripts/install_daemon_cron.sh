#!/usr/bin/env bash
# Install / update the autonomous-fix-daemon cron entry.
#
# Per CLAUDE.md §42 (gated operations): cron RUNS the daemon, daemon
# applies + commits, but daemon NEVER pushes. Operator pushes via:
#     python3 scripts/agent_task_board.py push --confirm
#
# Idempotent: re-running replaces the existing entry, doesn't duplicate.

case "${1:-}" in
  -h|--help)
    cat <<'HELP'
install_daemon_cron.sh — install autonomous-fix-daemon cron entry

Adds (or updates) a single crontab line that runs the daemon every
30 minutes for up to 3 cycles per invocation. Logs append to
.loop/daemon_cron.log so an operator can `tail -f` it for live
status.

Usage:
  bash scripts/install_daemon_cron.sh           # install / update
  bash scripts/install_daemon_cron.sh --remove  # uninstall
  bash scripts/install_daemon_cron.sh --status  # show current entry

The cron schedule (default `*/30 * * * *`) can be overridden via env:
  CRON_SCHEDULE="0 * * * *" bash scripts/install_daemon_cron.sh
HELP
    exit 0
    ;;
esac

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CRON_TAG="autonomous-fix-daemon-${REPO//\//_}"
CRON_SCHEDULE="${CRON_SCHEDULE:-*/30 * * * *}"
LOG_FILE="${REPO}/.loop/daemon_cron.log"
PYTHON_BIN="${REPO}/.venv/bin/python3"

CRON_LINE="${CRON_SCHEDULE} cd ${REPO} && ${PYTHON_BIN} scripts/autonomous_fix_daemon.py --max-cycles 3 --interval 60 >> ${LOG_FILE} 2>&1 # ${CRON_TAG}"

case "${1:-install}" in
  --remove)
    echo "Removing cron entry tagged ${CRON_TAG}..."
    (crontab -l 2>/dev/null | grep -v "${CRON_TAG}") | crontab -
    echo "✓ removed"
    ;;
  --status)
    echo "Current crontab entries for this daemon:"
    crontab -l 2>/dev/null | grep "${CRON_TAG}" || echo "(none installed)"
    ;;
  install|*)
    echo "Installing cron entry:"
    echo "  schedule: ${CRON_SCHEDULE}"
    echo "  command:  ${PYTHON_BIN} scripts/autonomous_fix_daemon.py --max-cycles 3 --interval 60"
    echo "  log:      ${LOG_FILE}"
    mkdir -p "${REPO}/.loop"
    touch "${LOG_FILE}"
    # Replace existing entry; append new.
    (crontab -l 2>/dev/null | grep -v "${CRON_TAG}"; echo "${CRON_LINE}") | crontab -
    echo "✓ installed"
    echo
    echo "Verify with:  bash scripts/install_daemon_cron.sh --status"
    echo "Watch logs:   tail -f ${LOG_FILE}"
    echo "Uninstall:    bash scripts/install_daemon_cron.sh --remove"
    ;;
esac
