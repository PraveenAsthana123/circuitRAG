# Issue dispatcher — local-model-assisted issue triage

> Operator runbook. Real signal sources (ruff/mypy/bandit) populate a
> checklist; deterministic auto-fix lane handles the bulk; local Ollama
> models propose fixes for medium-difficulty issues; security-flagged
> issues route to human review.
>
> Locked by `mcp/tests/drill_issue_dispatcher_format.py` (next iter).

## Why this exists

Scanning code for issues with an LLM produces unreliable lists. Real
deterministic tools (ruff, mypy, bandit) find concrete issues with
rule codes + line numbers. Local models then have a constrained job:
propose a fix for ONE specific rule violation. Drill verifies; commit
or escalate.

Pattern: **deterministic discovery + stochastic fix + deterministic
verification.**

## Components

| Component | Path | What it does |
| --- | --- | --- |
| Scanner | `scripts/issue_scanner.py` | Runs ruff; categorizes each issue by rule code → severity / difficulty / assignee; writes `.loop/issue_checklist.jsonl` |
| Dispatcher | `scripts/issue_dispatcher.py` | Reads checklist; routes per assignee (autofix vs local model vs human); supports dry-run / propose / apply |
| Audit | `.loop/issue_audit.jsonl` (gitignored) | One row per attempt: lane + outcome + tokens + latency |

## Routing table (rule code → assignee)

| Rule | Lane | Assignee |
| --- | --- | --- |
| `I001`, `F401`, `F403` | easy | `ruff:autofix` (deterministic) |
| `UP017`, `UP037`, `UP041`, `UP042` | easy | `ruff:autofix` |
| `W291`, `W292`, `W293` | easy | `ruff:autofix` |
| `E501` (line too long) | medium | `deepseek-coder:6.7b-instruct` |
| `E402` (import not at top) | medium | `deepseek-coder:6.7b-instruct` |
| `E711`, `E712`, `SIM102`, `SIM114` | medium | `deepseek-coder:6.7b-instruct` |
| `N806`, `N814`, `N999` (naming) | medium | `codegemma:7b-instruct` |
| `S110`, `S603`, `S607`, `S608` (security) | hard | `human-review` |

## Commands

### Generate the checklist

```bash
python3 scripts/issue_scanner.py
# Or include security findings (manual review):
python3 scripts/issue_scanner.py --include-security
```

### See what each lane would do (dry-run)

```bash
python3 scripts/issue_dispatcher.py
```

### Apply only the deterministic autofix lane

```bash
python3 scripts/issue_dispatcher.py --apply --only ruff:autofix
```

### Invoke a local model on ONE specific issue and print proposal

```bash
python3 scripts/issue_dispatcher.py --propose --id ruff-E402-__init__.py-L579
# Proposal printed to stdout; audit row written; nothing applied.
```

## Safety gates

1. **Default is dry-run.** `--apply` is explicit per invocation.
2. **Local-model proposals are NOT auto-applied.** Operator (or a
   future drill-gated apply step) reviews + applies.
3. **Security rules (`S*`) NEVER go to a model.** Always
   `human-review`. Hardcoded in `RULE_ROUTING`.
4. **Audit row per attempt.** `.loop/issue_audit.jsonl` records every
   lane invocation with outcome + tokens + latency.
5. **Apply step must run drill before commit** (planned: dispatcher
   `--apply --propose` chain integrates `scripts/run_drills.py`).

## Local Ollama models in use

| Model | Size | Used for |
| --- | --- | --- |
| `deepseek-coder:6.7b-instruct` | 3.8 GB | Line-length, import order, comparison style, simplification (E501, E402, E7xx, SIM*) |
| `codegemma:7b-instruct` | 5.0 GB | Naming conventions (N806, N814, N999) |

Choose a model not in this list by editing `RULE_ROUTING` in
`scripts/issue_scanner.py`. Available local inventory:

```bash
ollama list
```

## Empirically verified

`2026-04-30` first end-to-end invocation:

```
deepseek-coder:6.7b-instruct on ruff-E402-__init__.py-L579
  76 tokens, 36.9s
  Proposal: minimal unified diff (removal-only — INCORRECT for E402)
```

Lesson: the model proposed a removal where the correct fix is
relocation (move import to top). This is exactly why dry-run +
human-review is the default — the model is a proposal engine, not
an authoritative fixer. Drill-gated apply (planned) closes this.

## Failure modes & detection

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `missing .loop/issue_checklist.jsonl` | scanner not run | `python3 scripts/issue_scanner.py` |
| Ollama timeout (>120s) | model cold-loading | Wait + retry; first call after model swap is always slow |
| Proposal is malformed diff | small model misunderstood rule | Try a larger model OR escalate to `human-review` |
| Wrong fix applied | `--apply` used without review | Revert with `git checkout`; never apply local-model fixes blindly |

## Composes with

- `scripts/run_drills.py` — verification step (planned: `--apply --gate-on-drill`)
- `docs/runbooks/alertmanager-webhook.md` — same `.loop/<service>.env`
  + chmod 600 secret pattern (issue dispatcher does not need secrets;
  Ollama is local)
- `/admin/output-eval/deep` — citation discipline applies to fix
  proposals: every rule code cited must resolve to a real ruff rule
- `/admin/aiops/deep#autonomous-drift-detection` — ratchet pattern
  applies to issue counts: a regression in issue count past floor
  fires a watcher REJECT
- ADR-022 — convergent-work pattern: local-model proposals + ruff
  autofix can produce identical diffs; treat as convergence not bug

## Brutal rule

> Local models are proposal engines, not fixers. Without drill-gated
> apply + audit row + human review for security, the dispatcher is
> a faster way to break the codebase. The mechanism wins only when
> verification is as deterministic as discovery.
