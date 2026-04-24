/**
 * Per-tool pointers into the actual implementing files.
 *
 * Paths are relative to the repo root. The detail page reads these at
 * build-time via fs.readFile (RSC-safe) and renders them as code blocks
 * beneath the tabs — so you can *see* the code, not just read a claim
 * about it.
 */
export type CodeRef = {
  label: string;
  path: string;        // repo-relative
  language?: string;   // for a future highlighter
  maxLines?: number;   // truncate very long files
};

export const TOOL_CODE_REFS: Record<string, CodeRef[]> = {
  'postgres-rls': [
    { label: 'postgres-init.sql — role separation', path: 'scripts/postgres-init.sql', language: 'sql' },
    { label: 'FORCE RLS migration', path: 'services/ingestion-svc/migrations/003_rls_force.sql', language: 'sql' },
    { label: 'tenant_connection context manager', path: 'libs/py/documind_core/db_client.py', language: 'python', maxLines: 180 },
    { label: 'Cross-tenant RLS test (dual-connection)', path: 'libs/py/tests/test_rls_isolation.py', language: 'python' },
  ],
  'qdrant': [
    { label: 'Vector searcher (retrieval-svc)', path: 'services/retrieval-svc/app/services/vector_searcher.py', language: 'python', maxLines: 200 },
  ],
  'neo4j': [
    { label: 'Graph searcher', path: 'services/retrieval-svc/app/services/graph_searcher.py', language: 'python', maxLines: 200 },
  ],
  'redis': [
    { label: 'Cache with tenant-key namespace', path: 'libs/py/documind_core/cache.py', language: 'python', maxLines: 200 },
  ],
  'kafka': [
    { label: 'Kafka client (CloudEvents + DLQ)', path: 'libs/py/documind_core/kafka_client.py', language: 'python', maxLines: 250 },
    { label: 'Outbox pattern', path: 'libs/py/documind_core/outbox.py', language: 'python', maxLines: 200 },
  ],
  'ollama-vllm': [
    { label: 'Embedder client', path: 'services/retrieval-svc/app/services/embedder_client.py', language: 'python', maxLines: 180 },
  ],
  'istio': [
    { label: 'PeerAuthentication (mTLS STRICT)', path: 'infra/istio/20-peer-authentication.yaml', language: 'yaml' },
    { label: 'AuthorizationPolicy', path: 'infra/istio/30-authorization-policy.yaml', language: 'yaml' },
  ],
  'api-gateway': [
    { label: 'Gateway main (Go)', path: 'services/api-gateway/cmd/main.go', language: 'go', maxLines: 200 },
  ],
  'nginx-cdn': [
    { label: 'nginx.conf (edge + cache)', path: 'infra/nginx/nginx.conf', language: 'nginx' },
  ],
  'circuit-breakers': [
    { label: 'Generic CircuitBreaker', path: 'libs/py/documind_core/circuit_breaker.py', language: 'python' },
    { label: '5 specialized breakers', path: 'libs/py/documind_core/breakers.py', language: 'python', maxLines: 300 },
  ],
  'ccb': [
    { label: 'Cognitive Circuit Breaker', path: 'libs/py/documind_core/ccb.py', language: 'python', maxLines: 300 },
    { label: 'CCB tests', path: 'libs/py/tests/test_ccb.py', language: 'python', maxLines: 200 },
  ],
  'elk': [
    { label: 'Logging config (JSON via structlog)', path: 'libs/py/documind_core/logging_config.py', language: 'python', maxLines: 180 },
  ],
  'otel-stack': [
    { label: 'Observability module', path: 'libs/py/documind_core/observability.py', language: 'python', maxLines: 200 },
    { label: 'Observability Circuit Breaker', path: 'libs/py/documind_core/breakers.py', language: 'python', maxLines: 40 },
  ],
};
