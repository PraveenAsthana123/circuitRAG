import { describe, expect, it } from "vitest";
import { AgentFleetSupervisor } from "./agent-fleet";
import { AgentSupervisor } from "./agent-supervisor";
import { WorkflowDelegator } from "./workflow-delegator";
import { AgentWorkflowEngine } from "./agent-workflow-engine";
import { WorkflowPlanner } from "./planner";
import { Replanner } from "./replanner";
import { ToolSelector } from "./tool-selector";
import { HumanApprovalGate } from "./human-approval";
import { WorkflowStateStore } from "./workflow-state-store";
import { JobScheduler } from "./job-scheduler";

function clock(start = 1_000) {
  let now = start;
  return {
    now: () => now,
    advance: (ms: number) => { now += ms; },
  };
}

function makeSupervisor(now: () => number, readiness: () => boolean): AgentSupervisor {
  const engine = new AgentWorkflowEngine(
    new WorkflowPlanner(), new Replanner(), new ToolSelector(), new HumanApprovalGate(), new WorkflowStateStore(),
  );
  const delegator = new WorkflowDelegator(engine, { scheduler: new JobScheduler({ now, random: () => 0 }) });
  return new AgentSupervisor(delegator, {
    scheduler: new JobScheduler({ now, random: () => 0 }),
    now,
    heartbeatEveryMs: 100,
    readinessProbe: async () => readiness(),
    runWorkflowOnTick: false,
  });
}

describe("AgentFleetSupervisor", () => {
  it("default policy keeps exactly 100 active agents", async () => {
    const c = clock();
    const fleet = new AgentFleetSupervisor({
      supervisorFactory: () => makeSupervisor(c.now, () => true),
    });

    const snapshot = await fleet.reconcile();

    expect(snapshot.desiredActiveAgents).toBe(100);
    expect(snapshot.activeAgents).toBe(100);
    expect(snapshot.readyAgents).toBe(100);
    expect(snapshot.workingAgents).toBe(100);
    expect(snapshot.notWorkingAgents).toBe(0);
    expect(snapshot.allAgentsWorking).toBe(true);
    expect(fleet.getSupervisors()).toHaveLength(100);
  });

  it("replaces degraded agents to maintain the minimum active count", async () => {
    const c = clock();
    let allowReady = true;
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3, minActiveAgents: 3, maxActiveAgents: 3 },
      supervisorFactory: () => makeSupervisor(c.now, () => allowReady),
    });

    await fleet.reconcile();
    allowReady = false;
    c.advance(100);
    await fleet.reconcile();

    const snapshot = fleet.snapshot();
    expect(snapshot.degradedAgents).toBeGreaterThan(0);
    expect(snapshot.activeAgents).toBe(3);
    expect(snapshot.workingAgents).toBe(0);
    expect(snapshot.allAgentsWorking).toBe(false);
    expect(fleet.getSupervisors().length).toBeGreaterThan(3);
  });

  it("warms healthy replacements in the same reconcile cycle so all required agents work", async () => {
    const c = clock();
    const readinessByIndex = new Map<number, boolean>();
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 2, minActiveAgents: 2, minWorkingAgents: 2, maxActiveAgents: 2 },
      supervisorFactory: (index) => {
        readinessByIndex.set(index, true);
        return makeSupervisor(c.now, () => readinessByIndex.get(index) ?? true);
      },
    });

    await fleet.reconcile();
    readinessByIndex.set(0, false);
    readinessByIndex.set(1, false);
    c.advance(100);
    const snapshot = await fleet.reconcile();

    expect(snapshot.activeAgents).toBe(2);
    expect(snapshot.workingAgents).toBe(2);
    expect(snapshot.notWorkingAgents).toBe(0);
    expect(snapshot.allAgentsWorking).toBe(true);
    expect(snapshot.degradedAgents).toBe(2);
    expect(fleet.getSupervisors().length).toBe(4);
  });

  it("validates fleet policy bounds", () => {
    expect(() => new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 0 },
      supervisorFactory: () => makeSupervisor(() => 0, () => true),
    })).toThrow(/desiredActiveAgents/);
    expect(() => new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 2, minActiveAgents: 3 },
      supervisorFactory: () => makeSupervisor(() => 0, () => true),
    })).toThrow(/minActiveAgents/);
    expect(() => new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3, maxActiveAgents: 2 },
      supervisorFactory: () => makeSupervisor(() => 0, () => true),
    })).toThrow(/desiredActiveAgents/);
    expect(() => new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3, minWorkingAgents: 4 },
      supervisorFactory: () => makeSupervisor(() => 0, () => true),
    })).toThrow(/minWorkingAgents/);
  });
});
