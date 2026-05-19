import { describe, expect, it } from "vitest";
import { JobScheduler } from "./job-scheduler";

function clock(start = 1_000) {
  let now = start;
  return {
    now: () => now,
    advance: (ms: number) => { now += ms; },
  };
}

describe("JobScheduler", () => {
  it("runs only due jobs and orders by priority then runAt", async () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now, random: () => 0, concurrency: 10 });
    scheduler.schedule({ tenantId: "t", type: "low", payload: {}, priority: 1 });
    scheduler.schedule({ tenantId: "t", type: "later", payload: {}, priority: 99, delayMs: 50 });
    scheduler.schedule({ tenantId: "t", type: "high", payload: {}, priority: 10 });

    const seen: string[] = [];
    const result = await scheduler.runDue(async (job) => { seen.push(job.type); });

    expect(result).toMatchObject({ started: 2, succeeded: 2 });
    expect(seen).toEqual(["high", "low"]);
  });

  it("deduplicates active jobs by tenant-scoped idempotency key", () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now });
    const first = scheduler.schedule({ tenantId: "t", type: "x", payload: { n: 1 }, idempotencyKey: "same" });
    const second = scheduler.schedule({ tenantId: "t", type: "x", payload: { n: 2 }, idempotencyKey: "same" });
    const otherTenant = scheduler.schedule({ tenantId: "other", type: "x", payload: { n: 3 }, idempotencyKey: "same" });

    expect(second.jobId).toBe(first.jobId);
    expect(otherTenant.jobId).not.toBe(first.jobId);
  });

  it("retries failures with full-jitter backoff and then succeeds", async () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now, random: () => 0.5 });
    const job = scheduler.schedule({
      tenantId: "t", type: "retry", payload: {}, maxAttempts: 3,
      baseBackoffMs: 100, maxBackoffMs: 1_000,
    });

    let calls = 0;
    await scheduler.runDue(async () => {
      calls += 1;
      throw new Error("temporary");
    });
    const afterFail = scheduler.get(job.jobId, "t");
    expect(afterFail.status).toBe("queued");
    expect(afterFail.attempts).toBe(1);
    expect(afterFail.runAtMs).toBe(1_050);

    c.advance(49);
    expect(scheduler.due()).toHaveLength(0);
    c.advance(1);
    await scheduler.runDue(async () => { calls += 1; });

    expect(calls).toBe(2);
    expect(scheduler.get(job.jobId, "t").status).toBe("succeeded");
  });

  it("moves exhausted jobs to dead_letter with the final error", async () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now, random: () => 0 });
    const job = scheduler.schedule({ tenantId: "t", type: "fail", payload: {}, maxAttempts: 2 });

    await scheduler.runDue(async () => { throw new Error("boom-1"); });
    await scheduler.runDue(async () => { throw new Error("boom-2"); });

    const after = scheduler.get(job.jobId, "t");
    expect(after.status).toBe("dead_letter");
    expect(after.deadLetterReason).toBe("boom-2");
  });

  it("recurring jobs are rescheduled after success", async () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now });
    const job = scheduler.schedule({ tenantId: "t", type: "heartbeat", payload: {}, recurringEveryMs: 500 });

    await scheduler.runDue(async () => undefined);
    const after = scheduler.get(job.jobId, "t");

    expect(after.status).toBe("queued");
    expect(after.runAtMs).toBe(1_500);
  });

  it("expired leases can be acquired again, but active leases are hidden", async () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now, leaseMs: 100 });
    scheduler.schedule({ tenantId: "t", type: "slow", payload: {} });

    const running = scheduler.runDue(async () => {
      c.advance(50);
      expect(scheduler.due()).toHaveLength(0);
      c.advance(50);
      expect(scheduler.due()).toHaveLength(1);
    });
    await running;
  });

  it("cancels queued jobs and enforces tenant isolation", () => {
    const c = clock();
    const scheduler = new JobScheduler({ now: c.now });
    const job = scheduler.schedule({ tenantId: "tenant-A", type: "x", payload: {} });

    expect(() => scheduler.get(job.jobId, "tenant-B")).toThrow(/access denied/i);
    const cancelled = scheduler.cancel(job.jobId, "tenant-A", "operator stop");

    expect(cancelled.status).toBe("cancelled");
    expect(cancelled.deadLetterReason).toBe("operator stop");
    expect(scheduler.due()).toHaveLength(0);
  });

  it("validates unsafe scheduler configuration and job inputs", () => {
    expect(() => new JobScheduler({ concurrency: 0 })).toThrow(/concurrency/);
    expect(() => new JobScheduler({ leaseMs: 0 })).toThrow(/leaseMs/);

    const scheduler = new JobScheduler();
    expect(() => scheduler.schedule({ tenantId: "", type: "x", payload: {} })).toThrow(/tenantId/);
    expect(() => scheduler.schedule({ tenantId: "t", type: "", payload: {} })).toThrow(/type/);
    expect(() => scheduler.schedule({ tenantId: "t", type: "x", payload: {}, maxAttempts: 0 })).toThrow(/maxAttempts/);
    expect(() => scheduler.schedule({ tenantId: "t", type: "x", payload: {}, recurringEveryMs: 0 })).toThrow(/recurringEveryMs/);
  });
});
