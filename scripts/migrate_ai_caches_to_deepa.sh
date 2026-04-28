#!/bin/bash
# Migrate Tier-1 AI caches from / to /mnt/deepa/installed-software/
# Safe by design:
#   * rsync (resumable, non-destructive)
#   * source kept as <path>.bak-<date> until operator confirms
#   * symlink so existing tools still work
#   * rollback script preserves original until --finalize
#
# Per ~/.claude/policies/ai-storage-on-deepa.md
#
# Modes:
#   ./migrate_ai_caches_to_deepa.sh                # dry-run (default)
#   ./migrate_ai_caches_to_deepa.sh --apply        # actually migrate
#   ./migrate_ai_caches_to_deepa.sh --rollback     # undo last migration
#   ./migrate_ai_caches_to_deepa.sh --finalize     # delete .bak after verified
#
# Log: /mnt/deepa/installed-software/migration.log (JSONL, append-only)

set -euo pipefail

DEEPA_ROOT="/mnt/deepa/installed-software"
DATE_TAG="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="$DEEPA_ROOT/migration.log"
BAK_INDEX="$DEEPA_ROOT/.bak-index"

MODE="dry-run"
case "${1:-}" in
    --apply)    MODE="apply" ;;
    --rollback) MODE="rollback" ;;
    --finalize) MODE="finalize" ;;
    --help|-h)
        head -22 "$0" | sed 's/^# //; s/^#//'
        exit 0 ;;
    "") MODE="dry-run" ;;
    *)
        echo "Unknown mode: $1" >&2
        echo "Usage: $0 [--apply|--rollback|--finalize]" >&2
        exit 1 ;;
esac

# Tier-1 migration plan: source -> destination under DEEPA_ROOT
# Format: source_path|dest_subpath|description
declare -a PLAN=(
    "$HOME/.cache/huggingface|huggingface|HuggingFace Hub + Transformers + Datasets cache"
    "$HOME/.cache/pip|cache/pip|pip download cache"
    "$HOME/.cache/uv|cache/uv|uv (rust-based python pkg) cache"
    "$HOME/.cache/torch|torch|PyTorch model cache"
    "$HOME/.cache/ms-playwright|cache/playwright|Playwright browser binaries"
)

ensure_log() {
    mkdir -p "$DEEPA_ROOT"
    [ -f "$LOG_FILE" ] || touch "$LOG_FILE"
    [ -f "$BAK_INDEX" ] || touch "$BAK_INDEX"
}

log_event() {
    # log_event <event> <key=val> ...
    local event="$1"; shift
    local ts
    ts="$(date -u --iso-8601=seconds)"
    local kvs="\"timestamp\":\"$ts\",\"event\":\"$event\""
    for kv in "$@"; do
        kvs="$kvs,\"${kv%%=*}\":\"${kv#*=}\""
    done
    printf '{%s}\n' "$kvs" >> "$LOG_FILE"
}

human_size() {
    du -sh "$1" 2>/dev/null | cut -f1
}

dry_run_one() {
    local src="$1" dest="$2" desc="$3"
    if [ ! -e "$src" ]; then
        echo "  [skip]  $desc"
        echo "          source not present: $src"
        return
    fi
    local size; size="$(human_size "$src")"
    echo "  [plan]  $desc  ($size)"
    echo "          $src"
    echo "          -> $DEEPA_ROOT/$dest"
}

apply_one() {
    local src="$1" dest_subpath="$2" desc="$3"
    local dest="$DEEPA_ROOT/$dest_subpath"
    local bak="${src}.bak-${DATE_TAG}"

    if [ ! -e "$src" ]; then
        log_event "skip" "src=$src" "reason=not_present"
        echo "  [skip]    $desc — source missing"
        return
    fi
    if [ -L "$src" ]; then
        log_event "skip" "src=$src" "reason=already_symlinked"
        echo "  [skip]    $desc — already a symlink"
        return
    fi
    local size; size="$(human_size "$src")"
    echo "  [moving]  $desc  ($size)"
    log_event "migrate_start" "src=$src" "dest=$dest" "size=$size"

    # 1. rsync to destination (resumable; preserves perms; --delete handles partial prior runs)
    mkdir -p "$(dirname "$dest")"
    rsync -aP --no-i-r --info=progress2 "$src/" "$dest/" 2>&1 | tail -3
    log_event "rsync_done" "src=$src" "dest=$dest"

    # 2. Verify destination has at least as much content as source
    local src_count; src_count="$(find "$src" -type f 2>/dev/null | wc -l)"
    local dest_count; dest_count="$(find "$dest" -type f 2>/dev/null | wc -l)"
    if [ "$dest_count" -lt "$src_count" ]; then
        log_event "verify_failed" "src_count=$src_count" "dest_count=$dest_count"
        echo "  [FAIL]   verify: dest has $dest_count files, src has $src_count" >&2
        return 1
    fi
    log_event "verify_ok" "files=$dest_count"

    # 3. Move source to .bak (instant; same filesystem; reversible)
    mv "$src" "$bak"
    log_event "moved_to_bak" "src=$src" "bak=$bak"

    # 4. Symlink old path to new location
    ln -s "$dest" "$src"
    log_event "symlinked" "link=$src" "target=$dest"

    # 5. Record in index for --rollback / --finalize
    echo "$bak|$src|$dest|$DATE_TAG" >> "$BAK_INDEX"

    echo "  [done]    $desc"
    echo "            symlink: $src -> $dest"
    echo "            backup:  $bak"
}

rollback_all() {
    if [ ! -s "$BAK_INDEX" ]; then
        echo "Nothing to roll back (bak-index empty)."
        return
    fi
    echo "Rolling back ALL recorded migrations..."
    # Reverse order so most-recent rollbacks first
    tac "$BAK_INDEX" | while IFS='|' read -r bak link dest tag; do
        if [ ! -e "$bak" ]; then
            echo "  [skip] $link — bak missing ($bak)"
            log_event "rollback_skip" "link=$link" "reason=bak_missing"
            continue
        fi
        if [ -L "$link" ]; then
            rm "$link"
            log_event "rollback_rm_symlink" "link=$link"
        fi
        mv "$bak" "$link"
        log_event "rollback_restore" "bak=$bak" "link=$link"
        echo "  [restored] $link"
    done
    # Clear the index
    > "$BAK_INDEX"
    log_event "rollback_complete" "scope=all"
    echo "Rollback complete. /mnt/deepa copies untouched (you may delete manually)."
}

finalize_all() {
    if [ ! -s "$BAK_INDEX" ]; then
        echo "No backups to finalize (bak-index empty)."
        return
    fi
    local total_freed=0
    while IFS='|' read -r bak link dest tag; do
        if [ ! -e "$bak" ]; then
            echo "  [skip] $bak — already removed"
            continue
        fi
        local size; size="$(du -sb "$bak" 2>/dev/null | cut -f1)"
        rm -rf "$bak"
        log_event "finalized" "bak=$bak" "freed_bytes=$size"
        total_freed=$((total_freed + size))
        echo "  [removed] $bak"
    done < "$BAK_INDEX"
    > "$BAK_INDEX"
    local human; human="$(numfmt --to=iec --suffix=B "$total_freed" 2>/dev/null || echo "$total_freed bytes")"
    log_event "finalize_complete" "freed=$human"
    echo "Finalized. Total freed: $human"
}

print_disk_status() {
    echo "Disk status:"
    df -h / /mnt/deepa | sed 's/^/  /'
}

# ── Main ─────────────────────────────────────────────────────────
ensure_log
log_event "session_start" "mode=$MODE" "tag=$DATE_TAG"

echo "=================================================="
echo "AI cache migration — mode=$MODE"
echo "=================================================="
print_disk_status
echo

case "$MODE" in
    dry-run)
        echo "PLAN (no changes will be made):"
        echo
        for entry in "${PLAN[@]}"; do
            IFS='|' read -r src dest desc <<<"$entry"
            dry_run_one "$src" "$dest" "$desc"
        done
        echo
        echo "To execute: $0 --apply"
        echo "After verifying things work: $0 --finalize"
        echo "If anything breaks: $0 --rollback"
        ;;
    apply)
        echo "APPLYING MIGRATION..."
        echo
        for entry in "${PLAN[@]}"; do
            IFS='|' read -r src dest desc <<<"$entry"
            apply_one "$src" "$dest" "$desc"
        done
        echo
        print_disk_status
        echo
        echo "Backups kept at <source>.bak-${DATE_TAG} for rollback."
        echo "Verify your tools work, then: $0 --finalize"
        ;;
    rollback)
        rollback_all
        echo
        print_disk_status
        ;;
    finalize)
        finalize_all
        echo
        print_disk_status
        ;;
esac

log_event "session_end" "mode=$MODE"
