#!/usr/bin/env bash
# revert_auto_apply.sh — atomically revert daemon auto-applied fix(es).
#
# Per CLAUDE.md §50 + Tier 2 #2.10. Every daemon-applied fix is
# tagged `auto-apply-<issue_id>` at commit time. This script reverts
# by tag — single revert OR a range — without touching any
# operator-author commits.
#
# §42 SAFETY: revert creates a NEW commit (no force-push, no
# history rewrite). Push remains operator-only via:
#     python3 scripts/agent_task_board.py push --confirm

case "${1:-}" in
  -h|--help|"")
    cat <<'HELP'
revert_auto_apply.sh — revert daemon-applied fixes by tag

Usage:
  bash scripts/revert_auto_apply.sh --list                   # show all auto-apply tags
  bash scripts/revert_auto_apply.sh --revert <tag>           # revert single tag (creates new commit)
  bash scripts/revert_auto_apply.sh --revert-range <a> <b>   # revert all tags in range (newest..oldest)
  bash scripts/revert_auto_apply.sh --status <tag>           # show what tag points at

Per Tier 2 #2.10 of the autonomous-fix-bot roadmap. Tags follow
pattern `auto-apply-<sanitized-issue-id>` and are added by
autonomous_fix_daemon.py auto_commit_applied().

§42: NEVER force-pushes. Revert creates a new commit; operator
must `agent_task_board.py push --confirm` to ship.
HELP
    exit 0
    ;;
esac

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

case "$1" in
  --list)
    echo "Auto-apply tags (newest first):"
    git tag --list "auto-apply-*" --sort=-creatordate | head -30
    ;;
  --status)
    if [ -z "${2:-}" ]; then
      echo "x --status requires a tag name"
      exit 1
    fi
    if ! git rev-parse --verify "$2" >/dev/null 2>&1; then
      echo "x tag not found: $2"
      exit 1
    fi
    git show "$2" --stat --no-patch
    ;;
  --revert)
    if [ -z "${2:-}" ]; then
      echo "x --revert requires a tag name"
      exit 1
    fi
    tag="$2"
    if ! git rev-parse --verify "$tag" >/dev/null 2>&1; then
      echo "x tag not found: $tag"
      exit 1
    fi
    echo "Reverting commit at tag $tag..."
    git revert --no-edit "$tag"
    echo "✓ revert commit created (NOT yet pushed; §42)"
    ;;
  --revert-range)
    if [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
      echo "x --revert-range requires <newest-tag> <oldest-tag>"
      exit 1
    fi
    newest="$2"
    oldest="$3"
    echo "Reverting all auto-apply commits between $newest and $oldest (newest first)..."
    range=$(git log --format='%H' "$oldest^..$newest" 2>/dev/null)
    if [ -z "$range" ]; then
      echo "x range $oldest..$newest produced no commits"
      exit 1
    fi
    git revert --no-edit $range
    echo "✓ range revert commits created (NOT yet pushed; §42)"
    ;;
  *)
    echo "x unknown command: $1"
    echo "Run with --help for usage."
    exit 1
    ;;
esac
