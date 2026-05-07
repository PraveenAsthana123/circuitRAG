"""
Error-tracking integration — Sentry wrapper.

Why a wrapper rather than direct sentry_sdk calls everywhere:
- Sentry init must run ONCE at service startup (calling sentry_sdk
  multiple times produces silent multi-init bugs).
- The DSN is per-environment env var; this module reads it once
  and silently no-ops when unset (so dev/test runs don't need
  Sentry config).
- Per-tenant tagging is the load-bearing add-on — every error
  report MUST carry tenant_id so operators can filter incidents
  by customer. Doing this at the wrapper enforces it.

Usage::

    from documind_core.error_tracking import init_sentry, set_tenant_context

    # At service startup:
    init_sentry(service_name="retrieval-svc")

    # On every request (in middleware):
    set_tenant_context(tenant_id="acme")

    # On error: caller doesn't import sentry_sdk directly — wrapper
    # owns the dependency.
"""

from __future__ import annotations

import logging
import os
from typing import Any

__all__ = ["init_sentry", "set_tenant_context", "is_initialized", "capture_exception"]


log = logging.getLogger(__name__)

_initialized = False


def init_sentry(
    *,
    service_name: str,
    environment: str | None = None,
    dsn: str | None = None,
    sample_rate: float = 1.0,
    traces_sample_rate: float = 0.1,
) -> bool:
    """Initialize Sentry SDK if a DSN is available.

    Returns True if Sentry is now initialized; False if no-op (no
    DSN, lib not installed, or already initialized).

    DSN priority:
        1. explicit `dsn=` argument (test-only)
        2. `SENTRY_DSN` env var
        3. None → silent no-op (dev/test)
    """
    global _initialized

    if _initialized:
        return False

    effective_dsn = dsn or os.environ.get("SENTRY_DSN", "").strip()
    if not effective_dsn:
        log.info("sentry_skipped reason=no_dsn service=%s", service_name)
        return False

    try:
        import sentry_sdk
    except ImportError:
        log.warning("sentry_skipped reason=lib_missing service=%s", service_name)
        return False

    effective_env = environment or os.environ.get("DOCUMIND_ENV", "development")

    sentry_sdk.init(
        dsn=effective_dsn,
        environment=effective_env,
        # Sample rate gates expensive context capture; defaults are
        # conservative — operators bump in prod via env.
        sample_rate=sample_rate,
        traces_sample_rate=traces_sample_rate,
        # Stamp every event with the service so multi-service Sentry
        # projects can filter without operator-side rule writing.
        release=os.environ.get("DOCUMIND_RELEASE", "dev"),
    )
    sentry_sdk.set_tag("service", service_name)
    _initialized = True
    log.info("sentry_initialized service=%s env=%s", service_name, effective_env)
    return True


def set_tenant_context(*, tenant_id: str | None, user_id: str | None = None) -> None:
    """Attach tenant + user to the current Sentry scope.

    Call from request middleware on every request so error events
    carry the tenant tag. No-op if Sentry isn't initialized — keeps
    test/dev paths free of Sentry concerns.
    """
    if not _initialized:
        return

    try:
        import sentry_sdk
    except ImportError:
        return

    scope = sentry_sdk.get_isolation_scope()
    if tenant_id:
        scope.set_tag("tenant_id", tenant_id)
    if user_id:
        scope.set_user({"id": user_id})


def is_initialized() -> bool:
    """Whether init_sentry succeeded. Useful for /health/details."""
    return _initialized


def capture_exception(exc: BaseException, **extra: Any) -> str | None:
    """Capture an exception with optional structured `extra` context.

    Returns the Sentry event ID (for log correlation) or None when
    Sentry is not initialized. NEVER re-raises — capturing an
    exception cannot itself become a new exception.
    """
    if not _initialized:
        return None

    try:
        import sentry_sdk
    except ImportError:
        return None

    if extra:
        scope = sentry_sdk.get_isolation_scope()
        for k, v in extra.items():
            scope.set_extra(k, v)
    result = sentry_sdk.capture_exception(exc)
    return str(result) if result is not None else None


def _reset_for_tests() -> None:
    """Reset the module-level state so tests can re-init.

    The double-underscore prefix would be too aggressive — callers
    in real code shouldn't reach for this. Tests do.
    """
    global _initialized
    _initialized = False
