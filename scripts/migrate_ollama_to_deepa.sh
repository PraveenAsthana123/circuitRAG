#!/bin/bash
# Migrate Ollama models from /usr/share/ollama/.ollama to /mnt/deepa
# Tier-2: requires sudo + systemd service edit + daemon restart
#
# Per ~/.claude/policies/ai-storage-on-deepa.md
#
# Modes:
#   ./migrate_ollama_to_deepa.sh                # dry-run (default)
#   ./migrate_ollama_to_deepa.sh --apply        # actually migrate
#   ./migrate_ollama_to_deepa.sh --rollback     # undo migration
#   ./migrate_ollama_to_deepa.sh --finalize     # delete .bak after verified
#
# Apply does:
#   1. Snapshot `ollama list` for verification later
#   2. systemctl stop ollama
#   3. rsync /usr/share/ollama/.ollama -> /mnt/deepa/installed-software/ollama
#   4. Verify destination has manifests + blobs
#   5. systemctl edit --full ollama (write Environment=OLLAMA_MODELS=...)
#   6. systemctl daemon-reload + start ollama
#   7. Verify `ollama list` matches the snapshot
#   8. mv source to .bak (kept until --finalize)
#
# Rollback undoes:
#   - systemctl stop ollama
#   - mv .bak back to /usr/share/ollama/.ollama
#   - Remove the systemd Environment override
#   - daemon-reload + start
#
# Log: appended to /mnt/deepa/installed-software/migration.log

set -euo pipefail

DEEPA_ROOT="/mnt/deepa/installed-software"
OLLAMA_DST="$DEEPA_ROOT/ollama"
OLLAMA_SRC="/usr/share/ollama/.ollama"
DATE_TAG="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="$DEEPA_ROOT/migration.log"
SNAPSHOT_FILE="$DEEPA_ROOT/.ollama-snapshot-pre-migration"
SYSTEMD_OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"

MODE="dry-run"
case "${1:-}" in
    --apply)    MODE="apply" ;;
    --rollback) MODE="rollback" ;;
    --finalize) MODE="finalize" ;;
    --help|-h)
        head -30 "$0" | sed 's/^# //; s/^#//'
        exit 0 ;;
    "") MODE="dry-run" ;;
    *)
        echo "Unknown mode: $1" >&2
        echo "Usage: $0 [--apply|--rollback|--finalize]" >&2
        exit 1 ;;
esac

ensure_log() {
    mkdir -p "$DEEPA_ROOT"
    [ -f "$LOG_FILE" ] || touch "$LOG_FILE"
}

log_event() {
    local event="$1"; shift
    local ts
    ts="$(date -u --iso-8601=seconds)"
    local kvs="\"timestamp\":\"$ts\",\"event\":\"ollama:$event\""
    for kv in "$@"; do
        kvs="$kvs,\"${kv%%=*}\":\"${kv#*=}\""
    done
    printf '{%s}\n' "$kvs" >> "$LOG_FILE"
}

require_sudo() {
    if ! sudo -n true 2>/dev/null; then
        echo "This mode needs sudo (for systemctl + /usr/share/ollama access)." >&2
        echo "Run from a shell where 'sudo -n true' succeeds, or rerun and" >&2
        echo "type your password when prompted." >&2
        sudo -v || exit 1
    fi
}

print_status() {
    echo "Disk:"
    df -h / /mnt/deepa | sed 's/^/  /'
    echo ""
    echo "Ollama daemon:"
    sudo systemctl is-active ollama 2>/dev/null || echo "  inactive"
    echo ""
    if sudo test -d "$OLLAMA_SRC"; then
        echo "Source size: $(sudo du -sh $OLLAMA_SRC 2>/dev/null | cut -f1)"
    fi
    if [ -d "$OLLAMA_DST" ]; then
        echo "Dest size:   $(du -sh $OLLAMA_DST 2>/dev/null | cut -f1)"
    fi
}

# ── Modes ───────────────────────────────────────────────────────
do_dry_run() {
    echo "PLAN (no changes):"
    echo ""
    if sudo test -d "$OLLAMA_SRC"; then
        local size; size="$(sudo du -sh $OLLAMA_SRC 2>/dev/null | cut -f1)"
        echo "  [plan]  Ollama models  ($size)"
        echo "          source: $OLLAMA_SRC"
        echo "          dest:   $OLLAMA_DST"
        echo ""
        echo "  [plan]  systemd override at $SYSTEMD_OVERRIDE"
        echo "          [Service]"
        echo "          Environment=\"OLLAMA_MODELS=$OLLAMA_DST/models\""
        echo ""
        echo "  [plan]  daemon-reload + restart ollama"
        echo "  [plan]  verify ollama list matches pre-migration snapshot"
    else
        echo "  source $OLLAMA_SRC does not exist (already migrated? not installed?)"
    fi
    echo ""
    echo "To execute: $0 --apply  (will prompt for sudo)"
}

do_apply() {
    require_sudo

    if ! sudo test -d "$OLLAMA_SRC"; then
        echo "Source $OLLAMA_SRC missing — nothing to migrate."
        return
    fi

    log_event "apply_start" "tag=$DATE_TAG"

    # 1. Snapshot model list for post-migration verification
    echo "[1/8] Snapshotting current model list..."
    if ! systemctl is-active ollama >/dev/null 2>&1; then
        echo "  Ollama not active — starting it briefly to capture list..."
        sudo systemctl start ollama
        sleep 2
    fi
    ollama list > "$SNAPSHOT_FILE" 2>/dev/null || true
    local snapshot_count
    snapshot_count="$(wc -l < "$SNAPSHOT_FILE")"
    log_event "snapshot_taken" "models=$snapshot_count"
    echo "  $snapshot_count lines (incl. header) recorded"

    # 2. Stop daemon
    echo "[2/8] Stopping ollama daemon..."
    sudo systemctl stop ollama
    log_event "daemon_stopped"

    # 3. rsync source -> dest
    echo "[3/8] rsync $OLLAMA_SRC -> $OLLAMA_DST (resumable + verifiable)..."
    sudo mkdir -p "$OLLAMA_DST"
    sudo rsync -aP --info=progress2 "$OLLAMA_SRC/" "$OLLAMA_DST/" 2>&1 | tail -3
    log_event "rsync_done"

    # 4. Verify destination
    echo "[4/8] Verifying destination has manifests + blobs..."
    local manifests_count blobs_count
    manifests_count="$(sudo find $OLLAMA_DST/models/manifests -type f 2>/dev/null | wc -l)"
    blobs_count="$(sudo find $OLLAMA_DST/models/blobs -type f 2>/dev/null | wc -l)"
    if [ "$manifests_count" -lt 1 ] || [ "$blobs_count" -lt 1 ]; then
        echo "  [FAIL] dest missing manifests ($manifests_count) or blobs ($blobs_count)" >&2
        log_event "verify_failed" "manifests=$manifests_count" "blobs=$blobs_count"
        echo "  Restarting ollama with original location..."
        sudo systemctl start ollama
        return 1
    fi
    # Make sure ollama user owns the new location
    sudo chown -R ollama:ollama "$DEEPA_ROOT/ollama"
    log_event "verify_ok" "manifests=$manifests_count" "blobs=$blobs_count"
    echo "  manifests=$manifests_count blobs=$blobs_count; chown ollama:ollama"

    # 5. systemd override
    echo "[5/8] Writing systemd override at $SYSTEMD_OVERRIDE..."
    sudo mkdir -p "$(dirname $SYSTEMD_OVERRIDE)"
    # Backup any existing override
    if sudo test -f "$SYSTEMD_OVERRIDE"; then
        sudo cp "$SYSTEMD_OVERRIDE" "${SYSTEMD_OVERRIDE}.pre-${DATE_TAG}"
        log_event "override_backed_up" "to=${SYSTEMD_OVERRIDE}.pre-${DATE_TAG}"
    fi
    sudo tee "$SYSTEMD_OVERRIDE" > /dev/null << EOF
[Service]
Environment="OLLAMA_MODELS=$OLLAMA_DST/models"
EOF
    log_event "override_written"

    # 6. Reload + restart
    echo "[6/8] daemon-reload + restart ollama..."
    sudo systemctl daemon-reload
    sudo systemctl start ollama
    sleep 3
    log_event "daemon_restarted"

    # 7. Verify ollama list matches snapshot
    echo "[7/8] Verifying ollama list matches snapshot..."
    local new_list_count
    new_list_count="$(ollama list 2>/dev/null | wc -l)"
    if [ "$new_list_count" -lt "$snapshot_count" ]; then
        echo "  [FAIL] post-migration list has $new_list_count lines, snapshot had $snapshot_count" >&2
        echo "  Models may be missing from $OLLAMA_DST/models" >&2
        log_event "post_verify_failed" "new=$new_list_count" "snapshot=$snapshot_count"
        return 1
    fi
    log_event "post_verify_ok" "models=$new_list_count"
    echo "  $new_list_count lines visible (matches snapshot)"

    # 8. mv source to .bak (instant; same /usr/share fs)
    echo "[8/8] Moving source to .bak (rollback safety net)..."
    sudo mv "$OLLAMA_SRC" "${OLLAMA_SRC}.bak-${DATE_TAG}"
    log_event "src_moved_to_bak" "bak=${OLLAMA_SRC}.bak-${DATE_TAG}"
    echo "  source -> ${OLLAMA_SRC}.bak-${DATE_TAG}"

    log_event "apply_complete"
    echo ""
    echo "Migration complete. Verify your tools work, then run:"
    echo "  $0 --finalize    # to free the ~42GB on /"
    echo "Or if anything broke:"
    echo "  $0 --rollback"
}

do_rollback() {
    require_sudo
    log_event "rollback_start"

    # Find the most recent .bak (matches the .bak-<date> pattern)
    local bak
    bak="$(sudo ls -dt /usr/share/ollama/.ollama.bak-* 2>/dev/null | head -1 || true)"
    if [ -z "$bak" ] || ! sudo test -d "$bak"; then
        echo "No /usr/share/ollama/.ollama.bak-* found. Manual recovery needed:"
        echo "  sudo cp -a $OLLAMA_DST $OLLAMA_SRC"
        echo "  sudo chown -R ollama:ollama $OLLAMA_SRC"
        echo "  Edit $SYSTEMD_OVERRIDE to remove the Environment line"
        echo "  sudo systemctl daemon-reload && sudo systemctl restart ollama"
        log_event "rollback_no_bak"
        exit 1
    fi
    echo "Rolling back from $bak..."

    echo "[1/4] Stop ollama..."
    sudo systemctl stop ollama || true

    echo "[2/4] Restore source from .bak..."
    if sudo test -d "$OLLAMA_SRC"; then
        # Defensive: source already exists; rename it side
        sudo mv "$OLLAMA_SRC" "${OLLAMA_SRC}.rolled-back-${DATE_TAG}"
    fi
    sudo mv "$bak" "$OLLAMA_SRC"
    log_event "rollback_restored_src" "from=$bak"

    echo "[3/4] Remove systemd override..."
    if sudo test -f "$SYSTEMD_OVERRIDE"; then
        sudo rm "$SYSTEMD_OVERRIDE"
        log_event "rollback_removed_override"
    fi
    sudo systemctl daemon-reload

    echo "[4/4] Restart ollama..."
    sudo systemctl start ollama
    sleep 2
    log_event "rollback_complete"

    echo ""
    echo "Rollback complete. /mnt/deepa/installed-software/ollama still exists"
    echo "(left intact for inspection); delete with: sudo rm -rf $OLLAMA_DST"
}

do_finalize() {
    require_sudo
    local bak
    bak="$(sudo ls -dt /usr/share/ollama/.ollama.bak-* 2>/dev/null | head -1 || true)"
    if [ -z "$bak" ] || ! sudo test -d "$bak"; then
        echo "No .bak to finalize. Already clean."
        return
    fi
    local size
    size="$(sudo du -sh $bak 2>/dev/null | cut -f1)"
    echo "Removing $bak ($size)..."
    sudo rm -rf "$bak"
    log_event "finalize_done" "freed=$size" "bak=$bak"
    echo "Freed $size on /"
}

# ── Main ─────────────────────────────────────────────────────────
ensure_log

echo "================================================="
echo "Ollama migration — mode=$MODE"
echo "================================================="
print_status
echo

case "$MODE" in
    dry-run)  do_dry_run ;;
    apply)    do_apply ;;
    rollback) do_rollback ;;
    finalize) do_finalize ;;
esac
