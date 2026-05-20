// Iter 126 (2026-05-19): standalone CLI daemon that wraps
// AgentFleetSupervisor.reconcile() in a loop with graceful
// shutdown. Closes the gap explicitly flagged by the operator:
//
//   > "AgentFleetSupervisor is the in-code 100-agent control plane,
//   > but I did not see a repo CLI daemon that continuously calls
//   > fleet.reconcile() as a standalone process."
//
// Until this iter, the fleet supervisor only ran when embedded by
// a service / test harness — there was no operator path to "run
// the fleet" the way `ops_worker/worker.py --loop --interval 300`
// runs the Python ops worker. This iter ships the TypeScript
// equivalent.
//
// The daemon is built as a class (FleetReconcileDaemon) wrapping
// AgentFleetSupervisor so the loop logic is drillable in vitest
// WITHOUT spawning a subprocess. A thin runDaemonFromEnv() entry
// function wires the class to env vars + SIGTERM handlers for
// `node daemons/fleet-reconcile-daemon.js` operator use.
//
// Per CLAUDE.md §43 (drillable), §47.8 (3-probe pattern: this is
// the liveness-loop side of the Working-Ready snapshot), §52 (row
// 35 DR metrics: snapshot per cycle gives recoverability data),
// §57.7 (the operator-flagged gap is now drilled-closed, not just
// claimed).

import {
  AgentFleetSupervisor,
  AgentFleetSnapshot,
} from "../10-agent-workflow/agent-fleet";

/** Structural interface — accepts AgentFleetSupervisor AND any future
 *  fleet-supervisor adapter (e.g., K8sFleetSupervisor wrapping
 *  kubectl) that exposes the same reconcile() contract. Decoupling
 *  the daemon from the concrete AgentFleetSupervisor class is
 *  §52 row 23 boundary discipline. */
export interface ReconcilableFleet {
  reconcile(): Promise<AgentFleetSnapshot>;
}

export class DaemonAlreadyRunningError extends Error {
  constructor() {
    super("Daemon is already running");
    this.name = "DaemonAlreadyRunningError";
  }
}

export interface FleetReconcileDaemonLogger {
  /** Called per reconcile cycle with the snapshot + cycle metadata. */
  onCycle(event: FleetCycleEvent): void;
  /** Called when a reconcile cycle throws. Daemon continues. */
  onCycleError(event: FleetCycleErrorEvent): void;
  /** Called when start() begins and when graceful shutdown completes. */
  onLifecycle(event: FleetLifecycleEvent): void;
}

export interface FleetCycleEvent {
  readonly cycle: number;
  readonly snapshot: AgentFleetSnapshot;
  readonly cycleDurationMs: number;
  readonly timestamp: string;
}

export interface FleetCycleErrorEvent {
  readonly cycle: number;
  readonly errorName: string;
  readonly errorMessage: string;
  readonly timestamp: string;
}

export interface FleetLifecycleEvent {
  readonly phase: "starting" | "stopping" | "stopped";
  readonly reason?: string;
  readonly totalCycles: number;
  readonly timestamp: string;
}

/** Default logger — emits a single-line JSON per event to stdout.
 *  Matches the Component 3 telemetry convention so an OTel/log
 *  collector tail can ingest both streams uniformly. */
export class ConsoleFleetDaemonLogger implements FleetReconcileDaemonLogger {
  onCycle(event: FleetCycleEvent): void {
    process.stdout.write(JSON.stringify({ type: "fleet_reconcile", ...event }) + "\n");
  }
  onCycleError(event: FleetCycleErrorEvent): void {
    process.stdout.write(JSON.stringify({ type: "fleet_reconcile_error", ...event }) + "\n");
  }
  onLifecycle(event: FleetLifecycleEvent): void {
    process.stdout.write(JSON.stringify({ type: "fleet_daemon_lifecycle", ...event }) + "\n");
  }
}

export interface FleetReconcileDaemonOptions {
  readonly supervisor: ReconcilableFleet;
  readonly intervalMs: number;
  readonly logger?: FleetReconcileDaemonLogger;
}

export class FleetReconcileDaemon {
  private readonly logger: FleetReconcileDaemonLogger;
  private readonly intervalMs: number;
  private readonly supervisor: ReconcilableFleet;

  private running = false;
  private stopRequested = false;
  private stopReason?: string;
  private sleepCanceller?: () => void;
  private cycleCounter = 0;
  private lastSnapshotValue?: AgentFleetSnapshot;
  private inFlightReconcile?: Promise<void>;

  constructor(opts: FleetReconcileDaemonOptions) {
    if (opts.intervalMs < 10) {
      throw new Error(`intervalMs must be >= 10 (got ${opts.intervalMs})`);
    }
    this.supervisor = opts.supervisor;
    this.intervalMs = opts.intervalMs;
    this.logger = opts.logger ?? new ConsoleFleetDaemonLogger();
  }

  /** Returns when the loop exits (stop() called + in-flight cycle drained). */
  async start(): Promise<void> {
    if (this.running) throw new DaemonAlreadyRunningError();
    this.running = true;
    this.stopRequested = false;
    this.stopReason = undefined;

    this.logger.onLifecycle({
      phase: "starting",
      totalCycles: this.cycleCounter,
      timestamp: new Date().toISOString(),
    });

    while (!this.stopRequested) {
      const cycleNumber = ++this.cycleCounter;
      const cycleStart = Date.now();
      const reconcilePromise = this.runOneCycle(cycleNumber, cycleStart);
      this.inFlightReconcile = reconcilePromise;
      await reconcilePromise;
      this.inFlightReconcile = undefined;

      if (this.stopRequested) break;
      await this.cancellableSleep(this.intervalMs);
    }

    this.running = false;
    this.logger.onLifecycle({
      phase: "stopped",
      reason: this.stopReason,
      totalCycles: this.cycleCounter,
      timestamp: new Date().toISOString(),
    });
  }

  /** Request graceful shutdown. In-flight reconcile completes; the
   *  daemon then exits its loop. Subsequent sleeps cancel immediately. */
  stop(reason: string): void {
    if (!this.running) return;
    this.stopRequested = true;
    this.stopReason = reason;
    this.logger.onLifecycle({
      phase: "stopping",
      reason,
      totalCycles: this.cycleCounter,
      timestamp: new Date().toISOString(),
    });
    // Cancel any active sleep so the loop checks stopRequested immediately.
    if (this.sleepCanceller) this.sleepCanceller();
  }

  cycleCount(): number {
    return this.cycleCounter;
  }

  lastSnapshot(): AgentFleetSnapshot | undefined {
    return this.lastSnapshotValue;
  }

  isRunning(): boolean {
    return this.running;
  }

  private async runOneCycle(cycle: number, startMs: number): Promise<void> {
    try {
      const snapshot = await this.supervisor.reconcile();
      this.lastSnapshotValue = snapshot;
      this.logger.onCycle({
        cycle,
        snapshot,
        cycleDurationMs: Date.now() - startMs,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      // §57.7 honesty: a single failed reconcile MUST NOT crash the
      // daemon. The next cycle is the recovery attempt. Production
      // operators monitor onCycleError frequency.
      this.logger.onCycleError({
        cycle,
        errorName: err instanceof Error ? err.name : "Unknown",
        errorMessage: err instanceof Error ? err.message : String(err),
        timestamp: new Date().toISOString(),
      });
    }
  }

  /** Sleep that resolves immediately if stop() fires during the wait. */
  private cancellableSleep(ms: number): Promise<void> {
    return new Promise<void>((resolve) => {
      const handle = setTimeout(() => {
        this.sleepCanceller = undefined;
        resolve();
      }, ms);
      this.sleepCanceller = () => {
        clearTimeout(handle);
        this.sleepCanceller = undefined;
        resolve();
      };
    });
  }
}

// ───────────────────────────── CLI entry ─────────────────────────────

/** Wires the daemon to env vars + SIGTERM/SIGINT handlers for
 *  `node daemons/fleet-reconcile-daemon.js` operator use.
 *
 *  Env vars:
 *    FLEET_DESIRED_AGENTS    — default 100
 *    FLEET_RECONCILE_INTERVAL_MS — default 30000 (30s)
 *
 *  The caller MUST provide a supervisorFactory because that's the
 *  point where production replaces the default AgentSupervisor with
 *  whatever runtime backing it wants (K8s pod, in-process worker,
 *  etc.). This entry is for operator wiring; the actual factory
 *  comes from the deploying service. */
export function runDaemonFromEnv(
  buildSupervisor: () => AgentFleetSupervisor,
): FleetReconcileDaemon {
  const intervalMs = Number(process.env.FLEET_RECONCILE_INTERVAL_MS ?? 30_000);
  const daemon = new FleetReconcileDaemon({
    supervisor: buildSupervisor(),
    intervalMs,
  });

  const shutdown = (signal: string) => {
    daemon.stop(`signal:${signal}`);
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));

  return daemon;
}
