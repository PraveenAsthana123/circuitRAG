#!/usr/bin/env bash
# Generate an RSA keypair for JWT signing in local dev.
# Output: scripts/dev-keys/jwt-{private,public}.pem
# Never use these keys outside dev.
set -euo pipefail

OUT="${1:-scripts/dev-keys}"
mkdir -p "$OUT"

if [[ -f "$OUT/jwt-private.pem" && -f "$OUT/jwt-public.pem" ]]; then
    echo "dev jwt keypair already exists at $OUT"
    exit 0
fi

# 2048-bit RSA, PKCS#8 for the private key so both Go and Python parse it.
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$OUT/jwt-private.pem"
openssl rsa -in "$OUT/jwt-private.pem" -pubout -out "$OUT/jwt-public.pem"
chmod 600 "$OUT/jwt-private.pem"
chmod 644 "$OUT/jwt-public.pem"

echo "dev jwt keypair written to $OUT/"
echo "  private: $OUT/jwt-private.pem"
echo "  public:  $OUT/jwt-public.pem"
