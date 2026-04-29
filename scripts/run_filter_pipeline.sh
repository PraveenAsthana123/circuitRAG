#!/bin/bash
# Phase 5X: orchestrate snapshot → prom export → alert/webhook in one call.
#
# The 5K-5W mini-arc shipped seven independent operator tools; cron
# would have to invoke three of them per day. This wrapper does it as
# one call so a single crontab line covers the whole telemetry surface:
#
#   5 0 * * * scripts/run_filter_pipeline.sh \
#       --prometheus-out /var/lib/node_exporter/textfile/council.prom \
#       --webhook "https://hooks.slack.com/services/XXX" \
#       --alert-on "filtered>0.5"
#
# Design:
#   * EACH step runs INDEPENDENTLY — a snapshot failure does NOT abort
#     the prom export (which can use yesterday's snapshot), and a prom
#     export failure does NOT abort alerts (which read the live log).
#   * Active by default — cron invocations should DO things, not say
#     "would do things". Use --dry-run for preview.
#   * Exit code mirrors 5O: 1 if any alert fires, 0 otherwise. Step-
#     execution failures log to stderr but don't change the exit
#     code (best-effort orchestration).
#
# Usage:
#   scripts/run_filter_pipeline.sh                       # run all steps
#   scripts/run_filter_pipeline.sh --dry-run             # show commands
#   scripts/run_filter_pipeline.sh --prometheus-out PATH # add prom export
#   scripts/run_filter_pipeline.sh --webhook URL         # add webhook
#   scripts/run_filter_pipeline.sh --alert-on EXPR       # add alert (repeat)
#   scripts/run_filter_pipeline.sh --snapshot-date DATE  # override target date
#   scripts/run_filter_pipeline.sh --skip-snapshot       # don't snapshot
#   scripts/run_filter_pipeline.sh --skip-prometheus     # don't prom export
#
# Env:
#   PYTHON_BIN   — interpreter (default: /mnt/deepa/rag/.venv/bin/python)
#   COUNCIL_STATS_ENV_FILE — env file to source before flag parsing
#                            (default: /mnt/deepa/rag/.loop/council-stats.env)
#   COUNCIL_STATS_WEBHOOK — webhook URL (overridable via --webhook)
#
# Exit codes:
#   0  pipeline ran; no alerts fired
#   1  pipeline ran; one or more alerts fired
#   2  bad usage

set -uo pipefail   # NOT set -e: each step is independent

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON_BIN:-$REPO/.venv/bin/python}"
SNAPSHOT_SCRIPT="$REPO/scripts/council_stats_snapshot.py"
STATS_SCRIPT="$REPO/scripts/council_filter_stats.py"
ENV_FILE="${COUNCIL_STATS_ENV_FILE:-$REPO/.loop/council-stats.env}"

# Load operator-provided env without forcing secrets into crontab.
# Missing file is fine; malformed file degrades to stderr + no env values.
if [[ -f "$ENV_FILE" ]]; then
    set +u
    set -a
    # shellcheck disable=SC1090
    if ! . "$ENV_FILE"; then
        echo "[env] ✗ failed to load $ENV_FILE (continuing without env file)" >&2
    fi
    set +a
    set -u
fi

DRY_RUN=0
PROMETHEUS_OUT=""
WEBHOOK="${COUNCIL_STATS_WEBHOOK:-}"
WEBHOOK_FORMAT="generic"
SNAPSHOT_DATE=""
SKIP_SNAPSHOT=0
SKIP_PROMETHEUS=0
ALERT_EXPRS=()

usage() {
    sed -n '2,30p' "$0" >&2
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)        DRY_RUN=1; shift ;;
        --prometheus-out) PROMETHEUS_OUT="$2"; shift 2 ;;
        --webhook)        WEBHOOK="$2"; shift 2 ;;
        --webhook-format) WEBHOOK_FORMAT="$2"; shift 2 ;;
        --alert-on)       ALERT_EXPRS+=("$2"); shift 2 ;;
        --snapshot-date)  SNAPSHOT_DATE="$2"; shift 2 ;;
        --skip-snapshot)  SKIP_SNAPSHOT=1; shift ;;
        --skip-prometheus) SKIP_PROMETHEUS=1; shift ;;
        -h|--help)        usage ;;
        *)
            echo "unknown flag: $1" >&2
            sed -n '2,30p' "$0" >&2
            exit 2
            ;;
    esac
done

# ── helper: run a step, log result, never abort the pipeline ────────
# Args: step_label, command...
run_step() {
    local label="$1"; shift
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] [$label]: $*" >&2
        return 0
    fi
    echo "[$label] ▶ $*" >&2
    "$@"
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        echo "[$label] ✓ ok" >&2
    else
        echo "[$label] ✗ exit $rc (continuing pipeline)" >&2
    fi
    return $rc
}

# ── Step 1: snapshot ───────────────────────────────────────────────
if [[ $SKIP_SNAPSHOT -eq 0 ]]; then
    snap_args=("$PYTHON" "$SNAPSHOT_SCRIPT")
    if [[ -n "$SNAPSHOT_DATE" ]]; then
        snap_args+=(--date "$SNAPSHOT_DATE")
    fi
    run_step "snapshot" "${snap_args[@]}"
else
    echo "[snapshot] (skipped per --skip-snapshot)" >&2
fi

# ── Step 2: prometheus export ──────────────────────────────────────
if [[ $SKIP_PROMETHEUS -eq 0 && -n "$PROMETHEUS_OUT" ]]; then
    prom_args=("$PYTHON" "$STATS_SCRIPT"
               --prometheus
               --from-snapshot
               --prometheus-out "$PROMETHEUS_OUT")
    run_step "prometheus" "${prom_args[@]}"
elif [[ $SKIP_PROMETHEUS -eq 1 ]]; then
    echo "[prometheus] (skipped per --skip-prometheus)" >&2
elif [[ -z "$PROMETHEUS_OUT" ]]; then
    echo "[prometheus] (skipped: no --prometheus-out path given)" >&2
fi

# ── Step 3: alerts + webhook ───────────────────────────────────────
ALERT_EXIT=0
if [[ ${#ALERT_EXPRS[@]} -gt 0 ]]; then
    alert_args=("$PYTHON" "$STATS_SCRIPT")
    for expr in "${ALERT_EXPRS[@]}"; do
        alert_args+=(--alert-on "$expr")
    done
    if [[ -n "$WEBHOOK" ]]; then
        alert_args+=(--webhook "$WEBHOOK"
                     --webhook-format "$WEBHOOK_FORMAT")
    fi
    run_step "alerts" "${alert_args[@]}" >/dev/null
    ALERT_EXIT=$?
else
    echo "[alerts] (skipped: no --alert-on expressions)" >&2
fi

# ── Final exit ─────────────────────────────────────────────────────
# Mirror 5O's contract: alerts fired → 1, otherwise → 0. The pipeline
# itself doesn't propagate per-step failures — operators care about
# alert state, not whether one optional step glitched.
if [[ $ALERT_EXIT -eq 1 ]]; then
    echo "[pipeline] ✗ alerts fired (exit 1)" >&2
    exit 1
fi
echo "[pipeline] ✓ all steps completed" >&2
exit 0
