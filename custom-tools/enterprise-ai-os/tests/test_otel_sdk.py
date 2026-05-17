# Negative drills for Iter 43 (2026-05-17): OTel SDK Resource +
# auth header.

import sys
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_parse_headers_empty():
    from integrations.otel_sdk import _parse_headers
    assert _parse_headers(None) == {}
    assert _parse_headers("") == {}


def test_parse_headers_basic():
    from integrations.otel_sdk import _parse_headers
    assert _parse_headers("Authorization=Bearer abc") == {
        "Authorization": "Bearer abc",
    }


def test_parse_headers_multi():
    from integrations.otel_sdk import _parse_headers
    assert _parse_headers("Authorization=Bearer abc, X-Tenant=t1") == {
        "Authorization": "Bearer abc",
        "X-Tenant": "t1",
    }


def test_parse_headers_tolerates_whitespace():
    from integrations.otel_sdk import _parse_headers
    out = _parse_headers("  k1 = v1 ,  k2=v2  ")
    assert out == {"k1": "v1", "k2": "v2"}


def test_parse_headers_skips_malformed_pairs():
    from integrations.otel_sdk import _parse_headers
    out = _parse_headers("good=1, malformed-no-eq, =empty-key")
    assert out["good"] == "1"
    assert "malformed-no-eq" not in out


def test_BACKDOOR_CHECK_resource_attributes_set(monkeypatch):
    """Pre-fix: TracerProvider was constructed with no resource —
    every span looked identical across services / versions / envs."""
    monkeypatch.setenv("SERVICE_VERSION", "1.2.3")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("HOSTNAME", "pod-abc-1")

    import integrations.otel_sdk as mod

    captured = {}
    class FakeProvider:
        def __init__(self, resource=None):
            captured["resource"] = resource
        def add_span_processor(self, _): pass
    monkeypatch.setattr(mod, "TracerProvider", FakeProvider)
    monkeypatch.setattr(mod, "OTLPSpanExporter", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "BatchSpanProcessor", lambda _: MagicMock())
    monkeypatch.setattr(mod.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(mod.trace, "get_tracer", lambda name: MagicMock())

    mod.OpenTelemetrySDK().configure(service_name="svc")

    attrs = captured["resource"].attributes
    assert attrs["service.name"] == "svc"
    assert attrs["service.version"] == "1.2.3"
    assert attrs["deployment.environment"] == "staging"
    assert attrs["service.instance.id"] == "pod-abc-1"


def test_BACKDOOR_CHECK_warns_on_http_without_auth(monkeypatch, capsys):
    """HTTP endpoint + no auth header = trace data leak risk."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.local:4318/v1/traces")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)

    import integrations.otel_sdk as mod
    monkeypatch.setattr(mod, "TracerProvider", lambda **kw: MagicMock(add_span_processor=lambda _: None))
    monkeypatch.setattr(mod, "OTLPSpanExporter", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "BatchSpanProcessor", lambda _: MagicMock())
    monkeypatch.setattr(mod.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(mod.trace, "get_tracer", lambda name: MagicMock())

    mod.OpenTelemetrySDK().configure()
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "unauthenticated" in captured.err


def test_no_warn_when_https_or_auth_provided(monkeypatch, capsys):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://collector.local:4318/v1/traces")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_HEADERS", raising=False)

    import integrations.otel_sdk as mod
    monkeypatch.setattr(mod, "TracerProvider", lambda **kw: MagicMock(add_span_processor=lambda _: None))
    monkeypatch.setattr(mod, "OTLPSpanExporter", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "BatchSpanProcessor", lambda _: MagicMock())
    monkeypatch.setattr(mod.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(mod.trace, "get_tracer", lambda name: MagicMock())

    mod.OpenTelemetrySDK().configure()
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


def test_extra_resource_attrs_merged(monkeypatch):
    import integrations.otel_sdk as mod

    captured = {}
    class FakeProvider:
        def __init__(self, resource=None): captured["resource"] = resource
        def add_span_processor(self, _): pass
    monkeypatch.setattr(mod, "TracerProvider", FakeProvider)
    monkeypatch.setattr(mod, "OTLPSpanExporter", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "BatchSpanProcessor", lambda _: MagicMock())
    monkeypatch.setattr(mod.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(mod.trace, "get_tracer", lambda name: MagicMock())

    mod.OpenTelemetrySDK().configure(
        extra_resource_attrs={"cloud.region": "us-east-1", "team": "platform"},
    )
    attrs = captured["resource"].attributes
    assert attrs["cloud.region"] == "us-east-1"
    assert attrs["team"] == "platform"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
