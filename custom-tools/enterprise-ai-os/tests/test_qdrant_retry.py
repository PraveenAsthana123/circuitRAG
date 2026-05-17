# Negative drills for Iter 30 (2026-05-17): QdrantVectorClient retry.

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def qdrant_with_mock(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://test:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "test_collection")
    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = []

    import integrations.qdrant_client as mod
    monkeypatch.setattr(mod, "QdrantClient", lambda **kwargs: mock_qdrant)
    from integrations.retry_policy import RetryPolicy

    client = mod.QdrantVectorClient(
        retry_policy=RetryPolicy(max_retries=3, base_delay_ms=1,
                                  retry_on=(ConnectionError, TimeoutError)),
    )
    return client, mock_qdrant


def test_BACKDOOR_CHECK_retries_on_connection_error(qdrant_with_mock):
    client, mock = qdrant_with_mock
    attempts = {"n": 0}
    def flaky_search(**_):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return []
    mock.search.side_effect = flaky_search

    result = client.search(query_vector=[0.1])
    assert result == []
    assert attempts["n"] == 3


def test_propagates_non_retryable_error(qdrant_with_mock):
    client, mock = qdrant_with_mock
    mock.search.side_effect = ValueError("schema mismatch — not transient")
    with pytest.raises(ValueError, match="schema mismatch"):
        client.search(query_vector=[0.1])


def test_first_success_no_retry(qdrant_with_mock):
    client, mock = qdrant_with_mock
    result = client.search(query_vector=[0.1])
    assert result == []
    assert mock.search.call_count == 1


def test_max_retries_exhausted_reraises(qdrant_with_mock):
    client, mock = qdrant_with_mock
    mock.search.side_effect = ConnectionError("permanent")
    with pytest.raises(ConnectionError):
        client.search(query_vector=[0.1])
    # 1 initial + 3 retries = 4 attempts
    assert mock.search.call_count == 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
