# Kafka Monitoring And Troubleshooting Checklist

This note is a practical monitoring and troubleshooting checklist for Kafka in this repo.

Use it when:

- consumer lag grows
- events stop flowing
- retries spike
- DLQ fills
- replay or idempotency looks wrong

## 1. What To Monitor

### Core Kafka metrics

- producer failure rate
- consumer failure rate
- consumer lag
- retry-topic traffic
- DLQ depth
- oldest message age
- throughput by topic
- partition skew

### Repo-relevant metrics

- ingestion outbox backlog
- document pipeline stage lag
- eval replay lag
- audit event ingestion lag
- failure event spikes
- per-tenant lag where applicable

## 2. First Troubleshooting Questions

- [ ] Which topic is affected?
- [ ] Which consumer group is affected?
- [ ] Is lag growing, stable, or draining?
- [ ] Is the issue one partition or the whole topic?
- [ ] Did a deployment happen recently?
- [ ] Are producer errors also rising?
- [ ] Is this a data issue, broker issue, consumer issue, or schema issue?

## 3. Producer Troubleshooting Checklist

- [ ] Check the producer service health
- [ ] Check producer logs for publish failures
- [ ] Check whether the outbox is filling up
- [ ] Confirm the event envelope includes `event_id`, `tenant_id`, `request_id`, and `correlation_id`
- [ ] Confirm the correct topic name and version are used
- [ ] Confirm publish retry behavior is bounded and visible

Likely causes:

- Kafka unavailable
- wrong topic name
- schema mismatch
- outbox relay not running

## 4. Consumer Troubleshooting Checklist

- [ ] Check consumer-group lag
- [ ] Check if one partition is hot
- [ ] Check consumer logs for handler failures
- [ ] Check whether offsets are advancing
- [ ] Check whether dedupe logic is dropping too much or too little
- [ ] Check whether downstream dependencies are failing and causing retries

Likely causes:

- slow consumer
- poison message
- downstream dependency failure
- bad offset or commit behavior

## 5. DLQ Troubleshooting Checklist

- [ ] Check DLQ depth
- [ ] Check oldest message age
- [ ] Inspect a sample of DLQ messages
- [ ] Determine whether this is a schema issue, data issue, or code bug
- [ ] Decide whether to drop, patch, or replay

If DLQ grows:

- [ ] identify the producer
- [ ] identify the failing consumer
- [ ] identify whether the failure is deterministic

## 6. Replay Troubleshooting Checklist

- [ ] Confirm replay target topic and time range
- [ ] Confirm consumer is idempotent
- [ ] Confirm replay will not duplicate side effects
- [ ] Confirm replay is auditable
- [ ] Monitor lag and downstream pressure during replay

Likely causes of replay problems:

- weak idempotency
- current-state conflict with historical events
- replay volume saturating consumers

## 7. Monitoring Matrix

| Symptom | First metric | Next check | Likely cause |
|---|---|---|---|
| lag spike | consumer lag | partition distribution | slow consumer or downstream dependency |
| no new events consumed | offset movement | consumer logs | consumer crash or stuck handler |
| producer says success but consumers see nothing | topic throughput | outbox and broker state | wrong topic, relay issue, broker issue |
| DLQ growth | DLQ depth | sample messages | schema or poison-message problem |
| duplicate side effects | processed event tracking | dedupe behavior | idempotency bug |
| replay causes errors | replay throughput | downstream errors | unsafe replay assumptions |

## 8. Repo-Specific Operational Checklist

- [ ] Is the ingestion outbox draining?
- [ ] Is `processed_events` behaving as expected?
- [ ] Is consumer lag visible in Grafana?
- [ ] Are retry topics and DLQs monitored?
- [ ] Are failure events visible to observability and governance paths?
- [ ] Are per-tenant lag issues visible if a noisy tenant appears?

## 9. Bottom Line

Kafka troubleshooting should always answer:

- is the producer healthy?
- is the broker healthy?
- is the consumer healthy?
- is the downstream dependency healthy?
- is replay safe?
- is lag visible and actionable?

If any of those answers are unclear, the Kafka layer is still under-observed.
