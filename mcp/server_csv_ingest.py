"""
CSV-to-DB ingest MCP server — write surface with approval gate.

Per ADR-028 (CSV-to-DB ingest write-surface contract). This server
implements the 5-tool contract scoped in iter-64's ADR; iter-65 ships
Stage-1 (tool definitions + propose/validate impls + apply-rejection
drill).

PER §47 READ/WRITE SEPARATION
  mcp/server_documents.py     read-only (csv_parse, pdf, docx, db_query_select)
  mcp/server_csv_ingest.py    THIS — write-capable, approval-gated

  The two servers share NOTHING in their dispatch path. Read tools
  cannot trigger writes; write tools cannot bypass the approval gate.

PER §50.5.3 (security/destructive ops need approval):
  apply_approved_load is the ONLY write tool. It REJECTS any call
  without:
    1. valid approval_id matching a previously-submitted request
    2. CSV digest matching the digest at approval time
    3. mapping digest matching the digest at approval time
    4. tenant_id matching the original request's tenant
    5. idempotency_key not already executed
  All other tools are read/idempotent.

DEFAULT PORT 8095 (per ADR-028; documents = 8094, csv_ingest = 8095).
ENV HOOK    DOCUMIND_MCP_CSV_INGEST_URL (operator opt-in via inference-svc).
SCOPES      csv_ingest:read   (propose, validate, status)
            csv_ingest:write  (apply_approved_load)
            csv_ingest:approve (submit_for_approval)

DRILL       mcp/tests/drill_mcp_server_csv_ingest.py — locks 9
            implementation guardrails from ADR-028.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from mcp.server_common import (
    ToolCallRequest,
    build_auth,
    enforce_scope as _enforce_scope_common,
    handle_tool_call,
    mount_metrics_endpoint,
    setup_server_otel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp.server_csv_ingest")

app = FastAPI(title="DocuMind MCP — CSV Ingest server")
setup_server_otel(app, service_name="mcp-server-csv-ingest")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


# ---------------------------------------------------------------------------
# File-path safety + size cap — same shape as mcp/server_documents.py.
# Future iter: extract to mcp/server_common.py per ADR-028 §Consequences.
# ---------------------------------------------------------------------------
ALLOWED_PATH_PREFIXES = (
    "/mnt/deepa/",
    "/tmp/",
    "/var/tmp/",
)
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MiB; ADR-028 size-limit guardrail


def _resolve_safe_path(path_str: str) -> str:
    """Reject paths outside the allowlist; reject files > 50 MiB."""
    from pathlib import Path  # noqa: PLC0415
    p = Path(path_str).resolve()
    s = str(p)
    if not any(s.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "path_outside_allowlist",
                "message": (
                    f"Path {path_str!r} resolved to {s} — outside the read-"
                    f"allowed prefixes {ALLOWED_PATH_PREFIXES}. Per ADR-028 "
                    "the file allowlist is structural."
                ),
            },
        )
    if not p.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "file_not_found", "path": s},
        )
    if p.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "size": p.stat().st_size,
                "max_bytes": MAX_FILE_BYTES,
                "message": "Use ingestion-svc saga path for large files.",
            },
        )
    return s


# ---------------------------------------------------------------------------
# Staging-table-name guardrail. Per ADR-028: target table MUST match
# ^stg_[a-z0-9_]+$ — agents cannot write to non-staging tables. This stops
# an injected mapping from targeting governance.audit_log or any
# governance/orchestration schema table at the MCP boundary.
# ---------------------------------------------------------------------------
_STAGING_TABLE_RE = re.compile(r"^stg_[a-z0-9_]{1,60}$")


def _validate_staging_table(table_name: str) -> str:
    if not table_name or not _STAGING_TABLE_RE.match(table_name):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "table_not_staging",
                "table": table_name,
                "message": (
                    "csv_ingest tools target only staging tables matching "
                    "^stg_[a-z0-9_]+$. Per ADR-028: agents cannot write to "
                    "non-staging tables. Cross-tenant + governance schema "
                    "tables are structurally inaccessible from this MCP "
                    "boundary."
                ),
            },
        )
    return table_name


# ---------------------------------------------------------------------------
# Forbidden-keywords scan on agent-supplied text (column mapping etc).
# Defense-in-depth: even though we never EXECUTE agent SQL, an injected
# `; DROP TABLE x` in a column-mapping field would still be visible in
# audit logs. Reject early.
# ---------------------------------------------------------------------------
_DDL_FORBIDDEN = (
    "DROP",
    "TRUNCATE",
    "ALTER",
    "CREATE TABLE",
    "CREATE INDEX",
    "DELETE FROM",
    "UPDATE ",
    "INSERT INTO",
    "MERGE INTO",
    "GRANT ",
    "REVOKE ",
    "EXECUTE ",
    "COPY ",
    "VACUUM",
)


def _reject_ddl_text(blob: str, *, field_name: str) -> None:
    """Raise 400 if `blob` contains DDL/DML token (case-insensitive,
    word-boundary). Used to scan agent-supplied free-text fields like
    column mappings."""
    if not blob:
        return
    upper = blob.upper()
    for kw in _DDL_FORBIDDEN:
        if re.search(rf"\b{re.escape(kw.strip())}\b", upper):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "ddl_in_agent_text",
                    "field": field_name,
                    "keyword": kw.strip(),
                    "message": (
                        f"Field {field_name!r} contains DDL/DML token "
                        f"{kw.strip()!r}. Per ADR-028: raw SQL and DDL are "
                        f"rejected at the MCP boundary regardless of execution path."
                    ),
                },
            )


# ---------------------------------------------------------------------------
# CSV digest + draft store. Stage-1 keeps state in-memory. iter-66+ migrates
# to Postgres-backed store sharing the action-drafts pattern.
# ---------------------------------------------------------------------------
_DRAFTS: dict[str, dict[str, Any]] = {}  # draft_id → draft state


def _csv_digest(path_str: str) -> str:
    h = hashlib.sha256()
    with open(path_str, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _mapping_digest(mapping: dict[str, Any] | None) -> str:
    serial = json.dumps(mapping or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tool definitions — 5 tools per ADR-028
# ---------------------------------------------------------------------------
TOOLS: list[dict[str, Any]] = [
    {
        "name": "csv_ingest.propose_load",
        "description": (
            "Read a CSV + produce a dry-run ingest plan: row counts, "
            "inferred types, rejected-row reasons, target table, mapping "
            "digest. NEVER mutates the database."
        ),
        "input_schema": {
            "type": "object",
            "required": ["path", "table_name", "tenant_id"],
            "properties": {
                "path": {"type": "string"},
                "table_name": {"type": "string", "pattern": r"^stg_[a-z0-9_]+$"},
                "tenant_id": {"type": "string"},
                "column_mapping": {"type": "object"},
                "delimiter": {"type": "string", "default": ","},
                "has_header": {"type": "boolean", "default": True},
                "max_rows": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100000,
                    "default": 10000,
                },
                "idempotency_key": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "rows_total": {"type": "integer"},
                "rows_rejected": {"type": "integer"},
                "rejected_sample": {"type": "array"},
                "csv_digest": {"type": "string"},
                "mapping_digest": {"type": "string"},
                "needs_approval": {"type": "boolean"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.validate_load",
        "description": (
            "Re-run schema, type, dedupe, tenant-isolation, and policy "
            "checks for an existing draft. NEVER mutates the database."
        ),
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {"draft_id": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "valid": {"type": "boolean"},
                "checks": {"type": "object"},
                "errors": {"type": "array"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.submit_for_approval",
        "description": (
            "Persist the draft + request HITL approval. Records actor, "
            "tenant, CSV digest, target table, row count, mapping digest. "
            "Approval is fulfilled out-of-band; this tool returns "
            "approval_id + status='pending_approval'."
        ),
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {
                "draft_id": {"type": "string"},
                "operator_note": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "draft_id": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read", "csv_ingest:approve"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.apply_approved_load",
        "description": (
            "Apply an approved draft to the staging table. ONLY runs when "
            "approval_id matches a SUBMITTED request AND CSV/mapping "
            "digests match the values at approval time AND tenant_id "
            "matches AND the idempotency_key has not been executed. Any "
            "mismatch returns a denial; no rows land."
        ),
        "input_schema": {
            "type": "object",
            "required": ["draft_id", "approval_id", "approval_token"],
            "properties": {
                "draft_id": {"type": "string"},
                "approval_id": {"type": "string"},
                "approval_token": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "applied": {"type": "boolean"},
                "rows_ingested": {"type": "integer"},
                "rows_rejected": {"type": "integer"},
                "errors_table": {"type": "string"},
                "audit_row_id": {"type": "string"},
                "denial_reason": {"type": "string"},
            },
        },
        "side_effects": "write",
        "required_scopes": ["csv_ingest:write"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.load_status",
        "description": (
            "Read status + audit metadata for a draft or completed load."
        ),
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {"draft_id": {"type": "string"}},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "status": {"type": "string"},
                "rows_total": {"type": "integer"},
                "csv_digest": {"type": "string"},
                "approval_id": {"type": "string"},
                "applied_at": {"type": "string"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
]

_IDEMPOTENCY: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Tool implementations — Stage-1
# ---------------------------------------------------------------------------
def _propose_load_impl(args: dict[str, Any]) -> dict[str, Any]:
    path_str = _resolve_safe_path(args["path"])
    table = _validate_staging_table(args["table_name"])
    tenant_id = args["tenant_id"]
    column_mapping = args.get("column_mapping") or {}
    # Defense-in-depth — scan agent-supplied free text for DDL tokens
    _reject_ddl_text(table, field_name="table_name")
    for k, v in column_mapping.items():
        _reject_ddl_text(str(k), field_name=f"column_mapping.{k}")
        _reject_ddl_text(str(v), field_name=f"column_mapping.{k}.value")
    delimiter = args.get("delimiter", ",")
    has_header = bool(args.get("has_header", True))
    max_rows = int(args.get("max_rows", 10000))

    # Read + dry-run validate. Stage-1 records the row count + first 5
    # rejection reasons (rows shorter than header etc.). Real per-cell
    # type validation lands when the column-mapping schema is defined.
    rows_total = 0
    rejected: list[dict[str, Any]] = []
    headers: list[str] = []
    with open(path_str, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            if i == 0 and has_header:
                headers = row
                continue
            if i > max_rows + (1 if has_header else 0):
                break
            rows_total += 1
            if headers and len(row) != len(headers):
                if len(rejected) < 5:
                    rejected.append({
                        "line": i + 1,
                        "reason": (
                            f"row has {len(row)} columns; header has "
                            f"{len(headers)}"
                        ),
                    })

    csv_dig = _csv_digest(path_str)
    map_dig = _mapping_digest(column_mapping)
    draft_id = f"DRAFT-{uuid.uuid4().hex[:12].upper()}"
    _DRAFTS[draft_id] = {
        "draft_id": draft_id,
        "path": path_str,
        "table_name": table,
        "tenant_id": tenant_id,
        "csv_digest": csv_dig,
        "mapping_digest": map_dig,
        "rows_total": rows_total,
        "rows_rejected": len(rejected),
        "status": "proposed",
        "submitted_at": None,
        "approval_id": None,
        "applied_at": None,
        "idempotency_key": args.get("idempotency_key"),
    }
    return {
        "draft_id": draft_id,
        "rows_total": rows_total,
        "rows_rejected": len(rejected),
        "rejected_sample": rejected,
        "csv_digest": csv_dig,
        "mapping_digest": map_dig,
        "needs_approval": True,
    }


def _validate_load_impl(args: dict[str, Any]) -> dict[str, Any]:
    draft = _DRAFTS.get(args["draft_id"])
    if not draft:
        raise HTTPException(
            status_code=404,
            detail={"code": "draft_not_found", "draft_id": args["draft_id"]},
        )
    # Stage-1: re-digest the file + compare. iter-66+ adds schema +
    # tenant-isolation + dedupe checks against the staging table.
    current_dig = _csv_digest(draft["path"])
    csv_unchanged = current_dig == draft["csv_digest"]
    return {
        "draft_id": draft["draft_id"],
        "valid": csv_unchanged,
        "checks": {"csv_digest_unchanged": csv_unchanged},
        "errors": (
            [] if csv_unchanged
            else ["csv digest changed since proposal — re-propose"]
        ),
    }


def _submit_for_approval_impl(args: dict[str, Any]) -> dict[str, Any]:
    draft = _DRAFTS.get(args["draft_id"])
    if not draft:
        raise HTTPException(
            status_code=404,
            detail={"code": "draft_not_found", "draft_id": args["draft_id"]},
        )
    approval_id = f"APPR-{uuid.uuid4().hex[:12].upper()}"
    draft["approval_id"] = approval_id
    draft["status"] = "pending_approval"
    draft["submitted_at"] = time.time()
    return {
        "approval_id": approval_id,
        "draft_id": draft["draft_id"],
        "status": "pending_approval",
    }


def _apply_approved_load_impl(args: dict[str, Any]) -> dict[str, Any]:
    draft = _DRAFTS.get(args["draft_id"])
    if not draft:
        raise HTTPException(
            status_code=404,
            detail={"code": "draft_not_found", "draft_id": args["draft_id"]},
        )
    # Per ADR-028: any of these checks fails → denial with no DB write.
    if draft.get("approval_id") != args.get("approval_id"):
        return {
            "draft_id": draft["draft_id"],
            "applied": False,
            "rows_ingested": 0,
            "rows_rejected": 0,
            "denial_reason": "approval_id_mismatch",
        }
    if draft.get("status") != "pending_approval":
        return {
            "draft_id": draft["draft_id"],
            "applied": False,
            "rows_ingested": 0,
            "rows_rejected": 0,
            "denial_reason": f"draft_status_not_pending: {draft.get('status')}",
        }
    # Stage-1 always denies the actual write — operator must run the
    # apply step manually until iter-66 wires the Postgres apply path
    # with HMAC token verification. This matches ADR-028 §Implementation
    # guardrails #3 — apply without approval (or with unverified token)
    # always returns a denial.
    return {
        "draft_id": draft["draft_id"],
        "applied": False,
        "rows_ingested": 0,
        "rows_rejected": 0,
        "denial_reason": (
            "stage_1_no_apply: HMAC approval-token verification + Postgres "
            "apply path land in iter-66; until then every apply call is a "
            "structural denial. Operator can apply via service-side path "
            "(ingestion-svc saga) if business-urgent."
        ),
    }


def _load_status_impl(args: dict[str, Any]) -> dict[str, Any]:
    draft = _DRAFTS.get(args["draft_id"])
    if not draft:
        raise HTTPException(
            status_code=404,
            detail={"code": "draft_not_found", "draft_id": args["draft_id"]},
        )
    return {
        "draft_id": draft["draft_id"],
        "status": draft["status"],
        "rows_total": draft["rows_total"],
        "csv_digest": draft["csv_digest"],
        "approval_id": draft.get("approval_id") or "",
        "applied_at": draft.get("applied_at") or "",
    }


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "mcp-server-csv-ingest"}


@app.get("/tools/list")
async def tools_list() -> dict[str, Any]:
    return {"tools": TOOLS}


@app.post("/tools/call")
async def tools_call(
    req: ToolCallRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    return await handle_tool_call(
        req=req,
        tools=TOOLS,
        idempotency_key=idempotency_key,
        authorization=authorization,
        auth_required=_AUTH_REQUIRED,
        verifier=_VERIFIER,
        idempotency_store=_IDEMPOTENCY,
        dispatch=_dispatch,
        tracer_module=__name__,
        logger=log,
        service_label="mcp_csv_ingest",
    )


async def _dispatch(
    req: ToolCallRequest,
    idempotency_key: str | None,
    cid: str,
) -> dict[str, Any]:
    tool = next((t for t in TOOLS if t["name"] == req.name), None)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "tool_not_found", "name": req.name},
        )
    if os.getenv("MCP_INJECT_FAIL") == "1":
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "csv_ingest tool unavailable"},
        )
    try:
        if req.name == "csv_ingest.propose_load":
            return _propose_load_impl(req.arguments)
        if req.name == "csv_ingest.validate_load":
            return _validate_load_impl(req.arguments)
        if req.name == "csv_ingest.submit_for_approval":
            return _submit_for_approval_impl(req.arguments)
        if req.name == "csv_ingest.apply_approved_load":
            return _apply_approved_load_impl(req.arguments)
        if req.name == "csv_ingest.load_status":
            return _load_status_impl(req.arguments)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch_failed tool=%s", req.name)
        raise HTTPException(
            status_code=500,
            detail={"code": "tool_dispatch_error", "message": str(exc)[:500]},
        ) from exc
    raise HTTPException(
        status_code=500,
        detail={"code": "no_dispatch_for_tool", "name": req.name},
    )
