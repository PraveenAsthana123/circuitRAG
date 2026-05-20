// Iter 129 (2026-05-20): rollback-readiness validator that gates
// a deployment against the §47.7 4-layer rollback discipline AT
// BUILD TIME. A manifest bundle that passes evaluateRollbackReadiness()
// can be safely rolled back; one that fails has hard blockers
// listed before kubectl-apply touches the cluster.
//
// Companion to the operator runbook ROLLBACK.md. The runbook
// explains WHEN + HOW to roll back; this validator answers
// CAN we roll back? — a question every CD pipeline must answer
// BEFORE the deploy ships.
//
// Per CLAUDE.md §43 (drillable), §47.7 (4-layer rollback —
// app/DB/AI/infra), §52 row 6 trace-and-rollback, §57.7 (the
// "I claim it's rollback-safe" assertion is now drilled, not vibed).
//
// The 4 rollback layers (§47.7):
//   App     — kubectl set image / argo rollback to previous tag
//   DB      — expand→migrate→contract; never drop a column in the
//             same release that adds it
//   AI      — model + prompt registry rollback (registry.rollback())
//   Infra   — terraform state versioned; revert + apply

import type { FleetDaemonManifestBundle } from "./fleet-daemon-manifests";

export type RollbackLayer = "app" | "db" | "ai" | "infra";

export interface RollbackStep {
  readonly layer: RollbackLayer;
  /** Operator-runnable command. */
  readonly command: string;
  /** Estimated wall-clock for the step. */
  readonly estimatedSeconds: number;
  /** Why this step is necessary. */
  readonly rationale: string;
}

export interface RollbackReadinessReport {
  /** True iff there are no blockers. Warnings are OK. */
  readonly ready: boolean;
  /** Hard stops — must fix before deploy can be considered rollback-safe. */
  readonly blockers: ReadonlyArray<string>;
  /** Operational notes — deploy can ship but operator should know. */
  readonly warnings: ReadonlyArray<string>;
  /** Ordered rollback path the operator runs if revert is needed. */
  readonly rollbackPath: ReadonlyArray<RollbackStep>;
  /** Total estimated wall-clock for full rollback (app layer only). */
  readonly estimatedAppRollbackSeconds: number;
}

export interface RollbackEvaluateOptions {
  readonly bundle: FleetDaemonManifestBundle;
  /** Image tag the bundle is about to deploy. e.g. "registry/openclaw/fleet:v1.2.4" */
  readonly currentImageTag: string;
  /** Image tag the bundle would roll BACK to. e.g. "registry/openclaw/fleet:v1.2.3" */
  readonly previousImageTag: string;
}

export function evaluateRollbackReadiness(opts: RollbackEvaluateOptions): RollbackReadinessReport {
  const blockers: string[] = [];
  const warnings: string[] = [];

  // ─── §47.7 image-pinning discipline ────────────────────────
  if (opts.currentImageTag.endsWith(":latest")) {
    blockers.push("App: current image uses :latest — cannot pin rollback target (§47.7 image-pin rule)");
  }
  if (opts.previousImageTag.endsWith(":latest")) {
    blockers.push("App: previous image uses :latest — cannot guarantee rollback determinism (§47.7)");
  }
  if (opts.currentImageTag === opts.previousImageTag) {
    blockers.push("App: previousImageTag === currentImageTag — no rollback target to revert to");
  }
  if (!opts.currentImageTag.includes(":")) {
    blockers.push("App: current image has no tag — implicit :latest will be used (§47.7 forbids this)");
  }
  if (!opts.previousImageTag.includes(":")) {
    blockers.push("App: previous image has no tag — implicit :latest will be used (§47.7 forbids this)");
  }

  // ─── §47.7 RollingUpdate discipline ────────────────────────
  const deploySpec = opts.bundle.deployment.spec as {
    strategy?: { type?: string; rollingUpdate?: { maxUnavailable?: number; maxSurge?: number } };
    template: { spec: { terminationGracePeriodSeconds?: number; containers: Array<{ image?: string }> } };
  };
  const strategy = deploySpec.strategy;
  if (strategy?.type !== "RollingUpdate") {
    blockers.push(`App: Deployment.strategy.type must be RollingUpdate (got ${strategy?.type ?? "undefined"})`);
  }
  if (strategy?.rollingUpdate?.maxUnavailable !== 0) {
    blockers.push(`App: Deployment.strategy.rollingUpdate.maxUnavailable must be 0 (got ${strategy?.rollingUpdate?.maxUnavailable})`);
  }

  // ─── §47.8 grace period covers in-flight reconcile ─────────
  const grace = deploySpec.template.spec.terminationGracePeriodSeconds;
  if (grace === undefined || grace < 30) {
    blockers.push(`App: terminationGracePeriodSeconds must be set and >= 30 (got ${grace ?? "undefined"})`);
  }

  // ─── PodDisruptionBudget present ───────────────────────────
  if (!opts.bundle.podDisruptionBudget) {
    warnings.push("App: no PodDisruptionBudget — voluntary drain can take all replicas down at once");
  }

  // ─── Image consistency: manifest container image MUST match currentImageTag ─
  const containerImage = deploySpec.template.spec.containers[0]?.image;
  if (containerImage !== opts.currentImageTag) {
    blockers.push(`App: Deployment container image (${containerImage}) != currentImageTag (${opts.currentImageTag}) — bundle is out of sync`);
  }

  // ─── DB / AI / Infra layers ────────────────────────────────
  // The fleet daemon itself is stateless; these are warnings the
  // operator must verify in their deploying repo's release notes.
  warnings.push("DB: verify migration follows expand→migrate→contract; never drop columns added in same release (§47.7)");
  warnings.push("AI: if prompt/model registry version changed, ensure registry.rollback() is callable (§47.7 AI layer)");
  warnings.push("Infra: confirm terraform state is committed; revert is `terraform apply` of previous state (§47.7 infra layer)");

  // ─── Construct the rollback path ───────────────────────────
  const deployName = (opts.bundle.deployment.metadata as { name: string; namespace: string }).name;
  const namespace = (opts.bundle.deployment.metadata as { name: string; namespace: string }).namespace;
  const containerName = deploySpec.template.spec.containers[0] ? "fleet-daemon" : "container";

  const rollbackPath: RollbackStep[] = [
    {
      layer: "app",
      command: `kubectl rollout undo deployment/${deployName} -n ${namespace}`,
      estimatedSeconds: 30,
      rationale: "Reverts to the immediately previous ReplicaSet (K8s tracks history)",
    },
    {
      layer: "app",
      command: `kubectl set image deployment/${deployName} ${containerName}=${opts.previousImageTag} -n ${namespace}`,
      estimatedSeconds: 60,
      rationale: "Explicit revert to a specific previous tag (preferred over rollout undo when crossing multiple revisions)",
    },
    {
      layer: "app",
      command: `kubectl rollout status deployment/${deployName} -n ${namespace} --timeout=5m`,
      estimatedSeconds: 120,
      rationale: "Wait for rollback to converge; readiness probes drain old pods + admit new ones (§47.8)",
    },
  ];

  return {
    ready: blockers.length === 0,
    blockers,
    warnings,
    rollbackPath,
    estimatedAppRollbackSeconds: rollbackPath.reduce((sum, s) => sum + s.estimatedSeconds, 0),
  };
}
