# ADR-013: Audit-redaction policy — when to redact `details` JSONB

## Status

Proposed — recorded but not yet implementing. Promotes to Accepted
when the criteria below are met.

## Context

Commit `09458ef` shipped `PIIScanner.redact_value()` (recursive PII
redaction over JSON-shaped values) and `documind_pii_redactions_total
{kind}` (Prometheus counter). The "Out of scope" section of that
commit explicitly deferred wiring it into `AuditWriter.write` before
persisting `details`:

> Wiring redact_value into AuditWriter.write before persisting
> ``details``. The hash chain covers details, so redaction
> changes the hash — fine going forward, but reviewers may want
> raw values for forensics. Policy decision needs the ADR.

This ADR captures that decision-shape so a future implementer can
land the wire-up without re-litigating the trade-offs.

## The trade-off

Two values pull in opposite directions:

**Privacy**: `details` JSONB carries arbitrary caller-supplied
context — query strings, error messages, tool arguments, request
payloads. Any of these can leak PII (email in a query, SSN in a
form field) into governance.audit_log. Auditors with read access
to the audit log become accidental PII custodians.

**Forensic recoverability**: an audit log exists *because* the
original values matter at review time. "alice@example.com tried to
modify record 42" is more useful than "[REDACTED:email] tried to
modify [REDACTED:ssn]." Redacting at write-time loses information
the reviewer needs.

The hash-chain dimension matters but is solvable: redaction changes
the hash, but the chain continues from the new hash forward. Old
rows hash with raw values, new rows hash with redacted values, and
`audit_verify.py` keeps working. Verified mentally; would need a
drill if implementing.

## Decision

Audit details redaction is **opt-in per call**, mirroring ADR-004's
`fail_closed` shape. Default is **no redaction** (preserve forensic
value). Callers that know their `details` carry user-supplied PII
opt in:

```python
await audit.write(
    ...,
    details=user_supplied_payload,
    redact_pii=True,    # NEW — defaults to False
)
```

When `redact_pii=True`, the writer calls `PIIScanner().redact_value()`
on `details` before computing the hash and inserting. The
Prometheus counter `documind_pii_redactions_total{kind}` already
tracks the redactions; no new metric needed.

The default stays False because:

1. **Most audit writes are server-controlled `details`** —
   `mcp_draft.created` records `{draft_id, tool, reason,
   correlation_id}`; none of those carry PII unless the caller
   explicitly puts it there.
2. **The opt-in shape mirrors `fail_closed`** — both are
   per-call governance posture decisions made at the callsite,
   where the context is. Same rule of three: if a third
   audit-policy parameter shows up, lift to a helper.
3. **A blanket "always redact" default would silently lose
   forensic value** for the 90% of writes that don't carry PII,
   to defend against the 10% that do. Opt-in inverts that
   correctly.

### Promotion to Accepted

This ADR moves to Accepted when ALL of these are true:

- A real call site needs `redact_pii=True` (not hypothetical —
  identified by code review or incident).
- The implementing commit ships with a drill that asserts:
  - default behavior unchanged (no redaction)
  - `redact_pii=True` redacts the persisted JSONB
  - `documind_pii_redactions_total` increments per kind detected
  - hash chain still verifies after the redacted row lands
- The drill includes a forensic-recoverability negative assertion:
  a row with `redact_pii=False` MUST persist raw values (proves
  the default behavior is preserved).

Until then, the parameter is not added — adding it speculatively
would create an inconsistent surface (one place opts in, others
don't think to) without solving any real problem.

### When this ADR will be wrong

If a regulatory requirement (GDPR retention, HIPAA logs) lands
that mandates audit-side redaction at write-time, this ADR's
"opt-in default" is wrong and a successor ADR should flip the
default to True with `redact_pii=False` as the explicit forensic-
override. The trigger is *external policy*, not engineering
preference.

## Consequences

* No code change today. The TODO from `09458ef` is now structured
  as a decision-with-criteria rather than a free-floating "we
  should think about this."
* When the implementing commit lands, the parameter shape is fixed
  by this ADR — no new design pass needed at implementation time.
* The Prometheus counter (`documind_pii_redactions_total`) is the
  observability surface for both opt-in audit redaction AND any
  other call site that uses `redact_value()` (e.g., a future
  log-filter middleware). Single metric, multiple consumers.
* `audit_verify.py` continues to work without changes — it walks
  the chain through the stored hash regardless of whether the
  body was redacted before hashing.
