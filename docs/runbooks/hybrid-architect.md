# Hybrid Architect — runbook

> Composes Hub-and-Spoke (`agent_cli.orchestrator`) + Council
> (`council_engine.orchestrator`) into one entrypoint, gated by
> `risk_classifier`. Per CLAUDE.md §47 (architecture & design
> patterns).

## Why

The reference enterprise pattern (per CLAUDE.md §47.1, "Recommended
Enterprise Flow"):

```
User Request
    ↓
Coordinator (Hub) — execution orchestration
    ↓
Specialist Agents — work
    ↓
Council of Agents — review (high-risk only)
    ↓
Decision Engine — composite verdict
    ↓
Human Approval (HITL) — critical-risk only
    ↓
Final Output
```

The Hub alone is fast but has a single decision-maker (governance
gap). The Council alone is rigorous but expensive on every request
(cost gap). The Hybrid uses each where it earns its keep:

| Risk tier | Lane | Hub | Council | HITL |
| --- | --- | --- | --- | --- |
| `low` | `hub_only` | ✅ | ❌ | ❌ |
| `medium` | `hub_council` | ✅ | ✅ (deep=False) | ❌ |
| `high` | `hub_council_deep` | ✅ | ✅ (deep=True) | ❌ |
| `critical` | `hub_council_deep_hitl` | ✅ | ✅ (deep=True) | ✅ flag |
| _unknown_ | `hub_council_deep_hitl` (safest) | ✅ | ✅ (deep=True) | ✅ flag |

Low-risk requests use a deterministic fast hub by default
(`HYBRID_ARCHITECT_FAST_LOW_RISK=1`). This keeps the audit/history row
but skips the four local Ollama calls used by the full hub pipeline.
Set `HYBRID_ARCHITECT_FAST_LOW_RISK=0` to force the full hub even for
low-risk requests.

## Use it

```python
from hybrid_architect import process

decision = process("deploy v1.2 to production")
print(decision.short())
# lane=hub_council_deep risk=high final=APPROVED hitl=False hist=HIST_...

if decision.requires_hitl:
    # Escalate to human approver — see ops_worker/notifier.py
    ...
```

`HybridDecision` carries: `request_id`, `risk_level`, `lane`,
`hub_final_answer`, `hub_approval`, `council_decision` (full
`CouncilDecision` dump or `None`), `final_decision`, `final_answer`,
`history_id`, `requires_hitl`, `elapsed_ms`.

## Cost-gates baked in

1. **Council never runs on `low` risk.** The user's reference
   warned about cost explosion from running every request through
   debate. Lane gate enforces this.
2. **Council never runs after a hub `DENY`.** Asking 3 LLM agents
   to debate a request that already failed the destructive-intent
   regex burns tokens for no decision delta. Drilled.
3. **Council `reject` / `escalate` overrides hub.** Hub's answer is
   suppressed in `final_answer` but **preserved in the audit row**
   for forensics (§51). Drilled.

## Day-1 governance

- **Forensic substrate (§51)**: every run persists to
  `safety_store` via `save_history(entity_type='hybrid_architect_run')`.
  `history_id` is returned in the decision; `git log` + this row
  reconstruct what was true at moment X.
- **Langfuse trace (§48 explainability)**: `process()` opens a
  `trace_context` covering the hub span + (when invoked) the
  council span. Offline-safe — no-op when Langfuse is down.
- **HITL flag (§38 governance)**: `requires_hitl=True` on critical
  lane is the explicit "human must approve" signal — downstream
  systems gate on this field.

## Drill — `mcp/tests/drill_hybrid_architect.py`

9 steps, **6 negative assertions**:

1. POSITIVE — `_pick_lane()` covers all 4 risk tiers
2. NEGATIVE — empty input raises `ValueError` BEFORE any LLM call
3. POSITIVE+NEG — low risk → `hub_only`, council fn NEVER invoked
4. NEGATIVE — critical risk → `hub_council_deep_hitl` +
   `requires_hitl=True`
5. NEGATIVE — hub DENY short-circuits, council NEVER invoked
6. NEGATIVE — council `reject` overrides hub, answer suppressed
7. POSITIVE — history row written + `HybridDecision` JSON-serializable
8. NEGATIVE — unknown risk defaults to safest lane
9. POSITIVE+NEGATIVE — fast low-risk path preserves audit and skips
   injected hub/council LLM calls

The drill uses dependency-injected stubs for the hub + council
functions so it doesn't need Ollama. The hub and council each have
their OWN LLM-touching drills:

- `mcp/tests/drill_council_engine.py` — council Phase 1+2 contract
- `mcp/tests/drill_council_rounds.py` — Phase 3-5 (deep mode)
- `mcp/tests/drill_safety_approval_council.py` — approval gate

Run:

```bash
python3 mcp/tests/drill_hybrid_architect.py
# ALL 9 STEPS PASSED
```

## Composes with

Per §49:

- [`agent_cli.orchestrator`](../../agent_cli/orchestrator.py) — the hub
- [`council_engine.orchestrator`](../../council_engine/orchestrator.py) — the council
- [`risk_classifier`](../../risk_classifier/__init__.py) — the lane gate
- [`approval_agent`](../../approval_agent/__init__.py) — already integrated by hub
- [`safety_store`](../../safety_store/__init__.py) — every run persists
- [`scripts/langfuse_tracer.py`](../../scripts/langfuse_tracer.py) — trace emission
- [`docs/runbooks/langfuse.md`](langfuse.md) — Langfuse runbook
- [`mcp/tests/drill_hybrid_architect.py`](../../mcp/tests/drill_hybrid_architect.py) — 9-step contract

## Brutal rule

> If a request hit the Hybrid Architect and you cannot answer, in
> minutes, "what lane did it take, what did the hub return, what did
> the council say, did HITL fire" — your composition is a black box
> regardless of how clean each component is. The audit row + Langfuse
> trace + drill negatives are the contract that keeps the composition
> honest.
