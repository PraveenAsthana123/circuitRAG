# OpenTelemetry Repo-Wide Coverage Matrix

This note is the repo-wide OpenTelemetry coverage matrix.

It answers:

- which services and tools have OTel today
- what kind of OTel coverage exists
- what is still missing

This is a visibility matrix, not a completion claim.

## 1. Coverage Legend

Use these meanings:

- `none`
  no visible OTel wiring
- `dependency-only`
  OTel libraries are present, but active wiring is not visible
- `startup`
  service initializes OTel
- `service-level`
  startup + inbound request instrumentation
- `service-plus-dependency`
  service-level plus outbound dependency instrumentation
- `tool-level`
  service-plus-dependency plus useful manual spans around key tool or workflow decisions

## 2. Repo-Wide Matrix

| Component | Startup OTel | Inbound spans | Outbound spans | Manual workflow/tool spans | Current coverage |
|---|---|---|---|---|---|
| `api-gateway` | not visible | not visible | not visible | not visible | dependency-only |
| `identity-svc` | not visible | not visible | not visible | not visible | none |
| `ingestion-svc` | yes | yes | yes (`asyncpg`, `redis`, `httpx`) | partial | service-plus-dependency |
| `retrieval-svc` | yes | yes | yes (`redis`, `httpx`) | partial | service-plus-dependency |
| `inference-svc` | yes | yes | yes (`asyncpg`, `redis`, `httpx`) | partial | service-plus-dependency |
| `evaluation-svc` | yes | yes | not clearly visible beyond base setup | thin | service-level |
| `governance-svc` | not visible | not visible | not visible | not visible | none |
| `finops-svc` | not visible | not visible | not visible | not visible | none |
| `observability-svc` | not visible | not visible | not visible | not visible | none |
| `frontend` | not clearly active | not clearly active | not clearly active | not visible | dependency-only |
| `mcp-server-hr` | yes | yes | n/a HTTP server role | partial dispatch spans through common wrapper | service-level to tool-level partial |
| `mcp-server-itsm` | yes | yes | n/a HTTP server role | partial dispatch spans through common wrapper | service-level to tool-level partial |
| `mcp-server-drills` | yes | yes | n/a HTTP server role | partial dispatch spans through common wrapper | service-level to tool-level partial |
| `draft_replay` worker | implicit tracer use | worker-level span use visible | indirect | partial | partial |
| `MultiHopRagAgent` | no explicit startup | no explicit request wrapper | indirect via services | weak/manual not evident | partial concept only |

## 3. Evidence Sources

### Shared Python OTel layer

- [libs/py/documind_core/observability.py](/mnt/deepa/rag/libs/py/documind_core/observability.py)

### Python services using shared OTel

- [services/ingestion-svc/app/main.py](/mnt/deepa/rag/services/ingestion-svc/app/main.py)
- [services/retrieval-svc/app/main.py](/mnt/deepa/rag/services/retrieval-svc/app/main.py)
- [services/inference-svc/app/main.py](/mnt/deepa/rag/services/inference-svc/app/main.py)
- [services/evaluation-svc/app/main.py](/mnt/deepa/rag/services/evaluation-svc/app/main.py)

### MCP OTel scaffold

- [mcp/server_common.py](/mnt/deepa/rag/mcp/server_common.py)
- [mcp/server_hr.py](/mnt/deepa/rag/mcp/server_hr.py)
- [mcp/server_itsm.py](/mnt/deepa/rag/mcp/server_itsm.py)
- [mcp/server_drills.py](/mnt/deepa/rag/mcp/server_drills.py)

### Worker tracing evidence

- [services/inference-svc/app/workers/draft_replay.py](/mnt/deepa/rag/services/inference-svc/app/workers/draft_replay.py)

### Go service dependency-only evidence

- [services/api-gateway/go.mod](/mnt/deepa/rag/services/api-gateway/go.mod)

No equivalent visible startup wiring was found in the inspected Go service main paths.

## 4. Functional Coverage View

| Functional path | Trace continuity today | Notes |
|---|---|---|
| gateway -> ingestion | weak to partial | Python service side good; gateway side not clearly wired |
| gateway -> retrieval | weak to partial | same issue |
| gateway -> inference | weak to partial | same issue |
| inference -> retrieval -> model | partial to strong | Python-side service instrumentation exists |
| inference agent -> MCP -> MCP server | partial | MCP servers instrumented; tool-level detail still thin |
| degraded draft fallback | partial | visibility exists but path-level completeness needs review |
| replay worker -> MCP -> audit | partial | worker tracer exists, but continuity needs stronger proof |

## 5. Bottom Line

The repo already has:

- strong Python-side OTel foundations
- shared MCP server OTel scaffold

The biggest repo-wide coverage gaps are:

- Go services
- gateway trace propagation
- deeper tool-level manual spans
- stronger async and replay continuity
