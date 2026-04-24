#!/usr/bin/env bash
# Generate a self-signed TLS cert for local dev NGINX.
# Lands under ./data/nginx-tls/ (mounted into the container).
set -euo pipefail

OUT_DIR="${1:-./data/nginx-tls}"
mkdir -p "$OUT_DIR"

if [[ -f "$OUT_DIR/server.crt" && -f "$OUT_DIR/server.key" ]]; then
    echo "dev cert already exists at $OUT_DIR"
    exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -keyout "$OUT_DIR/server.key" \
    -out "$OUT_DIR/server.crt" -days 365 \
    -subj "/C=US/ST=Dev/L=Local/O=DocuMind/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:documind.local,IP:127.0.0.1"

chmod 600 "$OUT_DIR/server.key"
chmod 644 "$OUT_DIR/server.crt"
echo "dev TLS cert written to $OUT_DIR"
