import { JobScheduler, ScheduledJob } from "./job-scheduler";
import { WorkflowDelegator } from "./workflow-delegator";
import { MetricsRecorder } from "../06-observability/metrics";
import { Tracer } from "../06-observability/tracer";

export type AgentSupervisorStatus = "cold" | "warming" | "ready" | "degraded" | "stopped";
export type AgentNotificationSeverity = "info" | "warning" | "error" | "critical";

export interface AgentNotification {
  type: string;
  severity: AgentNotificationSeverity;
  message: string;
  timestampMs: number;
  metadata: Record<string, unknown>;
}

export interface AgentNotifier {
  notify(event: AgentNotification): void;
}

export class InMemoryAgentNotifier implements AgentNotifier {
  readonly events: AgentNotification[] = [];

  notify(event: AgentNotification): void {
    this.events.push({ ...event, metadata: { ...event.metadata } });
  }
}

export interface AgentSupervisorOptions {
  scheduler?: JobScheduler;
  notifier?: AgentNotifier;
  metrics?: MetricsRecorder;
  tracer?: Tracer;
  now?: () => number;
  heartbeatEveryMs?: number;
  heartbeatStaleAfterMs?: number;
  readinessProbe?: () => Promise<boolean>;
  warmup?: () => Promise<void>;
  runWorkflowOnTick?: boolean;
}

export interface AgentSupervisorSnapshot {
  status: AgentSupervisorStatus;
  started: boolean;
  lastHeartbeatMs?: number;
  lastWarmupMs?: number;
  lastError?: string;
}

const SYSTEM_TENANT = "system";
const HEARTBEAT_JOB = "agent.heartbeat";
const WARMUP_JOB = "agent.warmup";

export class AgentSupervisor {
  private readonly scheduler: JobScheduler;
  private readonly notifier: AgentNotifier;
  private readonly metrics: MetricsRecorder;
  private readonly tracer: Tracer;
  private readonly now: () => number;
  private readonly heartbeatEveryMs: number;
  private readonly heartbeatStaleAfterMs: number;
  private readonly readinessProbe: () => Promise<boolean>;
  private readonly warmupFn: () => Promise<void>;
  private readonly runWorkflowOnTick: boolean;
  private status: AgentSupervisorStatus = "cold";
  private started = false;
  private lastHeartbeatMs: number | undefined;
  private lastWarmupMs: number | undefined;
  private lastError: string | undefined;

  constructor(
    private readonly delegator: WorkflowDelegator,
    options: AgentSupervisorOptions = {},
  ) {
    this.scheduler = options.scheduler ?? new JobScheduler();
    this.notifier = options.notifier ?? new InMemoryAgentNotifier();
    this.metrics = options.metrics ?? new MetricsRecorder();
    this.tracer = options.tracer ?? new Tracer();
    this.now = options.now ?? (() => Date.now());
    this.heartbeatEveryMs = options.heartbeatEveryMs ?? 15_000;
    this.heartbeatStaleAfterMs = options.heartbeatStaleAfterMs ?? this.heartbeatEveryMs * 3;
    this.readinessProbe = options.readinessProbe ?? (async () => true);
    this.warmupFn = options.warmup ?? (async () => undefined);
    this.runWorkflowOnTick = options.runWorkflowOnTick ?? true;

    if (!Number.isInteger(this.heartbeatEveryMs) || this.heartbeatEveryMs < 1) {
      throw new Error("heartbeatEveryMs must be a positive integer");
    }
    if (!Number.isInteger(this.heartbeatStaleAfterMs) || this.heartbeatStaleAfterMs < this.heartbeatEveryMs) {
      throw new Error("heartbeatStaleAfterMs must be >= heartbeatEveryMs");
    }
  }

  start(): ScheduledJob {
    if (this.started) {
      return this.scheduler.schedule({
        tenantId: SYSTEM_TENANT,
        type: HEARTBEAT_JOB,
        payload: {},
        recurringEveryMs: this.heartbeatEveryMs,
        idempotencyKey: HEARTBEAT_JOB,
      });
    }

    this.started = true;
    this.status = "warming";
    this.notify("agent.starting", "info", "Agent supervisor starting", {});
    this.metrics.counter("agent_supervisor_started_total", 1, { component: "agent_supervisor" });

    this.scheduler.schedule({
      tenantId: SYSTEM_TENANT,
      type: WARMUP_JOB,
      payload: {},
      priority: 100,
      maxAttempts: 3,
      baseBackoffMs: 250,
      maxBackoffMs: 2_000,
      idempotencyKey: WARMUP_JOB,
    });

    return this.scheduler.schedule({
      tenantId: SYSTEM_TENANT,
      type: HEARTBEAT_JOB,
      payload: {},
      priority: 50,
      recurringEveryMs: this.heartbeatEveryMs,
      idempotencyKey: HEARTBEAT_JOB,
    });
  }

  stop(reason = "operator stop"): void {
    this.status = "stopped";
    this.started = false;
    this.notify("agent.stopped", "warning", "Agent supervisor stopped", { reason });
    this.metrics.counter("agent_supervisor_stopped_total", 1, { component: "agent_supervisor" });
  }

  async runTick(limit?: number): Promise<void> {
    const span = this.tracer.startSpan("agent.supervisor_tick", {
      component: "agent_supervisor",
      status: this.status,
    });
    try {
      if (!this.started) this.start();
      const supervisorResult = await this.scheduler.runDue(async (job) => this.runSupervisorJob(job), limit);
      if (supervisorResult.failed > 0 || supervisorResult.deadLettered > 0) {
        this.markDegraded(new Error("Supervisor control job failed"));
      }
      if (this.runWorkflowOnTick) {
        await this.delegator.runDue(limit);
      }
      this.checkHeartbeatFreshness();
      span.end("ok", { status: this.status });
    } catch (error) {
      this.markDegraded(error);
      span.end("error", { error: this.lastError });
      throw error;
    }
  }

  snapshot(): AgentSupervisorSnapshot {
    return {
      status: this.status,
      started: this.started,
      lastHeartbeatMs: this.lastHeartbeatMs,
      lastWarmupMs: this.lastWarmupMs,
      lastError: this.lastError,
    };
  }

  getNotifier(): AgentNotifier {
    return this.notifier;
  }

  private async runSupervisorJob(job: ScheduledJob): Promise<void> {
    if (job.type === WARMUP_JOB) {
      await this.runWarmup();
      return;
    }
    if (job.type === HEARTBEAT_JOB) {
      await this.runHeartbeat();
      return;
    }
    throw new Error(`Unsupported supervisor job type: ${job.type}`);
  }

  private async runWarmup(): Promise<void> {
    this.status = "warming";
    this.notify("agent.warmup.started", "info", "Agent warmup started", {});
    await this.warmupFn();
    const ready = await this.readinessProbe();
    if (!ready) {
      throw new Error("Agent readiness probe failed after warmup");
    }
    this.status = "ready";
    this.lastWarmupMs = this.now();
    this.lastError = undefined;
    this.metrics.counter("agent_warmup_success_total", 1, { component: "agent_supervisor" });
    this.notify("agent.warmup.completed", "info", "Agent warmup completed", {
      lastWarmupMs: this.lastWarmupMs,
    });
  }

  private async runHeartbeat(): Promise<void> {
    const ready = await this.readinessProbe();
    if (!ready) {
      throw new Error("Agent readiness probe failed");
    }
    this.status = "ready";
    this.lastHeartbeatMs = this.now();
    this.lastError = undefined;
    this.metrics.counter("agent_heartbeat_total", 1, { component: "agent_supervisor", status: "ready" });
    this.notify("agent.heartbeat", "info", "Agent heartbeat ok", {
      lastHeartbeatMs: this.lastHeartbeatMs,
    });
  }

  private checkHeartbeatFreshness(): void {
    if (!this.started || this.status === "stopped") return;
    if (this.lastHeartbeatMs === undefined) return;
    const age = this.now() - this.lastHeartbeatMs;
    if (age > this.heartbeatStaleAfterMs) {
      this.status = "degraded";
      this.lastError = `Heartbeat stale for ${age} ms`;
      this.metrics.counter("agent_heartbeat_stale_total", 1, { component: "agent_supervisor" });
      this.notify("agent.degraded", "critical", "Agent heartbeat is stale", { ageMs: age });
    }
  }

  private markDegraded(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    this.status = "degraded";
    this.lastError = message;
    this.metrics.counter("agent_supervisor_failure_total", 1, { component: "agent_supervisor" });
    this.notify("agent.degraded", "critical", "Agent supervisor degraded", { error: message });
  }

  private notify(
    type: string,
    severity: AgentNotificationSeverity,
    message: string,
    metadata: Record<string, unknown>,
  ): void {
    this.notifier.notify({
      type,
      severity,
      message,
      metadata,
      timestampMs: this.now(),
    });
  }
}
