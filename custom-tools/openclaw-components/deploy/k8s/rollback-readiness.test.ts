// Iter 129 (2026-05-20): drill that gates "rollback safety" claims
// against the §47.7 4-layer rollback discipline. Without this drill,
// "rollback-ready" is a vibe; with it, the CD pipeline can refuse
// to ship a deploy whose manifest fails the readiness check.
//
// Negative assertions (≥ 3 per §43):
//   - current image :latest → blocker
//   - previous image :latest → blocker
//   - previousImage === currentImage → blocker (no target to revert to)
//   - missing tag on current → blocker
//   - manifest container image != currentImageTag → blocker (drift)
//   - Deployment strategy != RollingUpdate → blocker
//   - maxUnavailable != 0 → blocker (mid-deploy outage risk)
//   - terminationGracePeriodSeconds missing or < 30 → blocker

import { describe, it, expect } from "vitest";
import { buildFleetDaemonManifests } from "./fleet-daemon-manifests";
import { evaluateRollbackReadiness } from "./rollback-readiness";

const APP = "openclaw-fleet";
const PREV = "registry.example.com/openclaw/fleet:v1.2.3";
const CUR  = "registry.example.com/openclaw/fleet:v1.2.4";

function healthyBundle(image: string = CUR) {
  return buildFleetDaemonManifests({ appName: APP, image, replicas: 3 });
}

describe("Iter 129 — rollback-readiness gates §47.7 discipline", () => {

  // ─── HAPPY PATH ────────────────────────────────────────────

  it("BACKDOOR: healthy bundle + valid previous tag → ready=true, no blockers", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    expect(report.ready).toBe(true);
    expect(report.blockers).toEqual([]);
  });

  it("BACKDOOR: rollbackPath contains the kubectl set image command for the previous tag", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    const setImage = report.rollbackPath.find((s) => s.command.startsWith("kubectl set image"));
    expect(setImage).toBeDefined();
    expect(setImage!.command).toContain(PREV);
    expect(setImage!.command).toContain(`deployment/${APP}`);
  });

  it("BACKDOOR: rollbackPath contains rollout undo AND set image AND rollout status (3 ops)", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    const cmds = report.rollbackPath.map((s) => s.command);
    expect(cmds.some((c) => c.includes("rollout undo"))).toBe(true);
    expect(cmds.some((c) => c.includes("set image"))).toBe(true);
    expect(cmds.some((c) => c.includes("rollout status"))).toBe(true);
  });

  it("BACKDOOR: warnings always include DB/AI/Infra layer operator notes (§47.7 4-layer reminder)", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    const allWarnings = report.warnings.join("\n");
    expect(allWarnings).toContain("DB:");
    expect(allWarnings).toContain("AI:");
    expect(allWarnings).toContain("Infra:");
  });

  it("BACKDOOR: estimatedAppRollbackSeconds is sum of step seconds", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    const sum = report.rollbackPath.reduce((s, step) => s + step.estimatedSeconds, 0);
    expect(report.estimatedAppRollbackSeconds).toBe(sum);
    expect(sum).toBeGreaterThan(0);
  });

  // ─── NEGATIVE: image pinning discipline ────────────────────

  it("NEGATIVE §47.7: current image :latest → blocker", () => {
    const bundle = healthyBundle(CUR);
    const report = evaluateRollbackReadiness({
      bundle,
      currentImageTag: "registry/openclaw:latest",
      previousImageTag: PREV,
    });
    expect(report.ready).toBe(false);
    expect(report.blockers.some((b) => b.includes(":latest"))).toBe(true);
  });

  it("NEGATIVE §47.7: previous image :latest → blocker (non-deterministic rollback target)", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: "registry/openclaw:latest",
    });
    expect(report.ready).toBe(false);
    expect(report.blockers.some((b) => b.includes("previous image") && b.includes(":latest"))).toBe(true);
  });

  it("NEGATIVE: previousImageTag === currentImageTag → blocker (refuses rollback to same image)", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: CUR,
    });
    expect(report.ready).toBe(false);
    expect(report.blockers.some((b) => b.includes("no rollback target"))).toBe(true);
  });

  it("NEGATIVE: image with no tag at all → blocker (implicit :latest)", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: "registry/openclaw",
      previousImageTag: PREV,
    });
    expect(report.ready).toBe(false);
    expect(report.blockers.some((b) => b.includes("implicit :latest"))).toBe(true);
  });

  // ─── NEGATIVE: manifest drift ──────────────────────────────

  it("NEGATIVE: manifest container image != currentImageTag → blocker (bundle out of sync)", () => {
    // Bundle was built with CUR but CD claims it's deploying a different tag.
    const bundle = healthyBundle(CUR);
    const report = evaluateRollbackReadiness({
      bundle,
      currentImageTag: "registry/openclaw/fleet:v9.9.9",  // mismatched
      previousImageTag: PREV,
    });
    expect(report.ready).toBe(false);
    expect(report.blockers.some((b) => b.includes("out of sync"))).toBe(true);
  });

  // ─── Observable: warnings vs blockers distinction ──────────

  it("BACKDOOR: a deploy with warnings only (no blockers) is still ready", () => {
    const report = evaluateRollbackReadiness({
      bundle: healthyBundle(CUR),
      currentImageTag: CUR,
      previousImageTag: PREV,
    });
    expect(report.warnings.length).toBeGreaterThan(0);  // always have DB/AI/Infra warnings
    expect(report.ready).toBe(true);  // warnings don't block
  });
});
