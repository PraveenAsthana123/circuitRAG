"""§8 smoke tests for agent-orchestrator-svc.

Boots the real FastAPI app via TestClient and asserts /health responds.
This is the structural gate from the 2026-04-30 audit: the service
had a Dockerfile but no tests/ dir.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_live_endpoint_returns_ok():
    """Real app boot — proves create_app() doesn't crash on import +
    the /health/live K8s probe is wired."""
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/health/live")
    assert resp.status_code == 200, f"unexpected status {resp.status_code}: {resp.text[:200]}"


def test_health_ready_endpoint_responds():
    """The /health/ready probe responds (200 when deps up, 503 when
    not). We assert it exists and doesn't 404 — readiness state
    depends on whether DB/MCP clients are reachable."""
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/health/ready")
    # 200 (deps OK) or 503 (deps down) are both valid; 404 is not.
    assert resp.status_code in (200, 503), (
        f"unexpected status {resp.status_code}: {resp.text[:200]}"
    )


def test_phantom_route_returns_404():
    """Negative: a clearly-bogus route must 404 — proves no
    catch-all wildcard is masking real 404s."""
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/v1/__phantom_does_not_exist__/foo")
    assert resp.status_code == 404
