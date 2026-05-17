# ✅ P2 IMPROVED (Iter 37, 2026-05-17): split into text + binary
#     clients. Pre-fix the single client used decode_responses=True,
#     which silently broke any caller that wanted to store binary
#     data (embeddings, raw bytes, encoded protobuf). bytes→str
#     decode would either raise UnicodeDecodeError on non-UTF8 binary
#     or silently corrupt.
#
#     Now:
#       - RedisClient: text-only (decode_responses=True). For JSON
#         payloads and string keys/values. Preserves the original
#         set_json / get_json / delete API.
#       - RedisBinaryClient: bytes-only (decode_responses=False).
#         For embeddings and other raw-byte values. Caller owns
#         encoding/decoding.
#       - Both share the same connection kwargs from env.

import os
import json
import redis
from typing import Any


def _connection_kwargs():
    return {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
    }


class RedisClient:
    """Text/JSON client (decode_responses=True). Existing API
    preserved for backcompat."""

    def __init__(self):
        self.client = redis.Redis(
            **_connection_kwargs(),
            decode_responses=True,
        )

    def set_json(self, key: str, value: Any, ttl_seconds: int = 3600):
        self.client.set(key, json.dumps(value), ex=ttl_seconds)

    def get_json(self, key: str):
        value = self.client.get(key)
        if not value:
            return None
        return json.loads(value)

    def delete(self, key: str):
        self.client.delete(key)


class RedisBinaryClient:
    """Bytes client (decode_responses=False). For embeddings, raw
    encoded payloads. Caller is responsible for encoding."""

    def __init__(self):
        self.client = redis.Redis(
            **_connection_kwargs(),
            decode_responses=False,
        )

    def set_bytes(self, key: str, value: bytes, ttl_seconds: int = 3600):
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError("RedisBinaryClient.set_bytes requires bytes")
        self.client.set(key, bytes(value), ex=ttl_seconds)

    def get_bytes(self, key: str) -> bytes | None:
        value = self.client.get(key)
        if value is None:
            return None
        # value is bytes when decode_responses=False
        return value if isinstance(value, (bytes, bytearray)) else bytes(value)

    def delete(self, key: str):
        self.client.delete(key)
