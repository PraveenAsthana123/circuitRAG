# ADR-009: Worker auto-rejects drafts after N consecutive 4xx-shape failures

## Status

Accepted — implemented in commit `880022e`.

## Context

A draft with malformed arguments (missing required field, expired
tool target, schema-violating payload) returns
`ok=False, error.code=internal_error` from MCP on every replay. Pre-
this-decision, the worker logged "draft_replay_failed" and kept
retrying every backoff window. Forever. Audit log filled with the
same error every minute. No operator visibility, no terminal state.

The bug surfaced live during a drill run when the user asked "why
is MCP failing?" — the answer was "leftover drafts from earlier
runs have malformed arguments and the worker is loop-retrying
them." That symptom alone proves the gap.

## Decision

Worker tracks per-draft consecutive-failure count. After
`auto_reject_threshold` (default 5) consecutive failures, the draft
is auto-transitioned to 'rejected' via the same
`MCPClient.reject_draft` pipeline operators use. Audit row carries:

  actor_type = `"worker"`
  actor_id   = service-token `sub` (per ADR-007)
  reason     = "auto-rejected by worker after N consecutive
                failures; last error: {...}"

Threshold is heuristic. Set to 0 to disable (legacy behaviour: retry
forever). Drill step 5 proves disable works.

## Consequences

* Permanent-failure inputs get a terminal state — autonomous loop
  cannot retry forever.
* Bounded growth: `_consecutive_failures` only carries entries for
  drafts that have failed at least once AND are still pending.
  Auto-reject pops the entry on transition.
* `outcome="auto_rejected"` Prometheus label graph spikes show
  upstream regressions that poison every retry (e.g. a tool whose
  args validator changed, breaking every replay).
* The escape valve (threshold=0) matters more than it looks —
  during an incident where the upstream is flapping, you may
  *want* the worker to retry every two seconds because the next
  attempt might succeed. Hard-coded threshold = policy debt;
  env-tunable = policy seam.
* Pairs with the backlog-age gauge (commit `334917e`): the
  threshold catches FAST permanent-failure spikes; the gauge
  catches the SLOW leak where drafts hit cb_wait/skipped_backoff
  and never reach the threshold. Both belong; one isn't a
  substitute.
