import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { JobScheduler, ScheduledJob } from "./job-scheduler";
import { WorkflowContext } from "./types";
import { NoopWorkflowMonitor, WorkflowMonitor } from "./workflow-monitor";

export interface WorkflowRunJobPayload extends Record<string, unknown> {
  workflowId: string;
  callerTenantId: string;
}

export interface WorkflowDelegatorOptions {
  scheduler?: JobScheduler;
  monitor?: WorkflowMonitor;
  maxAttempts?: number;
  baseBackoffMs?: number;
  maxBackoffMs?: number;
}

export class WorkflowDelegator {
  private readonly scheduler: JobScheduler;
  private readonly monitor: WorkflowMonitor;
  private readonly maxAttempts: number;
  private readonly baseBackoffMs: number;
  private readonly maxBackoffMs: number;

  constructor(
    private readonly engine: AgentWorkflowEngine,
    options: WorkflowDelegatorOptions = {},
  ) {
    this.scheduler = options.scheduler ?? new JobScheduler();
    this.monitor = options.monitor ?? new NoopWorkflowMonitor();
    this.maxAttempts = options.maxAttempts ?? 3;
    this.baseBackoffMs = options.baseBackoffMs ?? 1_000;
    this.maxBackoffMs = options.maxBackoffMs ?? 60_000;
  }

  delegateRunNext(context: WorkflowContext, priority = 0, delayMs = 0): ScheduledJob<WorkflowRunJobPayload> {
    const job = this.scheduler.schedule<WorkflowRunJobPayload>({
      tenantId: context.tenantId,
      type: "workflow.run_next",
      payload: {
        workflowId: context.workflowId,
        callerTenantId: context.tenantId,
      },
      priority,
      delayMs,
      maxAttempts: this.maxAttempts,
      baseBackoffMs: this.baseBackoffMs,
      maxBackoffMs: this.maxBackoffMs,
      idempotencyKey: `workflow.run_next:${context.workflowId}`,
    });
    this.monitor.workflowDelegated(context, job.jobId);
    return job;
  }

  async runDue(limit?: number) {
    return this.scheduler.runDue(async (job) => {
      if (job.type !== "workflow.run_next") {
        throw new Error(`Unsupported workflow job type: ${job.type}`);
      }
      const payload = job.payload as WorkflowRunJobPayload;
      await this.engine.runNext(payload.workflowId, payload.callerTenantId);
    }, limit);
  }

  getScheduler(): JobScheduler {
    return this.scheduler;
  }
}
