# ADR-006: JWT verifier rejects malformed-but-decodable tokens

## Status

Accepted — implemented in commit `4b11cf8`.

## Context

A token signed with the right key but carrying malformed claims
(`sub=42`, `roles="hr:write"` instead of `["hr:write"]`,
`tenant_id="alice"`) used to slip past `pyjwt.decode` and propagate
into `request.state`. Downstream code then exploded in ways the
operator could not reconstruct from a 500: an RLS `::uuid` cast in
audit_log, a `.split(':')` in scope check, a rate limiter keyed
by tenant_id.

## Decision

Layer a strict-shape validator AFTER `pyjwt.decode` (signature,
issuer, audience, expiry stay intact) and BEFORE the claims
propagate. The contract:

* `sub` — non-empty string, ≤256 chars. Accepts UUID, email,
  federated subject (`okta:abc`), service-account name. Pairs with
  ADR-001's TEXT actor_id.
* `tenant_id` — STRICT UUID format if present, OR empty/missing.
  Rejecting `"alice"` early beats failing the `::uuid` cast at
  audit-write time and dropping the row.
* `roles` — list of strings, each
  `[a-z][a-z0-9_-]*:[a-z][a-z0-9_-]*` shape. Hard cap of 32
  entries, 64 chars each. Catches the common bug "issuer emitted
  the role as a string instead of a list."
* `kind` — explicit `"access"` or `"refresh"` string; hard-fail on
  missing or wrong-type.

All failures raise `pyjwt.InvalidTokenError` so the existing
`JWTAuthMiddleware` translates to 401 with a structured
`INVALID_TOKEN` envelope — no new error path to wire.

## Consequences

* The downstream code can rely on shape — `request.state.sub`
  is always a string ≤256, `tenant_id` is always UUID-format or
  absent, `roles` is always a list of well-formed strings.
* A forged-signature token still 401s — the validator runs AFTER
  `pyjwt.decode`, so signature checks are unaffected (verified by
  drill step 6).
* Hard-fail on wrong kind means a refresh token can never be used
  on an access endpoint (defence in depth on top of `expected_kind`).
* The 32-role cap + 64-char-per-role cap bound metric label
  cardinality if any future code uses roles in labels (ADR-010
  forbids this anyway).
