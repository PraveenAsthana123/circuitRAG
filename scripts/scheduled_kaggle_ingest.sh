#!/usr/bin/env bash
# ============================================================================
# scheduled_kaggle_ingest.sh — periodic dataset → ingestion-svc bridge.
# ============================================================================
# Pulls a Kaggle dataset, slices its tabular text into per-document files,
# and uploads any NEW ones (de-duped by sha256 of body) to ingestion-svc.
# Designed for a cron / systemd-timer slot:
#
#   */15 * * * * /mnt/deepa/rag/scripts/scheduled_kaggle_ingest.sh \
#       >> /var/log/documind/scheduled_ingest.log 2>&1
#
# The script is idempotent — re-running it never re-ingests an already-
# ingested article. New articles in a future Kaggle dataset version get
# picked up on the next cron tick.
#
# Required env (with sensible defaults for this dev box):
#   INGESTION_URL         http://127.0.0.1:8082
#   TENANT_ID             137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a
#   KAGGLE_DATASET        hgultekin/bbcnewsarchive
#   KAGGLE_FILE           bbc-news-data.csv  (the file inside the zip)
#   MAX_NEW_PER_RUN       8   (capped well below the rate-limit of 10/min)
#   STATE_DIR             /var/lib/documind/scheduled_ingest
# ============================================================================
set -euo pipefail

usage() {
    cat <<'EOF'
Periodically ingest new articles from a Kaggle dataset into ingestion-svc.

Usage:
  scripts/scheduled_kaggle_ingest.sh

Environment:
  INGESTION_URL    ingestion service base URL
  TENANT_ID        tenant UUID for uploads
  KAGGLE_DATASET   Kaggle dataset slug
  KAGGLE_FILE      CSV/TSV file inside the dataset archive
  MAX_NEW_PER_RUN  upload budget per run
  STATE_DIR        working directory for seen-set and temporary files
  PYTHON_BIN       Python interpreter for the slicing helper
EOF
}

case "${1:-}" in
    -h|--help)
        usage
        exit 0
        ;;
esac

INGESTION_URL="${INGESTION_URL:-http://127.0.0.1:8082}"
TENANT_ID="${TENANT_ID:-137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a}"
KAGGLE_DATASET="${KAGGLE_DATASET:-hgultekin/bbcnewsarchive}"
KAGGLE_FILE="${KAGGLE_FILE:-bbc-news-data.csv}"
MAX_NEW_PER_RUN="${MAX_NEW_PER_RUN:-8}"
STATE_DIR="${STATE_DIR:-/tmp/documind-scheduled-ingest}"

mkdir -p "$STATE_DIR"
SEEN_FILE="$STATE_DIR/seen.txt"
WORK_DIR="$STATE_DIR/work"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] scheduled_ingest: $*"; }

# ---- 1. Pull dataset (idempotent: kaggle CLI re-downloads, we slice fresh) ---
log "pulling $KAGGLE_DATASET..."
kaggle datasets download "$KAGGLE_DATASET" -p "$WORK_DIR" --unzip --force \
    > "$WORK_DIR/kaggle.log" 2>&1
if [ ! -f "$WORK_DIR/$KAGGLE_FILE" ]; then
    log "ERROR: expected file $KAGGLE_FILE not found in dataset zip"
    ls -la "$WORK_DIR/"
    exit 1
fi

# ---- 2. Slice CSV into per-article .txt files keyed by sha256 of body -------
log "slicing $KAGGLE_FILE..."
ARTICLES_DIR="$WORK_DIR/articles"
mkdir -p "$ARTICLES_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - "$WORK_DIR/$KAGGLE_FILE" "$ARTICLES_DIR" "$MAX_NEW_PER_RUN" \
              "$SEEN_FILE" <<'PY'
import csv, hashlib, pathlib, sys
csv_path, out_dir, max_new, seen_path = sys.argv[1:5]
out = pathlib.Path(out_dir)
seen_p = pathlib.Path(seen_path)
seen = set()
if seen_p.exists():
    seen = set(seen_p.read_text().splitlines())
new = 0
written: list[str] = []
with open(csv_path) as f:
    r = csv.DictReader(f, delimiter="\t")
    for row in r:
        body = f"{row['title']}\n\n{row['content'].strip()}\n"
        h = hashlib.sha256(body.encode()).hexdigest()[:16]
        if h in seen:
            continue
        if new >= int(max_new):
            break
        fname = f"{row['category']}-{row['filename'].replace('.txt','')}-{h}.txt"
        (out / fname).write_text(body)
        written.append(h)
        new += 1
print(f"sliced new={new} (budget={max_new})")
print(f"written: {' '.join(written) if written else '(none)'}")
PY

NEW_COUNT=$(ls "$ARTICLES_DIR" 2>/dev/null | wc -l)
if [ "$NEW_COUNT" -eq 0 ]; then
    log "no new articles to ingest — done"
    exit 0
fi
log "ingesting $NEW_COUNT new articles..."

# ---- 3. Upload each, record the sha256 only on successful 202 ---------------
ok=0; fail=0
for f in "$ARTICLES_DIR"/*.txt; do
    [ -f "$f" ] || continue
    h=$(basename "$f" | grep -oE '[0-9a-f]{16}\.txt$' | sed 's/\.txt//')
    code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$INGESTION_URL/api/v1/documents/upload?sync=false" \
        -H "X-Tenant-ID: $TENANT_ID" \
        -F "file=@$f")
    if [ "$code" = "202" ]; then
        echo "$h" >> "$SEEN_FILE"
        ok=$((ok+1))
    else
        fail=$((fail+1))
        log "  upload-fail file=$(basename "$f") code=$code"
    fi
done

log "uploaded ok=$ok fail=$fail (budget=$MAX_NEW_PER_RUN)"
