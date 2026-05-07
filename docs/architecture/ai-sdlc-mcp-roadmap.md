# AI SDLC — MCP fleet roadmap

> Maps the SDLC use-case (source control → CI/CD → review → deploy →
> observe → incident → triage) to the MCP server fleet. Each row maps
> a SDLC surface to a current state + a concrete next-iter action.
> Per CLAUDE.md §45.4: every claim maps to either a runnable drill OR
> an explicit operator action OR a future-iter scope.

## Coverage as of iter-68

| SDLC stage | Surface | MCP server | Status | Notes |
|---|---|---|---|---|
| **Plan** | Issues / tickets | `jira` | ✅ iter-67 read | issue_lookup + JQL search |
| Plan | Tickets (lighter) | `linear` | ❌ MISSING | scaffold-on-request |
| Plan | Roadmap docs | `gdrive` / `confluence` | ✅ gdrive iter-67 / ❌ confluence | gdrive read-only |
| **Source control** | PR / issue / code search | `github` | ✅ iter-68 read | 6 tools; allow-list-narrowed |
| Source control | GitLab | `gitlab` | ❌ MISSING | scaffold-on-request |
| **Build / CI** | GitHub Actions | `github_actions` | ❌ MISSING | workflow status; needs scaffold |
| Build / CI | Jenkins | `jenkins` | ❌ MISSING | scaffold-on-request |
| **Review** | PR comments / approvals | `github (write)` | ❌ MISSING | needs ADR (write surface) |
| Review | Code review checklists | `github` | ✅ iter-68 read | via PR/code search |
| **Test** | Pytest / Jest / Ruff | `tests` | ✅ existing | run_pytest/run_jest/run_ruff |
| Test | Drill regression | `drills` | ✅ existing | drill.list / drill.run |
| Test | Static analysis (Sonar) | `sonarqube` | ❌ MISSING | scaffold-on-request |
| Test | Vulnerability scan (Snyk) | `snyk` | ⚠️ workflow only | iter-44 drill; no MCP tool |
| **Deploy** | Docker compose | `deploy` | ✅ existing | compose_apply/rollback |
| Deploy | k8s manifests | `kubectl` | ❌ MISSING | manifests at infra/k8s/ |
| Deploy | Argo CD / Flux | `argocd` | ❌ MISSING | scaffold-on-request |
| **Observe** | Metrics (Prometheus) | `observe` | ✅ existing | prom_query/p95/alerts |
| Observe | Logs (ES) | `elasticsearch` | ❌ MISSING | ES container exists; no MCP |
| Observe | Tracing (Jaeger) | `jaeger` | ❌ MISSING | Jaeger container exists; no MCP |
| Observe | LLM obs (Langfuse) | `langfuse` | ❌ MISSING | container exists; no MCP |
| Observe | Datadog / New Relic | `datadog` | ❌ MISSING | scaffold-on-request |
| **Incident** | Generic ITSM | `itsm` | ✅ existing (mock) | incident_lookup/open |
| Incident | ServiceNow | `servicenow` | ✅ iter-67 read | provider-specific |
| Incident | PagerDuty | `pagerduty` | ❌ MISSING | scaffold-on-request |
| Incident | Sentry (errors) | `sentry` | ❌ MISSING | scaffold-on-request |
| **Communication** | Microsoft Teams | `teams` | ✅ iter-67 read | channel/msg search |
| Communication | Slack | `slack` | ❌ MISSING | most-asked alt to Teams |
| Communication | WhatsApp | `whatsapp` | ✅ iter-67 read | template lookup only |
| **Knowledge** | Google Drive | `gdrive` | ✅ iter-67 read | file search + metadata |
| Knowledge | Confluence | `confluence` | ❌ MISSING | scaffold-on-request |
| Knowledge | Notion | `notion` | ❌ MISSING | scaffold-on-request |
| Knowledge | SharePoint | `sharepoint` | ❌ MISSING | scaffold-on-request |
| **Data** | CSV/PDF/Word/DB read | `documents` | ✅ iter-61 read | 4 tools |
| Data | DB write (CSV ingest) | `csv_ingest` | ✅ iter-65/66 | approval-gated |
| **Cloud** | AWS console / CLI | `aws` | ❌ MISSING | scaffold-on-request |
| Cloud | GCP | `gcp` | ❌ MISSING | scaffold-on-request |
| Cloud | Azure | `azure` | ❌ MISSING | scaffold-on-request |
| **AI ops** | LLM | `ollama` | ✅ existing | local model proxy |
| AI ops | Research / web | `research` | ✅ existing | URL fetch + synth |
| AI ops | Paperclip aggregator | `paperclip` | ✅ existing | snapshot/health |

## Headcount

```
Currently shipped MCP servers:    17 (was 16; iter-68 adds github)
Read-only surface:                 16 servers
Approval-gated write surface:       1 server (csv_ingest)
SDLC-relevant gaps (priority):     ~12 missing servers
```

## Next-iter priority list (AI SDLC focus)

| # | Server | Why | Stage-1 tools |
|---|---|---|---|
| 1 | **slack** | most-common dev-team comm alt to Teams | channel_list / message_search |
| 2 | **github_actions** | CI/CD status — agents reading "did the build pass?" | workflow_run_get / workflow_run_search |
| 3 | **sonarqube** | code quality; agents reading "any new violations?" | issues_search / measures_get |
| 4 | **sentry** | error monitoring; agents reading "any new errors?" | issue_search / event_lookup |
| 5 | **pagerduty** | on-call lookup; agents reading "who's paging right now?" | incident_lookup / oncall_get |
| 6 | **kubectl** | k8s state; agents reading "what's the pod state?" | pod_describe / svc_get / event_search |
| 7 | **confluence** | wiki/docs; agents searching corporate knowledge | page_search / page_get |
| 8 | **datadog** | metrics + logs alt; agents reading prod state | metric_query / log_search |
| 9 | **aws** | cloud resource inventory | ec2_describe / s3_list_bucket / cloudwatch_query |
| 10 | **github (write)** | PR comments via approval gate (ADR-029 pattern) | needs separate ADR |
| 11 | **slack (write)** | external messages with consent registry | needs ADR |
| 12 | **whatsapp (write)** | per ADR-029 pattern | needs ADR |

## Pattern (every new MCP server follows this)

```
1. Create mcp/server_<name>.py following the iter-67 template:
     - TOOLS list (read-only Stage-1)
     - _live_or_stub() pattern with env-driven config
     - Input validators (regex + allow-list as appropriate)
     - Standard /health + /tools/list + /tools/call routes

2. Add `("<name>", os.getenv("DOCUMIND_MCP_<NAME>_URL", ""))` to
   inference-svc mcp_spec list

3. Drill mcp/tests/drill_mcp_<name>_server.py with:
     - canonical structure check
     - tool count + namespace prefix check
     - all-tools-read-only check
     - input validator negative cases
     - live_or_stub stub-mode check

4. Add row to this roadmap: status = ✅ iter-NN
```

## Write surfaces — NEED separate ADRs

Per ADR-028 pattern, each of these has structural rejection at the
read-server boundary AND requires a separate write-server with its
own ADR:

- **github write** (PR comment, issue create, merge) — needs ADR-029
- **slack send** — needs ADR with consent + cost design
- **whatsapp send** — needs ADR with opt-in tracking
- **teams send** — same shape as Slack
- **jira create / transition** — needs ADR with permission scope
- **servicenow create_incident** — needs ADR
- **kubectl apply / delete** — needs ADR; same gating as deploy server
- **aws mutating ops** — needs ADR per service (ec2 / s3 / iam)

## References

- `docs/architecture/adr/028-csv-to-db-ingest-write-surface-contract.md`
  (the canonical write-surface ADR shape — every future write server
  follows this template)
- `mcp/tests/drill_mcp_saas_servers.py` (iter-67; locks the 5 SaaS
  read-only servers)
- `mcp/tests/drill_mcp_github_server.py` (iter-68; locks GitHub read-only
  contract; 11 steps / 5 negative)
- iter-61 `e707ee7` documents server (CSV/PDF/Word/DB read)
- iter-67 `<pending>` SaaS batch (Jira/Teams/WhatsApp/GDrive/ServiceNow)
- iter-68 `<pending>` GitHub
- CLAUDE.md §13 / §43 / §44 / §45.4 / §47 / §47.6 / §50.5.3 / §51 / §54
