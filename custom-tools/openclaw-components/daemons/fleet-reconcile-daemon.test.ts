// Iter 126 (2026-05-19): drill that proves FleetReconcileDaemon
// closes the operator-flagged gap:
//
//   > "I did not see a repo CLI daemon that continuously calls
//   > fleet.reconcile() as a standalone process."
//
// The drill exercises the class directly (not a subprocess) so
// it's fast + deterministic. The CLI entry function
// runDaemonFromEnv() is a thin process.on(SIGTERM) wrapper that
// inherits all the drilled invariants.
//
// Negative assertions (≥ 3 per §43):
//   - Failed reconcile cycle does NOT crash the daemon (continues
//     to next cycle, logs the error)
//   - Double-start throws DaemonAlreadyRunningError
//   - Idempotent stop on a non-running daemon does NOT throw
//   - intervalMs < 10 throws at construction (defensive validation)
//   - stop() during sleep returns the loop WITHIN ~1 cycle, NOT
//     waiting for the full intervalMs

import { describe, it, expect } from "vitest";
import {
  FleetReconcileDaemon,
  ReconcilableFleet,
  FleetReconcileDaemonLogger,
  FleetCycleEvent,
  FleetCycleErrorEvent,
  FleetLifecycleEvent,
  DaemonAlreadyRunningError,
} from "./fleet-reconcile-daemon";
import { AgentFleetSnapshot } from "../10-agent-workflow/agent-fleet";

const SNAPSHOT: AgentFleetSnapshot = {
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

class StubFleet implements ReconcilableFleet {
  cycles = 0;
  failNext = false;
  reconcileDelayMs = 0;
  async reconcile(): Promise<AgentFleetSnapshot> {
    this.cycles += 1;
    if (this.reconcileDelayMs > 0) {
      await new Promise((r) => setTimeout(r, this.reconcileDelayMs));
    }
    if (this.failNext) {
      this.failNext = false;
      throw new Error("simulated reconcile failure");
    }
    return SNAPSHOT;
  }
}

class CapturingLogger implements FleetReconcileDaemonLogger {
  readonly cycles: FleetCycleEvent[] = [];
  readonly errors: FleetCycleErrorEvent[] = [];
  readonly lifecycle: FleetLifecycleEvent[] = [];
  onCycle(e: FleetCycleEvent): void { this.cycles.push(e); }
  onCycleError(e: FleetCycleErrorEvent): void { this.errors.push(e); }
  onLifecycle(e: FleetLifecycleEvent): void { this.lifecycle.push(e); }
}

describe("Iter 126 — FleetReconcileDaemon CLI wrapper", () => {
  it("BACKDOOR: daemon runs ≥ 2 reconcile cycles before stop", async () => {
    const fleet = new StubFleet();
    const logger = new CapturingLogger();
    const daemon = new FleetReconcileDaemon({ supervisor: fleet, intervalMs: 10, logger });

    const runPromise = daemon.start();
    // Wait until at least 2 cycles have logged.
    await waitFor(() => logger.cycles.length >= 2, 1_000);
    daemon.stop("test-done");
    await runPromise;

    expect(logger.cycles.length).toBeGreaterThanOrEqual(2);
    expect(logger.cycles[0].cycle).toBe(1);
    expect(logger.cycles[0].snapshot.workingAgents).toBe(100);
    expect(daemon.cycleCount()).toBeGreaterThanOrEqual(2);
    expect(daemon.lastSnapshot()?.workingAgents).toBe(100);
  });

  it("BACKDOOR: lifecycle events emit in order starting → stopping → stopped", async () => {
    const fleet = new StubFleet();
    const logger = new CapturingLogger();
    const daemon = new FleetReconcileDaemon({ supervisor: fleet, intervalMs: 10, logger });

    const runPromise = daemon.start();
    await waitFor(() => logger.cycles.length >= 1, 1_000);
    daemon.stop("test");
    await runPromise;

    const phases = logger.lifecycle.map((e) => e.phase);
    expect(phases).toEqual(["starting", "stopping", "stopped"]);
    expect(logger.lifecycle[1].reason).toBe("test");
    expect(logger.lifecycle[2].reason).toBe("test");
  });

  it("NEGATIVE: a failed reconcile cycle does NOT crash the daemon — next cycle runs", async () => {
    const fleet = new StubFleet();
    fleet.failNext = true;
    const logger = new CapturingLogger();
    const daemon = new FleetReconcileDaemon({ supervisor: fleet, intervalMs: 10, logger });

    const runPromise = daemon.start();
    // Wait for an error AND a subsequent successful cycle.
    await waitFor(() => logger.errors.length >= 1 && logger.cycles.length >= 1, 1_000);
    daemon.stop("test");
    await runPromise;

    expect(logger.errors.length).toBeGreaterThanOrEqual(1);
    expect(logger.errors[0].errorMessage).toContain("simulated reconcile failure");
    expect(logger.cycles.length).toBeGreaterThanOrEqual(1);  // recovery cycle landed
    expect(daemon.isRunning()).toBe(false);
  });

  it("NEGATIVE: stop() during sleep returns the loop within ~1 interval (not waits full intervalMs)", async () => {
    const fleet = new StubFleet();
    const logger = new CapturingLogger();
    const intervalMs = 10_000;  // 10s — would take forever if stop didn't cancel sleep
    const daemon = new FleetReconcileDaemon({ supervisor: fleet, intervalMs, logger });

    const runPromise = daemon.start();
    await waitFor(() => logger.cycles.length >= 1, 1_000);

    const stopStartedAt = Date.now();
    daemon.stop("test");
    await runPromise;
    const shutdownTookMs = Date.now() - stopStartedAt;

    // Graceful shutdown must complete WAY faster than intervalMs.
    // Allow generous slack (1s) for vitest/CI overhead but assert
    // we did NOT wait the full 10s sleep.
    expect(shutdownTookMs).toBeLessThan(1_000);
  });

  it("NEGATIVE: stop() does NOT interrupt an in-flight reconcile — it waits for cycle to complete", async () => {
    const fleet = new StubFleet();
    fleet.reconcileDelayMs = 200;  // each cycle takes 200ms
    const logger = new CapturingLogger();
    const daemon = new FleetReconcileDaemon({ supervisor: fleet, intervalMs: 10, logger });

    const runPromise = daemon.start();
    // Wait until cycle is IN-PROGRESS (reconcile increments cycles immediately).
    await waitFor(() => fleet.cycles >= 1, 500);
    // Stop mid-reconcile.
    daemon.stop("mid-cycle");
    await runPromise;

    // The in-flight cycle MUST have completed (logged onCycle).
    expect(logger.cycles.length).toBeGreaterThanOrEqual(1);
    expect(logger.cycles[logger.cycles.length - 1].snapshot.workingAgents).toBe(100);
  });

  it("NEGATIVE: double-start throws DaemonAlreadyRunningError", async () => {
    const fleet = new StubFleet();
    const daemon = new FleetReconcileDaemon({
      supervisor: fleet,
      intervalMs: 10,
      logger: new CapturingLogger(),
    });

    const runPromise = daemon.start();
    await waitFor(() => daemon.isRunning(), 500);

    let err: unknown;
    try { await daemon.start(); } catch (e) { err = e; }
    expect(err).toBeInstanceOf(DaemonAlreadyRunningError);
    expect((err as { name: string }).name).toBe("DaemonAlreadyRunningError");

    daemon.stop("test");
    await runPromise;
  });

  it("NEGATIVE: stop() on a non-running daemon is idempotent (no throw)", () => {
    const fleet = new StubFleet();
    const daemon = new FleetReconcileDaemon({
      supervisor: fleet,
      intervalMs: 10,
      logger: new CapturingLogger(),
    });

    expect(() => daemon.stop("not-yet-started")).not.toThrow();
    expect(daemon.isRunning()).toBe(false);
    expect(daemon.cycleCount()).toBe(0);
  });

  it("NEGATIVE: intervalMs < 10 throws at construction (defensive validation)", () => {
    expect(() => new FleetReconcileDaemon({
      supervisor: new StubFleet(),
      intervalMs: 5,
      logger: new CapturingLogger(),
    })).toThrow(/intervalMs must be >= 10/);
  });

  it("BACKDOOR: cycleCount + lastSnapshot are observable from outside (operator polling)", async () => {
    const fleet = new StubFleet();
    const daemon = new FleetReconcileDaemon({
      supervisor: fleet,
      intervalMs: 10,
      logger: new CapturingLogger(),
    });

    expect(daemon.cycleCount()).toBe(0);
    expect(daemon.lastSnapshot()).toBeUndefined();

    const runPromise = daemon.start();
    await waitFor(() => daemon.cycleCount() >= 2, 1_000);
    expect(daemon.lastSnapshot()).toBeDefined();
    expect(daemon.lastSnapshot()?.workingAgents).toBe(100);

    daemon.stop("test");
    await runPromise;
  });
});

async function waitFor(predicate: () => boolean, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  throw new Error(`waitFor timed out after ${timeoutMs}ms`);
}
