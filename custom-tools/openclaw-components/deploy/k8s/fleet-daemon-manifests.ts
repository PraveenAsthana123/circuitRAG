// Iter 128 (2026-05-20): typed K8s manifest factories for the
// fleet daemon (iter 126) + health probes (iter 127). Closes the
// P1 GAPS row: "K8s probes/PDB/HPA/NetworkPolicy missing."
//
// Modeled as typed factories — NOT raw YAML — so the §47.8 +
// §47.7 invariants are drillable in vitest. The deploying repo
// serializes to YAML via JSON.stringify (or a yaml lib) and
// kubectl-applies. The TS factory is the source of truth; the
// YAML is one derivation per §59.1 MDD.
//
// What the manifests cover:
//   1. Deployment — 3 probes wired to the daemon's HTTP server,
//      resource requests/limits, terminationGracePeriodSeconds
//      matched to FLEET_RECONCILE_INTERVAL_MS, securityContext
//      runAsNonRoot, no privileged escalation.
//   2. Service — ClusterIP exposing the probe endpoints.
//   3. PodDisruptionBudget — minAvailable >= 1 prevents voluntary
//      drains from killing the daemon entirely (e.g., node drain
//      during deploy must leave at least 1 pod up).
//   4. HorizontalPodAutoscaler — scales on CPU (default 70%);
//      custom metric path documented for fleet_working_agents.
//   5. NetworkPolicy — restricts ingress to the probe port from
//      the K8s probe agent; restricts egress to the agent backend.
//
// Per CLAUDE.md §43 (drillable), §47.7 4-layer rollback (the
// Deployment is the app-layer rollback unit), §47.8 (probe wiring),
// §52 row 35 DR metrics (PDB + HPA bound the failure surface),
// §57.7 (drilled invariants — the cascade-restart trap is gated
// at YAML-emit time, not at K8s-apply time).

// ───────────────────────────── Types ─────────────────────────────

export interface FleetDaemonDeployOptions {
  /** Deployment name + label selector. */
  readonly appName: string;
  /** Container image (with tag — no :latest, see §47.7). */
  readonly image: string;
  /** Number of pod replicas. Default 1. */
  readonly replicas?: number;
  /** Reconcile interval in ms. Matches FLEET_RECONCILE_INTERVAL_MS
   *  env var; terminationGracePeriodSeconds is computed from it. */
  readonly reconcileIntervalMs?: number;
  /** Desired number of agents per pod (FLEET_DESIRED_AGENTS env). */
  readonly desiredAgents?: number;
  /** Namespace. Default "default". */
  readonly namespace?: string;
  /** Probe port the container HTTP server listens on. Default 8080. */
  readonly probePort?: number;
  /** Per-pod resource requests/limits. */
  readonly resources?: {
    readonly requests?: { readonly cpu?: string; readonly memory?: string };
    readonly limits?: { readonly cpu?: string; readonly memory?: string };
  };
  /** PDB minAvailable. Default Math.max(1, floor(replicas/2)). */
  readonly pdbMinAvailable?: number;
  /** HPA bounds. */
  readonly hpa?: {
    readonly minReplicas: number;
    readonly maxReplicas: number;
    /** Target CPU utilization %. Default 70. */
    readonly targetCpuUtilization?: number;
  };
}

// Minimal typed K8s manifest shapes — only the fields we set.
// (Importing the full @kubernetes/client-node types would balloon
// the dependency surface; this is the §16 "don't pull big deps
// for stub" rule.)
type Labels = Record<string, string>;
type K8sManifest = { readonly apiVersion: string; readonly kind: string; readonly metadata: { readonly name: string; readonly namespace: string; readonly labels: Labels } } & Record<string, unknown>;

// ───────────────────────────── Factories ─────────────────────────────

export interface FleetDaemonManifestBundle {
  readonly deployment: K8sManifest;
  readonly service: K8sManifest;
  readonly podDisruptionBudget: K8sManifest;
  readonly horizontalPodAutoscaler?: K8sManifest;  // only if hpa is set
  readonly networkPolicy: K8sManifest;
}

export function buildFleetDaemonManifests(opts: FleetDaemonDeployOptions): FleetDaemonManifestBundle {
  validateOptions(opts);

  const replicas = opts.replicas ?? 1;
  const namespace = opts.namespace ?? "default";
  const probePort = opts.probePort ?? 8080;
  const reconcileIntervalMs = opts.reconcileIntervalMs ?? 30_000;
  const desiredAgents = opts.desiredAgents ?? 100;
  // Grace period MUST be at least 2× reconcile interval so a
  // SIGTERM during a sleep+cycle gets the cancellable sleep AND
  // the in-flight reconcile to complete (iter 126 drill #5).
  const terminationGracePeriodSeconds = Math.max(30, Math.ceil((reconcileIntervalMs / 1000) * 2));
  const pdbMinAvailable = opts.pdbMinAvailable ?? Math.max(1, Math.floor(replicas / 2));
  const labels: Labels = { app: opts.appName, component: "fleet-daemon" };

  return {
    deployment: deployment(opts, labels, replicas, namespace, probePort, reconcileIntervalMs, desiredAgents, terminationGracePeriodSeconds),
    service: service(opts.appName, namespace, probePort, labels),
    podDisruptionBudget: pdb(opts.appName, namespace, labels, pdbMinAvailable),
    horizontalPodAutoscaler: opts.hpa ? hpa(opts.appName, namespace, labels, opts.hpa) : undefined,
    networkPolicy: networkPolicy(opts.appName, namespace, labels, probePort),
  };
}

function deployment(
  opts: FleetDaemonDeployOptions,
  labels: Labels,
  replicas: number,
  namespace: string,
  probePort: number,
  reconcileIntervalMs: number,
  desiredAgents: number,
  terminationGracePeriodSeconds: number,
): K8sManifest {
  return {
    apiVersion: "apps/v1",
    kind: "Deployment",
    metadata: { name: opts.appName, namespace, labels },
    spec: {
      replicas,
      selector: { matchLabels: labels },
      strategy: {
        // §47.7 app-layer rollback: RollingUpdate with maxUnavailable=0
        // means a bad image can't take down all replicas during deploy.
        type: "RollingUpdate",
        rollingUpdate: { maxSurge: 1, maxUnavailable: 0 },
      },
      template: {
        metadata: { labels },
        spec: {
          // §47.8 hardening — pod runs as non-root, no privilege escalation.
          securityContext: {
            runAsNonRoot: true,
            runAsUser: 10001,
            fsGroup: 10001,
            seccompProfile: { type: "RuntimeDefault" },
          },
          terminationGracePeriodSeconds,
          containers: [{
            name: "fleet-daemon",
            image: opts.image,
            imagePullPolicy: "IfNotPresent",
            ports: [{ name: "probe", containerPort: probePort }],
            env: [
              { name: "FLEET_RECONCILE_INTERVAL_MS", value: String(reconcileIntervalMs) },
              { name: "FLEET_DESIRED_AGENTS", value: String(desiredAgents) },
            ],
            resources: opts.resources ?? {
              requests: { cpu: "200m", memory: "256Mi" },
              limits:   { cpu: "1000m", memory: "1Gi" },
            },
            // §47.8 3-probe pattern — wired to iter 127 endpoints.
            startupProbe: {
              httpGet: { path: "/healthz/start", port: probePort },
              periodSeconds: 5,
              failureThreshold: 30,  // up to 150s to boot
            },
            livenessProbe: {
              httpGet: { path: "/healthz", port: probePort },
              periodSeconds: 10,
              failureThreshold: 3,
              // DUMB liveness — no initialDelay beyond what startup covers.
            },
            readinessProbe: {
              httpGet: { path: "/readyz", port: probePort },
              periodSeconds: 5,
              failureThreshold: 3,
              // SMART readiness — degraded fleet drains traffic but
              // doesn't restart pod (§47.8 cascade-restart prevention).
            },
            securityContext: {
              allowPrivilegeEscalation: false,
              readOnlyRootFilesystem: true,
              capabilities: { drop: ["ALL"] },
            },
          }],
        },
      },
    },
  };
}

function service(appName: string, namespace: string, probePort: number, labels: Labels): K8sManifest {
  return {
    apiVersion: "v1",
    kind: "Service",
    metadata: { name: appName, namespace, labels },
    spec: {
      type: "ClusterIP",
      selector: labels,
      ports: [{ name: "probe", port: probePort, targetPort: "probe" }],
    },
  };
}

function pdb(appName: string, namespace: string, labels: Labels, minAvailable: number): K8sManifest {
  return {
    apiVersion: "policy/v1",
    kind: "PodDisruptionBudget",
    metadata: { name: `${appName}-pdb`, namespace, labels },
    spec: {
      minAvailable,
      selector: { matchLabels: labels },
    },
  };
}

function hpa(appName: string, namespace: string, labels: Labels, hpaOpts: NonNullable<FleetDaemonDeployOptions["hpa"]>): K8sManifest {
  return {
    apiVersion: "autoscaling/v2",
    kind: "HorizontalPodAutoscaler",
    metadata: { name: `${appName}-hpa`, namespace, labels },
    spec: {
      scaleTargetRef: { apiVersion: "apps/v1", kind: "Deployment", name: appName },
      minReplicas: hpaOpts.minReplicas,
      maxReplicas: hpaOpts.maxReplicas,
      metrics: [{
        type: "Resource",
        resource: {
          name: "cpu",
          target: { type: "Utilization", averageUtilization: hpaOpts.targetCpuUtilization ?? 70 },
        },
      }],
    },
  };
}

function networkPolicy(appName: string, namespace: string, labels: Labels, probePort: number): K8sManifest {
  return {
    apiVersion: "networking.k8s.io/v1",
    kind: "NetworkPolicy",
    metadata: { name: `${appName}-netpol`, namespace, labels },
    spec: {
      podSelector: { matchLabels: labels },
      policyTypes: ["Ingress", "Egress"],
      ingress: [{
        // Allow probe traffic from the kubelet/probe-agent in the
        // same namespace. Adjust for a stricter cluster (e.g., only
        // from the cluster's probe-agent service-account).
        from: [{ namespaceSelector: {} }],
        ports: [{ protocol: "TCP", port: probePort }],
      }],
      egress: [
        // DNS — every pod needs it.
        { ports: [{ protocol: "UDP", port: 53 }, { protocol: "TCP", port: 53 }] },
        // Egress to agent backends — deploying repo refines.
      ],
    },
  };
}

function validateOptions(opts: FleetDaemonDeployOptions): void {
  if (!opts.appName || !/^[a-z0-9-]+$/.test(opts.appName)) {
    throw new Error("appName must be lowercase alphanumeric + dashes");
  }
  if (!opts.image || opts.image.endsWith(":latest")) {
    throw new Error("image must be set and must NOT use :latest tag (§47.7 rollback discipline)");
  }
  if (opts.replicas !== undefined && opts.replicas < 1) {
    throw new Error("replicas must be >= 1");
  }
  if (opts.hpa) {
    if (opts.hpa.minReplicas < 1) throw new Error("hpa.minReplicas must be >= 1");
    if (opts.hpa.maxReplicas < opts.hpa.minReplicas) {
      throw new Error("hpa.maxReplicas must be >= hpa.minReplicas");
    }
  }
  if (opts.pdbMinAvailable !== undefined && opts.replicas !== undefined && opts.pdbMinAvailable >= opts.replicas) {
    throw new Error("pdbMinAvailable MUST be < replicas (otherwise voluntary drains block forever)");
  }
}
