# Fleet daemon — deployment rollback runbook

> Closes GAPS.md P0 row "deployment rollback path missing."
> Composes with iter 126 (daemon) + iter 127 (probes) + iter 128 (K8s
> manifests) + iter 129 (`rollback-readiness.ts` validator).
>
> Per CLAUDE.md §47.7 four-layer rollback discipline.

## TL;DR

```bash
# 1. Verify rollback-readiness BEFORE deploy
npx tsx -e 'import { buildFleetDaemonManifests } from "./fleet-daemon-manifests"; \
  import { evaluateRollbackReadiness } from "./rollback-readiness"; \
  const r = evaluateRollbackReadiness({ \
    bundle: buildFleetDaemonManifests({ appName: "openclaw-fleet", image: "registry/openclaw:v1.2.4" }), \
    currentImageTag: "registry/openclaw:v1.2.4", \
    previousImageTag: "registry/openclaw:v1.2.3" }); \
  if (!r.ready) { console.error(r.blockers); process.exit(1); }'

# 2. If readiness passes, deploy
kubectl apply -f out/*.yaml

# 3. If revert is needed
kubectl rollout undo deployment/openclaw-fleet -n default
# OR explicit:
kubectl set image deployment/openclaw-fleet fleet-daemon=registry/openclaw:v1.2.3 -n default
kubectl rollout status deployment/openclaw-fleet -n default --timeout=5m
```

## Pre-deploy rollback-readiness gate

Every CD pipeline MUST call `evaluateRollbackReadiness()` BEFORE
`kubectl apply`. It returns `{ready, blockers, warnings, rollbackPath}`.
If `ready === false`, the pipeline MUST fail. The blockers list is
the operator-actionable fix-list.

The validator enforces 5 §47.7 invariants at build time:

| Invariant | Why |
|---|---|
| No `:latest` tag on current OR previous image | Floating tags can't pin a rollback target |
| `previousImageTag !== currentImageTag` | Refusing rollback to identical image |
| `Deployment.strategy.type === "RollingUpdate"` | Recreate strategy = total outage during deploy |
| `rollingUpdate.maxUnavailable === 0` | Prevent all replicas down mid-deploy |
| `terminationGracePeriodSeconds >= 30` | Cover the iter 126 daemon's sleep-cancel + in-flight-cycle grace |

## §47.7 four-layer rollback model

K8s rollback only covers the App layer. The other three layers
(DB, AI, Infra) need their own runbooks. The validator emits
warnings reminding the operator to check each.

| Layer | What it covers | Tool | Strategy |
|---|---|---|---|
| **App** | Deployment image, pod spec | `kubectl rollout undo` / `kubectl set image` | Blue-green / canary / RollingUpdate maxUnavailable=0 |
| **DB** | Schema migrations, data | Flyway / Liquibase / Alembic | Expand → Migrate → Contract — NEVER drop a column in the same release that adds it |
| **AI** | Model + prompt registry version | `registry.rollback(modelId, version)` | Model registry must support semver rollback; canary before promote |
| **Infra** | Terraform state, K8s namespace, IAM | `terraform apply` of previous state | Terraform state MUST be committed before deploy; revert = `terraform apply` of prior commit |

**Hard rule:** if you cannot rollback ALL FOUR layers in < 30 minutes,
the release is NOT rollback-safe. Don't ship.

## Rollback decision tree

```
  Deploy alarm fires (latency p95 > SLA, error rate > 1%, fleet workingAgents < 95)
                              │
                              ▼
            Is the issue clearly the new deploy? ──── NO ──► Investigate FIRST.
                              │                                    Don't rollback blindly.
                            YES
                              │
                              ▼
            Did the new deploy touch DB schema?  ──── YES ──► STOP. Use the DB
                              │                                rollback runbook
                              │                                (expand/migrate/contract).
                            NO  │                                Coordinate with DBA.
                              │
                              ▼
            Did it change the prompt/model       ──── YES ──► Roll back AI layer first
            registry version?                              (registry.rollback) THEN App.
                              │                            Out-of-order = stale prompts
                            NO                              hitting new app code.
                              │
                              ▼
            App-only rollback (the common case):
                              │
                              ▼
            kubectl rollout undo deployment/openclaw-fleet -n default
              ─ OR ─
            kubectl set image deployment/openclaw-fleet \
                fleet-daemon=<previous-pinned-tag> -n default
                              │
                              ▼
            kubectl rollout status deployment/openclaw-fleet \
                -n default --timeout=5m
                              │
                              ▼
            VERIFY:
              kubectl get pods -n default -l app=openclaw-fleet
              curl -s http://<service-cluster-ip>:8080/readyz | jq .
                              │
                              ▼
            Is /readyz returning 200 AND snapshot.allAgentsWorking=true?
              YES → rollback complete. Update incident log.
              NO  → readiness still failing — check daemon logs:
                    kubectl logs -n default -l app=openclaw-fleet --tail=100
                    Did the previous image have the same bug? Escalate.
```

## What the iter 126 daemon does during rollback

The §47.8 contract from iter 126's drill #5 + iter 127's drill #5:

1. **K8s sends SIGTERM** to the old pod.
2. **Daemon's `stop("signal:SIGTERM")` fires** — sets stopRequested flag, cancels any in-flight sleep, awaits in-flight reconcile.
3. **`terminationGracePeriodSeconds`** (default 60s, computed as 2× `reconcileIntervalMs`) gives the in-flight reconcile time to complete.
4. **Readiness probe starts returning 503** during shutdown (daemon stops emitting snapshot updates).
5. **K8s drains traffic** from the old pod (readiness=false → removed from Service endpoints).
6. **New pod boots, startupProbe runs** until first reconcile completes.
7. **New pod's readiness flips to 200**, K8s adds it to Service endpoints.
8. **Old pod exits cleanly** (or is SIGKILL'd if grace period exceeded).

If the rollback target image has a faster startup, the rollout
completes in ~120s. If slower, allow up to 5min via `--timeout=5m`.

## Verification commands (post-rollback)

```bash
# Replica count matches desired
kubectl get deployment openclaw-fleet -n default -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'

# All pods running the previous image tag
kubectl get pods -n default -l app=openclaw-fleet \
    -o jsonpath='{.items[*].spec.containers[0].image}' | tr ' ' '\n'

# Readiness probe returns 200 on at least one pod
for pod in $(kubectl get pods -n default -l app=openclaw-fleet -o name); do
  kubectl exec -n default "$pod" -- wget -qO- http://localhost:8080/readyz | jq -e '.status == "ok"'
done

# fleet_reconcile log line is fresh (within last interval)
kubectl logs -n default -l app=openclaw-fleet --tail=5 | grep fleet_reconcile
```

## What can go wrong (and what to do)

| Symptom | Likely cause | Action |
|---|---|---|
| `kubectl rollout undo` fails with "no rollout history" | `revisionHistoryLimit` exhausted | Use explicit `kubectl set image` with the previous tag |
| New pods stuck in `Pending` | Insufficient cluster resources OR PDB blocking | Check `kubectl describe pod`; check PDB `currentHealthy` vs `disruptionsAllowed` |
| Readiness probe never goes 200 after rollback | Previous image had the same bug OR config issue | Roll forward to known-good earlier tag; check ConfigMap/Secret versions |
| Old pods refuse to terminate | Daemon stuck in long reconcile | Confirm `terminationGracePeriodSeconds` is sufficient; check daemon logs for `fleet_reconcile_error` |
| Fleet `notWorkingAgents > 0` after rollback | Worker agents in degraded state | Wait for next reconcile cycle; check individual `AgentSupervisor` snapshots |
| Cascade pod restarts | livenessProbe wired to `/readyz` (cascade-restart bug) | Run `npm test -- deploy/k8s/` to verify drill #6; fix manifest if drill fails |

## Composes with

- [iter 126 — FleetReconcileDaemon](../../daemons/fleet-reconcile-daemon.ts) — the daemon being rolled back
- [iter 127 — FleetHealthProbe](../../probes/fleet-health-probe.ts) — the readiness signal that gates the rollout
- [iter 128 — manifest factories](./fleet-daemon-manifests.ts) — the manifests being applied
- [iter 129 — rollback-readiness validator](./rollback-readiness.ts) — the pre-deploy gate
- CLAUDE.md §47.7 — the 4-layer rollback discipline
- CLAUDE.md §47.8 — the 3-probe pattern that makes graceful rollout possible
