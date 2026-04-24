# Audit Verifier CLI — `scripts/audit_verify.py`

**Status:** 🟢 Green. 7-step drill catches both row-level tampering (BROKEN_HASH) and chain-level tampering (BROKEN_CHAIN).
**Date:** 2026-04-24

Closes the "audit verifier CLI" follow-up from DEMO-AUDIT. The
`AuditWriter` in `documind_core.audit` writes a hash-chained row on
every `mcp_draft.*` transition; this CLI is the reader side — runnable
from ops, CI, or cron.

---

## What shipped

```
scripts/audit_verify.py            — CLI walks governance.audit_log per tenant
mcp/tests/drill_audit_verifier.py  — 7-step drill
docs/DEMO-AUDIT-VERIFIER.md        — this file
```

## CLI surface

```bash
# verify every tenant
scripts/audit_verify.py

# one tenant
scripts/audit_verify.py --tenant 137e2ae5-09bc-44b3-b77f-cecb3ac3fe1a

# machine-readable
scripts/audit_verify.py --json

# include OK rows in --json output (default: issues only)
scripts/audit_verify.py --json --verbose

# only verify recent activity — trust the stored previous_hash on
# the first row at/after the cutoff as an anchor
scripts/audit_verify.py --since 2026-04-24
```

Exit code:
- **0** — every tenant's chain is intact
- **1** — one or more tenants had a `BROKEN_HASH`, `BROKEN_CHAIN`,
  or `MISSING_HASH` row

### Three failure modes it distinguishes

| Status | What it means |
| --- | --- |
| `BROKEN_HASH` | The row's `entry_hash` doesn't match a SHA-256 recompute from its own body + stored `previous_hash`. Someone edited the row. |
| `BROKEN_CHAIN` | The row's `previous_hash` doesn't match the prior row's `entry_hash`. A row was inserted or deleted mid-chain. |
| `MISSING_HASH` | `entry_hash` is NULL or empty. Typically a writer that didn't go through `AuditWriter`. |

`BROKEN_HASH` is *in-place* tampering; `BROKEN_CHAIN` is *structural*
tampering. Both are 1-exit signals; ops decides which is scarier.

## Connection model

Connects as `documind_ops` (BYPASSRLS) so a single run can see every
tenant's chain. This is appropriate for a governance tool — the
whole point is to surface cross-tenant integrity without an
application-layer scope — but the DSN is still env-driven, not
baked in:

```
DOCUMIND_PG_HOST      (default: localhost)
DOCUMIND_PG_PORT      (default: 55432)
DOCUMIND_PG_DB        (default: documind)
DOCUMIND_PG_OPS_USER      (default: documind_ops)
DOCUMIND_PG_OPS_PASSWORD  (default: documind_ops)
```

A production operator would bind these to a secret manager; the
verifier itself stays dumb about storage.

## The 7-step drill

```
── 1. baseline — verifier clean (exit 0, all OK) ──
  ✓ baseline 12 rows, all OK

── 2. tamper — flip `action` of one row in place ──
  ✓ tampered row id=281376b4 action='mcp_draft.created' → 'mcp_draft.injected'

── 3. verifier detects BROKEN_HASH on the tampered row ──
  ✓ BROKEN_HASH caught id=281376b4 action='mcp_draft.injected'
    detail=entry_hash 163f4545a1a0... != recomputed 342094ce8908...
  ✓ exit code=1 (tampering detected)

── 4. restore row; verifier clean again ──
  ✓ all 12 rows OK again

── 5. insert row with bad previous_hash — chain break ──
  ✓ synthetic row injected with bogus previous_hash

── 6. verifier reports BROKEN_CHAIN on the injected row ──
  ✓ BROKEN_CHAIN caught action=drill.injected
    detail=previous_hash deadbeefdead != expected 4007644370ca

── 7. delete synthetic row + draft; verifier clean ──
  ✓ cleanup OK, exit=0

════════════════════════════════════════
  ALL 7 AUDIT-VERIFIER STEPS PASSED
════════════════════════════════════════
```

Run it:

```bash
PYTHONPATH=/mnt/deepa/rag python mcp/tests/drill_audit_verifier.py
```

## Cron recipe

```cron
# Every hour at :07 — verify last 24h, alert on any exit-1.
7 * * * * /opt/documind/scripts/audit_verify.py \
    --since "$(date -u -d '24 hours ago' -Iseconds)" \
    --json > /var/log/documind/audit-$(date -u +%Y-%m-%dT%H).json
```

A follow-up can pipe the JSON into a webhook that alerts governance
when `summary.*.BROKEN_HASH > 0` or `BROKEN_CHAIN > 0`. Today the
exit code alone is enough for a simple `|| mail -s "audit tampering"
ops@...` wrapper.

## Subtlety — cascade depth of a BROKEN_HASH

When row N is tampered in place, the verifier reports BROKEN_HASH on
row N only. Subsequent rows (N+1, N+2, ...) still pass because they
chain on the **stored** `entry_hash` of row N, not the recomputed
one. In other words: the verifier faithfully reports what the DB
currently holds — a single in-place edit shows as exactly one row's
hash problem, not an avalanche of chain problems.

If an attacker wanted to tamper without being caught, they'd need to
recompute `entry_hash` for row N *and* every subsequent row — which
means they need the `AuditWriter` logic and write access to every
row in the chain. The hash chain's property is not "makes tampering
impossible" but "makes partial tampering detectable and full
tampering expensive."

## Remaining follow-ups

- `audit_verify.py --fix` — offer to write a sealed "tampering
  detected here" record into a sibling `audit_log_breaks` table when
  the chain is broken. Today the verifier is read-only.
- Alert webhook wrapper that posts to Slack / PagerDuty on exit-1.
- Per-tenant sealed-archive export: dump all rows + a signed
  `chain_seal` row for offline long-term storage.
