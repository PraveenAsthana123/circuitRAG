#!/usr/bin/env bash
# start_mcp_csv_ingest.sh — launch the approval-gated CSV ingest MCP server.
#
# Per ADR-028 this is a separate write-capable MCP server, not a
# documents-server extension.

set -uo pipefail

case "${1:-}" in
    -h|--help)
        cat <<'EOF'
start_mcp_csv_ingest.sh — launcher for the CSV ingest MCP server

USAGE
    bash scripts/start_mcp_csv_ingest.sh
    MCP_CSV_INGEST_PORT=8096 bash scripts/start_mcp_csv_ingest.sh

ENV
    MCP_CSV_INGEST_PORT                 Port to bind (default: 8095)
    CSV_INGEST_ALLOWED_TABLES           Comma-separated target table allowlist
    CSV_INGEST_SQLITE_PATH              Optional SQLite DB path for local apply
    CSV_INGEST_OPERATOR_APPROVAL_TOKEN  Optional token that marks approval accepted

ACTIVATION (inference-svc side)
    export DOCUMIND_MCP_CSV_INGEST_URL=http://localhost:8095
    docker compose restart inference-svc

OPTIONS
    -h, --help      Print this help and exit
EOF
        exit 0
        ;;
esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

PORT="${MCP_CSV_INGEST_PORT:-8095}"
VENV_PYTHON="$REPO/.venv/bin/python3"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "error: venv python not found at $VENV_PYTHON" >&2
    echo "       run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

echo "=== CSV ingest MCP server ($(date +%H:%M:%S)) ==="
echo "  port:   $PORT"
echo "  python: $VENV_PYTHON"
echo "  health: http://localhost:$PORT/health"
echo "  tools:  http://localhost:$PORT/tools/list"
echo

export PYTHONPATH="$REPO:$REPO/libs/py"
export MCP_CSV_INGEST_PORT="$PORT"

if "$VENV_PYTHON" -c "import uvicorn" 2>/dev/null; then
    exec "$VENV_PYTHON" -m uvicorn mcp.server_csv_ingest:app \
        --host 0.0.0.0 --port "$PORT" --log-level info
else
    echo "[warn] uvicorn not in venv; running via python -m" >&2
    exec "$VENV_PYTHON" -m mcp.server_csv_ingest
fi
