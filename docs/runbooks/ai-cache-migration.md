# Runbook — AI cache migration to /mnt/deepa/installed-software

> Operator's reference for `scripts/migrate_ai_caches_to_deepa.sh`.
> Per the policy at `~/.claude/policies/ai-storage-on-deepa.md`.

## What gets moved (Tier 1, safe)

| Source | Size class | Destination |
|---|---|---|
| `~/.cache/huggingface` | 5–200 GB | `/mnt/deepa/installed-software/huggingface/` |
| `~/.cache/pip` | 1–15 GB | `/mnt/deepa/installed-software/cache/pip/` |
| `~/.cache/uv` | 1–10 GB | `/mnt/deepa/installed-software/cache/uv/` |
| `~/.cache/torch` | 1–20 GB | `/mnt/deepa/installed-software/torch/` |
| `~/.cache/ms-playwright` | 0.5–3 GB | `/mnt/deepa/installed-software/cache/playwright/` |

What stays put (Tier 3, never move): `~/miniconda3`, `~/.nvm`,
`~/snap`, `~/.local/`, `/usr/lib/`, `/opt/`, `/usr/local/`. Moving
these breaks shell PATH / conda activation / system service files.
The policy doc explains why each is unsafe.

Ollama is Tier 2 — has its own migration script (sudo + systemd
restart). Run separately when ready.

## Modes

```bash
# Preview the plan (default; no changes)
scripts/migrate_ai_caches_to_deepa.sh

# Execute migration (rsync + symlink + .bak rename, ~10-15 min for 73 GB on HDD)
scripts/migrate_ai_caches_to_deepa.sh --apply

# Verify your tools work, then free the .bak originals
scripts/migrate_ai_caches_to_deepa.sh --finalize

# If something broke after --apply
scripts/migrate_ai_caches_to_deepa.sh --rollback
```

The script logs every event as JSON-line to
`/mnt/deepa/installed-software/migration.log` for auditability.

## How rollback works

After `--apply` runs, each migrated cache exists in three places:

1. **New canonical location**: `/mnt/deepa/installed-software/<tool>/`
   (used by tools via env var redirects)
2. **Symlink at the old path**: `~/.cache/<tool>` → new location
   (legacy tools that hardcode the path keep working)
3. **Backup at the old path with date suffix**: `~/.cache/<tool>.bak-<YYYYMMDD-HHMMSS>`
   (kept until operator runs `--finalize`)

`--rollback` reverses (1) and (2) by:

1. Removing each symlink
2. `mv`ing the `.bak-<date>` directory back to its original name
3. Clearing the bak-index

The new location at `/mnt/deepa/installed-software/<tool>/` stays
intact (rsync doesn't touch source). After `--rollback`, you can
delete `/mnt/deepa/installed-software/<tool>/` manually if you
don't want the duplicate.

`--finalize` is the one-way step: it deletes the `.bak-<date>`
directories. After finalize, **rollback is no longer possible** —
the original data is gone, and only the `/mnt/deepa` copy remains.
Run finalize ONLY after you've verified for at least one full
work session that all your AI tools still load models, run pip
installs, etc., correctly.

## OS sanity checks after `--apply`

Run these in order. ALL must pass before considering the
migration successful:

```bash
# 1. Disk freed: `/` should drop ~73 GB; /mnt/deepa should grow.
df -h / /mnt/deepa

# 2. Symlinks point to /mnt/deepa
ls -la ~/.cache/huggingface ~/.cache/pip ~/.cache/torch
# expected: lrwxrwxrwx  ...  /mnt/deepa/installed-software/...

# 3. New canonical locations are populated
ls /mnt/deepa/installed-software/huggingface/ | head
ls /mnt/deepa/installed-software/cache/pip/ | head

# 4. Backup originals exist (rollback safety net)
ls -d ~/.cache/*.bak-* 2>/dev/null

# 5. Python imports still work
python3 -c "import sys; print(sys.version)"

# 6. pip cache is readable through the symlink
pip cache info

# 7. PyTorch can find its cache
python3 -c "import torch; print(torch.hub.get_dir())"

# 8. HuggingFace tools resolve cache
python3 -c "from huggingface_hub import constants as c; print(c.HF_HUB_CACHE)"

# 9. Ollama daemon (if Ollama not yet migrated, it stays on /)
systemctl is-active ollama && ollama list | head

# 10. Shell can spawn fresh processes (the most basic OS sanity)
bash -c 'echo OK'
```

If any of 1-10 fails: `scripts/migrate_ai_caches_to_deepa.sh --rollback`
and report the failure in the migration.log.

## Adding the env vars (so future tools use the new location)

Append to `~/.bashrc` (or `~/.zshrc`):

```bash
# Per ~/.claude/policies/ai-storage-on-deepa.md
export AI_STORAGE_ROOT="/mnt/deepa/installed-software"
export HF_HOME="$AI_STORAGE_ROOT/huggingface"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export HF_DATASETS_CACHE="$HF_HOME/datasets"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export TORCH_HOME="$AI_STORAGE_ROOT/torch"
export PIP_CACHE_DIR="$AI_STORAGE_ROOT/cache/pip"
export UV_CACHE_DIR="$AI_STORAGE_ROOT/cache/uv"
export PLAYWRIGHT_BROWSERS_PATH="$AI_STORAGE_ROOT/cache/playwright"
export OLLAMA_MODELS="$AI_STORAGE_ROOT/ollama/models"
export TIKTOKEN_CACHE_DIR="$AI_STORAGE_ROOT/cache/tiktoken"
```

After editing, `source ~/.bashrc` or open a fresh terminal. The
symlinks created by `--apply` mean current tools work immediately;
the env vars ensure FUTURE downloads go to the right place even
if the symlink is later removed.

## Long-term: when /mnt/deepa fills up

- **Prune HuggingFace**: `huggingface-cli scan-cache` → review →
  `huggingface-cli delete-cache`
- **Prune pip**: `pip cache purge` (frees `$PIP_CACHE_DIR`)
- **Prune Torch**: manually delete `~/.cache/torch/hub/checkpoints/<old>`
- **Prune playwright**: `npx playwright uninstall` followed by
  re-install only the browser engines you use

These are all idempotent — they delete cached downloads that get
re-fetched if needed.

## Failure modes + recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `df` shows `/` still 80%+ full after `--apply` | Migration didn't run, or you only saw 1 cache moved | Check `tail /mnt/deepa/installed-software/migration.log` for `migrate_start` events without matching `verify_ok`. Re-run `--apply`. |
| Python import fails: `transformers` not found | pip cache symlink broken; re-runs delete `.bak-` | Run `--rollback`; investigate `migration.log`. |
| Ollama suddenly empty | You ran a Tier-2 Ollama migration without updating systemd | `sudo systemctl edit ollama` → check for `Environment="OLLAMA_MODELS=..."`; restart |
| `--rollback` complains "bak missing" | `--finalize` was already run | Recovery is from the `/mnt/deepa` copy: `cp -a /mnt/deepa/installed-software/<tool>/ ~/.cache/<tool>` |

## Logging

`/mnt/deepa/installed-software/migration.log` is JSON-line. Useful queries:

```bash
# Recent events
tail -20 /mnt/deepa/installed-software/migration.log | jq

# All session_start events
jq 'select(.event=="session_start")' /mnt/deepa/installed-software/migration.log

# All migrations and their sizes
jq 'select(.event=="migrate_start") | {src, size}' /mnt/deepa/installed-software/migration.log

# Last finalize event
jq 'select(.event=="finalize_complete") | .freed' /mnt/deepa/installed-software/migration.log | tail -1
```
