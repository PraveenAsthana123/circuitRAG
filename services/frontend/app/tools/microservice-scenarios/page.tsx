import Link from 'next/link';

export const metadata = { title: 'Microservice Scenarios — DocuMind' };

type Scenario = {
  pattern: string;
  problem: string;
  solution: string;
  documindExample: string;
  tradeoffs: string;
  docsUrl: string;
  docsLabel: string;
};

const SCENARIOS: Scenario[] = [
  {
    pattern: 'Database-per-service',
    problem: 'Services coupled through a shared DB end up deploying together; schema changes block everyone.',
    solution: 'Each service owns its schema. Cross-service reads go through APIs, not SQL joins.',
    documindExample:
      'One Postgres cluster, but six schemas (`identity`, `ingestion`, `governance`, `finops`, `eval`, `observability`). Each service connects with permissions scoped to its own schema. No cross-schema foreign keys.',
    tradeoffs: 'Easier deploys; harder reporting (need a dedicated analytics path, not JOINs).',
    docsUrl: 'https://microservices.io/patterns/data/database-per-service.html',
    docsLabel: 'microservices.io — Database per Service',
  },
  {
    pattern: 'API Gateway',
    problem: 'Clients shouldn’t know the internal topology; cross-cutting concerns like auth and rate-limit don’t belong in every service.',
    solution: 'Single edge entry point. Handles TLS, auth, rate-limit, correlation-ID, routing.',
    documindExample:
      'Go-written `api-gateway` validates JWTs, sets correlation-id header, enforces per-IP and per-tenant rate limits, then routes to the Python services. mTLS inside the mesh.',
    tradeoffs: 'Added hop; gateway can become a bottleneck if not horizontally scaled.',
    docsUrl: 'https://microservices.io/patterns/apigateway.html',
    docsLabel: 'microservices.io — API Gateway',
  },
  {
    pattern: 'Service Mesh (Istio)',
    problem: 'mTLS, retries, timeouts, circuit-breaking, traffic-shifting reinvented per service = bugs everywhere.',
    solution: 'Sidecar proxies handle these concerns uniformly; services stay thin.',
    documindExample:
      'Istio 1.23 with `PeerAuthentication: STRICT` (mTLS everywhere), `AuthorizationPolicy` per service, VirtualService canary 90/10 for new revisions, Kiali for mesh viz.',
    tradeoffs: 'Operational footprint (control plane + sidecars); extra CPU per pod.',
    docsUrl: 'https://istio.io/latest/docs/concepts/what-is-istio/',
    docsLabel: 'istio.io — What is Istio',
  },
  {
    pattern: 'Saga (orchestrated)',
    problem: 'Distributed transactions don’t exist across services; need business-level compensation.',
    solution: 'Central orchestrator runs steps, invokes compensations on failure.',
    documindExample:
      '`DocumentIngestionSaga` — parse → chunk → embed → index → stamp-model. Each step has a `_compensate_*`. `recovery-worker` picks up stuck sagas and runs compensations to completion.',
    tradeoffs: 'Orchestrator becomes a hot spot; compensations must be genuinely idempotent.',
    docsUrl: 'https://microservices.io/patterns/data/saga.html',
    docsLabel: 'microservices.io — Saga',
  },
  {
    pattern: 'Outbox',
    problem: 'Publishing to Kafka + writing to DB isn’t atomic; crash between leaves inconsistent state.',
    solution: 'Write the domain row + event to the same DB transaction. A relay tails the outbox and publishes.',
    documindExample:
      '`outbox.py` writes `(aggregate_id, type, payload)` to Postgres inside the domain transaction. The Kafka relay worker publishes with at-least-once; consumers dedupe on UUID.',
    tradeoffs: 'Write amplification; relay lag adds to end-to-end latency.',
    docsUrl: 'https://microservices.io/patterns/data/transactional-outbox.html',
    docsLabel: 'microservices.io — Transactional Outbox',
  },
  {
    pattern: 'CQRS (read ≠ write)',
    problem: 'Read workloads and write workloads have different scale curves and consistency needs.',
    solution: 'Separate services. Writes go through the command side; reads through a projection.',
    documindExample:
      '`ingestion-svc` (write) vs `retrieval-svc` (read). Write path hits Postgres + Qdrant + Neo4j; read path is latency-optimized with cache-through.',
    tradeoffs: 'Eventual consistency between write and read; two pipelines to operate.',
    docsUrl: 'https://martinfowler.com/bliki/CQRS.html',
    docsLabel: 'Martin Fowler — CQRS',
  },
  {
    pattern: 'Circuit Breaker',
    problem: 'A slow upstream takes every caller down with it.',
    solution: 'Trip after N failures; fail fast while OPEN; probe in HALF_OPEN.',
    documindExample:
      'Five specialized breakers: Retrieval, Token, Agent-Loop, Observability (inverted-polarity), plus the Cognitive Circuit Breaker on the LLM token stream.',
    tradeoffs: 'Thresholds need tuning; false positives frustrate users; metrics per breaker explode cardinality if named dynamically.',
    docsUrl: 'https://martinfowler.com/bliki/CircuitBreaker.html',
    docsLabel: 'Martin Fowler — Circuit Breaker',
  },
  {
    pattern: 'Idempotency Keys',
    problem: 'At-least-once delivery + client retries = duplicate resources.',
    solution: 'Client sends `Idempotency-Key`; server persists first response and replays it on retry.',
    documindExample:
      '`IdempotencyMiddleware` + `IdempotencyStore` — stores first response body for 24h keyed by `(tenant, key)`. Re-submit within window returns the cached 201, never creates a second document.',
    tradeoffs: 'Storage overhead; key-collision risk if clients reuse keys.',
    docsUrl: 'https://stripe.com/docs/api/idempotent_requests',
    docsLabel: 'Stripe — idempotency',
  },
  {
    pattern: 'Event-Driven + DLQ',
    problem: 'Poison messages block the consumer queue; blind retries cascade.',
    solution: 'Bounded retry with exponential backoff, then park in a dead-letter queue for human review.',
    documindExample:
      '`kafka_client.py` consumer with 3-try exponential backoff → DLQ topic. Governance service surfaces DLQ depth as an alert; operators inspect via the governance UI.',
    tradeoffs: 'Parked messages are forgotten state; need tooling + on-call rotation.',
    docsUrl: 'https://docs.confluent.io/platform/current/streams/concepts.html',
    docsLabel: 'Confluent — stream processing',
  },
  {
    pattern: 'Bulkhead',
    problem: 'One bad tenant or one bad feature takes the whole service down.',
    solution: 'Resource pools per tenant/feature so the blast radius is contained.',
    documindExample:
      'Per-tenant rate buckets in the gateway; separate Kafka consumer groups per workload; K8s PodDisruptionBudget keeps ingestion from eating all inference nodes.',
    tradeoffs: 'Under-utilization if buckets are oversized; operational complexity.',
    docsUrl: 'https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead',
    docsLabel: 'Microsoft — Bulkhead pattern',
  },
  {
    pattern: 'Strangler Fig (migrations)',
    problem: 'Rewrites stall; users suffer feature freezes.',
    solution: 'Route new traffic to the new implementation; old serves legacy until drained.',
    documindExample:
      'When the Python skeleton of an identity-svc was replaced by a Go implementation, Istio VirtualService did the routing; the old pods drained over a week with no user-visible outage.',
    tradeoffs: 'Two systems in prod at once; requires disciplined traffic shifting and shared contracts.',
    docsUrl: 'https://martinfowler.com/bliki/StranglerFigApplication.html',
    docsLabel: 'Martin Fowler — Strangler Fig',
  },
  {
    pattern: 'Sidecar (observability)',
    problem: 'Every service re-implementing logging/metrics/tracing bloats the image and drifts.',
    solution: 'Shared sidecar container runs OTel collector + log shipper.',
    documindExample:
      'OTel sidecar per pod pushes spans to Jaeger and metrics to Prometheus. Application code uses the OTel SDK; the sidecar handles retries, batching, and the Observability CB.',
    tradeoffs: 'One more container per pod; sidecar crashes can lose telemetry.',
    docsUrl: 'https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar',
    docsLabel: 'Microsoft — Sidecar pattern',
  },
];

export default function MicroserviceScenarios() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Microservice Design — Scenarios</h1>
        <p className="design-areas-sub">
          Each row is a pattern we use in DocuMind, with a concrete local example and a
          link to the canonical write-up. Use this page as a talking-point menu for
          architecture reviews.
        </p>
        <Link href="/tools" className="sysdesign-back">← back to tool index</Link>
      </header>

      <div className="method-grid">
        {SCENARIOS.map((s) => (
          <article key={s.pattern} className="method-card">
            <div className="method-card-head">
              <h3 className="method-name">{s.pattern}</h3>
            </div>
            <dl className="cb-card-dl">
              <dt>Problem</dt>
              <dd>{s.problem}</dd>
              <dt>Pattern</dt>
              <dd>{s.solution}</dd>
              <dt>DocuMind example</dt>
              <dd>{s.documindExample}</dd>
              <dt>Tradeoffs</dt>
              <dd>{s.tradeoffs}</dd>
              <dt>Reference</dt>
              <dd>
                <a href={s.docsUrl} target="_blank" rel="noopener noreferrer" className="cb-link">
                  {s.docsLabel} ↗
                </a>
              </dd>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
