# ADR-024: Stage-3 default-flip — best_config_loader default-on

## Status

Accepted — Stage-3 default-flip landed live 2026-05-05 after the
empirical loop produced verdict `earned` (19 promotions × 2 distinct
configs × 1.00 success ratio). Supersedes ADR-023's Stage-1 / Stage-2
default-deny posture.

## Context

ADR-023 documented the empirical RAG-config promotion loop with the
explicit gate that Stage-3 default-flip is **only** earned when:

- ≥ 10 promotion cycles in `.loop/best_config_history.jsonl`
- ≥ 0.80 success ratio (excluding skipped rows)
- ≥ 2 distinct winning configs (proves generalization, not overfitting)

The path from `stable_single_winner` to `earned` was documented in
`docs/runbooks/empirical-loop-stage3-promotion.md`. Two empirical
findings during that path drove this ADR:

1. **The simulated `run_rag` was deterministic given a config alone**
   (commit `93552d5` made it depend on question shape).
2. **The `is_specific` threshold was miscalibrated** for the actual
   gemma3:1b-generated question distribution (commit `ea56587`
   moved threshold from 8 → 13 words after observing live 9-21 word
   range).

After both fixes, `make empirical-stage3` returned:

```
verdict:        earned
rationale:      19 promotions over 2 distinct configs at success_ratio=1.00 ≥ 0.80
```

Per ADR-023's "alternatives considered" table:

> *Auto-flip Stage-3 default after first promotion* — REJECTED:
> §56.3 violation; one cycle is noise, not signal.

19 cycles is signal. Operator-driven flip is now justified.

## Decision

Flip `BEST_CONFIG_LOADER_ENABLED` default from off to ON in
`scripts/best_config_loader.py:50`. Operators opt OUT explicitly via
`BEST_CONFIG_LOADER_ENABLED=0`.

```python
# Before (ADR-023, default-deny):
BEST_CONFIG_LOADER_ENABLED = os.getenv("BEST_CONFIG_LOADER_ENABLED", "").strip() == "1"

# After (ADR-024, default-on):
_BEST_CONFIG_LOADER_RAW = os.getenv("BEST_CONFIG_LOADER_ENABLED", "1").strip()
BEST_CONFIG_LOADER_ENABLED = _BEST_CONFIG_LOADER_RAW != "0"
```

## Consequences

### Positive

- **Empirical winners propagate by default.** New deploys of
  inference-svc + retrieval-svc + ingestion-svc consume the
  best_config registry without operator opt-in. The 2026-05-05 winner
  (`min_score=0.5 / top_k=10 / rerank=False / chunking=recursive_paragraph_sentence`)
  is the live default.
- **§47 fail-safe still holds.** File missing/malformed → legacy
  un-tuned defaults (`min_score=0.0 / top_k=10 / rerank=False`).
  Operators who haven't run the empirical loop see no behavior change
  because there's no `.loop/best_config.json` for the loader to find.
- **Caller intent still wins.** The Stage-2 wires (commits `57a5ad0`
  + `2a939e6`) use Pydantic `model_fields_set` to distinguish
  caller-omitted from caller-default-passed fields. Explicit
  `min_score=0.0` (caller intentionally disabling the floor) is still
  honored — the loader only fills DEFAULTS, not overrides.
- **Operators retain explicit opt-out.** `BEST_CONFIG_LOADER_ENABLED=0`
  reverts to legacy un-tuned behavior in one env-flag flip. Useful
  during incident response or A/B testing.

### Negative

- **Behavior change for operators who already had `.loop/best_config.json`
  from Stage-2 testing but didn't set `BEST_CONFIG_LOADER_ENABLED=1`
  in their env.** Those callers will now see the empirical-tuned
  values where they previously saw legacy. Mitigation: explicit
  opt-out flag is the documented escape valve.
- **`stable_single_winner` verdict no longer blocks Stage-3.** Per the
  diversity check (commit `4a25c94`), single-winner is overfitting
  evidence. With this ADR, an operator can flip default-on EVEN IF
  diversity threshold isn't met — but they have to consciously do it
  by editing the loader source. The drill catches the new contract;
  the `earned` verdict is the qualifier.

### Risks accepted

- **A bad empirical winner now propagates by default.** If the empirical
  loop promotes a config that's wrong (e.g., min_score too high,
  filtering out useful chunks), it cascades to inference + retrieval
  defaults. Mitigation:
  - Promotion gate's three thresholds (pass_rate / margin / eval_set_size)
  - History append-only audit (`.loop/best_config_history.jsonl`)
  - `/api/v1/health/best-config` endpoints for operator visibility
  - Stage-3-earned diversity check (≥2 distinct configs)
  - Explicit opt-out env flag for incident response
- **Test environments without `.loop/best_config.json` see legacy
  defaults.** This is the intended fail-safe behavior. CI test runs
  that don't produce a best_config.json continue to use the
  un-tuned baseline.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep ADR-023 default-deny indefinitely | Operators run the loop, get the empirical winner, and have to manually set env flag in every deploy. Half-done feature. |
| Auto-flip default after first cycle | §56.3 violation: 1 cycle is noise. Same rejection as ADR-023. |
| Auto-flip after 5 cycles instead of 10 | Lower threshold = lower confidence. The 10-cycle floor came from §56.3 verbatim. |
| Default-on but require opt-IN per service | Adds 4 more env flags (one per consumer). Mitigation cost outweighs the explicit-control benefit when explicit opt-OUT already exists. |
| Schedule a background daemon that flips env once verdict=earned | Adds complexity (cron + state machine) that operator reading the file doesn't need. |

## Migration path

For an operator who has been using ADR-023's default-deny:

1. Pull latest. New default is on.
2. If you have `.loop/best_config.json` from prior empirical runs,
   the loader will start consuming it on next service restart.
3. If you DON'T want this — set `BEST_CONFIG_LOADER_ENABLED=0` in env.
4. Verify via `curl /api/v1/health/best-config` (both inference + retrieval).

## References

- `docs/architecture/adr/023-empirical-rag-config-promotion-loop.md`
  (superseded by this ADR)
- `docs/architecture/empirical-rag-config-loop.md` — chain overview
- `docs/runbooks/empirical-loop-stage3-promotion.md` — operator runbook
- CLAUDE.md `§38` `§43` `§47` `§56.3`

### Live verdict that triggered this flip

```
$ make empirical-stage3
verdict:        earned
rationale:      19 promotions over 2 distinct configs at success_ratio=1.00 ≥ 0.80
total attempts: 19
promoted:       19
distinct configs promoted: 2
cycles required: 10
```

### Commits in this transition

| Hash | Subject |
|---|---|
| `93552d5` | content-dependent simulated run_rag (unblocks --seed diversity) |
| `ea56587` | calibrate question-shape threshold to 13 words (was 8) |
| (this commit) | Stage-3 default-flip in best_config_loader; drill update |

## Composes with

- `§38` governance — every promotion logged with provenance
- `§43` drill discipline — `drill_best_config_loader_stage1` updated
- `§47` fail-safe — file missing → legacy defaults regardless of env
- `§54` no Co-Authored-By trailer
- `§56.3` Stage-3 default-flip earned-criteria
- `scripts/best_config_loader.py` — line 50 default change
- `scripts/stage3_earned_check.py` — meta-gate that produced verdict
- `docs/architecture/adr/023-empirical-rag-config-promotion-loop.md` — superseded
