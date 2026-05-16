#!/usr/bin/env bash
# Regenerate ALL auto-generated documentation in one command.
#
# Per §58 Folder-README Standard, every folder has up to 4 generated files:
#   1. README.md                                  - auto-current, drill-locked
#   2. FOLDER_REPORT.md                           - generic 20-section review
#   3. FRONTEND_ASSESSMENT_REPORT.md OR
#      BACKEND_ASSESSMENT_REPORT.md               - profile-specific 25-section
#   4. (project root only) production-review report
#
# This script runs every generator in the canonical order, in parallel
# where safe (different generators) and sequential where coupled (project
# README must be regenerated AFTER all folder READMEs exist).
#
# Usage:
#   bash scripts/regen_all_docs.sh                       # all batches
#   bash scripts/regen_all_docs.sh --reviewer "Your Name"  # name on review skeletons
#   bash scripts/regen_all_docs.sh --skip-mcp            # mcp/ is huge; skip for fast iter
#   bash scripts/regen_all_docs.sh --dry-run             # preview only
#   bash scripts/regen_all_docs.sh --audit               # also re-run the score dashboard
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

REVIEWER="${REVIEWER:-Praveen Asthana}"
SKIP_MCP=0
DRY_RUN=0
RUN_AUDIT=0

while [ $# -gt 0 ]; do
    case "$1" in
        --reviewer) REVIEWER="$2"; shift 2 ;;
        --skip-mcp) SKIP_MCP=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --audit) RUN_AUDIT=1; shift ;;
        --help|-h)
            sed -n '1,/^set -euo/p' "$0" | head -n -1
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

DRY_FLAG=""
[ "$DRY_RUN" = "1" ] && DRY_FLAG="--dry-run"

echo "=== regen_all_docs.sh ==="
echo "Reviewer:  $REVIEWER"
echo "Skip mcp:  $SKIP_MCP"
echo "Dry run:   $DRY_RUN"
echo "Audit:     $RUN_AUDIT"
echo "Started:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# Phase 1 - folder READMEs (parallel-safe across batches)
echo "Phase 1: Folder READMEs (32+ sections each)"
python3 scripts/generate_folder_report.py --batch services $DRY_FLAG --force &
SVC_PID=$!
python3 scripts/generate_folder_report.py --batch libs $DRY_FLAG --force &
LIB_PID=$!
python3 scripts/generate_folder_report.py --batch python $DRY_FLAG --force &
PY_PID=$!
wait $SVC_PID || true
wait $LIB_PID || true
wait $PY_PID  || true

# Frontend + api-gateway aren't picked up by --batch services (no Python),
# so regen explicitly.
python3 scripts/generate_folder_report.py --folder services/frontend $DRY_FLAG --force || true
python3 scripts/generate_folder_report.py --folder services/api-gateway $DRY_FLAG --force || true

if [ "$SKIP_MCP" = "0" ]; then
    python3 scripts/generate_folder_report.py --batch mcp $DRY_FLAG --force || true
fi

# Phase 2 - FOLDER_REPORT.md (generic 20-section review skeleton)
echo
echo "Phase 2: FOLDER_REPORT.md (generic review skeletons)"
python3 scripts/generate_folder_review_report.py --batch all --force --reviewer "$REVIEWER" || true

# Phase 3 - profile-specific assessment reports
echo
echo "Phase 3: FRONTEND/BACKEND_ASSESSMENT_REPORT.md (profile-specific)"
python3 scripts/generate_specialized_assessment.py --batch all --profile auto --force --reviewer "$REVIEWER" || true

# Phase 4 - project root README (depends on folder READMEs existing)
echo
echo "Phase 4: Project root README.md (20 enterprise sections)"
python3 scripts/generate_project_readme.py --force

# Phase 5 - optional audit score dashboard
if [ "$RUN_AUDIT" = "1" ]; then
    echo
    echo "Phase 5: Audit score dashboard"
    mkdir -p docs/dashboards
    python3 scripts/audit_readme_scores.py --html docs/dashboards/readme-audit.html
fi

echo
echo "Completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "Verify drills still pass:"
echo "  python3 mcp/tests/drill_readme_generator.py        # expect 12/12"
echo "  python3 mcp/tests/drill_folder_review_report.py    # expect 12/12"
echo "  python3 mcp/tests/drill_audit_readme_scores.py     # expect 11/11"
