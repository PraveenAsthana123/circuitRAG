'use client';

/**
 * AI Explainability + Interpretability (deep dive).
 *
 * Two topics:
 *  1. Global + local explainability (SHAP / LIME / counterfactual /
 *     model cards / fairness) — the analyst-side toolkit.
 *  2. Decision audit row + RAG four-part contract + agent tool-call
 *     trace + EU AI Act / NIST RMF / ISO 42001 mapping — the
 *     operator + regulator-side evidence trail.
 *
 * Composes with:
 *  - ~/.claude/policies/ai-explainability.md (the global policy this
 *    page materializes)
 *  - /admin/tracing/deep (request_id pipe carries the audit row)
 *  - /admin/llmops/deep (registry + audit storage)
 *  - /admin/checklist/deep (hard-stop #6: untested AI)
 *  - /admin/security/deep (OWASP A11–A15)
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — Global + local explainability
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'global-local-xai',
    title: '1. Global + local explainability — SHAP / LIME / counterfactual / model card / fairness',
    status: 'shipped',
    coreConcept:
      'Explainability has two layers: GLOBAL ("how does the model behave across all predictions?" — feature importance, PDP/ALE, fairness across groups, surrogate models) and LOCAL ("why this specific prediction?" — SHAP values, LIME, counterfactual, integrated gradients). For RAG: citation tracing maps answer span → source chunk. For agents: tool-call sequence + reflection log. Attention weights are NOT a substitute for attribution. Every deployed model needs a model card with both layers attached.',
    oneLiner: 'Global = how does it behave overall. Local = why this prediction. Both required. Attention ≠ explanation.',
    businessContext:
      'Regulator (EU AI Act Art. 86) demands an explanation of a specific past decision: "why was this loan denied?" Without persisted SHAP / counterfactual / citation trail attached to the audit row, your only honest answer is "the model said so". Counterfactual + minimal-change disclosure satisfies the right-to-explanation in regulated jurisdictions.',
    fiveW: {
      what: 'Global + local techniques mapped to use cases (ML / RAG / agents / regulated decisions) plus the model card discipline that documents both for every deployed model.',
      why: 'A model that is locally explainable but globally biased fails ethics + audit. A model that is globally fair but locally inscrutable fails the right-to-explanation. Both layers required.',
      where: 'Pre-deploy gate (model card review) + audit time (counterfactual API) + weekly fairness drift check.',
      when: 'Every deployment of a model that influences a person\'s outcome.',
      who: 'AI feature owner + data scientist + compliance reviewer.',
    },
    interview30s:
      'Global explainability tells me how the model behaves overall — SHAP global feature importance + PDP for one feature + fairness across groups. Local tells me why this specific prediction — SHAP local + counterfactual ("if income had been $X higher"). For RAG I add citation tracing: every answer span maps to a chunk; uncited spans are hallucination flags. For agents I add tool-call audit. Attention weights are NOT explanation — they show what the model attended to, not why an output happened.',
    hld: `flowchart LR
  Pred[Prediction] --> AuditRow[Decision audit row]
  AuditRow --> ExplainAPI[/api/v1/explain by id/]
  ExplainAPI --> Local[Local: SHAP local + counterfactual]
  ExplainAPI --> Citations[RAG: citation map + retrieval]
  ExplainAPI --> Tools[Agent: plan + tool calls]
  ModelCard[Model card] --> Global[Global: SHAP feature importance]
  ModelCard --> Fair[Fairness across groups]
  ModelCard --> ROI[Intended use + out-of-scope]`,
    flowchart: `flowchart TD
  Q{What does user need?} --> A1[Why this answer?]
  Q --> A2[Why this denial?]
  Q --> A3[How does the model behave?]
  Q --> A4[Is it fair?]
  A1 --> RAG[Citation map + retrieval trail]
  A2 --> CF[Counterfactual minimal change actionable plausible]
  A3 --> SG[Global SHAP + PDP + ALE]
  A4 --> FA[Disparate impact + equal opportunity gap]
  RAG --> Audit[Persist in audit row]
  CF --> Audit
  SG --> Card[Model card]
  FA --> Card`,
    sequence: `sequenceDiagram
  participant User
  participant Reg as Regulator
  participant API as /explain
  participant DB as audit table
  User->>Reg: "why was I denied?"
  Reg->>API: GET prediction_id=X
  API->>DB: lookup audit row
  DB-->>API: features, model_v, prompt_v
  API->>API: compute counterfactual
  API-->>Reg: explanation + counterfactual
  Reg-->>User: factor disclosure + actionable change`,
    coreLayers: [
      { layer: 'Model card', responsibility: 'Intended use + perf + fairness + global SHAP + limitations + owner. Per-model per-version.' },
      { layer: 'Audit row', responsibility: 'Per-prediction record keyed by request_id; survival = forensics works.' },
      { layer: 'Local API', responsibility: 'GET /api/v1/explain?prediction_id=X → SHAP top-features + counterfactual.' },
      { layer: 'Fairness', responsibility: 'Pre-deploy gate (DI ≥ 0.8) + weekly drift check.' },
      { layer: 'RAG citations', responsibility: 'Every answer span → source chunk; uncited = hallucination flag.' },
      { layer: 'Agent trace', responsibility: 'Plan + tool sequence + reflection + scope-grant log.' },
    ],
    lld: `classDiagram
  class ExplainabilityAPI {
    +explain(prediction_id) Explanation
    +counterfactual(prediction_id) Counterfactual
    +fairness_report(model_v) FairnessReport
  }
  class Explanation {
    +method
    +top_features
    +confidence
    +attribution_method
  }
  class Counterfactual {
    +minimal_change
    +actionable
    +plausible_in_distribution`,
    coreBuildingBlocks: [
      'Global: SHAP feature importance, permutation importance, PDP / ALE, surrogate model',
      'Local: SHAP local, LIME, counterfactual (DiCE / Alibi), integrated gradients (deep), anchors',
      'RAG: citation map + retrieval trail + groundedness score per claim',
      'Agent: plan + tool sequence + reflection + scope-grant audit',
      'Fairness: disparate impact ≥ 0.8, equal-opportunity gap < 5%, calibration parity',
      'Model card: intended use + training data + perf + fairness + limitations + owner + version history',
      'Counterfactual constraints: minimal + actionable (no protected attributes) + plausible',
    ],
    architectureRelevance: {
      backend: 'Persist explanation alongside prediction; API for retrieval.',
      rag: 'Citation contract is the explainability surface — every claim must trace to a chunk.',
      ai: 'Required for any AI feature with user-visible outcome.',
      microservices: 'Audit row carries explanation; survives across hops via baggage.request_id propagation.',
    },
    problem:
      'Regulator asks why a specific past decision was made. Without persisted explanation, the answer is "the model decided" — unacceptable under EU AI Act Art. 86. Or model bias goes undetected because no fairness gate ran pre-deploy.',
    whyThisApproach:
      'SHAP + counterfactual + citation are all open-source, well-validated. Persisting explanation at decision time (rather than recomputing at audit time) makes it reproducible — model + data version pinned to the decision.',
    whenToUse: [
      'Regulated decisions (loan / hire / insurance / content moderation)',
      'RAG / chatbot answers (citation contract)',
      'LLM agent actions (tool-call audit)',
      'Any AI with user-visible outcome',
    ],
    whenNotToUse: [
      'Internal AI tooling with no user impact (light tier: model card + version only)',
      'Pure inference batch jobs that touch no person-level decisions',
    ],
    input: 'Trained model + prediction request + audit table + fairness eval set.',
    process: [
      'Pre-deploy: compute global SHAP + fairness metrics → model card',
      'At inference: persist audit row with input_features + model_v + prompt_v + prediction',
      'On request: /api/v1/explain?prediction_id=X → compute local SHAP + counterfactual + return',
      'For RAG: persist citation map + retrieval trail at answer time',
      'For agents: persist plan + tool sequence + reflections',
      'Weekly: re-run fairness on production decisions; alert on drift',
    ],
    output: 'Explanation API response (JSON) + persisted audit row + model card + fairness dashboard.',
    implementationSteps: [
      { step: 'Compute global SHAP', logic: 'Pre-deploy: SHAP on training set; aggregate Shapley values per feature; rank.' },
      { step: 'Persist audit row', logic: 'At inference time: input features + hash + model_v + prompt_v + prediction + confidence.' },
      { step: 'Local explain endpoint', logic: 'GET /api/v1/explain → load audit row → compute SHAP local for that input + counterfactual.' },
      { step: 'Counterfactual constraints', logic: 'Minimal change (smallest flip) + only actionable features (NOT age/gender/race) + plausible (within distribution).' },
      { step: 'RAG citation map', logic: 'After LLM response: map every claim span → chunk_id; uncited = hallucination flag.' },
      { step: 'Agent tool trace', logic: 'Plan + ordered tool_calls (with args + result + scope_required + scope_granted) + reflections.' },
      { step: 'Fairness gate', logic: 'Pre-deploy: DI ≥ 0.8 + EO gap < 5%. Weekly: re-run on prod decisions; alert on drift.' },
      { step: 'Model card', logic: 'Intended use + perf + fairness + global SHAP + limitations + owner + version history. Versioned in registry; updating model without card = release blocked.' },
    ],
    codeExample: {
      language: 'python',
      code: `# Local explanation endpoint
@router.get("/api/v1/explain")
async def explain(prediction_id: str, repo: AuditRepo = Depends(...)) -> dict:
    audit = await repo.get_audit(prediction_id)
    if not audit:
        raise NotFoundError("prediction not found")

    # Reconstruct the input from the audit row (NOT from the original
    # request — that's stale; audit is the canonical record).
    features = audit.input_features
    model = registry.get(audit.model_name, audit.model_version)

    # Local SHAP — Shapley values for THIS prediction
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(features)
    top_5 = sorted(
        zip(model.feature_names, shap_values[0]),
        key=lambda x: abs(x[1]),
        reverse=True,
    )[:5]

    # Counterfactual — what minimal change flips the outcome?
    cf = generate_counterfactual(
        model, features,
        target_class=1 - audit.prediction,
        protected_attributes={"age", "gender", "race"},  # exclude
        max_features_changed=2,
    )

    return {
        "prediction_id": prediction_id,
        "model_version": audit.model_version,
        "method": "SHAP",
        "top_features": [
            {"feature": f, "contribution": float(c)} for f, c in top_5
        ],
        "counterfactual": {
            "summary": cf.human_readable(),
            "feature_changes": cf.deltas,
            "actionable": cf.is_actionable(),
        },
        "fairness_flag": audit.fairness_flag,
    }


# RAG citation contract — persisted at answer time
async def answer_with_citations(query: str) -> RAGAnswer:
    chunks = await retrieve(query, top_k=5)
    response = await llm.complete(build_prompt(query, chunks))

    # Map every answer span → chunk_id (the citation contract)
    citations = []
    for span in extract_claim_spans(response.text):
        chunk_id = match_to_source(span, chunks)
        if chunk_id is None:
            # UNCITED claim — flag as hallucination
            response.flags.append(HallucinationFlag(span=span))
        else:
            citations.append(Citation(span=span, source=chunk_id))

    # Persist citation map in audit row
    await audit_repo.insert_audit(
        request_id=baggage.get("request_id"),
        retrieval={"chunks": [c.id for c in chunks]},
        citations=[c.dict() for c in citations],
        guardrails={"hallucination_flags": [f.dict() for f in response.flags]},
    )
    return response`,
    },
    realUseCase:
      'EU regulator audit on a credit-risk model. With explainability persisted: pulled 1000 audit rows; ran fairness analysis (DI = 0.87, gap = 3.2%); pulled 50 random counterfactuals; ran SHAP on top-5 disputed decisions. Audit completed in 2 days. Without it: would have taken weeks of model rebuilding to compute retroactive explanations on stale data versions.',
    prosCons: {
      pros: [
        'Right-to-explanation satisfied for every past decision',
        'Bias detection automatic (pre-deploy + weekly drift)',
        'Operator MTTR for "why did the AI X" drops to seconds',
        'Compliance evidence is "open the audit row" not "rebuild"',
      ],
      cons: [
        'Persisted explanation = significant storage (every prediction × SHAP values × retention)',
        'Computing local SHAP on demand has latency (~100–500ms typical)',
        'Counterfactual generation needs careful constraint design',
      ],
    },
    limitations: [
      'Attention weights are NOT explanation (use SHAP / IG for transformers)',
      'SHAP assumes feature independence; correlated features distort',
      'Counterfactual minimal change ≠ causal explanation',
      'For deep models: integrated gradients > SHAP for compute cost',
    ],
    comparison: {
      left: 'Reactive (audit time)',
      right: 'Proactive (decision time)',
      rows: [
        { aspect: 'Reproducibility', left: 'Stale data', right: 'Pinned to decision' },
        { aspect: 'Audit prep', left: 'Weeks of rebuilds', right: 'One DB query' },
        { aspect: 'User-visible explain', left: 'Latency: hours', right: 'Latency: ms' },
        { aspect: 'Storage', left: 'Low', right: 'High (justified by regulatory needs)' },
      ],
    },
    challenges: [
      'Counterfactual must exclude protected attributes (legal in regulated jurisdictions)',
      'SHAP with correlated features — use ALE instead',
      'Attention weights as "explanation" anti-pattern remains common',
      'Model card stays in sync with model version (drift)',
      'Fairness drift detection sensitivity tuning',
    ],
    edgeCases: [
      { case: 'Counterfactual cites age/gender/race', solution: 'Block-list in counterfactual generator; raise on attempt' },
      { case: 'Model card stale vs deployed model', solution: 'Registry check at deploy: card.model_version == model.version, else block' },
      { case: 'SHAP slow on deep models', solution: 'Use integrated gradients or fast surrogate; cache common inputs' },
      { case: 'Fairness drift but no model change', solution: 'Likely data drift — investigate input distribution; not necessarily model retraining' },
      { case: 'Uncited RAG span', solution: 'Hallucination flag + (optional) refuse to display + permanent regression test for prompt' },
    ],
    solutions: [
      { problem: 'Audit asks for past decision explanation', solution: 'Persisted audit row + on-demand /explain endpoint' },
      { problem: 'Bias undetected', solution: 'Fairness pre-deploy gate + weekly drift check' },
      { problem: 'Hallucination shipped silently', solution: 'Citation contract: uncited span = hallucination flag at answer time' },
      { problem: 'Agent action without context', solution: 'Plan + tool sequence + scope-grant log persisted' },
      { problem: 'Model card stale', solution: 'Registry version-check enforced at deploy time' },
    ],
    bestPractices: {
      do: [
        'Persist explanation at decision time, not retroactively',
        'SHAP global + local; PDP / ALE for correlated features',
        'Counterfactual: minimal + actionable + plausible',
        'Citation contract on every RAG answer',
        'Agent: plan + tool sequence + scope-grant',
        'Fairness gate pre-deploy + weekly drift',
        'Model card per version, registry-enforced',
      ],
      avoid: [
        'Attention weights as "explanation"',
        'Counterfactual citing protected attributes',
        'Single global SHAP without per-prediction local',
        'Stale model card vs deployed version',
        'Skipping fairness gate "because the model is good"',
      ],
      optimize: [
        'Cache SHAP for common inputs',
        'Pre-compute counterfactual for top decision branches',
        'Surrogate model for fast user-facing explain',
      ],
    },
    antiPatterns: [
      'Use raw attention as "explanation"',
      'Single global feature ranking only (no per-prediction local)',
      'Compute explanation only when audit asks',
      'Counterfactual generated with raw distance, ignores feasibility',
      'Citation-free RAG answer',
    ],
    testing: ['Unit-test explainer: SHAP values sum equals model output offset (consistency)', 'Integration: /explain endpoint returns within 500ms', 'Fairness drill: disparate impact across known groups', 'RAG: every answer has citations OR hallucination flag'],
    testTypes: ['Unit (consistency)', 'Integration (API)', 'Fairness drill', 'RAG citation contract', 'Counterfactual feasibility'],
    testScenarios: [
      { scenario: 'Predict + /explain → SHAP top 5 returned', expected: 'response < 500ms with sorted features' },
      { scenario: 'Counterfactual cites age', expected: 'block-list raises; never returned' },
      { scenario: 'RAG answer with no chunks matched', expected: 'every claim flagged hallucination' },
      { scenario: 'DI < 0.8 in pre-deploy gate', expected: 'release blocked' },
    ],
    testData: [
      { type: 'Eval set with protected groups', example: '500 records labeled with sensitive attrs for fairness check' },
      { type: 'Counterfactual feasibility set', example: 'features × ranges showing realistic bounds' },
    ],
    debuggingChecklist: [
      'Audit row has input_features + model_v + prompt_v?',
      'Model card pinned to current version?',
      'Counterfactual block-list active?',
      'Fairness drift alert wired?',
      'RAG citation map persisted?',
      'Agent tool-call sequence in audit?',
    ],
    productionIssues: [
      { issue: 'Regulator asks for explanation; only logs available', rootCause: 'No persisted audit row; retrofit + start collecting' },
      { issue: 'Counterfactual cited "race"', rootCause: 'Block-list missing or bypass; tighten + fail-closed default' },
      { issue: 'DI dropped to 0.6 in production', rootCause: 'Data drift, not model change; investigate input distribution' },
      { issue: 'RAG hallucination caught by user', rootCause: 'Citation contract not enforced as block, only flag; tighten policy' },
    ],
    security: ['Explain endpoint requires auth (admin or user owns the decision)', 'PII redaction on explanation output if user-facing', 'Audit log of /explain queries (audit the audit)'],
    performance: [
      'Local SHAP: 100–500ms typical for tabular',
      '/explain endpoint p95 < 500ms (cache for common)',
      'Counterfactual: 200ms–2s depending on constraints',
      'Fairness drift: weekly batch, not per-request',
    ],
    costConsiderations: [
      'Audit storage scales with prediction volume × retention (regulated = 7y)',
      'SHAP compute = inference cost × ~1.5–3× depending on impl',
      'Counterfactual: ~100ms compute, often cached',
    ],
    scaling: ['Audit table partitioned by month', 'SHAP cache by input hash', 'Surrogate model for fast user-facing explain'],
    observability: ['Fairness dashboard (DI + EO gap over time)', 'Explain endpoint p95 latency', 'Hallucination flag rate', 'Counterfactual feasibility rate'],
    metrics: [
      { name: 'disparate_impact', example: '0.87 — target ≥ 0.8' },
      { name: 'equal_opportunity_gap_percent', example: '3.2 — target < 5' },
      { name: 'explain_latency_p95_ms', example: '380' },
      { name: 'hallucination_flag_rate', example: '0.018' },
      { name: 'audit_rows_per_day', example: '1.2M' },
    ],
    failureModes: [
      { mode: 'Stale model card', detect: 'Registry version mismatch at deploy', recover: 'Block deploy; force card update' },
      { mode: 'Counterfactual returns protected attribute', detect: 'Block-list test in CI', recover: 'Fail-closed; never return' },
      { mode: 'Fairness drift', detect: 'DI < 0.8 weekly', recover: 'Investigate input distribution; possible retrain' },
      { mode: 'Hallucination uncited', detect: 'Citation map gap', recover: 'Surface flag to user OR refuse to display per policy' },
    ],
    tradeoffs: [
      { decision: 'Persist explanation at decision time', tradeoff: 'Storage cost; reproducibility + low audit-time latency' },
      { decision: 'On-demand /explain', tradeoff: 'Higher per-call latency; no upfront storage' },
      { decision: 'Block hallucination vs flag', tradeoff: 'Strict UX; lossy for low-confidence answers' },
    ],
    decisionMatrix: [
      { option: 'Light (model card only)', whenToUse: 'Internal AI tooling; no user impact' },
      { option: 'Mid (audit row + on-demand explain)', whenToUse: 'Most production AI features' },
      { option: 'Full (audit + persisted SHAP + counterfactual + fairness gate)', whenToUse: 'Regulated decisions (loan/hire/insurance/medical)' },
    ],
    starStory: {
      situation: 'EU AI Act audit on a 1.2M-prediction-per-day credit-risk model. No persisted explainability.',
      task: 'Make audit pass + ship sustainable explainability.',
      action: 'Built audit row schema (input + model_v + prompt_v + prediction); /explain endpoint computing SHAP + counterfactual on demand; pre-deploy fairness gate (DI ≥ 0.8); model card per version. Block-listed protected attrs in counterfactual.',
      result: 'Audit passed. /explain p95 = 380ms. Bias drift alerts caught data shift two months later (DI = 0.79, alert fired); investigation found input pipeline regression. Saved a regulator-facing incident.',
    },
    interviewTraps: [
      'Quoting attention weights as explanation',
      'No mention of counterfactual constraints (protected attrs)',
      'No fairness gate pre-deploy',
      'No persisted audit row → cannot reproduce past decisions',
    ],
    finalScript:
      'Global = behavior overall (SHAP + PDP + fairness). Local = why this prediction (SHAP + counterfactual). RAG = citation contract. Agent = plan + tool trace. Counterfactual is minimal + actionable + plausible — never cites protected attributes. Persisted at decision time; on-demand /explain reads it.',
    alternatives: [
      { name: 'LIME instead of SHAP', tradeoff: 'Faster locally; less consistent global' },
      { name: 'Anchors', tradeoff: 'High precision rule per prediction; coarser' },
      { name: 'Surrogate decision tree', tradeoff: 'Communication-friendly; lossy approximation' },
    ],
    monitoring: ['Fairness DI + EO gap dashboard', 'Hallucination flag rate', '/explain endpoint latency', 'Counterfactual block-list trigger rate'],
    maturity: {
      mvp: 'Audit row + model card',
      production: 'Add /explain + fairness gate + RAG citations',
      enterprise: 'Add weekly drift + counterfactual + agent trace + EU AI Act mapping',
    },
    projectFit: ['Regulated decisions', 'RAG / chatbot', 'LLM agents', 'Multi-tenant AI SaaS'],
    interviewLine: 'Global + local. SHAP + counterfactual. Citation contract for RAG. Block protected attrs.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — Decision audit, RAG four-part contract, EU AI Act
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'audit-rag-contract-regulation',
    title: '2. Decision audit row + RAG four-part contract + EU AI Act / NIST RMF / ISO 42001',
    status: 'shipped',
    coreConcept:
      'The decision audit row IS the regulator-facing evidence. Required minimum: request_id (forensics join key), input + hash, model_version + prompt_version, prediction + confidence, explanation top_features, counterfactual, rules_applied, guardrails_triggered, human_override, fairness_flag, latency_ms, cost_tokens. For RAG, four parts must persist: retrieval trail + prompt rendering + citation map + guardrail trace. For agents: plan + tool sequence + reflections + scope-grant. EU AI Act Art. 12 mandates ≥ 6 month retention; SOC2 / regulated → 7 years.',
    oneLiner: 'Audit row is the evidence. RAG four-part contract. Agent tool trace. EU AI Act / NIST / ISO mapped explicitly.',
    businessContext:
      'A regulator (EU AI Act Art. 86) or a user disputes a specific past decision. With audit row + four-part contract: paste request_id, get full reasoning trail in seconds. Without: scramble for weeks rebuilding context, often impossible because data + model versions have drifted.',
    fiveW: {
      what: 'Schema + retention + endpoint contract for: decision audit row, RAG four-part trail, agent tool sequence. Mapped to EU AI Act / NIST AI RMF / ISO 42001 articles.',
      why: 'Right-to-explanation + right-to-audit + right-to-rectification all require reproducible evidence. The audit row is that evidence.',
      where: 'Postgres audit table partitioned by month + cold-storage after 30d.',
      when: 'Every AI decision; every regulated action.',
      who: 'AI feature owner + compliance + audit + regulator.',
    },
    interview30s:
      'Audit row keyed by request_id (propagated via baggage). Must contain: input + hash, model_v + prompt_v, prediction + confidence, top features, counterfactual, rules + guardrails fired, fairness flag, latency, cost. For RAG: four-part contract — retrieval trail (chunks + scores) + prompt rendering (final prompt sent) + citation map (span → chunk) + guardrail trace (filters fired). For agents: plan + tool sequence + reflections + scope-grant. Retention 7 years for regulated; ≥ 6 months under EU AI Act Art. 12.',
    hld: `flowchart LR
  Req[request_id from baggage] --> Audit[Audit row]
  Audit --> Input[input + hash]
  Audit --> Versions[model_v + prompt_v]
  Audit --> Pred[prediction + confidence]
  Audit --> Expl[explanation: top_features + counterfactual]
  Audit --> Pol[rules + guardrails + fairness]
  Audit --> Cost[latency + cost]
  Req --> RAG[RAG four-part]
  RAG --> Retrieval[chunks + scores]
  RAG --> Prompt[rendered prompt]
  RAG --> Cites[citation map]
  RAG --> Guards[guardrail trace]
  Req --> Agent[Agent trace]
  Agent --> Plan[plan]
  Agent --> Tools[tool sequence + scope]`,
    flowchart: `flowchart TD
  In[Inbound request] --> Mid[BaggageContextMiddleware sets request_id]
  Mid --> Inf[Inference]
  Inf --> Decide{Decision type}
  Decide -- ML pred --> AuditML[INSERT audit_ml row]
  Decide -- RAG --> AuditRag[INSERT audit row + retrieval + citations]
  Decide -- Agent --> AuditAgent[INSERT audit row + plan + tools]
  AuditML --> Resp[Response to user]
  AuditRag --> Resp
  AuditAgent --> Resp
  Resp --> Forensics[Future query by request_id]`,
    sequence: `sequenceDiagram
  participant User
  participant Edge as api-gateway
  participant Inf as inference-svc
  participant DB as audit table
  participant Reg as Regulator
  User->>Edge: POST predict
  Edge->>Inf: forward + baggage tenant_id user_id request_id
  Inf->>Inf: predict + explain + fairness check
  Inf->>DB: INSERT audit row (atomic with response)
  Inf-->>Edge: response + request_id echoed
  Edge-->>User: response
  Note over Reg: weeks later
  Reg->>Inf: GET /api/v1/explain by request_id
  Inf->>DB: SELECT audit row
  DB-->>Inf: full reasoning trail
  Inf-->>Reg: explanation + counterfactual + fairness`,
    coreLayers: [
      { layer: 'Audit row', responsibility: 'Per-decision record; the evidence trail.' },
      { layer: 'RAG four-part', responsibility: 'Retrieval + prompt + citations + guardrails.' },
      { layer: 'Agent trace', responsibility: 'Plan + tool sequence + reflections + scope-grant.' },
      { layer: 'Retention', responsibility: 'Hot 30d / cold 1y / regulated 7y. Partition by month.' },
      { layer: 'Forensics', responsibility: '/api/v1/explain?prediction_id=X reads audit row.' },
      { layer: 'Compliance export', responsibility: 'Daily dump to compliance bucket; tenant-scoped queries fast.' },
    ],
    lld: `classDiagram
  class AuditRow {
    +request_id: text PRIMARY
    +timestamp: timestamptz
    +tenant_id: text
    +user_id: text
    +model_name: text
    +model_version: text
    +prompt_version: text
    +input_features: jsonb
    +input_hash: text
    +prediction: text
    +confidence: float
    +explanation: jsonb
    +rules_applied: text[]
    +guardrails_triggered: text[]
    +human_override: bool
    +fairness_flag: text
    +latency_ms: int
    +cost_tokens: int
  }
  class RAGAuditExtension {
    +retrieval: jsonb
    +prompt_template: text
    +rendered_prompt: text
    +citations: jsonb
    +guardrail_trace: jsonb
  }
  class AgentAuditExtension {
    +plan: text
    +tool_calls: jsonb
    +reflections: jsonb
    +scope_grants: jsonb`,
    coreBuildingBlocks: [
      'request_id from baggage as PRIMARY KEY (propagated by BaggageContextMiddleware)',
      'Atomic INSERT in same transaction as response (outbox pattern if async)',
      'Indexes: (tenant_id, created_at), (model_version, created_at), (request_id) unique',
      'Partition by month for performance + retention archival',
      'Retention policy: regulated 7y, default 1y',
      'RAG four-part: retrieval + prompt + citations + guardrails',
      'Agent extension: plan + tools + reflections + scope-grants',
      'Compliance export: daily tenant-scoped dump',
    ],
    architectureRelevance: {
      backend: 'Postgres audit table is the canonical evidence store.',
      rag: 'Four-part contract is mandatory; every part persisted at answer time.',
      ai: 'Universal — applies to ML / RAG / agents.',
      microservices: 'request_id is the join key; baggage propagates across hops.',
    },
    problem:
      'Regulator demands evidence of a specific past decision. Without persisted audit row, only logs exist (rotated, partial, no model_v / prompt_v context). Compliance fails. User dispute (right-to-rectification) impossible.',
    whyThisApproach:
      'Atomic + indexed + partitioned + retention-policied. One INSERT per decision; one query per audit. Compliance export is a SQL view. EU AI Act Art. 12 minimum 6m retention satisfied; SOC2 / regulated 7y also satisfied.',
    whenToUse: [
      'Every AI decision that affects a person',
      'Regulated systems (EU AI Act, GDPR Art. 22, FDA AI/ML guidance)',
      'SOC2 / ISO 27001 / ISO 42001 audit-bound systems',
    ],
    whenNotToUse: [
      'Internal AI tooling with zero user impact (light tier suffices)',
      'Pure batch ML jobs that touch no person-level decisions',
    ],
    input: 'Inference output + baggage.request_id + tenant_id + user_id + model_v + prompt_v.',
    process: [
      'Inference completes; results computed',
      'Compute explanation: SHAP top features + counterfactual',
      'Run fairness check + guardrails',
      'Build audit row with all required fields',
      'INSERT in same transaction as response (or via outbox)',
      'Echo request_id in response header for client traceability',
      '(Async) backup to compliance bucket daily',
    ],
    output: 'Audit row in Postgres; available to /api/v1/explain endpoint forever (per retention).',
    implementationSteps: [
      { step: 'Audit table schema', logic: 'CREATE TABLE audit (request_id text PRIMARY KEY, ...). Partition by month. Index (tenant_id, created_at) + (model_version, created_at).' },
      { step: 'Atomic insert', logic: 'INSERT in same transaction as the response. If async, use outbox pattern (commit row + outbox entry, worker picks up).' },
      { step: 'request_id from baggage', logic: 'baggage.get("request_id") in handler — propagated by BaggageContextMiddleware.' },
      { step: 'RAG four-part', logic: 'Persist retrieval (chunk_ids + scores) + rendered prompt + citation map + guardrail flags.' },
      { step: 'Agent extension', logic: 'plan (string), tool_calls (jsonb array of {tool, args, result, scope_required, scope_granted}), reflections, scope_grants.' },
      { step: 'Retention policy', logic: 'Hot 30d in main table; cold-archive 1y; regulated 7y in compliance bucket.' },
      { step: 'Compliance export', logic: 'Daily SELECT WHERE tenant_id = X AND created_at >= ... → S3 bucket per tenant.' },
      { step: 'Forensics endpoint', logic: 'GET /api/v1/explain?prediction_id=X → SELECT audit + compute on-demand SHAP + return.' },
    ],
    codeExample: {
      language: 'sql',
      code: `-- Audit table — schema for per-decision evidence
CREATE TABLE audit (
  request_id          text PRIMARY KEY,
  timestamp           timestamptz NOT NULL DEFAULT now(),
  tenant_id           text NOT NULL,
  user_id             text,
  model_name          text NOT NULL,
  model_version       text NOT NULL,
  prompt_version      text,
  input_features      jsonb,
  input_hash          text,
  prediction          text,
  confidence          double precision,
  explanation         jsonb,
  rules_applied       text[],
  guardrails_triggered text[],
  human_override      boolean DEFAULT false,
  fairness_flag       text,
  latency_ms          int,
  cost_tokens         int,
  -- RAG-specific (nullable for ML predictions)
  retrieval           jsonb,
  rendered_prompt     text,
  citations           jsonb,
  guardrail_trace     jsonb,
  -- Agent-specific (nullable for ML/RAG)
  plan                text,
  tool_calls          jsonb,
  reflections         jsonb,
  scope_grants        jsonb
) PARTITION BY RANGE (timestamp);

-- Monthly partitions (rotate via cron / pg_partman)
CREATE TABLE audit_y2026m01 PARTITION OF audit
  FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- Indexes for compliance queries + forensics
CREATE INDEX audit_tenant_created ON audit (tenant_id, timestamp DESC);
CREATE INDEX audit_model_version ON audit (model_version, timestamp DESC);
CREATE INDEX audit_fairness_flag ON audit (fairness_flag) WHERE fairness_flag != 'pass';

-- RLS for tenant isolation (SOC2 CC6.1)
ALTER TABLE audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_tenant_isolation ON audit
  USING (tenant_id = current_setting('app.tenant_id', true));`,
    },
    realUseCase:
      'EU AI Act audit on a credit-risk + RAG-chatbot stack. Regulator asked for: 100 random decisions in last 6 months + counterfactual for each + fairness across protected groups + 10 RAG answer trails. With persisted audit + four-part contract: SQL query + /explain calls returned everything in 4 hours. Without: estimated 6-week project of model rebuilds + log archaeology.',
    prosCons: {
      pros: [
        'Right-to-explanation satisfied per Art. 86',
        'Right-to-audit satisfied per Art. 12 (≥ 6m retention)',
        'Right-to-rectification (user disputes) supported',
        'Forensics by request_id is one query',
        'Compliance export is a SQL view',
      ],
      cons: [
        'Storage scales fast: 1M predictions/day × ~5KB/row × 7y = ~12TB',
        'Cold-archive after 30d is cost saving but adds latency for old queries',
        'Schema evolution requires careful migrations',
      ],
    },
    limitations: [
      'Schema changes require expand-contract DB migrations',
      'Cold-archive retrieval has higher latency',
      'PII in input_features needs masking (compose with /admin/pii/deep)',
    ],
    comparison: {
      left: 'Logs only',
      right: 'Audit row + four-part + agent trace',
      rows: [
        { aspect: 'Reproducibility', left: 'No', right: 'Yes (model_v + prompt_v pinned)' },
        { aspect: 'Audit prep', left: 'Weeks of rebuild', right: 'Hours of SQL' },
        { aspect: 'Compliance export', left: 'Custom project', right: 'SQL view' },
        { aspect: 'Forensics latency', left: 'Days', right: 'Seconds' },
      ],
    },
    challenges: [
      'Storage cost trajectory under high-throughput AI',
      'Schema evolution backward compat',
      'PII in input_features masking (without losing reproducibility)',
      'Tenant isolation via RLS at scale',
      'Cold-archive retrieval UX',
    ],
    edgeCases: [
      { case: 'Async inference (worker queue)', solution: 'Outbox pattern — INSERT audit row + outbox entry; worker reconciles' },
      { case: 'Tenant deletion (GDPR Art. 17)', solution: 'Cascade delete by tenant_id; audit log of deletion event' },
      { case: 'Schema evolves mid-retention', solution: 'JSONB columns + versioned schema field; migrations are additive' },
      { case: 'Massive input_features payload', solution: 'Hash + cold-store actual; main row has hash only for queries' },
    ],
    solutions: [
      { problem: 'Regulator audit', solution: 'SQL on audit table + /explain endpoint + tenant export' },
      { problem: 'User dispute', solution: 'Look up by request_id (echoed in response header)' },
      { problem: 'Storage runaway', solution: 'Partition + cold-archive + retention policy automation' },
      { problem: 'Schema drift', solution: 'JSONB extensions + version field + additive migrations' },
      { problem: 'Cross-tenant leak', solution: 'RLS by tenant_id + audit of admin queries' },
    ],
    bestPractices: {
      do: [
        'Atomic INSERT with response',
        'Partition by month',
        'RLS for tenant isolation',
        'Index (tenant_id, created_at) + (request_id)',
        'Echo request_id in response header',
        'Compliance export as SQL view',
        'JSONB for evolvable schema',
      ],
      avoid: [
        'Fire-and-forget audit insert (lost on crash)',
        'Single tablespace for 7y retention (use partitions)',
        'Unindexed audit table (compliance export slow)',
        'PII without masking (compose with pii layer)',
      ],
      optimize: [
        'pg_partman for auto-rotation',
        'Cold storage to S3 after 30d',
        'Materialized fairness view (refresh hourly)',
      ],
    },
    antiPatterns: [
      'Logs-only "audit" (rotated, partial, no version pinning)',
      'No request_id propagation (cannot join across services)',
      'Storing model_v as int (loses semver context)',
      'No retention policy (storage runaway)',
    ],
    testing: ['Unit: audit row insert is part of response transaction', 'Integration: /explain by request_id returns full row', 'Tenant isolation: cross-tenant query returns 0 rows', 'Retention: rows older than 30d in cold tier', 'Compliance export: SQL view returns tenant-only data'],
    testTypes: ['Unit', 'Integration', 'Tenant isolation drill', 'Retention drill', 'Compliance export drill'],
    testScenarios: [
      { scenario: 'Predict → audit row inserted', expected: 'row exists by request_id immediately' },
      { scenario: 'Cross-tenant query (RLS)', expected: 'zero rows returned (isolation enforced)' },
      { scenario: 'Schema evolution (add field)', expected: 'old rows still queryable; new field nullable' },
      { scenario: '/explain on archived row', expected: 'cold-tier retrieval succeeds within 5s' },
    ],
    testData: [
      { type: 'Real audit row', example: 'request_id=req-abc; tenant=acme; model=credit-risk-v3.2; prediction=approve; conf=0.82' },
      { type: 'RAG four-part', example: 'retrieval=3 chunks; rendered_prompt=<full>; citations=2 spans; guardrails=[]' },
      { type: 'Agent trace', example: 'plan="lookup → balance → refund"; tool_calls=3 with scope_grants' },
    ],
    debuggingChecklist: [
      'request_id set at edge (CorrelationIdMiddleware)?',
      'Baggage propagated to inference?',
      'INSERT in same transaction as response?',
      'Indexes present on (tenant_id, created_at)?',
      'RLS policy active?',
      'Retention cron running?',
    ],
    productionIssues: [
      { issue: 'Audit insert fails after response', rootCause: 'Fire-and-forget; switch to outbox pattern' },
      { issue: 'Compliance export takes 30 min', rootCause: 'Missing index; add (tenant_id, created_at)' },
      { issue: 'Schema migration breaks old rows', rootCause: 'Non-additive migration; revert + use JSONB extension instead' },
      { issue: 'PII leaked in input_features export', rootCause: 'No masking layer; add pre-export redaction' },
    ],
    security: ['RLS by tenant_id', 'Audit log of admin queries on the audit table', 'PII redaction on compliance export', 'Encryption at rest (Postgres TDE or column-level)'],
    performance: [
      'Atomic insert: < 5ms p95',
      '/explain by request_id: < 100ms (cached) or < 500ms (with on-demand SHAP)',
      'Compliance export 30 days × 1 tenant: < 10s with index',
      'Cold-archive retrieval: < 5s',
    ],
    costConsiderations: [
      'Postgres hot tier: ~$0.15/GB/month × ~12TB at 7y = significant',
      'Cold S3: ~$0.023/GB/month — 80% reduction after 30d archive',
      'Compliance export bucket: separate budget',
      'Index storage: ~10–20% of table size',
    ],
    scaling: ['Partition by month', 'Read replicas for forensics endpoint', 'Cold tier after 30d', 'Per-tenant export buckets'],
    observability: ['Audit insert success rate (target ~1.0)', 'Audit table size dashboard', '/explain latency p95', 'Compliance export latency', 'Retention policy execution log'],
    metrics: [
      { name: 'audit_insert_success_rate', example: '0.9999' },
      { name: 'audit_table_size_tb', example: '4.2 (28% to cold)' },
      { name: 'explain_latency_p95_ms', example: '380' },
      { name: 'compliance_export_seconds', example: '6.4' },
      { name: 'retention_archive_lag_days', example: '0' },
    ],
    failureModes: [
      { mode: 'Audit insert fails', detect: 'Insert success rate dashboard', recover: 'Outbox pattern + reconcile worker' },
      { mode: 'RLS bypass', detect: 'Audit-the-audit log of admin queries', recover: 'Investigate + tighten policy' },
      { mode: 'Schema migration breaks compliance export', detect: 'Export drill in CI', recover: 'Revert + use JSONB extension' },
      { mode: 'Storage runaway', detect: 'Daily growth alert', recover: 'Tighten retention or archive sooner' },
    ],
    tradeoffs: [
      { decision: 'Atomic INSERT', tradeoff: 'Slower response; reliable audit' },
      { decision: 'JSONB columns', tradeoff: 'Schema-evolvable; slower queries on JSONB fields' },
      { decision: 'RLS', tradeoff: 'Tenant isolation; some query rewriting' },
      { decision: '7y retention', tradeoff: 'Storage cost; regulatory requirement' },
    ],
    decisionMatrix: [
      { option: 'Light (logs + minimal audit)', whenToUse: 'Internal AI; non-regulated' },
      { option: 'Mid (audit row + /explain)', whenToUse: 'Production AI; SOC2-bound' },
      { option: 'Full (audit + RAG four-part + agent + 7y retention)', whenToUse: 'Regulated (EU AI Act / FDA / GDPR Art. 22)' },
    ],
    starStory: {
      situation: 'EU AI Act audit on credit-risk + RAG-chatbot. Regulator demanded 100 random past decisions + counterfactuals + RAG trails + fairness across groups.',
      task: 'Make audit pass.',
      action: 'Audit table + four-part RAG contract + /explain endpoint shipped 9 months prior. Pulled 100 audit rows in 8 minutes; counterfactuals via /explain in 12 minutes; RAG trails via SQL on retrieval/citations columns in 5 minutes; fairness via materialized view in 20 seconds.',
      result: 'Audit completed in 4 hours of regulator interview vs estimated 6-week rebuild. Zero findings on technical controls. Same audit table re-used for SOC2 + ISO 42001 next year.',
    },
    interviewTraps: [
      'Logs as substitute for audit row',
      'No model_v / prompt_v in audit (cannot reproduce)',
      'No tenant isolation (RLS missing)',
      'No retention policy',
    ],
    finalScript:
      'Audit row keyed by request_id; atomic with response; partitioned monthly; RLS by tenant; retention 7y for regulated. RAG four-part: retrieval + prompt + citations + guardrails. Agent: plan + tool sequence + scope-grant. EU AI Act / NIST / ISO 42001 mapped explicitly. Compliance export is a SQL view.',
    alternatives: [
      { name: 'Logs + retroactive computation', tradeoff: 'Cheaper storage; cannot reproduce past decisions reliably' },
      { name: 'Document store (Mongo)', tradeoff: 'Schema-evolvable; weaker JOIN + RLS' },
      { name: 'Event-sourced (Kafka stream)', tradeoff: 'Replayable; complex query path; needs projections' },
    ],
    monitoring: ['Audit insert success', '/explain p95 latency', 'Compliance export latency', 'Audit table growth + cold-archive lag'],
    maturity: {
      mvp: 'Single audit table + minimal columns',
      production: 'Add four-part RAG + agent + RLS + partitioning',
      enterprise: 'Add cold archival + compliance export + EU AI Act mapping + drift dashboards',
    },
    projectFit: ['Regulated AI', 'Multi-tenant SaaS', 'EU / SOC2 / ISO audit-bound', 'Production LLM agents'],
    interviewLine: 'request_id is the join key. RAG four-part. Agent trace. RLS. Retention 7y. Audit prep in hours, not weeks.',
  },
];

export default function ExplainabilityDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">AI Explainability + Interpretability (deep dive)</h1>
        <p className="design-areas-sub">
          Global + local explainability (SHAP / LIME / counterfactual / model
          card / fairness) and the decision audit row + RAG four-part contract +
          agent tool-call trace mapped explicitly to EU AI Act Art. 12 / 86,
          NIST AI RMF, and ISO/IEC 42001. Materializes the global policy at
          ~/.claude/policies/ai-explainability.md.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/llmops/deep', label: 'LLMOps — model + prompt + eval registry', why: 'model card + audit row schemas live here; explanation endpoint reads from registry-backed audit storage' },
          { href: '/admin/tracing/deep#trace-draft-audit-linkage', label: 'Trace → draft → audit by request_id', why: 'request_id from baggage is the primary key on the audit row; forensics joins trace + draft + audit' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Hard-stop #6 (untested AI)', why: 'fairness gate (DI ≥ 0.8) + model card validation are pre-deploy hard-stop checks' },
          { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'OWASP A11–A15 + EU AI Act mapping', why: 'right-to-explanation (Art. 86) + logging + retention (Art. 12) live here; SOC2 CC6.1 RLS for tenant isolation' },
          { href: '/admin/pii/deep', label: 'PII in input_features', why: 'audit row\'s input_features needs masking before compliance export; never raw PII in the row sent to the regulator' },
        ]}
      />
    </div>
  );
}
