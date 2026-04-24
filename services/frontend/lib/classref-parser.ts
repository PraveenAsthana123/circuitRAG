/**
 * Extract readable repo paths from a design-area `classRef` string.
 *
 * classRef is free-form — examples from design-areas.ts:
 *   "infra/nginx/nginx.conf + services/api-gateway/cmd/main.go"
 *   "documind_core/middleware.py, encryption.py, infra/istio/20-peer-authentication.yaml"
 *   "libs/py/documind_core/ccb.py"
 *   "DbClient.tenant_connection + FORCE RLS migrations"
 *   "schema-per-service in db_client.py + migrations"
 *   "spec only"
 *
 * The parser extracts anything that looks like a file path with a known
 * extension, normalizes `documind_core/X.py` to `libs/py/documind_core/X.py`
 * since the repo keeps the shared Python package under libs/py/.
 */

const EXT = /\.(py|sql|go|ts|tsx|js|jsx|yaml|yml|json|conf|toml|md)$/;

/** Map of bare class / concept names → representative file(s) in the repo. */
const CLASS_TO_FILES: Record<string, string[]> = {
  'DbClient.tenant_connection': ['libs/py/documind_core/db_client.py'],
  'DbClient': ['libs/py/documind_core/db_client.py'],
  'documind_core.cache': ['libs/py/documind_core/cache.py'],
  'DocumentRepo.ALLOWED_TRANSITIONS': ['services/ingestion-svc/app/repositories/document_repo.py'],
  'DocumentRepo': ['services/ingestion-svc/app/repositories/document_repo.py'],
  'tenant_connection': ['libs/py/documind_core/db_client.py'],
  'IdempotencyStore': ['libs/py/documind_core/idempotency.py'],
  'IdempotencyMiddleware': ['libs/py/documind_core/idempotency.py'],
  'AgentLoopCircuitBreaker': ['libs/py/documind_core/breakers.py'],
  'PromptBuilder': ['libs/py/documind_core/prompt_builder.py'],
  'PROMPT_TEMPLATES': ['libs/py/documind_core/prompt_templates.py'],
  'GuardrailChecker': ['libs/py/documind_core/ai_governance.py'],
  'DocumentIngestionSaga._run_compensations': ['services/ingestion-svc/app/saga/document_saga.py'],
  'DocumentIngestionSaga': ['services/ingestion-svc/app/saga/document_saga.py'],
  'QdrantRepo.ensure_collection': ['services/retrieval-svc/app/services/vector_searcher.py'],
  'QdrantRepo': ['services/retrieval-svc/app/services/vector_searcher.py'],
  'Neo4jRepo': ['services/retrieval-svc/app/services/graph_searcher.py'],
  'Cache.tenant_key': ['libs/py/documind_core/cache.py'],
  'RateLimiter.tenant_key': ['libs/py/documind_core/rate_limit.py'],
  'PromptInjectionDetector': ['libs/py/documind_core/ai_governance.py'],
  'PIIScanner': ['libs/py/documind_core/ai_governance.py'],
  'AdversarialInputFilter': ['libs/py/documind_core/ai_governance.py'],
  'AIExplainer': ['libs/py/documind_core/ai_governance.py'],
  'ResponsibleAIChecker': ['libs/py/documind_core/ai_governance.py'],
  'InterpretabilityTrace': ['libs/py/documind_core/ai_governance.py'],
};

const SERVICE_ROOTS: Record<string, string> = {
  'services/ingestion-svc': 'services/ingestion-svc/app/main.py',
  'services/retrieval-svc': 'services/retrieval-svc/app/main.py',
  'services/inference-svc': 'services/inference-svc/app/main.py',
  'services/evaluation-svc': 'services/evaluation-svc/app/main.py',
  'services/identity-svc': 'services/identity-svc/app/main.py',
  'services/governance-svc': 'services/governance-svc/app/main.py',
  'services/observability-svc': 'services/observability-svc/app/main.py',
  'services/finops-svc': 'services/finops-svc/app/main.py',
  'services/api-gateway': 'services/api-gateway/cmd/main.go',
  'services/frontend': 'services/frontend/app/layout.tsx',
};

/** Split by common separators and pull tokens that look like paths or known names. */
export function parseClassRef(classRef: string): string[] {
  const paths: string[] = [];
  const tokens = classRef.split(/\s*\+\s*|,\s*|;\s*|::/);
  for (const raw of tokens) {
    const t = raw.trim();
    if (!t) continue;

    // Explicit class / concept mapping.
    const [head] = t.split(/[\s(]/);
    if (CLASS_TO_FILES[head]) {
      for (const f of CLASS_TO_FILES[head]) paths.push(f);
      continue;
    }

    // Service-root shorthand.
    if (SERVICE_ROOTS[head]) {
      paths.push(SERVICE_ROOTS[head]);
      continue;
    }

    // Path with a recognized extension.
    const m = t.match(/^([A-Za-z0-9_./\-]+)/);
    if (!m) continue;
    const candidate = m[1];
    if (EXT.test(candidate) && (candidate.includes('/') || BARE_DOCUMIND_CORE_FILES.has(candidate))) {
      paths.push(normalize(candidate));
    }
  }
  return Array.from(new Set(paths));
}

const BARE_DOCUMIND_CORE_FILES = new Set([
  'ai_governance.py', 'ccb.py', 'breakers.py', 'circuit_breaker.py',
  'db_client.py', 'cache.py', 'kafka_client.py', 'logging_config.py',
  'middleware.py', 'encryption.py', 'observability.py', 'outbox.py',
  'idempotency.py', 'config.py', 'exceptions.py', 'rate_limit.py',
]);

function normalize(p: string): string {
  if (p.startsWith('documind_core/')) return `libs/py/${p}`;
  // Bare libs/py/documind_core filename: "ai_governance.py" → full path.
  if (BARE_DOCUMIND_CORE_FILES.has(p)) return `libs/py/documind_core/${p}`;
  return p;
}
