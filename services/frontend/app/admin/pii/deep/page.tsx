'use client';

/**
 * PII (Personally Identifiable Information) detection + redaction
 * for multi-tenant audit logs and AI outputs.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'pii-detection-redaction',
    title: '1. PII detection + redaction',
    status: 'shipped',
    coreConcept: 'PII detection runs at two boundaries: ingestion (mask before storing) and output (redact before returning to tenant). Both use a layered pipeline: regex (cheap), NER (broader), policy (per-tenant, per-jurisdiction).',
    oneLiner: 'PII = audit-grade discipline at the boundary; never trust the model to redact itself.',
    businessContext: 'GDPR, HIPAA, and EU AI Act all require demonstrable PII handling. The cost of a leak — €20M / 4% turnover under GDPR, contract loss in B2B — is far higher than the cost of redaction.',
    fiveW: {
      what: 'A pipeline that detects PII (email, phone, SSN, name, ID) in ingested content and AI outputs, then masks or redacts based on per-tenant policy.',
      why: 'Models hallucinate PII; logs leak PII; cross-tenant queries can expose PII without RLS. Multi-layered defense at boundaries is the only reliable answer.',
      where: 'Ingestion: ingestion-svc runs PIIDetector before chunking. Output: inference-svc filters streaming response. Audit: audit_log writes use redact_pii=True flag.',
      when: 'Always for regulated tenants (HIPAA / GDPR / financial). Optional for internal-only tenants but recommended.',
      who: 'Security owns the policy. Data team owns the detection model. Platform owns the integration. Compliance audits the chain.',
    },
    interview30s: 'PII handling has three boundaries: ingestion (mask before chunking), output (redact streaming response), and audit (redact_pii flag on audit_log writes). Detection is layered: regex catches the obvious (email, phone), NER catches the contextual (names, addresses), policy enforces per-tenant rules. The non-negotiable test is a drill that pumps known PII through the pipeline and asserts it never reaches storage or output without redaction.',
    coreBuildingBlocks: [
      'Regex detectors — email, phone, SSN, credit card, IBAN',
      'NER (Named Entity Recognition) — spaCy / transformers for PERSON / ORG / LOC',
      'Per-tenant policy — strict (HIPAA) / standard (GDPR) / minimal (internal)',
      'Redaction strategies — mask, hash, tokenize, drop',
      'Audit chain — every redaction logged with policy version',
      'Drill — known PII corpus passes through pipeline, output verified clean',
    ],
    flowchart: `flowchart LR
  IN[Input text] --> REGEX[Regex pass]
  REGEX --> NER[NER model]
  NER --> POL[Policy resolver]
  POL --> ACT{Policy action}
  ACT -->|mask| M["Mask: ***@***.com"]
  ACT -->|hash| H[Hash tokenize]
  ACT -->|drop| D[Drop chunk entirely]
  M --> OUT[Output text]
  H --> OUT
  D --> OUT
  OUT --> AUD[audit_log write with policy_version]`,
    sequence: `sequenceDiagram
  autonumber
  participant Cli as Client
  participant Svc as Service
  participant PII as PIIDetector
  participant POL as PolicyResolver
  participant DB as DB
  Cli->>Svc: text input
  Svc->>PII: detect entities
  PII-->>Svc: spans + types
  Svc->>POL: resolve tenant policy
  POL-->>Svc: action per type
  Svc->>Svc: apply redactions
  Svc->>DB: store redacted + audit row
  DB-->>Svc: ok
  Svc-->>Cli: redacted output`,
    coreLayers: [
      { layer: 'Regex layer', responsibility: 'Cheap pattern matchers for email, phone, SSN, IBAN, credit card. Catches the obvious; low false-positive.' },
      { layer: 'NER layer', responsibility: 'spaCy or transformers model for PERSON / ORG / LOC / DATE. Catches contextual PII; higher false-positive.' },
      { layer: 'Policy layer', responsibility: 'Per-tenant + per-jurisdiction rules. HIPAA → mask all PHI; GDPR → consent-aware; internal → minimal.' },
      { layer: 'Action layer', responsibility: 'Mask (***@***), hash (deterministic), tokenize (recoverable), drop (entire span).' },
      { layer: 'Audit layer', responsibility: 'Every detection + redaction logged with policy_version + actor + timestamp. Integrity hash-chained.' },
    ],
    problem: 'PII leaks via three paths: ingested-stored, output-returned, audit-logged. App-level filtering misses contextual PII; model-level relies on the model. Boundary discipline is the only structural answer.',
    whyThisApproach: 'Layered detection (regex + NER) catches both obvious and contextual PII. Per-tenant policy lets one platform serve regulated and internal customers without code branches. Audit chain proves compliance to auditors.',
    whenToUse: [
      'Multi-tenant SaaS with regulated customers',
      'AI outputs delivered to end users',
      'Audit logs that may be reviewed by humans',
      'Cross-border data flows (GDPR, schrems-II)',
    ],
    whenNotToUse: [
      'Single-tenant internal tooling — overkill',
      'Synthetic-only training data — no real PII',
      'Pure metadata stores (no free text)',
    ],
    input: 'Free-text input + tenant_id + content_type (chunk, query, output)',
    process: [
      'Run regex detectors — collect candidate spans',
      'Run NER model on remaining text',
      'Merge spans, deduplicate overlap',
      'Resolve per-tenant policy',
      'Apply redaction action per span',
      'Write audit row with policy_version + redaction_count',
    ],
    output: 'Redacted text + audit chain entry. Original text preserved only in TTL\'d processing buffer if policy allows.',
    alternatives: [
      { name: 'AWS Comprehend / Azure DLP', tradeoff: 'Managed; data leaves region; per-call cost; vendor lock-in' },
      { name: 'Presidio (Microsoft)', tradeoff: 'Open-source; Python; self-host; needs ops investment' },
      { name: 'Custom regex only', tradeoff: 'Cheap; misses contextual PII; high false-negative on names' },
      { name: 'LLM-based redaction', tradeoff: 'Catches edge cases; expensive; non-deterministic; needs eval' },
    ],
    challenges: [
      'False positives reject legitimate input (e.g., product names matching person names)',
      'Multi-language NER weak on non-Latin scripts',
      'Performance — NER is 10-50ms per kb; budget tight',
      'Policy drift across jurisdictions',
      'Tokenization loses recoverability if hash is not reversible',
    ],
    edgeCases: [
      { case: 'NER misses a name in unusual context', solution: 'Layer fallback: regex for known formats + per-tenant allow-list of legitimate names' },
      { case: 'Customer wants legitimate PII passthrough (e.g., support ticket)', solution: 'Per-document policy override with explicit consent + audit row' },
      { case: 'Streaming output exceeds buffer', solution: 'Redact in chunks; never wait for full output if streaming SLA' },
      { case: 'False-positive on placeholder data', solution: 'Tenant policy: skip detection on tagged "synthetic" content' },
    ],
    failureModes: [
      { mode: 'PII detector down', detect: '/health/upstreams kind=pii', recover: 'Fail-closed: reject writes; alert on-call' },
      { mode: 'Policy resolver returns wrong tenant', detect: 'Audit row tenant_id mismatch', recover: 'Roll back deploy; verify tenant_connection() chain' },
      { mode: 'NER model degrades after retrain', detect: 'PII recall drops on benchmark', recover: 'Roll back model; re-eval; gate by drill' },
      { mode: 'Audit chain breaks (redaction not logged)', detect: 'Hash-chain integrity drill goes red', recover: 'Recompute chain from source; investigate gap' },
    ],
    monitoring: [
      'Per-tenant PII detections / day',
      'Detection latency p50/p99',
      'False-positive rate (manual review samples)',
      'Audit chain integrity drill green/red',
      'Policy version distribution across tenants',
    ],
    testing: [
      'Drill: known PII corpus → assert all redacted in output + audit',
      'Drill: synthetic name list → false-positive rate within tolerance',
      'Drill: streaming chunk redaction matches batch redaction',
      'Eval: per-jurisdiction policy correctness',
    ],
    security: [
      'PII never stored in raw form past processing buffer',
      'Hash-chained audit log per tenant',
      'Per-tenant policy version pinned per deploy',
      'Encryption at rest + in transit',
      'Access to raw PII spans audited',
    ],
    scaling: [
      'Regex layer: O(n) per text — trivial',
      'NER layer: GPU batching for high-volume tenants',
      'Per-tenant policy cached in Redis with TTL',
      '10x: scale NER replicas + batch sizes; 100x: dedicate GPU pool',
    ],
    maturity: {
      mvp: 'Regex-only; per-tenant policy in YAML',
      production: 'Regex + NER + policy resolver + audit chain + drills',
      enterprise: 'Multi-language NER + per-tenant model + LLM fallback + compliance dashboard',
    },
    limitations: [
      'NER has irreducible false-negative on creative PII patterns',
      'Performance budget tight for streaming SLA',
      'Cross-language coverage uneven (Latin scripts strong; CJK weaker)',
      'Tokenization loses semantic context for downstream models',
    ],
    projectFit: [
      'libs/py/documind_core/pii.py — PIIDetector + PolicyResolver',
      'libs/py/documind_core/audit_log.py — redact_pii flag',
      'governance.audit_log table — audit chain',
      'mcp/tests/drill_pii_redaction.py — pipeline drill',
    ],
    interviewLine: 'PII handling lives at three boundaries: ingest, output, and audit. Detection is layered (regex + NER + policy). The non-negotiable test is a drill that pumps known PII through and asserts redaction at every boundary.',
    finalScript: 'PII handling has three boundaries — ingest, output, and audit — and a layered detection pipeline at each. Regex catches the obvious (email, phone, SSN). NER catches the contextual (names, addresses, organizations). Policy resolves per-tenant + per-jurisdiction rules: HIPAA masks all PHI, GDPR is consent-aware, internal is minimal. Actions are mask, hash, tokenize, or drop. Every redaction writes an audit row with policy_version, hash-chained per tenant. The non-negotiable test is a drill that pumps a known-PII corpus through the pipeline and asserts no PII survives to storage or output. Mocks lie about regex-NER coverage; only the live pipeline shows where false-negatives hide.',
  },
];

export default function PiiDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">PII — Deep Dive</h1>
        <p className="design-areas-sub">
          PII detection + redaction at three boundaries (ingest, output, audit). Layered
          regex + NER + per-tenant policy. Drill-locked discipline.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
