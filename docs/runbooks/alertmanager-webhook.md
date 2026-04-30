# Alertmanager — Shared-Webhook Receiver Setup

> Operator runbook. Wires Alertmanager external delivery without
> baking secrets into git. Locked by
> `mcp/tests/drill_alertmanager_receiver_config.py`.

## Default state (out of the box)

`docker-compose.yml` boots Alertmanager with safe defaults:

```yaml
ALERTMANAGER_DEFAULT_RECEIVER: ${ALERTMANAGER_DEFAULT_RECEIVER:-local-log}
ALERTMANAGER_WEBHOOK_URL:      ${ALERTMANAGER_WEBHOOK_URL:-http://host.docker.internal:8099/alertmanager-placeholder}
```

The `local-log` receiver writes alerts to Alertmanager's stdout. No
external delivery; nothing leaks. Safe for fresh clones / CI / dev.

## Opting in to shared-webhook delivery

Two env vars flip Alertmanager from "log-only" to "POST every alert
to a real webhook":

| Variable | Value when opting in |
| --- | --- |
| `ALERTMANAGER_DEFAULT_RECEIVER` | `shared-webhook` |
| `ALERTMANAGER_WEBHOOK_URL` | the operator-supplied real URL |

Both must be set together — flipping the receiver without a real URL
silently POSTs to the placeholder host and drops the alerts. The
drill (§ below) prevents the receiver name from drifting; the
operator is responsible for the URL itself.

## Recommended env-secret path (matches `.loop/council-stats.env`)

Mirror the precedent set by
[`scripts/run_filter_pipeline.sh`](../../scripts/run_filter_pipeline.sh):
keep webhook secrets in `.loop/<service>.env` (chmod 600,
gitignored), and source them before bringing the service up.

### One-time setup

```bash
mkdir -p .loop
cat > .loop/alertmanager.env <<'EOF'
# Real values for the shared-webhook receiver.
# Sourced before `docker compose up -d alertmanager`.
# DO NOT commit; .loop/ is gitignored.
ALERTMANAGER_DEFAULT_RECEIVER=shared-webhook
ALERTMANAGER_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/REPLACE_ME
EOF
chmod 600 .loop/alertmanager.env
```

### Apply on each restart

```bash
set -a
. .loop/alertmanager.env
set +a
docker compose up -d alertmanager
```

The compose `command:` block already runs `sed` at boot to render
`__DEFAULT_RECEIVER__` / `__WEBHOOK_URL__` placeholders in
`infra/observability/alertmanager.yml` against the rendered env.
Restarting the container is enough; no manual file edits required.

### Verify

```bash
# 1. Drill — locks the contract end-to-end:
.venv/bin/python mcp/tests/drill_alertmanager_receiver_config.py

# 2. Check the receiver actually flipped inside the container:
docker exec documind-alertmanager wget -qO- http://localhost:9093/api/v2/status \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["config"]["original"])' \
  | grep -E "name:|url:"
# Expected: "name: shared-webhook" + the URL you set, NOT the placeholder.
```

## Choosing a webhook target

| Target | Format | URL shape |
| --- | --- | --- |
| Slack (incoming webhook) | Slack | `https://hooks.slack.com/services/T.../B.../...` |
| Discord | Discord (use Slack mode w/ `/slack` suffix) | `https://discord.com/api/webhooks/.../...slack` |
| PagerDuty (Events API v2) | generic JSON | `https://events.pagerduty.com/v2/enqueue` (route_key in payload) |
| Custom service | generic JSON | `https://your.host/alerts` |

Alertmanager's `webhook_configs` POSTs Alertmanager's native JSON
payload — Slack/Discord need their *Incoming Webhook* endpoints
specifically, not a generic webhook. For richer formatting (titles,
severity colors, runbook links), front the receiver with
[`webhook-bridge`](https://github.com/cloudflare/alertmanager-webhook-bridge)
or a small Lambda — that's a separate concern from the wiring this
runbook locks.

## Why this lives in `.loop/` and not `.env`

`.env` is repo-shared (committed to git in many setups; here it's
gitignored but read on every compose run). Putting the webhook URL
in `.env` blurs the "secret vs config" line.

`.loop/` is the project's secret-side-channel:

- Always gitignored (`.gitignore:116`).
- chmod 600 on creation (operator discipline).
- Sourced explicitly per service (`.loop/council-stats.env`,
  `.loop/alertmanager.env`, etc.) — no global blast radius.
- Loss recovery: regenerate the file from the matching runbook;
  the URL itself is the only thing the operator needs to keep.

## Failure modes & detection

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Drill step 5 fails (`stale placeholder-webhook receiver still present`) | Old receiver name leaked back into `alertmanager.yml` | Revert to `name: shared-webhook` per drill assertion |
| Alerts visible in `/alerts` UI but never reach external system | `ALERTMANAGER_DEFAULT_RECEIVER=shared-webhook` but `ALERTMANAGER_WEBHOOK_URL` still placeholder | Source `.loop/alertmanager.env`, restart container |
| External system rejects payload (4xx) | URL valid but format mismatch (e.g. Slack endpoint with raw Alertmanager JSON) | Use the dedicated Slack endpoint or front with a bridge |
| Config render silently no-ops | `sed` block in compose missing one of `__DEFAULT_RECEIVER__` / `__WEBHOOK_URL__` | Drill steps 1-4 catch this — re-run the drill after any compose edit |

## Related

- `mcp/tests/drill_alertmanager_receiver_config.py` — locks the
  contract; runs in the readonly tier (cheap; runs every loop).
- `infra/observability/alertmanager.yml` — the templated config the
  drill reads.
- `docker-compose.yml` (alertmanager service) — the sed-render boot
  command the drill verifies exists.
- `docs/runbooks/council-telemetry.md` — same env-secret pattern,
  applied to the council stats webhook.
- ADR-018 — three-way work allocation: webhook URL provisioning is
  operator-only credential work, not autonomous-loop scope.
