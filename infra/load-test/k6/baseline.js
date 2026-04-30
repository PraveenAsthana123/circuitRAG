// k6 baseline load test — circuitRAG / DocuMind platform
//
// Five-phase profile per global §47.10 + repo's
// /admin/load-testing/deep playbook:
//
//   PHASE 1 (smoke):   1 VU,    10s     — sanity, no errors expected
//   PHASE 2 (load):    100 VU,  3m      — sustain SLA target
//   PHASE 3 (stress):  100→1000 VU, 5m  — find breakpoint
//   PHASE 4 (soak):    100 VU,  10m     — memory growth detection
//   PHASE 5 (spike):   0→2000 VU 60s    — recovery test
//
// Targets (configurable via env):
//   BASE_URL           default http://localhost:8080  (api-gateway / nginx)
//   AUTH_BEARER        default unset (some endpoints require it)
//
// Run individual phases:
//   k6 run --stage 0:1,5s:0       infra/load-test/k6/baseline.js   # smoke only
//   k6 run                        infra/load-test/k6/baseline.js   # full profile
//   k6 run -e BASE_URL=https://...  infra/load-test/k6/baseline.js
//
// Run via wrapper (recommended):
//   bash scripts/load-test.sh smoke          # fast sanity
//   bash scripts/load-test.sh load           # 100 VU sustain
//   bash scripts/load-test.sh stress         # ramp to 1000
//   bash scripts/load-test.sh soak           # 10-min sustain
//   bash scripts/load-test.sh spike          # 0→2000 in 60s
//   bash scripts/load-test.sh full           # all 5 phases sequentially
//
// Exit code: 0 if all SLOs green; 99 if any threshold breached.
//
// Locked by mcp/tests/drill_load_test_setup.py.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const AUTH = __ENV.AUTH_BEARER ? `Bearer ${__ENV.AUTH_BEARER}` : '';

// Custom metrics — labelled for per-route SLO breakdown.
export const trendHealth = new Trend('documind_health_duration_ms', true);
export const trendApi = new Trend('documind_api_duration_ms', true);
export const counterErrors = new Counter('documind_errors_total');

// Stage profile — controlled by PROFILE env var so the wrapper can
// run individual phases without editing this file.
const PROFILE = __ENV.PROFILE || 'load';

const STAGES = {
  smoke:  [{ target: 1,    duration: '10s' }],
  load:   [
    { target: 100,  duration: '30s' },   // ramp
    { target: 100,  duration: '3m' },    // sustain at SLA target
    { target: 0,    duration: '15s' },   // ramp down
  ],
  stress: [
    { target: 100,   duration: '30s' },
    { target: 500,   duration: '2m' },
    { target: 1000,  duration: '2m' },   // find breakpoint
    { target: 0,     duration: '30s' },
  ],
  soak:   [
    { target: 100,  duration: '30s' },
    { target: 100,  duration: '10m' },   // 10-min sustain — memory growth window
    { target: 0,    duration: '30s' },
  ],
  spike:  [
    { target: 100,   duration: '15s' },
    { target: 2000,  duration: '60s' },  // 0→2000 in 60s
    { target: 100,   duration: '60s' },  // recovery
    { target: 0,     duration: '15s' },
  ],
};

export const options = {
  stages: STAGES[PROFILE] || STAGES.load,
  // SLO thresholds per global §47.10:
  //   p95 latency < 500ms for API; < 100ms for /healthz
  //   error rate < 1% under load
  thresholds: {
    'http_req_duration{name:health}':      ['p(95)<100'],
    'http_req_duration{name:api}':         ['p(95)<500'],
    'http_req_failed':                     ['rate<0.01'],
    'documind_errors_total':               ['count<1000'],
  },
  noConnectionReuse: false,
  insecureSkipTLSVerify: true, // dev nginx has self-signed cert
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

function commonHeaders() {
  const h = { 'Accept': 'application/json' };
  if (AUTH) h['Authorization'] = AUTH;
  return h;
}

export default function () {
  // 1. Health probe — fast, no auth, must be sub-100ms p95
  {
    const r = http.get(`${BASE_URL}/healthz`, {
      headers: commonHeaders(),
      tags: { name: 'health' },
    });
    trendHealth.add(r.timings.duration);
    const ok = check(r, {
      'health 200':       (res) => res.status === 200,
      'health <100ms':    (res) => res.timings.duration < 100,
    });
    if (!ok) counterErrors.add(1);
  }

  // 2. API call — sidecar event submission (canonical hot path)
  {
    const payload = JSON.stringify({
      content: `load-test paste ${__VU}-${__ITER}`,
      source: 'load-test',
    });
    const apiHeaders = Object.assign({}, commonHeaders(), {
      'Content-Type': 'application/json',
    });
    const r = http.post(`${BASE_URL}/api/v1/sidecar/events`, payload, {
      headers: apiHeaders,
      tags: { name: 'api' },
    });
    trendApi.add(r.timings.duration);
    const ok = check(r, {
      'api 2xx or 401':   (res) => res.status === 201 || res.status === 401,
      'api <500ms p95':   (res) => res.timings.duration < 500,
    });
    if (!ok) counterErrors.add(1);
  }

  sleep(1);
}

// Lifecycle hooks — log start/end markers for the wrapper to parse.
export function setup() {
  console.log(`[k6] PROFILE=${PROFILE} BASE_URL=${BASE_URL} stages=${JSON.stringify(STAGES[PROFILE] || STAGES.load)}`);
  // Sanity: hit /healthz once before the test starts.
  const r = http.get(`${BASE_URL}/healthz`, { tags: { name: 'setup' } });
  if (r.status !== 200) {
    console.error(`[k6] setup health check failed: ${r.status} ${r.body && r.body.toString().slice(0, 200)}`);
  }
  return { started_at: new Date().toISOString() };
}

export function teardown(data) {
  console.log(`[k6] started_at=${data.started_at} ended_at=${new Date().toISOString()}`);
}
