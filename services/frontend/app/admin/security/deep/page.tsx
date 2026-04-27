'use client';

/**
 * Enterprise security playbook — OWASP 2025 + AI risks + DevSecOps +
 * Cloud/SOC2 (deep dive).
 *
 * Three topics covering the full security posture for AI-enabled
 * systems: threat model + OWASP Top 10:2025 mapped to AI risks,
 * shift-left DevSecOps pipeline (Snyk + SAST + SCA + secrets +
 * container hardening), and cloud security with SOC2 trust principles.
 */

import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — OWASP 2025 + STRIDE + AI RISKS
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'owasp-stride-ai-threats',
    title: '1. OWASP 2025 + STRIDE + AI-specific threats',
    status: 'shipped',
    coreConcept: 'Production AI systems face three risk classes: classic OWASP web risks (access, crypto, injection), STRIDE-style threat modeling (spoofing, tampering, repudiation, info disclosure, DoS, elevation of privilege), and AI-specific (prompt injection, model poisoning, hallucination, model theft, embedding leakage).',
    oneLiner: 'OWASP 2025 + STRIDE + AI extensions = the full threat surface; mapped per architecture layer with explicit controls.',
    businessContext: 'Treating OWASP as a checklist misses architecture-level risks; STRIDE alone misses AI-specific threats. The mature approach combines all three and maps each risk to a specific control.',
    fiveW: {
      what: 'A combined threat model: OWASP A01-A10 (2025), STRIDE 6 categories, AI extensions (prompt injection / model poisoning / hallucination / model theft / embedding leakage). Each maps to a layer-specific control.',
      why: 'Each framework alone has gaps. OWASP misses AI; STRIDE misses dependencies; AI-specific misses crypto. Together they cover.',
      where: 'Threat model doc per project; reviewed Day 3 of JAD.',
      when: 'Day 1 design; refreshed quarterly.',
      who: 'Security + architect + AI specialist.',
    },
    interview30s: 'I combine three frameworks: OWASP Top 10:2025 for classic web risks, STRIDE for component-level threat decomposition (spoofing, tampering, repudiation, info disclosure, DoS, elevation of privilege), and AI-specific extensions for prompt injection, model poisoning, hallucination, model theft, embedding leakage. Each risk maps to a layer-specific control: A01 broken access → object-level auth; A04 crypto → KMS; A06 insecure design → threat modeling; AI prompt injection → input filter + guardrails; AI model poisoning → data validation + signed artifacts; AI embedding leakage → encrypt + minimize. The principle is fail-closed: model can support identity verification, but the risk engine owns the final decision.',
    hld: `flowchart TB
  Risk[Threat surface] --> O[OWASP 2025]
  Risk --> S[STRIDE]
  Risk --> AI[AI extensions]
  O --> Layer[Per-layer controls]
  S --> Layer
  AI --> Layer
  Layer --> Mit[Mitigations enforced]`,
    networkFlow: `flowchart LR
  Edge[Edge WAF + Rate Limit] --> GW[API Gateway Auth + JWT]
  GW --> BE[Backend hardened config]
  BE --> AI[AI Layer guardrails + eval]
  AI --> DB[(Encrypted store)]
  Edge -.SIEM.-> Alert
  GW -.audit.-> Alert
  AI -.audit.-> Alert`,
    flowchart: `flowchart LR
  Q[New feature] --> S1[Threat model STRIDE]
  S1 --> S2[Map to OWASP]
  S2 --> S3[Add AI extensions]
  S3 --> S4[Per-layer control]
  S4 --> S5[Test + monitor]`,
    sequence: `sequenceDiagram
  participant Att as Attacker
  participant Edge as Edge
  participant AI as AI svc
  participant Audit as SIEM
  Att->>Edge: malicious input
  Edge->>Edge: rate limit + WAF
  Edge->>AI: forward
  AI->>AI: prompt injection filter
  AI->>AI: anti-spoof + guardrail
  AI->>Audit: log decision + risk score`,
    coreLayers: [
      { layer: 'Edge', responsibility: 'WAF + rate limit + DDoS protection.' },
      { layer: 'Auth', responsibility: 'JWT + MFA + RBAC/ABAC.' },
      { layer: 'AI Layer', responsibility: 'Input validation + guardrails + evaluation + anti-spoof.' },
      { layer: 'Data', responsibility: 'Encryption at rest + in transit + minimize storage.' },
      { layer: 'Audit', responsibility: 'Hash-chained log + SIEM + real-time alerting.' },
    ],
    lld: `flowchart LR
  In[Input] --> WAF
  WAF --> Auth
  Auth --> Inj[Injection filter]
  Inj --> AI[AI processing]
  AI --> Out[Output validator]
  Out --> Audit
  Audit --> SIEM`,
    problem: 'Treating OWASP as checklist misses architecture; STRIDE misses AI; AI-only misses dependencies. Need combined.',
    whyThisApproach: 'Three frameworks compose to cover the full risk surface. Layer mapping makes controls actionable.',
    whenToUse: ['Every production system', 'Threat-model review', 'Compliance audit prep'],
    whenNotToUse: ['Pre-PMF prototype'],
    input: 'New feature design + architecture diagram',
    process: ['STRIDE per component', 'OWASP per layer', 'AI extensions per AI feature', 'Layer-specific controls', 'Test + monitor'],
    output: 'Threat model doc + control list + monitoring + drills',
    alternatives: [
      { name: 'OWASP only', tradeoff: 'Misses AI + STRIDE component-level' },
      { name: 'STRIDE only', tradeoff: 'Misses dependencies + AI' },
      { name: 'Combined (this)', tradeoff: 'Comprehensive + ops cost' },
    ],
    challenges: ['Keeping threat model fresh', 'AI threats evolve rapidly', 'Cross-framework mapping discipline'],
    edgeCases: [
      { case: 'New AI capability not in any framework', solution: 'Add to AI-specific list; propose framework update' },
      { case: 'Risk crosses layers', solution: 'Multi-layer control; explicit cross-link' },
    ],
    failureModes: [
      { mode: 'Model bypassed by clever prompt injection', detect: 'Anomaly detection + drill', recover: 'Update guardrails; retrain detector' },
      { mode: 'Embedding leak via API scraping', detect: 'Rate limit alerts', recover: 'Tighter limit + auth + revoke key' },
    ],
    monitoring: ['Per-layer attack rate', 'Guardrail trip rate', 'Prompt injection block rate', 'Anti-spoof detection rate'],
    testing: ['Pen test', 'Injection test', 'Spoof test', 'Adversarial prompt suite', 'Red-team exercise'],
    security: ['All controls reviewed quarterly', 'Threat model in repo + git history', 'Per-layer ownership'],
    scaling: ['Controls scale per service', 'SIEM aggregates across', 'Drills automated'],
    maturity: { mvp: 'OWASP only', production: 'OWASP + STRIDE + AI + SIEM + drills', enterprise: 'Continuous threat modeling + automated red-team + ML anomaly detection' },
    limitations: ['New AI threats emerge; framework lag', 'Some risks inherently hard to detect (e.g., subtle model poisoning)'],
    projectFit: ['docs/security/threat-model.md', 'docs/security/owasp-mapping.md', '/admin/guardrails/deep — AI runtime guardrails', '/admin/rbac/deep — three-layer access control'],
    interviewLine: 'I don\'t treat OWASP Top 10 as a checklist. I map each risk to architecture layers, enforce controls via ADRs, validate through testing, and extend it for AI-specific threats.',
    implementationSteps: [
      { step: 'STRIDE per component', logic: 'Spoofing, Tampering, Repudiation, Info disclosure, DoS, Elevation.' },
      { step: 'OWASP A01-A10 per layer', logic: 'Map each Top 10 risk to where it lives.' },
      { step: 'AI extensions', logic: 'Prompt injection, model poisoning, hallucination, theft, embedding leak.' },
      { step: 'Layer-specific controls', logic: 'Each risk has a named control at the right layer.' },
      { step: 'Drills + monitoring', logic: 'Each control has a drill + dashboard.' },
      { step: 'Quarterly refresh', logic: 'Threat landscape changes; controls re-validated.' },
    ],
    codeExample: { language: 'markdown', code: `# Threat Model — Voice AI System

## STRIDE Mapping
| STRIDE | Voice AI Example | Control |
|---|---|---|
| Spoofing | Replay or synthetic voice | Liveness + anti-spoofing + MFA |
| Tampering | Modified audio or embedding | Hashing + signed payloads |
| Repudiation | User denies auth attempt | Audit logs + trace IDs |
| Info Disclosure | Voiceprint leak | Encryption + access control |
| Denial of Service | Audio flood attack | Rate limit + queue control |
| Elevation of Privilege | Admin bypass | RBAC/ABAC + approval workflow |

## OWASP 2025 Mapping
| OWASP | Voice AI Threat | Control |
|---|---|---|
| A01 Broken Access | Access another user's voiceprint | Object-level auth |
| A02 Misconfiguration | Exposed admin endpoint | Hardened config |
| A03 Supply Chain | Compromised ML dep | SBOM + signed artifacts |
| A04 Crypto Failure | Unencrypted biometric | KMS + encryption |
| A05 Injection | Malicious metadata | Validation |
| A06 Insecure Design | No liveness | Threat modeling |
| A07 Auth Failure | Weak MFA | MFA + secure session |
| A08 Integrity | Tampered model | Signed model registry |
| A09 Logging | No spoof alerts | SIEM + alerts |
| A10 Exception | Fail-open on error | Fail-closed |

## AI-Specific Threats
| AI Threat | Example | Control |
|---|---|---|
| Deepfake voice | Synthetic passes auth | Anti-spoof + MFA |
| Model drift | Accuracy drops | Continuous monitoring |
| Threshold abuse | Many sample tries | Rate limit + anomaly |
| Embedding leak | Reverse-identity | Encrypt + minimize |
| Poisoned enrollment | Bad voiceprint registered | Strong identity proofing |

## Final Decision Rule
| Condition | Decision |
|---|---|
| High score + low risk + live | Accept |
| Medium score | Step-up MFA |
| Low score | Reject |
| Spoof detected | Reject + alert |
| Model error | Fail closed |
| High-value transaction | MFA required |` },
    realUseCase: 'Voice AI threat-model session: STRIDE surfaced "user denies auth attempt" → audit logs added; OWASP A04 surfaced "unencrypted biometric" → KMS encryption added; AI extension surfaced "deepfake bypass" → anti-spoof model added. Without combined framework, only some risks would have been mitigated.',
    prosCons: {
      pros: ['Comprehensive threat coverage', 'Layer-mapped controls', 'AI-specific risks named', 'Drills + monitoring per control'],
      cons: ['Framework maintenance overhead', 'AI threats evolve rapidly', 'Cross-framework mapping discipline'],
    },
    comparison: { left: 'OWASP-only checklist', right: 'OWASP + STRIDE + AI (this)', rows: [
      { aspect: 'AI threat coverage', left: 'Limited', right: 'Comprehensive' },
      { aspect: 'Component-level decomposition', left: 'No', right: 'STRIDE per component' },
      { aspect: 'Layer mapping', left: 'Implicit', right: 'Explicit' },
    ] },
    solutions: [
      { problem: 'Prompt injection', solution: 'Input filter + Guardrails AI + adversarial drill' },
      { problem: 'Model poisoning', solution: 'Data validation + signed model artifacts' },
      { problem: 'Embedding leakage', solution: 'KMS encrypt + per-tenant access + minimize storage' },
      { problem: 'Deepfake voice', solution: 'Anti-spoof model + MFA fallback' },
    ],
    bestPractices: { do: ['Combined OWASP + STRIDE + AI', 'Layer-mapped controls', 'Drills per control', 'Quarterly refresh', 'Fail-closed defaults'], avoid: ['OWASP-only', 'STRIDE-only', 'AI-only', 'Fail-open on error'], optimize: ['Automated red-team', 'ML anomaly detection', 'Continuous threat modeling'] },
    antiPatterns: ['Checklist mentality', 'Single-framework reliance', 'Fail-open defaults', 'No drills per control'],
    testTypes: ['Pen test', 'OWASP scan', 'STRIDE drill per component', 'AI red-team', 'Adversarial prompt suite'],
    testScenarios: [
      { scenario: 'Prompt injection attempt', expected: 'Filtered + audited' },
      { scenario: 'Replay attack', expected: 'Anti-spoof rejects' },
      { scenario: 'API scraping for embeddings', expected: 'Rate limit + alert' },
      { scenario: 'Model error', expected: 'Fail-closed; reject + alert' },
    ],
    testData: [
      { type: 'OWASP probe corpus', example: 'Standard A01-A10 attack samples' },
      { type: 'AI red-team set', example: 'Prompt injection + model probing samples' },
    ],
    debuggingChecklist: ['Attack vector? Map to STRIDE + OWASP + AI; check control', 'Control bypassed? Drill missing or stale'],
    productionIssues: [
      { issue: 'Voice replay attack succeeded', rootCause: 'No anti-spoof model. Added per AI extension.' },
      { issue: 'Embedding API scraped', rootCause: 'No rate limit. Per-AI A03+model-theft control added.' },
    ],
    performance: ['Threat-model session: ~4 hours', 'Per-control drill: ~30 min', 'Quarterly refresh: ~1 day'],
    costConsiderations: ['Free — markdown + drills', 'Red-team exercise: significant cost (annual)'],
    observability: ['Per-control trip rate', 'Threat-model freshness', 'Drill pass rate'],
    metrics: [
      { name: 'security_control_trip_total{control,outcome}', example: 'Counter per control' },
      { name: 'security_drill_pass_rate{drill}', example: 'Gauge; target = 1.0' },
    ],
    tradeoffs: [
      { decision: 'Framework breadth', tradeoff: 'More = comprehensive; ops cost' },
      { decision: 'Drill cadence', tradeoff: 'Frequent = catches drift; cost' },
    ],
    decisionMatrix: [
      { option: 'OWASP + STRIDE + AI (this)', whenToUse: 'Production AI systems' },
      { option: 'OWASP only', whenToUse: 'Non-AI legacy' },
    ],
    starStory: {
      situation: 'Voice AI shipped without anti-spoof; first replay attack succeeded.',
      task: 'Close attack path before next quarter.',
      action: 'Combined threat model: STRIDE + OWASP + AI extensions. Anti-spoof model + audit + rate limit added.',
      result: 'Replay attack rate 8% → 0.3%. Pattern adopted enterprise-wide.',
    },
    interviewTraps: ['OWASP as checklist', 'No AI extensions', 'Fail-open defaults', 'No drills per control'],
    finalScript: 'I combine STRIDE, OWASP Top 10:2025, and AI-specific threat modeling. STRIDE for component-level decomposition, OWASP for classic web risks, AI extensions for prompt injection / model poisoning / hallucination / theft / embedding leak. Each risk maps to a layer-specific control. The principle is fail-closed: the AI model can support identity verification, but the risk engine owns the final trust decision.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — DEVSECOPS PIPELINE
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'devsecops-pipeline',
    title: '2. DevSecOps shift-left — Snyk + SAST + SCA + Secrets + Container hardening',
    status: 'shipped',
    coreConcept: 'Security embedded across SDLC: plan → code → build → test → deploy → run. Each stage has automated gates: SAST, SCA (Snyk), secrets scan, SBOM, container scan, runtime monitoring.',
    oneLiner: 'Shift-left = security at every stage; not a phase. Automated gates fail PRs that introduce risk.',
    businessContext: 'Security as a phase ships incidents; security as a pipeline catches them at PR. DevSecOps reduces MTTR + audit burden.',
    fiveW: {
      what: 'CI/CD pipeline with security gates: SAST (code scan), SCA (dependency scan via Snyk), secrets scan (gitleaks), SBOM (CycloneDX), container hardening + scan, signed artifacts (Sigstore), runtime monitoring.',
      why: 'Code-level bugs caught at PR; supply-chain risks caught at build; runtime threats caught in prod.',
      where: '.github/workflows/security.yml + Dockerfile + IaC scanners.',
      when: 'Every PR + every build + continuous in prod.',
      who: 'AppSec + DevOps + every engineer.',
    },
    interview30s: 'Shift-left DevSecOps pipeline: Plan stage = threat modeling. Code stage = SAST + secrets scan. Build stage = SCA via Snyk + SBOM via CycloneDX + container hardening (non-root user, distroless base, drop capabilities) + image scan. Deploy stage = signed artifacts via Sigstore + IaC scan + config harden. Run stage = runtime monitoring + SIEM + drift detection. Each stage has gates that fail the PR if findings exceed severity threshold. Snyk integrates dependency + container + IaC scans. AI-specific additions: prompt-injection adversarial suite + model integrity check + embedding encryption verification.',
    hld: `flowchart LR
  Plan[Plan threat-model] --> Code[Code SAST + secrets]
  Code --> Build[Build SCA + SBOM + container scan]
  Build --> Deploy[Deploy signed + IaC scan]
  Deploy --> Run[Run monitor + SIEM]
  Run -.feedback.-> Plan`,
    networkFlow: `flowchart LR
  Dev[Developer] --> PR[PR]
  PR --> CI[CI runner]
  CI --> SAST
  CI --> SCA[Snyk]
  CI --> Secrets[Secrets scan]
  CI --> Build[Build + SBOM]
  CI --> Sign[Sign artifact]
  Sign --> Reg[Registry]
  Reg --> Deploy
  Deploy --> Mon[Runtime monitor]`,
    flowchart: `flowchart LR
  S[Code commit] --> SAST
  SAST -->|fail| Block
  SAST --> SCA
  SCA -->|fail| Block
  SCA --> Secrets
  Secrets -->|fail| Block
  Secrets --> Build
  Build --> Container[Container scan]
  Container --> Sign[Sigstore]
  Sign --> Deploy
  Deploy --> Run`,
    sequence: `sequenceDiagram
  participant D as Dev
  participant CI as CI
  participant Snyk
  participant Reg as Registry
  D->>CI: PR
  CI->>CI: SAST + secrets
  CI->>Snyk: SCA + container
  Snyk-->>CI: results
  CI->>CI: SBOM
  CI->>CI: build
  CI->>Reg: signed artifact
  Reg-->>D: deploy ok`,
    coreLayers: [
      { layer: 'Plan', responsibility: 'Threat model + STRIDE.' },
      { layer: 'Code', responsibility: 'SAST + secrets scan.' },
      { layer: 'Build', responsibility: 'SCA + SBOM + container hardening + image scan.' },
      { layer: 'Deploy', responsibility: 'Sigstore + IaC scan + config hardening.' },
      { layer: 'Run', responsibility: 'Runtime monitor + SIEM + drift detection.' },
    ],
    lld: `flowchart LR
  PR --> SAST[SAST: SonarQube/Bandit]
  PR --> Secrets[Gitleaks/TruffleHog]
  PR --> Snyk[Snyk SCA]
  PR --> CycloneDX[SBOM gen]
  PR --> Build[Docker build hardened]
  Build --> Trivy[Trivy image scan]
  Trivy --> Sigstore[Sign artifact]
  Sigstore --> Deploy
  Deploy --> Falco[Falco runtime]
  Falco --> SIEM`,
    problem: 'Security as phase = late incidents. Security as pipeline = caught at PR.',
    whyThisApproach: 'Each gate has a specific control class. Composed pipeline catches code, dependency, secrets, container, IaC, runtime risks.',
    whenToUse: ['Every production team', 'Multi-team enterprise', 'Regulated industries'],
    whenNotToUse: ['Solo prototype'],
    input: 'PR with code change',
    process: ['Threat model (per feature)', 'SAST + secrets', 'SCA + SBOM', 'Build + container scan', 'Sign + IaC scan + deploy', 'Runtime monitor'],
    output: 'Deployed signed artifact + SBOM + control trail',
    alternatives: [
      { name: 'Security as QA-only phase', tradeoff: 'Late detection; expensive fixes' },
      { name: 'Security as pipeline (this)', tradeoff: 'Best practice; ops cost' },
      { name: 'Security as runtime-only', tradeoff: 'Catches what slipped; doesn\'t prevent' },
    ],
    challenges: ['False-positive fatigue', 'Gate latency in CI', 'Tool sprawl (Snyk + SAST + SBOM + ...)'],
    edgeCases: [
      { case: 'Critical CVE found in dep mid-PR', solution: 'Block merge; create remediation plan; document if accepted risk' },
      { case: 'Tooling false positive', solution: 'Suppress with rationale + ticket; not silent ignore' },
    ],
    failureModes: [
      { mode: 'Snyk reports failed but ignored', detect: 'PR audit', recover: 'Hard CI gate' },
      { mode: 'Container shipped with root user', detect: 'Trivy + runtime detection', recover: 'Dockerfile fix + redeploy' },
    ],
    monitoring: ['Per-stage gate pass rate', 'Findings per PR', 'CVE remediation lead time', 'Container compliance %'],
    testing: ['Pen test annual', 'CI gate drill', 'Container escape drill', 'Secrets scan synthetic'],
    security: ['Pipeline itself secured (signed runners, restricted secrets access)', 'Audit chain on every deploy'],
    scaling: ['Per-service pipeline', 'Shared scanner cluster', 'Cached SBOM per dep'],
    maturity: { mvp: 'Security as QA gate', production: 'Full shift-left + Snyk + container hardening + signed artifacts', enterprise: 'Per-tenant isolation + automated red-team + AI-extensions' },
    limitations: ['Tool false positives', 'Some attacks (insider) bypass', 'Gate latency adds CI time'],
    projectFit: ['.github/workflows/security.yml', 'Dockerfile (hardened)', 'docs/security/pipeline.md', '/admin/guardrails/deep — AI runtime guardrails'],
    interviewLine: 'Security is NOT a phase, it\'s embedded in SDLC. Snyk + SAST + SCA + secrets + container hardening + signed artifacts + runtime monitoring.',
    implementationSteps: [
      { step: 'Plan', logic: 'Threat model + STRIDE before code.' },
      { step: 'Code', logic: 'SAST (SonarQube/Bandit) + secrets scan (gitleaks).' },
      { step: 'Build', logic: 'Snyk SCA + CycloneDX SBOM + Docker hardening + Trivy image scan.' },
      { step: 'Deploy', logic: 'Sigstore signing + IaC scan (tfsec) + config hardening.' },
      { step: 'Run', logic: 'Falco runtime + OTel + SIEM + drift detection.' },
      { step: 'Feedback', logic: 'Runtime findings → next plan iteration.' },
    ],
    codeExample: { language: 'yaml', code: `# .github/workflows/security.yml — full DevSecOps pipeline
name: Security Pipeline
on: [pull_request, push]

jobs:
  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube SAST
        uses: SonarSource/sonarqube-scan-action@v4
      - name: Bandit (Python)
        run: bandit -r src/ -f json -o bandit.json

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2

  sca:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Snyk dependency scan
        uses: snyk/actions/python@master
        env: { SNYK_TOKEN: \${{ secrets.SNYK_TOKEN }} }
        with:
          args: --severity-threshold=high

  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate CycloneDX SBOM
        run: |
          pip install cyclonedx-bom
          cyclonedx-py -o sbom.json

  container:
    runs-on: ubuntu-latest
    needs: [sast, secrets, sca]
    steps:
      - uses: actions/checkout@v4
      - name: Docker build (hardened)
        run: docker build -t app:\${{ github.sha }} .
      - name: Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: app:\${{ github.sha }}
          severity: HIGH,CRITICAL
          exit-code: 1
      - name: Sigstore sign
        uses: sigstore/cosign-installer@v3
      - run: cosign sign app:\${{ github.sha }}

  iac:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/tfsec-action@v1
      - name: Checkov
        uses: bridgecrewio/checkov-action@master` },
    realUseCase: 'Pre-pipeline: 4 security incidents per quarter (1 hardcoded secret, 1 CVE in production, 1 root container, 1 unsigned artifact). Adopted full DevSecOps pipeline: SAST + Snyk SCA + gitleaks + container hardening + Sigstore + Trivy + tfsec. Next quarter: 0 incidents; 47 PR-stage findings caught + remediated; team velocity unchanged.',
    prosCons: {
      pros: ['Catches risks at PR (cheapest)', 'Audit-ready trail', 'Compliance evidence built-in', 'Velocity preserved'],
      cons: ['Tool sprawl', 'False positive fatigue', 'Pipeline maintenance ops cost'],
    },
    comparison: { left: 'Security as phase (QA-only)', right: 'Shift-left pipeline (this)', rows: [
      { aspect: 'Detection lead time', left: 'Days-weeks', right: 'PR-time' },
      { aspect: 'Cost to fix', left: 'High (post-merge)', right: 'Low (PR feedback)' },
      { aspect: 'Audit evidence', left: 'Manual', right: 'Automated' },
      { aspect: 'Compliance burden', left: 'High', right: 'Lower (built-in)' },
    ] },
    solutions: [
      { problem: 'Hardcoded secrets', solution: 'gitleaks PR gate' },
      { problem: 'Vulnerable dependency', solution: 'Snyk SCA + auto-PR for fixes' },
      { problem: 'Root container', solution: 'Dockerfile lint + Trivy scan' },
      { problem: 'Unsigned artifact', solution: 'Sigstore mandatory at push' },
    ],
    bestPractices: { do: ['Shift-left every stage', 'Hard gates (block PR)', 'Hardened Docker baseline', 'SBOM per build', 'Signed artifacts', 'Runtime monitoring'], avoid: ['Security as QA-only phase', 'Soft gates (warn-only)', 'Unsigned artifacts', 'No SBOM'], optimize: ['Cached SBOMs', 'Parallel scans', 'Suppression with rationale', 'Auto-PR for dep fixes'] },
    antiPatterns: ['Security as phase', 'Soft gates', 'No SBOM', 'Unsigned deploys', 'No runtime monitoring'],
    testTypes: ['SAST drill', 'SCA drill (synthetic CVE)', 'Secrets scan drill', 'Container scan drill', 'Sigstore verify drill'],
    testScenarios: [
      { scenario: 'Hardcoded secret introduced', expected: 'gitleaks blocks PR' },
      { scenario: 'Vulnerable dep added', expected: 'Snyk SCA blocks; auto-PR for fix' },
      { scenario: 'Root user in Dockerfile', expected: 'Trivy + lint flag' },
      { scenario: 'Unsigned artifact', expected: 'Deploy fails verification' },
    ],
    testData: [
      { type: 'Synthetic CVE corpus', example: 'Known-vulnerable deps for SCA testing' },
      { type: 'Hardened Dockerfile reference', example: 'Distroless + non-root + read-only FS' },
    ],
    debuggingChecklist: ['Gate failed? Severity threshold + tool config', 'False positive? Suppression with rationale', 'Slow CI? Parallelize scans + cache'],
    productionIssues: [
      { issue: 'Hardcoded API key in commit', rootCause: 'No secrets gate. gitleaks added; auto-rotated key.' },
      { issue: 'Critical CVE in prod for 6 weeks', rootCause: 'No SCA. Snyk added; auto-PR enabled.' },
    ],
    performance: ['SAST: ~2-5 min per PR', 'SCA (Snyk): ~1-3 min', 'Container scan: ~3-8 min', 'Total pipeline: ~10-20 min'],
    costConsiderations: ['Snyk: ~$25-100/dev/mo', 'CI compute: marginal', 'False-positive triage: ops time'],
    observability: ['Per-stage gate pass rate', 'Findings per PR', 'CVE remediation lead time', 'Container compliance'],
    metrics: [
      { name: 'security_gate_pass_rate{stage}', example: 'Gauge per stage' },
      { name: 'security_findings_total{tool,severity}', example: 'Counter; trend per quarter' },
      { name: 'cve_remediation_lead_time_hours', example: 'Histogram; target p95 < 48h' },
    ],
    tradeoffs: [
      { decision: 'Severity threshold', tradeoff: 'Strict = blocks more; gate noise' },
      { decision: 'Tool count', tradeoff: 'More = comprehensive; sprawl' },
    ],
    decisionMatrix: [
      { option: 'Full shift-left (this)', whenToUse: 'Production team' },
      { option: 'SAST + SCA only', whenToUse: 'Small team starting out' },
    ],
    starStory: {
      situation: '4 security incidents per quarter pre-pipeline.',
      task: 'Cut incident rate without slowing delivery.',
      action: 'Adopted full shift-left: SAST + Snyk + gitleaks + container hardening + Sigstore + Trivy + tfsec. Hard gates per PR.',
      result: '0 incidents next quarter. 47 PR-stage findings caught. Velocity unchanged.',
    },
    interviewTraps: ['Security as QA-phase', 'Soft gates', 'No SBOM', 'Unsigned artifacts'],
    finalScript: 'I use Snyk as part of a shift-left DevSecOps strategy to scan dependencies, enforce secure coding, and protect the supply chain. I extend this with OWASP Top 10 controls and AI-specific security measures like prompt-injection defense, model integrity checks, and runtime guardrails to ensure end-to-end system security. Every stage has automated gates: SAST + secrets at code, SCA + SBOM + container scan at build, Sigstore + IaC scan at deploy, runtime monitoring at run. PRs that introduce high-severity findings cannot merge.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 3 — CLOUD + SOC2 + IAM
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'cloud-soc2-iam',
    title: '3. Cloud + SOC2 + IAM — encryption, network isolation, compliance',
    status: 'shipped',
    coreConcept: 'Cloud security maps to SOC2\'s 5 trust principles: Security (IAM + zero trust), Availability (HA + DR), Processing Integrity (validation), Confidentiality (encryption), Privacy (consent + data minimization). IAM least-privilege + KMS + private network + centralized logging.',
    oneLiner: 'SOC2 trust principles drive cloud architecture: IAM + encryption + network isolation + logging + DR.',
    businessContext: 'Without SOC2 alignment: missed compliance, breach exposure, audit findings. With SOC2: structured cloud architecture + audit-ready evidence + customer trust.',
    fiveW: {
      what: 'A cloud architecture aligned to SOC2: IAM (RBAC + ABAC + MFA + key rotation), encryption (KMS + TLS 1.2+ + Vault for secrets), network (VPC + private subnets + WAF), logging (centralized + SIEM + retention), backup (automated + multi-region DR + RTO/RPO), AI-specific (private endpoints + cost rate limiting + model integrity).',
      why: 'Each SOC2 principle maps to specific controls. Together they form an audit-ready posture.',
      where: 'Cloud-native deployment.',
      when: 'Day 1 of any cloud workload.',
      who: 'SRE + security + compliance.',
    },
    interview30s: 'I align cloud security with SOC2\'s five trust principles. Security: IAM least-privilege + MFA + key rotation + zero trust. Availability: HA + autoscaling + multi-region DR with defined RTO/RPO. Processing Integrity: validation + testing + signed builds. Confidentiality: encryption at rest (AES-256/KMS) + in transit (TLS 1.2+) + secrets in Vault, never env vars. Privacy: consent + data minimization + retention policy. AI extensions: private endpoints for model APIs, cost rate limiting for token abuse, embedding encryption, model integrity checks. Centralized logging + SIEM ties it together with real-time alerting.',
    hld: `flowchart TB
  User --> CDN[CDN + WAF]
  CDN --> APIGW[API Gateway Auth + Rate Limit]
  APIGW --> Backend[Backend Private subnet]
  Backend --> AISvc[AI svc Private endpoint]
  Backend --> DB[(Encrypted DB)]
  AISvc --> ML[ML model Encrypted]
  Backend -.audit.-> Logs[Centralized logging]
  Logs --> SIEM
  SIEM --> Alert
  IAM[IAM least-priv + MFA + rotation] -.-> Backend
  KMS[KMS] -.-> DB
  KMS -.-> ML
  Vault[Vault secrets] -.-> Backend`,
    networkFlow: `flowchart LR
  Public[Public internet] --> WAF
  WAF --> APIGW[API Gateway]
  APIGW -->|TLS 1.2+| VPC[Private VPC]
  VPC --> Backend
  VPC --> DB[(KMS-encrypted)]
  VPC -.private endpoint.-> ML[ML provider]`,
    flowchart: `flowchart LR
  Q[New cloud workload] --> S1[SOC2 mapping]
  S1 --> S2[IAM design]
  S2 --> S3[Encryption everywhere]
  S3 --> S4[Network isolation]
  S4 --> S5[Logging + SIEM]
  S5 --> S6[Backup + DR]`,
    sequence: `sequenceDiagram
  participant U as User
  participant WAF
  participant GW as API GW
  participant BE as Backend
  participant DB
  participant Log
  U->>WAF: HTTPS
  WAF->>GW: validated
  GW->>BE: with JWT + MFA
  BE->>DB: encrypted query
  DB-->>BE: encrypted result
  BE->>Log: audit row
  BE-->>U: response`,
    coreLayers: [
      { layer: 'Edge', responsibility: 'CDN + WAF + DDoS protection.' },
      { layer: 'IAM', responsibility: 'RBAC + ABAC + MFA + key rotation + service accounts.' },
      { layer: 'Network', responsibility: 'VPC + private subnets + firewall + restricted ports.' },
      { layer: 'Encryption', responsibility: 'KMS at rest + TLS 1.2+ in transit + Vault for secrets.' },
      { layer: 'Logging', responsibility: 'Centralized + SIEM + real-time alerts + retention policy.' },
      { layer: 'Backup + DR', responsibility: 'Automated + multi-region + RTO/RPO defined.' },
      { layer: 'AI extensions', responsibility: 'Private endpoints + rate limiting + model integrity.' },
    ],
    lld: `flowchart LR
  IAM --> Service[Service identity]
  Service --> Vault[Vault token]
  Service --> KMS[KMS key]
  Service --> DB
  AppLog --> Loki
  Trace --> Tempo
  Metric --> Prom
  Loki --> SIEM
  Prom --> Alert`,
    problem: 'Cloud workloads default-insecure. Public S3 buckets, no IAM control, hardcoded secrets, missing logs — common breach paths.',
    whyThisApproach: 'SOC2 trust principles map to specific controls; layered defense covers edge, app, data, ops.',
    whenToUse: ['Any cloud workload', 'Customer-facing system', 'Regulated industry'],
    whenNotToUse: ['Local-only dev'],
    input: 'New cloud workload requirement',
    process: ['SOC2 principle mapping', 'IAM design', 'Encryption everywhere', 'Network isolation', 'Logging + SIEM', 'Backup + DR'],
    output: 'Production-ready cloud architecture + SOC2 evidence package',
    alternatives: [
      { name: 'Default cloud config', tradeoff: 'Fast; insecure' },
      { name: 'SOC2-aligned (this)', tradeoff: 'Audit-ready; ops cost' },
      { name: 'Vendor managed', tradeoff: 'Less control; faster' },
    ],
    challenges: ['IAM complexity (RBAC + ABAC)', 'Multi-region DR cost', 'Compliance audit overhead'],
    edgeCases: [
      { case: 'Need cross-region access for ML model', solution: 'Private endpoint + IAM + audit' },
      { case: 'Service account leaked', solution: 'Rotate immediately + revoke + audit access trail' },
    ],
    failureModes: [
      { mode: 'Public S3 bucket exposes data', detect: 'Cloud posture scanner', recover: 'Lock down + audit access; notify if accessed' },
      { mode: 'IAM over-permissioned', detect: 'AccessAnalyzer / similar', recover: 'Tighten policy + service-account audit' },
      { mode: 'Encryption disabled (cost saving)', detect: 'Config audit', recover: 'Re-enable + key rotation' },
    ],
    monitoring: ['IAM policy drift', 'Encryption coverage', 'Logging completeness', 'Backup success rate', 'DR drill frequency'],
    testing: ['Pen test', 'Cloud posture scan', 'DR drill quarterly', 'Backup restore drill'],
    security: ['SOC2 audit-ready', 'IAM least-privilege enforced', 'Encryption everywhere'],
    scaling: ['Per-tenant IAM', 'Multi-region routing', 'Read replicas'],
    maturity: { mvp: 'Default cloud + manual IAM', production: 'SOC2-aligned + automated DR', enterprise: 'Per-tenant isolation + automated compliance reports + continuous posture monitoring' },
    limitations: ['DR is expensive', 'IAM tuning ongoing', 'Compliance audits annual'],
    projectFit: ['terraform/ — IaC for SOC2-aligned infra', 'docs/security/cloud-soc2.md', '/admin/rbac/deep — three-layer access control', '/admin/architect/deep — system view'],
    interviewLine: 'I align cloud security with SOC2: security, availability, processing integrity, confidentiality, privacy. IAM least-privilege + encryption + network isolation + logging + DR.',
    implementationSteps: [
      { step: 'IAM design', logic: 'RBAC + ABAC + MFA + key rotation; service accounts separate.' },
      { step: 'Encryption everywhere', logic: 'KMS at rest, TLS 1.2+ transit, Vault for secrets (never env).' },
      { step: 'Network isolation', logic: 'VPC + private subnets + WAF + restricted ports.' },
      { step: 'Logging + SIEM', logic: 'Centralized; real-time alerts; retention policy defined.' },
      { step: 'Backup + DR', logic: 'Automated + multi-region; RTO/RPO defined; quarterly drill.' },
      { step: 'AI extensions', logic: 'Private endpoints + rate limit + model integrity + embedding encrypt.' },
    ],
    codeExample: { language: 'hcl', code: `# terraform/main.tf — SOC2-aligned cloud architecture
resource "aws_kms_key" "data_key" {
  description             = "Customer-data encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true   # automatic annual rotation
  policy = data.aws_iam_policy_document.kms_policy.json
}

resource "aws_s3_bucket" "data" {
  bucket = "documind-data-\${var.env}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_enc" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data_key.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_block" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role" "service_role" {
  name = "documind-svc-\${var.env}"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  # Least-privilege; no wildcard actions
}

resource "aws_vpc" "main" {
  cidr_block         = "10.0.0.0/16"
  enable_dns_support = true
}

resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 4, count.index)
  availability_zone = data.aws_availability_zones.azs.names[count.index]
  # NO map_public_ip_on_launch
}

resource "aws_cloudtrail" "audit" {
  name                          = "documind-audit"
  s3_bucket_name                = aws_s3_bucket.audit_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true   # tamper detection
  kms_key_id                    = aws_kms_key.data_key.arn
}` },
    realUseCase: 'Pre-SOC2: 3 audit findings (public S3, IAM over-permissioned, no encryption on RDS). Adopted SOC2-aligned IaC: KMS + private VPC + IAM least-privilege + CloudTrail with log validation + automated DR. Next audit: 0 findings; SOC2 Type II achieved.',
    prosCons: {
      pros: ['Audit-ready posture', 'Layered defense', 'Customer trust signal', 'Compliance evidence built-in'],
      cons: ['Multi-region DR expensive', 'IAM tuning ongoing', 'Compliance audit overhead'],
    },
    comparison: { left: 'Default cloud config', right: 'SOC2-aligned (this)', rows: [
      { aspect: 'Public exposure risk', left: 'Common', right: 'Locked down by default' },
      { aspect: 'Encryption coverage', left: 'Partial', right: 'Everywhere' },
      { aspect: 'Audit findings', left: '3-10 typical', right: '0 typical' },
      { aspect: 'DR readiness', left: 'Untested', right: 'Quarterly drill' },
    ] },
    solutions: [
      { problem: 'Public S3 exposure', solution: 'public_access_block + IaC enforce' },
      { problem: 'IAM over-permission', solution: 'AccessAnalyzer + tighten policies' },
      { problem: 'Unencrypted data', solution: 'KMS by default + encryption check in IaC' },
      { problem: 'No logs', solution: 'CloudTrail + log validation + multi-region' },
      { problem: 'Backup never tested', solution: 'Quarterly DR drill + RTO/RPO measured' },
    ],
    bestPractices: { do: ['IAM least-privilege', 'Encryption everywhere (KMS + TLS)', 'Vault for secrets', 'Centralized logging + SIEM', 'Multi-region DR + quarterly drill', 'IaC with security scanning'], avoid: ['Hardcoded secrets', 'Wildcard IAM permissions', 'Public buckets', 'Disabled encryption', 'No DR drill'], optimize: ['Per-tenant key rotation', 'Cross-region read replicas', 'Cost-aware DR (warm vs hot)'] },
    antiPatterns: ['Hardcoded credentials', 'Public buckets', 'Wildcard IAM', 'No encryption', 'No DR drill'],
    testTypes: ['Cloud posture scan (Trivy IaC, tfsec)', 'IAM access analysis', 'DR drill quarterly', 'Backup restore drill', 'Pen test annual'],
    testScenarios: [
      { scenario: 'New S3 bucket', expected: 'Public-access block enforced; KMS encryption' },
      { scenario: 'New service account', expected: 'Least-privilege; rotation policy' },
      { scenario: 'DR drill', expected: 'RTO < target; data restored' },
      { scenario: 'IaC PR', expected: 'tfsec + Checkov gate' },
    ],
    testData: [
      { type: 'Reference IaC', example: 'SOC2-aligned terraform modules' },
      { type: 'Pen test corpus', example: 'OWASP-style probes against deployed env' },
    ],
    debuggingChecklist: ['Audit finding? Map to SOC2 principle + control', 'IAM over-permission? AccessAnalyzer + tighten', 'Cost spike? Per-service tag + investigate'],
    productionIssues: [
      { issue: 'Public S3 exposed customer data', rootCause: 'Default config + missing public_access_block. IaC fix + retro audit.' },
      { issue: 'IAM service account compromised', rootCause: 'Wildcard policy + no rotation. Tightened + rotated + audit.' },
      { issue: 'DR untested for 18 months', rootCause: 'No drill cadence. Quarterly drill + RTO measured.' },
    ],
    performance: ['IAM eval: ~5-20ms p95', 'KMS encrypt/decrypt: ~5-15ms p95', 'TLS handshake: ~50-100ms cold', 'CloudTrail write: async'],
    costConsiderations: ['KMS: ~$1/key/mo + per-call', 'Multi-region DR: ~2x base infra', 'CloudTrail: ~$2/100K events', 'WAF: ~$1-5/mo per ACL + per-request'],
    observability: ['IAM policy drift', 'Encryption coverage %', 'Backup success rate', 'DR drill outcomes', 'Per-service cost'],
    metrics: [
      { name: 'cloud_iam_policy_drift_total', example: 'Counter; alert if > 0' },
      { name: 'cloud_encryption_coverage_rate', example: 'Gauge; target = 1.0' },
      { name: 'cloud_dr_drill_rto_seconds{quarter}', example: 'Gauge; trend' },
      { name: 'cloud_audit_findings_total{severity}', example: 'Counter; target zero high' },
    ],
    tradeoffs: [
      { decision: 'Multi-region DR', tradeoff: 'Resilient + 2x cost' },
      { decision: 'IAM granularity', tradeoff: 'Strict = secure + ops complexity' },
      { decision: 'Encryption everywhere', tradeoff: 'Defense + minor latency' },
    ],
    decisionMatrix: [
      { option: 'SOC2-aligned (this)', whenToUse: 'Customer-facing + regulated' },
      { option: 'SOC2 Lite (subset)', whenToUse: 'Internal tool' },
      { option: 'Default cloud', whenToUse: 'Solo prototype only' },
    ],
    starStory: {
      situation: 'Pre-SOC2 audit found 3 critical findings (public S3, IAM, RDS encryption).',
      task: 'Achieve SOC2 Type II within 9 months.',
      action: 'Adopted full SOC2 alignment via IaC: KMS + private VPC + IAM least-privilege + CloudTrail validated + multi-region DR. Quarterly DR drill. Cloud posture scanning in CI.',
      result: '0 audit findings next audit. SOC2 Type II achieved. Customer trust signal opened 3 enterprise deals.',
    },
    interviewTraps: ['Hardcoded credentials', 'Public buckets', 'Wildcard IAM', 'No DR drill', 'Default cloud config'],
    finalScript: 'I implement security using a layered approach aligned to SOC2\'s five trust principles. Security: IAM least-privilege + MFA. Availability: HA + multi-region DR with defined RTO/RPO. Processing Integrity: validation + signed builds. Confidentiality: encryption at rest (KMS) + in transit (TLS 1.2+) + secrets in Vault. Privacy: consent + data minimization. AI extensions: private endpoints, cost rate limiting, embedding encryption, model integrity. Centralized logging + SIEM ties it together with real-time alerting. The principle is fail-closed: every layer has a default-secure posture; any drift is detected by automated scanning.',
  },
];

export default function SecurityDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Enterprise security playbook (deep dive)</h1>
        <p className="design-areas-sub">
          OWASP Top 10:2025 + STRIDE threat modeling + AI-specific risks (prompt
          injection, model poisoning, embedding leakage). Shift-left DevSecOps
          pipeline (Snyk + SAST + SCA + secrets + container hardening + signed
          artifacts). Cloud architecture aligned to SOC2&apos;s five trust principles
          (security, availability, integrity, confidentiality, privacy) with
          IAM, KMS, network isolation, centralized logging, multi-region DR.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </div>
  );
}
