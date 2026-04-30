# Langfuse — LLM observability runbook

> Captures every LLM call (prompt + completion + cost + latency +
> trace) to a queryable UI. Opt-in via compose profile to preserve
> the file-header philosophy ("app services run natively").
>
> Locked by `mcp/tests/drill_langfuse_compose.py`.

## What Langfuse adds vs OTel + Prometheus

| Concern | OTel/Prom (existing) | Langfuse (this) |
| --- | --- | --- |
| Per-LLM-call traces | spans only; no prompt/completion bodies | full prompt + completion + token cost |
| Prompt versioning | not stored | versioned prompts with deploy tracking |
| Token cost per request | aggregate counter | per-request, per-model breakdown |
| Eval rubrics | none | LLM-as-judge eval framework |
| Replay / debug | trace + log | session replay with full I/O |

## Bring up

```bash
docker compose --profile observability up -d langfuse
```

Default URL: `http://localhost:3002` (Grafana already owns 3001).

First-run setup (operator action):

1. Visit `http://localhost:3002`
2. Sign up with any local email (auth is local; no email sent)
3. Create a project named `documind-dev`
4. Settings → API Keys → create new keypair
5. Save to `.loop/langfuse.env` (chmod 600):

```bash
mkdir -p .loop
cat > .loop/langfuse.env <<'EOF'
LANGFUSE_PUBLIC_KEY="pk-lf-REPLACE_ME"
LANGFUSE_SECRET_KEY="sk-lf-REPLACE_ME"
LANGFUSE_HOST="http://localhost:3002"
EOF
chmod 600 .loop/langfuse.env
```

Mirrors the `.loop/<service>.env` pattern from `alertmanager-webhook.md`
+ `cdn-integration.md` + `council-stats.env`.

## Wire to a Python service (sidecar-advisor canonical example)

```bash
# Add langfuse client to the service's requirements
cd services/sidecar-advisor
echo "langfuse>=2.50,<3" >> requirements.txt
.venv/bin/pip install -r requirements.txt
```

Then in the LLM-call site:

```python
# services/sidecar-advisor/advisor.py (illustrative)
import os
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

# Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env
_langfuse = Langfuse() if os.getenv("LANGFUSE_PUBLIC_KEY") else None

@observe()
async def run_council(event_type: str, content: str) -> dict:
    if _langfuse:
        langfuse_context.update_current_observation(
            metadata={"event_type": event_type, "content_hash": hash(content)},
        )
    # ... existing council logic ...
    return advice
```

The `@observe()` decorator captures input + output + latency + error
to Langfuse. Token cost is auto-computed if the LLM client is
instrumented (langfuse has wrappers for openai / anthropic / litellm).

## Verify

```bash
# Container health
docker compose ps langfuse
# Expected: STATUS = Up (healthy) after ~30s

# UI smoke
curl -sf http://localhost:3002/api/public/health | head

# Drill that locks the contract
python3 mcp/tests/drill_langfuse_compose.py
```

After wiring + a council run, the Langfuse UI shows:
- Each `run_council` invocation as a trace
- Per-author / per-reviewer / per-chair model call as observations
- Prompt + completion text per call
- Token count + latency per call

## Tear down

```bash
docker compose --profile observability stop langfuse
docker compose --profile observability rm -f langfuse
# Postgres data persists; langfuse_db remains for re-up
```

## Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Health check fails for >2 min | langfuse migrations running on first boot | wait; check logs `docker compose logs langfuse` |
| `DATABASE_URL: connection refused` | postgres not up yet | check `depends_on` healthy gate; restart langfuse |
| 500 error on first signup | NEXTAUTH_SECRET / SALT < 32 chars | regenerate; use `openssl rand -hex 32` |
| LLM calls not appearing in UI | client not instrumented or env vars missing | check `LANGFUSE_PUBLIC_KEY` is set in service env |
| Old traces missing | retention policy | dev profile keeps 7 days; configurable via env |

## Why this lives behind a profile

File-header philosophy of `docker-compose.yml`:

> Application services are run natively (`go run` / `uvicorn` / `npm
> run dev`) so you get fast rebuilds, debuggers, and logs directly.

Langfuse is observability infrastructure (data-store-tier in spirit)
but its setup overhead (signup, project creation, key generation)
makes it heavier than other infra services. Opt-in profile means:
- Default `docker compose up` excludes it
- Operators who need LLM-call observability run `--profile observability`
- Same pattern as api-gateway's `--profile app` (commit `4f8e1b0`)

## Composes with

- `docs/runbooks/alertmanager-webhook.md` — same `.loop/<svc>.env`
  chmod-600 secret pattern
- `docs/runbooks/cdn-integration.md` — same `.loop/<svc>.env` pattern
- `services/sidecar-advisor/advisor.py` — primary LLM-call site
- `infra/observability/otel-config.yaml` — OTel collects spans;
  Langfuse is complementary (LLM-specific richness vs OTel's
  service-graph richness)
- §38 audit row — Langfuse trace_id can be the §38 audit row's
  trace_id field, closing the LLM-call ↔ governance audit loop
- `/admin/llmops/deep` — operator surface that Langfuse data feeds

## Brutal rule

> OTel + Prometheus give you "the service is slow"; Langfuse gives
> you "the LLM call costing $0.43 used prompt v17 with this
> completion." Without per-LLM observability, FinOps rollouts are
> guesswork and prompt regressions surface as "users complaining."
> Run Langfuse the moment LLM cost or prompt-version drift becomes
> a real concern.
