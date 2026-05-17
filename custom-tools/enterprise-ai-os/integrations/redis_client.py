import os
import json
import redis
from typing import Any


class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True
        )

    def set_json(self, key: str, value: Any, ttl_seconds: int = 3600):
        self.client.set(
            key,
            json.dumps(value),
            ex=ttl_seconds
        )

    def get_json(self, key: str):
        value = self.client.get(key)

        if not value:
            return None

        return json.loads(value)

    def delete(self, key: str):
        self.client.delete(key)
