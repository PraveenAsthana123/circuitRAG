# 43-reference-architecture — operating-model document (no code)

## What this folder is

An 18-section reference architecture document covering C4 model
(L1 / L2 / L3), HLD, LLD, end-to-end sequence flow, multi-agent
sequence, RAG detailed flow, security architecture, observability
architecture, Kubernetes topology, network zones, failure handling,
deployment flow, data flow, recommended production tech stack,
NFR targets, and architecture principles.

## Sister doc

Component 42 covers the **operating model** (org / SDLC / governance /
KPIs / roles). Component 43 covers the **reference architecture**
(C4 / sequence / topology / tech stack). They overlap on principles
and intent; both share the same caveat — diagrams without owners and
artifacts are posters, not deliverables.

## Cross-reference with this repo's actual architecture

| Component 43 section | Where it's implemented (or partly) in this repo |
|---|---|
| §1 C4 L1 System Context | `docs/architecture/c4/L1-*.md` |
| §2 C4 L2 Containers | `docs/architecture/c4/L2-*.md` |
| §3 C4 L3 Components | `docs/architecture/c4/L3-*.md` |
| §5 LLD | `docs/architecture/c4/L4-*.md` + ADRs in `docs/adr/` |
| §6 End-to-End Sequence | `request_id` baggage flow per CLAUDE.md §47 |
| §8 RAG Detailed Flow | `services/retrieval-svc/` (real implementation) |
| §9 Security Architecture | CLAUDE.md §47.6 (OWASP + STRIDE + DevSecOps + SOC2) |
| §10 Observability | `ops-compose/` (Jaeger + Prometheus + Grafana) |
| §11 K8s Topology | `infra/k8s/` (if present) + Istio sidecars |
| §13 Failure Handling | Component 7 (resilience) + CLAUDE.md §47.7 (4-layer rollback) |
| §14 Deployment Flow | `.github/workflows/` + Argo Rollouts |
| §17 NFR Targets | CLAUDE.md §53.4 (capacity model + SLO) |

So most of Component 43 is also already encoded in this repo's
architecture docs and policies. The Component 43 markdown is a
useful single-page summary; the actual implementation lives elsewhere.

## What's NOT in this folder

- No code
- No tests
- No drills
- No artifacts that prove the diagrams reflect reality

## Honest review

See [`../GAPS.md`](../GAPS.md) Component 43 row. Short version: same
critique as Component 42 — diagrams are useful for stakeholder
alignment but become wallpaper without (artifact + owner + measurement
+ drill) per row.
