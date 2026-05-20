// Iter 127 (2026-05-20): Kubernetes-compatible 3-probe health
// endpoints for the FleetReconcileDaemon (iter 126). Implements
// the CLAUDE.md §47.8 3-probe pattern:
//
//   STARTUP    "Have I finished booting?"
//              Ready iff cycleCount() >= 1.
//              K8s does not run liveness/readiness until startup succeeds.
//
//   LIVENESS   "Am I alive?"  — DUMB process check
//              Ready iff daemon.isRunning() === true.
//              MUST NOT check fleet/agent/dep state. Per §47.8:
//              "liveness checking deps causes cascade pod restarts."
//              A degraded fleet (some workers down) is a readiness
//              signal, NOT a liveness signal.
//
//   READINESS  "Can I serve right now?"  — SMART dependency check
//              Ready iff lastSnapshot().allAgentsWorking === true
//              AND startup completed (cycleCount() >= 1).
//              A pod that fails readiness is removed from service
//              endpoints but NOT restarted — exactly what we want
//              when the fleet is reconciling.
//
// Per CLAUDE.md §43 (drillable), §47.8 (3-probe semantics),
// §52 row 23 (boundary integration: probes depend on a structural
// ReadableFleetState, not the concrete daemon class), §57.7
// (drilled invariants — esp. the §47.8 "liveness never checks
// deps" rule is the locked negative assertion).
//
// This module ships the EVALUATION logic only. Wiring it to a
// real HTTP server (http.createServer / fastify / express) is
// the deploying service's job — the daemon stays HTTP-server
// agnostic (composition root concern).

import type { AgentFleetSnapshot } from "../10-agent-workflow/agent-fleet";

/** Structural interface — daemon (or any future fleet adapter)
 *  exposing the operator-polling surface satisfies this. */
export interface ReadableFleetState {
  isRunning(): boolean;
  cycleCount(): number;
  lastSnapshot(): AgentFleetSnapshot | undefined;
}

export type ProbeKind = "startup" | "liveness" | "readiness";

export type ProbeStatus = "ok" | "starting" | "degraded" | "dead";

export interface ProbeResult {
  readonly probe: ProbeKind;
  readonly status: ProbeStatus;
  readonly httpCode: 200 | 503;
  readonly cycles: number;
  readonly snapshot?: AgentFleetSnapshot;
  readonly reason?: string;
  readonly timestamp: string;
}

export class UnknownProbeKindError extends Error {
  constructor(kind: string) {
    super(`Unknown probe kind: ${kind}`);
    this.name = "UnknownProbeKindError";
  }
}

export class FleetHealthProbe {
  constructor(private readonly fleet: ReadableFleetState) {}

  evaluate(kind: ProbeKind): ProbeResult {
    switch (kind) {
      case "startup":   return this.evaluateStartup();
      case "liveness":  return this.evaluateLiveness();
      case "readiness": return this.evaluateReadiness();
      default:
        throw new UnknownProbeKindError(kind);
    }
  }

  /** STARTUP — has the daemon booted at least once?
   *  Returns 200 once cycleCount() >= 1, 503 before that. */
  private evaluateStartup(): ProbeResult {
    const cycles = this.fleet.cycleCount();
    const ready = cycles >= 1;
    return this.build("startup", ready, ready ? undefined : "no reconcile cycle completed yet");
  }

  /** LIVENESS — is the process loop alive? Dumb check only.
   *  MUST NOT inspect fleet/dep state per §47.8. */
  private evaluateLiveness(): ProbeResult {
    const alive = this.fleet.isRunning();
    return this.build("liveness", alive, alive ? undefined : "daemon loop is not running");
  }

  /** READINESS — can the fleet serve right now?
   *  Smart dep check: startup completed AND allAgentsWorking. */
  private evaluateReadiness(): ProbeResult {
    const cycles = this.fleet.cycleCount();
    if (cycles < 1) {
      return this.build("readiness", false, "startup not yet completed");
    }
    const snapshot = this.fleet.lastSnapshot();
    if (!snapshot) {
      return this.build("readiness", false, "no snapshot recorded yet");
    }
    if (!snapshot.allAgentsWorking) {
      return this.build(
        "readiness",
        false,
        `${snapshot.notWorkingAgents}/${snapshot.desiredActiveAgents} agents not yet working`,
      );
    }
    return this.build("readiness", true);
  }

  private build(probe: ProbeKind, ready: boolean, reason?: string): ProbeResult {
    return {
      probe,
      status: this.statusFor(probe, ready),
      httpCode: ready ? 200 : 503,
      cycles: this.fleet.cycleCount(),
      snapshot: this.fleet.lastSnapshot(),
      reason,
      timestamp: new Date().toISOString(),
    };
  }

  private statusFor(probe: ProbeKind, ready: boolean): ProbeStatus {
    if (ready) return "ok";
    if (probe === "startup")  return "starting";
    if (probe === "liveness") return "dead";
    return "degraded";  // readiness failure
  }
}
