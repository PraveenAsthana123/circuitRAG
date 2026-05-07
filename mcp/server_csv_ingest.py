# ruff: noqa: I001
"""
CSV ingest MCP server — approval-gated CSV-to-DB write surface.

Per ADR-028 this server is separate from ``mcp/server_documents.py``.
Documents MCP remains read-only; this namespace owns the write-capable
CSV ingest workflow:

  * csv_ingest.propose_load
  * csv_ingest.validate_load
  * csv_ingest.submit_for_approval
  * csv_ingest.apply_approved_load
  * csv_ingest.load_status

The implementation is deliberately conservative. Agents never submit raw
SQL. They submit a target table name and a CSV-header to DB-column mapping.
The server validates identifiers, computes CSV/mapping digests, records an
approval draft, and only applies a draft when the approved digest tuple still
matches. If ``CSV_INGEST_SQLITE_PATH`` is set, apply performs parameterized
INSERTs into an existing SQLite table. Without a DB path, apply records an
in-memory write result so the approval gate can be exercised locally without
external resources.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
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

app = FastAPI(title="DocuMind MCP — CSV ingest server")
setup_server_otel(app, service_name="mcp-server-csv-ingest")
mount_metrics_endpoint(app)

_AUTH_REQUIRED, _VERIFIER = build_auth()

ALLOWED_PATH_PREFIXES = ("/mnt/deepa/", "/tmp/", "/var/tmp/")  # noqa: S108 - ADR-028 local ingest allowlist
MAX_FILE_BYTES = int(os.getenv("CSV_INGEST_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
FORBIDDEN_SQL_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|MERGE|COPY|VACUUM|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


@dataclass
class CsvIngestState:
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    loads: dict[str, dict[str, Any]] = field(default_factory=dict)
    memory_db: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


state = CsvIngestState()


def _enforce_scope(authorization: str | None, tool: dict[str, Any]) -> dict[str, Any]:
    return _enforce_scope_common(_VERIFIER, authorization, tool)


def _build_idempotency_store():
    from mcp.idempotency import InMemoryIdempotencyStore, PostgresIdempotencyStore

    pg_host = os.getenv("DOCUMIND_PG_HOST", "").strip()
    if pg_host and os.getenv("MCP_IDEMPOTENCY_DURABLE", "true").lower() == "true":
        dsn = (
            f"postgresql://{os.getenv('DOCUMIND_PG_USER', 'documind_app')}:"
            f"{os.getenv('DOCUMIND_PG_PASSWORD', 'documind_app')}@"
            f"{pg_host}:{os.getenv('DOCUMIND_PG_PORT', '5432')}/"
            f"{os.getenv('DOCUMIND_PG_DB', 'documind')}"
        )
        return PostgresIdempotencyStore(
            dsn, ttl_seconds=int(os.getenv("MCP_IDEMPOTENCY_TTL_S", "86400")),
        )
    return InMemoryIdempotencyStore()


_IDEMPOTENCY = _build_idempotency_store()


TOOLS: list[dict[str, Any]] = [
    {
        "name": "csv_ingest.propose_load",
        "description": "Read a CSV and produce a deterministic ingest draft plan. Does not write target DB rows.",
        "input_schema": {
            "type": "object",
            "required": ["path", "target_table", "column_mapping", "tenant_id"],
            "properties": {
                "path": {"type": "string"},
                "target_table": {"type": "string"},
                "column_mapping": {"type": "object"},
                "tenant_id": {"type": "string"},
                "dedupe_key": {"type": "string"},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": 100000, "default": 10000},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.validate_load",
        "description": "Re-run schema, digest, tenant, duplicate, and policy checks for a draft.",
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {"draft_id": {"type": "string"}},
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.submit_for_approval",
        "description": "Persist or update an approval request for a draft; optional operator token can approve it.",
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {
                "draft_id": {"type": "string"},
                "approved_by": {"type": "string"},
                "approval_token": {"type": "string"},
            },
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:write"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.apply_approved_load",
        "description": "Apply an approved CSV ingest draft using the approved digest tuple only.",
        "input_schema": {
            "type": "object",
            "required": ["draft_id", "tenant_id"],
            "properties": {
                "draft_id": {"type": "string"},
                "tenant_id": {"type": "string"},
            },
        },
        "side_effects": "write",
        "required_scopes": ["csv_ingest:write", "csv_ingest:approve"],
        "idempotent": True,
    },
    {
        "name": "csv_ingest.load_status",
        "description": "Read approval and apply status for a CSV ingest draft.",
        "input_schema": {
            "type": "object",
            "required": ["draft_id"],
            "properties": {"draft_id": {"type": "string"}},
        },
        "side_effects": "read",
        "required_scopes": ["csv_ingest:read"],
        "idempotent": True,
    },
]


def _reject_raw_sql_surface(args: dict[str, Any]) -> None:
    if "sql" in args or "query" in args:
        raise HTTPException(
            status_code=400,
            detail={"code": "raw_sql_rejected", "message": "Raw SQL is not accepted by csv_ingest tools."},
        )
    blob = json.dumps(args, sort_keys=True, default=str)
    if FORBIDDEN_SQL_RE.search(blob):
        raise HTTPException(
            status_code=400,
            detail={"code": "ddl_or_sql_keyword_rejected", "message": "SQL/DDL keywords are rejected at the MCP boundary."},
        )


def _safe_identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not IDENT_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail={"code": "invalid_identifier", "field": label, "value": value})
    return value


def _allowed_tables() -> set[str]:
    raw = os.getenv("CSV_INGEST_ALLOWED_TABLES", "csv_ingest_demo")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _resolve_safe_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    s = str(p)
    if not any(s.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail={"code": "path_outside_allowlist", "path": s, "allowed": ALLOWED_PATH_PREFIXES},
        )
    if not p.is_file():
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "path": s})
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail={"code": "file_too_large", "size": size, "max_bytes": MAX_FILE_BYTES})
    return p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _mapping_digest(mapping: dict[str, str], target_table: str) -> str:
    payload = {"target_table": target_table, "column_mapping": mapping}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_tenant(req_tenant: str | None, arg_tenant: str | None) -> str:
    if not arg_tenant:
        raise HTTPException(status_code=400, detail={"code": "tenant_required"})
    if req_tenant and req_tenant != arg_tenant:
        raise HTTPException(
            status_code=403,
            detail={"code": "tenant_mismatch", "request_tenant": req_tenant, "argument_tenant": arg_tenant},
        )
    return arg_tenant


def _read_csv_rows(path: Path, *, max_rows: int) -> tuple[list[str], list[dict[str, str]], bool]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        truncated = False
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                truncated = True
                break
            rows.append({str(k): "" if v is None else str(v) for k, v in row.items() if k is not None})
    return headers, rows, truncated


def _validate_mapping(headers: list[str], mapping: Any) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        raise HTTPException(status_code=400, detail={"code": "invalid_column_mapping"})
    normalized: dict[str, str] = {}
    for src, dest in mapping.items():
        if src not in headers:
            raise HTTPException(status_code=400, detail={"code": "unknown_csv_column", "column": src})
        normalized[str(src)] = _safe_identifier(str(dest), label=f"column_mapping.{src}")
    return normalized


def _make_draft_id(*, tenant_id: str, csv_digest: str, mapping_digest: str, dedupe_key: str) -> str:
    raw = f"{tenant_id}:{csv_digest}:{mapping_digest}:{dedupe_key}"
    return "CSV-" + hashlib.sha256(raw.encode()).hexdigest()[:16].upper()


def _plan_from_args(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    _reject_raw_sql_surface(args)
    tenant_id = _validate_tenant(req_tenant, args.get("tenant_id"))
    target_table = _safe_identifier(str(args.get("target_table", "")), label="target_table")
    allowed = _allowed_tables()
    if target_table not in allowed:
        raise HTTPException(status_code=403, detail={"code": "target_table_not_allowed", "target_table": target_table, "allowed": sorted(allowed)})
    path = _resolve_safe_path(str(args.get("path", "")))
    max_rows = int(args.get("max_rows", 10000))
    headers, rows, truncated = _read_csv_rows(path, max_rows=max_rows)
    mapping = _validate_mapping(headers, args.get("column_mapping"))
    dedupe_key = str(args.get("dedupe_key") or "")
    if dedupe_key and dedupe_key not in headers:
        raise HTTPException(status_code=400, detail={"code": "unknown_dedupe_key", "dedupe_key": dedupe_key})

    rejected_rows = []
    if "tenant_id" in headers:
        bad = [i for i, row in enumerate(rows, start=1) if row.get("tenant_id") not in ("", tenant_id)]
        rejected_rows.extend({"row": i, "reason": "tenant_mismatch"} for i in bad[:50])
    duplicate_count = 0
    if dedupe_key:
        seen: set[str] = set()
        for row in rows:
            value = row.get(dedupe_key, "")
            if value in seen:
                duplicate_count += 1
            seen.add(value)

    csv_digest = _sha256_file(path)
    mdig = _mapping_digest(mapping, target_table)
    draft_id = _make_draft_id(
        tenant_id=tenant_id,
        csv_digest=csv_digest,
        mapping_digest=mdig,
        dedupe_key=dedupe_key,
    )
    return {
        "draft_id": draft_id,
        "path": str(path),
        "target_table": target_table,
        "tenant_id": tenant_id,
        "headers": headers,
        "column_mapping": mapping,
        "dedupe_key": dedupe_key,
        "csv_digest": csv_digest,
        "mapping_digest": mdig,
        "row_count": len(rows),
        "truncated": truncated,
        "duplicate_count": duplicate_count,
        "rejected_rows": rejected_rows,
        "status": "proposed",
        "created_at": time.time(),
    }


def _propose_load(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    plan = _plan_from_args(args, req_tenant)
    state.plans[plan["draft_id"]] = plan
    return {"ok": True, "result": {"plan": plan}}


def _validate_load(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    draft_id = str(args.get("draft_id", ""))
    plan = state.plans.get(draft_id)
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "draft_id": draft_id})
    _validate_tenant(req_tenant, plan["tenant_id"])
    current_digest = _sha256_file(Path(plan["path"]))
    checks = {
        "csv_digest_matches": current_digest == plan["csv_digest"],
        "mapping_digest_matches": _mapping_digest(plan["column_mapping"], plan["target_table"]) == plan["mapping_digest"],
        "no_rejected_rows": not plan["rejected_rows"],
        "target_table_allowed": plan["target_table"] in _allowed_tables(),
    }
    return {"ok": True, "result": {"draft_id": draft_id, "valid": all(checks.values()), "checks": checks}}


def _submit_for_approval(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    _reject_raw_sql_surface(args)
    draft_id = str(args.get("draft_id", ""))
    plan = state.plans.get(draft_id)
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "draft_id": draft_id})
    _validate_tenant(req_tenant, plan["tenant_id"])
    approval = {
        "draft_id": draft_id,
        "status": "pending",
        "tenant_id": plan["tenant_id"],
        "target_table": plan["target_table"],
        "csv_digest": plan["csv_digest"],
        "mapping_digest": plan["mapping_digest"],
        "row_count": plan["row_count"],
        "requested_at": time.time(),
        "approved_by": None,
        "approved_at": None,
    }
    expected_token = os.getenv("CSV_INGEST_OPERATOR_APPROVAL_TOKEN", "").strip()
    supplied_token = str(args.get("approval_token") or "")
    if expected_token and supplied_token == expected_token:
        approval["status"] = "approved"
        approval["approved_by"] = str(args.get("approved_by") or "operator")
        approval["approved_at"] = time.time()
    elif supplied_token:
        raise HTTPException(status_code=403, detail={"code": "invalid_approval_token"})
    state.approvals[draft_id] = approval
    return {"ok": True, "result": {"approval": approval}}


def _assert_approved(plan: dict[str, Any]) -> dict[str, Any]:
    approval = state.approvals.get(plan["draft_id"])
    if not approval or approval.get("status") != "approved":
        raise HTTPException(status_code=403, detail={"code": "approval_required", "draft_id": plan["draft_id"]})
    current_csv_digest = _sha256_file(Path(plan["path"]))
    current_mapping_digest = _mapping_digest(plan["column_mapping"], plan["target_table"])
    mismatches = [
        key for key, current in (
            ("csv_digest", current_csv_digest),
            ("mapping_digest", current_mapping_digest),
            ("target_table", plan["target_table"]),
            ("tenant_id", plan["tenant_id"]),
        )
        if approval.get(key) != current
    ]
    if mismatches:
        raise HTTPException(status_code=409, detail={"code": "approval_digest_mismatch", "fields": mismatches})
    return approval


def _rows_for_insert(plan: dict[str, Any]) -> list[dict[str, Any]]:
    _, rows, _ = _read_csv_rows(Path(plan["path"]), max_rows=max(plan["row_count"], 1))
    out = []
    for row in rows:
        if row.get("tenant_id") not in (None, "", plan["tenant_id"]):
            continue
        mapped = {dest: row[src] for src, dest in plan["column_mapping"].items()}
        out.append(mapped)
    return out


def _sqlite_apply(plan: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    db_path = os.getenv("CSV_INGEST_SQLITE_PATH", "").strip()
    if not db_path:
        state.memory_db.setdefault(plan["target_table"], []).extend(rows)
        return {"backend": "memory", "inserted_rows": len(rows), "target_table": plan["target_table"]}
    columns = list(plan["column_mapping"].values())
    placeholders = ", ".join("?" for _ in columns)
    col_sql = ", ".join(f'"{c}"' for c in columns)
    # target_table + columns are validated with IDENT_RE before this point;
    # row values remain parameterized through executemany.
    sql = f'INSERT INTO "{plan["target_table"]}" ({col_sql}) VALUES ({placeholders})'  # noqa: S608
    with sqlite3.connect(db_path) as conn:
        conn.executemany(sql, [[row.get(c, "") for c in columns] for row in rows])
        conn.commit()
    return {"backend": "sqlite", "inserted_rows": len(rows), "target_table": plan["target_table"]}


def _apply_approved_load(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    _reject_raw_sql_surface(args)
    draft_id = str(args.get("draft_id", ""))
    plan = state.plans.get(draft_id)
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "draft_id": draft_id})
    _validate_tenant(req_tenant, args.get("tenant_id"))
    _validate_tenant(req_tenant, plan["tenant_id"])
    if args.get("tenant_id") != plan["tenant_id"]:
        raise HTTPException(status_code=403, detail={"code": "tenant_mismatch", "request_tenant": plan["tenant_id"], "argument_tenant": args.get("tenant_id")})
    approval = _assert_approved(plan)
    rows = _rows_for_insert(plan)
    result = _sqlite_apply(plan, rows)
    load = {
        "draft_id": draft_id,
        "status": "applied",
        "approval": approval,
        "result": result,
        "applied_at": time.time(),
        "load_id": "LOAD-" + uuid.uuid4().hex[:12].upper(),
    }
    state.loads[draft_id] = load
    return {"ok": True, "result": load}


def _load_status(args: dict[str, Any], req_tenant: str | None) -> dict[str, Any]:
    draft_id = str(args.get("draft_id", ""))
    plan = state.plans.get(draft_id)
    if not plan:
        raise HTTPException(status_code=404, detail={"code": "draft_not_found", "draft_id": draft_id})
    _validate_tenant(req_tenant, plan["tenant_id"])
    return {
        "ok": True,
        "result": {
            "draft_id": draft_id,
            "plan_status": plan.get("status", "proposed"),
            "approval": state.approvals.get(draft_id),
            "load": state.loads.get(draft_id),
        },
    }


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


async def _dispatch(req: ToolCallRequest, idempotency_key: str | None, cid: str) -> dict[str, Any]:
    if req.name == "csv_ingest.propose_load":
        return _propose_load(req.arguments, req.tenant_id)
    if req.name == "csv_ingest.validate_load":
        return _validate_load(req.arguments, req.tenant_id)
    if req.name == "csv_ingest.submit_for_approval":
        return _submit_for_approval(req.arguments, req.tenant_id)
    if req.name == "csv_ingest.apply_approved_load":
        return _apply_approved_load(req.arguments, req.tenant_id)
    if req.name == "csv_ingest.load_status":
        return _load_status(req.arguments, req.tenant_id)
    raise HTTPException(status_code=404, detail={"code": "tool_not_found", "name": req.name})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("MCP_CSV_INGEST_PORT", "8095")))
