// Iter 128 (2026-05-20): drills the K8s manifest factories to lock
// the §47.7 + §47.8 invariants at build time. A malformed manifest
// shipped to kubectl wastes minutes on rollback; failing the
// drill at PR time costs seconds.
//
// Negative assertions (≥ 3 per §43):
//   - image with :latest tag throws (§47.7 — can't pin rollback to floating tag)
//   - pdbMinAvailable >= replicas throws (would block all voluntary drains)
//   - hpa.maxReplicas < minReplicas throws
//   - appName with uppercase/underscore throws (K8s naming rules)
//   - livenessProbe path is /healthz (NOT /readyz — proves the
//     §47.8 dumb-vs-smart split is wired correctly)
//   - readinessProbe path is /readyz (NOT /healthz)
//   - terminationGracePeriodSeconds >= 2× reconcileInterval

import { describe, it, expect } from "vitest";
import {
  buildFleetDaemonManifests,
  FleetDaemonDeployOptions,
} from "./fleet-daemon-manifests";

const BASE: FleetDaemonDeployOptions = {
  appName: "openclaw-fleet",
  image: "registry.example.com/openclaw/fleet:v1.2.3",
};

describe("Iter 128 — Fleet daemon K8s manifests", () => {
  it("BACKDOOR: produces a complete bundle (Deployment + Service + PDB + NetworkPolicy)", () => {
    const m = buildFleetDaemonManifests(BASE);
    expect(m.deployment.kind).toBe("Deployment");
    expect(m.service.kind).toBe("Service");
    expect(m.podDisruptionBudget.kind).toBe("PodDisruptionBudget");
    expect(m.networkPolicy.kind).toBe("NetworkPolicy");
    expect(m.horizontalPodAutoscaler).toBeUndefined();  // only emitted when opts.hpa set
  });

  it("BACKDOOR: HPA is emitted when hpa option provided", () => {
    const m = buildFleetDaemonManifests({ ...BASE, hpa: { minReplicas: 2, maxReplicas: 10 } });
    expect(m.horizontalPodAutoscaler?.kind).toBe("HorizontalPodAutoscaler");
    const spec = m.horizontalPodAutoscaler!.spec as { minReplicas: number; maxReplicas: number };
    expect(spec.minReplicas).toBe(2);
    expect(spec.maxReplicas).toBe(10);
  });

  it("BACKDOOR §47.8: livenessProbe maps to /healthz (the DUMB endpoint)", () => {
    const m = buildFleetDaemonManifests(BASE);
    const containers = (m.deployment.spec as { template: { spec: { containers: Array<Record<string, unknown>> } } }).template.spec.containers;
    const liveness = containers[0].livenessProbe as { httpGet: { path: string } };
    expect(liveness.httpGet.path).toBe("/healthz");
  });

  it("BACKDOOR §47.8: readinessProbe maps to /readyz (the SMART endpoint)", () => {
    const m = buildFleetDaemonManifests(BASE);
    const containers = (m.deployment.spec as { template: { spec: { containers: Array<Record<string, unknown>> } } }).template.spec.containers;
    const readiness = containers[0].readinessProbe as { httpGet: { path: string } };
    expect(readiness.httpGet.path).toBe("/readyz");
  });

  it("BACKDOOR §47.8: startupProbe maps to /healthz/start", () => {
    const m = buildFleetDaemonManifests(BASE);
    const containers = (m.deployment.spec as { template: { spec: { containers: Array<Record<string, unknown>> } } }).template.spec.containers;
    const startup = containers[0].startupProbe as { httpGet: { path: string } };
    expect(startup.httpGet.path).toBe("/healthz/start");
  });

  it("NEGATIVE §47.8: livenessProbe path is NEVER /readyz (cascade-restart prevention)", () => {
    // If a future refactor accidentally swaps the paths, this drill
    // fires. The §47.8 hard rule depends on liveness checking dumb
    // and readiness checking deps — confusing them inverts the
    // safety properties.
    const m = buildFleetDaemonManifests(BASE);
    const containers = (m.deployment.spec as { template: { spec: { containers: Array<Record<string, unknown>> } } }).template.spec.containers;
    const liveness = containers[0].livenessProbe as { httpGet: { path: string } };
    expect(liveness.httpGet.path).not.toBe("/readyz");
  });

  it("BACKDOOR §47.7: terminationGracePeriodSeconds is >= 2× reconcileIntervalMs (graceful shutdown)", () => {
    const m = buildFleetDaemonManifests({ ...BASE, reconcileIntervalMs: 30_000 });
    const grace = (m.deployment.spec as { template: { spec: { terminationGracePeriodSeconds: number } } }).template.spec.terminationGracePeriodSeconds;
    expect(grace).toBeGreaterThanOrEqual(60);  // 2 × 30s
  });

  it("BACKDOOR §47.7: deployment uses RollingUpdate with maxUnavailable=0", () => {
    const m = buildFleetDaemonManifests(BASE);
    const strategy = (m.deployment.spec as { strategy: { type: string; rollingUpdate: { maxUnavailable: number } } }).strategy;
    expect(strategy.type).toBe("RollingUpdate");
    expect(strategy.rollingUpdate.maxUnavailable).toBe(0);  // never lose all replicas mid-deploy
  });

  it("BACKDOOR §47.8: pod runs as non-root with readOnlyRootFilesystem + no privilege escalation", () => {
    const m = buildFleetDaemonManifests(BASE);
    const podSpec = (m.deployment.spec as { template: { spec: { securityContext: Record<string, unknown>; containers: Array<{ securityContext: Record<string, unknown> }> } } }).template.spec;
    expect(podSpec.securityContext.runAsNonRoot).toBe(true);
    expect(podSpec.containers[0].securityContext.allowPrivilegeEscalation).toBe(false);
    expect(podSpec.containers[0].securityContext.readOnlyRootFilesystem).toBe(true);
  });

  it("BACKDOOR: env carries FLEET_RECONCILE_INTERVAL_MS + FLEET_DESIRED_AGENTS", () => {
    const m = buildFleetDaemonManifests({ ...BASE, reconcileIntervalMs: 45_000, desiredAgents: 250 });
    const env = (m.deployment.spec as { template: { spec: { containers: Array<{ env: Array<{ name: string; value: string }> }> } } }).template.spec.containers[0].env;
    const envMap = Object.fromEntries(env.map((e) => [e.name, e.value]));
    expect(envMap.FLEET_RECONCILE_INTERVAL_MS).toBe("45000");
    expect(envMap.FLEET_DESIRED_AGENTS).toBe("250");
  });

  it("BACKDOOR: PDB selector matches Deployment labels (cross-manifest consistency)", () => {
    const m = buildFleetDaemonManifests(BASE);
    const deployLabels = (m.deployment.spec as { selector: { matchLabels: Record<string, string> } }).selector.matchLabels;
    const pdbSelector = (m.podDisruptionBudget.spec as { selector: { matchLabels: Record<string, string> } }).selector.matchLabels;
    expect(pdbSelector).toEqual(deployLabels);
  });

  it("BACKDOOR: Service selector matches Deployment labels (cross-manifest consistency)", () => {
    const m = buildFleetDaemonManifests(BASE);
    const deployLabels = (m.deployment.spec as { selector: { matchLabels: Record<string, string> } }).selector.matchLabels;
    const svcSelector = (m.service.spec as { selector: Record<string, string> }).selector;
    expect(svcSelector).toEqual(deployLabels);
  });

  // ─── Defensive validation ─────────────────────────────────────

  it("NEGATIVE §47.7: image with :latest tag throws (rollback discipline)", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, image: "registry/openclaw:latest" }))
      .toThrow(/must NOT use :latest tag/);
  });

  it("NEGATIVE: missing image throws", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, image: "" }))
      .toThrow();
  });

  it("NEGATIVE: appName with uppercase/underscore throws (K8s naming rules)", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, appName: "MyFleet" }))
      .toThrow(/lowercase alphanumeric/);
    expect(() => buildFleetDaemonManifests({ ...BASE, appName: "my_fleet" }))
      .toThrow(/lowercase alphanumeric/);
  });

  it("NEGATIVE: pdbMinAvailable >= replicas throws (would block voluntary drains forever)", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, replicas: 3, pdbMinAvailable: 3 }))
      .toThrow(/pdbMinAvailable MUST be < replicas/);
    expect(() => buildFleetDaemonManifests({ ...BASE, replicas: 3, pdbMinAvailable: 5 }))
      .toThrow(/pdbMinAvailable MUST be < replicas/);
  });

  it("NEGATIVE: hpa.maxReplicas < minReplicas throws", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, hpa: { minReplicas: 5, maxReplicas: 2 } }))
      .toThrow(/maxReplicas must be >= hpa.minReplicas/);
  });

  it("NEGATIVE: replicas < 1 throws", () => {
    expect(() => buildFleetDaemonManifests({ ...BASE, replicas: 0 }))
      .toThrow(/replicas must be >= 1/);
  });

  // ─── Observable: bundle round-trips through JSON.stringify (kubectl-applyable) ─

  it("BACKDOOR: full bundle JSON-serializes cleanly (kubectl apply ready)", () => {
    const m = buildFleetDaemonManifests({ ...BASE, replicas: 3, hpa: { minReplicas: 2, maxReplicas: 10 } });
    const serialized = JSON.stringify(m);
    const parsed = JSON.parse(serialized);
    expect(parsed.deployment.kind).toBe("Deployment");
    expect(parsed.horizontalPodAutoscaler.kind).toBe("HorizontalPodAutoscaler");
  });
});
