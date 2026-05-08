'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'service-mesh-pattern',
    title: '1. Service mesh pattern (sidecar proxy + control plane)',
    status: 'partial',
    coreConcept: 'A service mesh injects a sidecar proxy (Envoy) into every pod that intercepts all inbound and outbound traffic. The sidecar handles mTLS, retries, timeouts, traffic shaping, observability, and authorization policy — moving these cross-cutting concerns out of application code into infrastructure. A control plane (Istio, Linkerd) configures the sidecars centrally.',
    problem: 'Cross-service concerns (mTLS, retries, timeouts, telemetry, auth) leak into every service\'s code. Every team reinvents retry logic differently. A platform-wide policy change (e.g. "all internal traffic must be mTLS") requires N service edits + N redeploys. Observability is fragmented across libraries.',
    whyThisApproach: 'Sidecar proxy decouples policy from application code. Every service speaks plain HTTP to localhost; the sidecar terminates mTLS upstream and downstream. Platform policy changes once in the control plane and applies fleet-wide. Telemetry is uniform across services because every hop traverses the sidecar.',
    whenToUse: ['Multi-service Kubernetes deployments (>5 services)', 'Mixed-language polyglot fleets where SDK consistency is hard', 'Zero-trust networks (mTLS between every pair)', 'Per-tenant traffic-policy requirements', 'Strict observability mandate (every hop traced)'],
    whenNotToUse: ['Single-service monoliths (sidecar overhead with no payoff)', 'Sub-millisecond latency budgets where sidecar adds 1-2ms', 'Resource-constrained edge deployments', 'Teams without ops capacity to operate the control plane'],
    input: 'service deployment + AuthorizationPolicy + DestinationRule + VirtualService manifests',
    process: [
      'Pod starts with istio-proxy sidecar injected automatically',
      'Outbound call from app: app → localhost → sidecar → mTLS → peer sidecar → peer app',
      'AuthorizationPolicy enforced at peer sidecar before app sees request',
      'Telemetry emitted by both sidecars (traceparent propagated via baggage)',
      'Control plane pushes config updates via xDS to every sidecar',
    ],
    output: 'Mesh-enforced traffic invariants: mTLS, authz, retries, telemetry — without app code knowing.',
    flowchart: `flowchart LR
  ctl[Istio Control Plane] -->|xDS push| s1[sidecar A]
  ctl -->|xDS push| s2[sidecar B]
  app1[App A] -->|localhost| s1
  s1 -->|mTLS| s2
  s2 -->|authz check| s2
  s2 -->|localhost| app2[App B]
  s1 -.OTel.-> col[(Telemetry Collector)]
  s2 -.OTel.-> col`,
    sequence: `sequenceDiagram
  autonumber
  participant A as App A (frontend)
  participant SA as Sidecar A
  participant SB as Sidecar B
  participant B as App B (api-gateway)
  participant T as Telemetry
  A->>SA: HTTP (localhost)
  SA->>SA: pick route, retry policy
  SA->>SB: mTLS + traceparent
  SB->>SB: AuthorizationPolicy check
  alt allowed
    SB->>B: HTTP (localhost)
    B-->>SB: response
    SB-->>SA: response
    SA-->>A: response
  else denied
    SB-->>SA: 403 RBAC: access denied
    SA-->>A: 403
  end
  SA->>T: span (outbound)
  SB->>T: span (inbound)`,
    alternatives: [
      { name: 'Library-based (Hystrix, Resilience4j)', tradeoff: 'In-process — fast; per-language; team-by-team adoption; uneven policy' },
      { name: 'API gateway only', tradeoff: 'Centralised at edge; no service-to-service guarantees; mTLS on internal traffic missing' },
      { name: 'No mesh — plain HTTP', tradeoff: 'Cheapest; no mTLS; no uniform telemetry; retry storms during partial outages' },
    ],
    challenges: [
      'Operational overhead of running Istio + Envoy sidecars',
      'Sidecar injection failures (pod stuck in init)',
      'Resource overhead (sidecar adds CPU + memory per pod)',
      'Debugging traffic that vanishes in the sidecar (envoy access logs essential)',
      'Mesh upgrade coordination (control-plane vs data-plane version skew)',
    ],
    edgeCases: [
      { case: 'Pod deployed without sidecar', solution: 'Namespace label istio-injection=enabled + admission controller catches drift' },
      { case: 'Mesh outage takes down all traffic', solution: 'Sidecars cache config; fail-static so existing connections survive control-plane outage' },
      { case: 'mTLS cert rotation during high traffic', solution: 'Istio rotates certs ahead of expiry; gradual rollout via SDS' },
      { case: 'AuthorizationPolicy too strict — legit traffic blocked', solution: 'Stage in PERMISSIVE mode first; observe denials; switch to STRICT' },
    ],
    failureModes: [
      { mode: 'Sidecar OOM', detect: 'pod restart loop on Envoy', recover: 'Increase sidecar memory limit; profile traffic volume; reduce telemetry verbosity' },
      { mode: 'Authorization policy drift', detect: 'service unreachable from peer that previously worked', recover: 'kubectl get authorizationpolicies; diff against canonical 50-authorization.yaml' },
      { mode: 'Control plane disconnected', detect: 'sidecars stuck on stale config; xDS failure metrics rising', recover: 'Restart istiod; sidecars reconnect; cached config keeps existing traffic alive' },
    ],
    monitoring: [
      'istio_requests_total (per source/destination/code)',
      'istio_request_duration_milliseconds',
      'istio_tcp_connections_opened_total',
      'envoy_cluster_upstream_rq_retry',
      'authorization-policy denial rate per service',
    ],
    testing: [
      'drill_istio_authorization_policy (locks the §47 trust-boundary policy contract)',
      'drill_mesh_mtls_only (every internal connection is mTLS)',
      'drill_mesh_namespace_isolation (cross-namespace calls blocked unless allowed)',
    ],
    security: [
      'mTLS by default — every internal hop encrypted + mutually authenticated',
      'AuthorizationPolicy enforces principle of least privilege per §47 trust boundary',
      'PERMISSIVE → STRICT migration is the safe rollout path; never go STRICT first',
      'Service identity = SPIFFE ID; cluster.local/ns/<ns>/sa/<sa> is canonical',
    ],
    scaling: [
      '10x: 50 pods × ~200MB sidecar = ~10GB extra cluster memory',
      '100x: per-namespace control planes; sidecar mode shared across namespace',
      'Cost driver: sidecar CPU + telemetry volume; throttle access-log sampling',
    ],
    maturity: {
      mvp: 'No mesh — plain HTTP between services',
      production: 'PARTIAL — AuthorizationPolicy YAML exists in infra/istio/; mTLS not yet enforced; control plane not deployed in compose stack',
      enterprise: 'Full Istio control plane + STRICT mTLS + per-tenant traffic policy + canary rollouts + cross-region mesh federation',
    },
    limitations: [
      'No deployed Istio control plane in current compose stack — manifests are reference-only',
      'mTLS not enforced; PERMISSIVE → STRICT migration path documented but not executed',
      'No drill yet locks the AuthorizationPolicy contract',
    ],
    projectFit: [
      'infra/istio/50-authorization.yaml — per-service AuthorizationPolicy (10+ policies)',
      'docs/architecture/c4-component.md — Design Area 3 trust boundary',
      'docs/runbooks/genai-rag-failure-scenarios-and-debugging-playbook.md — mesh debugging',
      'Future: drill_istio_authorization_policy + envoy access-log capture',
    ],
    interviewLine: 'A service mesh moves cross-service concerns — mTLS, retries, timeouts, authz, telemetry — out of application code into a sidecar proxy controlled centrally. Done well, it gives zero-trust between every pod plus uniform observability. Done badly, it adds 200MB per pod and a control-plane upgrade nightmare. The decision is: do you have enough services to amortize the operational cost?',
    implementationSteps: [
      { step: 'Namespace inject', logic: 'kubectl label ns documind istio-injection=enabled — sidecars added on next deploy.' },
      { step: 'AuthorizationPolicy per service', logic: 'ALLOW only legitimate callers; named <caller>-to-<callee>; default-deny via mesh PeerAuthentication.' },
      { step: 'PeerAuthentication mTLS', logic: 'Start in PERMISSIVE; observe non-mTLS traffic; flip to STRICT after zero non-mTLS observed for N days.' },
      { step: 'DestinationRule traffic policy', logic: 'Per-destination retry budget, timeout, outlier detection — replaces app-level breaker patterns at mesh layer.' },
      { step: 'Telemetry to OTel collector', logic: 'Sidecar emits spans + metrics; collector unifies with app-emitted spans via traceparent baggage.' },
      { step: 'Drill the policy contract', logic: 'drill_istio_authorization_policy parses the YAML and asserts each service has a deny-by-default policy.' },
      { step: 'Stage rollout', logic: 'Deploy mesh in dev; soak; promote to staging; promote to prod with canary per ADR-016.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# infra/istio/50-authorization.yaml — least-privilege per-service policy
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: api-gateway-policy
  namespace: documind
spec:
  selector:
    matchLabels: { app: api-gateway }
  action: ALLOW
  rules:
    - from:
        - source:
            namespaces: ["istio-system"]   # ingress gateway
    - from:
        - source:
            principals: ["cluster.local/ns/documind/sa/frontend"]
---
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: documind-mtls
  namespace: documind
spec:
  mtls:
    mode: STRICT  # every connection mTLS or rejected
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: identity-svc-retry
  namespace: documind
spec:
  host: identity-svc
  trafficPolicy:
    connectionPool:
      tcp: { maxConnections: 100 }
    outlierDetection:
      consecutiveErrors: 5
      interval: 30s
      baseEjectionTime: 30s`,
    },
    starStory: {
      situation: 'Cross-service concerns (mTLS, retry, timeout, telemetry, authz) were creeping into every service\'s code. Each team had a slightly different retry budget; mTLS was on the roadmap "next quarter" for 3 quarters running.',
      task: 'Design the mesh layer that takes cross-service policy out of code, with a staged migration path so we never break existing traffic.',
      action: 'PARTIAL — wrote AuthorizationPolicy + PeerAuthentication + DestinationRule manifests under infra/istio/. Documented PERMISSIVE → STRICT mTLS rollout. Control plane deployment + drill still on the roadmap.',
      result: 'When complete: mesh-enforced mTLS + uniform retry budgets + central authz policy. Single PR for fleet-wide policy changes. Telemetry uniform across services. Adds ~200MB per pod; trade-off documented.',
    },
    interviewTraps: [
      'Saying "use Istio" without acknowledging the operational cost (control-plane upgrade pain is real)',
      'STRICT mTLS as the day-1 setting (legit traffic gets blocked; PERMISSIVE first)',
      'Treating sidecar as a black box (envoy access logs are the debug surface)',
    ],
    finalScript: 'A service mesh is infrastructure-level cross-cutting concerns — mTLS, retry, timeout, authz, telemetry — moved out of code. The win: single-PR fleet-wide policy + uniform observability + zero-trust networking. The cost: 200MB per pod + control-plane operational burden. The decision rule: more than 5 services and a polyglot fleet → mesh probably wins. Single service → never. In between → measure first.',
  },
  {
    slug: 'istio-this-codebase',
    title: '2. Istio in this codebase (current state + roadmap)',
    status: 'partial',
    coreConcept: 'This project ships AuthorizationPolicy YAML for 10+ services under infra/istio/50-authorization.yaml — naming convention <caller>-to-<callee>, principle of least privilege per Design Area 3 trust boundary. The control plane is NOT deployed in the current docker-compose stack; the YAML is reference-grade for k8s deployments.',
    problem: 'Internal trust assumptions were implicit. "frontend can call api-gateway" was a wiki sentence, not a configuration. When a new service was added, no canonical place documented who could call it. Reviewers had no way to spot cross-namespace calls that bypassed the trust boundary.',
    whyThisApproach: 'Codify the trust boundary as Istio AuthorizationPolicy YAML even before the control plane is deployed — the YAML serves as documentation + test asset + future deploy artifact. Naming convention <caller>-to-<callee> makes review queries trivial (grep for "to-identity-svc" finds every caller).',
    whenToUse: ['Service-pair connectivity definition', 'New-service onboarding (which service can reach me?)', 'Audit query for cross-namespace calls', 'Source of truth for k8s deployment when mesh activates'],
    whenNotToUse: ['Compose-only deployments where no mesh is present (YAML is reference, not active)', 'Services that need promiscuous internal access (anti-pattern; revisit design)', 'External public-traffic policy (use ingress gateway, not service-to-service authz)'],
    input: 'service identity (k8s ServiceAccount) + namespace + caller-list',
    process: [
      'New service added → author <caller>-to-<service>-policy.yaml entries',
      'Source principal cluster.local/ns/<ns>/sa/<sa> for each authorized caller',
      'PR review: grep for the new service across infra/istio/ to verify policies registered',
      'On k8s deploy: kubectl apply -f infra/istio/ → mesh enforces',
      'Audit: AuthorizationPolicy denial metric → operator sees which caller was rejected',
    ],
    output: 'Reviewable trust boundary + future-deploy artifact + audit query target.',
    flowchart: `flowchart LR
  fe[frontend.sa] -->|allow| api[api-gateway.sa]
  api -->|allow| ident[identity-svc.sa]
  api -->|allow| doc[documind-svc.sa]
  unknown[unknown caller] -.deny.-> api
  unknown -.deny.-> ident`,
    sequence: `sequenceDiagram
  autonumber
  participant New as New service author
  participant Repo as infra/istio/
  participant Rev as Reviewer
  participant K as Kubernetes
  New->>Repo: add AuthorizationPolicy YAML for <caller>-to-<service>
  New->>Rev: open PR
  Rev->>Repo: grep for <service>; verify caller list correct
  Rev-->>New: APPROVE
  New->>K: kubectl apply -f infra/istio/
  K->>K: Istio control plane pushes policy via xDS
  K-->>New: enforced fleet-wide`,
    alternatives: [
      { name: 'Wiki documentation only', tradeoff: 'Drifts; no enforcement; no test asset' },
      { name: 'Code-level allow-lists', tradeoff: 'Per-service ad hoc; uneven; no central audit' },
      { name: 'Network policies (NetworkPolicy)', tradeoff: 'L4 only; no mTLS / identity; coarser than Istio AuthorizationPolicy' },
    ],
    challenges: [
      'YAML drift from real-world traffic (policy declares allowed callers; actual callers may differ)',
      'Service rename without updating policy (old principal lingers)',
      'PERMISSIVE → STRICT cutover requires zero non-mTLS traffic for N days',
    ],
    edgeCases: [
      { case: 'Service has no policy (default-deny vs default-allow)', solution: 'Mesh-wide default-deny via PeerAuthentication; explicit per-service ALLOW' },
      { case: 'Multiple namespaces talking', solution: 'Cross-namespace calls explicit in source.namespaces; reviewer flags any new namespace' },
      { case: 'Service account renamed', solution: 'CI grep step: every principal in infra/istio/ must resolve to a real ServiceAccount' },
    ],
    failureModes: [
      { mode: 'Policy YAML drifts from real traffic', detect: 'Sidecar denial rate rising for legit caller', recover: 'Update policy; deploy; monitor envoy denial metric' },
      { mode: 'Mesh not deployed yet but policy assumed enforced', detect: 'Cross-namespace traffic flowing despite "deny" YAML', recover: 'Verify mesh is active; if compose-only, treat YAML as documentation' },
      { mode: 'New service shipped without policy', detect: 'service responds 200 to anyone', recover: 'PR template requires policy; admission controller blocks deploy without policy' },
    ],
    monitoring: [
      'istio_requests_total{response_code="403", reporter="destination"} (denial rate per service)',
      'AuthorizationPolicy resource count = N services (every service has at least one policy)',
      'PeerAuthentication mode (STRICT vs PERMISSIVE) per namespace',
    ],
    testing: [
      'drill_istio_authorization_policy_yaml (PLANNED — every service has a policy entry)',
      'drill_istio_naming_convention (every policy follows <caller>-to-<callee> pattern)',
      'drill_mesh_principal_resolves (every principal resolves to a real ServiceAccount)',
    ],
    security: [
      'AuthorizationPolicy is the canonical trust-boundary documentation per §47 Design Area 3',
      'Principal naming SPIFFE-conformant (cluster.local/ns/<ns>/sa/<sa>)',
      'Reviewable in PR — no implicit trust',
      'mTLS enforcement requires PeerAuthentication mode=STRICT (not yet deployed)',
    ],
    scaling: [
      '10x: ~10 services, ~10 policies — easily reviewable',
      '100x: ~100 services × multiple callers — needs auto-generation from service mesh observability',
      'Cost driver: review time per new service (mitigated by naming convention)',
    ],
    maturity: {
      mvp: 'No policy — every service trusts every caller',
      production: 'PARTIAL — YAML reference for 10+ services committed; control plane not deployed in compose; drills not yet present',
      enterprise: 'Full Istio control plane + STRICT mTLS + auto-generated policies from observability + per-tenant policy variants',
    },
    limitations: [
      'Control plane NOT deployed in current docker-compose stack (k8s manifests only)',
      'No drill yet asserts the policy contract',
      'PERMISSIVE → STRICT mTLS migration path documented but not executed',
    ],
    projectFit: [
      'infra/istio/50-authorization.yaml — 10+ AuthorizationPolicy entries',
      'docs/architecture/c4-component.md — Design Area 3 trust boundary',
      '/admin/security/deep — sibling page covering identity layer',
      'Future: services/frontend tests — drill_istio_authorization_policy_yaml',
    ],
    interviewLine: 'Even before the mesh is deployed, the AuthorizationPolicy YAML is the canonical trust-boundary documentation. Every service-pair relationship lives there in <caller>-to-<callee> naming. Reviewable, queryable, and ready for the day the control plane goes live.',
    implementationSteps: [
      { step: 'Naming convention', logic: '<caller>-to-<callee>-policy in metadata.name; grep finds every caller of a service.' },
      { step: 'SPIFFE principals', logic: 'Source as cluster.local/ns/documind/sa/<sa>; canonical Istio identity.' },
      { step: 'Per-service file or block', logic: 'Single YAML for now; split per-service file when N services > 30.' },
      { step: 'PR review checklist', logic: 'New service must add at least one ALLOW entry; absent = default-deny (when mesh active).' },
      { step: 'CI principal validation', logic: 'CI step asserts every source.principals[*] resolves to a real ServiceAccount.' },
      { step: 'Drill the contract', logic: 'drill_istio_authorization_policy_yaml asserts every service has at least one policy + naming convention.' },
      { step: 'Activate mesh', logic: 'When k8s migration lands: kubectl apply -f infra/istio/; PERMISSIVE → STRICT after soak.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# infra/istio/50-authorization.yaml — naming convention demo
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  # convention: <caller>-to-<callee>; readable + greppable
  name: frontend-to-api-gateway-policy
  namespace: documind
spec:
  selector:
    matchLabels: { app: api-gateway }
  action: ALLOW
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/documind/sa/frontend"]
---
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: api-gateway-to-identity-svc-policy
  namespace: documind
spec:
  selector:
    matchLabels: { app: identity-svc }
  action: ALLOW
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/documind/sa/api-gateway"]`,
    },
    starStory: {
      situation: 'New services were being added without explicit trust-boundary documentation. "frontend can call api-gateway" was implicit — no canonical place to verify, and reviewers had no consistent query.',
      task: 'Codify the trust boundary in a reviewable, future-deployable form even before the mesh is operational.',
      action: 'Authored AuthorizationPolicy YAML with <caller>-to-<callee> naming. Documented in C4 component diagram (Design Area 3). Set up the PR review query (grep <service> finds every caller).',
      result: 'Trust boundary now greppable. New-service onboarding has a canonical artifact. When the control plane lands, the YAML deploys unchanged.',
    },
    interviewTraps: [
      'Treating Istio AuthorizationPolicy and Kubernetes NetworkPolicy as interchangeable (former is L7 + identity; latter is L4 only)',
      'Authoring YAML without verifying principals resolve to real ServiceAccounts (typo deploy = denial-of-service)',
      'Applying STRICT mTLS without a PERMISSIVE soak (legit non-mTLS traffic gets blocked at flip)',
    ],
    finalScript: 'Istio in this codebase is documentation-as-code today, deploy-artifact tomorrow. The AuthorizationPolicy YAML names the trust boundary explicitly per service-pair. The naming convention makes review queries trivial. PeerAuthentication will flip mTLS from PERMISSIVE to STRICT after a soak period. The bet: when the k8s migration lands, the policy layer is already canonical — no scramble to write authz on day one.',
  },
  {
    slug: 'kiali-integration',
    title: '3. Kiali integration (canonical addon + Grafana deep-links)',
    status: 'shipped',
    coreConcept: 'Kiali is the service-mesh visualization console. Two install paths: (a) docker-compose container — BROKEN by design (Kiali v1.86 hard-blocks outside K8s with "unable to load in-cluster configuration"), and (b) canonical install — pod inside minikube/dm-istio via the official Istio kiali addon, port-forwarded to host:20001 so the docker-compose frontend BFF can probe it. circuitRAG ships path (b) with a project ConfigMap override that wires Kiali to Prometheus (host:9090), Grafana (host:3001), Jaeger (host:16686), and 13 Istio ServiceEntries representing the docker-compose tool stack. 15 Grafana dashboards are auto-provisioned with titles matching Kiali deep-link names exactly.',
    problem: 'Without Kiali wiring, mesh observability has three failure modes: (1) Kiali UI panels render empty because the addon default points at prometheus.istio-system which doesn\'t exist; (2) deep-links from Kiali to Grafana 404 because the dashboard names don\'t match; (3) docker-compose tool services (prometheus, grafana, jaeger, kibana, paperclip MCP, hybrid-architect, etc.) are invisible to Kiali because they\'re not K8s pods. Operators land on a "service mesh dashboard" that shows nothing useful.',
    whyThisApproach: 'Cluster-side ConfigMap override + ServiceEntries for compose services + auto-provisioned Grafana dashboards + drill that locks the title-match contract bidirectionally. The drill catches both "Kiali deep-link without dashboard" AND "dashboard without Kiali link" — orphans clutter, missing dashboards 404. Forward-contract panels (e.g. documind_council_apply_rate) render empty until the metric is emitted, but they\'re labeled " (forward-contract)" so the empty state is HONEST per §57.7.',
    whenToUse: ['Multi-service mesh deployment (>3 services with sidecars)', 'Operator needs single pane of glass for mesh + metrics + traces', 'Compliance asks for "show me who can call who"', 'Investigating tail-latency tied to a specific service pair'],
    whenNotToUse: ['No mesh deployed (compose-only stack — Kiali has nothing to graph)', 'Sub-1ms latency budgets where Kiali polling adds load on Prometheus', 'Single-service deployments (mesh + Kiali both wasted)'],
    input: 'minikube cluster (dm-istio profile) + Istio control plane + kubectl context + scripts/istio-up.sh executed',
    process: [
      'kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.22/samples/addons/kiali.yaml',
      'kubectl apply -f infra/kiali/kiali-cluster-config.yaml (overrides addon default)',
      'kubectl rollout restart deploy/kiali (loads new ConfigMap)',
      'kubectl apply -f infra/kiali/service-entries.yaml (13 ServiceEntries for compose services)',
      'bash scripts/kiali-port-forward.sh (idempotent; svc/kiali 20001:20001)',
      'python3 scripts/generate-grafana-dashboards.py (writes 15 dashboards)',
      'Grafana auto-picks up via 30s provisioning poll',
      'BFF /api/v1/integrations-health probes http://localhost:20001/kiali/healthz → HEALTHY',
    ],
    output: 'Kiali console at http://localhost:20001/kiali with: live mesh graph (istiod + gateways + 13 SEs), Prometheus metrics (real Istio + forward-contract documind_*), Jaeger traces (in-cluster trace lookups), 15 Grafana deep-links (each click lands on a real dashboard).',
    flowchart: `flowchart LR
  op[Operator] -->|http://localhost:20001/kiali| pf[kubectl port-forward]
  pf -->|svc/kiali 20001| ks[Kiali pod in minikube]
  ks -->|external_services.prometheus| prom[(Prometheus on host:9090)]
  ks -->|external_services.grafana| graf[(Grafana on host:3001)]
  ks -->|external_services.tracing| jaeger[(Jaeger on host:16686)]
  ks -->|reads| ic[(Istio control plane)]
  se[(13 ServiceEntries)] -.MESH_EXTERNAL.- ks
  se -.->|host.minikube.internal| compose[docker-compose tools]
  graf -->|reads| prom
  click ks "/admin/integrations-health" "BFF probe"`,
    sequence: `sequenceDiagram
  autonumber
  participant Op as Operator
  participant BFF as integrations-health BFF
  participant K as Kiali pod
  participant P as Prometheus (host)
  participant G as Grafana (host)
  participant J as Jaeger (host)
  Op->>BFF: GET /api/v1/integrations-health
  BFF->>K: GET http://localhost:20001/kiali/healthz
  K-->>BFF: 200 (healthy)
  BFF-->>Op: { Kiali: HEALTHY, latency_ms: 41 }
  Op->>K: open /kiali console
  K->>P: PromQL queries (host.minikube.internal:9090)
  P-->>K: metric series
  Op->>K: click "View in Grafana" deep-link
  K->>G: redirect to dashboard with matching title
  G->>P: render panels
  Op->>K: click trace lookup
  K->>J: GET /api/services
  J-->>K: trace list`,
    alternatives: [
      { name: 'docker-compose Kiali container with kubeconfig mount', tradeoff: 'Tries to bypass in-cluster init; v1.86 still calls rest.InClusterConfig() and fatals; fragile' },
      { name: 'Linkerd Viz (alternative mesh dashboard)', tradeoff: 'Tied to Linkerd, not Istio — different mesh; not applicable here' },
      { name: 'Bare Grafana Istio dashboards without Kiali', tradeoff: 'Loses graph view; loses authz policy visualization; loses trace lookup integration' },
      { name: 'No mesh visualization at all', tradeoff: 'Operators read sidecar access logs by hand; works for 1-2 services, breaks at fleet scale' },
    ],
    bestPractices: {
      do: [
        'Apply the cluster ConfigMap AFTER the addon manifest so the override wins',
        'Use resolution: DNS for ServiceEntries pointing at host.minikube.internal (STATIC rejects hostnames)',
        'Generate Grafana dashboards from a single source so titles stay in sync with Kiali deep-link names',
        'Mark forward-contract metrics explicitly (suffix " (forward-contract)") so empty panels are honest',
        'Drill the title-match contract bidirectionally (deep-link → dashboard AND dashboard → deep-link)',
      ],
      avoid: [
        'docker-compose --profile mesh kiali (the broken container approach)',
        'Hardcoding 192.168.99.1 instead of host.minikube.internal (subnet rotation breaks it)',
        'Hand-writing 15 dashboard JSONs (drift inevitable; titles silently shift)',
        'Bare /healthz path on Kiali probe (web_root is /kiali so bare /healthz 404s)',
      ],
      optimize: [
        'Run the port-forward at boot via a systemd user-service or compose sidecar so manual restart isn\'t needed',
        'Keep dashboard JSONs minimal — Grafana 11.x renders 2-4 panels faster than 12+',
        'Use Grafana provisioning poll (updateIntervalSeconds: 30) instead of explicit reload calls in CI',
      ],
    },
    interviewTraps: [
      'Claiming Kiali "just works" via docker-compose (the v1.86 in-cluster requirement bites every first-time integrator)',
      'Forgetting the ConfigMap rollout-restart step (Kiali keeps using the old config until pod recreates)',
      'Confusing addon-default Prometheus URL (prometheus.istio-system) with the project\'s actual Prometheus location',
      'Pointing Grafana deep-links at dashboard URLs (UID-based) instead of dashboard titles (Kiali looks up by title)',
    ],
    finalScript: 'Kiali integration in this codebase is the canonical Istio addon install + a project ConfigMap override that wires three host-side observability tools. The override is necessary because the addon\'s defaults assume an in-cluster Prometheus that doesn\'t exist here. 13 ServiceEntries make the docker-compose tools visible to the mesh as MESH_EXTERNAL nodes. 15 Grafana dashboards auto-generated to match Kiali\'s deep-link names exactly, with a drill that locks the title-match contract in both directions. The hard lesson: every Kiali default points at "what Istio installs by itself"; circuitRAG installs Istio next to docker-compose tools, so every default needs the override.',
  },
];

export default function ServiceMeshDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Service mesh deep dive</h1>
          <p className="page-subtitle">
            Three surfaces — the service-mesh pattern (sidecar proxy + control
            plane), Istio in this codebase (AuthorizationPolicy YAML + roadmap
            to active mesh), and the canonical Kiali integration (in-cluster
            addon + Grafana deep-links + 13 ServiceEntries) — explained
            through the universal 20-dimension framework.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/microservices/deep', label: 'Microservices deep-dive', why: 'service mesh is one of four microservices resilience patterns; this page covers the mesh-layer specifics' },
          { href: '/admin/security/deep', label: 'Security deep-dive', why: 'mesh authz is the §47 Design Area 3 trust-boundary mechanism; this page details the YAML' },
          { href: '/admin/breakers/deep', label: 'Circuit breakers', why: 'app-level breakers and mesh-level outlier detection are complementary; mesh handles transport, app handles business logic' },
          { href: '/admin/tracing/deep#baggage-propagation', label: 'Baggage propagation', why: 'sidecars propagate traceparent + baggage automatically; tracing relies on this' },
          { href: '/admin/rollout/deep#rollback-strategy', label: 'Rollback strategy', why: 'PERMISSIVE → STRICT mTLS migration is a staged rollout the rollback playbook documents' },
          { href: '/admin/monitoring', label: 'Integrations health monitor', why: 'Kiali appears as a HEALTHY entry in the 19-tool BFF probe — the cluster ConfigMap + port-forward make this work' },
          { href: '/admin/tools-launcher', label: 'Tools launcher', why: 'Kiali traffic-light status surfaces here; clicking the tile opens the Kiali console' },
        ]}
      />
    </>
  );
}
