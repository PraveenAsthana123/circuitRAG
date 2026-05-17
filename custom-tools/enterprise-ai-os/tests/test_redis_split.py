# Negative drills for Iter 37 (2026-05-17): Redis text/binary split.

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def patched_redis(monkeypatch):
    import integrations.redis_client as mod
    instances = []
    def fake_redis(**kwargs):
        i = MagicMock()
        i._kwargs = kwargs
        i._store = {}
        def fake_set(key, value, ex=None):
            i._store[key] = value
        def fake_get(key):
            return i._store.get(key)
        def fake_delete(key):
            i._store.pop(key, None)
        i.set.side_effect = fake_set
        i.get.side_effect = fake_get
        i.delete.side_effect = fake_delete
        instances.append(i)
        return i
    monkeypatch.setattr(mod.redis, "Redis", fake_redis)
    return mod, instances


def test_BACKDOOR_CHECK_text_client_uses_decode_true(patched_redis):
    """Pre-fix: only one client existed and it always decoded
    responses — silently corrupting binary."""
    mod, instances = patched_redis
    mod.RedisClient()
    assert instances[0]._kwargs["decode_responses"] is True


def test_binary_client_uses_decode_false(patched_redis):
    mod, instances = patched_redis
    mod.RedisBinaryClient()
    assert instances[0]._kwargs["decode_responses"] is False


def test_binary_client_round_trip_with_real_bytes(patched_redis):
    mod, _ = patched_redis
    client = mod.RedisBinaryClient()
    payload = bytes([0x00, 0xff, 0x80, 0x01, 0x7f])  # non-UTF8
    client.set_bytes("key", payload)
    assert client.get_bytes("key") == payload


def test_binary_client_rejects_non_bytes_input(patched_redis):
    mod, _ = patched_redis
    client = mod.RedisBinaryClient()
    with pytest.raises(TypeError):
        client.set_bytes("key", "string-not-bytes")  # type: ignore


def test_text_client_json_round_trip(patched_redis):
    mod, _ = patched_redis
    client = mod.RedisClient()
    client.set_json("k", {"hello": "world"})
    # Simulate what redis returns after JSON serialization with
    # decode_responses=True: a string.
    assert client.client._store["k"] == '{"hello": "world"}'


def test_get_returns_none_on_missing_key(patched_redis):
    mod, _ = patched_redis
    assert mod.RedisClient().get_json("missing") is None
    assert mod.RedisBinaryClient().get_bytes("missing") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
