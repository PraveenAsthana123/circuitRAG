# Component 2 — Agent Runtime — source notes

## Files provided in source paste

- ✓ `types.ts` — `AgentTask`, `PlanStep`, `AgentPlan`, `ExecutionResult`
- ✓ `planner.ts` — `Planner.createPlan()`
- ✓ `executor.ts` — `Executor.execute()`
- ✓ `agent-runtime.ts` — `AgentRuntime.run()`

## File listed in folder layout but NOT provided

- ✗ **`model-client.ts`** — appears in the source's folder tree but no source
  code was shown. Probable intent: bridge between `Planner` / `Executor`
  and an LLM (likely Component 8's `LLMRouter`). The executor's empty
  `try` block — which currently has no statement that can throw — was
  probably meant to call `modelClient.complete(...)` for `action: "think"`
  steps and `modelClient.respond(...)` for `action: "respond"` steps.
- ✗ **No test file provided** — same source pattern; tests were shown
  for components 3-9 but not for 1 or 2.

## Behaviour gaps in the source as-given

| Observation | Impact |
|---|---|
| `Planner.createPlan()` returns a **hardcoded 2-step plan** | No real planning — same plan for any input |
| `Executor.execute()` `try` block contains only `results.push(...)` — no throw possible, so the `catch` is unreachable | The error-handling path is theatre; `success: true` is hardcoded |
| `action: "tool"` plan steps are defined in the type but **never routed** | If the planner ever emits a tool step, the executor ignores the action and treats it like any other |
| `AgentRuntime.run()` returns `string`, not `AgentResponse` from Component 1 | Type mismatch — Gateway can't actually call this without an adapter |
| No tool registry / no memory / no guardrails / no tracing | Component 2 cannot compose with components 3–8 as-shipped |

## What would make this Component 2 real

1. `model-client.ts` with at least one real provider call (delegated to
   Component 8's `LLMRouter` is the cleanest mapping)
2. `Planner` driven by the LLM — given the user input + available tools,
   ask the model to output a structured plan (JSON schema validation
   per CLAUDE.md §59.4)
3. `Executor` actually routes per `step.action`:
   - `think` → `modelClient.complete()`
   - `tool` → `toolDispatcher.dispatch()` (Component 3)
   - `respond` → produce final answer
4. Trace context (`requestId`, `tenantId`, `traceId`) threaded through
   `AgentTask` and propagated to every downstream call
5. Loop iteration limit (max planning rounds) to prevent runaway agents
6. Per-step guardrail evaluation (Component 5)
7. Per-step memory read/write (Component 4)

See `../GAPS.md` Component 2 row for severity-tagged version.
