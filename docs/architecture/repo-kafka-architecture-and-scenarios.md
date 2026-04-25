# Repo Kafka Architecture And Scenarios

This note explains how Kafka fits this repo specifically.

Kafka is not an optional detail here.
It is part of the architecture direction for:

- ingestion workflows
- evaluation and analytics
- async retries and replay patterns
- audit and failure events

Relevant sources:

- [docs/scenarios/phase-02-kafka-event-architecture.md](/mnt/deepa/rag/docs/scenarios/phase-02-kafka-event-architecture.md)
- [docs/architecture/C4-container.md](/mnt/deepa/rag/docs/architecture/C4-container.md)
- [libs/py/documind_core/kafka_client.py](/mnt/deepa/rag/libs/py/documind_core/kafka_client.py)
- [services/ingestion-svc/migrations/002_outbox.sql](/mnt/deepa/rag/services/ingestion-svc/migrations/002_outbox.sql)

## 1. Why Kafka Is In This Repo

Kafka exists in this repo for real architecture reasons:

- document ingestion is multi-stage
- async fan-out is useful
- retries and replay matter
- evaluation and analytics consume events
- audit and failure events fit event streams well

That makes Kafka a good fit for the repo’s design goals.

## 2. Repo-Specific Kafka Shape

The architecture direction is:

```text
producer service
  -> outbox or event producer
  -> Kafka topic
  -> consumer group
  -> downstream service or worker
```

Kafka shows up as the async backbone in:

- [docs/architecture/C4-container.md](/mnt/deepa/rag/docs/architecture/C4-container.md)

The topic and consumer-group catalog is already documented in:

- [docs/scenarios/phase-02-kafka-event-architecture.md](/mnt/deepa/rag/docs/scenarios/phase-02-kafka-event-architecture.md)

## 3. Current Repo Mechanisms

### Event producer and consumer base

The shared Python Kafka utilities are in:

- [libs/py/documind_core/kafka_client.py](/mnt/deepa/rag/libs/py/documind_core/kafka_client.py)

Important repo-specific properties:

- CloudEvents-style envelopes
- producer idempotence enabled
- idempotent consumer base
- dedupe behavior

### Transactional outbox

The ingestion service has an outbox pattern:

- [services/ingestion-svc/migrations/002_outbox.sql](/mnt/deepa/rag/services/ingestion-svc/migrations/002_outbox.sql)

This matters because it prevents:

- write succeeds but event is lost

which is one of the most dangerous event-driven failure modes.

### Processed event tracking

The ingestion side also has processed-event tracking:

- [services/ingestion-svc/migrations/001_initial.sql](/mnt/deepa/rag/services/ingestion-svc/migrations/001_initial.sql)

This supports idempotent consumption.

## 4. Kafka Scenarios In This Repo

### Ingestion pipeline scenarios

- `doc.uploaded.v1` published after upload
- parser workers consume and emit `doc.parsed.v1`
- chunker workers consume and emit `doc.chunked.v1`
- embedding workers consume and emit `doc.embedded.v1`
- index writers consume and emit `doc.indexed.v1`

### Query and evaluation scenarios

- `rag.query.received.v1` for analytics and sampling
- `rag.response.generated.v1` for eval, audit, and FinOps
- `rag.feedback.v1` for user feedback
- `eval.replay.requested.v1` for replay against new model or prompt

### MCP and governance scenarios

- `mcp.tool.requested.v1`
- `mcp.tool.completed.v1`
- `mcp.tool.failed.v1`
- `approval.requested.v1`
- `audit.event.v1`
- `system.failure.v1`

## 5. Highest-Value Kafka Scenarios For This Repo

These are the most important ones to validate:

1. document upload publishes the right event
2. ingestion stages consume and publish in the correct order
3. duplicate event does not duplicate side effects
4. consumer crash before/after processing is safe
5. outbox drains after Kafka recovery
6. DLQ behavior exists for poison messages
7. consumer lag is visible and alertable
8. replay can reprocess historical events safely

## 6. Monitoring Expectations

Kafka is only trustworthy if its operational signals are visible.

### Must-watch metrics

- consumer lag
- throughput by topic
- retry volume
- DLQ depth
- oldest message age
- producer failure rate
- consumer error rate

### Repo-relevant dashboards

- ingestion pipeline lag
- eval and feedback lag
- failure event spikes
- per-tenant lag where applicable
- DLQ dashboards

The repo already documents consumer lag expectations in the scenario docs.

## 7. Main Risks In This Repo’s Kafka Story

### Risk 1: topic catalog and real implementation drift

The documented event architecture is strong, but the live implementation must keep up with it.

### Risk 2: duplicate handling gaps

If any consumer path ignores idempotency assumptions, replay and retry become dangerous.

### Risk 3: operational invisibility

Kafka systems fail badly when lag, retries, or DLQs are not visible.

### Risk 4: over-architecting async flows too early

Not every workflow needs Kafka immediately.
Async design should remain justified by real failure, scale, or decoupling needs.

## 8. Bottom Line

Kafka is a strong fit for this repo’s:

- ingestion workflows
- analytics and eval flows
- failure and audit events
- event-driven future architecture

The key trust condition is:

- keep contracts explicit
- keep consumers idempotent
- keep lag and DLQ visible
- keep replay safe
