'use client';

/**
 * Technical evolution + efficiency (deep dive).
 *
 * Two topics:
 *  1. tech-radar-paved-road — Tech Radar (Adopt/Trial/Assess/Hold) +
 *     paved-road / service chassis + deprecation policy. The
 *     "evolution control system" that limits choice + accelerates
 *     consistent shipping.
 *  2. finops-devex — FinOps (cost as a design decision) + DevEx
 *     (developer experience as a defect-prevention strategy). The
 *     "sustainability discipline pair".
 *
 * Composes with /admin/cicd/deep + /admin/principles/deep +
 * /admin/checklist/deep.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — Tech Radar + paved road + deprecation policy
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'tech-radar-paved-road',
    title: '1. Tech Radar + paved road + deprecation — the evolution control system',
    status: 'shipped',
    coreConcept:
      'Standardize the path. Limit choices. Enable speed. Three components: Tech Radar (Adopt / Trial / Assess / Hold rings, updated quarterly, backed by ADRs, enforced via templates + CI lint) constrains what teams can pick. Paved road / service chassis (logging + tracing + metrics + auth + RBAC + health probes + CI/CD pipeline + dashboards + AI guardrail stubs) ships ALL of that in <1 hour for any new service. Deprecation policy (APIs N + N-1 supported with 90-180 day notice, runtimes N-1, SDKs 2 versions max) prevents zombie services. Together: speed without sprawl.',
    oneLiner: 'Tech radar limits choice. Paved road accelerates the path. Deprecation kills zombies. Three together = speed without sprawl.',
    businessContext:
      'Without these three: every team picks their own ORM, logging library, deployment style. Onboarding takes 8 weeks. Cross-team incident response collapses (no shared mental model). Tech debt compounds because old patterns are never explicitly retired — they just accumulate. The Tech Radar + paved road + deprecation triple cuts onboarding to 4 weeks AND prevents the sprawl that kills 5-year-old codebases.',
    fiveW: {
      what: 'Three governance instruments (radar + chassis + deprecation) that together constrain choice, accelerate consistent shipping, and prevent sprawl.',
      why: 'Pure freedom = sprawl. Pure control = bottleneck. The triple finds the productive middle: standard path is FAST + cheap, deviation requires explicit ADR.',
      where: 'Org-wide policy + per-service application. Radar lives in `docs/architecture/tech-radar.md`; chassis in `templates/service-chassis/`; deprecation in `docs/architecture/deprecation-policy.md`.',
      when: 'Day 1 of a multi-team org. Single-team startups can defer until team #2 lands.',
      who: 'ARB owns the radar + deprecation policy; platform team owns the chassis. Service owners consume.',
    },
    interview30s:
      "Three pieces. Tech Radar — Adopt / Trial / Assess / Hold rings, ADR-backed, quarterly review. Limits what teams can pick — Hold means CI blocks new uses. Paved road / service chassis — every new service spins up in <1 hour with logging + tracing + metrics + auth + health probes + CI/CD + dashboards + AI hooks already wired. Deprecation policy — APIs support current + previous major, runtimes N-1, 90 days internal notice / 180 days external, CI warnings then fail after EOL. Together: a new team ships consistently fast; old patterns retire automatically.",
    hld: `flowchart LR
  Radar[Tech Radar Adopt/Trial/Assess/Hold] --> Choice[Choice constrained]
  Chassis[Service chassis] --> Speed[Bootstrap < 1h]
  Deprecation[Deprecation policy] --> Retire[Old retired automatically]
  Choice --> Service[New service]
  Speed --> Service
  Retire --> Service
  Service --> Production[Consistent prod shape]`,
    flowchart: `flowchart TD
  Q1{Tech radar exists?} -- no --> Sprawl[Tool sprawl, resume-driven dev]
  Q1 -- yes --> Q2{Paved road exists?}
  Q2 -- no --> Slow[Each new svc reinvents]
  Q2 -- yes --> Q3{Deprecation policy?}
  Q3 -- no --> Zombies[Old patterns never retire]
  Q3 -- yes --> Q4{ARB review cadence?}
  Q4 -- no --> Drift[Radar stale]
  Q4 -- yes --> Done[Speed + consistency + retirement]`,
    sequence: `sequenceDiagram
  participant Team as New team
  participant Chassis as Service chassis CLI
  participant ARB
  participant Prod
  Team->>Chassis: new-service init my-svc
  Chassis-->>Team: scaffolded with logging/tracing/auth/CI
  Team->>Team: implement domain logic
  Team->>ARB: any non-Adopt deps?
  ARB-->>Team: ADR required for Trial / Hold deviation
  Team->>Prod: deploy via paved CI/CD
  Note over Team,Prod: < 1 hour to first production deploy`,
    coreLayers: [
      { layer: 'Tech Radar', responsibility: 'Adopt / Trial / Assess / Hold rings; ADR-backed; quarterly ARB review; CI lint enforces.' },
      { layer: 'Service chassis', responsibility: 'Logging + tracing + metrics + auth + RBAC + health probes + CI/CD + dashboards + alerts + AI guardrail stubs.' },
      { layer: 'Deprecation policy', responsibility: 'APIs N + N-1; runtimes N-1; SDKs 2 max; 90d internal / 180d external notice; CI warns → fails on EOL.' },
      { layer: 'ARB', responsibility: 'Approves additions to Adopt; reviews ADR-backed deviations; quarterly cadence.' },
      { layer: 'Templates / lint', responsibility: 'Tools enforce: `cookiecutter` for chassis; `dependency-cruiser` / custom CI checks block Hold-tier deps.' },
    ],
    lld: `classDiagram
  class TechRadar {
    +adopt: Tech[]
    +trial: Tech[]
    +assess: Tech[]
    +hold: Tech[]
    +quarterly_review()
  }
  class ServiceChassis {
    +logging
    +tracing
    +metrics
    +auth
    +ci_cd
    +health_probes
    +ai_hooks
    +bootstrap_minutes: 60
  }
  class DeprecationPolicy {
    +api_versions_supported: 2
    +internal_notice_days: 90
    +external_notice_days: 180
    +ci_warn_then_fail
  }`,
    coreBuildingBlocks: [
      'docs/architecture/tech-radar.md (or Backstage radar plugin)',
      'templates/service-chassis/ (cookiecutter or scaffold tool)',
      'docs/architecture/deprecation-policy.md + per-API EOL dates',
      'ARB charter + quarterly cadence + ADR template',
      'CI lint that blocks Hold-tier deps (dependency-cruiser, custom check, npm overrides, etc.)',
      'CI warning → fail-on-EOL annotation per deprecated API',
      'Onboarding doc that walks: chassis init → first deploy in <1 hour',
    ],
    architectureRelevance: {
      backend: 'Universal — every backend service derives from chassis.',
      rag: 'Same; chassis gains AI-specific hooks (prompt registry, eval harness, guardrail stubs).',
      ai: 'Tech Radar applies to LLM providers + vector DBs + embedding models same as any other tech.',
      microservices: 'Chassis IS the microservices day-1 starter. Without it, every team reinvents.',
    },
    problem:
      "Multi-team org, no governance. Team A picks Postgres + RabbitMQ + Datadog; team B picks MySQL + Kafka + New Relic; team C picks DynamoDB + SQS + custom logging. 6 months later: cross-team incident requires 3 different debugging skill sets; onboarding is service-specific not org-wide; old patterns never explicitly retire. Velocity drops to crawl.",
    whyThisApproach:
      "Pure freedom doesn't scale; pure control bottlenecks. The triple is the productive middle: 80% of work uses Adopt-tier tools via the chassis (fast); 20% justifies deviation via ADR (controlled). Old patterns retire automatically.",
    whenToUse: [
      'Org with > 1 team (the moment a 2nd team forms)',
      'Greenfield org-wide standardization',
      'Post-acquisition / post-merger integration',
      'After a "tech sprawl" incident',
    ],
    whenNotToUse: [
      'Pre-product-market-fit startup (premature governance)',
      'Single-team org (overhead exceeds value)',
    ],
    input: 'Existing service inventory + dep audit + team list + org topology.',
    process: [
      'Audit current state: every service\'s tech stack catalogued.',
      'ARB drafts initial Tech Radar (4 rings, ~30-50 entries).',
      'Platform team builds the chassis to consume Adopt-tier tools only.',
      'Deprecation policy drafted: which APIs are N-1, EOL dates assigned.',
      'CI lint added: block Hold-tier deps; warn-then-fail on deprecated APIs.',
      'Onboarding doc: "from `chassis init` to first prod deploy in <1 hour".',
      'Quarterly ARB review: rotate items between rings; deprecate explicit.',
    ],
    output: 'New services consistent in shape; old patterns retired on schedule; cross-team debugging works because mental model is shared.',
    implementationSteps: [
      { step: 'Initial radar', logic: '4 rings × 4 quadrants (Languages / Frameworks / Tools / Platforms). 30-50 entries. ADR per change.' },
      { step: 'Service chassis init', logic: 'Cookiecutter or yeoman generator. `chassis init my-svc` produces a working repo with CI/CD wired.' },
      { step: 'Deprecation policy doc', logic: 'API version SUPPORTED matrix. EOL dates explicit. 90d internal / 180d external notice.' },
      { step: 'CI lint Hold-tier', logic: 'dependency-cruiser config or custom check that fails on import of Hold-listed deps.' },
      { step: 'CI warn-then-fail EOL', logic: 'Cron-based: warn 90 days before EOL; fail on EOL date. Annotation per deprecated import.' },
      { step: 'Quarterly ARB cadence', logic: 'Calendar event. Review outstanding ADRs. Move items between rings. Update radar published version.' },
      { step: 'Onboarding doc', logic: 'Step-by-step: chassis init → fill in domain logic → CI green → first deploy. Target: < 1 hour for a developer who knows the language.' },
    ],
    codeExample: {
      language: 'yaml',
      code: `# docs/architecture/tech-radar.yaml — single source of truth
version: 2026-Q2
quadrants:
  - languages-and-frameworks
  - tools
  - platforms
  - techniques

rings:
  adopt:
    - { name: Python 3.11, quadrant: languages-and-frameworks, since: 2024-Q1 }
    - { name: FastAPI,     quadrant: languages-and-frameworks, since: 2023-Q3 }
    - { name: PostgreSQL,  quadrant: platforms, since: 2022-Q1 }
    - { name: Ruff,        quadrant: tools, since: 2025-Q2 }
    - { name: OpenTelemetry, quadrant: tools, since: 2024-Q4 }
  trial:
    - { name: Pydantic v2, quadrant: languages-and-frameworks, since: 2025-Q4 }
    - { name: Qdrant,      quadrant: platforms, since: 2025-Q3 }
  assess:
    - { name: Polars,      quadrant: tools, since: 2026-Q1 }
  hold:
    - { name: SQLAlchemy 1.x, quadrant: tools, eol: 2026-Q3, replacement: SQLAlchemy 2.x }
    - { name: flake8,         quadrant: tools, eol: 2025-Q4, replacement: Ruff }
    - { name: requests,       quadrant: tools, replacement: httpx }

deprecations:
  - { api: /api/v1/old-prompt-format, eol: 2026-09-01, replacement: /api/v2/prompt }


# .github/workflows/ci.yml — block Hold-tier deps
- name: Tech radar — block Hold deps
  run: |
    python scripts/check-tech-radar.py
    # exit non-zero if any import in src/ uses a Hold-listed package


# Service chassis bootstrap (template repo)
$ chassis init my-svc
> Creating my-svc/...
> ✓ Logging (structlog + JSON formatter)
> ✓ Tracing (OpenTelemetry + W3C baggage)
> ✓ Metrics (Prometheus + Grafana dashboard)
> ✓ Auth (JWT + RBAC scaffolds)
> ✓ Health probes (/health/live, /health/ready, /health/startup)
> ✓ CI/CD (.github/workflows/ci.yml + drills.yml)
> ✓ AI guardrail stubs (prompt registry stub + eval harness stub)
> ✓ Compose footer template
> Time: 47s. Ready to git push.`,
    },
    realUseCase:
      'A 200-engineer org migrated to the radar + chassis + deprecation triple over 2 quarters. Onboarding new engineers dropped from 8 weeks to 4 weeks. Cross-team incident MTTR fell ~30% because every service\'s logs / metrics / traces look identical. Three previously-zombie tools (flake8, requests, SQLAlchemy 1.x) retired on explicit timelines without a single "we forgot to migrate" rollback.',
    prosCons: {
      pros: [
        'New service to first deploy in <1 hour',
        'Cross-team debugging works (shared mental model)',
        'Old tools retire on schedule',
        'Onboarding time halves',
        'ADR-backed deviation when needed',
      ],
      cons: [
        'Initial setup: 1-2 quarters platform-team effort',
        'ARB cadence is real engineering hours',
        'Some friction when a team needs a Hold-tier tool urgently',
      ],
    },
    limitations: [
      'Premature for pre-PMF startups',
      'Single-team orgs over-engineer with this',
      'Radar must be enforced (lint) or it\'s decoration',
    ],
    comparison: {
      left: 'Free-for-all',
      right: 'Radar + chassis + deprecation',
      rows: [
        { aspect: 'New service bootstrap', left: 'Days', right: '< 1 hour' },
        { aspect: 'Onboarding time', left: '8 weeks', right: '4 weeks' },
        { aspect: 'Cross-team incident MTTR', left: 'High', right: '-30%' },
        { aspect: 'Tool sprawl', left: 'Inevitable', right: 'Bounded' },
        { aspect: 'Deprecation success', left: 'Rare', right: 'On schedule' },
      ],
    },
    challenges: [
      'Getting senior engineers to accept the radar (looks like loss of agency)',
      'Maintaining the chassis (real ongoing platform-team work)',
      'Quarterly ARB hygiene (cadence slips easily)',
      'Lint enforcement requires custom tooling per language',
    ],
    edgeCases: [
      { case: 'New tool genuinely needs to land mid-quarter', solution: 'Trial ring + ADR + 6-month review; not full Adopt yet' },
      { case: 'Deprecation deadline missed', solution: 'CI fail forces hand. Don\'t extend silently — formal escalation' },
      { case: 'Chassis falls behind on a security patch', solution: 'Platform team treats chassis as a product; security is P0' },
      { case: 'ARB review skipped a quarter', solution: 'Calendar-blocked; missing one is a P2 issue' },
    ],
    solutions: [
      { problem: 'Tool sprawl', solution: 'Tech Radar Hold ring + CI lint blocks new uses' },
      { problem: 'Slow new-service bootstrap', solution: 'Service chassis with all observability + auth + CI/CD pre-wired' },
      { problem: 'Old patterns never retire', solution: 'Deprecation policy with explicit EOL dates + CI warn-then-fail' },
      { problem: 'Cross-team debugging difficulty', solution: 'Chassis enforces shared logging / tracing / metrics shape' },
      { problem: '"Resume-driven development"', solution: 'ADR required for non-Adopt deps; reviewer gates the why' },
    ],
    bestPractices: {
      do: [
        'Quarterly ARB review (calendar-blocked)',
        'ADR-backed every radar movement',
        'CI lint enforces Hold-tier blocks',
        'Chassis owns logging + tracing + metrics + auth + CI/CD',
        'Deprecation EOL dates explicit',
      ],
      avoid: [
        'Radar without enforcement (lint absent)',
        'Chassis without ongoing platform-team ownership',
        'Deprecation without dates ("eventually")',
        'ARB review skipped quarters',
        'Premature governance pre-PMF',
      ],
      optimize: [
        'Quarterly cadence in calendar',
        'Chassis updates push via dependency bot',
        'Auto-generated radar HTML from YAML',
      ],
    },
    antiPatterns: [
      'Radar published once; never updated',
      'Chassis owned by "everyone" (= no one)',
      'Deprecation by Slack message',
      'Tool sprawl via "Trial" abuse',
      'Premature governance pre-PMF',
    ],
    testing: ['Drill: chassis init produces working repo', 'Drill: CI lint blocks Hold-tier import', 'Drill: deprecated API call fails CI on EOL date'],
    testTypes: ['Chassis bootstrap drill', 'Lint-block drill', 'Deprecation enforcement drill'],
    testScenarios: [
      { scenario: '`chassis init my-svc` → working CI in 60s', expected: 'pass' },
      { scenario: 'Import a Hold-listed dep', expected: 'CI fails with link to ADR template' },
      { scenario: 'Call a deprecated API past EOL', expected: 'CI fails with replacement suggestion' },
      { scenario: 'ADR proposes new Adopt entry', expected: 'ARB review + radar update next quarter' },
    ],
    testData: [
      { type: 'Real radar', example: 'docs/architecture/tech-radar.yaml versioned in git' },
      { type: 'Real chassis', example: 'templates/service-chassis/ scaffold' },
    ],
    debuggingChecklist: [
      'Radar published + accessible?',
      'Chassis bootstrap < 1h verified recently?',
      'Deprecation EOL dates explicit + tracked?',
      'CI lint configured to block Hold-tier?',
      'ARB last met when?',
    ],
    productionIssues: [
      { issue: 'New service forgot logging', rootCause: 'Started outside chassis; retrofit + add chassis-init drill' },
      { issue: 'Library X is "Hold" but team A still uses', rootCause: 'CI lint absent or X added pre-policy; grandfather + retire' },
      { issue: 'Onboarding takes 6 weeks not 4', rootCause: 'Chassis docs stale; refresh + run drill' },
    ],
    security: ['Radar restricts Hold-tier deps with known CVEs', 'Chassis includes security headers + secret scan baseline', 'Deprecation removes vulnerable libraries on schedule'],
    performance: [
      'Chassis init: < 1 hour to first deploy',
      'ARB review: 1-2 hours quarterly',
      'CI lint overhead: < 30s per PR',
    ],
    costConsiderations: [
      'Platform team: 2-3 FTE for chassis + radar maintenance',
      'Saves: weeks per new-service bootstrap × N services × eng cost',
    ],
    scaling: ['Chassis evolves with org; v1 → v2 → v3 explicit', 'Radar grows with adopted tech; quadrants stable', 'Per-domain radar variants for diverse orgs'],
    observability: ['Radar version dashboard', 'Chassis version per service', 'Deprecation timeline tracker', 'ARB minutes archive'],
    metrics: [
      { name: 'new_service_bootstrap_minutes_p95', example: '47' },
      { name: 'onboarding_weeks_to_first_pr', example: '4' },
      { name: 'deprecations_completed_on_time_percent', example: '0.92' },
      { name: 'arb_review_cadence_quarterly', example: '1.0' },
    ],
    failureModes: [
      { mode: 'Radar stale', detect: 'Last update > 6 months', recover: 'Force ARB review + ratchet' },
      { mode: 'Chassis drift from latest standards', detect: 'New service vs old chassis differ', recover: 'Platform team upgrade + auto-PR existing services' },
      { mode: 'Deprecation deadline silently extended', detect: 'CI fail bypassed', recover: 'No silent extensions; formal ADR or accept the fail' },
    ],
    tradeoffs: [
      { decision: 'Radar enforced via lint', tradeoff: 'Some friction; bounded sprawl' },
      { decision: 'Chassis ownership', tradeoff: 'Platform-team cost; massive eng-team productivity gain' },
      { decision: 'Hard deprecation deadlines', tradeoff: 'Some pain at EOL; old code actually retires' },
    ],
    decisionMatrix: [
      { option: 'No governance', whenToUse: 'Single-team or pre-PMF' },
      { option: 'Radar only (no chassis)', whenToUse: 'Loose org alignment, no platform-team' },
      { option: 'Radar + chassis only', whenToUse: 'Multi-team, but no legacy debt' },
      { option: 'Triple (recommended)', whenToUse: 'Multi-team, real org with legacy + new builds' },
    ],
    starStory: {
      situation: '200-engineer org. Tool sprawl. Onboarding 8 weeks. Cross-team incidents took 3+ engineers + 4+ hours.',
      task: 'Standardize without bottlenecking.',
      action: 'Stood up ARB. Published Tech Radar (~40 entries). Built service chassis (cookiecutter, ~3 weeks platform-team effort). Wrote deprecation policy with explicit EOL dates. Wired CI lint for Hold-tier blocks + EOL warn/fail.',
      result: 'Onboarding 8 → 4 weeks. New service bootstrap minutes (chassis init → green CI). Cross-team MTTR -30% (shared logging/tracing). 3 zombie tools retired on schedule. ADR throughput up; deviation hidden behind a thin paper-gate.',
    },
    interviewTraps: [
      'Saying "we have a tech radar" without enforcement',
      'No mention of paved road / chassis',
      'Deprecation by Slack',
      'No quarterly cadence',
    ],
    finalScript:
      'Three pieces: Tech Radar (Adopt/Trial/Assess/Hold, ADR-backed, quarterly), service chassis (logging + tracing + metrics + auth + CI/CD wired in <1h bootstrap), deprecation policy (APIs N+N-1, runtimes N-1, 90d internal / 180d external notice, CI warn-then-fail). Together: speed without sprawl. Onboarding halves. Old retires on schedule.',
    alternatives: [
      { name: 'No governance', tradeoff: 'Maximum freedom; sprawl' },
      { name: 'Heavy ARB only', tradeoff: 'Bottleneck; teams work around' },
      { name: 'Triple (this)', tradeoff: 'Investment; sustainable productivity' },
    ],
    monitoring: ['Radar version + ARB cadence dashboard', 'Chassis bootstrap latency dashboard', 'Deprecation timeline tracker'],
    maturity: {
      mvp: 'Radar + paved road basic chassis',
      production: '+ Deprecation policy + CI lint',
      enterprise: '+ Quarterly ARB + per-domain radar variants + auto-upgrade chassis',
    },
    projectFit: ['Multi-team orgs', 'Post-acquisition integration', 'Mature codebases', 'Polyglot stacks'],
    interviewLine: 'Radar + chassis + deprecation. Speed without sprawl. Onboarding halves. Old retires.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — FinOps + DevEx
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'finops-devex',
    title: '2. FinOps + DevEx — cost as a design decision, friction as a defect cause',
    status: 'shipped',
    coreConcept:
      "FinOps treats cost as a first-class architectural property: every architecture decision has a cost curve; resource tagging (team / env / cost_center) makes it observable; budgets + autoscaling at ~60% trigger threshold (not 80-90%) prevent surprise spikes; quarterly right-sizing reviews kill idle dev/QA. DevEx treats developer friction as defect-correlation: slow local setup → engineers skip local testing → bugs ship; slow CI → engineers bypass tests → regressions. The pair is the sustainability discipline — FinOps prevents budget death, DevEx prevents engineer attrition + quality decay.",
    oneLiner: 'FinOps: cost is a design property, not an accounting problem. DevEx: friction in tools = defects in systems.',
    businessContext:
      'A team ships fast, scales fast, ignores cost. 6 months later: surprise $50K monthly bill from one Kafka cluster + one auto-scaled inference fleet. Or: local setup takes 2 days; engineers skip local testing; defects compound. Both kill velocity differently — finance kills the budget, friction kills the people. FinOps + DevEx as a discipline pair prevents both deaths.',
    fiveW: {
      what: 'Two adjacent disciplines that compound. FinOps controls infra cost trajectory. DevEx controls engineer-time waste + quality.',
      why: 'They share the same shape: instrument → measure → budget → optimize → repeat. Different metrics, same cycle. Both compound 5–10× over the year.',
      where: 'Per-service tagging (FinOps) + per-repo `make up` parity (DevEx).',
      when: 'FinOps: month 3 of any cloud project (before it gets expensive). DevEx: day 1 of any team > 1 person.',
      who: 'FinOps: platform + finance partner. DevEx: platform + every engineer.',
    },
    interview30s:
      'FinOps: cost is architecture. Tag every resource with team / env / cost_center. Budgets + autoscale at ~60% (headroom for spikes). Quarterly right-sizing reviews kill idle dev/QA. Pick serverless for spiky / containers for steady / managed-DB for ops-light. DevEx: local setup < 1 hour via DevContainers + Docker Compose + seed data + `make up`. CI < 10 min or engineers bypass it. Service catalog (Backstage) + auto-published API specs + golden-path docs (PR + ADR + runbook + incident templates). The two discipline-pair: FinOps prevents budget death, DevEx prevents engineer attrition.',
    hld: `flowchart LR
  subgraph FinOps
    Tag[Resource tagging] --> Budget[Per-team budgets]
    Budget --> Autoscale[Autoscale at 60 percent]
    Autoscale --> Review[Quarterly right-size]
  end
  subgraph DevEx
    Setup[Local parity in DevContainer] --> Path[Golden path docs]
    Path --> Catalog[Service catalog Backstage]
    Catalog --> Templates[PR ADR runbook templates]
  end`,
    flowchart: `flowchart TD
  Q1{Resource tagging?} -- no --> Surprise[Surprise bills + no per-team accountability]
  Q1 -- yes --> Q2{Autoscale at 60 percent?}
  Q2 -- no --> Spike[Saturation events spike costs]
  Q2 -- yes --> Q3{Local setup less than 1h?}
  Q3 -- no --> Friction[Engineers skip local; bugs ship]
  Q3 -- yes --> Q4{Service catalog?}
  Q4 -- no --> Discoverability[Hard to find APIs / runbooks]
  Q4 -- yes --> Done[FinOps + DevEx healthy]`,
    sequence: `sequenceDiagram
  participant Engineer
  participant LocalEnv as DevContainer
  participant Catalog as Backstage
  participant Cloud
  Engineer->>LocalEnv: make up
  LocalEnv-->>Engineer: full stack running 47s
  Engineer->>Catalog: search inference-svc
  Catalog-->>Engineer: API spec, runbook, owner, on-call
  Engineer->>Cloud: deploy
  Cloud->>Cloud: tagged team=ai cost_center=ai-prod
  Cloud-->>Engineer: live; budget board updated`,
    coreLayers: [
      { layer: 'FinOps tagging', responsibility: 'team / env / cost_center on every resource. Without: no per-team accountability.' },
      { layer: 'FinOps budgets', responsibility: 'Per-service / per-team monthly budgets + alert thresholds.' },
      { layer: 'FinOps autoscale', responsibility: 'Trigger at ~60% (headroom for spin-up time). Idle dev/QA off-hours.' },
      { layer: 'DevEx local', responsibility: 'DevContainer / Docker Compose / seed data → < 1h to first run.' },
      { layer: 'DevEx golden path', responsibility: 'PR template + ADR template + runbook template + incident template.' },
      { layer: 'DevEx catalog', responsibility: 'Backstage / OpsLevel / equivalent — service ownership + APIs + runbooks searchable.' },
    ],
    lld: `classDiagram
  class FinOpsControl {
    +tag(resource)
    +set_budget(team)
    +autoscale_threshold: 0.6
    +quarterly_review()
  }
  class DevExControl {
    +local_setup_minutes: less_60
    +ci_minutes: less_10
    +catalog: Backstage
    +golden_path
  }
  class CostCurve {
    +serverless: spiky
    +container: steady
    +managed: ops_light
  }
  FinOpsControl --> CostCurve`,
    coreBuildingBlocks: [
      'Resource tagging policy: team, env, cost_center, service',
      'Per-team monthly budgets in cloud console + alert at 50/80/100%',
      'Autoscale threshold ~60% (headroom for cold-start)',
      'Idle dev/QA shutdown cron (off-hours)',
      'Quarterly right-sizing review (CPU < 10% sustained → downsize)',
      'DevContainer / Docker Compose / `make up` for local parity',
      'Seed data for offline dev',
      'Service catalog (Backstage / OpsLevel)',
      'Golden-path docs: PR + ADR + runbook + incident templates',
      'Service template (cookiecutter or chassis from topic 1)',
    ],
    architectureRelevance: {
      backend: 'FinOps gates infra choice. DevEx gates onboarding speed.',
      rag: 'FinOps especially critical (token cost). DevEx: local mock for LLM provider so engineers can dev offline.',
      ai: 'Token budget + cost-per-request alerts + per-tenant cost rollups.',
      microservices: 'Tagging at service-level; catalog tracks ownership + on-call rotation.',
    },
    problem:
      'A team scales fast, ignores cost trajectory. Surprise $50K bill from one Kafka cluster + auto-scaled inference fleet. Or local setup takes 2 days, engineers skip local testing, bugs ship to production.',
    whyThisApproach:
      'Both disciplines have the same shape: instrument → measure → budget → optimize → repeat. They compound 5–10× over a year if neglected.',
    whenToUse: [
      'FinOps: month 3 of any cloud project',
      'DevEx: day 1 of any multi-engineer team',
      'Both: org-wide policy + per-service application',
    ],
    whenNotToUse: [
      'Throwaway prototypes',
      'Pre-PMF startups (premature optimization)',
    ],
    input: 'Cloud bill + service inventory + onboarding feedback + dev environment audit.',
    process: [
      'FinOps: audit current bill + tag retroactively. Set budgets per team. Configure autoscale at 60%. Quarterly right-sizing.',
      'DevEx: audit local setup time + CI time + catalog coverage. DevContainer for local parity. Backstage for catalog. Golden-path templates.',
      'Both: dashboard. Cost per service trend; setup time trend; CI duration trend.',
      'Quarterly review: cost trends, DevEx friction reports, action items per team.',
    ],
    output: 'Predictable cost trajectory + 1-hour onboarding + sustainable engineer + budget health.',
    implementationSteps: [
      { step: 'Tag every resource', logic: 'Terraform module with required tags. CI lint blocks PRs that introduce untagged resources.' },
      { step: 'Per-team budgets', logic: 'Cloud-console budgets with alert at 50/80/100% of monthly target.' },
      { step: 'Autoscale at 60%', logic: 'CPU 60% target; headroom for spin-up time. NOT 80-90% — that\'s already saturated.' },
      { step: 'Idle shutdown', logic: 'Cron stops dev/QA off-hours (M-F 7pm → M-F 7am + weekend off).' },
      { step: 'Quarterly right-size', logic: 'Any instance < 10% CPU sustained → downsize. 10-30% → review. > 80% → scale up.' },
      { step: 'DevContainer + make up', logic: 'Single command brings up full stack locally with seed data. Target: < 1 hour for new engineer.' },
      { step: 'Service catalog', logic: 'Backstage. Auto-discover from each repo\'s `catalog-info.yaml`. Owner + on-call + API spec + runbook link per service.' },
      { step: 'Golden-path templates', logic: 'PR template, ADR template (per topic 1), runbook template, incident template. All in `docs/templates/`.' },
    ],
    codeExample: {
      language: 'hcl',
      code: `# terraform/modules/standard-tags/variables.tf — FinOps required tags
variable "team" {
  type        = string
  description = "Owning team. Required for FinOps cost rollup."
}

variable "env" {
  type        = string
  description = "Environment: dev / staging / prod."
  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be dev, staging, or prod."
  }
}

variable "cost_center" {
  type        = string
  description = "Finance cost center for billing."
}

locals {
  required_tags = {
    team        = var.team
    env         = var.env
    cost_center = var.cost_center
    managed_by  = "terraform"
  }
}

# Apply to every resource:
resource "aws_ecs_service" "app" {
  # ...
  tags = local.required_tags
}


# .devcontainer/devcontainer.json — DevEx local parity
{
  "name": "documind-rag",
  "dockerComposeFile": "../docker-compose.yml",
  "service": "dev",
  "workspaceFolder": "/workspace",
  "postCreateCommand": "make up && make seed",
  "extensions": [
    "ms-python.python",
    "charliermarsh.ruff",
    "esbenp.prettier-vscode"
  ],
  "forwardPorts": [3000, 5432, 8084]
}


# Makefile — DevEx golden path
.PHONY: up down seed test
up:        ## Bring up full local stack (postgres, redis, all services)
\tdocker compose up -d --wait
\t@echo "Stack up. Frontend: http://localhost:3000"

seed:      ## Seed dev tenants + sample documents
\tpython scripts/seed_dev.py

test:      ## Run unit + integration tests
\tpytest -q

down:      ## Tear down + remove volumes
\tdocker compose down -v


# scripts/quarterly-rightsize.py — FinOps quarterly review
# For each ECS service: query CloudWatch CPU avg over last 14 days.
# Print recommendations: < 10% → downsize 1 step; 10-30% → review;
# > 80% → upsize. Apply via Terraform PR.`,
    },
    realUseCase:
      'A SaaS team in 2025 had a $400K/month cloud bill growing 8% MoM untagged. After 1 quarter of FinOps + DevEx: tagging on every resource, budgets per team, autoscale 90% → 60%, idle shutdown for dev/QA, DevContainer for local parity. Result: cloud bill flat (saved $200K annualized via right-sizing + idle shutdown); new engineer onboarding 8 days → 4 days; CI time 18 min → 7 min (caching + parallelization).',
    prosCons: {
      pros: [
        'Predictable cost trajectory',
        'Engineer onboarding halves',
        'CI faster + more reliable',
        'Right-sizing finds genuine waste',
        'Service catalog answers "who owns this?"',
      ],
      cons: [
        'Tagging policy enforcement is real CI work',
        'Catalog (Backstage) requires real platform-team investment',
        'Quarterly reviews cost engineering hours',
      ],
    },
    limitations: [
      'Cost optimization has diminishing returns past 30-50% saved',
      'DevEx improvements compound but slowly (weeks)',
      'Tagging retroactively is painful',
    ],
    comparison: {
      left: 'No FinOps + DevEx',
      right: 'Both disciplines wired',
      rows: [
        { aspect: 'Cloud bill predictability', left: 'Surprises', right: 'Forecastable' },
        { aspect: 'Onboarding time', left: '8 weeks', right: '4 weeks' },
        { aspect: 'CI duration', left: '15-30 min', right: '< 10 min' },
        { aspect: 'Cost per service known', left: 'No', right: 'Yes' },
        { aspect: 'Service ownership clarity', left: 'Tribal', right: 'Catalog' },
      ],
    },
    challenges: [
      'Tagging compliance — easy to forget in a one-off resource',
      'Autoscale at 60% sometimes triggers too eagerly (tune)',
      'Backstage requires per-service catalog-info.yaml maintenance',
      'CI < 10 min requires constant work as suite grows',
    ],
    edgeCases: [
      { case: 'Untagged resource sneaks in', solution: 'Cloud-Custodian / cloud-native policy: untagged resource auto-deleted after 24h in dev' },
      { case: 'Local setup breaks for one platform (Apple Silicon)', solution: 'Multi-arch Docker images; tested in CI matrix' },
      { case: 'Catalog YAML stale', solution: 'CI lint per repo: catalog-info.yaml validated against schema' },
      { case: 'CI time creeping past 10 min', solution: 'Profile + parallelize + cache; re-budget before 12 min hard cap' },
    ],
    solutions: [
      { problem: 'Surprise cloud bills', solution: 'Tagging + per-team budgets + 50/80/100% alerts' },
      { problem: 'Engineers skip local testing', solution: 'DevContainer + `make up` < 1h target' },
      { problem: 'CI takes too long', solution: 'Cache deps + parallelize tests + tier with drills (per CI commit thread)' },
      { problem: 'Cannot find service owner', solution: 'Backstage catalog + auto-published API specs' },
      { problem: 'Idle dev/QA wasting money', solution: 'Cron shutdown off-hours' },
    ],
    bestPractices: {
      do: [
        'Tag every resource (CI-enforced)',
        'Per-team budgets + 3-tier alerts',
        'Autoscale at ~60% target',
        'Idle dev/QA off-hours',
        'DevContainer for local parity',
        'Service catalog (Backstage)',
        'Golden-path templates (PR / ADR / runbook / incident)',
        'Quarterly right-sizing review',
      ],
      avoid: [
        'Untagged resources (auto-delete in dev)',
        'Autoscale at 80-90% (already saturated)',
        'Local setup > 2 hours',
        'CI > 15 min',
        'Service ownership by tribal knowledge',
      ],
      optimize: [
        'Cloud-Custodian for tag enforcement',
        'Backstage auto-discovery',
        'Make targets standardized across repos',
      ],
    },
    antiPatterns: [
      'Cost optimization as one-off project (vs ongoing discipline)',
      'DevEx as developer self-service tax (vs platform investment)',
      'Untagged "temporary" resources that live forever',
      'Local README that drifts from actual setup',
      'Catalog populated once, then abandoned',
    ],
    testing: ['Drill: untagged resource creation fails CI', 'Drill: `make up` < 1h on clean machine', 'Drill: catalog-info.yaml validation per repo'],
    testTypes: ['Tag enforcement drill', 'Local-setup drill', 'Catalog validation drill', 'Quarterly right-size simulation'],
    testScenarios: [
      { scenario: 'Terraform PR introduces untagged resource', expected: 'CI fails with required tag list' },
      { scenario: 'New engineer runs `make up`', expected: 'Stack up in < 1h with seed data' },
      { scenario: 'Backstage catalog query for service X', expected: 'Returns owner + on-call + API spec + runbook link' },
      { scenario: 'Quarterly right-size: CPU < 10% on 5 services', expected: 'PR generated to downsize each' },
    ],
    testData: [
      { type: 'Real cloud bill', example: 'Tagged + per-service breakdown' },
      { type: 'Real catalog', example: 'Backstage catalog with N services + on-call rotation' },
    ],
    debuggingChecklist: [
      'Tagging policy enforced in CI?',
      'Per-team budgets configured + alerts wired?',
      'Autoscale threshold ~60%?',
      'DevContainer in `.devcontainer/`?',
      '`make up` documented + tested?',
      'Backstage catalog accessible?',
      'Golden-path templates current?',
    ],
    productionIssues: [
      { issue: 'Surprise $30K/month spike', rootCause: 'Untagged resource; retroactive tag + new CI lint to prevent recurrence' },
      { issue: 'New engineer takes 2 weeks to first PR', rootCause: 'Local setup broken; refresh DevContainer + run drill' },
      { issue: 'Cannot find on-call for service X', rootCause: 'catalog-info.yaml stale; CI lint to validate per repo' },
    ],
    security: ['Untagged resources auto-deleted in dev (security exposure timer)', 'Catalog has audit log of changes', 'DevContainer secrets via vault, not committed'],
    performance: [
      'Autoscale react time: < 5 min',
      '`make up`: < 1 hour for new engineer',
      'CI: < 10 min',
      'Catalog query: < 1s',
    ],
    costConsiderations: [
      'Tagging CI lint: free (custom check)',
      'Backstage hosting: ~$200/month per cluster',
      'Right-sizing review: 1 day quarterly',
      'Saves: typically 30-50% of cloud bill in first year',
    ],
    scaling: ['Multi-account FinOps via Cloud-Custodian', 'Per-domain catalog views in Backstage', 'Per-language DevContainer variants'],
    observability: ['Cost-per-service trend dashboard', 'Onboarding-time histogram', 'CI duration p95 over time', 'Catalog coverage %'],
    metrics: [
      { name: 'cost_per_service_usd_monthly', example: '$2400 (inference-svc)' },
      { name: 'onboarding_to_first_pr_days', example: '4' },
      { name: 'ci_duration_p95_minutes', example: '7' },
      { name: 'catalog_coverage_percent', example: '0.94' },
      { name: 'untagged_resources_count', example: '0' },
    ],
    failureModes: [
      { mode: 'Untagged resource', detect: 'Cloud-Custodian scan', recover: 'Auto-delete in dev; alert in prod' },
      { mode: 'Catalog drift', detect: 'CI lint failure', recover: 'Per-repo catalog-info.yaml validation' },
      { mode: 'CI > 15 min', detect: 'Duration trend dashboard', recover: 'Profile + parallelize + cache' },
      { mode: 'Local setup broken', detect: 'New-engineer drill timeout', recover: 'Refresh DevContainer + redo drill' },
    ],
    tradeoffs: [
      { decision: 'Autoscale at 60% vs 80%', tradeoff: 'More headroom (cost) vs less surge tolerance' },
      { decision: 'Backstage vs no catalog', tradeoff: 'Platform investment vs tribal knowledge' },
      { decision: 'CI < 10 min hard cap', tradeoff: 'Aggressive optimization vs comprehensive coverage' },
    ],
    decisionMatrix: [
      { option: 'No discipline', whenToUse: 'Pre-PMF only' },
      { option: 'FinOps only', whenToUse: 'Cost-pressed; small team' },
      { option: 'DevEx only', whenToUse: 'Growing team; cost not yet biting' },
      { option: 'Both (recommended)', whenToUse: 'Multi-team org; cloud-native; growing' },
    ],
    starStory: {
      situation: '$400K/month cloud bill growing 8% MoM. Untagged. Onboarding 8 days. CI 18 min.',
      task: 'Stop the bleed without slowing teams.',
      action: 'FinOps: tagged everything via Cloud-Custodian + retroactive Terraform. Per-team budgets. Autoscale 90% → 60%. Idle dev/QA shutdown. DevEx: DevContainer for local parity. Backstage catalog. Golden-path templates. Make targets standardized.',
      result: 'Cloud bill flat ($200K annualized save). Onboarding 8 → 4 days. CI 18 → 7 min. Cost-per-service known per team. Surprise spikes eliminated. New engineers shipping PR by day 4.',
    },
    interviewTraps: [
      'FinOps as one-off project',
      'DevEx as "engineers handle their own setup"',
      'Untagged resources tolerated',
      'Autoscale at 80% target',
      'No catalog',
    ],
    finalScript:
      'FinOps: cost is architecture. Tag everything (CI-enforced). Per-team budgets + 3-tier alerts. Autoscale 60% target. Idle dev/QA off-hours. Quarterly right-size. DevEx: DevContainer + `make up` < 1h. Service catalog (Backstage). Golden-path templates. CI < 10 min. The pair compounds: budget health + engineer attrition prevention.',
    alternatives: [
      { name: 'Reactive cost control', tradeoff: 'Cheap to start; surprise bills' },
      { name: 'DevEx via README only', tradeoff: 'Fast write; rapid drift' },
      { name: 'Both wired (this)', tradeoff: 'Real platform investment; sustainable' },
    ],
    monitoring: ['Cost dashboard per team', 'Onboarding-time histogram', 'CI duration trend', 'Catalog coverage %', 'Untagged resource count'],
    maturity: {
      mvp: 'Tagging + DevContainer + README golden path',
      production: '+ Per-team budgets + autoscale 60% + Backstage + quarterly review',
      enterprise: '+ Cloud-Custodian enforcement + multi-account FinOps + per-domain catalog',
    },
    projectFit: ['Multi-team orgs', 'Cloud-native production', 'Growing engineering org', 'Cost-pressured AI workloads'],
    interviewLine: 'Cost is architecture. Friction is defects. Tag everything. DevContainer + make up. Catalog. Golden path. Quarterly right-size.',
  },
];

export default function TechEvolutionDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Technical evolution + efficiency (deep dive)</h1>
        <p className="design-areas-sub">
          Tech Radar (Adopt / Trial / Assess / Hold) + paved-road / service
          chassis + deprecation policy — the evolution control system that
          limits choice and accelerates consistent shipping. Plus FinOps (cost
          as a design property) + DevEx (friction as defect cause) — the
          sustainability discipline pair that prevents budget death and
          engineer attrition.
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/principles/deep', label: 'Principles — SOLID + 17-factor', why: 'service chassis ships principles by default; tech radar gates dependencies that violate them' },
          { href: '/admin/cicd/deep', label: 'CI/CD — pipeline gate', why: 'tech radar Hold-tier blocks enforced via CI lint; FinOps untagged-resource block runs in same gate' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Checklist §11 governance + §13 FinOps + §14 DevEx', why: 'three checklist sections directly correspond to topics on this page' },
          { href: '/admin/llmops/deep', label: 'LLMOps — token cost', why: 'AI cost discipline is FinOps applied to inference; per-tenant token rollups in same FinOps tagging schema' },
          { href: '/admin/code-quality/deep', label: 'Code quality — linting baseline', why: 'service chassis ships the lint stack day 1; deprecation policy retires Hold-tier lint tools' },
        ]}
      />
    </div>
  );
}
