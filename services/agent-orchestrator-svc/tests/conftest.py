"""pytest config for agent-orchestrator-svc tests."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Disable Prometheus HTTP server during tests — otherwise creating the
# app twice in a single test session collides on port 9464.
os.environ.setdefault("DOCUMIND_PROMETHEUS_PORT", "0")

# Disable Pydantic plugins during tests. The installed logfire 4.32.1
# auto-registers via entry-point group `pydantic` and transitively
# imports `opentelemetry.sdk._logs.ReadableLogRecord` — added in OTel
# ≥1.36 but the venv has OTel 1.34.1. Plugin discovery is triggered
# on every pydantic import, blocking pytest at collection time. The
# env var is the documented escape hatch and must be set BEFORE the
# first `import pydantic`.
os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "*")

import pytest  # noqa: E402 — imported after env-var setup above

SVC = Path(__file__).resolve().parents[1]
if str(SVC) not in sys.path:
    sys.path.insert(0, str(SVC))


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords:
            continue
        if hasattr(item, "function") and asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
