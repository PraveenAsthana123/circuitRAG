'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'hallucination-citation-eval',
    title: '1. Hallucination detection via citation resolution',
    status: 'shipped',
    coreConcept: 'Every LLM claim must cite a chunk_id from the retrieval set; the verifier resolves each citation to a real chunk before the answer is surfaced. Uncited spans are flagged as hallucination. The citation discipline IS the hallucination guardrail — without it, the LLM is free to invent facts.',
    problem: 'LLMs produce plausible text whether or not the underlying facts exist. "The system uses Postgres 16 with pgvector" sounds correct even when the codebase uses Postgres 14. Without per-claim citation resolution, no operator can distinguish reproduced fact from invention.',
    whyThisApproach: 'Citation discipline shifts hallucination detection from "judgement call" to "lookup". Each citation has a chunk_id; chunk_ids resolve or they don\'t. This is exactly how academic papers handle the same problem; the verifier is mechanical.',
    whenToUse: ['Every RAG answer (mandatory per §39 + §48)', 'Council advisory output', 'AIOps incident narrative', 'Any LLM output influencing a regulated decision'],
    whenNotToUse: ['Pure-creative output (no factual claims)', 'Single-shot completions where retrieval is empty by design', 'Prompts with no factual grounding required'],
    input: 'LLM response text + the retrieval set (list of {chunk_id, content}) + a citation parser',
    process: [
      'Parse response for citation tokens (e.g. [chunk_42] or §N inline)',
      'Resolve each citation: does chunk_id exist in retrieval set?',
      'For each cited chunk: does the response\'s claim around the citation actually match the chunk content?',
      'Compute citation pass rate; below threshold → reject answer',
      'Surface failed citations to operator with the offending span',
    ],
    output: 'Pass/fail flag + per-citation resolution table + hallucination span list.',
    flowchart: `flowchart LR
  resp[LLM response] --> parse[Parse citation tokens]
  parse --> r{each cite resolves?}
  r -->|no| flag[Flag hallucination span]
  r -->|yes| sim{claim matches chunk?}
  sim -->|low similarity| flag
  sim -->|high similarity| ok[Accept]
  flag --> reject[Reject answer + surface span]
  ok --> deliver[Deliver to user]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant RAG as RAG svc
  participant LLM as LLM
  participant V as Verifier
  U->>RAG: query
  RAG->>RAG: retrieve(query)
  RAG->>LLM: prompt(query, chunks)
  LLM-->>RAG: response with citation markers
  RAG->>V: verify(response, chunks)
  V->>V: parse citations
  loop each citation
    V->>V: resolve chunk_id
    V->>V: similarity(claim, chunk.content)
  end
  alt all pass
    V-->>RAG: accept
    RAG-->>U: response + citations
  else any fail
    V-->>RAG: reject + spans
    RAG-->>U: insufficient evidence
  end`,
    alternatives: [
      { name: 'Trust the LLM', tradeoff: 'Hallucinations leak to users; regulator-killer' },
      { name: 'Human review every answer', tradeoff: 'Doesn\'t scale; defeats purpose of RAG' },
      { name: 'External fact-check service', tradeoff: 'Expensive; adds latency; cannot cite project-internal chunks' },
    ],
    challenges: [
      'Citation parser robustness across LLM output styles',
      'Similarity threshold tuning (too strict = reject valid answers; too loose = miss hallucinations)',
      'Multi-claim sentences ("X and Y") where only X is cited',
      'Quoted claims that paraphrase the chunk',
    ],
    edgeCases: [
      { case: 'LLM cites correct chunk but mis-paraphrases', solution: 'Embedding similarity (cited chunk vs claim span) below threshold → reject' },
      { case: 'Claim has no citation (orphaned fact)', solution: 'Treat as hallucination span; reject or rewrite' },
      { case: 'Same chunk cited 5 times', solution: 'Counted once for resolution; OK to repeat' },
      { case: 'Citation references chunk outside retrieval set', solution: 'Hard reject; chunk_id must come from this query\'s retrieval' },
    ],
    failureModes: [
      { mode: 'Citation parser misses citations', detect: 'Pass rate suspiciously high; no rejects despite obvious hallucinations', recover: 'Test parser on golden set; tighten regex' },
      { mode: 'Similarity threshold too tight', detect: 'High false-positive rate; valid answers rejected', recover: 'Walk threshold per ratchet pattern' },
      { mode: 'Retrieval returned wrong chunks', detect: 'Low citation pass rate cascade across queries', recover: 'Inspect retrieval; embedding model drift; re-embed' },
    ],
    monitoring: [
      'documind_eval_citation_pass_rate (per query)',
      'documind_eval_hallucination_spans_total (count of rejected spans)',
      'documind_eval_similarity_score_p50 (distribution; spot drift)',
      '/admin/output-eval citation panel',
    ],
    testing: [
      'drill_eval_citation_resolver (synthetic chunks + LLM response → verifier output)',
      'drill_eval_similarity_threshold (golden set + tuning regression)',
      'drill_rag_citation_e2e (full RAG path with citation marker preservation)',
    ],
    security: [
      'Verifier is read-only over retrieval set; no PII leakage',
      'Failed citation spans logged but content redacted (may contain user query)',
      'Citation chain itself is the audit trail (§48 explainability requirement)',
    ],
    scaling: [
      '10x: in-process verifier; O(citations × chunks) per query',
      '100x: pre-computed embedding index for similarity check; sub-ms per claim',
      'Cost driver: similarity computation; switch to cheaper embedding for verifier-only path',
    ],
    maturity: {
      mvp: 'No verifier — trust the LLM; ship hallucinations',
      production: 'Citation resolver + similarity threshold + per-query pass rate + ratchet floor',
      enterprise: 'Per-domain similarity thresholds + claim-level entailment model + reviewer feedback loop',
    },
    limitations: [
      'Similarity threshold is global (per-domain tuning is enterprise-tier)',
      'Multi-hop claims (chunk → derived fact) hard to verify',
      'No automated rewrite of failed answers (operator must re-query)',
    ],
    projectFit: [
      'libs/py/documind_core/ai_governance.py — guardrail surface',
      'services/sidecar-advisor/* — council uses citation pattern',
      'docs/architecture/adr/ — ADRs on RAG retrieval',
      '/admin/explainability/deep — citation discipline framing',
    ],
    interviewLine: 'Hallucination detection is not magic — it is citation resolution. Every claim cites a chunk_id; the verifier resolves each one against the retrieval set; failed resolutions are hallucination spans. Same model academic papers use; mechanical, auditable, regulator-ready.',
    implementationSteps: [
      { step: 'Citation marker convention', logic: 'LLM is prompted to cite as [chunk_42] inline; parser regex extracts.' },
      { step: 'Resolver against retrieval set', logic: 'Each chunk_id must appear in the query\'s retrieval; no external cites.' },
      { step: 'Similarity check per cite', logic: 'Embedding cosine of claim span vs chunk content; threshold per ratchet.' },
      { step: 'Pass rate aggregator', logic: 'Per query: cited_passing / cited_total; below floor → reject answer.' },
      { step: 'Surface flagged spans', logic: 'UI highlights failed-citation spans in red; operator sees what the LLM made up.' },
      { step: 'Audit row write', logic: 'Citation table persists per answer (§48); reproducible incident review.' },
      { step: 'Drill the verifier', logic: 'drill_eval_citation_resolver locks the parser + resolver + threshold contract.' },
    ],
    codeExample: {
      language: 'python',
      code: `# libs/py/documind_core/eval/citation_verifier.py
import re
from dataclasses import dataclass

CITATION_RE = re.compile(r"\\[chunk_(\\w+)\\]")

@dataclass
class VerifyResult:
    pass_rate: float
    hallucination_spans: list[str]
    failed_citations: list[str]

def check_citations(response: str, retrieval_set: dict[str, str],
                    similarity_fn, threshold: float = 0.55) -> VerifyResult:
    cited_ids = set(m.group(1) for m in CITATION_RE.finditer(response))
    failed_cites = [c for c in cited_ids if c not in retrieval_set]
    spans = []
    passing = 0
    for c in cited_ids - set(failed_cites):
        idx = response.find(f"[chunk_{c}]")
        span = response[max(0, idx-200):idx]
        sim = similarity_fn(span, retrieval_set[c])
        if sim >= threshold:
            passing += 1
        else:
            spans.append(span)
    total = len(cited_ids) or 1
    return VerifyResult(
        pass_rate=passing / total,
        hallucination_spans=spans,
        failed_citations=failed_cites,
    )`,
    },
    starStory: {
      situation: 'Council answers occasionally cited file paths that didn\'t exist or attributed quotes to functions never written. Operators caught these manually; the LLM offered no signal that the claim was invented.',
      task: 'Mechanical hallucination detection that surfaces invented spans before operator review.',
      action: 'Built citation_verifier.py over the existing retrieval-set output. Added similarity threshold + pass-rate floor (ratchet). Drill the parser + resolver + threshold.',
      result: 'Hallucination spans now surface in red in the operator UI. Council answers below 80% citation pass rate auto-reject. Floor walked from 0.6 to 0.55 once observed reality stabilised.',
    },
    interviewTraps: [
      'Trusting the LLM\'s self-confidence (high confidence ≠ correct)',
      'Citation count without resolution (cosmetic; doesn\'t catch invention)',
      'No per-domain similarity tuning (medical vs code generation should not share threshold)',
    ],
    finalScript: 'Citation discipline is the hallucination guardrail. Every claim cites a chunk_id; the verifier resolves each; similarity check catches paraphrase drift; the pass rate has a floor that walks per the ratchet pattern. Together: invented facts are mechanically detectable, not a judgement call. That is what makes the council answer regulator-traceable rather than just plausible.',
  },
  {
    slug: 'evaluation-harness',
    title: '2. Evaluation harness (golden set + regression delta)',
    status: 'partial',
    coreConcept: 'A frozen golden dataset of (query, expected output) pairs that runs on every prompt-version or model-version change. Pass/fail rate vs the golden set is the gate for promoting a prompt to production. Without this harness, a prompt change is uncontrolled — accuracy regressions slip in silently.',
    problem: 'Prompt changes look harmless but shift model behaviour subtly. A 1-line "be more concise" tweak can drop accuracy on the 80% case to satisfy 5% complaints. Without golden-set regression, the operator has no feedback signal beyond "production users complaining".',
    whyThisApproach: 'Golden set + regression delta is the same pattern as code-test coverage. Every prompt change must pass; new test cases extend coverage; failed cases auto-bisect to the offending prompt edit. Per global §48 + §38 governance gates, eval is a deployment prerequisite for AI features.',
    whenToUse: ['Every prompt registry update', 'Every model swap', 'Periodic drift check (weekly)', 'Pre-release governance gate'],
    whenNotToUse: ['Throwaway exploratory prompts', 'One-shot completions for non-critical paths', 'Anything where ground truth is undefined'],
    input: 'golden_set.jsonl: [{query, expected_keys, expected_citations, min_score}, ...]',
    process: [
      'Run prompt against each golden query via the council',
      'Score response: keys present, citations match, length OK, similarity ≥ min_score',
      'Compute pass rate; compare to baseline pass rate from prior version',
      'Delta < threshold → promote; ≥ threshold → block release',
      'Surface failed cases with diff against expected for operator review',
    ],
    output: 'Pass-rate report + per-case diff + promotion/block decision.',
    flowchart: `flowchart LR
  prompt[Prompt vN] --> run[Run against golden set]
  run --> score[Score per case]
  score --> agg[Aggregate pass rate]
  agg --> baseline{>= baseline?}
  baseline -->|yes| promote[Promote vN]
  baseline -->|no| block[Block release + diff]`,
    sequence: `sequenceDiagram
  autonumber
  participant Dev as Prompt author
  participant H as Harness
  participant G as Golden set
  participant Reg as Prompt registry
  Dev->>H: trigger run for prompt_vN
  H->>G: load golden cases
  loop each case
    H->>H: run case via council with vN
    H->>H: score against expected
  end
  H->>H: aggregate pass rate
  alt rate >= baseline
    H->>Reg: promote vN
    H-->>Dev: APPROVED
  else regression
    H-->>Dev: BLOCKED + diff
  end`,
    alternatives: [
      { name: 'Manual A/B review', tradeoff: 'Slow; subjective; scales poorly past 10 cases' },
      { name: 'External eval SaaS', tradeoff: 'Mature tools; expensive; cannot use project-internal council' },
      { name: 'No eval, ship + monitor', tradeoff: 'Status quo for many teams; users are the test; reputation risk' },
    ],
    challenges: [
      'Golden set drift (cases lose relevance as product changes)',
      'Subjective scoring (when is "concise" right?)',
      'Coverage gap (golden cases don\'t exercise edge of distribution)',
      'Cost (running every prompt change against full golden set)',
    ],
    edgeCases: [
      { case: 'Golden case becomes obsolete', solution: 'Versioned golden set; deprecate cases with reason; new cases replace' },
      { case: 'Pass rate stuck at 80% forever', solution: 'Floor walked per ratchet; 80% is the new normal until cause is fixed' },
      { case: 'Regression in 1 case crucial to a customer', solution: 'Tag cases with priority; weighted scoring; high-priority regression always blocks' },
      { case: 'Same case scored differently by 2 reviewers', solution: 'Write rubric; LLM-as-judge calibrated against rubric per ADR' },
    ],
    failureModes: [
      { mode: 'Golden set rots — never updated', detect: 'Cases predate last 3 releases', recover: 'Quarterly review; archive irrelevant; add 5 new cases' },
      { mode: 'Cost dominates', detect: 'documind_eval_cost_usd > budget', recover: 'Sample golden set per prompt change; full run weekly' },
      { mode: 'Latency blocks release', detect: 'Run > 10min for 100 cases', recover: 'Parallelize; cache responses for unchanged cases' },
    ],
    monitoring: [
      'documind_eval_pass_rate{prompt_version}',
      'documind_eval_regression_delta (vs prior version)',
      'documind_eval_cost_usd (per run)',
      'documind_eval_runtime_seconds_p95',
    ],
    testing: [
      'drill_eval_harness_promotion (locks the promote/block decision logic)',
      'drill_eval_golden_set_versioning (golden set has version + deprecation discipline)',
      'drill_eval_cost_budget (run cost ≤ daily budget)',
    ],
    security: [
      'Golden set may contain PII — store under access control + redact in logs',
      'Cost trace per run for §41 FinOps audit',
      'Prompt versions immutable post-promotion; rollback via registry, not edit',
    ],
    scaling: [
      '10x: 100-case golden set runs in ~2 minutes per prompt change',
      '100x: tiered golden set (smoke = 10 cases / full = 100 cases per release)',
      'Cost driver: LLM tokens per case; cache + reuse for unchanged inputs',
    ],
    maturity: {
      mvp: 'Manual review of 5 sample answers per prompt change',
      production: 'PARTIAL — council promotion gate exists; no formal golden set yet',
      enterprise: 'Full harness with versioned golden set + ratchet floor + cost budget + LLM-as-judge with rubric',
    },
    limitations: [
      'No formal golden set committed yet — promotion is judgement-based',
      'No regression-delta gate in CI',
      'No cost budget per run',
    ],
    projectFit: [
      'services/sidecar-advisor/* — council with prompt registry (foundation)',
      'docs/architecture/adr/ — prompt versioning ADRs',
      '/admin/llmops/deep — operator surface for prompt registry',
      'Future: services/eval-harness/ + tests/golden_sets/ + CI hook',
    ],
    interviewLine: 'Evaluation harness is golden-set regression, exactly like code tests. Every prompt change must pass; the floor walks; failed cases surface with diffs. Without it, prompt edits are uncontrolled and accuracy regressions slip silently into production.',
    implementationSteps: [
      { step: 'Golden set format', logic: 'JSONL with query + expected_keys + expected_citations + min_score per case.' },
      { step: 'Scorer per case', logic: 'Keys present, citations resolve, similarity ≥ min_score, length within bounds.' },
      { step: 'Aggregate + delta', logic: 'Pass rate vs baseline; regression > threshold → block.' },
      { step: 'Cost budget', logic: 'Per-run cost cap; fail-fast if exceeded; documented in §41 FinOps.' },
      { step: 'Versioned golden set', logic: 'Cases have version + deprecation reason; never edit, only deprecate + add.' },
      { step: 'CI integration', logic: 'Runs on every prompt registry PR; blocks merge on regression.' },
      { step: 'Drill the gate', logic: 'drill_eval_harness_promotion locks the promote/block decision.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/eval-harness/app/runner.py — PARTIAL skeleton
import json
from pathlib import Path

def load_golden(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]

def score_case(case: dict, response: str, citations: list[str]) -> dict:
    keys_ok = all(k in response for k in case["expected_keys"])
    cites_ok = set(case.get("expected_citations", [])).issubset(citations)
    length_ok = len(response) <= case.get("max_length", 4000)
    sim = case.get("similarity_fn", lambda r, e: 1.0)(response, case["expected_text"])
    return {
        "passed": keys_ok and cites_ok and length_ok and sim >= case["min_score"],
        "keys_ok": keys_ok,
        "cites_ok": cites_ok,
        "length_ok": length_ok,
        "similarity": sim,
    }

def execute_run(golden_path: Path, prompt_version: str) -> dict:
    cases = load_golden(golden_path)
    results = [score_case(c, *run_council(c["query"], prompt_version)) for c in cases]
    pass_rate = sum(r["passed"] for r in results) / len(results)
    return {"prompt_version": prompt_version, "pass_rate": pass_rate, "cases": results}`,
    },
    starStory: {
      situation: 'Prompt edits were promoted on operator judgement alone. Subtle accuracy regressions slipped through; users complained weeks later; root cause was always "we changed the prompt".',
      task: 'Mechanical regression eval gating prompt promotion, with cost budget + versioned golden set.',
      action: 'PARTIAL — council promotion gate exists; formal golden set + CI integration are still on the roadmap. Skeleton in services/eval-harness/ planned alongside drill_eval_harness_promotion.',
      result: 'When complete: every prompt change auto-runs against golden set; regression > threshold blocks promotion; cost budget caps spend per run.',
    },
    interviewTraps: [
      'No baseline (cannot compute regression delta)',
      'Static golden set that rots over time',
      'No cost budget (eval runs become a budget bomb)',
    ],
    finalScript: 'Output evaluation is two halves: hallucination guardrail at runtime (citation discipline) and regression at promotion time (golden set). The first protects users from invented facts; the second protects the system from prompt regressions. Both are mechanical, both are auditable, both are governance-gate prerequisites per §38. Without them, AI features ship on hope.',
  },
];

export default function OutputEvalDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Output evaluation deep dive</h1>
          <p className="page-subtitle">
            Two surfaces — runtime hallucination guardrail (citation
            resolution) and promotion-time regression (golden set) — explained
            through the universal 20-dimension framework.
          </p>
        </div>
      </div>
      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/llmops/deep', label: 'LLMOps scorecard', why: 'output evaluation is the production-readiness gate for prompt promotion; LLMOps owns the registry' },
          { href: '/admin/explainability/deep', label: 'Explainability evidence', why: 'citation trail produced by the hallucination guardrail IS the explainability audit row per §48' },
          { href: '/admin/rag/deep#post-retrieval', label: 'RAG · Post-retrieval', why: 'citation discipline lives in the post-retrieval stage where claims are bound to chunks' },
          { href: '/admin/guardrails/deep', label: 'AI Guardrails', why: 'hallucination guardrail is one of three guardrail layers; this page details its mechanics' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'no eval = no promote; release blocked per §38 deployment prerequisite' },
        ]}
      />
    </>
  );
}
