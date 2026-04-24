"""pytest config — enables async test functions."""
import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords:
            continue
        # auto-mark coroutine tests
        if hasattr(item, "function") and asyncio_is_coroutine(item.function):
            item.add_marker(pytest.mark.asyncio)


def asyncio_is_coroutine(fn) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(fn)
