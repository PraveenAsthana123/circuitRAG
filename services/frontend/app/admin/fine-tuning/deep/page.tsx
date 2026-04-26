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

  // ---- 5. Alignment training (RLHF / DPO / ORPO / KTO / RLAIF) ----
  {
    slug: 'alignment-training',
    title: '5. Alignment training — RLHF / DPO / ORPO / KTO / RLAIF',
    status: 'partial',
    coreConcept: 'Training the model on PREFERENCES rather than ideal-output examples. SFT teaches "the answer should look like X"; alignment teaches "answer A is better than answer B". Required for production-grade quality + safety beyond raw SFT.',
    oneLiner: 'Alignment = preferences over examples. RLHF was the OG; DPO is the cheap modern default; ORPO does SFT+alignment in one pass.',
    businessContext: 'SFT alone produces models that follow format but emit subtly wrong/unsafe answers. Production-quality user-facing AI needs preference-based fine-tuning to lock in nuanced quality + refusal behavior.',
    fiveW: {
      what: 'Family of techniques: RLHF (reward model + PPO), DPO (direct optimization on preference pairs), ORPO (single-stage SFT+alignment), KTO (works with thumbs-up/down), Constitutional AI / RLAIF (AI feedback instead of human).',
      why: 'SFT can\'t express "this answer is better than that one" beyond format. Alignment trains the policy on relative preference, which is what users actually care about.',
      where: 'After SFT in the standard pipeline. Production user-facing models. Refusal training. Safety alignment.',
      when: 'You have preference data (paired comparisons OR thumbs-up/down) AND SFT is no longer the bottleneck.',
      who: 'AI/ML team owns. Safety team co-owns refusal training. Product owns the preference-collection UX.',
    },
    interview30s: 'Alignment training is the step after SFT. Instead of (input, ideal-output) pairs, you train on preference pairs — "answer A is better than answer B". RLHF was the original (Anthropic, OpenAI) — train a reward model, then use PPO. DPO is the modern default — directly optimizes on preference pairs without a separate reward model, half the ops complexity. ORPO does SFT + alignment in one stage. KTO works with thumbs-up/down (no pairs needed). RLAIF replaces human feedback with AI critique — scales without human bottleneck. The non-negotiable test is a held-out preference benchmark.',
    coreBuildingBlocks: [
      'Preference dataset — pairs (chosen, rejected) OR thumbs (up/down)',
      'Reward model (RLHF only) — trained on pairs to score outputs',
      'PPO trainer (RLHF) OR direct optimization (DPO/ORPO/KTO)',
      'Reference model — KL-divergence anchor (prevents collapse)',
      'Eval — held-out preference benchmark + general-quality benchmarks',
      'Constitutional rules (RLAIF) — written principles AI applies',
    ],
    flowchart: `flowchart LR
  SFT[SFT model] --> P[Preference data]
  P --> M{Method}
  M -->|RLHF| RM[Train reward model]
  RM --> PPO[PPO with KL anchor]
  M -->|DPO| DPO[Direct preference optimization]
  M -->|ORPO| ORPO[Single-stage SFT plus align]
  M -->|KTO| KTO[Thumbs up or down loss]
  M -->|RLAIF| RLAIF[AI critique loop]
  PPO --> AL[Aligned model]
  DPO --> AL
  ORPO --> AL
  KTO --> AL
  RLAIF --> AL
  AL --> E[Held-out preference eval]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Sys as Production system
  participant DS as Preference store
  participant TR as Trainer
  U->>Sys: query
  Sys-->>U: 2 candidate answers A B
  U->>Sys: pick A
  Sys->>DS: log A over B
  DS->>TR: batch preference pairs
  TR->>TR: DPO or RLHF training
  TR->>TR: KL divergence anchor
  TR-->>Sys: aligned model v2`,
    coreLayers: [
      { layer: 'Preference collection', responsibility: 'Pairs (chosen, rejected) OR single thumbs. UX in product surfaces preference signal.' },
      { layer: 'Reward / direct loss', responsibility: 'RLHF: reward model + PPO. DPO/ORPO/KTO: direct loss on preferences.' },
      { layer: 'Reference anchor', responsibility: 'KL divergence vs SFT model prevents collapse to short/safe outputs.' },
      { layer: 'Eval', responsibility: 'Held-out preference set + general benchmarks (MMLU, etc) to detect regression.' },
      { layer: 'Refusal training', responsibility: 'Specific subset training the model to refuse unsafe requests.' },
    ],
    problem: 'SFT produces format-correct but quality-mediocre answers. Users prefer one over another for nuanced reasons; SFT can\'t learn that signal.',
    whyThisApproach: 'DPO is half the ops of RLHF with similar gains. ORPO collapses two stages into one. RLAIF removes human bottleneck. Each lets us train on preference cheaply.',
    whenToUse: ['Production user-facing AI', 'Safety / refusal training', 'After SFT plateaus', 'Have preference data (paired or thumbs)'],
    whenNotToUse: ['Pre-SFT', 'No preference data', 'Format-only tasks (SFT suffices)'],
    input: 'SFT model + preference dataset (pairs or thumbs) + KL anchor',
    process: [
      'Collect preference data via product UX OR red-team',
      'Pick method: RLHF (legacy), DPO (default), ORPO (1-stage), KTO (thumbs), RLAIF (AI feedback)',
      'Train with KL anchor to prevent collapse',
      'Eval on held-out preference + general benchmarks',
      'Canary deploy; compare against SFT-only',
    ],
    output: 'Aligned model variant. Higher preference-win-rate + similar/better general quality.',
    alternatives: [
      { name: 'RLHF (PPO)', tradeoff: 'OG; high ops cost; harder to tune; ~2x compute of SFT' },
      { name: 'DPO', tradeoff: 'Modern default; cheaper than RLHF; needs paired preferences' },
      { name: 'ORPO', tradeoff: 'Single stage; saves a training pass; newer (2024)' },
      { name: 'KTO', tradeoff: 'Works with thumbs (no pairs); slightly weaker than DPO' },
      { name: 'RLAIF / Constitutional', tradeoff: 'No human bottleneck; depends on critic LLM quality' },
    ],
    challenges: [
      'Preference collection UX is expensive',
      'Reward hacking (model gaming the metric)',
      'KL collapse (model copies SFT exactly)',
      'Distribution shift from preferences to production',
    ],
    edgeCases: [
      { case: 'Reward model overconfident on adversarial', solution: 'Diverse pref data; eval includes adversarial; KL anchor' },
      { case: 'KTO with imbalanced thumbs', solution: 'Reweight loss; balance positive/negative' },
      { case: 'Constitutional rules conflict', solution: 'Explicit precedence in rule set; ADR per change' },
    ],
    failureModes: [
      { mode: 'Reward hacking', detect: 'Eval gap between reward model and human eval', recover: 'Diversify preferences; constrain via KL' },
      { mode: 'Quality collapse', detect: 'General benchmark regress', recover: 'Lower learning rate; stronger KL anchor' },
      { mode: 'Refusal over-fire', detect: 'False-refusal rate spike', recover: 'Add allowed examples; recalibrate' },
    ],
    monitoring: ['Preference win-rate vs SFT-only', 'False-refusal rate', 'KL divergence from reference', 'General benchmark scores'],
    testing: ['Held-out preference eval', 'Adversarial reward-hacking probe', 'Refusal calibration drill', 'General quality regression'],
    security: ['Preference data audit chain', 'No PII in preferences', 'Per-tenant alignment if needed'],
    scaling: ['DPO ~1.5x SFT compute', 'RLHF ~2-3x', 'Preference collection is the bottleneck (UX investment)'],
    maturity: {
      mvp: 'No alignment; SFT only',
      production: 'DPO + held-out preference eval + refusal training',
      enterprise: 'Multi-stage (SFT → DPO → constitutional) + per-tenant adapters + dashboard',
    },
    limitations: ['Preference quality is the ceiling', 'Reward hacking always possible', 'KL anchor is a heuristic'],
    projectFit: ['eval-svc — preference benchmark', 'governance.preference_log — pairs + thumbs', 'libs/py/documind_core/model_registry.py'],
    interviewLine: 'Alignment trains on preferences. DPO is the modern default. KL anchor prevents collapse. Reward hacking is the always-on risk.',
    finalScript: 'Alignment training is the step after SFT. Instead of teaching format with (input, ideal-output) pairs, you teach preference: answer A is better than answer B. RLHF was the original — train a reward model, then PPO. DPO is the modern default — directly optimize on preference pairs, no separate reward model, half the ops cost. ORPO collapses SFT and alignment into one stage. KTO works with thumbs up/down (no pairs needed). RLAIF replaces human feedback with AI critique to scale beyond human bottleneck. The KL-divergence anchor prevents the model collapsing to short/safe outputs. Eval covers held-out preference plus general benchmarks. Production user-facing models need this; SFT alone is insufficient.',
  },

  // ---- 6. PEFT family ----
  {
    slug: 'peft-techniques',
    title: '6. PEFT — LoRA / QLoRA / DoRA / Adapters / IA3',
    status: 'shipped',
    coreConcept: 'Parameter-efficient fine-tuning trains a tiny adapter (~0.1-1% of base weights) instead of the whole model. Lets us ship per-tenant variants for $10-50 each, compose adapters at serve time, swap out without redeploy.',
    oneLiner: 'PEFT = train tiny adapter, freeze base. LoRA is default; QLoRA cheaper; DoRA newer; per-tenant ships at scale.',
    businessContext: 'Full FT costs $1k-10k per run. Need per-tenant + per-feature variants? PEFT drops that to $10-50 per variant. Suddenly per-customer FT is economically viable.',
    fiveW: {
      what: 'Family of techniques where the base model is frozen and a small set of additional parameters is trained: LoRA (low-rank), QLoRA (4-bit quantized base + LoRA), DoRA (decoupled magnitude+direction), Adapters (Houlsby/Pfeiffer bottleneck), IA3 (vector scaling), Prefix/Prompt tuning (soft prompts).',
      why: '0.1-1% of full FT cost. Adapters compose at serve time (per-tenant + per-feature stack). Swap without redeploy.',
      where: 'Default for SFT/DPO/RAFT in this codebase. Per-tenant variants. Per-feature variants. Cheap experimentation.',
      when: 'Always for SFT/alignment unless you specifically need full FT (rare).',
      who: 'AI/ML team owns adapter training. Platform owns serve-time composition. Each tenant can have its own adapter stack.',
    },
    interview30s: 'PEFT is how you make fine-tuning economically viable at multi-tenant scale. LoRA freezes the base and trains a low-rank adapter — typically 0.1-1% of base parameters. QLoRA quantizes the base to 4-bit so you can train a 70B model on a single GPU. DoRA decouples magnitude and direction, slightly better than LoRA. Adapters are the older bottleneck variant. Per-tenant adapters compose at serve time — base + tenant-A + feature-X. The drill verifies that swapping adapters doesn\'t leak across tenants.',
    coreBuildingBlocks: [
      'LoRA — low-rank decomposition (A * B with rank r=8/16/32)',
      'QLoRA — 4-bit NF4-quantized base + LoRA on top',
      'DoRA — decoupled magnitude + direction; slightly outperforms LoRA',
      'Adapters — Houlsby/Pfeiffer bottleneck layers',
      'IA3 — vector scaling on activations (smaller than LoRA)',
      'Prefix / prompt tuning — soft prompts (cheapest, weakest)',
      'Adapter composition — multiple LoRAs stacked at serve time',
    ],
    flowchart: `flowchart LR
  B[Base model frozen] --> L[Add LoRA adapter rank r]
  L --> T[Train only adapter ~1 pct params]
  T --> S[Save adapter ~10 MB]
  S --> R[Registry per tenant or feature]
  R --> SRV[Serve compose base + adapters]
  SRV --> O[Output]`,
    sequence: `sequenceDiagram
  autonumber
  participant DS as Dataset
  participant TR as LoRA trainer
  participant REG as Adapter registry
  participant SRV as Serve runtime
  DS->>TR: 1k-10k examples + base model
  TR->>TR: freeze base; train LoRA only
  TR->>REG: publish adapter id v1
  SRV->>REG: load base + tenant adapter
  SRV-->>SRV: merge or compose at inference`,
    coreLayers: [
      { layer: 'Base layer', responsibility: 'Frozen pretrained model. Shared across all tenants. Loaded once into GPU memory.' },
      { layer: 'Adapter layer', responsibility: 'Per-tenant or per-feature adapter (~10MB-100MB). Versioned, signed, audit-trailed.' },
      { layer: 'Composition layer', responsibility: 'Serve-time merge: base + adapter1 + adapter2. PEFT library handles math.' },
      { layer: 'Registry layer', responsibility: 'Adapter version + dataset hash + hyperparams. Per-tenant + per-feature.' },
      { layer: 'Eval layer', responsibility: 'Per-adapter held-out eval. Cross-tenant leak drill.' },
    ],
    problem: 'Full fine-tuning costs $1k-10k per run, makes per-tenant variants uneconomic. We need cheap, composable, per-tenant variants.',
    whyThisApproach: 'LoRA: 0.1-1% of full cost. Adapters compose. Quality gap < 5% vs full FT for most tasks.',
    whenToUse: ['SFT cheap variants', 'Per-tenant adapters', 'Per-feature adapters', 'Rapid experimentation', 'Multi-tenant SaaS'],
    whenNotToUse: ['Brand-new domain — full FT may earn its weight', 'Quality gap matters at the margin'],
    input: 'Base model + dataset + PEFT config (rank, alpha, dropout, target modules)',
    process: [
      'Load frozen base; insert LoRA modules at attention + MLP layers',
      'Freeze base parameters; train only adapter weights',
      'Save adapter (~10-100MB) separate from base',
      'Register with version + dataset hash',
      'At serve time: load base once + load adapter per request',
      'Optionally merge adapter into base for inference latency',
    ],
    output: 'Adapter (~10-100MB) + registry entry. Composes with base at serve time.',
    alternatives: [
      { name: 'Full fine-tuning', tradeoff: '$1k-10k per run; no per-tenant economics; better quality on niche tasks' },
      { name: 'LoRA (default)', tradeoff: 'Cheap; composable; ~5% quality gap on hardest tasks' },
      { name: 'QLoRA', tradeoff: 'Even cheaper (4-bit base); slight quality hit; can train 70B on 1 GPU' },
      { name: 'DoRA', tradeoff: 'Newer; slightly better than LoRA; less ecosystem maturity' },
      { name: 'Prompt tuning', tradeoff: 'Cheapest; weakest quality; soft-prompt-only' },
    ],
    challenges: ['Hyperparam tuning (rank, alpha, dropout)', 'Adapter composition correctness', 'Serve-time latency overhead', 'Cross-tenant leak via shared base'],
    edgeCases: [
      { case: 'Adapter rank too low → underfit', solution: 'Increase rank from 8 → 16 → 32; reeval' },
      { case: 'Adapter merged into wrong base', solution: 'Pin (base_version, adapter_version) tuple; verify at load' },
      { case: 'Two adapters conflict at composition', solution: 'Test composed eval; weight per adapter' },
    ],
    failureModes: [
      { mode: 'Adapter trained on wrong base', detect: 'Eval scores collapse', recover: 'Recheck base hash; retrain' },
      { mode: 'Cross-tenant adapter leak', detect: 'Drill: tenant-A adapter applied to tenant-B query', recover: 'Per-request adapter selection enforced; audit log' },
      { mode: 'Quality drift over rank', detect: 'Eval per rank value', recover: 'Search rank space; pick best for task' },
    ],
    monitoring: ['Adapter eval scores per version', 'Serve-time composition latency', 'Adapter swap rate', 'Cross-tenant audit'],
    testing: ['Per-adapter held-out eval', 'Composed-adapter eval', 'Cross-tenant leak drill', 'Latency benchmarks per composition'],
    security: ['Adapter signed at registry', 'Per-request adapter selection enforced', 'Tenant_id required in serve API'],
    scaling: ['Base loaded once shared', 'Adapters loaded per-request from registry cache', '70B model + LoRA fits on 1 H100 with QLoRA'],
    maturity: {
      mvp: 'Single LoRA per fine-tune; manual deploy',
      production: 'Per-tenant adapters + registry + per-request selection + drill',
      enterprise: 'Adapter composition + federated training + per-feature stack + dashboard',
    },
    limitations: ['~5% quality gap on hardest tasks', 'Composition latency overhead', 'Hyperparam space large'],
    projectFit: ['libs/py/documind_core/peft_loader.py', 'inference-svc — per-request adapter selection', 'mcp/tests/drill_lora_*.py'],
    interviewLine: 'PEFT is how you make per-tenant fine-tuning viable. LoRA is default. QLoRA cheaper. Per-tenant adapters compose at serve time. Cross-tenant drill non-negotiable.',
    finalScript: 'PEFT — parameter-efficient fine-tuning — is the technique that makes per-tenant fine-tuning economically viable. LoRA freezes the base model and trains a low-rank adapter, typically 0.1 to 1 percent of base parameters. QLoRA quantizes the base to 4-bit so you can train a 70-billion-parameter model on a single H100. DoRA decouples magnitude and direction for a small quality lift over LoRA. Adapters compose at serve time: base plus tenant-A plus feature-X. The cost is around $10 to $50 per adapter run versus $1k-10k for full FT. Quality gap is typically under 5%. The drill that gates this is cross-tenant leak — adapter trained on tenant A must never apply to tenant B query. Per-request adapter selection enforced at the serve layer.',
  },

  // ---- 7. RAFT ----
  {
    slug: 'raft-retrieval-augmented-ft',
    title: '7. RAFT — Retrieval-Augmented Fine-Tuning',
    status: 'partial',
    coreConcept: 'Train the model to USE retrieved chunks correctly — cite them, ignore distractors, refuse when context is insufficient. Closes the gap between RAG retrieval quality and grounded answer quality.',
    oneLiner: 'RAFT = teach the model how to use RAG. Cite the right chunks; ignore distractors; refuse when context is empty.',
    businessContext: 'Plain SFT teaches format. Plain RAG retrieves chunks. RAFT teaches the model to actually USE the chunks correctly — the missing link that lifts grounded-answer quality 10-20%.',
    fiveW: {
      what: 'Fine-tuning regime where each training example includes (query, K retrieved chunks where some are gold and some are distractors, gold answer with citations). Teaches the model to cite, ignore noise, and refuse on empty context.',
      why: 'Models trained without RAFT often "hallucinate around" retrieved content or cite the wrong chunk. RAFT explicitly trains the use-retrieval behavior.',
      where: 'After SFT/DPO. Specifically for grounded RAG systems. Most enterprise RAG quality wins come from RAFT-style training.',
      when: 'You have RAG retrieval working AND want quality lift on grounded answers. Have a corpus + query/answer set.',
      who: 'AI/ML team owns RAFT training. Retrieval team owns chunk-quality eval. Combined eval covers both axes.',
    },
    interview30s: 'RAFT is fine-tuning specifically for RAG. Each training example includes the query plus K retrieved chunks — some gold, some distractors — plus the gold answer with citations. The model learns three things: cite the right chunks, ignore distractors, refuse when context is insufficient. It\'s the missing link between SFT (format) and RAG (retrieval). Production RAG quality typically lifts 10-20% with RAFT. The eval covers retrieval quality + answer accuracy + citation correctness.',
    coreBuildingBlocks: [
      'Training set — (query, K chunks mix gold + distractor, gold answer with cite-anchors)',
      'Distractor sampling — random irrelevant chunks per query',
      'Citation format — explicit chunk IDs in answer',
      'Refusal data — queries with empty/irrelevant context expect refusal',
      'Eval — retrieval quality + answer accuracy + citation accuracy',
    ],
    flowchart: `flowchart LR
  Q[Query] --> R[Retrieve K chunks]
  R --> M[Mix gold and distractor]
  M --> P[Prompt + chunks]
  P --> LLM[Train LLM]
  LLM --> A[Answer with citations]
  A --> E{Eval}
  E -->|cite right| OK[Reward]
  E -->|cite wrong| BAD[Penalize]
  E -->|use distractor| BAD
  E -->|refuse on empty| OK`,
    sequence: `sequenceDiagram
  autonumber
  participant DS as Dataset builder
  participant Ret as Retriever
  participant TR as Trainer
  DS->>Ret: query Q
  Ret-->>DS: chunks gold
  DS->>DS: add random distractors
  DS->>TR: query + chunks + gold answer with cites
  TR->>TR: train cite + ignore + refuse
  TR-->>TR: eval citation accuracy`,
    coreLayers: [
      { layer: 'Distractor mining', responsibility: 'Add irrelevant chunks per query so model learns to filter.' },
      { layer: 'Citation format', responsibility: 'Explicit chunk IDs (or doc:page) the model must emit alongside the answer.' },
      { layer: 'Refusal corpus', responsibility: 'Queries with no/poor context expect "I don\'t have enough information" refusal.' },
      { layer: 'Eval layer', responsibility: 'Citation accuracy + answer accuracy + refusal calibration. Combined RAG eval.' },
    ],
    problem: 'SFT models hallucinate around retrieved context or cite wrong chunks. Pure RAG without RAFT gets ~70% citation accuracy.',
    whyThisApproach: 'Explicitly trains the use-retrieval behavior the production system needs. 10-20% quality lift typical.',
    whenToUse: ['Grounded RAG production', 'Citation-required answers', 'Compliance / audit needing source traceability', 'Have a query/answer corpus'],
    whenNotToUse: ['Pure generative tasks', 'Knowledge-injection-only FT', 'No retrieval pipeline yet'],
    input: '(query, retrieved chunks, gold answer with cite anchors) examples + retrieval pipeline',
    process: [
      'Build (query, top-K chunks, gold answer) dataset; chunks = gold ∪ distractors',
      'Format prompt: query + numbered chunks + answer-with-cites template',
      'Fine-tune with cross-entropy on the gold answer',
      'Add refusal examples: empty/irrelevant context → "I don\'t have enough info"',
      'Eval: citation accuracy + answer accuracy + refusal calibration',
      'Canary deploy; compare against pure-RAG-on-SFT',
    ],
    output: 'RAFT-trained model. Cites correct chunks. Ignores distractors. Refuses on empty context.',
    alternatives: [
      { name: 'Plain SFT + RAG', tradeoff: 'Cheaper; weaker citation accuracy; hallucinates around chunks' },
      { name: 'Long-context FT (no retrieval)', tradeoff: 'Simpler; expensive at serve; misses fresh data' },
      { name: 'Retrieval-only no FT', tradeoff: 'Cheapest; weakest grounded quality; format drift' },
    ],
    challenges: [
      'Distractor quality (too easy = no signal; too hard = noise)',
      'Citation format consistency',
      'Refusal calibration (over-refuse vs under-refuse)',
      'Eval ground truth (citation correctness is hard to measure)',
    ],
    edgeCases: [
      { case: 'Gold chunk is borderline relevant', solution: 'Multi-annotator review; reject ambiguous' },
      { case: 'Model cites distractor', solution: 'Penalize in loss; increase distractor count in training' },
      { case: 'Refusal on actually-answerable query', solution: 'Recalibrate refusal threshold; review false-refuse cases' },
    ],
    failureModes: [
      { mode: 'Citation accuracy regresses', detect: 'Eval citation-accuracy metric drops', recover: 'Re-train with stricter distractor mining' },
      { mode: 'Over-refusal', detect: 'False-refuse rate spike', recover: 'Add allowed examples; reduce refusal weight' },
      { mode: 'Distribution drift from production', detect: 'Production vs eval gap widens', recover: 'Sample production queries for eval refresh' },
    ],
    monitoring: ['Citation accuracy', 'False-refuse rate', 'Hallucination rate (vs RAFT-eval)', 'Per-tenant accuracy'],
    testing: ['Drill: distractor injection → ignored', 'Drill: empty context → refused', 'Drill: gold answer cited correctly', 'Combined RAG + RAFT eval'],
    security: ['No PII in distractor corpus', 'Citation linker validated', 'Tenant scope on training data'],
    scaling: ['Compute parity with SFT', 'Distractor sampling fast (random from corpus)', 'Eval loop expensive (combined RAG + answer + cite)'],
    maturity: {
      mvp: 'Plain SFT + RAG',
      production: 'RAFT + citation eval + refusal calibration + drill',
      enterprise: 'Per-tenant RAFT + automated distractor mining + citation linker dashboard',
    },
    limitations: ['Distractor quality bounds gain', 'Citation eval is hard', 'Doesn\'t replace good retrieval'],
    projectFit: [
      'eval-svc — citation accuracy + answer accuracy + refusal',
      'retrieval-svc — RAG pipeline that feeds RAFT training',
      '/admin/rag/deep#post-retrieval — citation linker',
    ],
    interviewLine: 'RAFT teaches the model to USE RAG correctly — cite the right chunks, ignore distractors, refuse on empty context. The missing link between SFT and pure RAG.',
    finalScript: 'RAFT — Retrieval-Augmented Fine-Tuning — is the missing link between SFT and pure RAG. Each training example is a query plus K retrieved chunks (some gold, some distractors) plus the gold answer with explicit chunk citations. The model learns three things at once: cite the right chunks, ignore distractors, refuse when the context is insufficient. Pure SFT plus RAG gets around 70% citation accuracy in production; RAFT typically lifts that to 90%+. The eval covers citation accuracy, answer accuracy, and refusal calibration. The non-negotiable test is a distractor-injection drill: add a chunk that mentions the right entity but the wrong fact, and verify the model still cites the gold chunk.',
  },

  // ---- 8. Tool-use / function-calling FT ----
  {
    slug: 'tool-use-fine-tuning',
    title: '8. Tool-use / function-calling fine-tuning',
    status: 'partial',
    coreConcept: 'Train the model to emit structured tool calls (JSON, schema-validated) instead of free text. Required prerequisite for any agent system — prevents the model from hallucinating fake API calls.',
    oneLiner: 'Tool-use FT = teach the model when + how + with what args to call a tool. Required for agents.',
    businessContext: 'Multi-agent systems (OpenClaw workers) need the LLM to emit valid tool calls. Without tool-use FT the model hallucinates function names and arg shapes — every call fails validation.',
    fiveW: {
      what: 'Fine-tuning regime where examples are (user query, available tool schemas, ground-truth tool call OR direct answer). Teaches the model to pick the right tool, fill args correctly, and answer directly when no tool is needed.',
      why: 'Base models inconsistently emit tool calls. Production agents need >95% schema-valid call rate to be usable.',
      where: 'After SFT. Required before deploying OpenClaw-style worker agents. Per-feature tool registry.',
      when: 'Building agents OR exposing function-calling to users. Need per-tenant or per-feature tool sets.',
      who: 'AI/ML team owns training. Tool registry team owns schemas. Each tool feature defines positive + negative examples.',
    },
    interview30s: 'Tool-use fine-tuning teaches the model to emit valid function calls. Each example is a user query, a list of available tool schemas (in JSON or OpenAPI), and either a ground-truth tool call with args OR a direct answer. The model learns when to call a tool, which one, with what arguments, AND when to skip and answer directly. Production agents need >95% schema-valid call rate; without tool-use FT, base models hallucinate function names. The drill validates every call against the schema before execution.',
    coreBuildingBlocks: [
      'Tool registry — declared tools with input/output schemas',
      'Training data — (query, available tools, gold call OR direct answer)',
      'Negative examples — query that should NOT trigger a tool',
      'Multi-tool examples — query that needs N tools chained',
      'Refusal — query unauthorized for available tools',
      'Schema validator — enforces call shape before execution',
    ],
    flowchart: `flowchart LR
  Q[User query] --> M[Model]
  T[Tool registry] --> M
  M --> D{Decision}
  D -->|tool call| C[JSON call with args]
  D -->|direct answer| A[Plain text]
  D -->|refuse| R[Refusal]
  C --> V{Schema valid}
  V -->|yes| EX[Execute tool]
  V -->|no| BLK[Block plus log]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant LLM as LLM
  participant V as Schema validator
  participant T as Tool runtime
  U->>LLM: query plus available tools
  LLM-->>LLM: emit tool call JSON
  LLM->>V: validate
  alt valid
    V->>T: execute
    T-->>LLM: result
    LLM-->>U: final answer
  else invalid
    V-->>LLM: error
    LLM-->>U: refusal or retry
  end`,
    coreLayers: [
      { layer: 'Tool registry', responsibility: 'Declared tools with JSON Schema for input + output. Per-tenant + per-feature.' },
      { layer: 'Training data', responsibility: '(query, tools, gold call OR answer OR refusal). Balanced across positive + negative.' },
      { layer: 'Validator', responsibility: 'Schema-validates every emitted call before execution. Reject malformed.' },
      { layer: 'Multi-tool layer', responsibility: 'Examples with chained tool calls; teaches sequencing.' },
      { layer: 'Refusal layer', responsibility: 'Examples for queries the model lacks tools for; teaches honest refusal.' },
    ],
    problem: 'Base models hallucinate tool names + arg shapes. Agents fail to execute. Wrong tool called = wrong action.',
    whyThisApproach: 'Direct supervision on (query, tool call) pairs gives the model the exact shape needed. Schema validation gates enforces it.',
    whenToUse: ['Agent systems (OpenClaw)', 'Function-calling user features', 'Per-tenant tool registries', 'Multi-step orchestration'],
    whenNotToUse: ['Pure Q&A no tools', 'Read-only summarization', 'Chat without action authority'],
    input: 'Tool registry + training set (query + available tools + gold output)',
    process: [
      'Curate tool registry with JSON schemas',
      'Build training examples: balanced across (call, direct answer, refusal)',
      'Include multi-tool sequences',
      'Train via SFT with structured-output loss',
      'Validate all emitted calls against schema',
      'Eval: call-validity rate + correctness + refusal calibration',
    ],
    output: 'Tool-use-tuned model. >95% schema-valid call rate. Correct tool selection.',
    alternatives: [
      { name: 'Prompt-based tool use', tradeoff: 'No FT; base-model dependent; ~70-85% valid rate' },
      { name: 'Constrained decoding (JSON mode)', tradeoff: 'Forces valid JSON; doesn\'t teach correct tool choice' },
      { name: 'Function-calling API (OpenAI)', tradeoff: 'Vendor lock; works out-of-box; cost per call' },
    ],
    challenges: [
      'Tool registry drift (schema changes break trained model)',
      'Tool selection under ambiguous queries',
      'Multi-tool sequencing',
      'Negative examples (when NOT to call a tool)',
    ],
    edgeCases: [
      { case: 'Two valid tools for same query', solution: 'Train preference; eval-tested decision' },
      { case: 'Schema field added after training', solution: 'Re-train OR fall back to "default" arg' },
      { case: 'Model emits tool call when query forbids', solution: 'Refusal training + per-call OPA gate' },
    ],
    failureModes: [
      { mode: 'Schema-invalid call rate spikes', detect: 'Validator rejection rate > 5%', recover: 'Re-train with current schemas' },
      { mode: 'Wrong tool selected', detect: 'Per-tool accuracy benchmark drops', recover: 'Add disambiguating examples; retrain' },
      { mode: 'Tool injection attack', detect: 'Calls outside registry', recover: 'OPA layer enforces allowlist; alert' },
    ],
    monitoring: ['Schema-valid call rate', 'Per-tool accuracy', 'Refusal calibration', 'Multi-tool sequence success rate'],
    testing: ['Drill: every emitted call schema-valid', 'Drill: tool-injection rejected', 'Drill: refusal on unauthorized', 'Eval: per-tool accuracy'],
    security: ['Schema validation pre-execution', 'OPA per-tool policy gate', 'Per-tenant tool registry'],
    scaling: ['Tool registry cached in Redis', 'Schema validation O(1) per call', 'Adapter per per-tenant tool set'],
    maturity: {
      mvp: 'Prompt-based tools only',
      production: 'Tool-use FT + schema validator + per-tool eval + drill',
      enterprise: 'Per-tenant tool registries + automated schema-drift detection + adapter composition',
    },
    limitations: ['Schema drift breaks trained model', 'Multi-tool sequencing has training-data sparsity', 'Quality bounded by tool-call examples'],
    projectFit: ['/admin/ai-orchestration/deep — OpenClaw uses this', '/admin/mcp/deep — MCPClient enforces schema', 'libs/py/documind_core/tools.py'],
    interviewLine: 'Tool-use FT teaches the model to emit valid tool calls. Required prerequisite for agents. Schema validation gates execution.',
    finalScript: 'Tool-use fine-tuning teaches the model to emit structured function calls. Each training example is a user query, the list of available tool schemas, and either a ground-truth tool call with arguments, a direct text answer, or a refusal. The model learns four things: when to call a tool, which one, with what arguments, and when to skip and answer directly. Production agents need above 95% schema-valid call rate to be usable; without tool-use FT, base models hallucinate function names and argument shapes. The schema validator gates execution — every emitted call must validate before it runs. Drills cover validity, tool-injection rejection, and refusal calibration. Required prerequisite for any OpenClaw-style worker agent.',
  },

  // ---- 9. Knowledge distillation ----
  {
    slug: 'knowledge-distillation',
    title: '9. Knowledge distillation — teacher → student',
    status: 'partial',
    coreConcept: 'Train a small "student" model to mimic a large "teacher" model\'s outputs. Captures most of the teacher\'s capability at a fraction of the inference cost. The FinOps lever for AI.',
    oneLiner: 'Distillation = train small model to copy big model. 80% quality at 10-20% cost.',
    businessContext: 'Production AI inference cost dominates AI budgets. A 70B teacher costs ~10x a 7B student per token. Distillation captures most of the quality at a fraction of the cost — the single biggest FinOps lever.',
    fiveW: {
      what: 'Train a smaller student model on (input, teacher-output) pairs OR (input, teacher-token-distribution) pairs. Student learns to mimic teacher behavior at lower compute.',
      why: 'Production token cost dominates. Switching from 70B to 7B saves 80-90% on inference. Quality gap typically 5-15%.',
      where: 'Production inference path. Replace teacher with student behind the same API surface.',
      when: 'Have a quality-sufficient teacher and inference cost is the bottleneck.',
      who: 'AI/ML team owns distillation. FinOps team consumes the cost reduction. SRE team owns the swap.',
    },
    interview30s: 'Knowledge distillation trains a small student model to mimic a large teacher. Two flavors: response distillation, where the student learns from the teacher\'s final outputs, and logit distillation, where the student matches the teacher\'s next-token probability distribution. Logit is higher quality but needs teacher access at training time. Typical: 70B teacher → 7B student, 80% quality at 10-20% inference cost. The drill compares student vs teacher on a held-out eval; if quality gap > 15%, increase student size or distillation data volume.',
    coreBuildingBlocks: [
      'Teacher model — large, high-quality',
      'Student model — smaller (target inference cost)',
      'Distillation dataset — (input, teacher-output) OR (input, teacher-logits)',
      'Loss — cross-entropy on response OR KL-divergence on logits',
      'Eval — student vs teacher gap on held-out set',
      'Cost dashboard — token cost before/after distillation',
    ],
    flowchart: `flowchart LR
  T[Teacher 70B] --> G[Generate over corpus]
  G --> D[Distillation dataset]
  S[Student 7B] --> TR[Train on dataset]
  D --> TR
  TR --> SE[Eval student vs teacher]
  SE -->|gap < 15 pct| OK[Deploy student]
  SE -->|gap > 15 pct| MORE[More data or larger student]`,
    sequence: `sequenceDiagram
  autonumber
  participant T as Teacher 70B
  participant DS as Distillation set
  participant TR as Trainer
  participant S as Student 7B
  participant E as Eval
  T->>DS: generate over input corpus
  DS->>TR: input plus teacher output pairs
  TR->>S: train on dataset
  TR->>E: eval student vs teacher
  E-->>TR: quality gap percent`,
    coreLayers: [
      { layer: 'Teacher', responsibility: 'Source of truth model. Frozen during distillation. Cost not in critical path.' },
      { layer: 'Distillation set', responsibility: 'Generated by teacher over input corpus. Quality of inputs matters.' },
      { layer: 'Student', responsibility: 'Target model. Smaller; cheaper to serve.' },
      { layer: 'Loss', responsibility: 'Response distillation (CE on text) OR logit distillation (KL on probabilities).' },
      { layer: 'Eval', responsibility: 'Held-out gap measurement. Gates deploy.' },
    ],
    problem: 'Production token cost dominates AI budgets. Teacher quality is needed but teacher inference cost is prohibitive.',
    whyThisApproach: 'Student inherits most of teacher\'s capability at fraction of cost. Drop-in API replacement once trained.',
    whenToUse: ['Inference cost is the bottleneck', 'Teacher quality is sufficient', 'Production traffic > some threshold (offsets training cost)'],
    whenNotToUse: ['Quality is the bottleneck', 'Teacher itself is not yet good enough', 'Traffic too low to justify training'],
    input: 'Teacher model + student architecture + input corpus',
    process: [
      'Generate distillation dataset by running teacher over input corpus',
      'Train student on (input, teacher-output) OR (input, teacher-logits)',
      'Eval student vs teacher on held-out set',
      'If gap < tolerance: canary deploy student',
      'Compare cost + quality in production; full rollout',
    ],
    output: 'Smaller student model + cost reduction. Quality gap < N% per held-out eval.',
    alternatives: [
      { name: 'Use smaller base directly', tradeoff: 'Cheaper to start; lower quality than distilled student' },
      { name: 'Quantize teacher (INT8/INT4)', tradeoff: 'Cheaper; doesn\'t reduce parameter count; modest savings' },
      { name: 'Speculative decoding', tradeoff: 'Keeps teacher quality; small student helps; complex' },
    ],
    challenges: [
      'Teacher generation cost during distillation',
      'Distribution coverage of distillation corpus',
      'Quality gap unpredictable for niche queries',
      'Student-API compatibility (token-by-token vs response)',
    ],
    edgeCases: [
      { case: 'Teacher refuses on adversarial; student doesn\'t', solution: 'Mix refusal-distillation examples; recalibrate' },
      { case: 'Student smaller than typical → quality collapses', solution: 'Increase student size OR distillation data volume' },
      { case: 'Distillation corpus skewed', solution: 'Stratified sampling across query types + tenants' },
    ],
    failureModes: [
      { mode: 'Quality gap exceeds tolerance', detect: 'Eval drops below baseline', recover: 'More data + larger student; revisit student architecture' },
      { mode: 'Cost reduction less than expected', detect: 'Production token cost only marginally lower', recover: 'Check student-vs-teacher param ratio; consider further compression' },
      { mode: 'Latency regression on student', detect: 'p99 spikes', recover: 'Compile + quantize student; serving optimization' },
    ],
    monitoring: ['Student vs teacher quality gap', 'Token cost per inference', 'Latency p95/p99', 'Per-tenant quality (sampled)'],
    testing: ['Held-out eval per student version', 'Per-task quality benchmark', 'Cost regression test', 'Latency benchmark'],
    security: ['Distillation corpus PII redacted', 'Student model registry signed', 'Teacher access controlled'],
    scaling: ['Distillation cost ~teacher inference over corpus', 'Student deploys cheaper than teacher', 'Per-tenant student variants viable'],
    maturity: {
      mvp: 'Single student variant',
      production: 'Distillation pipeline + held-out eval + canary + cost dashboard',
      enterprise: 'Per-domain students + automated re-distillation when teacher updates + dashboard',
    },
    limitations: ['Quality gap is irreducible; bounded by student size', 'Distillation corpus coverage matters', 'Student misses teacher\'s edge-case behavior'],
    projectFit: [
      '/admin/llmops/deep#deployment — model deployment pipeline',
      'libs/py/documind_core/model_registry.py',
      'eval-svc — student vs teacher gap',
    ],
    interviewLine: 'Distillation is the FinOps lever — small student mimics big teacher. 80% quality at 10-20% cost. Held-out eval gates the deploy.',
    finalScript: 'Knowledge distillation is the largest single FinOps lever in production AI. Train a small student model to mimic a large teacher. Two flavors: response distillation, where the student learns from the teacher\'s text outputs, and logit distillation, where the student matches the teacher\'s next-token probability distribution. Logit is higher quality but requires teacher access at training time. Typical result: a 70-billion teacher distills to a 7-billion student at around 80% quality and 10-20% inference cost. Production traffic above some threshold justifies the training investment. The drill compares student to teacher on a held-out eval; if the gap exceeds tolerance, increase distillation data volume or student size. Per-domain students let us serve customized variants without retraining the teacher.',
  },

  // ---- 10. Full fine-tuning ----
  {
    slug: 'full-fine-tuning',
    title: '10. Full fine-tuning — every parameter updates',
    status: 'partial',
    coreConcept: 'Update ALL base-model parameters during training. Maximum quality ceiling, maximum cost. Used when PEFT (LoRA family) hits a quality wall and the budget justifies full GPU time.',
    oneLiner: 'Full FT = every weight updates. Highest quality, highest cost. Use only when PEFT plateaus.',
    businessContext: 'PEFT covers ~95% of production fine-tuning needs at 1-5% of the cost. Full FT is reserved for cases where the last 5% of quality is worth the 100x cost — typically a base model rebuild or a niche-domain rewrite.',
    fiveW: {
      what: 'Train the full transformer parameter set (billions of weights) on a fine-tuning dataset. Cross-entropy loss; standard backprop; no frozen layers.',
      why: 'PEFT (LoRA) caps at ~95% of full-FT quality on most tasks. The remaining gap matters for some cases: foundational rebuilds, deep domain adaptation, capability injection.',
      where: 'Pretraining base + instruct rebuild. Niche-domain models (medical, legal, security). Foundation-model providers, not most enterprise teams.',
      when: 'PEFT plateau measured + remaining gap matters + budget approved. Almost never the default in 2025+.',
      who: 'AI/ML team OR foundation-model vendor. Requires GPU cluster (A100/H100 × N). Multi-day training runs.',
    },
    interview30s: 'Full fine-tuning updates every base-model parameter. The ceiling is higher than PEFT but the cost is 100x. In 2025 most teams default to LoRA/QLoRA — the quality gap is under 5% on most tasks. Full FT is reserved for cases where that gap matters: foundational base rebuild, niche-domain rewrites, capability injection. The brutal rule: don\'t full-FT until you\'ve measured a PEFT plateau and the gap is worth the cost. Per-tenant full-FT is almost never economic.',
    coreBuildingBlocks: [
      'Training cluster — A100/H100 × N (≥8 for 7B; ≥64 for 70B)',
      'Distributed training — DeepSpeed / FSDP for sharding',
      'Mixed precision — bfloat16 or fp16',
      'Checkpointing — every N steps; resumable',
      'Eval — full benchmark suite, not just task-specific',
      'Cost tracking — GPU-hours + electricity + storage',
    ],
    flowchart: `flowchart LR
  M[Base 7B-70B] --> S[Distributed shard FSDP DeepSpeed]
  S --> T[Train all params + dataset]
  T --> CK[Checkpoint every N steps]
  CK --> E[Full benchmark eval]
  E -->|plateau| ST[Stop]
  E -->|quality up| CONT[Continue]
  CONT --> T
  ST --> REG[Registry signed]`,
    sequence: `sequenceDiagram
  autonumber
  participant DS as Dataset
  participant TR as Trainer
  participant CL as Cluster
  participant CK as Checkpoint
  participant E as Eval
  DS->>TR: dataset 100k-1M examples
  TR->>CL: shard model across GPUs
  loop training steps
    TR->>TR: forward backward
    TR->>CK: every N steps
  end
  TR->>E: full benchmark
  E-->>TR: scores`,
    coreLayers: [
      { layer: 'Compute layer', responsibility: '≥8 H100 for 7B; ≥64 for 70B. Multi-day runs typical.' },
      { layer: 'Sharding layer', responsibility: 'FSDP / DeepSpeed-Zero3. Data + parameter parallelism.' },
      { layer: 'Optimization layer', responsibility: 'AdamW typically. Mixed precision. Gradient checkpointing for memory.' },
      { layer: 'Eval layer', responsibility: 'Full benchmark suite — task + general benchmarks. Detect catastrophic forgetting.' },
      { layer: 'Cost layer', responsibility: 'Track GPU-hours + storage + bandwidth. Justify before run.' },
    ],
    problem: 'PEFT (LoRA) caps at ~95% of full-FT quality. The remaining gap matters for some specific cases.',
    whyThisApproach: 'Maximum quality ceiling. Required for foundational rebuilds and niche-domain rewrites. Necessary when adapter expressivity isn\'t enough.',
    whenToUse: [
      'PEFT plateau measured AND remaining gap > 5% AND budget justifies',
      'Foundational rebuild (instruct-tuning a fresh base)',
      'Niche-domain rewrite (medical, legal — sometimes)',
      'Capability injection (long-context, multimodal)',
    ],
    whenNotToUse: [
      'Default for any production task — PEFT first',
      'Per-tenant variants — uneconomic',
      'Iterating on prompts / data — too slow + costly',
      'Quality already good enough — diminishing returns',
    ],
    input: 'Base model + dataset (100k-1M+ examples) + GPU cluster + days of compute',
    process: [
      'Justify cost via PEFT plateau measurement',
      'Provision GPU cluster (≥8 H100 for 7B)',
      'Shard via DeepSpeed-Zero3 / FSDP',
      'Train with mixed-precision + gradient checkpointing',
      'Checkpoint every N steps',
      'Eval full benchmark suite',
      'Compare quality + cost vs PEFT baseline',
      'If justified: register; if not: rollback to PEFT',
    ],
    output: 'Fully fine-tuned model variant. Tracked GPU-hours + dataset hash + benchmark scores.',
    alternatives: [
      { name: 'LoRA (PEFT default)', tradeoff: '100x cheaper; ~5% quality gap on hardest tasks' },
      { name: 'QLoRA', tradeoff: 'Even cheaper than LoRA; slight quality hit; 70B on 1 GPU' },
      { name: 'Continued pretraining (unsupervised)', tradeoff: 'Cheaper than full SFT; teaches vocab not format' },
      { name: 'Distillation from a larger model', tradeoff: 'Avoid full-FT entirely; small student inherits big teacher' },
    ],
    challenges: [
      'GPU cost prohibitive for most teams',
      'Catastrophic forgetting on out-of-distribution',
      'Distributed training infrastructure',
      'Reproducibility across cluster topology',
      'Eval cost dominates iteration',
    ],
    edgeCases: [
      { case: 'OOM mid-training', solution: 'Gradient checkpointing; lower batch size; shard more aggressively' },
      { case: 'Catastrophic forgetting on general benchmarks', solution: 'Mix 5-10% general data; lower learning rate' },
      { case: 'Run interrupted at hour 36 of 72', solution: 'Resume from checkpoint; never restart from scratch' },
      { case: 'Quality matches PEFT baseline', solution: 'Roll back to PEFT; document cost-no-justified ADR' },
    ],
    failureModes: [
      { mode: 'Quality regresses on general benchmarks', detect: 'MMLU / TruthfulQA drop', recover: 'Mix general data; lower learning rate; partial rollback' },
      { mode: 'GPU node failure mid-run', detect: 'Cluster monitor alert', recover: 'Resume from checkpoint; replace node' },
      { mode: 'Budget overrun', detect: 'GPU-hour tracker exceeds estimate', recover: 'Stop early; eval current checkpoint; decide' },
    ],
    monitoring: ['GPU utilization', 'Loss curve', 'Eval scores per checkpoint', 'GPU-hour cost tracker'],
    testing: ['Full benchmark suite per checkpoint', 'Catastrophic-forgetting probes', 'Cost-vs-PEFT comparison', 'Resumability drill'],
    security: ['Dataset audit chain', 'Model registry signed', 'GPU cluster access controlled'],
    scaling: ['7B: ~$1k-5k per run on 8x H100 (1-2 days)', '70B: ~$50k-200k per run on 64x H100 (3-7 days)', 'Most enterprise teams use cloud spot for ~50% savings'],
    maturity: {
      mvp: 'Almost always inappropriate at MVP — use LoRA',
      production: 'Reserved for foundational rebuilds; ADR justified',
      enterprise: 'Foundation-model providers OR niche-domain specialists',
    },
    limitations: [
      'Cost scales with parameter count',
      'Catastrophic forgetting is real',
      'Reproducibility hard across cluster topology',
      'Almost never the right default in 2025+',
    ],
    projectFit: [
      'libs/py/documind_core/model_registry.py — registry-side identical to PEFT',
      'eval-svc — full benchmark suite required',
      '/admin/fine-tuning/deep#peft-techniques — the cheaper default',
    ],
    interviewLine: 'Full FT is the maximum-quality, maximum-cost option. Reserved for foundational rebuilds. PEFT is default in 2025; full FT only after PEFT plateau measured.',
    finalScript: 'Full fine-tuning updates every base-model parameter — no frozen layers, no adapters. The quality ceiling is higher than PEFT but the cost is roughly 100x: a 7B model takes 8 H100s for 1-2 days; a 70B model takes 64 H100s for 3-7 days. In 2025 the default is LoRA or QLoRA — the quality gap to full FT is typically under 5% on most tasks. Full FT is reserved for cases where the gap matters: foundational rebuilds, niche-domain rewrites, capability injection like long-context or multimodal. The brutal rule: don\'t full-FT until you\'ve measured a PEFT plateau and the remaining gap is worth the cost. Per-tenant full-FT is almost never economic. Catastrophic forgetting on general benchmarks is the always-on risk; mix 5-10% general data to mitigate.',
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
