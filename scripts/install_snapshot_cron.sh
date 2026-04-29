#!/bin/bash
# Phase 5Q: install / uninstall the council_stats_snapshot.py daily cron line.
#
# Phase 5N built the snapshot script. Without a cron line firing it, the
# script is manual-only — operators have to remember to run it daily.
# Phase 5Q closes the gap with an idempotent installer that mirrors the
# Tier-1 cache migration pattern: dry-run by default, explicit apply,
# always backup before mutate, reversible via rollback.
#
# Usage:
#   scripts/install_snapshot_cron.sh                     # default: --dry-run
#   scripts/install_snapshot_cron.sh --dry-run           # show what would happen
#   scripts/install_snapshot_cron.sh --status            # is it installed?
#   scripts/install_snapshot_cron.sh --apply             # install (idempotent)
#   scripts/install_snapshot_cron.sh --rollback          # remove
#   scripts/install_snapshot_cron.sh --uninstall         # alias for rollback
#
# Env:
#   PYTHON_BIN   — interpreter path; defaults to /mnt/deepa/rag/.venv/bin/python
#                  so the cron contract stays on the Deepa drive.
#
# Exit codes:
#   0  success
#   1  expected error (e.g. crontab unreadable on apply)
#   2  bad usage
#
# Idempotency:
#   --apply may be re-run safely. Any prior managed line (identified by
#   the magic-comment marker below) is stripped before the fresh line
#   is appended. So --apply == "ensure exactly one managed line exists".
#
# Reversibility:
#   Every mutation writes the pre-mutation crontab to
#   /mnt/deepa/rag/.loop/cron-backups/crontab.*.bak
#   before crontab(1) is touched. --rollback also makes a backup so an
#   accidental rollback can be reversed by piping the .bak file back in.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON_BIN:-$REPO/.venv/bin/python}"
SCRIPT="$REPO/scripts/council_stats_snapshot.py"
BACKUP_DIR="$REPO/.loop/cron-backups"

# Marker comment lets us round-trip find/replace our managed line without
# disturbing whatever else the operator has in their crontab. Keep this
# string stable — operator runbooks that grep crontabs for the marker
# would break on a rename.
MARKER="# managed by install_snapshot_cron.sh: phase-5Q"
CRON_SCHEDULE="5 0 * * *"   # 00:05 UTC daily — clear of midnight log rotation
CRON_LINE="$CRON_SCHEDULE $PYTHON $SCRIPT >/dev/null 2>&1 $MARKER"

MODE="--dry-run"
[[ $# -gt 0 ]] && MODE="$1"

usage() {
    sed -n '2,30p' "$0"
    exit 0
}

# Read the operator's current crontab. crontab -l exits 1 when no crontab
# is installed; we treat that as an empty crontab (valid operator state).
current_crontab() {
    crontab -l 2>/dev/null || true
}

# Strip every line containing our marker. grep -v returns 1 when nothing
# matches the inverse pattern (i.e. EVERY line had the marker); harmless.
strip_managed() {
    grep -vF "$MARKER" || true
}

# Write a backup so the user can recover from any mutation:
#   crontab /mnt/deepa/rag/.loop/cron-backups/crontab.before-snapshot-cron-YYYYMMDD-HHMMSS.bak
backup_crontab() {
    local label="$1"
    mkdir -p "$BACKUP_DIR"
    local backup="$BACKUP_DIR/crontab.before-${label}-$(date +%Y%m%d-%H%M%S).bak"
    current_crontab > "$backup"
    echo "$backup"
}

case "$MODE" in
    --dry-run)
        echo "[DRY-RUN] would install:"
        echo "  $CRON_LINE"
        echo ""
        echo "[DRY-RUN] current crontab:"
        current_crontab | sed 's/^/  /' || true
        echo ""
        echo "[DRY-RUN] no changes made. Run with --apply to install."
        ;;

    --status)
        if current_crontab | grep -qF "$MARKER"; then
            echo "[STATUS] managed cron line installed:"
            current_crontab | grep -F "$MARKER" | sed 's/^/  /'
        else
            echo "[STATUS] no managed cron line installed"
        fi
        ;;

    --apply)
        backup=$(backup_crontab "snapshot-cron-apply")
        echo "[APPLY] crontab backup → $backup"
        # Idempotent: strip any prior managed line, then append fresh.
        # Empty input is fine — printf without trailing newline would
        # produce a malformed crontab; we rebuild via newline-joined
        # blocks below.
        new=$(current_crontab | strip_managed)
        if [[ -n "$new" ]]; then
            printf '%s\n%s\n' "$new" "$CRON_LINE" | crontab -
        else
            printf '%s\n' "$CRON_LINE" | crontab -
        fi
        echo "[APPLY] cron line installed:"
        echo "  $CRON_LINE"
        echo ""
        echo "[APPLY] verify with: $0 --status"
        ;;

    --rollback|--uninstall)
        backup=$(backup_crontab "snapshot-cron-rollback")
        echo "[ROLLBACK] crontab backup → $backup"
        new=$(current_crontab | strip_managed)
        if [[ -n "$new" ]]; then
            printf '%s\n' "$new" | crontab -
        else
            # Empty crontab. Some crontab(1) implementations refuse
            # empty stdin; explicitly remove the user crontab instead.
            crontab -r 2>/dev/null || true
        fi
        echo "[ROLLBACK] managed cron line removed"
        echo ""
        echo "[ROLLBACK] to restore the prior crontab: crontab $backup"
        ;;

    -h|--help)
        usage
        ;;

    *)
        echo "unknown mode: $MODE" >&2
        sed -n '2,30p' "$0" >&2
        exit 2
        ;;
esac
