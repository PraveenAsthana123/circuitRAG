import { randomUUID } from "crypto";

export type ScheduledJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "dead_letter"
  | "cancelled";

export interface ScheduledJob<TPayload extends Record<string, unknown> = Record<string, unknown>> {
  jobId: string;
  tenantId: string;
  type: string;
  payload: TPayload;
  status: ScheduledJobStatus;
  priority: number;
  runAtMs: number;
  createdAtMs: number;
  updatedAtMs: number;
  attempts: number;
  maxAttempts: number;
  baseBackoffMs: number;
  maxBackoffMs: number;
  leaseUntilMs?: number;
  lockedBy?: string;
  idempotencyKey?: string;
  recurringEveryMs?: number;
  lastError?: string;
  deadLetterReason?: string;
}

export interface ScheduleJobInput<TPayload extends Record<string, unknown> = Record<string, unknown>> {
  tenantId: string;
  type: string;
  payload: TPayload;
  delayMs?: number;
  priority?: number;
  maxAttempts?: number;
  baseBackoffMs?: number;
  maxBackoffMs?: number;
  idempotencyKey?: string;
  recurringEveryMs?: number;
}

export interface JobSchedulerOptions {
  now?: () => number;
  random?: () => number;
  workerId?: string;
  concurrency?: number;
  leaseMs?: number;
}

export interface JobRunResult {
  started: number;
  succeeded: number;
  failed: number;
  deadLettered: number;
}

export type JobHandler = (job: ScheduledJob) => Promise<void>;

const DEFAULT_MAX_ATTEMPTS = 3;
const DEFAULT_BASE_BACKOFF_MS = 1_000;
const DEFAULT_MAX_BACKOFF_MS = 60_000;
const DEFAULT_LEASE_MS = 30_000;
const DEFAULT_CONCURRENCY = 4;

export class JobScheduler {
  private readonly jobs = new Map<string, ScheduledJob>();
  private readonly idempotency = new Map<string, string>();
  private readonly now: () => number;
  private readonly random: () => number;
  private readonly workerId: string;
  private readonly concurrency: number;
  private readonly leaseMs: number;

  constructor(options: JobSchedulerOptions = {}) {
    this.now = options.now ?? (() => Date.now());
    this.random = options.random ?? Math.random;
    this.workerId = options.workerId ?? `worker-${randomUUID()}`;
    this.concurrency = options.concurrency ?? DEFAULT_CONCURRENCY;
    this.leaseMs = options.leaseMs ?? DEFAULT_LEASE_MS;

    if (!Number.isInteger(this.concurrency) || this.concurrency < 1) {
      throw new Error("concurrency must be a positive integer");
    }
    if (!Number.isInteger(this.leaseMs) || this.leaseMs < 1) {
      throw new Error("leaseMs must be a positive integer");
    }
  }

  schedule<TPayload extends Record<string, unknown>>(
    input: ScheduleJobInput<TPayload>,
  ): ScheduledJob<TPayload> {
    this.validateInput(input);

    if (input.idempotencyKey) {
      const key = this.idempotencyKey(input.tenantId, input.idempotencyKey);
      const existingId = this.idempotency.get(key);
      const existing = existingId ? this.jobs.get(existingId) : undefined;
      if (existing && ["queued", "running", "succeeded"].includes(existing.status)) {
        return existing as ScheduledJob<TPayload>;
      }
    }

    const now = this.now();
    const job: ScheduledJob<TPayload> = {
      jobId: randomUUID(),
      tenantId: input.tenantId,
      type: input.type,
      payload: input.payload,
      status: "queued",
      priority: input.priority ?? 0,
      runAtMs: now + (input.delayMs ?? 0),
      createdAtMs: now,
      updatedAtMs: now,
      attempts: 0,
      maxAttempts: input.maxAttempts ?? DEFAULT_MAX_ATTEMPTS,
      baseBackoffMs: input.baseBackoffMs ?? DEFAULT_BASE_BACKOFF_MS,
      maxBackoffMs: input.maxBackoffMs ?? DEFAULT_MAX_BACKOFF_MS,
      idempotencyKey: input.idempotencyKey,
      recurringEveryMs: input.recurringEveryMs,
    };

    this.jobs.set(job.jobId, job);
    if (job.idempotencyKey) {
      this.idempotency.set(this.idempotencyKey(job.tenantId, job.idempotencyKey), job.jobId);
    }
    return { ...job };
  }

  get(jobId: string, tenantId: string): ScheduledJob {
    const job = this.jobs.get(jobId);
    if (!job) throw new Error(`Job not found: ${jobId}`);
    if (job.tenantId !== tenantId) throw new Error("Job access denied");
    return { ...job };
  }

  cancel(jobId: string, tenantId: string, reason = "cancelled"): ScheduledJob {
    const job = this.jobs.get(jobId);
    if (!job) throw new Error(`Job not found: ${jobId}`);
    if (job.tenantId !== tenantId) throw new Error("Job access denied");
    if (["succeeded", "dead_letter"].includes(job.status)) {
      throw new Error(`Cannot cancel job in status ${job.status}`);
    }
    job.status = "cancelled";
    job.deadLetterReason = reason;
    job.leaseUntilMs = undefined;
    job.lockedBy = undefined;
    job.updatedAtMs = this.now();
    return { ...job };
  }

  list(tenantId: string, status?: ScheduledJobStatus): ScheduledJob[] {
    return Array.from(this.jobs.values())
      .filter((job) => job.tenantId === tenantId)
      .filter((job) => status === undefined || job.status === status)
      .map((job) => ({ ...job }));
  }

  due(limit = this.concurrency): ScheduledJob[] {
    const now = this.now();
    return Array.from(this.jobs.values())
      .filter((job) => job.status === "queued" || this.isExpiredLease(job, now))
      .filter((job) => job.runAtMs <= now)
      .sort((a, b) => {
        if (b.priority !== a.priority) return b.priority - a.priority;
        if (a.runAtMs !== b.runAtMs) return a.runAtMs - b.runAtMs;
        return a.createdAtMs - b.createdAtMs;
      })
      .slice(0, Math.max(0, limit))
      .map((job) => ({ ...job }));
  }

  async runDue(handler: JobHandler, limit = this.concurrency): Promise<JobRunResult> {
    const candidates = this.due(limit);
    const leased: ScheduledJob[] = [];
    for (const candidate of candidates) {
      const job = this.tryAcquire(candidate.jobId);
      if (job) leased.push(job);
    }

    const result: JobRunResult = {
      started: leased.length,
      succeeded: 0,
      failed: 0,
      deadLettered: 0,
    };

    await Promise.all(leased.map(async (job) => {
      try {
        await handler({ ...job });
        const completed = this.markSucceeded(job.jobId);
        if (completed.status === "succeeded") result.succeeded += 1;
      } catch (error) {
        const failed = this.markFailed(job.jobId, error);
        if (failed.status === "dead_letter") result.deadLettered += 1;
        else result.failed += 1;
      }
    }));

    return result;
  }

  private tryAcquire(jobId: string): ScheduledJob | undefined {
    const job = this.jobs.get(jobId);
    if (!job) return undefined;
    const now = this.now();
    if (!(job.status === "queued" || this.isExpiredLease(job, now))) return undefined;
    if (job.runAtMs > now) return undefined;

    job.status = "running";
    job.lockedBy = this.workerId;
    job.leaseUntilMs = now + this.leaseMs;
    job.attempts += 1;
    job.updatedAtMs = now;
    return { ...job };
  }

  private markSucceeded(jobId: string): ScheduledJob {
    const job = this.requireJob(jobId);
    const now = this.now();
    if (job.recurringEveryMs !== undefined) {
      job.status = "queued";
      job.runAtMs = now + job.recurringEveryMs;
      job.leaseUntilMs = undefined;
      job.lockedBy = undefined;
      job.lastError = undefined;
      job.updatedAtMs = now;
      return { ...job };
    }

    job.status = "succeeded";
    job.leaseUntilMs = undefined;
    job.lockedBy = undefined;
    job.lastError = undefined;
    job.updatedAtMs = now;
    return { ...job };
  }

  private markFailed(jobId: string, error: unknown): ScheduledJob {
    const job = this.requireJob(jobId);
    const now = this.now();
    const message = error instanceof Error ? error.message : String(error);
    job.lastError = message;
    job.leaseUntilMs = undefined;
    job.lockedBy = undefined;

    if (job.attempts >= job.maxAttempts) {
      job.status = "dead_letter";
      job.deadLetterReason = message;
      job.updatedAtMs = now;
      return { ...job };
    }

    job.status = "queued";
    job.runAtMs = now + this.nextBackoffMs(job);
    job.updatedAtMs = now;
    return { ...job };
  }

  private nextBackoffMs(job: ScheduledJob): number {
    const exponential = job.baseBackoffMs * (2 ** Math.max(0, job.attempts - 1));
    const capped = Math.min(exponential, job.maxBackoffMs);
    return Math.floor(this.random() * capped);
  }

  private isExpiredLease(job: ScheduledJob, now: number): boolean {
    return job.status === "running" && job.leaseUntilMs !== undefined && job.leaseUntilMs <= now;
  }

  private requireJob(jobId: string): ScheduledJob {
    const job = this.jobs.get(jobId);
    if (!job) throw new Error(`Job not found: ${jobId}`);
    return job;
  }

  private validateInput(input: ScheduleJobInput): void {
    if (!input.tenantId) throw new Error("tenantId is required");
    if (!input.type) throw new Error("type is required");
    if (input.delayMs !== undefined && (!Number.isFinite(input.delayMs) || input.delayMs < 0)) {
      throw new Error("delayMs must be a non-negative finite number");
    }
    if (input.maxAttempts !== undefined && (!Number.isInteger(input.maxAttempts) || input.maxAttempts < 1)) {
      throw new Error("maxAttempts must be a positive integer");
    }
    if (input.baseBackoffMs !== undefined && (!Number.isFinite(input.baseBackoffMs) || input.baseBackoffMs < 0)) {
      throw new Error("baseBackoffMs must be a non-negative finite number");
    }
    if (input.maxBackoffMs !== undefined && (!Number.isFinite(input.maxBackoffMs) || input.maxBackoffMs < 1)) {
      throw new Error("maxBackoffMs must be a positive finite number");
    }
    if (input.recurringEveryMs !== undefined && (!Number.isInteger(input.recurringEveryMs) || input.recurringEveryMs < 1)) {
      throw new Error("recurringEveryMs must be a positive integer");
    }
  }

  private idempotencyKey(tenantId: string, key: string): string {
    return `${tenantId}:${key}`;
  }
}
