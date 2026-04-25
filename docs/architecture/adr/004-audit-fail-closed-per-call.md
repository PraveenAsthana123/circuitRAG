# ADR-004: `fail_closed` is per-call, not per-action policy table

## Status

Accepted — implemented in commit `0fad44b`.

## Context

After commit `2b47d4a` made audit fail-open the default + added a
graphable counter for dropped rows, the next question was: which
actions deserve a hard guarantee? An operator clicking "Replay"
on a draft expects a visible 5xx if the audit row would be lost,
not a silent success.

Two designs were considered:

* **Policy table** — `governance.audit_actions` rows mapping each
  action name to fail-open / fail-closed. Read at startup, applied
  inside `AuditWriter.write`.
* **Per-call parameter** — `write(..., fail_closed: bool = False)`.
  Caller decides per call.

## Decision

Per-call parameter, default `False`.

The policy table was rejected because:

* It's design-then-fix — adds a config surface and a fetching code
  path before the first real use case demands it.
* Most callers want fail-open — the default. Forcing every caller to
  consult a table inverts the common case.
* Per-call lets the callsite make the decision in context — the admin
  /resolve route knows it's operator-driven; the worker knows it's
  autonomous. That information is already present at the callsite.

The two callers that opt in today:

* `services/inference-svc/app/routers/__init__.py:resolve_draft` —
  `audit_fail_closed=True` when `actor_type == "operator"`.
* `mcp/client.py:reject_draft` — defaults `audit_fail_closed=True`
  (rejection is governance-terminal).

Both modes increment `documind_audit_write_failures_total
{action,error_type}` so the counter graphs both regardless of
posture. The only difference is whether the exception escapes.

## Consequences

* Existing callers are unaffected — default is still fail-open.
* New governance-critical callers opt in by adding one parameter.
* The decision site is the callsite, where the context is. No
  surprise from a remote policy table.
* If a third opt-in caller lands, lift to a small helper (per the
  rule of three). Two callers with one keyword arg is the right
  scale today.
* `DataError` is the wrapper exception, with `__cause__` preserving
  the original. FastAPI's standard error handler maps `DataError`
  to 5xx with the consistent envelope.
