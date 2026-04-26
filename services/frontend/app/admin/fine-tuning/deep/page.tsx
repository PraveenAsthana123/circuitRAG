'use client';

/**
 * Fine-tuning scenarios: supervised, unsupervised, semi-supervised.
 * Plus the brutal RAG-vs-fine-tuning decision rule.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ---- 1. Supervised Fine-Tuning ----
  {
    slug: 'supervised-fine-tuning',
    title: '1. Supervised Fine-Tuning (SFT)',
    status: 'shipped',
    coreConcept: 'Train the model on labeled (input, correct-output) pairs. Use when you know the exact answer shape — tone, format, structure, compliance language. Bad labels in, bad model out.',
    oneLiner: 'SFT = teach style + format via labeled examples. Quality of labels = quality of model.',
    businessContext: 'Customer-facing AI must match approved tone (banking compliance, medical safety, legal precision). Prompting alone drifts under load; SFT bakes the format into the weights.',
    fiveW: {
      what: 'Continued training of a base/instruct model on a curated dataset of (prompt, ideal-completion) pairs. Cross-entropy loss against the target completion.',
      why: 'Need consistent, compliant output format that survives temperature jitter and prompt changes. Better than long system prompts for high-volume traffic.',
      where: 'Customer support, legal assistants, medical triage, sales scripts, enterprise chatbots — anywhere format/tone matters more than recall.',
      when: 'You have ≥ 1k high-quality human-reviewed examples; format/tone is the bottleneck (not knowledge freshness).',
      who: 'AI/ML team owns training. SMEs (compliance, legal, medical, support leads) own labels. Eval team owns golden test set.',
    },
    interview30s: 'SFT is teaching format. We collect 1k-10k human-reviewed (question, approved-answer) pairs, fine-tune a base model with cross-entropy loss, and ship it as a tone-locked variant. The non-negotiable test is a held-out eval set scored on format compliance, factual accuracy, and tone match. Fewer than 500 examples = don\'t fine-tune; improve prompting + RAG instead. Bad labels = bad model — single biggest failure mode.',
    coreBuildingBlocks: [
      'Labeled dataset — (input, ideal-output) pairs, ≥1k high-quality',
      'SME review pipeline — domain experts approve every example',
      'Train script — LoRA / QLoRA / full FT depending on budget',
      'Held-out eval set — never seen during training; scores format + accuracy',
      'Model registry — versioned with dataset hash + hyperparams',
      'Canary deployment — 5% traffic; compare against base model',
      'Rollback plan — model + dataset version pinned per deploy',
    ],
    architectureRelevance: {
      backend: 'Fine-tuned model loaded behind inference-svc. Routing config picks SFT model for specific tenants/features.',
      rag: 'SFT + RAG combined: RAG provides knowledge, SFT enforces answer format. Most enterprise wins come from this pair.',
      ai: 'Model registry tracks base + SFT version + dataset hash + LoRA adapters. Audit trail for compliance.',
      microservices: 'SFT model behind a feature flag; gradual rollout via Istio VirtualService traffic split.',
    },
    flowchart: `flowchart LR
  D[Labeled dataset 1k-10k] --> R[SME review]
  R --> T[Train base + LoRA]
  T --> E[Held-out eval]
  E -->|pass| REG[Model registry]
  E -->|fail| FIX[Fix labels or hyperparams]
  FIX --> T
  REG --> CAN[Canary 5 pct]
  CAN --> COMP{vs base}
  COMP -->|better| FULL[Full rollout]
  COMP -->|worse| ROLL[Rollback]`,
    sequence: `sequenceDiagram
  autonumber
  participant SME as SME reviewer
  participant DS as Dataset
  participant TR as Train job
  participant E as Eval
  participant REG as Registry
  SME->>DS: review and label examples
  TR->>DS: load curated set
  TR->>TR: fine-tune with cross-entropy
  TR->>E: run held-out eval
  E-->>TR: scores format and accuracy
  TR->>REG: publish v2 with dataset hash
  REG-->>TR: version pinned`,
    coreLayers: [
      { layer: 'Dataset', responsibility: 'Curated (input, output) pairs. SME-reviewed. Versioned. Audit trail per change.' },
      { layer: 'Training', responsibility: 'LoRA / QLoRA for cheap; full FT for premium. Cross-entropy on ideal completion.' },
      { layer: 'Eval', responsibility: 'Held-out set scored on format compliance + factual accuracy + tone. Gates registry.' },
      { layer: 'Registry', responsibility: 'Versioned model + dataset hash + hyperparams. Reproducible.' },
      { layer: 'Deployment', responsibility: 'Canary 5% → compare metrics → full rollout OR rollback. Feature-flagged.' },
    ],
    problem: 'Pure prompting drifts under load. Long system prompts add token cost. Format compliance + tone consistency must survive temperature jitter and prompt edits.',
    whyThisApproach: 'SFT bakes format into weights — survives prompt churn. LoRA makes it cheap (~$10-100 per fine-tune). Versioned registry makes it reproducible.',
    whenToUse: ['Compliant tone required (banking, medical, legal)', 'Format consistency matters more than recall', '≥1k high-quality labeled examples available', 'Inference cost reduction (smaller fine-tuned model)'],
    whenNotToUse: ['Need latest facts → use RAG', '< 500 examples available — improve prompting first', 'Knowledge changes weekly → can\'t bake it in', 'Tasks where reasoning > format'],
    input: 'Curated (prompt, ideal-output) dataset + base model + hyperparams',
    process: [
      'Collect candidate (input, output) pairs from production logs or expert hand-writing',
      'SME review every example — reject ambiguous, fix incorrect',
      'Split: train 80% / val 10% / held-out 10%',
      'Fine-tune via LoRA / QLoRA with cross-entropy loss',
      'Eval against held-out set — format + accuracy + tone',
      'On pass: publish to registry with dataset hash',
      'Canary deploy 5% traffic; compare against base',
      'Full rollout OR rollback based on metrics',
    ],
    output: 'Fine-tuned model variant + eval scorecard + audit trail. Deployed behind feature flag.',
    alternatives: [
      { name: 'Long system prompt', tradeoff: 'No training; drifts under load; high token cost' },
      { name: 'Few-shot prompting', tradeoff: 'Cheaper than SFT; weaker format consistency' },
      { name: 'RLHF', tradeoff: 'Better for nuanced quality; needs preference data; harder to operate' },
      { name: 'DPO', tradeoff: 'Cheaper than RLHF; similar gains; needs preference pairs' },
    ],
    challenges: [
      'Bad labels = bad model (largest failure)',
      'Catastrophic forgetting on out-of-distribution queries',
      'Eval-to-prod gap (metric ≠ user satisfaction)',
      'Dataset drift over time',
      'GPU cost for full FT',
    ],
    edgeCases: [
      { case: '< 500 examples — should we still SFT?', solution: 'No — improve prompting + RAG; add eval; revisit at 1k' },
      { case: 'Labels disagree on edge cases', solution: 'Triage with SME panel; create style guide; reject ambiguous' },
      { case: 'Production drifts away from labeled distribution', solution: 'Periodic retraining with sampled prod logs (review first)' },
      { case: 'Fine-tuned model regresses on out-of-domain', solution: 'Mix some general-domain examples in training (5-10%)' },
    ],
    failureModes: [
      { mode: 'Bad label leaks into training', detect: 'Eval drops; SME spot-check', recover: 'Revoke version; re-clean dataset; retrain' },
      { mode: 'Hyperparam regression', detect: 'Eval scores below baseline', recover: 'Roll back to prior config; investigate' },
      { mode: 'Catastrophic forgetting', detect: 'Out-of-domain eval set fails', recover: 'Lower learning rate; mix general examples; LoRA adapter' },
    ],
    monitoring: ['Eval score trend per version', 'Production format-compliance rate', 'User satisfaction (sampled)', 'Cost per inference (vs base)', 'Distribution drift (input embeddings)'],
    testing: ['Held-out eval after every train', 'Adversarial probe (jailbreak, format-confusion)', 'Out-of-distribution canary', 'Periodic SME review of sampled prod outputs'],
    security: ['Dataset audit chain', 'No PII in training data without redaction', 'Model registry signed', 'Per-tenant adapter (no cross-leak)'],
    scaling: [
      '$10-100 per LoRA training run',
      'Inference parity with base after merge',
      'Per-tenant LoRA adapters compose at serve time',
    ],
    maturity: {
      mvp: 'Single SFT run; manual deploy',
      production: 'LoRA + held-out eval + canary + rollback',
      enterprise: 'Per-tenant adapters + automated retraining + drift detection + audit trail',
    },
    limitations: [
      'Quality bounded by label quality',
      'Doesn\'t help with knowledge freshness',
      'Risk of overfitting on narrow distribution',
    ],
    projectFit: [
      'libs/py/documind_core/model_registry.py',
      'eval-svc — held-out + adversarial benchmarks',
      'governance.model_audit — version + dataset hash trail',
      'mcp/tests/drill_sft_*.py — eval gates',
    ],
    interviewLine: 'SFT is teaching format. ≥1k SME-reviewed examples. LoRA makes it cheap. Held-out eval gates the deploy. Bad labels = bad model — single biggest risk.',
    finalScript: 'Supervised fine-tuning teaches format. We collect 1k to 10k human-reviewed (input, approved-output) pairs, fine-tune a base model with cross-entropy loss using LoRA for cost efficiency, and gate the deploy on a held-out eval covering format compliance, factual accuracy, and tone match. Canary 5% traffic; compare against base on production metrics; full rollout or rollback. Below 500 examples — don\'t SFT; improve prompting and RAG first. The single biggest failure mode is bad labels — every example is SME-reviewed before training. Per-tenant LoRA adapters let us serve customized variants without retraining the base.',
  },

  // ---- 2. Unsupervised Fine-Tuning ----
  {
    slug: 'unsupervised-fine-tuning',
    title: '2. Unsupervised Fine-Tuning (Domain Adaptation)',
    status: 'partial',
    coreConcept: 'Continued pre-training on raw domain text — no labels. Teaches the model your industry vocabulary (oil & gas, banking, medical, legal). Doesn\'t teach answer format.',
    oneLiner: 'Unsupervised FT = domain language. Teaches vocabulary; doesn\'t teach format.',
    businessContext: 'Generic models miss niche terminology — "BHP" in petroleum vs banking, "SOAP" in medical vs API. Continued pretraining on raw domain corpus closes the vocabulary gap.',
    fiveW: {
      what: 'Continued pretraining (next-token prediction) on raw domain documents — manuals, SOPs, transcripts, papers. No (input, output) structure required.',
      why: 'Base models trained on general web miss specialized vocabulary. Domain adaptation makes downstream SFT or RAG more accurate by giving the model the right priors.',
      where: 'Pre-step before SFT or RAG deployment. Specifically valuable for niche industries with proprietary terminology.',
      when: 'You have a large raw domain corpus (≥100MB clean text) and base model misses key terms. Often combined with subsequent SFT.',
      who: 'Data team owns corpus curation. AI/ML team owns training. Domain SMEs validate terminology coverage post-train.',
    },
    interview30s: 'Unsupervised fine-tuning is domain language adaptation. We feed raw domain text — manuals, SOPs, transcripts — and continue pretraining the base model. No labels needed. Output: a model that has seen your terminology in context. It doesn\'t teach format (use SFT for that) and doesn\'t teach knowledge freshness (use RAG for that). The discipline: clean and dedupe the corpus first; otherwise the model learns noise. Verify with perplexity benchmarks on held-out domain text.',
    coreBuildingBlocks: [
      'Raw corpus — manuals, SOPs, logs, transcripts, papers (≥100MB)',
      'Cleaning pipeline — dedup, language detect, OCR-error fix, PII redaction',
      'Tokenizer check — verify domain terms not over-fragmented',
      'Continued-pretraining job — next-token prediction on the corpus',
      'Perplexity eval — held-out domain text; lower = better',
      'SME terminology spot-check — does the model use terms correctly?',
    ],
    architectureRelevance: {
      backend: 'Fine-tuned base loaded as a new variant; can serve as foundation for downstream SFT.',
      rag: 'Domain-adapted base improves RAG retrieval prompts and grounded generation quality on niche content.',
      ai: 'Tokenizer extension for very specialized vocabulary; embedding versioning still applies if used.',
      microservices: 'Same deployment shape as SFT — feature flag + canary + audit.',
    },
    flowchart: `flowchart LR
  R[Raw corpus 100MB+] --> C[Clean and dedupe]
  C --> P[PII redact]
  P --> T[Tokenizer check]
  T --> CPT[Continued pretraining]
  CPT --> PE[Perplexity eval]
  PE -->|pass| REG[Registry]
  PE -->|fail| FIX[More corpus or longer train]
  REG --> SFT[Optional downstream SFT]`,
    sequence: `sequenceDiagram
  autonumber
  participant DS as Data team
  participant CL as Cleaner
  participant TR as Train
  participant E as Eval
  DS->>CL: raw documents
  CL->>CL: dedup language redact
  CL->>TR: cleaned corpus
  TR->>TR: continued pretraining
  TR->>E: held-out perplexity
  E-->>TR: score
  TR->>TR: register variant`,
    coreLayers: [
      { layer: 'Corpus layer', responsibility: 'Raw domain text. Curated, deduped, PII-redacted, language-tagged.' },
      { layer: 'Tokenizer layer', responsibility: 'Verify domain terms encode efficiently. Optionally extend vocabulary.' },
      { layer: 'Training layer', responsibility: 'Continued pretraining — next-token prediction. Lower learning rate than from-scratch.' },
      { layer: 'Eval layer', responsibility: 'Perplexity on held-out domain text. Sanity-check on benchmarks.' },
      { layer: 'Registry layer', responsibility: 'Variant tagged as "domain-adapted base". Subsequent SFT builds on it.' },
    ],
    problem: 'Base models miss niche terminology. RAG and SFT both work better on a domain-adapted base.',
    whyThisApproach: 'No labels required → cheap to start. Improves downstream RAG + SFT quality. Cleanly composable with subsequent steps.',
    whenToUse: ['Niche industry vocabulary', 'Large raw corpus available', 'Pre-step before SFT', 'Tokenizer fragments key terms'],
    whenNotToUse: ['General-domain task — base model is fine', 'Small corpus — gains marginal', 'Need answer format → use SFT', 'Need fresh facts → use RAG'],
    input: 'Cleaned + deduped + redacted raw text corpus + base model + hyperparams',
    process: [
      'Curate raw corpus from domain sources',
      'Clean: dedup, language detect, OCR fix, PII redact',
      'Tokenizer audit: are key terms encoded efficiently?',
      'Continued pretraining with lower learning rate',
      'Perplexity eval on held-out domain text',
      'SME terminology spot-check',
      'Register as domain-adapted base; downstream SFT optional',
    ],
    output: 'Domain-adapted base model variant. Lower perplexity on held-out domain text vs original base.',
    alternatives: [
      { name: 'Skip — use general base + RAG', tradeoff: 'Cheaper; weaker on niche terminology' },
      { name: 'Tokenizer extension only', tradeoff: 'Cheap; helps fragmentation; doesn\'t teach context' },
      { name: 'Few-shot domain prompting', tradeoff: 'Cheapest; doesn\'t scale; high token cost' },
    ],
    challenges: [
      'Noise in raw corpus → model learns garbage',
      'Catastrophic forgetting on general tasks',
      'Tokenizer mismatch breaks downstream SFT',
      'No clear stopping criterion (perplexity is a proxy)',
      'GPU cost scales with corpus size',
    ],
    edgeCases: [
      { case: 'Corpus has PII', solution: 'Mandatory Presidio redaction step; audit redaction rate' },
      { case: 'Corpus dominated by one document', solution: 'Dedupe + downsample; balanced sources' },
      { case: 'Domain term tokenized as 8 BPE pieces', solution: 'Tokenizer extension OR accept the inefficiency' },
      { case: 'General-task perplexity rises', solution: 'Mix 5-10% general-domain examples; lower learning rate' },
    ],
    failureModes: [
      { mode: 'Model learns OCR noise', detect: 'Garbled outputs; SME spot-check', recover: 'Re-clean corpus; retrain from base' },
      { mode: 'Catastrophic forgetting', detect: 'General benchmarks regress', recover: 'Mix general data; lower LR; retrain' },
      { mode: 'Tokenizer drift', detect: 'Downstream SFT loss spikes', recover: 'Pin tokenizer version; retrain SFT on matching base' },
    ],
    monitoring: ['Held-out perplexity', 'Token-fragmentation ratio for key terms', 'General-benchmark scores (drift)', 'Training loss curve'],
    testing: ['Perplexity on held-out domain', 'General-benchmark sanity check', 'Tokenizer audit on key terms', 'SME terminology spot-check'],
    security: ['PII redacted before training', 'Corpus access controlled', 'Per-tenant variants isolated'],
    scaling: ['Corpus size: 100MB → 10GB → 100GB+ (cost scales)', 'LoRA-on-base for cheap variant; full FT for premium'],
    maturity: {
      mvp: 'Single corpus; manual eval',
      production: 'Cleaned corpus + perplexity eval + SME spot-check + registry',
      enterprise: 'Multi-domain corpus + automated drift detection + per-domain variants',
    },
    limitations: [
      'Doesn\'t teach answer format',
      'Doesn\'t teach knowledge freshness',
      'Quality bounded by corpus quality',
    ],
    projectFit: [
      'data-svc — corpus curation + cleaning',
      'eval-svc — perplexity benchmarks',
      'libs/py/documind_core/model_registry.py',
    ],
    interviewLine: 'Unsupervised fine-tuning teaches domain language. Clean and dedupe before training; otherwise the model learns noise. Pairs with SFT (format) and RAG (knowledge).',
    finalScript: 'Unsupervised fine-tuning is domain language adaptation. We continue pretraining the base model on raw domain text — manuals, SOPs, transcripts, papers — with a cleaning pipeline that deduplicates, redacts PII, and tags language. No labels required. Output is a domain-adapted base where downstream SFT and RAG both perform better. The discipline: corpus quality is the bottleneck — noise in equals noise out. Perplexity eval on held-out text gates the registry; SMEs spot-check terminology. It doesn\'t teach format (SFT does that) or freshness (RAG does that) — it teaches vocabulary.',
  },

  // ---- 3. Semi-Supervised Fine-Tuning ----
  {
    slug: 'semi-supervised-fine-tuning',
    title: '3. Semi-Supervised Fine-Tuning',
    status: 'partial',
    coreConcept: 'Combine a small labeled set with a large unlabeled set. Pseudo-labels expand coverage; SME review keeps quality. Best when labels are expensive but raw data is plentiful.',
    oneLiner: 'Semi-supervised = small gold + large raw. Pseudo-labels expand coverage; SME review prevents drift.',
    businessContext: 'Most enterprise scenarios have abundant raw data (chat history, claim records, call transcripts) but expensive labels (1k SME-reviewed answers, 100k raw tickets). Semi-supervised exploits both.',
    fiveW: {
      what: 'Bootstrap from a small labeled set; use the model to pseudo-label the unlabeled set; SME review high-confidence + high-impact samples; combine for SFT.',
      why: 'Labels are the bottleneck. Pseudo-labeling cheaply 10x\'s coverage; SME review on subset keeps quality bounded.',
      where: 'Insurance claims, healthcare FAQ, ecommerce support, voice agent transcripts, RAG assistant Q&A.',
      when: 'You have ~1k labels and ~100k unlabeled. Labels expensive (SME hours); raw data cheap (production logs).',
      who: 'AI/ML team owns pipeline. SMEs review high-impact samples. Eval team owns the gold held-out set.',
    },
    interview30s: 'Semi-supervised exploits the gap: labels are expensive (1k SME-reviewed), raw data is cheap (100k tickets). Bootstrap an SFT from the labeled set; use it to pseudo-label the unlabeled set; SME review the high-impact + low-confidence samples; combine for a second SFT round. Repeat until eval plateaus. The non-negotiable check is human review on the highest-impact samples — pseudo-label errors compound silently.',
    coreBuildingBlocks: [
      'Labeled seed set — SME-reviewed (input, output) pairs (~1k)',
      'Unlabeled corpus — raw production data (~100k)',
      'Bootstrap SFT — train initial model on labeled set',
      'Pseudo-labeler — bootstrap model labels unlabeled corpus',
      'Confidence + impact triage — flag low-confidence + high-impact for review',
      'SME review queue — humans approve / reject pseudo-labels',
      'Combined train — labeled + reviewed pseudo-labels = next round',
      'Eval on held-out — gates each round',
    ],
    architectureRelevance: {
      backend: 'Same SFT deployment shape; pseudo-labeling job runs as scheduled batch.',
      rag: 'Semi-supervised SFT often beats pure SFT for grounded RAG — model learns from production query distribution.',
      ai: 'Each round logged with dataset version; rollback granularity per round.',
      microservices: 'Pseudo-labeler is a worker pool; SME review is a queue with human-in-the-loop.',
    },
    flowchart: `flowchart LR
  L[Labeled 1k] --> S1[Bootstrap SFT v1]
  U[Unlabeled 100k] --> S1
  S1 --> PL[Pseudo-label corpus]
  PL --> CT{Confidence + impact}
  CT -->|low conf or high impact| HR[SME review]
  CT -->|high conf low impact| AC[Auto-accept]
  HR --> CB[Combined dataset]
  AC --> CB
  CB --> S2[SFT v2]
  S2 --> E[Eval on held-out]
  E -->|improved| REG[Registry]
  E -->|plateau| STOP[Stop]
  E -->|regress| ROLL[Rollback]`,
    sequence: `sequenceDiagram
  autonumber
  participant L as Labeled set
  participant U as Unlabeled corpus
  participant T1 as Train v1
  participant PL as Pseudo-label
  participant SME as SME review
  participant T2 as Train v2
  participant E as Eval
  L->>T1: 1k examples
  T1->>PL: deploy bootstrap model
  U->>PL: 100k unlabeled
  PL->>PL: pseudo-label all
  PL->>SME: low-conf + high-impact samples
  SME-->>PL: approved labels
  PL->>T2: combined dataset
  T2->>E: eval held-out
  E-->>T2: scores`,
    coreLayers: [
      { layer: 'Labeled layer', responsibility: 'SME-curated seed set. Versioned. Audit chain per change.' },
      { layer: 'Bootstrap', responsibility: 'Train initial model on labeled set only. Used as pseudo-labeler.' },
      { layer: 'Pseudo-label', responsibility: 'Run bootstrap model over unlabeled corpus; emit (input, predicted-output, confidence).' },
      { layer: 'Triage', responsibility: 'Confidence × impact matrix. Low-conf or high-impact → SME queue. Else auto-accept.' },
      { layer: 'Review', responsibility: 'SME approves / rejects pseudo-labels. Bounded review budget per round.' },
      { layer: 'Train v2+', responsibility: 'Combine labeled + reviewed pseudo-labels. Train next round. Eval-gated.' },
    ],
    problem: 'Labels are expensive. Raw data is cheap. Pure SFT under-uses the cheap data; pure unsupervised misses the format signal in labels.',
    whyThisApproach: 'Pseudo-labeling 10x\'s coverage; SME review on subset keeps quality bounded; iterative rounds reduce error compounding.',
    whenToUse: ['~1k labels + ~100k unlabeled', 'SME hours scarce', 'Production data abundant', 'Tasks with strong format consistency need'],
    whenNotToUse: ['Labels plentiful → use pure SFT', 'No labels available → use pure unsupervised', 'Tasks where pseudo-labels can\'t be SME-validated'],
    input: 'Labeled seed set + unlabeled corpus + base model + SME review budget',
    process: [
      'Train bootstrap SFT v1 on labeled seed',
      'Run v1 over unlabeled corpus → pseudo-labels with confidence',
      'Triage: low-confidence OR high-impact samples → SME queue',
      'SME review approves / rejects flagged samples',
      'Combine: labeled + reviewed pseudo-labels',
      'Train v2 on combined set',
      'Eval on held-out gold set',
      'If improved: register; if plateau: stop; if regress: rollback',
      'Optionally repeat with v2 as new pseudo-labeler',
    ],
    output: 'Iteratively-improved SFT model + audit chain per round + reviewed pseudo-label corpus.',
    alternatives: [
      { name: 'Pure SFT (1k labels)', tradeoff: 'Simpler; under-uses cheap data; weaker on coverage' },
      { name: 'Pure unsupervised', tradeoff: 'No format signal; weaker on task quality' },
      { name: 'Active learning', tradeoff: 'Smarter SME spending; harder to operate; needs uncertainty model' },
      { name: 'Knowledge distillation from larger model', tradeoff: 'No labels needed; depends on teacher quality; cost' },
    ],
    challenges: [
      'Pseudo-label errors compound across rounds',
      'SME review budget is finite',
      'Confidence calibration on bootstrap model is unreliable',
      'High-impact triage rule is hard to define',
      'Eval-to-prod gap (golden set bias)',
    ],
    edgeCases: [
      { case: 'Bootstrap model overconfident on wrong answers', solution: 'Calibration step; lower auto-accept threshold; expand SME sample' },
      { case: 'High-impact samples skewed to one tenant', solution: 'Stratified sampling across tenants in triage' },
      { case: 'SME review backlog grows', solution: 'Bound queue; prioritize by impact × confidence' },
      { case: 'Round v3 regresses vs v2', solution: 'Stop iteration; ship v2; investigate distribution drift' },
    ],
    failureModes: [
      { mode: 'Pseudo-label errors compound', detect: 'Eval drops across rounds', recover: 'Re-review rejected pseudo-labels; regenerate from cleaner v1' },
      { mode: 'SME burnout / queue saturation', detect: 'Review SLA missed', recover: 'Bound queue; auto-defer low-impact; scale SME team' },
      { mode: 'Confidence model miscalibrated', detect: 'High-confidence samples have high error rate', recover: 'Recalibrate; lower auto-accept threshold' },
    ],
    monitoring: ['Per-round eval delta', 'SME approval rate per pseudo-labeler version', 'Auto-accept vs review ratio', 'Per-tenant distribution in dataset', 'Model confidence calibration'],
    testing: ['Held-out gold eval per round', 'Stratified eval (per-tenant, per-feature)', 'Adversarial pseudo-label injection drill', 'Confidence calibration check'],
    security: ['SME review audit chain', 'No PII in pseudo-labels without redaction', 'Per-tenant dataset isolation'],
    scaling: ['Pseudo-labeler runs as worker pool (100k examples ~1h on GPU)', 'SME review queue rate-limited per reviewer'],
    maturity: {
      mvp: 'Single round; manual triage; manual eval',
      production: 'Iterative rounds + triage rules + SME queue + audit + rollback',
      enterprise: 'Active learning + per-tenant adapters + automated drift detection + dashboard',
    },
    limitations: [
      'Quality compounds errors',
      'Bounded by pseudo-labeler quality',
      'SME review budget is the rate limit',
    ],
    projectFit: [
      'eval-svc — golden set + per-round eval',
      'data-svc — pseudo-labeler worker pool',
      'governance.action_drafts — SME review queue (re-used pattern)',
      'libs/py/documind_core/model_registry.py',
    ],
    interviewLine: 'Semi-supervised exploits the gap: ~1k labels + ~100k raw. Pseudo-label, SME review the high-impact subset, retrain. Pseudo-label errors compound — that\'s the key risk.',
    finalScript: 'Semi-supervised fine-tuning is the realistic enterprise scenario: about a thousand SME-reviewed labels and a hundred thousand raw production records. Bootstrap a v1 model on the labeled seed; deploy it as a pseudo-labeler over the unlabeled corpus; emit each (input, predicted-output, confidence) triple. Triage: low-confidence or high-impact samples go to SME review; rest auto-accept. Combine the reviewed pseudo-labels with the original labeled set; train v2; eval on a held-out gold set. Repeat until eval plateaus. The non-negotiable check is human review on high-impact samples — pseudo-label errors compound silently across rounds. Per-round audit + rollback per registry version.',
  },

  // ---- 4. RAG vs Fine-Tuning ----
  {
    slug: 'rag-vs-fine-tuning',
    title: '4. RAG vs Fine-Tuning — the brutal decision rule',
    status: 'shipped',
    coreConcept: 'RAG and fine-tuning solve different problems. RAG = freshness + dynamic data. Fine-tuning = format + reasoning patterns. Most production systems use BOTH; the question is which loads the bottleneck.',
    oneLiner: 'RAG = facts; fine-tuning = format. Most production = both, with fine-tuned LLM behind RAG retrieval.',
    businessContext: 'Teams burn cycles fine-tuning what RAG would solve cheaper, OR running RAG over a model whose tone is wrong. The decision rule is a 30-second audit.',
    fiveW: {
      what: 'A decision matrix mapping the actual constraint (freshness, format, reasoning, cost) to the right tool (RAG, fine-tuning, both, neither).',
      why: 'Wrong choice = months of wasted training cost OR retrieval-noise that fine-tuning can\'t fix.',
      where: 'Architecture decision before any production AI build.',
      when: 'Always at the start; revisit when constraints change (regulator update, new tenant tier).',
      who: 'AI/ML lead + product + compliance. Architect signs the ADR.',
    },
    interview30s: 'RAG and fine-tuning answer different questions. Need latest facts? RAG. Need answer format and tone? Fine-tuning. Need private dynamic data? RAG. Need strict policy wording? Fine-tuning + guardrails. Most production systems pair them: fine-tuned LLM behind RAG retrieval. Below 500 examples — don\'t fine-tune; improve RAG and prompting first. Above 1k high-quality examples — fine-tuning earns its weight. Lots of raw text but few labels — semi-supervised.',
    decisionMatrix: [
      { option: 'RAG only', whenToUse: 'Need latest facts; private dynamic data; corpus changes weekly; < 500 labeled examples' },
      { option: 'SFT only', whenToUse: 'Format / tone / compliance language is the bottleneck; ≥ 1k high-quality labels; knowledge static' },
      { option: 'Unsupervised FT only', whenToUse: 'Domain vocabulary gap; large raw corpus; no labels yet' },
      { option: 'Semi-supervised FT', whenToUse: '~1k labels + ~100k raw; SME hours scarce' },
      { option: 'RAG + SFT (most common)', whenToUse: 'Production grade — RAG gives facts; SFT enforces format' },
      { option: 'RAG + unsupervised + SFT', whenToUse: 'Niche industry + format requirements + dynamic facts' },
      { option: 'Neither (prompting only)', whenToUse: 'Pre-PMF; cost-extreme; tasks where prompting suffices' },
    ],
    flowchart: `flowchart TB
  Q{Bottleneck} --> F1{Need latest facts}
  F1 -->|yes| RAG[Use RAG]
  F1 -->|no| F2{Need format or tone}
  F2 -->|yes| F3{Have 1k+ labels}
  F3 -->|yes| SFT[Use SFT plus optional RAG]
  F3 -->|no| F4{Have raw corpus}
  F4 -->|yes| SS[Semi-supervised plus RAG]
  F4 -->|no| PRP[Improve prompting first]
  F2 -->|no| F5{Domain vocabulary gap}
  F5 -->|yes| UNS[Unsupervised FT]
  F5 -->|no| BASE[Use base model + RAG]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant R as RAG retriever
  participant L as Fine-tuned LLM
  participant G as Guardrails
  U->>R: query
  R->>R: retrieve top-K chunks
  R->>L: prompt + chunks
  L->>L: generate with fine-tuned format
  L->>G: output validation
  G-->>U: streamed answer + citations`,
    coreLayers: [
      { layer: 'Decision', responsibility: 'Run the 30-second audit before any build. Bottleneck = facts → RAG; format → FT; both → pair.' },
      { layer: 'RAG layer', responsibility: 'Retrieves dynamic context per query. Cheap to update; expensive to fine-tune format.' },
      { layer: 'Fine-tuned LLM', responsibility: 'Sits behind RAG. Receives chunks + query; emits format-compliant answer.' },
      { layer: 'Guardrails', responsibility: 'Output validation. Citation deadline. Forbidden patterns. Wraps both paths.' },
      { layer: 'Eval', responsibility: 'Combined eval: retrieval quality + answer format + factual accuracy. Gates deploys.' },
    ],
    problem: 'Wrong choice burns months of GPU + SME hours. Pure FT can\'t serve fresh facts; pure RAG can\'t enforce tone.',
    whyThisApproach: 'Decision matrix forces the audit upfront. Pairing both is the production sweet spot for most enterprise.',
    whenToUse: ['Any production AI build', 'Architecture review for AI features', 'Cost / scope conversations with leadership'],
    whenNotToUse: ['Pure prompting prototype phase'],
    input: 'Bottleneck (freshness, format, reasoning, cost) + label availability + corpus availability',
    process: [
      'Identify the actual bottleneck',
      'Check label + corpus availability',
      'Map to decision matrix',
      'Document choice in ADR',
      'Build minimum viable; eval; iterate',
    ],
    output: 'A documented architecture decision that survives stakeholder review.',
    alternatives: [
      { name: 'Pure prompting (no RAG, no FT)', tradeoff: 'Cheapest; lowest quality at scale' },
      { name: 'RAG only', tradeoff: 'Fast facts; weak format' },
      { name: 'FT only', tradeoff: 'Strong format; stale facts' },
      { name: 'RAG + FT (paired)', tradeoff: 'Best quality; highest ops cost' },
    ],
    challenges: [
      'Stakeholders want the "shiny" choice (FT) when RAG would do',
      'Underestimating SME hours for FT labels',
      'Underestimating corpus curation cost for unsupervised',
      'Mid-build pivots',
    ],
    edgeCases: [
      { case: 'Need both fresh facts AND strict format', solution: 'RAG + SFT paired; eval covers both axes' },
      { case: 'Stakeholder demands FT but you have 200 examples', solution: 'Show the decision matrix; recommend RAG + better prompts' },
      { case: 'Knowledge changes daily', solution: 'RAG only; FT will be stale within a week' },
    ],
    failureModes: [
      { mode: 'FT chosen, knowledge stale within month', detect: 'Eval drift on factual benchmark', recover: 'Add RAG layer; retrain less often' },
      { mode: 'RAG chosen, format inconsistent', detect: 'User complaints; format-compliance metric', recover: 'Add SFT; combined eval' },
    ],
    monitoring: ['Eval scores per axis (retrieval, format, factual)', 'Per-decision audit trail', 'Cost per inference comparison'],
    testing: ['Pre-build audit drill', 'Combined RAG + FT eval', 'Cost simulation per choice'],
    security: ['Decision documented in ADR', 'Per-tenant choice if needed'],
    scaling: ['RAG scales with corpus size', 'FT scales with re-training cadence', 'Combined: dual-axis ops'],
    maturity: {
      mvp: 'Pick one; ship; iterate',
      production: 'Decision matrix + ADR + combined eval',
      enterprise: 'Per-tenant choice + automated drift detection + retraining schedule',
    },
    limitations: [
      'No silver bullet — pairing is more expensive',
      'Decision is reversible but expensive',
    ],
    projectFit: [
      'docs/plans/<feature>.md — ADR per AI build',
      'eval-svc — combined eval pipeline',
      '/admin/architect/deep — system-level decisions',
    ],
    interviewLine: 'RAG = facts; fine-tuning = format. Most production = both. Below 500 examples → don\'t fine-tune. Above 1k → fine-tuning earns its weight.',
    finalScript: 'RAG and fine-tuning answer different questions. Need latest facts or private dynamic data → RAG. Need answer format, tone, or strict policy wording → fine-tuning, with guardrails. Most production systems pair them: a fine-tuned LLM sitting behind a RAG retriever, with output guardrails wrapping the response. The brutal rule: fewer than 500 examples — don\'t fine-tune; improve RAG and prompting first. A thousand to ten thousand high-quality examples — supervised fine-tuning is useful. Lots of raw text but few labels — semi-supervised. Need cheaper or faster inference — fine-tune a smaller model. Document the choice in an ADR before any code lands; mid-build pivots are expensive.',
  },
];

export default function FineTuningDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Fine-Tuning Scenarios — Deep Dive</h1>
        <p className="design-areas-sub">
          Three fine-tuning approaches plus the brutal RAG-vs-fine-tuning decision rule.
          Supervised teaches format. Unsupervised teaches domain language. Semi-supervised
          exploits abundant raw data with scarce labels. Most production = RAG + fine-tuning,
          paired with guardrails.
        </p>
        <p className="design-areas-sub" style={{ fontStyle: 'italic' }}>
          🎯 Below 500 examples — don&apos;t fine-tune; improve RAG. ≥ 1k high-quality —
          SFT earns its weight. ~1k labeled + ~100k raw — semi-supervised. Need fresh
          facts → RAG, not fine-tuning.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
