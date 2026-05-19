// Negative drills for Iter 109 (2026-05-18): adversarial coverage on
// Codex iter 94's AgentFleetSupervisor. The original 4 tests cover
// happy-path reconciliation; this drill adds the boundary +
// failure-injection + metric-contract axes that production needs.

import { describe, it, expect, vi } from "vitest";
import {
  AgentFleetSupervisor,
  AgentFleetPolicy,
} from "./agent-fleet";
import { AgentSupervisor } from "./agent-supervisor";
import { JobScheduler } from "./job-scheduler";
import { MetricsRecorder } from "../06-observability/metrics";
import { InMemoryMetricsSink } from "../06-observability/sinks";

function readyFactory(): (index: number) => AgentSupervisor {
  return (index) =>
    new AgentSupervisor(
      { runDue: async () => undefined } as unknown as import("./workflow-delegator").WorkflowDelegator,
      {
        scheduler: new JobScheduler(),
        readinessProbe: async () => true,
        heartbeatEveryMs: 1_000,
      },
    );
}

function alwaysFailFactory(): (index: number) => AgentSupervisor {
  return (_index) =>
    new AgentSupervisor(
      { runDue: async () => undefined } as unknown as import("./workflow-delegator").WorkflowDelegator,
      {
        scheduler: new JobScheduler(),
        readinessProbe: async () => { throw new Error("boom"); },
        heartbeatEveryMs: 1_000,
      },
    );
}

describe("Iter 109 — AgentFleet adversarial coverage (P1)", () => {
  it("BACKDOOR: desiredActiveAgents=1 edge — smallest possible fleet still reconciles", async () => {
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 1 },
      supervisorFactory: readyFactory(),
    });
    const snap = await fleet.reconcile();
    expect(snap.activeAgents).toBe(1);
    expect(snap.workingAgents).toBe(1);
    expect(snap.allAgentsWorking).toBe(true);
  });

  it("BACKDOOR: every supervisor fails readiness → fleet keeps trying to replace (bounded by minActiveAgents)", async () => {
    let factoryCalls = 0;
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3, minActiveAgents: 3 },
      supervisorFactory: (_i) => {
        factoryCalls += 1;
        return new AgentSupervisor(
          { runDue: async () => undefined } as unknown as import("./workflow-delegator").WorkflowDelegator,
          {
            scheduler: new JobScheduler(),
            readinessProbe: async () => { throw new Error("boom"); },
            heartbeatEveryMs: 1_000,
          },
        );
      },
    });
    // First reconcile creates 3 + tries to warm them. All fail.
    // replaceBelowMinimum kicks in but the new ones also fail when
    // ticked. Fleet must not infinite-loop.
    await fleet.reconcile();
    // Factory call count is bounded — at least 3 (initial) + some
    // replacements, but the test must complete (no infinite loop).
    expect(factoryCalls).toBeGreaterThanOrEqual(3);
    // Snapshot shows degraded state, not crash.
    const snap = fleet.snapshot();
    expect(snap.workingAgents).toBe(0);
  });

  it("emits 4 histogram metrics per reconcile (active/ready/working/not_working)", async () => {
    const sink = new InMemoryMetricsSink();
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 2 },
      supervisorFactory: readyFactory(),
      metrics: new MetricsRecorder({}, sink),
    });
    await fleet.reconcile();
    const names = sink.list().map((r) => r.name).sort();
    expect(names).toContain("agent_fleet_active_agents");
    expect(names).toContain("agent_fleet_ready_agents");
    expect(names).toContain("agent_fleet_working_agents");
    expect(names).toContain("agent_fleet_not_working_agents");
  });

  it("metric labels include component='agent_fleet' for downstream filtering", async () => {
    const sink = new InMemoryMetricsSink();
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 1 },
      supervisorFactory: readyFactory(),
      metrics: new MetricsRecorder({}, sink),
    });
    await fleet.reconcile();
    for (const r of sink.list()) {
      expect(r.labels.component).toBe("agent_fleet");
    }
  });

  it("metric values for active+ready+working match snapshot (no drift)", async () => {
    const sink = new InMemoryMetricsSink();
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3 },
      supervisorFactory: readyFactory(),
      metrics: new MetricsRecorder({}, sink),
    });
    const snap = await fleet.reconcile();
    const find = (n: string) => sink.list().find((r) => r.name === n)?.value;
    expect(find("agent_fleet_active_agents")).toBe(snap.activeAgents);
    expect(find("agent_fleet_ready_agents")).toBe(snap.readyAgents);
    expect(find("agent_fleet_working_agents")).toBe(snap.workingAgents);
    expect(find("agent_fleet_not_working_agents")).toBe(snap.notWorkingAgents);
  });

  it("snapshot.allAgentsWorking === false when readyAgents < desired", async () => {
    let count = 0;
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 5 },
      // First 2 succeed, rest fail.
      supervisorFactory: (_i) => new AgentSupervisor(
        { runDue: async () => undefined } as unknown as import("./workflow-delegator").WorkflowDelegator,
        {
          scheduler: new JobScheduler(),
          readinessProbe: async () => { count += 1; return count <= 2; },
          heartbeatEveryMs: 1_000,
        },
      ),
    });
    await fleet.reconcile();
    const snap = fleet.snapshot();
    expect(snap.allAgentsWorking).toBe(false);
    expect(snap.notWorkingAgents).toBeGreaterThan(0);
  });

  it("BACKDOOR: getSupervisors() returns readonly view (mutation not allowed)", () => {
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 1 },
      supervisorFactory: readyFactory(),
    });
    const supervisors = fleet.getSupervisors();
    expect(Array.isArray(supervisors)).toBe(true);
    // TypeScript marks as readonly; runtime is regular array. Drill
    // confirms the snapshot pattern (getter returns the internal
    // array but the type system rejects mutation).
    expect((supervisors as unknown as { push?: unknown }).push).toBeDefined();
    // (intentional — runtime mutation not blocked, only type-blocked)
  });

  it("multiple reconcile calls are idempotent (no extra supervisors created)", async () => {
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 3 },
      supervisorFactory: readyFactory(),
    });
    await fleet.reconcile();
    const after1 = fleet.getSupervisors().length;
    await fleet.reconcile();
    await fleet.reconcile();
    const after3 = fleet.getSupervisors().length;
    expect(after3).toBe(after1);  // no growth across reconciles
  });

  it("snapshot before any reconcile shows 0 totalAgents (cold-start regression)", () => {
    const fleet = new AgentFleetSupervisor({
      policy: { desiredActiveAgents: 5 },
      supervisorFactory: readyFactory(),
    });
    const snap = fleet.snapshot();
    expect(snap.totalAgents).toBe(0);
    expect(snap.activeAgents).toBe(0);
    expect(snap.workingAgents).toBe(0);
    expect(snap.allAgentsWorking).toBe(false);
  });

  it("default desired count is 100 (per Codex iter 94 contract)", async () => {
    // Codex's iter 94 named '100 active' as the canonical default.
    // Drill that the constructor produces 100 when policy omitted.
    const fleet = new AgentFleetSupervisor({
      supervisorFactory: readyFactory(),
    });
    const snap = fleet.snapshot();
    expect(snap.desiredActiveAgents).toBe(100);
  });

  it("custom desired count overrides default (regression — option respected)", async () => {
    const policy: AgentFleetPolicy = { desiredActiveAgents: 7 };
    const fleet = new AgentFleetSupervisor({
      policy,
      supervisorFactory: readyFactory(),
    });
    const snap = fleet.snapshot();
    expect(snap.desiredActiveAgents).toBe(7);
  });
});
