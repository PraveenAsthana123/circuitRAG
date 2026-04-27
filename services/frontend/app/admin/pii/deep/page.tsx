'use client';

/**
 * PII (Personally Identifiable Information) detection + redaction
 * for multi-tenant audit logs and AI outputs.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
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
    implementationSteps: [
      { step: 'Define detector chain', logic: 'Regex (high precision, low recall) → NER (contextual) → policy (per-tenant + jurisdiction).' },
      { step: 'Set per-tenant policies', logic: 'HIPAA = mask all PHI; GDPR = consent-aware; internal = minimal redaction.' },
      { step: 'Pick action per category', logic: 'Mask (***), hash (HMAC), tokenize (reversible by ops), or drop (delete).' },
      { step: 'Boundary 1: ingest', logic: 'Detect at parse-time before chunks land in Postgres / Qdrant.' },
      { step: 'Boundary 2: output', logic: 'Re-scan LLM responses before streaming to client.' },
      { step: 'Boundary 3: audit', logic: 'Audit_log writes use redact_pii=True; never log raw PII.' },
      { step: 'Drill the negative', logic: 'Inject known-PII corpus; assert ZERO survives to storage or output.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/pii.py — layered detector + per-tenant policy
import re
from dataclasses import dataclass
from typing import Literal
import spacy

NLP = spacy.load("en_core_web_sm")  # NER
EMAIL = re.compile(r"\\b[\\w.+-]+@[\\w-]+\\.[\\w.-]+\\b")
PHONE = re.compile(r"\\b\\+?[\\d\\s().-]{7,}\\b")
SSN = re.compile(r"\\b\\d{3}-\\d{2}-\\d{4}\\b")

Action = Literal["mask", "hash", "tokenize", "drop"]

@dataclass
class Policy:
    jurisdiction: str  # "hipaa" | "gdpr" | "internal"
    rules: dict[str, Action]
    version: str

def detect_layers(text: str) -> list[tuple[int, int, str]]:
    """Returns (start, end, category) tuples in document order."""
    spans = []
    for cat, pattern in [("EMAIL", EMAIL), ("PHONE", PHONE), ("SSN", SSN)]:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), cat))
    doc = NLP(text)
    for ent in doc.ents:
        if ent.label_ in ("PERSON", "ORG", "GPE"):
            spans.append((ent.start_char, ent.end_char, ent.label_))
    spans.sort()
    # merge overlapping spans
    merged = []
    for s in spans:
        if merged and s[0] < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], s[1]), merged[-1][2])
        else:
            merged.append(s)
    return merged

def redact(text: str, policy: Policy) -> tuple[str, list[dict]]:
    spans = detect_layers(text)
    audit = []
    out_chunks = []
    cursor = 0
    for start, end, cat in spans:
        action = policy.rules.get(cat, "mask")
        out_chunks.append(text[cursor:start])
        replacement = {
            "mask": "[REDACTED]",
            "hash": f"#{hash(text[start:end]) & 0xfffffff:x}",
            "tokenize": f"<tok:{cat}:{end-start}>",
            "drop": "",
        }[action]
        out_chunks.append(replacement)
        audit.append({
            "category": cat, "action": action,
            "policy_version": policy.version,
            "char_range": [start, end],
        })
        cursor = end
    out_chunks.append(text[cursor:])
    return "".join(out_chunks), audit`,
    },
    realUseCase: 'A HIPAA customer onboarded with 50K medical records. Pipeline: ingest detects 47 categories of PHI (regex + NER + custom medical terms). Policy: ALL mask except patient_id which tokenizes (reversible by ops only). Output boundary re-scans LLM responses before streaming. Drill harness pumped a public-PII corpus through; baseline 100% redaction. Then injected one synthetic typo ("john,smith" not "john.smith") — regex missed but NER caught. Without the layered approach, that one would have leaked.',
    prosCons: {
      pros: [
        'Three boundaries = defense in depth (no single point of failure)',
        'Per-tenant policy supports HIPAA + GDPR + internal in one platform',
        'Layered detection (regex + NER) catches both common + contextual PII',
        'Audit chain proves redaction happened (compliance evidence)',
        'Drill discipline catches false-negatives BEFORE they leak',
      ],
      cons: [
        'NER inference adds 30–80ms p95 per chunk',
        'False positives on names that look like common words ("Bill", "Mark")',
        'Tokenize-and-reverse path needs strict access control on the reverse key',
        'Policy churn: jurisdiction rules change, tested via re-running the drill set',
      ],
    },
    comparison: {
      left: 'Regex-only PII detection',
      right: 'Layered: regex + NER + per-tenant policy',
      rows: [
        { aspect: 'Recall on emails / SSNs', left: '~95%', right: '~99%' },
        { aspect: 'Recall on names / orgs', left: '~30%', right: '~85% (NER)' },
        { aspect: 'Per-jurisdiction support', left: 'One policy fits all', right: 'HIPAA / GDPR / internal independently' },
        { aspect: 'Latency overhead', left: '~2ms p95', right: '~30-80ms p95 (NER)' },
        { aspect: 'False-positive rate', left: 'Low (literal patterns only)', right: 'Higher; tunable via NER threshold' },
      ],
    },
    solutions: [
      { problem: 'NER false positives on common-word names', solution: 'Confidence threshold + per-tenant allowlist of common words' },
      { problem: 'Regex misses PII in malformed text', solution: 'NER backstop catches contextual mentions' },
      { problem: 'Output stream leaks PII generated by LLM', solution: 'Re-scan LLM responses pre-stream at output boundary' },
      { problem: 'Audit log itself leaks PII', solution: 'redact_pii=True flag on every audit write; verified by drill' },
      { problem: 'Tokenized values leaked via the reverse key', solution: 'BYPASSRLS on reverse + audit per access; key in HSM' },
    ],
    bestPractices: {
      do: [
        'Three boundaries: ingest, output, audit',
        'Layer regex + NER + policy for defense in depth',
        'Per-tenant policy versioned; audit logs cite policy_version',
        'Drill pumps known-PII corpus through; asserts zero survives',
        'NER + regex confidence thresholds tuned per jurisdiction',
      ],
      avoid: [
        'Regex-only detection (misses contextual PII)',
        'Single global policy across HIPAA/GDPR/internal',
        'Skipping the output-boundary scan ("LLM won\'t generate PII")',
        'Logging raw PII in audit for "convenience"',
      ],
      optimize: [
        'NER batching across chunks (3-5x throughput)',
        'Cache redaction results by chunk_hash + policy_version',
        'Quantize NER model to int8 for faster inference',
        'Sharded reverse-token key store for tokenize-action access control',
      ],
    },
    antiPatterns: [
      'PII handling at one boundary only (e.g., ingest only)',
      'Regex-only — misses 70% of names/orgs',
      'Single policy across jurisdictions',
      'No drill — you don\'t know what you\'re missing',
      'Tokenize-without-access-control on reverse',
      'Logging raw PII in audit',
    ],
    testTypes: [
      'Drill: known-PII corpus → assert zero PII in Postgres/Qdrant/audit/output',
      'Negative drill: synthetic typo PII (regex misses) → NER must catch',
      'Policy diff drill: HIPAA mask vs GDPR consent-aware on same input',
      'Performance drill: NER overhead p95 ≤ budget',
    ],
    testScenarios: [
      { scenario: 'Email "john@x.com" in user query', expected: 'Detected (EMAIL); masked at ingest before Postgres write' },
      { scenario: 'Patient name "John Smith" in medical record', expected: 'NER detects PERSON; HIPAA policy → mask' },
      { scenario: 'LLM response generates "+1-555-1234"', expected: 'Output boundary detects PHONE; mask before stream' },
      { scenario: 'Audit log write with raw payload', expected: 'redact_pii=True applied; raw PII never reaches DB' },
      { scenario: 'Tokenized patient_id used by support agent', expected: 'Reverse-token call gated + audited; key in HSM' },
    ],
    testData: [
      { type: 'Public PII corpus', example: '500 sentences with email/phone/SSN/names; baseline recall measured' },
      { type: 'Synthetic typo set', example: 'PII variants regex misses ("john,smith", "555  1234"); NER backstop tested' },
      { type: 'Per-jurisdiction fixture', example: 'Same record × HIPAA/GDPR/internal; outputs diverge per policy' },
    ],
    debuggingChecklist: [
      'PII leaked? Check which boundary missed (ingest? output? audit?)',
      'False positive on a common name? Check NER confidence + allowlist',
      'Latency spike? NER batching or quantization may have regressed',
      'Audit row has raw PII? redact_pii=True flag missing on the write call',
      'Tokenize reverse failing? Audit log + key permissions',
    ],
    productionIssues: [
      { issue: 'GDPR customer leaked patient name in LLM response', rootCause: 'Output boundary scan was disabled by feature flag for performance test, never re-enabled.' },
      { issue: 'Regex caught email but missed name in same sentence', rootCause: 'NER fell back to "no_model" because spaCy load failed silently at startup.' },
      { issue: '12% regression in NER recall after model upgrade', rootCause: 'Drill ran on golden set but didn\'t catch domain-specific terms (medication names) that needed custom tagger.' },
    ],
    performance: [
      'Regex layer: ~1-2ms per chunk',
      'NER layer: ~30-80ms p95 per chunk (CPU); ~10ms (GPU batched)',
      'Output boundary scan: same overhead, gated by streaming buffer',
      'Throughput per worker: ~50 chunks/s with NER batched',
    ],
    costConsiderations: [
      'NER inference: ~$0.02 per 1000 chunks (CPU) / ~$0.005 (GPU shared)',
      'Reverse-token HSM: ~$50/mo (managed) or self-host',
      'Audit storage: ~200 bytes per redaction row × 30-day retention',
    ],
    observability: [
      'Trace: per-chunk redaction trace with detected categories + actions',
      'Metrics: detection count by category, action distribution, latency p95',
      'Logs: raw PII NEVER logged; only category + char_range + policy_version',
      'Audit: hash-chained per tenant; verified by drill_audit_seal',
    ],
    metrics: [
      { name: 'documind_pii_detected_total{category,action}', example: 'Counter; spike on category may indicate new PII type' },
      { name: 'documind_pii_redaction_latency_seconds{boundary}', example: 'Histogram; alert if p95 > budget per boundary' },
      { name: 'documind_pii_drill_recall', example: 'Gauge; target ≥ 0.99 on golden set; alert below' },
      { name: 'documind_pii_audit_chain_failures_total', example: 'Counter; alert at any > 0' },
    ],
    tradeoffs: [
      { decision: 'Regex-only vs layered detection', tradeoff: 'Layered catches more but adds 30-80ms p95' },
      { decision: 'Mask vs tokenize for patient ID', tradeoff: 'Mask is simpler; tokenize allows reversible ops with audit' },
      { decision: 'Per-tenant policy vs global', tradeoff: 'Per-tenant supports HIPAA+GDPR; ops complexity grows' },
      { decision: 'Output-boundary scan', tradeoff: 'Adds latency to every response; without it LLM can leak' },
    ],
    decisionMatrix: [
      { option: 'Layered detection (this)', whenToUse: 'Multi-tenant + multi-jurisdiction + audit needs' },
      { option: 'Regex-only', whenToUse: 'Internal tool, single jurisdiction, simple PII categories' },
      { option: 'Vendor PII service (e.g., AWS Comprehend)', whenToUse: 'No NER infra; willing to pay per-token API cost' },
    ],
    starStory: {
      situation: 'HIPAA customer onboarded; first PII drill failed: 8 of 50 medical records leaked patient names through ingest.',
      task: 'Get to 100% redaction on the golden set + lock the discipline.',
      action: 'Added NER layer behind regex (was regex-only). Tuned confidence threshold via golden-set sweeps. Added per-jurisdiction policy. Wrote drill_pii_three_boundaries that pumps known PII through ingest + output + audit; asserts zero in Postgres/Qdrant/audit/stream. Drill in CI gates main.',
      result: 'Recall went 92% → 99.7%. HIPAA audit passed first attempt. Pattern adopted by GDPR customer 2 months later (just policy switch).',
    },
    interviewTraps: [
      'Saying "we use regex" without mentioning NER',
      'Single-boundary redaction (ingest only)',
      'Logging raw PII in audit "for debuggability"',
      'Tokenize without access-control + audit on reverse',
      'No drill — claiming coverage based on unit tests',
    ],
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
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/guardrails/deep', label: 'Output guardrail (PII redact on response)', why: 'PII detection runs both pre-ingestion (corpus) AND on output (LLM response) — guardrails layer wraps the output filter' },
          { href: '/admin/rag/deep', label: 'RAG pre-ingestion masking', why: 'mask PII before chunking + embedding so vector DB never holds raw PII; tokenization preserves referential integrity' },
          { href: '/admin/security/deep#cloud-soc2-iam', label: 'SOC2 CC6.2 + GDPR PII', why: 'PII handling = SOC2 confidentiality TSC + GDPR Art. 32; both demand encryption + access control + retention' },
          { href: '/admin/tracing/deep', label: 'PII NEVER in baggage', why: 'baggage is plaintext header — block list in helper API rejects baggage_set("email", ...) at the boundary' },
          { href: '/admin/checklist/deep#lifecycle-checklist', label: '§10 AI row + §7 security', why: 'PII removed pre-ingestion + audit log redaction = checklist hard requirements; tied to hard-stop #1' },
        ]}
      />
    </div>
  );
}
