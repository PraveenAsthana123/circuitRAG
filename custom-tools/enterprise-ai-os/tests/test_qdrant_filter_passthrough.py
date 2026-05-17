# Negative drill for the P0 Qdrant filter-passthrough fix in
# integrations/qdrant_client.py (2026-05-17).
#
# Pre-fix bug: `filters` argument was accepted but never passed to
# the underlying `self.client.search()`. Multi-tenant deployments
# that relied on filtering by tenant_id received cross-tenant
# results silently.
#
# These tests use a mock Qdrant client to verify the `query_filter`
# argument is correctly assembled and passed through.

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def qdrant_client_with_mock(monkeypatch):
    # Inject env so QdrantClient constructor doesn't try real network
    monkeypatch.setenv("QDRANT_URL", "http://test:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "test_collection")

    # Patch the constructor BEFORE importing the module under test
    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = []

    import integrations.qdrant_client as mod
    monkeypatch.setattr(mod, "QdrantClient", lambda **kwargs: mock_qdrant)

    client = mod.QdrantVectorClient()
    return client, mock_qdrant


def test_no_filter_passes_query_filter_as_none(qdrant_client_with_mock):
    client, mock = qdrant_client_with_mock
    client.search(query_vector=[0.1, 0.2], top_k=3)
    kwargs = mock.search.call_args.kwargs
    assert kwargs["query_filter"] is None
    assert kwargs["limit"] == 3


def test_dict_filters_become_qdrant_filter(qdrant_client_with_mock):
    """BACKDOOR CHECK: pre-fix version silently dropped this dict."""
    client, mock = qdrant_client_with_mock
    client.search(
        query_vector=[0.1, 0.2],
        top_k=3,
        filters={"tenant_id": "tenant-a"},
    )
    kwargs = mock.search.call_args.kwargs
    qfilter = kwargs["query_filter"]
    assert qfilter is not None, (
        "REGRESSION: filters dict was silently dropped (pre-fix bug)"
    )
    # Verify the Filter contains a `must` clause with the tenant_id
    assert len(qfilter.must) == 1
    assert qfilter.must[0].key == "tenant_id"
    assert qfilter.must[0].match.value == "tenant-a"


def test_multi_key_dict_becomes_and_filter(qdrant_client_with_mock):
    client, mock = qdrant_client_with_mock
    client.search(
        query_vector=[0.1],
        filters={"tenant_id": "tenant-a", "doc_type": "policy"},
    )
    qfilter = mock.search.call_args.kwargs["query_filter"]
    assert len(qfilter.must) == 2
    keys = {c.key for c in qfilter.must}
    assert keys == {"tenant_id", "doc_type"}


def test_prebuilt_query_filter_takes_precedence(qdrant_client_with_mock):
    """If caller passes a real Filter, it's used as-is (not regenerated)."""
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
    client, mock = qdrant_client_with_mock
    pre_built = Filter(
        must=[FieldCondition(key="custom", match=MatchValue(value=42))]
    )
    client.search(
        query_vector=[0.1],
        query_filter=pre_built,
        # filters dict is provided too; should be IGNORED because
        # query_filter wins.
        filters={"ignored": "ignored"},
    )
    actual = mock.search.call_args.kwargs["query_filter"]
    assert actual is pre_built  # same object, not a translation


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
