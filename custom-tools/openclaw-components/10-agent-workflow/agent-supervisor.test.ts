import { describe, expect, it, vi } from "vitest";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { WorkflowDelegator } from "./workflow-delegator";
import { JobScheduler } from "./job-scheduler";
import { AgentSupervisor, InMemoryAgentNotifier } from "./agent-supervisor";

function clock(start = 1_000) {
  let now = start;
  return {
    now: () => now,
    advance: (ms: number) => { now += ms; },
  };
}

function delegator(scheduler = new JobScheduler()): WorkflowDelegator {
  const engine = new AgentWorkflowEngine(
    new WorkflowPlanner(), new Replanner(), new ToolSelector(), new HumanApprovalGate(), new WorkflowStateStore(),
  );
  return new WorkflowDelegator(engine, { scheduler });
}

describe("AgentSupervisor", () => {
  it("starts cold, schedules warmup + heartbeat, and becomes ready after warmup", async () => {
    const c = clock();
    const notifier = new InMemoryAgentNotifier();
    const warmup = vi.fn(async () => undefined);
    const supervisor = new AgentSupervisor(delegator(), {
      scheduler: new JobScheduler({ now: c.now, random: () => 0 }),
      notifier,
      now: c.now,
      heartbeatEveryMs: 100,
      readinessProbe: async () => true,
      warmup,
      runWorkflowOnTick: false,
    });

    supervisor.start();
    expect(supervisor.snapshot().status).toBe("warming");
    await supervisor.runTick();

    expect(warmup).toHaveBeenCalledTimes(1);
    expect(supervisor.snapshot()).toMatchObject({ status: "ready", started: true, lastWarmupMs: 1_000 });
    expect(notifier.events.map((e) => e.type)).toEqual([
      "agent.starting",
      "agent.warmup.started",
      "agent.heartbeat",
      "agent.warmup.completed",
    ]);
  });

  it("emits recurring heartbeat notifications and keeps the agent warm", async () => {
    const c = clock();
    const notifier = new InMemoryAgentNotifier();
    const supervisor = new AgentSupervisor(delegator(), {
      scheduler: new JobScheduler({ now: c.now, random: () => 0 }),
      notifier,
      now: c.now,
      heartbeatEveryMs: 100,
      readinessProbe: async () => true,
      runWorkflowOnTick: false,
    });

    await supervisor.runTick();
    c.advance(100);
    await supervisor.runTick();

    const heartbeats = notifier.events.filter((e) => e.type === "agent.heartbeat");
    expect(heartbeats).toHaveLength(2);
    expect(supervisor.snapshot().lastHeartbeatMs).toBe(1_100);
  });

  it("marks degraded and notifies when readiness fails", async () => {
    const c = clock();
    const notifier = new InMemoryAgentNotifier();
    const supervisor = new AgentSupervisor(delegator(), {
      scheduler: new JobScheduler({ now: c.now, random: () => 0 }),
      notifier,
      now: c.now,
      heartbeatEveryMs: 100,
      readinessProbe: async () => false,
      runWorkflowOnTick: false,
    });

    await supervisor.runTick();

    expect(supervisor.snapshot().status).toBe("degraded");
    expect(notifier.events.some((e) => e.type === "agent.degraded" && e.severity === "critical")).toBe(true);
  });

  it("runs delegated workflow jobs on each tick so queued agent work keeps moving", async () => {
    const c = clock();
    const store = new WorkflowStateStore();
    const engine = new AgentWorkflowEngine(
      new WorkflowPlanner(), new Replanner(), new ToolSelector(), new HumanApprovalGate(), store,
    );
    const workflow = engine.start({
      workflowId: "wf-supervised", requestId: "r", tenantId: "t", userId: "u", traceId: "tr",
    }, "keep moving");
    const workflowScheduler = new JobScheduler({ now: c.now, random: () => 0 });
    const wfDelegator = new WorkflowDelegator(engine, { scheduler: workflowScheduler });
    wfDelegator.delegateRunNext(workflow.context);

    const supervisor = new AgentSupervisor(wfDelegator, {
      scheduler: new JobScheduler({ now: c.now, random: () => 0 }),
      now: c.now,
      heartbeatEveryMs: 100,
      readinessProbe: async () => true,
    });

    await supervisor.runTick();

    expect(store.get(workflow.context.workflowId, "t").steps[0].status).toBe("completed");
    expect(wfDelegator.getScheduler().list("t", "queued")).toHaveLength(0);
  });

  it("stop sends an update notification and moves status to stopped", () => {
    const c = clock();
    const notifier = new InMemoryAgentNotifier();
    const supervisor = new AgentSupervisor(delegator(), { notifier, now: c.now });

    supervisor.start();
    supervisor.stop("deploy update");

    expect(supervisor.snapshot().status).toBe("stopped");
    expect(notifier.events.at(-1)).toMatchObject({
      type: "agent.stopped",
      severity: "warning",
      metadata: { reason: "deploy update" },
    });
  });

  it("validates heartbeat configuration", () => {
    expect(() => new AgentSupervisor(delegator(), { heartbeatEveryMs: 0 })).toThrow(/heartbeatEveryMs/);
    expect(() => new AgentSupervisor(delegator(), { heartbeatEveryMs: 100, heartbeatStaleAfterMs: 50 })).toThrow(/heartbeatStaleAfterMs/);
  });
});
