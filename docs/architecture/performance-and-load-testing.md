# Performance And Load Testing

This note describes how to approach performance testing and load testing for this repo.

The goal is not to produce one vanity benchmark.
The goal is to answer practical questions like:

- where does latency come from?
- which service saturates first?
- what happens under burst traffic?
- how does degraded mode behave under load?
- how long does recovery take after an outage?
- what does concurrency do to cost, backlog, and user experience?

## 1. What To Measure

Performance and load testing should be multi-dimensional.

### Core latency metrics

- p50 latency
- p95 latency
- p99 latency
- timeout rate

### Throughput metrics

- requests per second
- concurrent request count
- tool calls per second
- ingestion throughput
- replay throughput

### Error and resilience metrics

- 5xx rate
- breaker-open rate
- breaker rejection rate
- degraded draft rate
- replay success rate
- replay lag

### AI and retrieval metrics

- retrieval latency
- retrieval cache hit rate
- model latency
- tokens per request
- prompt size and context size
- cost per request

### Operational backlog metrics

- queue depth
- oldest pending draft age
- worker lag
- consumer lag where applicable

## 2. Types Of Performance Testing

Use more than one test type.

### Micro-benchmarks

Used for:

- hot utility paths
- ranking or scoring code
- token counting or chunking code
- critical serialization paths

Useful when:

- you need to isolate one hot path

### Service-level load tests

Used for:

- one service at a time
- one endpoint at a time
- one dependency relationship at a time

Examples:

- gateway burst tests
- retrieval query concurrency
- inference answer latency under concurrent load

### Workflow-level load tests

Used for:

- upload -> ingest -> retrieve -> answer
- ask -> MCP call -> degraded draft
- replay backlog drain after dependency recovery

These matter more than isolated endpoint benchmarks because they show real bottlenecks.

### Resilience-under-load tests

Used for:

- outage during traffic
- dependency slowdown under traffic
- breaker-open behavior under sustained load
- replay after traffic resumes

These are the highest-value tests for this repo.

## 3. Main Load Scenarios For This Repo

### Gateway and API edge

Test:

- burst traffic
- sustained request rate
- oversized payload rejection
- correlation and auth overhead under load

Watch:

- p95 and p99 latency
- 4xx and 5xx rates
- rate-limit behavior

### Retrieval service

Test:

- hybrid retrieval under concurrency
- cold cache vs warm cache
- large top-k requests
- vector and graph backend latency under pressure

Watch:

- retrieval latency
- cache hit rate
- backend timeout rate
- quality degradation when latency rises

### Inference service

Test:

- concurrent answer generation
- long-context prompts
- streaming vs non-streaming behavior
- model backend slowdown

Watch:

- answer latency
- timeout rate
- token usage
- degraded or fallback behavior

### MCP and tool execution

Test:

- normal tool traffic
- slow downstream systems
- MCP server outage
- breaker-open fast-reject behavior

Watch:

- tool latency
- success/error/degraded/replay outcomes
- draft creation rate
- denial rate
- replay lag

### Replay worker

Test:

- backlog accumulation
- backlog drain after dependency recovery
- namespace-specific degradation
- worker fairness across tenants

Watch:

- pending draft count
- replay throughput
- oldest pending age
- skip and error rates

### Frontend

Test:

- core page load under slow APIs
- failed API rendering under traffic
- document listing and ask-page responsiveness

Watch:

- client-visible latency
- console errors
- failed-request UX
- browser-network waterfall

## 4. Test Levels And Suggested Targets

Do not start with the biggest test.
Use progressive load levels.

### Level 1: baseline

Goal:

- prove the system is healthy at expected normal traffic

Example assertions:

- stable p95
- no 5xx spikes
- no unexpected breaker opens

### Level 2: peak

Goal:

- prove the system can handle realistic burst traffic

Example assertions:

- p95 stays within agreed tolerance
- error rate remains bounded
- queue growth is manageable

### Level 3: stress

Goal:

- find saturation and failure thresholds

Example assertions:

- system fails predictably
- breakers open before cascade
- degraded mode remains safe

### Level 4: recovery

Goal:

- prove the system recovers cleanly after a failure window

Example assertions:

- replay backlog drains
- breaker closes after recovery
- latency returns toward baseline

## 5. Load Contracts Worth Defining

Example load contracts for this repo:

| Scenario | Example tool | Contract |
|---|---|---|
| Baseline ask traffic | k6 or Locust | p95 under target; no unexpected 5xx |
| Peak ask traffic | k6 | bounded latency growth; error rate under threshold |
| Retrieval cold cache | synthetic load | initial spike then recovery; cache warms normally |
| MCP outage under traffic | chaos + load | draft fallback works; no cascade |
| Replay recovery | worker replay test | backlog drains within target window |
| Long-context inference | synthetic prompts | cost and latency tracked; no runaway timeouts |

## 6. Tooling Options

The repo does not yet ship a full load-testing suite, but good tool choices are:

- `k6`
  good for HTTP and API load scenarios
- `Locust`
  good for Python-friendly workflow and stateful scenarios
- browser DevTools
  useful for frontend waterfall and F12 validation
- Prometheus and Grafana
  required for observing behavior during tests

If you add scripts, a reasonable location is:

- `scripts/load/`

## 7. What To Watch During Tests

Performance testing is not only about the final report.
You should watch the live system while the test runs.

### Gateway

- request rate
- p95 latency
- 429 rate
- auth or routing failures

### Retrieval

- Qdrant latency
- Neo4j latency
- Redis hit rate
- retrieval cache effectiveness

### Inference

- model latency
- timeout rate
- token usage
- fallback behavior

### MCP

- per-tool outcomes
- breaker state by namespace
- degraded draft creation
- denial spikes

### Worker and governance

- draft backlog
- replay throughput
- audit write failures
- oldest pending age

## 8. Benchmarks That Actually Matter

For this repo, the most meaningful benchmarks are:

- end-to-end ask latency
- retrieval latency and quality under concurrency
- MCP action success vs degraded behavior
- replay recovery time after outage
- cost and token behavior under concurrent load
- operator visibility into failures under pressure

Those matter more than a synthetic single-endpoint number with no workflow context.

## 9. Common Performance Mistakes

- benchmarking only one happy endpoint
- ignoring degraded-mode behavior
- ignoring replay backlog after outage
- measuring latency without measuring cost
- measuring throughput without checking correctness
- running load without watching traces and metrics
- claiming “fast” without defining a contract

## 10. Strong Next Steps For This Repo

The most useful next additions would be:

1. `scripts/load/` with `k6` or `Locust` scenarios
2. benchmark baselines for:
   - ask flow
   - retrieval flow
   - MCP degraded flow
   - replay recovery
3. dashboards focused on:
   - latency
   - breaker state
   - draft backlog
   - replay health
   - cost and token trends
4. explicit performance SLOs per critical path

## 11. Bottom Line

Performance and load testing in this repo should prove more than speed.

It should prove:

- stable latency under normal traffic
- predictable behavior under peak traffic
- safe failure under stress
- clean recovery after outage
- bounded cost under concurrency
- operator visibility during incidents

That is the standard that makes performance testing useful here.
