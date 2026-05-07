# ADR-028: CSV-to-DB ingest write-surface contract

## Status

Proposed — 2026-05-07. This ADR scopes the future implementation
contract only; no write surface is implemented by this ADR.

## Context

`mcp/server_documents.py` deliberately exposes read-only document tools:
CSV parsing, PDF text extraction, DOCX text extraction, and read-only
database SELECT. The server and its drill both state the same boundary:
write tools do not belong in the documents server.

The next requested surface is different: CSV-to-DB ingest with an
approval workflow. That is a write path. It can create or update rows,
bind a CSV schema to a table contract, and produce operator-visible
side effects. If added to the documents server, the read-only
`documents:read` trust boundary would be blurred and agents could
confuse "parse this CSV" with "load this CSV into Postgres."

Per §47, MCP servers are split by domain and risk boundary. Documents
MCP owns extraction. CSV-to-DB ingest must be a separate write-capable
server with its own port, scopes, approval state, idempotency keys, and
audit rows.

## Decision

CSV-to-DB ingest will be implemented as a **separate MCP server**, not
as another tool on `mcp/server_documents.py`.

The proposed server contract is:

- Server: `mcp/server_csv_ingest.py`
- Launcher: `scripts/start_mcp_csv_ingest.sh`
- Default port: `8095`
- Inference env hook: `DOCUMIND_MCP_CSV_INGEST_URL`
- Namespace: `csv_ingest.*`
- Scopes: `csv_ingest:read`, `csv_ingest:write`, `csv_ingest:approve`
- Side effects: proposal and validation tools are read/idempotent;
  apply tools are write and always approval-gated

The initial tool set should be:

- `csv_ingest.propose_load`: accept a CSV path, target table contract,
  tenant id, column mapping, dedupe key, and idempotency key; return a
  draft ingest plan with row counts, inferred types, rejected rows, and
  SQL preview metadata. It must not mutate the database.
- `csv_ingest.validate_load`: re-run schema, type, row-count,
  duplicate, tenant-isolation, and policy checks for a draft. It must
  not mutate the database.
- `csv_ingest.submit_for_approval`: persist an approval request using
  the existing approval/action-draft pattern. It must record actor,
  tenant, CSV digest, target table, row count, mapping digest, and
  requested side effects.
- `csv_ingest.apply_approved_load`: apply only an approved draft whose
  CSV digest, mapping digest, target table, actor, tenant, and
  idempotency key still match the approved request.
- `csv_ingest.load_status`: read status and audit metadata for a draft
  or completed load.

The server must reject:

- raw SQL from agents
- DDL (`CREATE`, `ALTER`, `DROP`, `TRUNCATE`)
- cross-tenant target tables or rows
- apply calls without a matching approval
- apply calls when the CSV content or mapping changed after approval
- paths outside the existing file allowlist pattern
- files over the configured size limit

Approval is not a UI-only convention. Approval state is part of the
tool contract. The apply tool must fail closed if approval storage,
audit storage, idempotency storage, or policy evaluation is unavailable.

## Consequences

### Positive

- The existing documents MCP server remains genuinely read-only.
- Write permissions are isolated behind a new namespace and scopes.
- Operators can grant `documents:read` without implicitly granting
  CSV-to-DB writes.
- The approval workflow becomes testable at the MCP boundary instead of
  living only in frontend copy or runbook prose.
- Idempotency and audit requirements are explicit before implementation.

### Negative

- A second server, launcher, env var, and drill set must be maintained.
- The first implementation has to integrate with existing approval and
  audit surfaces before any useful database write can land.
- Operators must start another local service to exercise the full
  CSV-to-DB path.

## Implementation guardrails

The future implementation needs drills for:

1. documents server still has zero write tools
2. CSV-ingest server advertises write side effects only on apply
3. apply without approval returns a denial
4. approval digest mismatch blocks apply
5. duplicate idempotency key returns the original result
6. raw SQL and DDL are rejected before database access
7. tenant mismatch is rejected before database access
8. launcher honors `MCP_CSV_INGEST_PORT` and uses no sudo
9. inference-svc only connects when `DOCUMIND_MCP_CSV_INGEST_URL` is set

## Alternatives considered

### A1. Add `documents.csv_to_db_ingest` to the documents MCP server

Rejected. It violates the read-only contract and forces a single server
to carry both extraction and mutation risk.

### A2. Reuse ingestion-svc HTTP upload directly from agents

Rejected for the agent-facing contract. `ingestion-svc` remains the
system-of-record pipeline, but agents still need an MCP approval wrapper
that presents proposal, validation, approval, apply, and status as one
auditable tool sequence.

### A3. Allow agents to generate SQL inserts after CSV parsing

Rejected. Raw SQL generation at the agent boundary is the wrong
primitive for governed ingest. The server must own mappings, policy,
tenant checks, idempotency, and audit.

## References

- Documents MCP server shipped in `e707ee7`
- Documents MCP launcher + inference-svc env wiring shipped in `cf4db6a`
- `mcp/server_documents.py`
- `mcp/tests/drill_mcp_server_documents.py`
- `mcp/tests/drill_documents_mcp_wiring.py`
- ADR-011 drill pattern, ADR-014 advisory contract, ADR-018 work
  allocation, ADR-025 feature-flag-gated dual-write
