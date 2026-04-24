"""pytest config — enables async test functions and wires service paths."""
from __future__ import annotations

import sys
from pathlib import Path

# Make every service's `app` package importable without an install step.
# Tests can then `from app.services.X import Y` for the service they target.
REPO = Path(__file__).resolve().parents[3]
for svc in ("ingestion-svc", "retrieval-svc", "inference-svc", "evaluation-svc"):
    path = REPO / "services" / svc
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

import pytest  # noqa: E402


def pytest_collection_modifyitems(config, items):
    import asyncio
    for item in items:
        if "asyncio" in item.keywords:
            continue
        if hasattr(item, "function") and asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
