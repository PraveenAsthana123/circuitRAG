# CI drill suite — setup + branch-protection runbook

The `.github/workflows/drills.yml` workflow runs the §43 drill suite
on every PR + push to `main`/`develop` + on a nightly schedule. The
workflow files alone do **not** block bad merges; branch protection
is what turns the workflow checks into required-status gates.

This runbook is the one-time setup the repo admin runs after this
file lands.

---

## 1. Tier definitions (what runs in CI today)

Three resource tiers, declared via `# RESOURCES:` headers in each
drill file + filtered by `scripts/run_drills.py --allow-resources=...`.

| Tier | Workflow job | Drills | Infra | Wall (typical) |
|------|--------------|--------|-------|---------------|
| **1 — fast** | `drills-fast` | 15 | Python only | ~10s |
| **2 — pg** | `drills-pg` | 23 | + Postgres service container | ~30s with cold-start |
| **3 — stack** | _(not yet wired)_ | 60 | + docker-compose (MCP + inference + retrieval + Redis + Kafka) | ~5 min cold-start |

**Tier 1 covers:** baggage propagation, log formatter, Kafka inject/extract,
runner scheduler, eval gate, JWT contract, PII redaction, retrieval-side
breaker contract, etc.

**Tier 2 adds:** audit-log RLS + partitioning, audit-seal hash chain,
audit verifier, idempotency-key dedup, action-draft state constraints,
worker backlog metrics, etc.

**Tier 3 (deferred)** covers: every drill that hits a live MCP server
on `:8090`, the inference-svc on `:8084`, retrieval / qdrant, or
playwright-driven frontend drills. The scaffold via `--allow-resources`
makes adding it later mechanical:

```yaml
drills-stack:
  services:
    postgres:  { ... }
  steps:
    - name: docker compose up
      run: docker compose -f docker-compose.yml up -d --wait
    - name: Run full drill suite
      env:
        DOCUMIND_INFERENCE_URL: http://localhost:8084
        DOCUMIND_MCP_URL: http://localhost:8090
        # ...
      run: |
        python scripts/run_drills.py \
          --allow-resources=pg,inference,mcp_hr,mcp_drills,redis,kafka,qdrant,retrieval,playwright,frontend \
          --parallel 2 \
          --report junit=drill-results-stack.xml
```

---

## 2. Required branch-protection setup (one-time, by repo admin)

Per `~/.claude/CLAUDE.md` §43.7 + §15.2, drills are commit-discipline,
not opt-in CI. Wire them as **required status checks**:

### GitHub Settings → Branches → Add rule (or edit existing for `main`)

Required checks (search by job name):

- [x] **CI / python** *(existing)*
- [x] **CI / go** *(existing, matrix)*
- [x] **CI / frontend** *(existing)*
- [x] **CI / docker-build** *(existing)*
- [x] **Drills / Drills (zero infra)** ← **add**
- [x] **Drills / Drills (Postgres tier)** ← **add**

Other recommended toggles (per `~/.claude/CLAUDE.md` §15):

- [x] Require pull request reviews before merging (≥1 approval)
- [x] Dismiss stale approvals on new commits
- [x] Require linear history (squash + rebase merges only)
- [x] Require branches to be up to date before merging
- [x] Require status checks to pass before merging

Apply the same rule to `develop`. **Do NOT** check "Allow force pushes"
or "Allow deletions" on either protected branch.

---

## 3. Adding a new drill — checklist

Per `~/.claude/CLAUDE.md` §43.4, every new drill must:

1. Live under `mcp/tests/drill_*.py`.
2. Declare a `# RESOURCES: <tokens>` header at the top — the runner
   defaults to "touches everything" if the header is missing, which
   serializes the drill against every other and skips it in tier 1.
3. End with `ALL N STEPS PASSED` (exit 0) on success or red `✗ + exit 1`
   on failure.
4. Include at least one **negative assertion** (per §43.6) — what
   the drill *rejects*, not just what it *accepts*.

### Resource-tag vocabulary

| Token | Meaning |
|-------|---------|
| `none` / `readonly` | Pure in-process or read-only; tier 1 |
| `pg` | Reads / writes Postgres; tier 2 |
| `frontend` | Hits Next.js dev server (localhost:3000); tier 3 |
| `playwright` | Drives a browser via Playwright; tier 3 |
| `inference` | Hits inference-svc (localhost:8084); tier 3 |
| `mcp_hr` / `mcp_drills` | Hits an MCP server on `:8090` etc; tier 3 |
| `redis` / `kafka` / `qdrant` / `retrieval` | Tier 3 backing services |

The tier filter (`--allow-resources`) accepts a comma-separated list;
a drill is kept only when **every** resource it declares is in the
allow-list. Empty-set drills (`none` / `readonly`) always pass —
they're parallel-safe with everything.

Verify your tag locally:

```bash
# Should appear in the right tier:
python scripts/run_drills.py --allow-resources= --list  | grep my_drill   # tier 1
python scripts/run_drills.py --allow-resources=pg --list | grep my_drill  # tier 2
```

---

## 4. Reading drill failures in the GitHub UI

Both jobs upload a JUnit XML artifact (`drill-results-fast.xml` /
`drill-results-pg.xml`) regardless of pass/fail. To investigate a
failure:

1. Open the failed run on GitHub Actions.
2. Expand "Run zero-infra drills" (or the PG equivalent) — the runner
   prints per-drill check / cross markers + a "tail" of the failed
   drill's stderr after the summary banner.
3. Download the JUnit artifact for IDE-friendly viewing (most IDEs +
   test-result viewers parse JUnit XML).

Common failure shapes:

- **Pre-existing stale PG state** (rare in CI; service container is
  fresh per run). If a drill expects "no prior break rows" and finds
  some, the dev DB needs cleaning — does NOT affect CI.
- **Dep drift** — a `pip install` step pulled in a newer transitive
  that broke an OTel propagator import. Pin the offender in the
  install step or in `libs/py/pyproject.toml`.
- **Real regression** — a `# NEGATIVE FAILED:` row in the runner
  output. The drill caught a contract break. Read the assertion
  message for what changed.

---

## 5. Nightly drift-detection schedule

The workflow runs on `cron: "30 0 * * *"` (00:30 UTC daily). This
catches:

- Dep / image / OTel / structlog updates that quietly break a drill
  between PRs (no PR landed → no PR-time signal).
- Drills that depend on the current calendar month (e.g.
  `drill_audit_log_partitioned` bootstraps current + next-2 months
  partitions; on the 1st of each month a fresh CI cluster regresses
  if the helper's year-rollover broke).

If the nightly job fails on a date where no PR landed, treat it as a
**P2 regression** — open an issue with the run URL. The 30-min offset
from `:00` UTC reduces collision with other repos' cron jobs and
keeps GitHub Actions runner contention lower.

---

## 6. Adding tier 3 (`drills-stack`) later — TODO

The remaining ~60 drills exercise the live app stack. Wiring them
requires:

1. `docker compose up -d --wait` for postgres + kafka + redis + qdrant
   + the MCP servers + inference-svc + retrieval-svc + frontend.
2. Apply migrations + seed dev tenants.
3. Wait for `/health` + `/health/ready` on every service.
4. Run drills with `--allow-resources=pg,inference,mcp_hr,...,frontend,playwright`.
5. `docker compose down -v` cleanup.

Realistic CI cost: ~5 min cold-start + ~3 min drill wall = ~8 min
per run. Reasonable for nightly; expensive for every PR. Suggested
shape: nightly only, plus manual `workflow_dispatch` for operator
verification before risky merges.

---

## 7. Final checklist (one-time, by repo admin)

- [ ] Branch protection rule on `main` includes both new drill checks
- [ ] Branch protection rule on `develop` includes both new drill checks
- [ ] First nightly run completes successfully (visible on Actions tab the
  morning after this commit lands)
- [ ] `~/.claude/CLAUDE.md` §43 + §15 reviewed by team — drill discipline
  is committed culture, not just CI

After this checklist is green, the drill catalog is **enforced**, not
documentation. A future PR that breaks W3C baggage propagation, the
log formatter contract, or audit_log RLS fails the build without a
human noticing in review.
