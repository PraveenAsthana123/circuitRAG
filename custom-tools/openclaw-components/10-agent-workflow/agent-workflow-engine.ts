import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { RollbackManager } from "./rollback-manager";
import { ToolDispatcher } from "../03-tooling/tool-dispatcher";
import { ToolRequest, ToolErrorMeta } from "../03-tooling/types";
import { WorkflowMonitor } from "./workflow-monitor";
import {
  WorkflowContext,
  WorkflowState,
  WorkflowStep,
  RetryableError,
  StepErrorEnvelope,
  StepErrorCauseEnvelope,
  ReplanHistoryEntry,
} from "./types";

const cloneSteps = (steps: WorkflowStep[]): WorkflowStep[] =>
  steps.map((step) => ({ ...step }));

/**
 * Iter 60 (2026-05-17): redact common PII / secret patterns from an
 * error message string. Returns a NEW string with each match
 * replaced by `[REDACTED:<type>]`. Intentionally narrow — the engine
 * doesn't depend on the §04 SecretScanner (that would couple the
 * workflow engine to a different component's evolution). Instead
 * this catches the patterns most likely to appear in interpolated
 * error messages:
 *   - email address
 *   - JWT (header.payload.signature)
 *   - Bearer token (Authorization-header style)
 *   - AWS access key id prefix
 *   - Long contiguous digit runs (credit-card / account-number-ish)
 *
 * Real production should layer the §04 SecretScanner + a real
 * scanner (TruffleHog / gitleaks) for entropy-based detection.
 * This stub closes the obvious-pattern interpolation gap.
 *
 * Exported for the iter 60 drill — not part of the engine API.
 */
export function redactSensitiveMessage(msg: string | undefined): string | undefined {
  if (msg === undefined) return undefined;
  let out = msg;
  // Order matters: longer / more-specific patterns FIRST so a
  // JWT doesn't get partially eaten by the digit-run rule.
  out = out.replace(
    /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
    "[REDACTED:jwt]",
  );
  out = out.replace(
    /\bBearer\s+[A-Za-z0-9._\-]+/gi,
    "Bearer [REDACTED:bearer_token]",
  );
  out = out.replace(
    /\b(AKIA|ASIA)[A-Z0-9]{16}\b/g,
    "[REDACTED:aws_access_key]",
  );
  out = out.replace(
    // RFC-5322-lite email; deliberately strict on the local part to
    // avoid over-redacting normal words containing "@".
    /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
    "[REDACTED:email]",
  );
  out = out.replace(
    // 13-19 contiguous digits (with optional spaces/dashes between
    // groups of 4). Catches credit cards + long account numbers
    // without catching ordinary integers like 12345.
    /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}\b/g,
    "[REDACTED:digits]",
  );
  return out;
}

/**
 * Iter 59 (2026-05-17): redact absolute filesystem paths from a JS
 * stack trace while preserving function names and `:line:col`.
 *
 * Examples:
 *   "    at fn (/mnt/deepa/rag/.../engine.ts:42:10)"
 *     → "    at fn ([redacted]:42:10)"
 *   "    at fn (file:///home/p/proj/file.mjs:7:3)"
 *     → "    at fn ([redacted]:7:3)"
 *   "    at /tmp/x.mjs:5:9"             (anonymous, no parens)
 *     → "    at [redacted]:5:9"
 *   "    at runScriptInThisContext (node:internal/vm:209:10)"
 *     → unchanged (node:internal/* carries no host info)
 *
 * Exported for the iter 59 drill — not part of the public engine API.
 */
export function redactStackPaths(stack: string | undefined): string | undefined {
  if (stack === undefined) return undefined;
  return stack.split("\n").map((line) => {
    // node:internal pseudo-URLs reveal no host info — leave alone.
    if (line.includes("(node:") || /\bat\s+node:/.test(line)) return line;
    // Parenthesized form: "    at fn ((file:///)?/path/to/file.ts:LINE:COL)"
    // Capture trailing :digits:digits and replace the path inside parens.
    let redacted = line.replace(
      /\(((?:file:\/\/\/?)?[^()]+?)(:\d+:\d+)\)/g,
      "([redacted]$2)",
    );
    // Anonymous form: "    at /path/to/file.ts:LINE:COL"  (no parens)
    redacted = redacted.replace(
      /(\s+at\s+)((?:file:\/\/\/?)?(?:\/|[A-Za-z]:[\\/])[^\s()]+?)(:\d+:\d+)\s*$/,
      "$1[redacted]$3",
    );
    return redacted;
  }).join("\n");
}

const DEFAULT_MAX_STEP_OUTPUT_BYTES = 64 * 1024;
/** Iter 58: cap how many recovery_steps replan may insert per
 *  workflow. Without a cap, a recovery_step that itself fails will
 *  trigger ANOTHER recovery_step; the step list grows unboundedly
 *  and the workflow-state-store memory does too. Default 3 allows
 *  modest in-flight recovery (try → recovery → recovery → recovery)
 *  before declaring the workflow lost. */
const DEFAULT_MAX_RECOVERY_DEPTH = 3;
/** Iter 58: canonical name a replanned step gets. The replanner
 *  also uses this string; the engine counts steps with this name to
 *  enforce the cap. If you rename it in replanner.ts, update here. */
const RECOVERY_STEP_NAME = "recovery_step";

/** Iter 67 (2026-05-17): default attempt-rate-limit window settings.
 *  60 attempts / 60s = 1 attempt per second on average. The TOTAL
 *  count of recovery_steps is already capped (iter 58), but without
 *  a rate limit an attacker (or a misconfigured caller in a tight
 *  loop) can still hammer runNext() many times per second within
 *  that cap — wasting compute and producing thrashy logs. The
 *  window-based limit defends the workflow's near-term attempt rate
 *  ON TOP OF the long-term depth cap. */
const DEFAULT_MAX_ATTEMPTS_PER_WINDOW = 60;
const DEFAULT_ATTEMPT_WINDOW_MS = 60_000;

export interface AgentWorkflowEngineOptions {
  /** Real tool execution path. When supplied, runNext() dispatches
   *  selected workflow steps through Component 3 ToolDispatcher
   *  instead of the legacy simulateToolExecution hook. */
  toolDispatcher?: ToolDispatcher;
  /** Production guard: refuse construction unless toolDispatcher is
   *  supplied. Keeps local tests able to subclass simulateToolExecution
   *  while making production config fail closed. */
  requireRealToolDispatcher?: boolean;
  /** Optional monitoring/tracing adapter for workflow metrics and spans. */
  monitor?: WorkflowMonitor;
  /** Iter 56: cap persisted per-step output to defend in-memory state. */
  maxStepOutputBytes?: number;
  /** Iter 58: cap recovery-step replan depth per workflow. When the
   *  workflow already contains this many recovery_steps and another
   *  failure occurs, the engine does NOT replan again — it marks the
   *  workflow `failed` and stops. */
  maxRecoveryDepth?: number;
  /** Iter 59: redact host filesystem paths from lastError.stack
   *  before persisting. Default `true` because audit rows + operator
   *  UIs surface this field; leaking absolute paths reveals deploy
   *  layout to anyone reading the workflow. Set `false` in dev to
   *  preserve full debuggable stacks. Function names, line, and
   *  column are always preserved. */
  redactStackPaths?: boolean;
  /** Iter 60: redact common PII / secret patterns from
   *  lastError.message before persisting (email, JWT, Bearer token,
   *  AWS access key, credit-card-length digit runs). Default
   *  `true` — error messages routinely embed user input via
   *  template-literal interpolation. Set `false` only when the
   *  consumer is trusted + the redaction false-positive rate
   *  becomes a debugging burden. */
  redactMessages?: boolean;
  /** Iter 67 (2026-05-17): sliding-window rate limit on runNext()
   *  attempts per workflow. When this many attempts occur within
   *  `attemptWindowMs`, the next attempt throws WorkflowRateLimitedError
   *  rather than running the step. Default 60 attempts / 60_000 ms.
   *  Composes with the iter 58 recovery-depth cap: depth caps the
   *  LIFETIME number of replans; this caps the SHORT-TERM rate of
   *  any runNext() call (retry, replan, ordinary advance) so a tight
   *  loop cannot exhaust compute even within the lifetime budget.
   *  Constructor rejects values < 1. */
  maxAttemptsPerWindow?: number;
  /** Iter 67: window length in ms for `maxAttemptsPerWindow`.
   *  Constructor rejects values < 1. */
  attemptWindowMs?: number;
}

export class StepOutputTooLargeError extends Error {
  constructor(sizeBytes: number, maxBytes: number) {
    super(`Step output is ${sizeBytes} bytes; limit is ${maxBytes} bytes`);
    this.name = "StepOutputTooLargeError";
  }
}

/** Iter 58: raised internally when the recovery cap is hit. Surfaces
 *  on the failed step's lastError so operator can see "we gave up
 *  retrying recovery" rather than just "workflow failed". */
export class RecoveryDepthExceededError extends Error {
  constructor(depth: number, max: number) {
    super(`Recovery depth ${depth} exceeds max ${max}; workflow abandoned`);
    this.name = "RecoveryDepthExceededError";
  }
}

/** Iter 67: raised when a workflow's runNext() rate exceeds the
 *  configured sliding-window cap. The workflow id is in the message
 *  so the audit log (and the caller's catch block) can pin down
 *  WHICH workflow tripped the limit — without it, an operator
 *  watching aggregated logs cannot localize a misbehaving caller.
 *  This error does NOT touch the workflow state — the workflow
 *  remains in whatever status it had; the caller must back off and
 *  retry later (or escalate). */
export class WorkflowRateLimitedError extends Error {
  public readonly workflowId: string;
  public readonly maxAttemptsPerWindow: number;
  public readonly attemptWindowMs: number;
  constructor(workflowId: string, max: number, windowMs: number) {
    super(
      `Workflow ${workflowId} exceeded rate limit ` +
      `(${max} attempts per ${windowMs} ms)`,
    );
    this.name = "WorkflowRateLimitedError";
    this.workflowId = workflowId;
    this.maxAttemptsPerWindow = max;
    this.attemptWindowMs = windowMs;
  }
}

/**
 * Iter M1.1 (2026-05-18): synthetic Error wrapper that turns a
 * ToolErrorMeta into an Error.cause chain that toErrorEnvelope's
 * existing recursive traversal already handles. Pre-fix the engine
 * threw `new Error(result.error)` which lost class + stack + cause
 * because ToolResult only carried a string `error` field. Iter M1.1
 * added ToolResult.errorMeta and this class is the bridge from that
 * meta into the StepErrorEnvelope.cause field already wired by
 * toCauseEnvelope.
 */
class SyntheticToolCause extends Error {
  constructor(meta: ToolErrorMeta) {
    super(meta.message);
    this.name = meta.name;
    if (meta.stack !== undefined) {
      this.stack = meta.stack;
    }
    if (meta.cause !== undefined) {
      // Recursively wrap nested causes. Bounded by JS engine + our
      // own cause shape (1 level deep at the schema layer); deeper
      // chains from real tools also serialize fine because each
      // SyntheticToolCause is a real Error with .cause.
      (this as Error & { cause?: Error }).cause = new SyntheticToolCause({
        name: meta.cause.name,
        message: meta.cause.message,
        stack: meta.cause.stack,
      });
    }
  }
}

export class ToolDispatchFailedError extends Error {
  public readonly toolName: string;
  constructor(toolName: string, message: string, meta?: ToolErrorMeta) {
    super(message);
    this.name = "ToolDispatchFailedError";
    this.toolName = toolName;
    if (meta !== undefined) {
      // ES2022 cause chain — toCauseEnvelope walks this automatically.
      (this as Error & { cause?: Error }).cause = new SyntheticToolCause(meta);
    }
  }
}

/**
 * Iter 55 (2026-05-17): read-only view of prior completed steps'
 * outputs, passed into simulateToolExecution so a step can chain
 * off upstream results (e.g. fetch-then-summarize). Stale outputs
 * from retried/replanned steps are excluded — only `completed`
 * steps before currentStepIndex appear.
 */
export interface StepOutputContext {
  /** Output of an upstream completed step, by name. undefined if no
   *  such step has completed yet. */
  getByName(stepName: string): unknown;
  /** Output of an upstream completed step, by stepId. undefined if
   *  no such step has completed yet. */
  getById(stepId: string): unknown;
}

export class AgentWorkflowEngine {
  private readonly rollbackManager: RollbackManager;
  /** Iter 67: per-workflow sliding window of runNext() attempt
   *  timestamps (epoch ms). Keys are workflowIds; values are
   *  monotonically-appended timestamps trimmed each time the
   *  window slides. Different workflows have independent windows. */
  private readonly attemptsByWorkflow = new Map<string, number[]>();

  constructor(
    private readonly planner: WorkflowPlanner,
    private readonly replanner: Replanner,
    private readonly toolSelector: ToolSelector,
    private readonly approvalGate: HumanApprovalGate,
    private readonly store: WorkflowStateStore,
    private readonly options: AgentWorkflowEngineOptions = {},
  ) {
    this.rollbackManager = new RollbackManager(store);
    if (this.options.requireRealToolDispatcher && !this.options.toolDispatcher) {
      throw new Error("AgentWorkflowEngine requires a real ToolDispatcher in production mode");
    }
    const maxBytes = this.maxStepOutputBytes();
    if (!Number.isFinite(maxBytes) || maxBytes < 0) {
      throw new Error("maxStepOutputBytes must be a non-negative finite number");
    }
    const maxDepth = this.maxRecoveryDepth();
    if (!Number.isInteger(maxDepth) || maxDepth < 0) {
      throw new Error("maxRecoveryDepth must be a non-negative integer");
    }
    // Iter 67: validate the rate-limit settings at construction so a
    // misconfiguration is loud at startup, not silent until the
    // first runNext() call. Both must be >= 1 — zero or negative
    // would either lock the workflow out forever (max==0) or make
    // the window meaningless (windowMs <= 0).
    const maxAttempts = this.maxAttemptsPerWindow();
    if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
      throw new Error("maxAttemptsPerWindow must be a positive integer (>= 1)");
    }
    const windowMs = this.attemptWindowMs();
    if (!Number.isInteger(windowMs) || windowMs < 1) {
      throw new Error("attemptWindowMs must be a positive integer (>= 1)");
    }
  }

  start(context: WorkflowContext, userGoal: string): WorkflowState {
    const state = this.planner.createPlan(context, userGoal);

    this.store.save({
      ...state,
      status: "planning",
    });

    console.log(JSON.stringify({
      type: "workflow_started",
      workflowId: context.workflowId,
      requestId: context.requestId,
      tenantId: context.tenantId,
      stepCount: state.steps.length,
      traceId: context.traceId,
      timestamp: new Date().toISOString(),
    }));
    this.options.monitor?.workflowStarted(context, state.steps.length);

    return state;
  }

  async runNext(workflowId: string, callerTenantId: string): Promise<WorkflowState> {
    // tenantId required for §47 multi-tenant isolation; the store
    // throws WorkflowAccessDeniedError if it doesn't match.
    const state = this.store.get(workflowId, callerTenantId);

    // Iter 67: sliding-window rate-limit check. The window is the
    // most recent `attemptWindowMs` ms; if `maxAttemptsPerWindow`
    // attempts already fell inside it, the next attempt is
    // rejected. Append the current timestamp AFTER the check so
    // the rejected attempt does NOT itself count toward the budget
    // (otherwise the window would never drain on a hot loop).
    // The check runs AFTER store.get on purpose: an unauthorized
    // caller (wrong tenantId) gets WorkflowAccessDeniedError, NOT a
    // rate-limit message — auth failure must remain the loudest
    // signal a misconfigured caller sees.
    const now = Date.now();
    const windowMs = this.attemptWindowMs();
    const maxAttempts = this.maxAttemptsPerWindow();
    const cutoff = now - windowMs;
    const recent = (this.attemptsByWorkflow.get(workflowId) ?? [])
      .filter((t) => t >= cutoff);
    if (recent.length >= maxAttempts) {
      throw new WorkflowRateLimitedError(workflowId, maxAttempts, windowMs);
    }
    recent.push(now);
    this.attemptsByWorkflow.set(workflowId, recent);

    const step = state.steps[state.currentStepIndex];

    if (!step) {
      const completed = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "completed" as const,
      };
      this.store.save(completed);
      return completed;
    }

    if (step.requiresApproval) {
      this.approvalGate.requestApproval(state.context, step);

      const waiting = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "awaiting_approval" as const,
      };

      this.store.save(waiting);
      return waiting;
    }

    const toolName = this.toolSelector.select(step);
    const monitorStartedAt = Date.now();
    const monitorSpan = this.options.monitor?.stepStarted(
      state.context,
      step,
      toolName,
    );

    // Iter 55: build the read-only output context for THIS step.
    // Only completed upstream steps contribute; retried steps with
    // status reset to "pending" automatically vanish from the lookup.
    const outputContext = this.buildOutputContext(state.steps, state.currentStepIndex);

    try {
      console.log(JSON.stringify({
        type: "workflow_step_started",
        workflowId,
        stepId: step.stepId,
        stepName: step.name,
        selectedTool: toolName,
        traceId: state.context.traceId,
        timestamp: new Date().toISOString(),
      }));

      // ✅ P1 FIXED (2026-05-17): persist `running` BEFORE awaiting
      // the tool. Pre-fix: status was mutated but not saved; a crash
      // mid-tool left the step looking `pending` on restart and it
      // would run twice. Now the running state is durable.
      step.status = "running";
      this.store.save({
        ...state,
        steps: cloneSteps(state.steps),
        status: "executing" as const,
      });

      const result = await this.executeSelectedTool(toolName, outputContext, step, state);
      const outputSizeBytes = this.measureOutputBytes(result);
      if (outputSizeBytes > this.maxStepOutputBytes()) {
        throw new StepOutputTooLargeError(outputSizeBytes, this.maxStepOutputBytes());
      }

      step.status = "completed";
      // Iter 55: persist the tool's return value so a downstream
      // step's outputContext.getByName(step.name) can read it.
      // Iter 56: output was measured before assignment, so oversized
      // values fail the step before they enter persisted workflow state.
      step.output = result;
      step.outputSizeBytes = outputSizeBytes;
      // Iter 57: success path clears any stale error from a prior
      // retried attempt — the final state of the step is "completed
      // with no error", not "completed with a leftover error".
      step.lastError = undefined;
      this.options.monitor?.stepSucceeded(
        state.context,
        step,
        toolName,
        Date.now() - monitorStartedAt,
        outputSizeBytes,
      );
      monitorSpan?.end("ok", { outputSizeBytes });

      const nextState = {
        ...state,
        steps: cloneSteps(state.steps),
        status: "executing" as const,
        currentStepIndex: state.currentStepIndex + 1,
      };

      this.store.save(nextState);

      return nextState;
    } catch (error) {
      // Iter 44: distinguish transient (retryable) from permanent.
      const isRetryable = error instanceof RetryableError;
      const currentRetries = step.retryCount ?? 0;
      const maxRetries = step.maxRetries ?? 0;

      if (isRetryable && currentRetries < maxRetries) {
        this.options.monitor?.stepFailed(
          state.context,
          step,
          toolName,
          Date.now() - monitorStartedAt,
          true,
          "retry",
        );
        monitorSpan?.end("error", { outcome: "retry" });
        step.retryCount = currentRetries + 1;
        step.status = "pending"; // ready for the next runNext() call
        // Iter 55: a retried step has no valid output yet — clear any
        // stale value so the rerun's outputContext cannot read a
        // failed-and-retried sibling's leftover data.
        step.output = undefined;
        step.outputSizeBytes = undefined;
        // Iter 57: capture the error envelope so audit / debugging /
        // operator UI can see WHY the retry happened. Overwritten on
        // every retry attempt, cleared on success, preserved through
        // replan on the permanent path.
        step.lastError = this.toErrorEnvelope(error, true);
        const retryState = {
          ...state,
          steps: cloneSteps(state.steps),
          status: "executing" as const,
        };
        this.store.save(retryState);

        console.warn(JSON.stringify({
          type: "workflow_step_retry",
          workflowId,
          stepId: step.stepId,
          retryCount: step.retryCount,
          maxRetries,
          error: error.message,
          traceId: state.context.traceId,
          timestamp: new Date().toISOString(),
        }));

        return retryState;
      }

      // Non-retryable OR exhausted → replan.
      step.status = "failed";
      // Iter 55: a failed step has no valid output.
      step.output = undefined;
      step.outputSizeBytes = undefined;
      // Iter 57: attach error envelope BEFORE replan so the
      // replanner's `{...failedStep, status: "failed"}` copy carries
      // it through to the final state. Operator UI sees lastError
      // on the failed step even after the recovery step has run.
      step.lastError = this.toErrorEnvelope(error, isRetryable);

      // Iter 58: cap recovery depth. Count recovery_steps in the
      // CURRENT plan; if at/above cap, abandon the workflow rather
      // than inserting yet another doomed recovery_step. The just-
      // failed step's lastError is overwritten with a
      // RecoveryDepthExceededError so the audit row makes the
      // STOP-REASON visible (not just "permanent fail").
      const existingRecoveryCount = state.steps.filter(
        (s) => s.name === RECOVERY_STEP_NAME,
      ).length;
      if (existingRecoveryCount >= this.maxRecoveryDepth()) {
        this.options.monitor?.stepFailed(
          state.context,
          step,
          toolName,
          Date.now() - monitorStartedAt,
          isRetryable,
          "abandon",
        );
        monitorSpan?.end("error", { outcome: "abandon" });
        const giveUp = new RecoveryDepthExceededError(
          existingRecoveryCount,
          this.maxRecoveryDepth(),
        );
        step.lastError = this.toErrorEnvelope(giveUp, false);
        // Iter 66: even though we are abandoning, this IS a replan
        // event in the audit sense — the workflow tried to recover
        // and gave up. Operator must see "we gave up at depth N"
        // as the final entry in replanHistory, not just on the
        // failed step's lastError. retryable: false by construction
        // (RecoveryDepthExceededError is not retryable).
        const abandonEntry: ReplanHistoryEntry = {
          timestamp: new Date().toISOString(),
          failedStepId: step.stepId,
          failedStepName: step.name,
          errorName: step.lastError.name,
          errorMessage: step.lastError.message,
          retryable: false,
          recoveryDepthAtTime: existingRecoveryCount,
        };
        const abandonedHistory: ReplanHistoryEntry[] = [
          ...(state.replanHistory ?? []),
          abandonEntry,
        ];
        const abandoned = {
          ...state,
          steps: cloneSteps(state.steps),
          status: "failed" as const,
          replanHistory: abandonedHistory,
        };
        this.store.save(abandoned);
        console.warn(JSON.stringify({
          type: "workflow_abandoned",
          workflowId,
          stepId: step.stepId,
          recoveryDepth: existingRecoveryCount,
          maxRecoveryDepth: this.maxRecoveryDepth(),
          reason: giveUp.message,
          traceId: state.context.traceId,
          timestamp: new Date().toISOString(),
        }));
        return abandoned;
      }

      // Iter 66: record a replan-history entry BEFORE handing state
      // to the replanner. Replanner preserves replanHistory via
      // `...state` spread, so the entry rides through to the final
      // saved state. recoveryDepthAtTime captures the depth BEFORE
      // this replan adds a new recovery_step (i.e. how many recovery
      // attempts had ALREADY happened when this failure occurred).
      this.options.monitor?.stepFailed(
        state.context,
        step,
        toolName,
        Date.now() - monitorStartedAt,
        isRetryable,
        "replan",
      );
      monitorSpan?.end("error", { outcome: "replan" });

      const replanEntry: ReplanHistoryEntry = {
        timestamp: new Date().toISOString(),
        failedStepId: step.stepId,
        failedStepName: step.name,
        errorName: step.lastError ? step.lastError.name
          : (error instanceof Error ? error.name : "NonError"),
        errorMessage: step.lastError ? step.lastError.message
          : (error instanceof Error ? error.message : "Unknown error"),
        retryable: isRetryable,
        recoveryDepthAtTime: existingRecoveryCount,
      };
      const enrichedHistory: ReplanHistoryEntry[] = [
        ...(state.replanHistory ?? []),
        replanEntry,
      ];

      const replanned = this.replanner.replan(
        {
          ...state,
          steps: cloneSteps(state.steps),
          status: "failed",
          replanHistory: enrichedHistory,
        },
        error instanceof Error ? error.message : "Unknown error"
      );

      this.store.save(replanned);

      return replanned;
    }
  }

  rollback(workflowId: string, callerTenantId: string, reason: string): WorkflowState {
    // tenantId required for §47 multi-tenant isolation.
    return this.rollbackManager.rollback(workflowId, callerTenantId, reason);
  }

  // Protected so a test subclass can override to simulate retryable
  // vs permanent failures. Real production replaces this entirely
  // with a Component 3 ToolDispatcher.dispatch() call.
  //
  // Iter 55: now returns the tool's result (unknown). The engine
  // persists it on the step so downstream steps can read it via
  // the StepOutputContext passed in `context`. The default impl
  // returns undefined to preserve pre-iter-55 behavior.
  protected async simulateToolExecution(
    toolName: string,
    _context: StepOutputContext,
    _step: WorkflowStep,
  ): Promise<unknown> {
    if (!toolName) {
      throw new Error("No tool selected");
    }
    return undefined;
  }

  private async executeSelectedTool(
    toolName: string,
    outputContext: StepOutputContext,
    step: WorkflowStep,
    state: WorkflowState,
  ): Promise<unknown> {
    if (!this.options.toolDispatcher) {
      return this.simulateToolExecution(toolName, outputContext, step);
    }

    const result = await this.options.toolDispatcher.dispatch(
      this.toToolRequest(toolName, step, state),
    );
    if (!result.success) {
      // Iter M1.1 (2026-05-18): preserve the dispatcher's structured
      // error metadata via Error.cause so toCauseEnvelope picks it up.
      // Pre-fix: bare `new Error(result.error)` lost the class name,
      // stack, and any underlying cause chain. Now a ToolDispatch-
      // FailedError carries the dispatcher's ToolErrorMeta as a
      // synthetic Error-like cause; toErrorEnvelope's existing
      // recursive cause traversal flattens it into StepErrorEnvelope.
      throw new ToolDispatchFailedError(
        toolName,
        result.error ?? `Tool dispatch failed: ${toolName}`,
        result.errorMeta,
      );
    }
    return result.output;
  }

  private toToolRequest(
    toolName: string,
    step: WorkflowStep,
    state: WorkflowState,
  ): ToolRequest {
    return {
      toolName,
      input: {
        workflowId: state.context.workflowId,
        stepId: step.stepId,
        stepName: step.name,
        goal: step.goal,
        previousOutputs: this.completedOutputsBeforeCurrentStep(state),
      },
      context: {
        requestId: state.context.requestId,
        sessionId: state.context.sessionId ?? state.context.workflowId,
        userId: state.context.userId,
        tenantId: state.context.tenantId,
        traceId: state.context.traceId,
        roles: state.context.roles,
      },
      idempotencyKey: `${state.context.workflowId}:${step.stepId}:${step.retryCount ?? 0}`,
    };
  }

  private completedOutputsBeforeCurrentStep(state: WorkflowState): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const step of state.steps.slice(0, state.currentStepIndex)) {
      if (step.status === "completed") {
        out[step.name] = step.output;
      }
    }
    return out;
  }

  private maxStepOutputBytes(): number {
    return this.options.maxStepOutputBytes ?? DEFAULT_MAX_STEP_OUTPUT_BYTES;
  }

  private maxRecoveryDepth(): number {
    return this.options.maxRecoveryDepth ?? DEFAULT_MAX_RECOVERY_DEPTH;
  }

  private maxAttemptsPerWindow(): number {
    return this.options.maxAttemptsPerWindow ?? DEFAULT_MAX_ATTEMPTS_PER_WINDOW;
  }

  private attemptWindowMs(): number {
    return this.options.attemptWindowMs ?? DEFAULT_ATTEMPT_WINDOW_MS;
  }

  // Iter 57: normalize anything thrown into the persisted error
  // envelope. Non-Error throws ("string", numbers, undefined) are
  // common in JS — the catch block must NOT crash when stack/message
  // are absent.
  // Iter 59: stack is redacted by default to hide host filesystem
  // layout from anyone who can read the persisted envelope.
  private toErrorEnvelope(thrown: unknown, retryable: boolean): StepErrorEnvelope {
    const now = new Date().toISOString();
    if (thrown instanceof Error) {
      const rawMessage = thrown.message;
      return {
        name: thrown.name,
        // Iter 60: sanitize before persisting. Sanitizer is pure on
        // strings and undefined-safe — applies to both Error and
        // NonError branches.
        message: this.shouldRedactMessage()
          ? (redactSensitiveMessage(rawMessage) ?? rawMessage)
          : rawMessage,
        stack: this.shouldRedactStack() ? redactStackPaths(thrown.stack) : thrown.stack,
        cause: this.toCauseEnvelope(thrown.cause),
        retryable,
        timestamp: now,
      };
    }
    const rawNonErrorMessage =
      typeof thrown === "string" ? thrown : JSON.stringify(thrown ?? null);
    return {
      name: "NonError",
      message: this.shouldRedactMessage()
        ? (redactSensitiveMessage(rawNonErrorMessage) ?? rawNonErrorMessage)
        : rawNonErrorMessage,
      retryable,
      timestamp: now,
    };
  }

  private toCauseEnvelope(cause: unknown): StepErrorCauseEnvelope | undefined {
    if (cause === undefined) return undefined;
    if (cause instanceof Error) {
      return {
        name: cause.name,
        message: this.shouldRedactMessage()
          ? (redactSensitiveMessage(cause.message) ?? cause.message)
          : cause.message,
        stack: this.shouldRedactStack() ? redactStackPaths(cause.stack) : cause.stack,
        cause: this.toCauseEnvelope(cause.cause),
      };
    }
    const raw = typeof cause === "string" ? cause : JSON.stringify(cause ?? null);
    return {
      name: "NonError",
      message: this.shouldRedactMessage()
        ? (redactSensitiveMessage(raw) ?? raw)
        : raw,
    };
  }

  private shouldRedactStack(): boolean {
    return this.options.redactStackPaths ?? true;
  }

  private shouldRedactMessage(): boolean {
    return this.options.redactMessages ?? true;
  }

  private measureOutputBytes(output: unknown): number {
    if (output === undefined) return 0;

    let serialized: string;
    try {
      serialized = JSON.stringify(output);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      throw new Error(`Step output must be JSON-serializable: ${message}`);
    }

    if (serialized === undefined) return 0;
    return Buffer.byteLength(serialized, "utf8");
  }

  // Iter 55: build the read-only output view passed to a tool. Only
  // steps strictly before `currentStepIndex` with status === "completed"
  // contribute — pending / running / failed / skipped steps are
  // invisible, and a step cannot see its own output (lookup is
  // by upstream completed steps only).
  private buildOutputContext(
    steps: WorkflowStep[],
    currentStepIndex: number,
  ): StepOutputContext {
    const upstream = steps.slice(0, currentStepIndex).filter(
      (s) => s.status === "completed",
    );
    return {
      getByName(stepName: string): unknown {
        const hit = upstream.find((s) => s.name === stepName);
        return hit ? hit.output : undefined;
      },
      getById(stepId: string): unknown {
        const hit = upstream.find((s) => s.stepId === stepId);
        return hit ? hit.output : undefined;
      },
    };
  }
}
