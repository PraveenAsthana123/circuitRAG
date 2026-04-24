"""pytest config for ingestion-svc tests — adds the service's parent dir to path."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SVC = Path(__file__).resolve().parents[1]
if str(SVC) not in sys.path:
    sys.path.insert(0, str(SVC))


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords:
            continue
        if hasattr(item, "function") and asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
