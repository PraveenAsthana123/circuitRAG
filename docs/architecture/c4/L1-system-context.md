# C4 L1 — System Context

> Highest-level view: users + the system + external systems it talks to.
> No internal containers shown at this level — those are L2.

## Diagram

```mermaid
graph TB
    %% --- People ---
    Analyst[("Risk Analyst<br>Business User Tier 1-3")]:::person
    Operator[("Platform Operator<br>(SRE / DevOps)")]:::person
    Auditor[("Auditor<br>(EU AI Act / SOC2)")]:::person

    %% --- System under design ---
    System["DocuMind RAG Platform<br/><br/>9-stage agentic pipeline:<br>research → strategy → code → review →<br>test → security → advise → deploy → observe<br/><br/>+ 100GB multi-format RAG<br>+ §48 explainability surface<br>+ §42 hard-stop deploy gates"]:::system

    %% --- External systems ---
    Ollama[("Local Ollama<br>Tier-A LLMs<br>deepseek-coder, qwen2.5,<br>starcoder2, llama3.1...")]:::ext
    Claude[("Claude CLI<br>Tier-B LLM<br>(reused local auth)")]:::ext
    Codex[("Codex CLI<br>Tier-B LLM<br>(reused local auth)")]:::ext
    Prom[("Prometheus<br>+ Alertmanager<br>(observability)")]:::ext
    DocSources[("Document Sources<br>PDF / DOCX / HTML / MD<br>customer policy archive,<br>Basel III docs, ...")]:::ext

    %% --- Relationships ---
    Analyst -->|"submit task<br>(banking risk review)"| System
    Operator -->|"approve / force-state<br>operator UI"| System
    Auditor -->|"GET /api/v1/agentic/<br>tasks/{id}/explain<br>§48.4 audit row"| System

    System -->|"local HTTP<br>cheap stages"| Ollama
    System -->|"shell-out for<br>novel-topic stages"| Claude
    System -->|"shell-out for<br>novel coder stages"| Codex
    System -->|"emit metrics<br>+ read AM alerts"| Prom
    System -->|"fetch URLs<br>(httpx)"| DocSources

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef ext fill:#999999,stroke:#666666,color:#fff
```

## Personas (3)

| Persona | Tier | Demo scenario |
|---|---|---|
| **Risk Analyst** | Business basic / advanced / expert | "Show high-risk loans this quarter with policy citations" |
| **Platform Operator** | SRE / DevOps | "Approve a flagged deploy at 3 AM" / "Force-open breaker for maintenance" |
| **Auditor** | Regulator-facing | "Pull §48.4 audit row for decision X" / "Show counterfactual" |

## External Systems (5)

| System | Why we depend on it | Failure mode |
|---|---|---|
| **Local Ollama** | Tier-A LLM (free, fast, local) | Slow → call_timeout_s; CB trips |
| **Claude CLI** | Tier-B LLM (novel topics) | Subprocess hang → CB trips → fall back to Tier-A |
| **Codex CLI** | Tier-B for code-heavy novel work | Same as Claude |
| **Prometheus + Alertmanager** | Observer's two-signal rollback rule | DBCircuitBreaker pattern; observer stays passive |
| **Document Sources** | Researcher's URL fetches (E6) | Per-URL httpx timeout; URLs failing → fetch_ok=false |

## Boundaries

- **Inside the system**: orchestrator, 4 MCP servers, Postgres, qdrant, frontend, observability stack
- **Outside the system**: Ollama (separate container), Claude/Codex CLI (system binaries),
  external HTTP doc sources, Prometheus stack (separately deployed)

## Trust boundaries

```
Analyst → [TLS / gateway / auth] → System
                                       ↓
                                  [tenant_id check + RLS]
                                       ↓
                                  Tools execute under
                                  per-tenant scope (CB-F)
```

The system's identity boundary today is: gateway authenticates the
caller; orchestrator trusts the `tenant_id` field on requests.
**P0 #31 brutal-review finding** — orchestrator should also validate
JWT signed by the gateway. Not yet wired.
