"""pytest config for documind_core unit tests.

These tests exercise ONLY the shared library — no service code. Service-
specific tests live under ``services/<svc>/tests/`` with their own
conftest that sets up that service's path.
"""
from __future__ import annotations

import asyncio

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords:
            continue
        if hasattr(item, "function") and asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
