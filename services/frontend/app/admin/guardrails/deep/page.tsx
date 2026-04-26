'use client';

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'ai-guardrails',
    title: '1. AI guardrails — input + output + behavioral',
    status: 'shipped',
    coreConcept: 'AI guardrails are runtime checks at three boundaries: input (prompt injection, PII, policy), output (toxicity, hallucination, forbidden patterns), and behavioral (drift, repetition, agent-loop overrun). Each fires independently; combined they harden the LLM path.',
    oneLiner: 'Guardrails = three boundaries (input, output, behavior); each fires independently; combined they prevent the LLM from owning the platform\'s behavior.',
    businessContext: 'AI features fail in non-traditional ways: hallucination, prompt injection, toxic output, agent runaway loops. The cost of a leak — content moderation incident, regulatory action — exceeds the cost of layered runtime checks.',
    fiveW: {
      what: 'A pipeline of input guardrails (before LLM call), output guardrails (during streaming), and behavioral guardrails (across multi-step agent loops) that block, redact, or interrupt the response.',
      why: 'LLMs are not steerable enough to self-police. Hallucination + prompt injection + toxic output are real failure modes; runtime checks are the structural answer.',
      where: 'inference-svc applies input guardrails before LLM call. Token-stream wrapper applies output + behavioral guardrails. governance-svc enforces policy.',
      when: 'Always for user-facing AI. Risk-tiered for internal: minimal for dev, full for prod.',
      who: 'AI/ML team owns. Security reviews thresholds. Compliance audits guardrail decisions.',
    },
    interview30s: 'Guardrails fire at three boundaries. Input: prompt-injection detection, PII masking, policy gating before the LLM call. Output: token-stream inspection for toxicity, hallucination signals, forbidden patterns — uses our Cognitive Circuit Breaker pattern. Behavioral: agent-loop budget (max depth, wall-clock, repeated tool calls), drift detection. Each guardrail is independent; one tripping doesn\'t block others. Decisions are audited per request_id. The non-negotiable test is a drill that pumps known prompt-injection / toxic / hallucination probes through and asserts each is caught.',
    coreBuildingBlocks: [
      'Input: prompt-injection detector (heuristic + LLM-judge)',
      'Input: PII masker (regex + NER, see /admin/pii/deep)',
      'Input: policy resolver (per-tenant + per-jurisdiction)',
      'Output: Cognitive Circuit Breaker (CCB) — repetition, drift, rule-breach',
      'Output: forbidden-pattern signal (PII, jailbreak leakage)',
      'Output: citation-deadline signal (must emit citation by token N)',
      'Behavioral: agent-loop CB (depth, wall-clock, repeated calls)',
      'Audit: every guardrail decision logged with request_id',
    ],
    flowchart: `flowchart LR
  IN[User input + tenant] --> INJ[Prompt-injection detector]
  INJ -->|safe| PII[PII masker]
  INJ -->|attack| BLK1[BLOCK + audit]
  PII --> POL[Policy resolver]
  POL -->|allow| LLM[LLM call]
  POL -->|deny| BLK2[BLOCK + audit]
  LLM --> CCB[Cognitive CB on stream]
  CCB -->|clean| OUT[Stream to user]
  CCB -->|breach| INT[INTERRUPT + audit]
  OUT --> CITE[Citation-deadline check]
  CITE -->|miss| INT2[INTERRUPT + audit]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Inf as inference-svc
  participant G as Guardrails
  participant L as LLM
  participant Aud as Audit
  U->>Inf: query + tenant
  Inf->>G: input guardrails
  G-->>Inf: decision (allow / block / mask)
  alt allowed
    Inf->>L: prompt with chunks
    L-->>Inf: token stream
    loop per token chunk
      Inf->>G: output guardrails
      G-->>Inf: continue OR interrupt
    end
    Inf-->>U: streamed answer + citations
  else blocked
    Inf->>Aud: log block
    Inf-->>U: policy denial response
  end
  Inf->>Aud: log decision per request_id`,
    coreLayers: [
      { layer: 'Input layer', responsibility: 'Pre-LLM checks: prompt-injection, PII masking, policy gating. Fast (< 50ms each).' },
      { layer: 'Output layer', responsibility: 'Per-token-chunk inspection during stream. CCB for repetition/drift; forbidden-pattern regex; citation deadline.' },
      { layer: 'Behavioral layer', responsibility: 'Across agent loops: depth budget, wall-clock budget, repeated-call detection.' },
      { layer: 'Decision layer', responsibility: 'Each guardrail returns ALLOW / BLOCK / INTERRUPT / DEGRADE. Combined into final action.' },
      { layer: 'Audit layer', responsibility: 'Every decision logged with request_id, guardrail_name, input snippet, action, latency.' },
      { layer: 'Threshold layer', responsibility: 'Per-tenant + per-feature thresholds. Reviewed monthly via online sampling.' },
    ],
    problem: 'LLMs hallucinate, can be prompt-injected, can emit toxic output. Without runtime guardrails, the model owns the platform\'s behavior — which is dangerous + expensive + unauditable.',
    whyThisApproach: 'Layered checks at boundaries (input, output, behavior) catch different failure modes. Independent firing prevents cascade. Audit chain proves compliance to auditors.',
    whenToUse: ['User-facing AI features', 'Regulated tenants', 'Agent loops with side effects', 'Public APIs to AI'],
    whenNotToUse: ['Internal dev tools (minimal guardrails sufficient)', 'Read-only summarization (output-only)', 'Synthetic data generation'],
    input: 'User query + tenant + retrieval chunks + per-tenant policy',
    process: [
      'Input: run prompt-injection detector + PII masker + policy resolver',
      'If allowed: call LLM with prompt + chunks',
      'Stream wrap: per-chunk run CCB + forbidden-pattern + citation-deadline',
      'Behavioral: track agent depth + wall-clock + repeated-call across loop',
      'Decision: combine guardrail outcomes; log per request_id',
      'Action: stream / block / interrupt / degrade',
    ],
    output: 'Streamed answer (if allowed) OR policy-denial OR interrupt-with-fallback. Audit row per request with all guardrail decisions.',
    alternatives: [
      { name: 'NeMo Guardrails (NVIDIA)', tradeoff: 'Comprehensive; opinionated DSL; learning curve' },
      { name: 'LangChain output parsers', tradeoff: 'Easy; weak on prompt-injection; not multi-boundary' },
      { name: 'AWS Bedrock Guardrails', tradeoff: 'Managed; per-call cost; vendor lock-in' },
      { name: 'Custom regex-only', tradeoff: 'Cheap; misses semantic attacks; high false-negative' },
    ],
    challenges: [
      'Prompt-injection attack surface evolves faster than detector coverage',
      'False positives reject legitimate queries',
      'Performance budget tight (< 100ms total guardrails for streaming SLA)',
      'Multi-language coverage uneven',
      'Threshold tuning needs production data',
    ],
    edgeCases: [
      { case: 'Legitimate query contains PII (medical context)', solution: 'Per-tenant policy override + audit; never silent passthrough' },
      { case: 'CCB false-positive on technical content with repetition', solution: 'Per-feature threshold + n-gram window tuning' },
      { case: 'Agent loop genuinely needs depth > budget', solution: 'Tier-aware budget + explicit consent path' },
      { case: 'Citation-deadline misses on streaming answer with late citation', solution: 'Buffer up to deadline; emit citation OR block before token N' },
    ],
    failureModes: [
      { mode: 'Guardrail service down', detect: '/health/upstreams kind=guardrails', recover: 'Fail-closed: reject AI calls; alert on-call' },
      { mode: 'Detector model degrades', detect: 'False-negative spike on probe corpus', recover: 'Roll back model; re-eval; gate by drill' },
      { mode: 'Threshold miscalibrated', detect: 'False-positive complaints + audit review', recover: 'Tune threshold; re-eval; document in ADR' },
      { mode: 'Audit chain breaks', detect: 'Hash-chain integrity drill goes red', recover: 'Recompute chain; investigate gap' },
    ],
    monitoring: [
      'Per-guardrail decision rate (ALLOW / BLOCK / INTERRUPT)',
      'Per-guardrail latency p50/p99',
      'False-positive rate from sampled review',
      'Hallucination rate (eval-svc benchmark)',
      'Prompt-injection block rate trend',
      'Audit chain integrity per tenant',
    ],
    testing: [
      'Drill: known-attack prompt corpus → assert each blocked',
      'Drill: PII probe → assert masked',
      'Drill: synthetic toxic output → CCB interrupts',
      'Drill: agent depth probe → CB opens at threshold',
      'Eval: false-positive rate per detector',
    ],
    security: [
      'Detector models versioned + signed',
      'Threshold config in Vault',
      'Audit chain hash-chained per tenant',
      'No raw user PII in audit_log details (use redact_pii=True)',
    ],
    scaling: [
      'Input guardrails parallelizable (independent)',
      'CCB stream-wrapper adds < 5ms per chunk',
      'Agent CB state in Redis (per request_id)',
    ],
    maturity: {
      mvp: 'Regex-only output check + agent depth limit',
      production: 'Layered (input + output + behavioral) + audit + drills',
      enterprise: 'Per-tenant thresholds + LLM-judge for prompt-injection + dashboard for sampled review',
    },
    limitations: [
      'No detector is 100% — false-negatives exist',
      'Attack surface evolves; detector lag is real',
      'Performance budget caps depth of checks',
      'Multi-language coverage uneven',
    ],
    projectFit: [
      'libs/py/documind_core/breakers.py — CCB, agent-loop CB, forbidden-pattern, citation-deadline',
      'libs/py/documind_core/ccb.py — Cognitive CB signals',
      'inference-svc — input guardrail orchestration',
      'mcp/tests/drill_guardrail_*.py — per-detector drills',
      '/tools/ccb — CCB tool detail page',
    ],
    interviewLine: 'AI guardrails fire at three boundaries — input, output, behavioral. Each is independent; combined they keep the model from owning the platform\'s behavior. Decisions audited per request_id; the drill pumps known attacks through and asserts each is caught.',
    finalScript: 'AI guardrails fire at three boundaries. Input: prompt-injection detector, PII masker, policy resolver — runs before the LLM call, blocks attacks fast. Output: per-token-chunk inspection during stream — Cognitive Circuit Breaker for repetition and drift, forbidden-pattern regex for jailbreak leakage and PII exfil, citation-deadline signal that interrupts if the model fails to cite by token N. Behavioral: agent-loop budget bounding depth + wall-clock + repeated-call. Each guardrail is independent — one tripping doesn\'t cascade — and each decision is logged per request_id with input snippet, action, and latency. Thresholds are per-tenant and per-feature, reviewed monthly via sampled audit. The drill pumps known prompt-injection corpora, PII probes, toxic-output triggers, and agent-overrun probes; each must be caught. Mocks lie about prompt-injection coverage; only live detector against real attack corpus shows where false-negatives hide.',
  },
];

export default function GuardrailsDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">AI Guardrails — Deep Dive</h1>
        <p className="design-areas-sub">
          Three-boundary defense: input (prompt-injection, PII, policy), output (CCB,
          forbidden-pattern, citation-deadline), behavioral (agent-loop budget). Audit
          chain per request_id. Drill-locked.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
