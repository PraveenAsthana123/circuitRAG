# Performance, Load Tooling, And Matrices

This note answers these questions for this repo:

- what tools should be installed first
- how performance should be tested
- how load should be tested
- how to report results
- how to think in matrices instead of one-off test runs

The goal is to give one practical control document for performance and load engineering.

It is intentionally centered on the tools that matter most for this repo:

- `k6`
- `Locust`
- `pytest-benchmark`
- `Playwright`
- `OpenTelemetry`
- `Prometheus`
- `Grafana`
- `Langfuse` or `Phoenix`
- `Ragas`
- `Promptfoo`

The repo does **not** currently ship `scripts/load/` yet.
This note therefore covers both:

- what to install now
- how to structure the implementation you would add next

## 1. Recommended Install Set

Do not install everything on day one.
Install by phase.

### Phase 1: minimum useful stack

- `k6`
- `OpenTelemetry`
- `Prometheus`
- `Grafana`

Why:

- `k6` gives fast HTTP load testing
- `OpenTelemetry` gives request tracing
- `Prometheus` gives metrics storage
- `Grafana` gives dashboards during tests

### Phase 2: workflow and AI visibility

- `Locust`
- `Langfuse` or `Phoenix`

Why:

- `Locust` is useful when flows become stateful or workflow-shaped
- `Langfuse` or `Phoenix` gives AI-specific visibility beyond infra telemetry

### Phase 3: regression and benchmark depth

- `pytest-benchmark`
- `Playwright`
- `Ragas`
- `Promptfoo`

Why:

- `pytest-benchmark` covers hot-path code performance
- `Playwright` covers browser-visible performance and failure behavior
- `Ragas` and `Promptfoo` cover retrieval and prompt regressions

## 1.1 Practical install commands

These are pragmatic starting points, not a locked standard.

### k6

Linux example:

```bash
sudo gpg -k
sudo apt-get update
sudo apt-get install -y gnupg ca-certificates
curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install -y k6
```

### Locust

```bash
python -m venv .venv-load
source .venv-load/bin/activate
pip install locust
```

### pytest-benchmark

```bash
source .venv/bin/activate  # or your active repo venv
pip install pytest-benchmark
```

### Playwright

```bash
cd services/frontend
npm install
npx playwright install
```

### Prometheus and Grafana

Use either:

- local Docker Compose additions
- or the existing observability and infra path in this repo

Recommended first step:

- keep local startup simple
- scrape gateway, Python services, Go services, and MCP `/metrics`

### Langfuse or Phoenix

Install only after baseline metrics and tracing exist.
Otherwise AI-specific visibility will sit on top of weak core observability.

## 2. Recommended Repo Layout

If you productize performance testing, a clean layout is:

```text
scripts/
  load/
    k6/
    locust/
    fixtures/
  benchmark/
    python/
    browser/
reports/
  performance/
    baseline/
    peak/
    stress/
    recovery/
dashboards/
  grafana/
```

Recommended additions:

```text
docs/
  reports/
    performance/
      YYYY-MM-DD-baseline.md
      YYYY-MM-DD-peak.md
      YYYY-MM-DD-stress.md
      YYYY-MM-DD-recovery.md
```

And for fixture discipline:

```text
scripts/load/fixtures/
  ask_payloads.json
  mcp_payloads.json
  documents/
```

## 3. Tool Decision Matrix

| Tool | Primary role | Best for | Weak at | Repo priority |
|---|---|---|---|---|
| `k6` | HTTP load testing | API and service traffic | rich browser flows | very high |
| `Locust` | workflow load testing | stateful and multi-step scenarios | simpler static HTTP tests | high |
| `pytest-benchmark` | code micro-benchmarking | hot functions and local regressions | full-system load | medium |
| `Playwright` | browser and UX testing | user-visible latency and failure states | backend-only throughput | high |
| `OpenTelemetry` | traces | end-to-end request lineage | dashboards by itself | must-have |
| `Prometheus` | metrics storage | time-series metrics | traces and UX | must-have |
| `Grafana` | dashboards | live load observability | raw load generation | must-have |
| `Langfuse` or `Phoenix` | AI tracing | prompt, retrieval, tool visibility | generic infra metrics | high |
| `Ragas` | RAG evaluation | groundedness and retrieval quality | pure system load | medium |
| `Promptfoo` | prompt regression | CI-style eval gates | runtime observability | medium |

## 3.1 Tool install priority matrix

| Tool | Install now | Install later | Why |
|---|---|---|---|
| `k6` | yes | no | fastest value for HTTP baseline and peak tests |
| `Locust` | yes if workflow testing matters now | yes if not | needed for stateful MCP and replay scenarios |
| `pytest-benchmark` | later | yes | useful after hot paths are stable |
| `Playwright` | yes if frontend is important now | yes if backend-first | needed for browser-visible performance and F12 failures |
| `OpenTelemetry` | yes | no | essential for diagnosing performance runs |
| `Prometheus` | yes | no | essential metrics store |
| `Grafana` | yes | no | essential human-readable evidence layer |
| `Langfuse` / `Phoenix` | later | yes | only valuable once core traces and metrics exist |
| `Ragas` | later | yes | quality benchmark, not base load tool |
| `Promptfoo` | later | yes | regression guard, not runtime load tool |

## 4. Task Matrix

Use a task matrix so every tool has a defined job.

| Task | k6 | Locust | pytest-benchmark | Playwright | OTel | Prometheus | Grafana | Langfuse/Phoenix | Ragas | Promptfoo |
|---|---|---|---|---|---|---|---|---|---|---|
| API load | primary | optional | no | no | observe | measure | display | optional | no | no |
| Stateful workflow load | limited | primary | no | optional | observe | measure | display | optional | no | no |
| Browser-visible latency | no | no | no | primary | observe | partial | display | optional | no | no |
| Hot-path code benchmark | no | no | primary | no | no | optional | optional | no | no | no |
| Retrieval quality regression | no | no | no | no | optional | optional | optional | optional | primary | optional |
| Prompt regression | no | no | no | no | optional | optional | optional | optional | optional | primary |
| Traceability during load | no | no | no | no | primary | partial | display | strong AI detail | no | no |

## 4.1 Service-to-tool matrix

This is the most practical matrix for this repo.

| Service / path | Primary load tool | Secondary tools | Main benchmark concern |
|---|---|---|---|
| API gateway | `k6` | OTel, Prometheus, Grafana | RPS, routing latency, auth overhead |
| retrieval-svc | `k6` | OTel, Prometheus, Grafana, Ragas | p95 latency, cache hit rate, backend pressure |
| inference-svc | `k6` | OTel, Prometheus, Grafana, Langfuse/Phoenix | answer latency, timeout rate, token cost |
| MCP action path | `Locust` | OTel, Prometheus, Grafana | degraded draft rate, tool latency, denial rate |
| replay worker | `Locust` | Prometheus, Grafana, OTel | backlog drain, replay throughput, oldest pending age |
| frontend ask/upload/documents | `Playwright` | browser DevTools, OTel | user-visible latency and error UX |
| Python hot paths | `pytest-benchmark` | CI | local regressions in ranking, scoring, serialization |
| prompt and retrieval quality | `Promptfoo`, `Ragas` | Langfuse/Phoenix | quality drift, regression, groundedness |

## 5. Operation Matrix

This matrix says what each tool does operationally during a test run.

| Tool | Operation | Input | Output |
|---|---|---|---|
| `k6` | generate stateless HTTP traffic | endpoint definitions, payloads, thresholds | request metrics, pass/fail summary |
| `Locust` | generate user-like workflow traffic | user classes, wait times, task flows | throughput, latency, failure distribution |
| `pytest-benchmark` | benchmark function or code path | Python benchmark tests | benchmark history and regression signals |
| `Playwright` | run browser flows | page actions, assertions, env URLs | UX timing, failures, screenshots, traces |
| `OpenTelemetry` | capture spans | instrumented app traffic | traces and span metadata |
| `Prometheus` | scrape and store metrics | exporter endpoints | time-series metrics |
| `Grafana` | render dashboards | Prometheus and other datasources | graphs, panels, alerts |
| `Langfuse` / `Phoenix` | capture AI run details | prompt, retrieval, output, tool metadata | AI traces, prompt or run inspection |
| `Ragas` | evaluate RAG output quality | question, context, answer datasets | quality scores and regressions |
| `Promptfoo` | compare prompt or model outputs | test cases, assertions, prompt versions | pass/fail and score reports |

## 5.1 Operation matrix by test phase

| Phase | Primary tool | Operation | Exit question |
|---|---|---|---|
| baseline | `k6` | normal traffic at expected load | does the system behave normally at day-to-day volume? |
| peak | `k6` or `Locust` | burst traffic and concurrency | does latency remain bounded at likely spikes? |
| stress | `k6` and `Locust` | push until saturation | does failure happen safely and predictably? |
| failure-under-load | `Locust` + chaos | dependency outage during load | do breaker and degraded paths work under pressure? |
| recovery | `Locust` | traffic resumes after outage | does replay recover and backlog drain? |
| browser validation | `Playwright` | user-facing timing and failure UX | does the UI remain understandable under stress? |

## 6. Error Matrix

This matrix says which failure classes each tool should catch.

| Error class | k6 | Locust | pytest-benchmark | Playwright | OTel | Prometheus | Grafana | Langfuse/Phoenix | Ragas | Promptfoo |
|---|---|---|---|---|---|---|---|---|---|---|
| 5xx surge | yes | yes | no | partial | observe | yes | yes | partial | no | no |
| timeout spike | yes | yes | partial | yes | observe | yes | yes | partial | no | no |
| breaker-open behavior | partial | yes | no | no | observe | yes | yes | partial | no | no |
| degraded draft behavior | partial | yes | no | partial | observe | yes | yes | partial | no | no |
| replay backlog recovery | no | yes | no | no | observe | yes | yes | no | no | no |
| browser failure UX | no | no | no | yes | partial | no | partial | no | no | no |
| prompt regression | no | no | no | no | no | no | no | partial | partial | yes |
| retrieval quality regression | no | no | no | no | no | no | no | partial | yes | partial |

## 6.1 Error matrix by lifecycle stage

| Lifecycle stage | Error classes to force |
|---|---|
| request ingress | 429, 401, bad route, malformed payload |
| retrieval | timeout, slow vector DB, cold cache, empty results |
| inference | long context, slow model, timeout, bad fallback |
| MCP action | 403 denial, 5xx dependency failure, breaker open |
| degraded mode | draft persist failure visibility, repeated degraded responses |
| replay | non-pending conflict, replay failure, backlog accumulation |
| frontend | failed API, hydration issue, slow page, retry UX |

## 7. Observability Matrix

This matrix says what each tool contributes to observability.

| Tool | Latency | Throughput | Errors | Traces | AI detail | Cost signals | Backlog visibility |
|---|---|---|---|---|---|---|---|
| `k6` | yes | yes | yes | no | no | no | no |
| `Locust` | yes | yes | yes | no | no | no | no |
| `pytest-benchmark` | local only | no | regression | no | no | no | no |
| `Playwright` | user-visible | no | UX failures | optional | no | no | no |
| `OpenTelemetry` | yes | partial | yes | primary | partial | partial | partial |
| `Prometheus` | yes | yes | yes | no | no | partial | yes |
| `Grafana` | display | display | display | display links | partial | partial | display |
| `Langfuse` / `Phoenix` | yes | partial | partial | strong AI traces | primary | partial | no |
| `Ragas` | no | no | no | no | quality detail | no | no |
| `Promptfoo` | no | no | pass/fail | no | prompt detail | no | no |

## 7.1 Observability matrix by metric family

| Metric family | Source of truth | Why it matters |
|---|---|---|
| request latency | Prometheus histograms + Grafana | baseline operational health |
| trace spans | OpenTelemetry | cross-service bottleneck diagnosis |
| MCP tool outcomes | MCP Prometheus counters | action path truthfulness |
| breaker state | breaker metrics | safe failure under load |
| draft backlog | governance and worker metrics | degraded-mode recovery health |
| AI run metadata | Langfuse or Phoenix | prompt/retrieval/tool decision visibility |
| RAG quality | Ragas | load without correctness is meaningless |
| prompt regression | Promptfoo | release safety for AI behavior |

## 8. Loop Matrix

The loop matrix explains where each tool fits in the engineering loop.

| Loop stage | k6 | Locust | pytest-benchmark | Playwright | OTel | Prometheus | Grafana | Langfuse/Phoenix | Ragas | Promptfoo |
|---|---|---|---|---|---|---|---|---|---|---|
| pre-merge regression | optional | no | yes | yes | no | no | no | no | yes | yes |
| staging baseline | yes | yes | optional | yes | yes | yes | yes | yes | yes | yes |
| peak validation | yes | yes | no | optional | yes | yes | yes | yes | no | no |
| stress and failure | yes | yes | no | optional | yes | yes | yes | partial | no | no |
| recovery validation | no | yes | no | no | yes | yes | yes | partial | no | no |
| postmortem analysis | input only | input only | no | screenshots | yes | yes | yes | yes | optional | optional |

## 8.1 Engineering loop matrix

| Loop | Deliverable | Tools |
|---|---|---|
| local developer loop | quick baseline and browser sanity | `k6`, `Playwright` |
| CI loop | regressions and hot-path slowdowns | `pytest-benchmark`, `Promptfoo`, optionally `Playwright` |
| staging loop | baseline + peak + dashboards | `k6`, `Locust`, OTel, Prometheus, Grafana |
| pre-prod loop | failure-under-load + recovery proof | `Locust`, chaos triggers, OTel, Grafana |
| postmortem loop | traces, metrics, screenshots, quality drift review | OTel, Grafana, Langfuse/Phoenix, Ragas |

## 9. Benchmarking Matrix

This is the “benchmark each tool” view.

| Tool | Benchmark target | Good benchmark examples | Main output |
|---|---|---|---|
| `k6` | HTTP/API performance | gateway QPS, retrieval endpoint latency, inference endpoint latency | latency and throughput summary |
| `Locust` | multi-step workflow performance | ask -> MCP call -> degraded draft, replay worker drain | workflow throughput and failure profile |
| `pytest-benchmark` | code hot-path performance | reranking code, token estimation, JSON serialization, scoring paths | local benchmark baseline |
| `Playwright` | browser performance | ask page load, upload form latency, failed API UX timing | user-visible timing and failures |
| `OpenTelemetry` | trace completeness | gateway -> retrieval -> inference -> MCP coverage | trace quality and missing-span analysis |
| `Prometheus` | metrics completeness | breaker, tool outcomes, replay backlog, latency histograms | time-series metric coverage |
| `Grafana` | dashboard usefulness | operator latency dashboard, MCP health board, replay dashboard | human-usable visual evidence |
| `Langfuse` / `Phoenix` | AI run explainability | prompt version comparison, retrieval path inspection, tool choice traces | run-level AI visibility |
| `Ragas` | RAG quality | faithfulness, answer relevance, context precision | quality score reports |
| `Promptfoo` | prompt safety and regression | prompt version A vs B, model A vs B, structured output checks | eval pass/fail and comparison report |

## 9.1 Benchmark matrix by repo-critical path

| Critical path | Benchmark type | Key metrics | Failure signal |
|---|---|---|---|
| ask flow | end-to-end latency | p95, p99, error rate, token cost | rising latency with flat CPU often means downstream wait |
| retrieval flow | service benchmark | retrieval p95, cache hit rate, backend timeout rate | cache miss storm or backend saturation |
| MCP tool call | workflow benchmark | tool latency, degraded rate, denial rate | 5xx spikes, breaker opening, draft surge |
| replay recovery | recovery benchmark | oldest pending age, replay throughput, replay success | backlog not draining after dependency recovery |
| browser ask page | UX benchmark | time to usable, failed-request UX, console errors | fast API but broken user perception |

## 10. Scenario Matrix

You asked for a deep matrix.
The most useful way to organize that is by scenario.

| Scenario | Primary tool | Secondary tools | What to prove |
|---|---|---|---|
| baseline API traffic | `k6` | Prometheus, Grafana, OTel | normal traffic stays within latency target |
| workflow under burst | `Locust` | Prometheus, Grafana, OTel | multi-step flows stay correct under concurrency |
| frontend under slow APIs | `Playwright` | browser DevTools, OTel | user sees useful loading and error states |
| MCP outage under load | `Locust` | OTel, Prometheus, Grafana | degraded draft fallback works and no cascade occurs |
| replay recovery | `Locust` | Prometheus, Grafana, OTel | backlog drains and replay succeeds after recovery |
| hot-path code regression | `pytest-benchmark` | CI | local slowdowns are caught before merge |
| prompt regression | `Promptfoo` | Langfuse, Ragas | prompt changes do not silently degrade quality |
| retrieval quality drift | `Ragas` | Langfuse, Grafana | quality changes are detected and explained |

## 10.1 Deep scenario pack

If you want the “deep matrix” version, start with these named scenarios:

1. `baseline_ask_traffic`
   normal ask load against gateway, retrieval, inference
2. `peak_ask_traffic`
   burst ask load to expose p95 drift
3. `retrieval_cold_cache`
   flush cache and watch warm-up behavior
4. `mcp_outage_under_load`
   MCP failure while action traffic continues
5. `breaker_open_fast_reject`
   prove fail-fast instead of retry storm
6. `replay_backlog_recovery`
   measure drain rate after dependency recovery
7. `frontend_slow_api_ux`
   prove UI behavior under latency and failures
8. `prompt_regression_compare`
   compare prompt or model versions
9. `retrieval_quality_regression`
   compare retrieval pipeline quality before and after changes

## 11. Reporting Format

Every performance or load test should generate a report with the same shape.

### Minimum report sections

1. scope
2. environment
3. dataset or fixtures
4. workload definition
5. thresholds
6. results
7. failures
8. traces and dashboards used
9. bottlenecks observed
10. recommended actions

### Minimum result table

| Metric | Baseline | Peak | Stress | Recovery | Target | Status |
|---|---:|---:|---:|---:|---:|---|
| p95 latency | | | | | | |
| error rate | | | | | | |
| breaker-open rate | | | | | | |
| degraded draft rate | | | | | | |
| replay lag | | | | | | |
| retrieval latency | | | | | | |
| token cost / request | | | | | | |

## 11.1 Recommended report filenames

Use deterministic report names:

- `reports/performance/YYYY-MM-DD-baseline-api.md`
- `reports/performance/YYYY-MM-DD-peak-ask.md`
- `reports/performance/YYYY-MM-DD-stress-mcp.md`
- `reports/performance/YYYY-MM-DD-recovery-replay.md`

## 11.2 Recommended report evidence bundle

Each report should link to:

- raw load summary
- Grafana screenshots or dashboard URLs
- trace IDs or trace links
- relevant logs
- incident notes if a threshold was exceeded
- recommended actions and owners

## 11.3 Decision matrix for report outcomes

| Outcome | Meaning | Action |
|---|---|---|
| pass | all thresholds met | keep baseline as reference |
| pass with warnings | acceptable but degrading | create follow-up issue before scale-up |
| fail safe | threshold missed but system degraded correctly | improve capacity or latency, keep resilience behavior |
| fail unsafe | threshold missed and system cascaded or corrupted workflow | block release |

## 12. Recommended First Implementation For This Repo

If you want the smallest useful implementation, do this first:

### Install first

- `k6`
- `OpenTelemetry`
- `Prometheus`
- `Grafana`

### Add next

- `Locust`
- `Langfuse` or `Phoenix`

### Add after that

- `Playwright`
- `pytest-benchmark`
- `Ragas`
- `Promptfoo`

### First benchmark pack

1. gateway baseline load
2. retrieval baseline load
3. inference baseline load
4. MCP outage under traffic
5. replay recovery

## 12.1 Concrete first backlog

The first practical backlog should be:

1. create `scripts/load/k6/`
2. add one gateway baseline scenario
3. add one retrieval baseline scenario
4. add one inference baseline scenario
5. create `scripts/load/locust/`
6. add one MCP degraded scenario
7. add one replay recovery scenario
8. add one Grafana dashboard for:
   - latency
   - breaker state
   - draft backlog
   - replay throughput
9. add one report template under `reports/performance/`

## 12.2 Suggested initial thresholds

Use placeholder thresholds first, then tune with real data.

| Path | Initial target |
|---|---|
| gateway p95 | `< 200ms` excluding backend wait |
| retrieval p95 | `< 750ms` |
| ask flow p95 | `< 3s` baseline |
| ask flow peak p95 | `< 5s` |
| MCP degraded path | no cascade, draft persisted correctly |
| replay recovery | backlog draining trend visible within first recovery window |

## 13. Tool-by-Tool Summary

### `k6`

- install if you want fast API load generation
- use for baseline, peak, and simple stress tests
- not enough by itself for workflow or replay testing

### `Locust`

- install if you want realistic workflow traffic
- use for MCP, draft, replay, and stateful scenarios
- stronger than `k6` once flows become multi-step

### `pytest-benchmark`

- install if you want code-level regression protection
- use for hot Python paths only
- not a replacement for service or workflow load tests

### `Playwright`

- install if you care about browser-visible performance and F12 failures
- use for user-critical pages and slow-API rendering
- complements backend tests, does not replace them

### `OpenTelemetry`

- install immediately if you want trustworthy diagnosis
- required to understand request flow under load
- not a load tool, but required during load testing

### `Prometheus`

- install immediately if you want metric evidence
- required for latency, error, breaker, backlog, and replay metrics

### `Grafana`

- install immediately if humans need to understand the test while it runs
- required to turn raw metrics into operational decisions

### `Langfuse` or `Phoenix`

- install when AI workflow visibility becomes important
- use to inspect prompt, retrieval, and tool behavior under load

### `Ragas`

- install when retrieval quality needs benchmarking
- use for correctness and groundedness, not throughput

### `Promptfoo`

- install when prompt changes become a release risk
- use for regression gates and model/prompt comparison

## 13.1 What each tool must generate

You asked for what each tool must generate.
This is the strictest useful interpretation.

| Tool | Must generate |
|---|---|
| `k6` | latency summary, throughput summary, threshold pass/fail, raw request metrics |
| `Locust` | workflow throughput, failure distribution, concurrency behavior, scenario outcome summary |
| `pytest-benchmark` | benchmark baseline, regression delta, hot-path timing report |
| `Playwright` | screenshots or traces, browser timing, failure-state evidence |
| `OpenTelemetry` | trace spans, cross-service timing evidence, missing-span gaps |
| `Prometheus` | numeric metrics history |
| `Grafana` | dashboard panels and incident-readable visuals |
| `Langfuse` / `Phoenix` | AI run traces, prompt/retrieval/tool metadata |
| `Ragas` | retrieval/groundedness score report |
| `Promptfoo` | prompt/model comparison report and pass/fail assertions |

## 13.2 What each tool cannot replace

| Tool | Cannot replace |
|---|---|
| `k6` | workflow realism, browser UX, AI quality scoring |
| `Locust` | browser UX, code micro-benchmarking |
| `pytest-benchmark` | system load testing |
| `Playwright` | backend throughput tests |
| `OpenTelemetry` | metrics storage and dashboards |
| `Prometheus` | traces and AI quality evaluation |
| `Grafana` | load generation |
| `Langfuse` / `Phoenix` | infra metrics and generic SRE dashboards |
| `Ragas` | runtime observability |
| `Promptfoo` | production monitoring |

## 14. Bottom Line

If the question is “what should I install first,” the answer is:

1. `k6`
2. `OpenTelemetry`
3. `Prometheus`
4. `Grafana`
5. `Locust`
6. `Langfuse` or `Phoenix`

If the question is “how do I build the deep matrix,” the answer is:

- do not use one giant score
- use task, operation, error, observability, loop, and benchmarking matrices
- keep each tool assigned to a clear job

That is how performance and load testing become operational engineering instead of random test runs.

## 15. Final recommendation

If you want the shortest serious answer:

- install `k6`, `OpenTelemetry`, `Prometheus`, and `Grafana` first
- add `Locust` next for workflow and replay scenarios
- add `Langfuse` or `Phoenix` when AI-path diagnosis becomes necessary
- add `Playwright`, `pytest-benchmark`, `Ragas`, and `Promptfoo` as depth layers

If you want the deepest practical setup:

- require every tool to generate a concrete report artifact
- keep task, operation, error, observability, loop, and benchmark matrices separate
- benchmark each critical path, not just each endpoint
- treat degraded mode and recovery as first-class performance scenarios
