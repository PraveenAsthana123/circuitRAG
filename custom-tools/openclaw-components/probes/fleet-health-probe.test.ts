// Iter 127 (2026-05-20): drill that proves the §47.8 3-probe
// pattern is implemented correctly for FleetHealthProbe.
//
// The HARD invariant per §47.8: liveness MUST be a dumb process
// check that never inspects dependency state. Failing this rule
// causes cascade pod restarts — a degraded fleet would trigger
// liveness failures, K8s would kill the pod, the replacement pod
// would also see a degraded fleet, kill loop ensues. Drill #5
// locks this rule: degraded fleet with 0 working agents must
// STILL return 200 on liveness as long as daemon.isRunning().
//
// Negative assertions (≥ 3 per §43):
//   - Startup returns 503 before first cycle (correct K8s
//     startupProbe behavior — don't let pod join the cluster yet)
//   - Liveness does NOT inspect fleet state (returns 200 even
//     when allAgentsWorking=false) — §47.8 dumb-liveness rule
//   - Readiness IS strict (returns 503 when allAgentsWorking=false)
//   - Unknown probe kind throws UnknownProbeKindError
//   - readiness on undefined snapshot returns 503 with reason
//   - liveness on stopped daemon returns 503 (process-level death)

import { describe, it, expect } from "vitest";
import {
  FleetHealthProbe,
  ReadableFleetState,
  UnknownProbeKindError,
} from "./fleet-health-probe";
import type { AgentFleetSnapshot } from "../10-agent-workflow/agent-fleet";

const HEALTHY: AgentFleetSnapshot = {
  desiredActiveAgents: 100,
  totalAgents: 100,
  activeAgents: 100,
  readyAgents: 100,
  workingAgents: 100,
  notWorkingAgents: 0,
  allAgentsWorking: true,
  warmingAgents: 0,
  degradedAgents: 0,
  stoppedAgents: 0,
};

const DEGRADED: AgentFleetSnapshot = {
  ...HEALTHY,
  workingAgents: 60,
  notWorkingAgents: 40,
  allAgentsWorking: false,
  degradedAgents: 40,
};

class StubFleet implements ReadableFleetState {
  constructor(
    public running: boolean,
    public cycles: number,
    public snapshot: AgentFleetSnapshot | undefined,
  ) {}
  isRunning(): boolean { return this.running; }
  cycleCount(): number { return this.cycles; }
  lastSnapshot(): AgentFleetSnapshot | undefined { return this.snapshot; }
}

describe("Iter 127 — FleetHealthProbe implements §47.8 3-probe pattern", () => {

  // ─── STARTUP probe ─────────────────────────────────────────

  it("BACKDOOR: startup returns 200 after first reconcile cycle", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 1, HEALTHY));
    const result = probe.evaluate("startup");
    expect(result.httpCode).toBe(200);
    expect(result.status).toBe("ok");
    expect(result.probe).toBe("startup");
  });

  it("NEGATIVE: startup returns 503 before first cycle (cycles===0)", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 0, undefined));
    const result = probe.evaluate("startup");
    expect(result.httpCode).toBe(503);
    expect(result.status).toBe("starting");
    expect(result.reason).toContain("no reconcile cycle completed yet");
  });

  // ─── LIVENESS probe — the §47.8 hard invariant ─────────────

  it("BACKDOOR: liveness returns 200 when daemon.isRunning()", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 5, HEALTHY));
    expect(probe.evaluate("liveness").httpCode).toBe(200);
  });

  it("NEGATIVE: liveness returns 503 when daemon is stopped (process-level death)", () => {
    const probe = new FleetHealthProbe(new StubFleet(false, 5, HEALTHY));
    const result = probe.evaluate("liveness");
    expect(result.httpCode).toBe(503);
    expect(result.status).toBe("dead");
    expect(result.reason).toContain("daemon loop is not running");
  });

  it("NEGATIVE: §47.8 — liveness does NOT inspect fleet state (degraded fleet still alive)", () => {
    // The HARD §47.8 invariant: if liveness checked allAgentsWorking,
    // a degraded fleet would trigger pod restarts, replacement pod
    // would also be degraded, cascade restart loop ensues.
    // Liveness MUST be a dumb process check.
    const probe = new FleetHealthProbe(new StubFleet(true, 5, DEGRADED));
    const result = probe.evaluate("liveness");
    expect(result.httpCode).toBe(200);
    expect(result.status).toBe("ok");
  });

  it("NEGATIVE: §47.8 — liveness returns 200 with ZERO working agents (extreme case)", () => {
    // Even more extreme: 0/100 agents working. Liveness STILL 200.
    // The fleet is unusable but the daemon process is alive and
    // trying — K8s should NOT restart the pod (that loses the
    // recovery progress). Readiness will fail and drain traffic.
    const zeroWorking: AgentFleetSnapshot = {
      ...HEALTHY,
      workingAgents: 0,
      notWorkingAgents: 100,
      allAgentsWorking: false,
      readyAgents: 0,
    };
    const probe = new FleetHealthProbe(new StubFleet(true, 5, zeroWorking));
    expect(probe.evaluate("liveness").httpCode).toBe(200);
  });

  // ─── READINESS probe ───────────────────────────────────────

  it("BACKDOOR: readiness returns 200 when allAgentsWorking AND startup completed", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 1, HEALTHY));
    const result = probe.evaluate("readiness");
    expect(result.httpCode).toBe(200);
    expect(result.status).toBe("ok");
  });

  it("NEGATIVE: readiness returns 503 when fleet is degraded (notWorking > 0)", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 1, DEGRADED));
    const result = probe.evaluate("readiness");
    expect(result.httpCode).toBe(503);
    expect(result.status).toBe("degraded");
    expect(result.reason).toContain("40/100 agents not yet working");
  });

  it("NEGATIVE: readiness returns 503 before first cycle (startup not done)", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 0, undefined));
    const result = probe.evaluate("readiness");
    expect(result.httpCode).toBe(503);
    expect(result.reason).toContain("startup not yet completed");
  });

  it("NEGATIVE: readiness returns 503 on undefined snapshot (defensive)", () => {
    // Edge: cycle counter incremented (startup OK) but snapshot
    // hasn't landed yet — shouldn't happen in practice but the
    // probe must not crash.
    const probe = new FleetHealthProbe(new StubFleet(true, 1, undefined));
    const result = probe.evaluate("readiness");
    expect(result.httpCode).toBe(503);
    expect(result.reason).toContain("no snapshot recorded yet");
  });

  // ─── Defensive ─────────────────────────────────────────────

  it("NEGATIVE: unknown probe kind throws UnknownProbeKindError", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 1, HEALTHY));
    let err: unknown;
    try {
      probe.evaluate("not-a-real-probe" as never);
    } catch (e) { err = e; }
    expect(err).toBeInstanceOf(UnknownProbeKindError);
  });

  // ─── Observable envelope ───────────────────────────────────

  it("BACKDOOR: every result carries cycles + snapshot + timestamp (operator visibility)", () => {
    const probe = new FleetHealthProbe(new StubFleet(true, 42, HEALTHY));
    const result = probe.evaluate("readiness");
    expect(result.cycles).toBe(42);
    expect(result.snapshot?.workingAgents).toBe(100);
    expect(result.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});
