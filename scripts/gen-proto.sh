#!/usr/bin/env bash
# Regenerate gRPC stubs for Go + Python from proto/*.proto.
# Requires: protoc, protoc-gen-go, protoc-gen-go-grpc, grpcio-tools (Python).
#
# Install:
#   Go:     go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
#           go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
#   Python: pip install 'grpcio-tools>=1.65'
#
# Output:
#   proto/**/*_pb2.py           (Python messages)
#   proto/**/*_pb2_grpc.py      (Python stubs)
#   proto/**/*.pb.go             (Go messages)
#   proto/**/*_grpc.pb.go        (Go stubs)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.."; pwd)"
cd "$ROOT"

PROTO_DIR="proto"
PROTOS=$(find "$PROTO_DIR" -name "*.proto")

# ---- Go ---------------------------------------------------------------------
if command -v protoc-gen-go >/dev/null 2>&1; then
  echo "[proto] Go stubs..."
  protoc -I"$PROTO_DIR" \
    --go_out=. --go_opt=paths=source_relative \
    --go-grpc_out=. --go-grpc_opt=paths=source_relative \
    $PROTOS
else
  echo "[proto] skipping Go (install protoc-gen-go + protoc-gen-go-grpc)"
fi

# ---- Python -----------------------------------------------------------------
if python3 -c "import grpc_tools.protoc" 2>/dev/null; then
  echo "[proto] Python stubs..."
  python3 -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$PROTO_DIR" \
    --grpc_python_out="$PROTO_DIR" \
    $PROTOS

  # Add empty __init__.py so Python can import them as packages.
  find "$PROTO_DIR" -type d -exec touch {}/__init__.py \;
else
  echo "[proto] skipping Python (install 'grpcio-tools>=1.65')"
fi

echo "[proto] done."
