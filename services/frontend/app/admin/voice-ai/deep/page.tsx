'use client';

/**
 * Voice AI deep dive — speaker recognition evolution + voice
 * authentication system + AI-extended threat model.
 *
 * JFA → i-vector → x-vector → ECAPA-TDNN: the evolution of speaker
 * recognition from explicit factor decomposition to learned deep
 * embeddings. Plus a production-ready voice authentication system
 * design with C4 + ADRs + JAD framing + STRIDE threat model.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — JFA EVOLUTION
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'jfa-to-x-vector',
    title: '1. JFA → i-vector → x-vector → ECAPA-TDNN — speaker recognition evolution',
    status: 'shipped',
    coreConcept: 'Speaker recognition has moved from explicit statistical decomposition (JFA) to compact total-variability vectors (i-vector) to learned deep embeddings (x-vector, ECAPA-TDNN). Each step traded explainability for accuracy + scalability.',
    oneLiner: 'JFA = explicit separation. i-vector = compact representation. x-vector / ECAPA-TDNN = learned representation (production default).',
    businessContext: 'Voice biometrics power banking auth, call-center identification, forensics. Choosing the right model determines accuracy, latency, scalability, and compliance posture. Modern production = x-vector or ECAPA-TDNN; JFA is research-only today.',
    fiveW: {
      what: 'A family of speaker-recognition models. JFA decomposes M = m + Vy + Ux + Dz (universal background + speaker + channel + residual). i-vector compresses to one total-variability vector. x-vector uses a DNN to learn an embedding. ECAPA-TDNN is the SOTA refinement.',
      why: 'Speech mixes speaker identity with channel + noise. Each model represents this differently — JFA explicitly, i-vector implicitly, x-vector learned.',
      where: 'Banking voice auth, call-center authentication, forensics, voice biometrics.',
      when: 'Today: x-vector or ECAPA-TDNN for production; i-vector for low-compute legacy; JFA only as research baseline.',
      who: 'AI/ML team for model selection; security for risk threshold; product for FAR/FRR target.',
    },
    interview30s: 'Speaker recognition has evolved through four generations. JFA decomposes speech into speaker + channel + noise factors via Gaussian mixture models — explainable but complex and not scalable. i-vector compresses to one total-variability vector — simpler, lower accuracy. x-vector uses a DNN to learn the embedding directly — high accuracy, real-time, GPU-friendly. ECAPA-TDNN is the current SOTA, refining x-vector with attentive pooling and squeeze-excitation. For production today I use ECAPA-TDNN paired with anti-spoofing, risk-based thresholds, MFA fallback, and audit logging. JFA stays in research labs.',
    hld: `flowchart LR
  JFA[JFA explicit decomposition] --> IV[i-vector compact vector]
  IV --> XV[x-vector DNN embedding]
  XV --> ECAPA[ECAPA-TDNN attentive pooling]
  classDef legacy fill:#fee,stroke:#991b1b
  classDef current fill:#d1fae5,stroke:#065f46
  class JFA legacy
  class XV,ECAPA current`,
    networkFlow: `flowchart LR
  Audio[User voice] --> Feat[Feature extraction MFCC]
  Feat --> Model[Speaker model]
  Model --> Embed[Embedding]
  Embed --> Score[Similarity scoring]
  Score --> Decision[Accept Reject Review]`,
    flowchart: `flowchart LR
  Q[Voice biometric need] --> S1[Pick generation]
  S1 -->|legacy| JFA
  S1 -->|legacy compute-tight| IV
  S1 -->|production default| XV
  S1 -->|SOTA| ECAPA
  S1 --> S2[Pair with anti-spoof + threshold + MFA]`,
    sequence: `sequenceDiagram
  participant U as User
  participant F as Feature Extractor
  participant E as Embedding Model
  participant S as Similarity Engine
  participant D as Decision
  U->>F: voice sample
  F->>E: MFCC
  E->>S: embedding
  S->>D: cosine score
  D-->>U: accept reject review`,
    coreLayers: [
      { layer: 'JFA (legacy)', responsibility: 'M = m + Vy + Ux + Dz; explicit factor decomposition.' },
      { layer: 'i-vector', responsibility: 'Total variability matrix → one compact vector.' },
      { layer: 'x-vector', responsibility: 'TDNN-based DNN learns speaker embedding from MFCC.' },
      { layer: 'ECAPA-TDNN', responsibility: 'Attentive statistical pooling + squeeze-excitation; SOTA accuracy.' },
      { layer: 'Scoring', responsibility: 'Cosine or PLDA between probe + enrolled embedding.' },
    ],
    lld: `flowchart LR
  AudioBytes --> MFCC[MFCC feature extraction]
  MFCC --> TDNN[TDNN layers]
  TDNN --> Pool[Attentive statistical pooling]
  Pool --> FC[Fully connected]
  FC --> Embed[192-d embedding]
  Embed --> CompareWith[Stored voiceprint]
  CompareWith --> Cosine[Cosine similarity]
  Cosine --> Threshold[Risk threshold]`,
    problem: 'JFA is too complex for production scale; manual factor tuning fails at thousands of speakers. i-vector is better but accuracy plateaus. Need learned representation.',
    whyThisApproach: 'x-vector + ECAPA-TDNN learn speaker embeddings from data directly. GPU-friendly inference. Real-time. Robust to noise + channel.',
    whenToUse: ['Production voice auth', 'Call-center identification', 'High-accuracy security', 'Anything past pre-2018'],
    whenNotToUse: ['Research baseline (use JFA for explainability comparison)', 'Extreme low-compute embedded device (use i-vector)'],
    input: 'Audio sample (≥3-5s, 16kHz min)',
    process: ['Audio capture', 'Validate quality + length', 'MFCC extraction', 'Embedding via DNN', 'Similarity score vs enrolled', 'Threshold decision', 'Optional MFA on borderline'],
    output: 'Accept / reject / step-up MFA / manual review + audit row + score',
    alternatives: [
      { name: 'JFA', tradeoff: 'Explainable; complex; legacy-only today' },
      { name: 'i-vector', tradeoff: 'Compact; lower accuracy than DNN' },
      { name: 'x-vector', tradeoff: 'High accuracy; GPU inference; production default' },
      { name: 'ECAPA-TDNN', tradeoff: 'SOTA; same ops profile as x-vector' },
    ],
    challenges: ['Threshold calibration (FAR vs FRR)', 'Anti-spoofing for replay/deepfake', 'Short-audio confidence', 'Noise robustness'],
    edgeCases: [
      { case: 'Same speaker different noise/device', solution: 'Robust embedding handles; threshold may need per-channel calibration' },
      { case: 'Different speakers similar voice', solution: 'Tighter threshold + MFA fallback' },
      { case: 'Short audio < 3s', solution: 'Reject + retry; low-confidence flag' },
      { case: 'Replay or deepfake attack', solution: 'Anti-spoofing model + liveness check' },
    ],
    failureModes: [
      { mode: 'Model drift', detect: 'EER trend up over weeks', recover: 'Retrain with fresh data + recalibrate threshold' },
      { mode: 'Spoof attack succeeds', detect: 'Anti-spoof score below threshold', recover: 'Reject + alert + flag account' },
    ],
    monitoring: ['EER (Equal Error Rate)', 'FAR + FRR per tenant', 'Spoof detection rate', 'Per-call latency', 'Manual review rate'],
    testing: ['Drill: same-speaker different-channel still passes', 'Drill: replay attack rejected', 'Drill: deepfake rejected', 'Drill: short audio low-confidence path'],
    security: ['Store embeddings, not raw audio', 'Encrypt at rest + in transit', 'Per-tenant access', 'MFA fallback on high-risk'],
    scaling: ['Embedding inference: ~50-200ms p95 on GPU', 'Per-tenant voiceprint DB', 'Cosine score: O(N) per call'],
    maturity: { mvp: 'JFA or i-vector', production: 'x-vector + anti-spoof + risk threshold + MFA', enterprise: 'ECAPA-TDNN + per-tenant calibration + continuous monitoring + drift detection' },
    limitations: ['EER never zero on noisy real-world audio', 'Anti-spoofing arms race', 'Cross-language degradation'],
    projectFit: ['services/voice-svc/ — voice biometric service', 'libs/py/voice_models/ — embedding wrappers', 'mcp/tests/drill_voice_*.py — anti-spoof + threshold drills'],
    interviewLine: 'For production voice auth I use ECAPA-TDNN, not JFA. JFA stays in research; production needs DNN embeddings + anti-spoofing + risk threshold + MFA fallback + audit logging.',
    implementationSteps: [
      { step: 'Pick model', logic: 'ECAPA-TDNN for new builds; x-vector for legacy parity.' },
      { step: 'Feature extraction', logic: 'MFCC 20-40 coefficients + delta + delta-delta.' },
      { step: 'Embedding model', logic: 'TDNN + attentive pooling + 192-d projection.' },
      { step: 'Scoring', logic: 'Cosine similarity vs enrolled voiceprint.' },
      { step: 'Anti-spoofing', logic: 'Separate model detects replay/synthetic; gates decision.' },
      { step: 'Risk threshold', logic: 'Per-tenant calibration; FAR/FRR target.' },
      { step: 'MFA fallback', logic: 'Borderline + high-risk transactions step-up.' },
    ],
    codeExample: { language: 'python', code: `# services/voice-svc/app/embedding.py — ECAPA-TDNN inference
import torch
from speechbrain.pretrained import EncoderClassifier

# SpeechBrain pretrained ECAPA-TDNN
model = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
)

class SpeakerEmbedder:
    def __init__(self, model=model):
        self._model = model

    def embed(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Audio → 192-d L2-normalized embedding."""
        with torch.no_grad():
            embedding = self._model.encode_batch(audio_tensor)
        return torch.nn.functional.normalize(embedding.squeeze(), dim=-1)

class SimilarityEngine:
    def __init__(self, embedder: SpeakerEmbedder):
        self._embedder = embedder

    def score(self, probe_audio: torch.Tensor, enrolled: torch.Tensor) -> float:
        probe_emb = self._embedder.embed(probe_audio)
        return torch.dot(probe_emb, enrolled).item()

class VoiceAuthDecision:
    def __init__(self, similarity: SimilarityEngine, anti_spoof, threshold_mgr):
        self._sim = similarity
        self._anti_spoof = anti_spoof
        self._th = threshold_mgr

    def authenticate(self, user_id: str, audio: torch.Tensor) -> dict:
        # Anti-spoof first
        if not self._anti_spoof.is_genuine(audio):
            return {"decision": "reject", "reason": "spoof_detected"}
        enrolled = voiceprint_repo.get(user_id)
        score = self._sim.score(audio, enrolled)
        decision = self._th.decide(user_id, score)
        return {"decision": decision, "score": score}` },
    realUseCase: 'Banking voice auth: original system used i-vector with EER 4.2%. Migrated to ECAPA-TDNN; EER dropped to 1.1%. Added anti-spoofing model; replay attack success rate fell from 8% to 0.3%. Per-tenant threshold calibration cut FRR by 40% on noisy mobile customers. Full system: x-vector + anti-spoof + per-tenant threshold + MFA on >$10K transactions + audit chain.',
    prosCons: {
      pros: ['SOTA accuracy (EER ~1%)', 'GPU-friendly real-time inference', 'Robust to channel + noise', 'Pretrained models available (SpeechBrain, NeMo)'],
      cons: ['GPU required for low latency', 'Embedding leakage = biometric leak (encrypt!)', 'Anti-spoofing arms race', 'Cross-language degradation'],
    },
    comparison: { left: 'JFA (legacy)', right: 'ECAPA-TDNN (this)', rows: [
      { aspect: 'EER', left: '~5-7%', right: '~1%' },
      { aspect: 'Real-time', left: 'Hard', right: 'Easy on GPU' },
      { aspect: 'Scalability', left: 'Poor', right: 'Excellent' },
      { aspect: 'Noise robustness', left: 'Medium', right: 'Very Good' },
      { aspect: 'Production maturity', left: 'Pre-2018', right: '2024+ standard' },
    ] },
    solutions: [
      { problem: 'Replay attack', solution: 'Anti-spoofing model + liveness' },
      { problem: 'Threshold abuse via many samples', solution: 'Rate limit + anomaly detection' },
      { problem: 'Voiceprint leakage', solution: 'Encrypt embeddings + access control' },
      { problem: 'Short audio false-reject', solution: 'Quality gate; require ≥3s; retry capture' },
      { problem: 'Model drift', solution: 'Continuous monitoring + retraining schedule' },
    ],
    bestPractices: { do: ['Use ECAPA-TDNN or x-vector for new builds', 'Anti-spoof model alongside', 'Per-tenant threshold calibration', 'Store embeddings not raw audio', 'MFA fallback on high-risk', 'Audit every authentication'], avoid: ['JFA in production', 'Raw audio storage', 'No anti-spoofing', 'Fixed threshold across tenants', 'Skipping liveness check'], optimize: ['Quantize ECAPA-TDNN for CPU inference', 'Embedding cache for repeat enrollment', 'Per-channel calibration (mobile vs desktop)'] },
    antiPatterns: ['JFA in production', 'No anti-spoofing', 'Raw audio storage', 'No MFA fallback', 'No drift monitoring'],
    testTypes: ['EER drill on golden set', 'Anti-spoof drill (replay + deepfake)', 'Threshold calibration drill', 'Model drift drill (weekly)'],
    testScenarios: [
      { scenario: 'Same speaker different channel', expected: 'Pass with high score' },
      { scenario: 'Replay attack', expected: 'Anti-spoof rejects' },
      { scenario: 'Different speakers similar voice', expected: 'Tight threshold rejects; MFA fallback' },
      { scenario: 'Short audio < 3s', expected: 'Quality gate rejects; retry' },
      { scenario: 'Deepfake voice', expected: 'Anti-spoof model detects + rejects' },
    ],
    testData: [
      { type: 'VoxCeleb golden set', example: 'Standard speaker-verification benchmark' },
      { type: 'Replay attack corpus', example: 'ASVspoof challenge dataset' },
      { type: 'Per-tenant calibration set', example: 'Customer-specific channel + noise profiles' },
    ],
    debuggingChecklist: ['EER spike? Check drift trend + retrain', 'False reject high? Per-tenant threshold + channel calibration', 'Spoof getting through? Anti-spoof model + threshold review'],
    productionIssues: [
      { issue: 'Replay attack success rate 8%', rootCause: 'No anti-spoofing model. Added; rate dropped to 0.3%.' },
      { issue: 'Mobile customers had 12% false-reject', rootCause: 'Single global threshold. Per-channel calibration; FRR dropped 40%.' },
      { issue: 'Voiceprint DB breach risk', rootCause: 'Embeddings stored unencrypted. Added KMS encryption + access control.' },
    ],
    performance: ['Embedding inference: ~50-200ms p95 GPU; ~500ms-1s CPU', 'Cosine score: <1ms per pair', 'Anti-spoofing: ~30-100ms p95'],
    costConsiderations: ['GPU inference: ~$0.001 per auth at scale', 'Embedding storage: ~1KB per user', 'Audit storage: ~500 bytes per auth × retention'],
    observability: ['Per-tenant EER trend', 'Per-tenant FAR/FRR', 'Spoof detection rate', 'Per-channel score distribution', 'Audit chain integrity'],
    metrics: [
      { name: 'voice_auth_eer{tenant}', example: 'Gauge weekly; alert on regression' },
      { name: 'voice_auth_far{tenant}', example: 'Gauge; target ≤ 0.1%' },
      { name: 'voice_auth_frr{tenant}', example: 'Gauge; target ≤ 5%' },
      { name: 'voice_auth_spoof_detected_total{type}', example: 'Counter; type=replay|deepfake' },
    ],
    tradeoffs: [
      { decision: 'Threshold tightness', tradeoff: 'Tight = lower FAR; higher FRR (UX)' },
      { decision: 'Anti-spoof aggressiveness', tradeoff: 'Strict = safer; more legitimate rejects' },
      { decision: 'Per-tenant vs global threshold', tradeoff: 'Per-tenant = better calibration; ops cost' },
    ],
    decisionMatrix: [
      { option: 'ECAPA-TDNN (this)', whenToUse: 'New production build; security matters' },
      { option: 'x-vector', whenToUse: 'Legacy parity; simpler ops' },
      { option: 'i-vector', whenToUse: 'Embedded device; extreme low compute' },
      { option: 'JFA', whenToUse: 'Research baseline only' },
    ],
    starStory: {
      situation: 'Banking voice auth at EER 4.2% with replay attack rate 8%; CFO threatened to disable.',
      task: 'Get to bank-grade security (EER < 1%, replay < 1%) without disabling.',
      action: 'Migrated i-vector → ECAPA-TDNN. Added anti-spoofing model. Per-tenant threshold calibration. MFA on > $10K. Audit chain.',
      result: 'EER 4.2% → 1.1%. Replay attack 8% → 0.3%. FRR dropped 40% on mobile. Pattern adopted as bank standard.',
    },
    interviewTraps: ['JFA in production', 'No anti-spoofing', 'Raw audio storage', 'No MFA fallback', 'Fixed threshold across all tenants'],
    finalScript: 'Joint Factor Analysis decomposes speech into speaker + channel + noise factors via Gaussian mixture models — explainable but complex and not scalable; pre-2018 production. i-vector compresses to one total-variability vector — simpler, lower accuracy. x-vector uses a DNN to learn the embedding directly — high accuracy, real-time, GPU-friendly. ECAPA-TDNN is the current SOTA, refining x-vector with attentive pooling. For production today I use ECAPA-TDNN paired with anti-spoofing, risk-based thresholds, MFA fallback, and audit logging. JFA stays in research labs; production needs all five layers: model + anti-spoof + threshold + MFA + audit.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — VOICE AUTH SYSTEM
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'voice-auth-system',
    title: '2. Voice Authentication System — full architecture (C4 + ADRs + JAD)',
    status: 'shipped',
    coreConcept: 'Production voice auth is not just a model. It needs enrollment + consent + liveness + risk threshold + MFA fallback + audit + monitoring + incident response. The model verifies; the architecture controls trust.',
    oneLiner: 'The model verifies identity; the architecture controls trust. Enrollment + liveness + threshold + MFA + audit are non-negotiable.',
    businessContext: 'Banks, call centers, secure portals adopt voice biometrics for friction reduction. Without the full architecture, voice auth is risk-amplifying not risk-reducing.',
    fiveW: {
      what: 'A voice authentication system: enrollment flow + consent + liveness + embedding model + similarity + threshold + MFA + audit + monitoring + incident playbook.',
      why: 'A model alone is a black box; the architecture wraps it with controls that make it production-safe.',
      where: 'Banking voice login, call-center agent auth, secure portal step-up, IoT device enrollment.',
      when: 'Deploy after JAD + ADRs + threat model.',
      who: 'AI/ML team for model; security for risk + threshold; product for UX; compliance for consent.',
    },
    interview30s: 'A production voice auth system has eleven components: audio validator (format + quality), noise reducer, voice activity detector, feature extractor (MFCC), embedding model (ECAPA-TDNN), similarity engine (cosine/PLDA), threshold manager (per-tenant calibrated), anti-spoof detector (replay + deepfake), decision engine (accept/reject/MFA/review), audit logger (hash-chained), monitoring (EER + FAR/FRR + drift). Plus enrollment flow with consent, liveness check, embedding storage (NEVER raw audio), MFA binding, retention policy. The model verifies; the architecture controls trust.',
    hld: `flowchart TB
  User[User] --> APIGW[API Gateway]
  APIGW --> Validator[Audio Validator]
  Validator --> NoiseRed[Noise Reducer]
  NoiseRed --> VAD[Voice Activity Detector]
  VAD --> Liveness[Liveness Detector]
  Liveness --> Feat[Feature Extractor MFCC]
  Feat --> Embed[Embedding Model ECAPA]
  Embed --> Sim[Similarity Engine]
  Sim --> Thresh[Threshold Manager per-tenant]
  Thresh --> Decision[Decision Engine]
  Decision --> Audit[Audit Logger]
  Decision -->|low score| MFA[MFA Step-up]
  Decision -->|high risk| HITL[Manual Review]
  Embed -.lookup.-> VPDB[(Voiceprint DB encrypted)]`,
    networkFlow: `flowchart LR
  Mobile[Mobile App] -->|HTTPS| APIGW
  APIGW -->|gRPC| VoiceSvc[Voice Auth Service]
  VoiceSvc -->|encrypted| VPDB[(Voiceprint DB)]
  VoiceSvc -->|audit| Chain[(Hash-chain audit)]`,
    flowchart: `flowchart LR
  Q[Authentication request] --> S1[Validate audio]
  S1 --> S2[Liveness check]
  S2 -->|fail| Reject1[Reject spoof]
  S2 -->|pass| S3[Embed]
  S3 --> S4[Compare]
  S4 --> S5[Risk score]
  S5 -->|high score| Accept
  S5 -->|medium| MFA
  S5 -->|low| Reject2
  Accept --> Audit
  MFA --> Audit
  Reject1 --> Audit
  Reject2 --> Audit`,
    sequence: `sequenceDiagram
  participant U as User
  participant GW as Gateway
  participant V as Voice Svc
  participant L as Liveness
  participant M as Match
  participant D as Decision
  participant A as Audit
  U->>GW: voice + claim
  GW->>V: forward
  V->>L: liveness check
  L-->>V: pass
  V->>M: embed + compare
  M-->>V: score
  V->>D: decide
  D-->>V: accept reject mfa
  V->>A: audit
  V-->>U: result`,
    coreLayers: [
      { layer: 'Audio validator', responsibility: 'Format, length, sample rate, quality gate.' },
      { layer: 'Noise reducer + VAD', responsibility: 'Clean audio for embedding.' },
      { layer: 'Liveness + anti-spoof', responsibility: 'Detect replay, synthetic voice, deepfake.' },
      { layer: 'Embedding + similarity', responsibility: 'ECAPA-TDNN + cosine/PLDA.' },
      { layer: 'Threshold manager', responsibility: 'Per-tenant calibration; FAR/FRR target.' },
      { layer: 'Decision engine', responsibility: 'Accept / reject / MFA step-up / manual review.' },
      { layer: 'Audit + monitoring', responsibility: 'Hash-chain log; EER + drift dashboards.' },
    ],
    lld: `flowchart LR
  Audio --> Val[Validator]
  Val --> Pre[Preprocess]
  Pre --> Live[Liveness]
  Live --> Emb[Embed]
  Emb --> Sim[Similarity]
  Sim --> Th[Threshold]
  Th --> Dec[Decision]
  Dec --> Aud[Audit]`,
    problem: 'Model-only voice auth is a black box. Without enrollment + consent + liveness + threshold + MFA + audit, voice auth amplifies risk vs reduces it.',
    whyThisApproach: 'Eleven-component architecture covers the full lifecycle. Model is one component; ten others enforce trust controls around it.',
    whenToUse: ['Banking', 'Call-center authentication', 'High-value transaction step-up', 'Identity proofing'],
    whenNotToUse: ['Casual non-security UX (use simpler bio)'],
    input: 'Voice sample + claimed user_id + risk context',
    process: ['Validate audio', 'Liveness', 'Embed', 'Compare', 'Threshold', 'Decide', 'Audit'],
    output: 'Decision + score + audit row + escalation if needed',
    alternatives: [
      { name: 'Password only', tradeoff: 'Simple; phishable + reusable' },
      { name: 'OTP only', tradeoff: 'Simple; SIM-swap vulnerable' },
      { name: 'Voice biometric only', tradeoff: 'Frictionless; spoof risk + privacy' },
      { name: 'Voice + MFA + threshold (this)', tradeoff: 'Best balance; ops cost' },
    ],
    challenges: ['Enrollment quality drives auth quality', 'Cross-channel calibration', 'Anti-spoof arms race', 'Compliance for biometric data'],
    edgeCases: [
      { case: 'User has cold/sore throat', solution: 'Threshold tolerance + MFA fallback + retry policy' },
      { case: 'Background noise (street, café)', solution: 'Noise reducer + per-environment threshold' },
      { case: 'Twin / similar voice', solution: 'Tighter threshold + always-MFA on high-value' },
      { case: 'User changes age (puberty, illness)', solution: 'Re-enroll periodically; drift detection' },
    ],
    failureModes: [
      { mode: 'Voiceprint DB breach', detect: 'Access audit', recover: 'Force re-enroll + revoke; biometric is harder than password' },
      { mode: 'Anti-spoof model bypassed', detect: 'Spoof rate spike', recover: 'Update model; tighten threshold; alert' },
      { mode: 'Model drift on customer', detect: 'EER per-tenant trend', recover: 'Re-enroll affected user; retrain' },
    ],
    monitoring: ['Per-tenant EER + FAR + FRR', 'Spoof detection rate', 'Manual review rate', 'Per-call latency p95', 'Audit chain integrity'],
    testing: ['Drill: enrollment flow end-to-end', 'Drill: replay attack rejected', 'Drill: deepfake rejected', 'Drill: MFA step-up triggered', 'Drill: voiceprint encryption + access control'],
    security: ['Store embeddings not raw audio', 'Encrypt at rest (KMS) + in transit (TLS)', 'Per-tenant access control', 'MFA fallback', 'Audit every authentication', 'Consent + retention compliance'],
    scaling: ['Per-tenant voiceprint sharding', 'GPU pool for embedding', 'Cosine score ~O(1) per pair', 'Audit chain async write'],
    maturity: { mvp: 'Model + threshold', production: '11-component + anti-spoof + MFA + audit', enterprise: 'Per-tenant calibration + drift detection + biometric registry + SOC2 + EU AI Act compliance' },
    limitations: ['Biometrics are revocable only by re-enrollment', 'False reject = user pain', 'Privacy regulations vary'],
    projectFit: ['services/voice-svc/ — voice auth service', 'libs/py/voice/ — components', 'mcp/tests/drill_voice_*.py — per-component drills', '/admin/c4-model/deep — architecture framing', '/admin/jad/deep — JAD-driven decisions'],
    interviewLine: 'The model verifies identity; the architecture controls trust. Eleven components, with anti-spoofing + risk threshold + MFA + audit non-negotiable.',
    implementationSteps: [
      { step: 'Enrollment flow', logic: 'Consent → 3+ samples → quality gate → embed → store in encrypted DB → bind to MFA.' },
      { step: 'Authentication flow', logic: 'Validate → liveness → embed → compare → threshold → decide → audit.' },
      { step: 'Per-tenant threshold', logic: 'Calibrate per channel + per user-segment.' },
      { step: 'MFA fallback', logic: 'Step-up on borderline + always for high-value.' },
      { step: 'Audit chain', logic: 'Hash-chained per tenant; tamper-evident.' },
      { step: 'Drift monitoring', logic: 'Per-tenant EER weekly; alert on regression.' },
      { step: 'Incident playbook', logic: 'Spoof detected → rate-limit + alert + investigate.' },
    ],
    codeExample: { language: 'python', code: `# services/voice-svc/app/auth.py — production voice auth
class VoiceAuthService:
    def __init__(self, validator, liveness, embedder, similarity,
                 threshold_mgr, decision, audit, anti_spoof):
        self._validator = validator
        self._liveness = liveness
        self._embedder = embedder
        self._sim = similarity
        self._th = threshold_mgr
        self._decision = decision
        self._audit = audit
        self._anti_spoof = anti_spoof

    async def authenticate(self, user_id: str, audio: bytes,
                           context: AuthContext) -> AuthResult:
        # 1. Quality gate
        quality = self._validator.validate(audio)
        if not quality.passed:
            await self._audit.log(user_id, "reject", "poor_audio", context)
            return AuthResult.reject("poor_audio_quality")

        # 2. Liveness + anti-spoof
        if not await self._liveness.check(audio):
            await self._audit.log(user_id, "reject", "spoof", context)
            return AuthResult.reject("spoof_detected")
        if not await self._anti_spoof.is_genuine(audio):
            await self._audit.log(user_id, "reject", "anti_spoof", context)
            return AuthResult.reject("anti_spoof_failed")

        # 3. Embed + compare
        probe = await self._embedder.embed(audio)
        enrolled = await voiceprint_repo.get(user_id, encrypted=True)
        score = self._sim.compare(probe, enrolled)

        # 4. Decide
        decision = self._decision.decide(
            user_id=user_id, score=score, context=context,
        )
        # decision: accept | reject | mfa_step_up | manual_review

        # 5. Audit
        await self._audit.log(user_id, decision.outcome, decision.reason, context, score=score)

        return AuthResult(
            decision=decision.outcome, score=score,
            mfa_required=decision.outcome == "mfa_step_up",
        )` },
    realUseCase: 'Banking voice auth pre-architecture: model-only, EER 5%, no anti-spoofing, no MFA fallback. Replay attack rate 8%; FRR 12%. Adopted full 11-component architecture: ECAPA-TDNN + anti-spoof + per-tenant threshold + MFA + audit chain. Result: EER 1.1%, replay 0.3%, FRR 7%. Compliance signed off; pattern adopted enterprise-wide.',
    prosCons: {
      pros: ['Frictionless UX (after enrollment)', 'Phishing-resistant', 'Audit-grade evidence', 'MFA fallback covers borderline'],
      cons: ['Biometric data is highly regulated', 'Voiceprint breach is hard to remediate', 'Cross-language degradation', 'Anti-spoof arms race'],
    },
    comparison: { left: 'Password + OTP', right: 'Voice + anti-spoof + MFA (this)', rows: [
      { aspect: 'UX friction', left: 'High', right: 'Low post-enrollment' },
      { aspect: 'Phishability', left: 'High', right: 'Low' },
      { aspect: 'SIM-swap risk', left: 'OTP vulnerable', right: 'Voice not affected' },
      { aspect: 'Compliance burden', left: 'Lower', right: 'Higher (biometric)' },
      { aspect: 'Spoof risk', left: 'N/A', right: 'Real (replay/deepfake) — mitigated' },
    ] },
    solutions: [
      { problem: 'Replay attack', solution: 'Anti-spoof + liveness + threshold + MFA' },
      { problem: 'Voiceprint breach', solution: 'Encrypt + access control + MFA + re-enroll + revoke' },
      { problem: 'Cross-channel degradation', solution: 'Per-channel threshold calibration' },
      { problem: 'Cold / sore throat false-reject', solution: 'Threshold tolerance + MFA fallback + retry' },
    ],
    bestPractices: { do: ['11-component architecture', 'Embeddings only (no raw audio)', 'Anti-spoof + liveness', 'Per-tenant threshold', 'MFA fallback', 'Audit chain', 'Drift monitoring', 'Consent + retention compliance'], avoid: ['Raw audio storage', 'No anti-spoofing', 'Fixed global threshold', 'No MFA fallback', 'No drift monitoring'], optimize: ['Quantize ECAPA for CPU edge', 'Embedding cache', 'Per-channel calibration', 'Continuous re-enrollment'] },
    antiPatterns: ['Model-only auth', 'Raw audio storage', 'No liveness', 'No MFA', 'No drift monitoring'],
    testTypes: ['End-to-end auth drill', 'Replay attack drill', 'Deepfake drill', 'MFA step-up drill', 'Voiceprint encryption drill', 'Per-tenant threshold drill'],
    testScenarios: [
      { scenario: 'Genuine user clean audio', expected: 'Accept high score' },
      { scenario: 'Replay attack', expected: 'Anti-spoof rejects' },
      { scenario: 'Borderline score', expected: 'MFA step-up' },
      { scenario: 'Deepfake voice', expected: 'Anti-spoof rejects + alert' },
      { scenario: 'Voiceprint DB access', expected: 'Encryption check + access audit' },
      { scenario: 'High-value transaction', expected: 'Always MFA regardless of score' },
    ],
    testData: [
      { type: 'VoxCeleb golden set', example: 'Standard speaker verification benchmark' },
      { type: 'ASVspoof corpus', example: 'Replay + synthetic voice attacks' },
      { type: 'Per-tenant calibration', example: 'Customer-specific channel + noise samples' },
    ],
    debuggingChecklist: ['EER spike? Drift trend + retrain', 'Spoof getting through? Anti-spoof model + threshold', 'False reject high? Per-channel threshold + cold/illness retry policy', 'Voiceprint DB access? Audit + encryption check'],
    productionIssues: [
      { issue: 'Replay attack rate 8%', rootCause: 'No anti-spoofing. Added; rate dropped to 0.3%.' },
      { issue: 'Mobile FRR 12%', rootCause: 'Single global threshold. Per-channel calibration; FRR dropped 40%.' },
      { issue: 'Voiceprint DB breach risk', rootCause: 'Embeddings unencrypted. KMS encryption added.' },
      { issue: 'CFO threatened to disable voice auth', rootCause: 'Model-only; no MFA fallback. 11-component architecture deployed.' },
    ],
    performance: ['End-to-end auth: ~150-400ms p95', 'Embedding: ~50-200ms GPU; ~500ms-1s CPU', 'Anti-spoof: ~30-100ms p95', 'Audit write: async ~10ms'],
    costConsiderations: ['GPU inference: ~$0.001-0.005 per auth', 'Voiceprint storage: ~1KB per user', 'Anti-spoof compute: similar to embedding', 'Compliance audit: significant ongoing cost'],
    observability: ['Per-tenant EER + FAR/FRR weekly', 'Spoof detection rate', 'MFA step-up rate', 'Manual review rate', 'Audit chain integrity', 'Per-channel score distribution'],
    metrics: [
      { name: 'voice_auth_decision_total{tenant,outcome}', example: 'Counter; outcome distribution' },
      { name: 'voice_auth_eer{tenant,p}', example: 'Gauge weekly; alert on regression' },
      { name: 'voice_auth_spoof_attempts_total{type,outcome}', example: 'Counter; type=replay|deepfake' },
      { name: 'voice_auth_mfa_stepup_rate{tenant}', example: 'Gauge; trend' },
    ],
    tradeoffs: [
      { decision: 'Threshold tightness', tradeoff: 'Tight = lower FAR; higher FRR' },
      { decision: 'Always-MFA on high-value', tradeoff: 'Friction vs security' },
      { decision: 'Re-enrollment cadence', tradeoff: 'Frequent = drift-resilient; UX cost' },
    ],
    decisionMatrix: [
      { option: '11-component architecture (this)', whenToUse: 'Production voice auth' },
      { option: 'Model + threshold only', whenToUse: 'Internal tool only' },
      { option: 'Voice + password fallback', whenToUse: 'Lower-risk consumer app' },
    ],
    starStory: {
      situation: 'Banking voice auth EER 5%, replay attack 8%, FRR 12%; CFO threatened to disable.',
      task: 'Bank-grade security without disabling.',
      action: 'Deployed 11-component architecture: ECAPA-TDNN + anti-spoof + per-tenant threshold + MFA + audit chain. drill_voice_replay + drill_voice_threshold + drill_voiceprint_encryption in CI.',
      result: 'EER 1.1%, replay 0.3%, FRR 7%. Compliance signed off. Adopted enterprise-wide.',
    },
    interviewTraps: ['Model-only auth', 'No anti-spoofing', 'Raw audio storage', 'No MFA fallback', 'No drift monitoring'],
    finalScript: 'A production voice authentication system is not only a speaker recognition model. It needs enrollment with consent, liveness detection, anti-spoofing, risk-based thresholds, MFA fallback, audit logging, drift monitoring, and incident response. The model verifies identity, but the architecture controls trust. Eleven components: validator, noise reducer, VAD, liveness, feature extractor, embedding model, similarity engine, threshold manager, anti-spoof detector, decision engine, audit logger. Plus enrollment flow, retention policy, and compliance review.',
  },
];

export default function VoiceAIDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Voice AI — speaker recognition + voice auth (deep dive)</h1>
        <p className="design-areas-sub">
          From JFA to ECAPA-TDNN: how speaker recognition evolved from explicit factor
          decomposition to learned deep embeddings. Plus a production-grade voice
          authentication system: 11 components covering enrollment, anti-spoofing,
          per-tenant thresholds, MFA fallback, audit chain, drift monitoring.
          The model verifies; the architecture controls trust.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/security/deep#owasp-stride-ai-threats', label: 'Voice biometric = bio PII', why: 'voice clip is sensitive biometric; STRIDE table required; spoofing is the highest threat' },
          { href: '/admin/pii/deep', label: 'PII pre-ingestion + retention', why: 'voice samples = SOC2 confidentiality + GDPR Art. 9 special-category data; consent + retention schedule mandatory' },
          { href: '/admin/guardrails/deep', label: 'Voice clone consent guardrail', why: 'TTS voice cloning requires consent record + watermarking (AudioSeal / Resemble Detect); refuse public-figure clones' },
          { href: '/admin/llmops/deep', label: 'Speaker model versioning + eval', why: 'ECAPA-TDNN model in registry with EER + DCF metrics; rollback via registry pointer flip' },
          { href: '/admin/checklist/deep#lifecycle-checklist', label: '§10 AI row applies', why: 'voice biometrics goes through the same eval gate + cost budget + fallback model rules as any AI feature' },
        ]}
      />
    </div>
  );
}
