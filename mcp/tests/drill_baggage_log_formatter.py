#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: _inject_baggage processor pulls W3C baggage into every JSON log
record.

Composes with:
- drill_baggage_propagation.py (helper API contract)
- drill_baggage_middleware.py (real middleware stack producer)

This one closes the loop on the consumer side: once baggage exists in
the OTel context, every structlog event auto-includes those fields so
logs become tenant-filterable across services without callers needing
explicit kwargs.

Four exercised steps in this local drill shape:

 1. _inject_baggage exists in documind_core.logging_config and is
    wired into the processor chain in setup_logging.
 2. Log emitted INSIDE a baggage scope carries the baggage fields
    in the JSON output.
 3. NEGATIVE: log emitted OUTSIDE any baggage scope MUST NOT carry
    those fields. No leak from the parent scope.
 4. NEGATIVE: explicit log kwargs win over baggage. If caller passes
    `tenant_id="explicit"`, baggage's value MUST NOT overwrite it.
 5. _inject_baggage composes with _inject_context — when both
    contextvar and baggage have the same key, contextvar wins (it
    runs FIRST in the processor chain). This documents the
    collision-resolution policy.
 6. NEGATIVE: the processor short-circuits gracefully without
    OTel SDK installed (ImportError handled).

Run:
    PYTHONPATH=/tmp/baggage_test_stubs:/mnt/deepa/rag \\
        .venv-tts/bin/python3 mcp/tests/drill_baggage_log_formatter.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path


def green(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def red(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}")


def yellow(msg: str) -> None:
    print(f"\033[33m⚠\033[0m {msg}")


def main() -> int:
    failed = 0
    total = 6
    repo = Path("/mnt/deepa/rag")

    # ── Step 1 ───────────────────────────────────────────────────
    print("\n[1/6] _inject_baggage exists + wired into processor chain")
    try:
        src = (repo / "libs/py/documind_core/logging_config.py").read_text()
        assert "def _inject_baggage" in src, (
            "_inject_baggage processor missing from logging_config"
        )
        # Verify it's wired into the shared processor list — must appear
        # in the shared = [...] block, not just defined.
        # Look for the line in the processor chain that references it.
        in_chain = False
        for line in src.split("\n"):
            stripped = line.strip()
            if stripped == "_inject_baggage,":
                in_chain = True
                break
        assert in_chain, (
            "_inject_baggage defined but NOT wired into setup_logging's "
            "shared processor list"
        )
        # Verify ImportError fallback present
        assert "except ImportError" in src, (
            "_inject_baggage missing OTel-optional fallback"
        )
        green("_inject_baggage defined + wired into processor chain + "
              "OTel-optional fallback present")
    except Exception as exc:  # noqa: BLE001
        red(f"step 1 failed: {exc}")
        failed += 1

    # ── OTel availability gate ───────────────────────────────────
    try:
        from opentelemetry import baggage as _bag  # noqa: F401
        otel_present = True
    except ImportError:
        otel_present = False

    if not otel_present:
        yellow("opentelemetry SDK not installed locally; remaining steps "
               "require it. CI containers run the full drill.")
        return 0 if failed == 0 else 1

    try:
        import structlog  # noqa: F401
    except ImportError:
        yellow("structlog not available locally; steps 2-6 require it.")
        return 0 if failed == 0 else 1

    sys.path.insert(0, str(repo / "libs/py"))

    # Helper: capture JSON log output to an in-memory stream and parse.
    def capture_logs(action) -> list[dict]:
        """Run `action`, return list of parsed JSON log records emitted."""
        import logging

        from documind_core.logging_config import (
            get_logger,
            setup_logging,
        )

        # Redirect stdout to a buffer so we can read JSON output.
        buf = io.StringIO()
        # Temporarily replace the stdlib root handler to write to buf.
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            setup_logging(service_name="drill", level="INFO", json_format=True)
            # The handler in setup_logging wrote to sys.stdout AT CALL TIME.
            # That captured the buf via the redirect ABOVE. So calls now
            # write to buf.
            logger = get_logger("drill")
            action(logger)
            # Flush stdlib root handlers
            logging.getLogger().handlers[0].flush()
        finally:
            sys.stdout = old_stdout

        # Parse each line as JSON
        records = []
        for line in buf.getvalue().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # skip non-JSON lines (e.g. test framework output)
        return records

    # ── Step 2 ───────────────────────────────────────────────────
    print("\n[2/6] Log inside baggage scope carries baggage fields in JSON")
    try:
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        def emit(logger):
            ctx = _ot_baggage.set_baggage("tenant_id", "acme-prod")
            ctx = _ot_baggage.set_baggage("user_id", "u-42", context=ctx)
            ctx = _ot_baggage.set_baggage("request_id", "req-xyz", context=ctx)
            token = _ot_context.attach(ctx)
            try:
                logger.info("inside_baggage_scope", action="probe")
            finally:
                _ot_context.detach(token)

        records = capture_logs(emit)
        assert records, "no JSON log records emitted"
        rec = next(
            (r for r in records if r.get("message") == "inside_baggage_scope"),
            None,
        )
        assert rec is not None, (
            f"expected event with message='inside_baggage_scope', "
            f"got records: {records}"
        )
        assert rec.get("tenant_id") == "acme-prod", (
            f"tenant_id missing from log record: {rec}"
        )
        assert rec.get("user_id") == "u-42", (
            f"user_id missing from log record: {rec}"
        )
        assert rec.get("request_id") == "req-xyz", (
            f"request_id missing from log record: {rec}"
        )
        green(f"baggage fields landed in JSON log: tenant_id={rec.get('tenant_id')} "
              f"user_id={rec.get('user_id')} request_id={rec.get('request_id')}")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 2 failed: {exc!r}")
        failed += 1

    # ── Step 3: NEGATIVE — outside scope, no baggage in log ──────
    print("\n[3/6] NEGATIVE: log outside baggage scope has NO baggage fields")
    try:
        # No set_baggage; no attach. Fresh context.
        def emit_outside(logger):
            logger.info("outside_baggage_scope", note="no_baggage_set_here")

        records = capture_logs(emit_outside)
        rec = next(
            (r for r in records if r.get("message") == "outside_baggage_scope"),
            None,
        )
        assert rec is not None, f"expected message='outside_baggage_scope', got {records}"
        for forbidden in ("tenant_id", "user_id", "request_id"):
            # Some of these may be set by _inject_context contextvars
            # (which start at default=""); _inject_context only adds if
            # the value is truthy, so empty contextvar = no field.
            # Same for baggage: if not set, no baggage entry.
            value = rec.get(forbidden)
            assert value in (None, "", []), (
                f"NEGATIVE FAILED: {forbidden}={value!r} leaked into log "
                f"record outside any baggage/contextvar scope. Full record: {rec}"
            )
        green("log outside baggage scope has no spurious tenant/user/request_id "
              "fields — W3C contract holds")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 3 failed: {exc!r}")
        failed += 1

    # ── Step 4: NEGATIVE — explicit log kwargs win over baggage ──
    print("\n[4/6] NEGATIVE: explicit log kwargs win over baggage values")
    try:
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        def emit_override(logger):
            ctx = _ot_baggage.set_baggage("tenant_id", "from-baggage")
            token = _ot_context.attach(ctx)
            try:
                # Explicit kwarg should NOT be overwritten by baggage value
                logger.info("override_test", tenant_id="explicit-override")
            finally:
                _ot_context.detach(token)

        records = capture_logs(emit_override)
        rec = next(
            (r for r in records if r.get("message") == "override_test"),
            None,
        )
        assert rec is not None, f"expected message='override_test', got {records}"
        assert rec.get("tenant_id") == "explicit-override", (
            f"NEGATIVE FAILED: explicit kwarg tenant_id='explicit-override' "
            f"got overwritten by baggage. Got tenant_id={rec.get('tenant_id')!r}. "
            f"Processor must NOT clobber existing fields."
        )
        green(f"explicit kwarg won: tenant_id={rec.get('tenant_id')!r} "
              f"(baggage tried 'from-baggage', was correctly ignored)")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 4 failed: {exc!r}")
        failed += 1

    # ── Step 5: contextvar wins over baggage on collision ────────
    print("\n[5/6] On collision, contextvar (_inject_context) wins over baggage "
          "(_inject_baggage runs after)")
    try:
        from documind_core.logging_config import (
            bind_request_context,
            clear_request_context,
        )
        from opentelemetry import baggage as _ot_baggage
        from opentelemetry import context as _ot_context

        def emit_collision(logger):
            # Set DIFFERENT values in contextvar vs baggage for the same key.
            bind_request_context(
                correlation_id="cid-from-contextvar",
                tenant_id="tenant-from-contextvar",
            )
            ctx = _ot_baggage.set_baggage("tenant_id", "tenant-from-baggage")
            token = _ot_context.attach(ctx)
            try:
                logger.info("collision_test")
            finally:
                _ot_context.detach(token)
                clear_request_context()

        records = capture_logs(emit_collision)
        rec = next(
            (r for r in records if r.get("message") == "collision_test"),
            None,
        )
        assert rec is not None, f"expected collision_test, got {records}"
        # _inject_context runs BEFORE _inject_baggage, so contextvar value
        # is set first and _inject_baggage skips (key already in dict).
        assert rec.get("tenant_id") == "tenant-from-contextvar", (
            f"collision policy violated: expected contextvar to win, "
            f"got tenant_id={rec.get('tenant_id')!r}"
        )
        green("contextvar wins over baggage on collision — order in the "
              "processor chain documented + locked: explicit > contextvar > baggage")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 5 failed: {exc!r}")
        failed += 1

    # ── Step 6: ImportError fallback for OTel-missing path ───────
    print("\n[6/6] _inject_baggage degrades gracefully if OTel removed at "
          "import time (source scan)")
    try:
        src = (repo / "libs/py/documind_core/logging_config.py").read_text()
        # Find the _inject_baggage function body
        import re
        m = re.search(
            r"def _inject_baggage\([^)]*\)[^:]*:(.*?)(?=\ndef |\Z)",
            src, re.DOTALL,
        )
        assert m, "could not isolate _inject_baggage function body for inspection"
        body = m.group(1)
        # The body must have try/except ImportError that returns event_dict
        # short-circuit BEFORE attempting baggage.get_all().
        assert "except ImportError" in body, (
            "ImportError handler missing — function will crash on services "
            "without OTel SDK"
        )
        assert "return event_dict" in body, (
            "fallback path does not return event_dict, will break the "
            "processor chain"
        )
        # The order matters: ImportError fallback BEFORE the baggage call
        import_idx = body.index("except ImportError")
        get_all_idx = body.index("get_all()")
        assert import_idx < get_all_idx, (
            "OTel ImportError check happens AFTER baggage.get_all() call — "
            "the call would fail before the handler engages. Reorder."
        )
        green("OTel-missing fallback engages BEFORE baggage call — "
              "services without tracing keep producing logs")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 6 failed: {exc!r}")
        failed += 1

    print()
    if failed == 0:
        green(f"ALL {total} STEPS PASSED")
        return 0
    red(f"{failed}/{total} STEPS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
