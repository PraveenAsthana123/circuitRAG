# Operator activation — 7 post-iter-19 items

> Iter-1-19 shipped 19 iterations of feature work. 7 items at the end
> of the session are operator-side: they require credentials / sudo /
> governance triage that autonomous-loop work cannot complete.
>
> This runbook is the canonical activation sequence — drilled by
> `mcp/tests/drill_operator_activation.py`.

## Status

- **Items 1, 2, 3, 5 (env flags + session secret)**: handled
  automatically when `.env` is created via the recipe in
  [§Items 1-5](#items-1-3-5-env-flags-via-env). The drill verifies
  `.env` shape if present.
- **Item 4 (XAI_API_KEY)**: requires operator-obtained credential
  from `https://console.x.ai`. Documented; cannot be auto-set.
- **Item 6 (Ollama daemon identity)**: requires `sudo`. Documented;
  outside §42 autonomous-loop scope.
- **Item 7 (577 HITL drafts triage)**: governance-decision territory
  per §38. Triage report generator drilled at
  `mcp/tests/drill_hitl_drafts_triage.py`.

## Items 1-3, 5: env flags via `.env`

Single-command activation — generates a fresh
`DOCUMIND_SESSION_TOKEN_SECRET` and enables all 3 §47.7 dual-write
flags:

```bash
SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
cat > .env <<EOF
DOCUMIND_ENV=development
MCP_GATEWAY_SQL_AUDIT_ENABLED=1
OPS_WORKER_SQL_ENABLED=1
MCP_TOOLS_SYNC_ENABLED=1
DOCUMIND_SESSION_TOKEN_SECRET=${SECRET}
XAI_API_KEY=
EOF
```

The file is `.gitignore`d (per `.gitignore:.env` line). Each flag
references a drilled invariant:

| Item | Flag | Drill | Composes with |
| --- | --- | --- | --- |
| 1 | `MCP_GATEWAY_SQL_AUDIT_ENABLED=1` | `drill_mcp_gateway_dual_write.py` | iter 11 |
| 2 | `OPS_WORKER_SQL_ENABLED=1` | `drill_ops_worker_dual_write.py` | iter 12 |
| 3 | `MCP_TOOLS_SYNC_ENABLED=1` | `drill_tools_catalog_sync.py` | iter 13 |
| 5 | `DOCUMIND_SESSION_TOKEN_SECRET=…` | `drill_session_token_approval.py` | iter 6 |

After setting `.env`, restart any running services to pick up the
new env. Per ADR-025: "The legacy file remains authoritative until
a future contract-phase operator decision removes it."

### Verify activation

```bash
# Confirm .env loaded into a Python process:
set -a; source .env; set +a
python3 -c "
import os
for f in ('MCP_GATEWAY_SQL_AUDIT_ENABLED', 'OPS_WORKER_SQL_ENABLED',
          'MCP_TOOLS_SYNC_ENABLED', 'DOCUMIND_SESSION_TOKEN_SECRET'):
    v = os.environ.get(f, '<unset>')
    if 'SECRET' in f and v != '<unset>':
        print(f'{f} = {v[:8]}…{v[-4:]} ({len(v)} chars)')
    else:
        print(f'{f} = {v}')
"

# Run the dashboard surface to see migrate-phase status:
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from paperclip_manager import snapshot
mps = snapshot()['migrate_phase_status']
for name, flag in mps['flags'].items():
    print(f'{name:30} enabled={flag[\"enabled\"]}')
"
```

Expected output: 3 flags `enabled=True`, secret 64-char hex.

## Item 4: `XAI_API_KEY` (operator credential)

ChatXAI integration shipped in iter 10 (`fa7358d`). The
`langchain-xai` library is importable but cannot call without a
valid API key.

```bash
# 1. Get a key from https://console.x.ai (free tier available)
# 2. Add to .env:
echo "XAI_API_KEY=xai-…actual-key-here…" >> .env
# 3. Restart processes
```

**Honest gap** (per Paperclip `ai_integrations` surface): until
`XAI_API_KEY` is set, `ChatXAI()` instantiation fails and the
honest_gap row appears in the dashboard.

## Item 6: Ollama daemon identity key (sudo)

The Ollama daemon at `/usr/share/ollama/.ollama/` is missing its
`id_ed25519` identity key, blocking ALL `ollama pull` operations.
Discovered in iter 10 (`fa7358d`).

```bash
# Sudo required — Ollama daemon runs as user ollama (UID/GID owned
# by ollama:ollama mode 750, dir /usr/share/ollama/ unreadable by
# operator user).

# Option A — restart (may auto-regenerate):
sudo systemctl restart ollama
ollama pull qwen2.5:latest    # smoke test

# Option B — manually generate the key as the ollama user:
sudo -u ollama ssh-keygen -t ed25519 \
  -f /usr/share/ollama/.ollama/id_ed25519 \
  -N "" -C "ollama-daemon"
sudo systemctl restart ollama

# Option C — point Ollama at user-writable home:
# (reqs systemd unit edit; see /etc/systemd/system/ollama.service)
sudo systemctl edit ollama
# add: Environment="OLLAMA_HOME=/var/lib/ollama"
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Outside §42 autonomous-loop scope (sudo). Operator-action required.

**Honest gap** (per Paperclip `ai_integrations` surface): the
ollama probe still works (it lists installed models) but pull
operations fail. Surface flags this state.

## Item 7: 577 HITL drafts triage (governance)

`governance.action_drafts` table holds tool-call drafts auto-created
when an MCP server was unreachable. 577 are pending; bulk-rejecting
or bulk-replaying them is governance-decision territory per §38.

```bash
# Generate a read-only triage report (no state change):
python3 scripts/hitl_drafts_triage.py > docs/reports/hitl-drafts-triage-$(date +%Y%m%d).md

# Manual replay of one draft (authoritative path; per §43):
python3 scripts/replay_action_draft.py --draft-id DRAFT-XXXX

# Bulk-reject by age (operator-explicit; example for >30d stale):
psql ... -c "UPDATE governance.action_drafts
              SET status='rejected', replayed_at=NOW(),
                  replay_result='{\"reason\": \"stale_>30d\"}'::jsonb
              WHERE status='pending' AND created_at < NOW() - INTERVAL '30 days';"
```

The triage report classifies pending drafts by:
- **Age bucket** (< 1d / < 7d / < 30d / >= 30d)
- **Originating server** (research / hr / itsm / observe / ...)
- **Failure reason** (cb_open / ConnectError / http_502 / ...)
- **Stale candidates** (any > 30d with status='pending')

Operator reviews the report, decides which subset to bulk-reject vs
re-replay, runs the appropriate command above. NOT an autonomous-
loop iteration — explicit governance decision per §38.

## Summary

| # | Item | Autonomous-doable? | Status |
| --- | --- | --- | --- |
| 1 | `MCP_GATEWAY_SQL_AUDIT_ENABLED=1` | ✅ via `.env` | doc + drill |
| 2 | `OPS_WORKER_SQL_ENABLED=1` | ✅ via `.env` | doc + drill |
| 3 | `MCP_TOOLS_SYNC_ENABLED=1` | ✅ via `.env` | doc + drill |
| 4 | `XAI_API_KEY` | ❌ operator credential | doc only |
| 5 | `DOCUMIND_SESSION_TOKEN_SECRET` | ✅ generated locally | doc + drill |
| 6 | Ollama daemon identity key | ❌ sudo | doc only |
| 7 | 577 HITL drafts triage | ❌ §38 governance | triage script + drill |

Per §44 stop conditions: items 4 and 6 are genuinely outside
autonomous-loop scope. Items 1-3, 5 are activated when operator runs
the `.env` recipe above. Item 7's triage script is autonomous-doable
(read-only); the actual triage decisions are operator territory.
