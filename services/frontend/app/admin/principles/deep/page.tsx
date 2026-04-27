'use client';

/**
 * Architecture principles (deep dive).
 *
 * Two topics: SOLID applied to AI-SDLC + microservices, and the
 * twelve-factor / KISS / YAGNI / DRY operating model extended for
 * AI systems.
 */

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  // ═══════════════════════════════════════════════════════════════
  // TOPIC 1 — SOLID FOR AI-SDLC + MICROSERVICES
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'solid-ai-microservices',
    title: '1. SOLID — applied to AI-SDLC + microservices',
    status: 'shipped',
    coreConcept: 'SOLID is not just OOP theory. SRP reduces blast radius; OCP supports safe extension; LSP protects contracts; ISP prevents bloated interfaces; DIP keeps business logic independent of infrastructure. AI-generated code without SOLID becomes a god-class swamp.',
    oneLiner: 'SRP = one reason to change. OCP = extend not modify. LSP = preserve contract. ISP = small interfaces. DIP = depend on abstractions.',
    businessContext: 'AI coding tools generate code fast; without SOLID guardrails, that code becomes unmaintainable in 3 months. SOLID is what keeps AI-assisted dev from creating tech debt at velocity.',
    fiveW: {
      what: 'Five OOP principles applied to classes (e.g., LLMProvider interface), microservices (e.g., one service = one capability), and AI-generated code (e.g., prevent god classes).',
      why: 'Each principle controls a specific failure mode of complexity.',
      where: 'Code review + architecture review + AI-PR gates.',
      when: 'Every PR; especially AI-touched ones.',
      who: 'Engineers + reviewers + tech leads.',
    },
    interview30s: 'SOLID is not just OOP theory; I use it to control complexity in AI-generated code, microservices, and enterprise architecture. SRP — one class or service has one reason to change; reduces blast radius. OCP — open for extension, closed for modification; new behavior plugs in via interface, not by patching stable code. LSP — child classes preserve parent\'s expected behavior; ReadOnlyRepository inheriting Repository and throwing on save() is a violation. ISP — small focused interfaces; one huge AIService with chat + embedding + vision + speech is wrong, split into ChatModel + EmbeddingModel. DIP — depend on abstraction not concrete; business logic uses LLMProvider interface, not OpenAIClient directly. In microservices: SRP = one service per capability, OCP = new service plugs in via contract, LSP = service version preserves contract, ISP = APIs split by client need, DIP = services depend on contracts/events not direct DB. In AI-assisted dev: SOLID is the lint that prevents Copilot/Cursor god-class swamp.',
    hld: `flowchart TB
  AppLayer[Business logic]
  AppLayer -->|depends on| Abstraction[LLMProvider interface]
  Abstraction -.implemented by.-> OpenAI[OpenAIProvider]
  Abstraction -.implemented by.-> Bedrock[BedrockProvider]
  Abstraction -.implemented by.-> Local[LocalProvider]
  classDef principle fill:#dbeafe,stroke:#1e40af
  class Abstraction principle`,
    networkFlow: `flowchart LR
  Service[Service A] -.contract.-> ServiceB[Service B]
  Service -.events.-> Bus[Event bus]
  Service -.does NOT.-> DBOther[(DB of Service B)]`,
    flowchart: `flowchart LR
  Q[New requirement] --> S[Apply SOLID]
  S --> SRP{One responsibility?}
  S --> OCP{Extend not modify?}
  S --> LSP{Preserve contract?}
  S --> ISP{Small interface?}
  S --> DIP{Depend on abstraction?}
  All --> Code`,
    sequence: `sequenceDiagram
  participant App as AnswerService
  participant LLM as LLMProvider interface
  participant OAI as OpenAIProvider
  App->>LLM: generate prompt
  LLM->>OAI: dispatch
  OAI-->>LLM: response
  LLM-->>App: response
  Note over App,LLM: Tomorrow swap to Bedrock — App unchanged`,
    coreLayers: [
      { layer: 'SRP', responsibility: 'One reason to change. Reduces blast radius.' },
      { layer: 'OCP', responsibility: 'Extend not modify. Plug in via interface.' },
      { layer: 'LSP', responsibility: 'Subclasses preserve expected behavior.' },
      { layer: 'ISP', responsibility: 'Clients depend only on what they use.' },
      { layer: 'DIP', responsibility: 'Depend on abstractions, not concrete impl.' },
    ],
    lld: `flowchart LR
  Logic[Business logic] -->|interface| Repo[Repository]
  Repo -.impl.-> PG[PostgresRepo]
  Repo -.impl.-> Mock[MockRepo for tests]
  Logic -->|interface| LLM[LLMProvider]
  LLM -.impl.-> OAI[OpenAIProvider]`,
    problem: 'Without SOLID, AI-generated + human code drifts into god classes, fat interfaces, hardcoded dependencies. Tech debt at velocity.',
    whyThisApproach: 'Each principle has a specific failure-mode prevention. Together they keep complexity bounded.',
    whenToUse: ['Every PR', 'AI-PR review especially', 'Microservice boundary design'],
    whenNotToUse: ['Hackathon throwaway scripts'],
    input: 'New code change',
    process: ['SRP audit', 'OCP audit', 'LSP audit', 'ISP audit', 'DIP audit'],
    output: 'PR that passes SOLID lint',
    alternatives: [
      { name: 'Skip SOLID', tradeoff: 'Fast; debt accumulates' },
      { name: 'SOLID + AI gates (this)', tradeoff: 'Disciplined; review overhead' },
      { name: 'Dogmatic SOLID everywhere', tradeoff: 'Over-engineered prototype' },
    ],
    challenges: ['AI generates god classes by default', 'OCP without YAGNI = over-engineering', 'DIP everywhere = abstraction tax'],
    edgeCases: [
      { case: 'New LLM provider (Claude)', solution: 'Add ClaudeProvider; AnswerService unchanged (OCP + DIP win)' },
      { case: 'AI suggested 500-line god class', solution: 'Split via SRP; refactor PR' },
      { case: 'Performance critical hot path', solution: 'Allow concrete coupling with comment + ADR' },
    ],
    failureModes: [
      { mode: 'God class accumulates', detect: 'Class > 500 lines', recover: 'SRP refactor' },
      { mode: 'Fat interface (ISP violation)', detect: 'Interface with > 10 methods', recover: 'Split per concern' },
      { mode: 'Hardcoded vendor (DIP violation)', detect: 'Direct OpenAI client in business logic', recover: 'Introduce interface' },
    ],
    monitoring: ['Lint metrics: god class count, fat interface count, hardcoded deps', 'Per-PR SOLID check'],
    testing: ['Each interface has multiple impls (OCP)', 'Mock-friendly via DIP', 'Each class has narrow tests via SRP'],
    security: ['DIP enables interface-based security wrappers', 'SRP isolates security-critical classes'],
    scaling: ['SRP supports independent scaling', 'DIP supports test/mock substitution'],
    maturity: { mvp: 'Ad-hoc design', production: 'SOLID enforced via review + lint', enterprise: 'SOLID + AI-PR gate + automated metric tracking' },
    limitations: ['Over-applied SOLID = abstraction tax', 'Performance hot paths may need concrete coupling'],
    projectFit: ['libs/py/documind_core/ — interface-based primitives', 'services/*-svc/ — class-based with constructor DI', 'AI-PR gate (ADR-001) checks SOLID'],
    interviewLine: 'SOLID is the lint that prevents Copilot god-class swamp at velocity. Each principle prevents a specific complexity failure mode.',
    implementationSteps: [
      { step: 'SRP', logic: 'One class = one reason to change.' },
      { step: 'OCP', logic: 'Extend via new class implementing interface; don\'t modify stable code.' },
      { step: 'LSP', logic: 'Subclasses honor parent\'s contract behavior.' },
      { step: 'ISP', logic: 'Split fat interfaces by client concern.' },
      { step: 'DIP', logic: 'Business logic depends on interfaces; concrete via constructor injection.' },
      { step: 'AI-PR review', logic: 'AI-touched PRs explicitly checked for god classes + fat interfaces.' },
    ],
    codeExample: { language: 'python', code: `# libs/py/documind_core/llm.py — DIP + OCP
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str: ...

class OpenAIProvider(LLMProvider):
    async def generate(self, prompt: str) -> str:
        return await self._client.chat(prompt)

class BedrockProvider(LLMProvider):
    async def generate(self, prompt: str) -> str:
        return await self._client.invoke(prompt)

# Business logic depends on interface (DIP)
class AnswerService:
    def __init__(self, llm: LLMProvider, retriever: RetrieverInterface):
        self._llm = llm
        self._retriever = retriever

    async def answer(self, question: str, tenant_id: str) -> str:
        chunks = await self._retriever.fetch(question, tenant_id)
        prompt = build_prompt(question, chunks)
        return await self._llm.generate(prompt)

# ISP — split by concern
class EmbedderInterface(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

class ChatInterface(ABC):
    @abstractmethod
    async def chat(self, prompt: str) -> str: ...

# NOT this:
# class HugeAIInterface(ABC):
#     @abstractmethod
#     async def embed(self, text): ...
#     @abstractmethod
#     async def chat(self, prompt): ...
#     @abstractmethod
#     async def speech_to_text(self, audio): ...
#     @abstractmethod
#     async def text_to_speech(self, text): ...

# LSP — subclass preserves contract
class WriteRepository(ABC):
    @abstractmethod
    async def save(self, item): ...

# WRONG: ReadOnlyRepository(WriteRepository) that throws on save()
# RIGHT: separate ReadRepository + WriteRepository interfaces` },
    realUseCase: 'Pre-SOLID: god class UserService (validation + DB + email + audit + auth) — every change touched 800 lines + 30 tests. Refactored via SRP into UserValidator + UserRepository + EmailNotifier + AuditLogger + AuthService. Per-class change blast radius dropped 90%; tests focused.',
    prosCons: {
      pros: ['Bounded complexity', 'Testable via DIP', 'Extensible via OCP', 'Reviewable via SRP'],
      cons: ['Abstraction tax if over-applied', 'Onboarding curve', 'Some performance hot paths suffer'],
    },
    comparison: { left: 'No SOLID (god classes)', right: 'SOLID applied (this)', rows: [
      { aspect: 'Per-change blast radius', left: 'Whole class', right: 'One concern' },
      { aspect: 'Testability', left: 'Hard (concrete coupling)', right: 'Easy (DIP + mocks)' },
      { aspect: 'Vendor swap', left: 'Touch every caller', right: 'New impl class' },
      { aspect: 'AI-generated code quality', left: 'God classes', right: 'Bounded' },
    ] },
    solutions: [
      { problem: 'God class', solution: 'SRP refactor' },
      { problem: 'Vendor lock-in', solution: 'DIP interface + multiple impls' },
      { problem: 'Fat interface', solution: 'ISP split by concern' },
      { problem: 'Subclass breaks', solution: 'LSP audit' },
    ],
    bestPractices: { do: ['SRP per class', 'OCP via interfaces', 'LSP audit subclasses', 'ISP split fat interfaces', 'DIP for testability', 'AI-PR explicit SOLID check'], avoid: ['God classes', 'Fat interfaces', 'Hardcoded vendors in business logic', 'Subclasses that throw on parent methods'], optimize: ['SOLID lint metrics', 'Per-PR auto-check'] },
    antiPatterns: ['God class', 'Fat interface', 'Hardcoded vendor', 'Throw-on-parent-method subclass'],
    testTypes: ['Unit per class (SRP enables)', 'Mock substitution (DIP enables)', 'Interface contract tests'],
    testScenarios: [
      { scenario: 'New LLM provider', expected: 'Implement LLMProvider; AnswerService unchanged' },
      { scenario: 'AI generates 500-line class', expected: 'PR review flags SRP violation' },
      { scenario: 'Mock LLM in test', expected: 'DIP allows substitution' },
    ],
    testData: [{ type: 'Reference SOLID examples', example: 'Per-principle good + bad code samples' }],
    debuggingChecklist: ['Hard to test? DIP missing', 'Touching many files for one change? SRP violation', 'Vendor swap costly? OCP/DIP gaps'],
    productionIssues: [
      { issue: '800-line UserService god class', rootCause: 'No SRP. Refactored.' },
      { issue: 'Vendor swap took 2 weeks', rootCause: 'Hardcoded OpenAI client. DIP added.' },
    ],
    performance: ['Interface dispatch: <1μs', 'Constructor injection: negligible', 'Mock substitution: free in tests'],
    costConsiderations: ['Free — design discipline', 'Reviewer time amortizes via lower defect rate'],
    observability: ['Class size distribution', 'Interface fan-out', 'Per-PR SOLID lint'],
    metrics: [
      { name: 'class_loc_distribution{p}', example: 'Histogram; p95 < 500 lines target' },
      { name: 'interface_method_count_p', example: 'Histogram; p95 < 10 target' },
    ],
    tradeoffs: [
      { decision: 'SOLID rigor', tradeoff: 'Strict = clean; over-engineering risk' },
      { decision: 'Interface granularity', tradeoff: 'Many = ISP; few = simpler' },
    ],
    decisionMatrix: [
      { option: 'SOLID applied (this)', whenToUse: 'Production code; multi-team' },
      { option: 'SOLID-light', whenToUse: 'Prototype phase' },
      { option: 'No SOLID', whenToUse: 'Throwaway script' },
    ],
    starStory: {
      situation: 'AI-assisted dev velocity 30% up; tech debt up 60% in 3 months. God classes everywhere.',
      task: 'Keep velocity + cap debt.',
      action: 'Added SOLID lint to AI-PR gate (ADR-001). Refactored top-5 god classes. Reviewer training.',
      result: 'Velocity unchanged; tech debt growth dropped to 10% per quarter. AI-PRs match human-PR quality.',
    },
    interviewTraps: ['Treating SOLID as OOP-only theory', 'Skipping SOLID review on AI-PRs', 'Over-applying (every class has interface)'],
    finalScript: 'SOLID is not just object-oriented theory. I use it to control complexity in AI-generated code, microservices, and enterprise architecture. SRP reduces blast radius — one class or service has one reason to change. OCP supports safe extension — new LLM providers plug in via interface, AnswerService unchanged. LSP protects contracts — subclasses preserve parent\'s expected behavior. ISP prevents bloated interfaces — split AIService into ChatModel + EmbeddingModel by concern. DIP keeps business logic independent of infrastructure — service depends on LLMProvider interface, not OpenAIClient directly. In microservices, SRP means one service per capability; in AI-assisted dev, SOLID is the lint that prevents Copilot god-class swamp at velocity.',
  },

  // ═══════════════════════════════════════════════════════════════
  // TOPIC 2 — TWELVE-FACTOR + KISS/YAGNI/DRY
  // ═══════════════════════════════════════════════════════════════
  {
    slug: 'twelve-factor-kiss-yagni-dry',
    title: '2. Twelve-factor + KISS / YAGNI / DRY — extended for AI systems',
    status: 'shipped',
    coreConcept: 'Twelve-factor for cloud-native + KISS/YAGNI/DRY for engineering judgment, both extended for AI: model + prompt + data + evaluation + cost as additional factors. Each principle has a counter-rule for when to break it.',
    oneLiner: 'Twelve-factor + AI extensions = production-ready. KISS/YAGNI/DRY are heuristics, not rules.',
    businessContext: 'Twelve-factor predates AI; the original 12 don\'t cover model versioning, prompt registry, eval gates, cost. Adding 5 AI factors makes the model production-ready. KISS/YAGNI/DRY are essential heuristics but every senior engineer must know when to break them.',
    fiveW: {
      what: 'Twelve-factor app (codebase / dependencies / config / backing services / build-release-run / processes / port binding / concurrency / disposability / dev-prod parity / logs / admin tasks) + AI extensions (model / prompt / data / evaluation / cost). KISS / YAGNI / DRY as judgment heuristics with counter-rules.',
      why: 'Twelve-factor codifies cloud-native; AI extensions cover what 2011 couldn\'t. KISS/YAGNI/DRY guide complexity tradeoffs.',
      where: 'Service chassis + AI-SDLC.',
      when: 'New service Day 1; every architecture review.',
      who: 'Architect + tech lead + AI ops.',
    },
    interview30s: 'I combine twelve-factor app principles with AI extensions and KISS/YAGNI/DRY heuristics. Twelve-factor: one codebase per service, locked dependencies, config via env + secret manager, backing services replaceable, build-release-run separated, stateless processes, port binding for API-first, horizontal scaling, fast start + graceful shutdown, dev-prod parity, centralized structured logs, admin tasks via pipelines. AI extensions add: model versioned, prompt versioned, data governed, evaluation continuous, cost monitored. KISS/YAGNI/DRY are heuristics I break when they conflict with each other — DRY breaks when coupling increases; KISS breaks when system requires abstraction; YAGNI breaks when future is predictable platform need. Folder structure: layer + feature hybrid for backend (domain / application / infrastructure / api / ai), feature-first for frontend.',
    hld: `flowchart TB
  TwelveFactor[12-factor app] --> AIExt[+ 5 AI extensions]
  AIExt --> Service[Production service]
  KISS[KISS] -.heuristic.-> Service
  YAGNI[YAGNI] -.heuristic.-> Service
  DRY[DRY] -.heuristic.-> Service
  Counter[Counter-rules: when to break] -.guides.-> Service`,
    networkFlow: `flowchart LR
  Repo[One codebase] --> Build[Build]
  Build --> Release[Release artifact]
  Release --> Run[Stateless process]
  Run -->|env| Config
  Run -->|API| Port[Port-bound]
  Run -->|logs| Stdout[Centralized]`,
    flowchart: `flowchart LR
  Q[New service] --> S1[Apply 12 factors]
  S1 --> S2[Apply 5 AI extensions]
  S2 --> S3[KISS check + YAGNI check + DRY check]
  S3 --> S4[Counter-rule check]
  S4 --> O[Production-ready service]`,
    sequence: `sequenceDiagram
  participant Dev as Developer
  participant CI
  participant Reg as Registry
  participant Run as Runtime
  Dev->>CI: code change
  CI->>CI: build
  CI->>Reg: release artifact
  Reg->>Run: deploy
  Run->>Run: stateless process
  Run->>Run: graceful shutdown ready`,
    coreLayers: [
      { layer: 'Codebase + dep + config', responsibility: 'Factors I-III: one repo, locked deps, env config.' },
      { layer: 'Build-release-run + processes', responsibility: 'Factors V-VI: separated stages; stateless.' },
      { layer: 'Port + concurrency + disposability', responsibility: 'Factors VII-IX: API-first, horizontal, fast restart.' },
      { layer: 'Parity + logs + admin', responsibility: 'Factors X-XII: dev-prod parity, structured logs, pipeline admin.' },
      { layer: 'AI extensions', responsibility: 'Model + prompt + data + eval + cost versioned + monitored.' },
      { layer: 'KISS/YAGNI/DRY heuristics', responsibility: 'Complexity judgment; counter-rules when to break.' },
    ],
    lld: `flowchart LR
  Backend[src/] --> Domain[domain DDD]
  Backend --> App[application use cases]
  Backend --> Infra[infrastructure DB API]
  Backend --> API[api controllers]
  Backend --> AI[ai prompts models eval guardrails]`,
    problem: 'Twelve-factor predates AI; original 12 miss model + prompt + eval + cost. KISS/YAGNI/DRY without counter-rules cause new problems (over-DRY couples; over-KISS misses needed abstraction).',
    whyThisApproach: '17 factors total cover cloud-native + AI. KISS/YAGNI/DRY with explicit counter-rules give judgment instead of dogma.',
    whenToUse: ['Every production service', 'Architecture review', 'New-team setup'],
    whenNotToUse: ['Throwaway prototype'],
    input: 'New service or refactor scope',
    process: ['Apply 12 factors', 'Apply 5 AI extensions', 'KISS check', 'YAGNI check', 'DRY check', 'Counter-rule check'],
    output: 'Production-ready service + extension audit',
    alternatives: [
      { name: 'Twelve-factor only', tradeoff: 'Cloud-native; misses AI' },
      { name: '17-factor (this)', tradeoff: 'AI-ready; ops cost' },
      { name: 'No principles', tradeoff: 'Fast prototype; tech debt' },
    ],
    challenges: ['DRY vs decoupling tension', 'KISS vs abstraction need', 'AI factors require dedicated infra (registry, eval)'],
    edgeCases: [
      { case: 'DRY between two services', solution: 'Counter-rule: DRY at service boundary causes tight coupling; allow duplication' },
      { case: 'KISS but problem demands abstraction', solution: 'Add abstraction with rationale in ADR' },
      { case: 'YAGNI but feature is platform need', solution: 'Build platform layer with explicit ADR' },
    ],
    failureModes: [
      { mode: 'Stateful process kills horizontal scale', detect: 'Sessions in local memory', recover: 'Move to Redis; stateless going forward' },
      { mode: 'Hardcoded config', detect: 'Code grep for hostnames/secrets', recover: 'Env + Vault' },
      { mode: 'No model registry', detect: 'No rollback path for prompt', recover: 'Adopt registry + version' },
    ],
    monitoring: ['Per-factor compliance per service', 'AI extension adoption rate', 'KISS/YAGNI/DRY review notes'],
    testing: ['Twelve-factor compliance audit', 'AI extension drill', 'Folder structure lint'],
    security: ['Factor III (config) + Vault for secrets', 'AI extension model integrity', 'Signed builds'],
    scaling: ['Stateless processes scale horizontally', 'Per-factor + per-AI-extension scales independently'],
    maturity: { mvp: 'Some factors followed', production: 'All 12 + 5 AI extensions', enterprise: 'Auto-compliance check + per-service scorecard' },
    limitations: ['12-factor is opinionated cloud-native; doesn\'t fit edge / IoT', 'AI extensions evolve rapidly', 'Heuristic judgment requires experience'],
    projectFit: ['service-chassis template enforces all 17', '/admin/c4-model/deep — system view', '/admin/architect/deep — role lens'],
    interviewLine: 'Twelve-factor + 5 AI extensions = production AI service. KISS/YAGNI/DRY are heuristics with counter-rules; rigid application creates new problems.',
    implementationSteps: [
      { step: 'Apply 12 factors', logic: 'Codebase, deps, config, services, build-release-run, processes, port, concurrency, disposability, parity, logs, admin.' },
      { step: 'Apply 5 AI extensions', logic: 'Model + prompt + data + evaluation + cost versioned + monitored.' },
      { step: 'KISS heuristic + counter', logic: 'Simple by default; abstraction when system requires.' },
      { step: 'YAGNI heuristic + counter', logic: 'Build when needed; build platform when predictable.' },
      { step: 'DRY heuristic + counter', logic: 'Single source; allow duplication when coupling increases.' },
      { step: 'Folder structure', logic: 'Backend layer+feature hybrid; frontend feature-first.' },
    ],
    codeExample: { language: 'markdown', code: `# Service Chassis Compliance Checklist

## Twelve-Factor (12)
- [ ] I. Codebase: one repo per service
- [ ] II. Dependencies: locked + scanned (Snyk)
- [ ] III. Config: env + secret manager (Vault)
- [ ] IV. Backing services: replaceable (DB, cache, LLM, vector DB)
- [ ] V. Build/release/run: separated stages (CI/CD)
- [ ] VI. Processes: stateless containers
- [ ] VII. Port binding: API-first
- [ ] VIII. Concurrency: horizontal scaling (K8s autoscale)
- [ ] IX. Disposability: fast start + graceful shutdown
- [ ] X. Dev/prod parity: same infra (Docker/K8s)
- [ ] XI. Logs: centralized + structured
- [ ] XII. Admin: pipelines/jobs

## AI Extensions (5)
- [ ] Model: versioned (v1, v2 rollback)
- [ ] Prompt: versioned + tested
- [ ] Data: governed + classified
- [ ] Evaluation: built-in scoring
- [ ] Cost: token monitoring

## KISS / YAGNI / DRY Heuristics (judgment)
- [ ] KISS check: simplest design that works
- [ ] YAGNI check: built only what's needed now
- [ ] DRY check: single source of truth
- [ ] Counter-rules documented in ADR if breaking

## Folder Structure
\`\`\`
src/
├── domain/              # business logic (DDD)
├── application/         # use cases
├── infrastructure/      # DB, API, external
├── api/                 # controllers/routes
├── ai/                  # AI layer
│   ├── prompts/
│   ├── models/
│   ├── evaluation/
│   └── guardrails/
├── config/
└── tests/
\`\`\``,
    },
    realUseCase: 'New AI service skipped Factor VI (stateless) — used local sessions. Couldn\'t horizontally scale. Refactored: sessions to Redis. New service with all 17 factors + folder structure shipped in 4 weeks; sister service without compliance shipped in 8 weeks with subsequent rework. Compliance discipline is faster long-term.',
    prosCons: {
      pros: ['Cloud-native default', 'AI-ready production', 'Heuristics give judgment', 'Onboarding fast (standard chassis)'],
      cons: ['17 factors is opinionated', 'KISS/YAGNI/DRY break-judgment requires experience', 'Folder structure may not fit all'],
    },
    comparison: { left: 'Original 12-factor only', right: '12 + 5 AI extensions (this)', rows: [
      { aspect: 'AI rollback', left: 'No', right: 'Model registry + fallback' },
      { aspect: 'Prompt versioning', left: 'No', right: 'Required factor' },
      { aspect: 'Eval gate', left: 'No', right: 'Built-in' },
      { aspect: 'Cost monitoring', left: 'No', right: 'Per-tenant tracked' },
    ] },
    solutions: [
      { problem: 'Stateful breaks scale', solution: 'Factor VI: stateless + Redis sessions' },
      { problem: 'Hardcoded config', solution: 'Factor III: env + Vault' },
      { problem: 'No AI rollback', solution: 'AI Extension 1: model registry' },
      { problem: 'AI cost surprise', solution: 'AI Extension 5: token monitoring + budget' },
    ],
    bestPractices: { do: ['All 12 factors', 'All 5 AI extensions', 'KISS by default', 'YAGNI by default', 'DRY by default', 'Document counter-rule breaks in ADR'], avoid: ['Stateful processes', 'Hardcoded config', 'Skipping AI extensions', 'Dogmatic KISS/YAGNI/DRY'], optimize: ['Service-chassis template', 'Auto-compliance lint', 'Per-service scorecard'] },
    antiPatterns: ['Stateful processes', 'Hardcoded config', 'Dogmatic DRY (across services)', 'No AI extensions'],
    testTypes: ['Twelve-factor audit', 'AI extension drill', 'Folder structure lint', 'Counter-rule ADR check'],
    testScenarios: [
      { scenario: 'New service kickoff', expected: 'Chassis applied + all 17 factors checked' },
      { scenario: 'AI feature added', expected: '5 AI extensions verified' },
      { scenario: 'KISS broken via abstraction', expected: 'ADR with rationale' },
    ],
    testData: [{ type: 'Reference chassis', example: 'service-chassis template repo' }],
    debuggingChecklist: ['Can\'t scale? Factor VI stateless', 'Hardcoded host? Factor III config', 'No AI rollback? AI Extension 1', 'Cost surprise? AI Extension 5'],
    productionIssues: [
      { issue: 'Service couldn\'t horizontally scale', rootCause: 'Local sessions (Factor VI). Migrated to Redis.' },
      { issue: 'AI feature regressed; no rollback', rootCause: 'No model registry. Added.' },
    ],
    performance: ['Compliance audit: ~30 min per service', 'Folder reorg: ~1-2 days', 'Heuristic counter-rule check: per-PR review'],
    costConsiderations: ['Free — design discipline', 'AI extensions: registry + eval + monitoring infra'],
    observability: ['Per-factor compliance %', 'Per-AI-extension adoption', 'KISS/YAGNI/DRY break notes per quarter'],
    metrics: [
      { name: 'service_chassis_compliance{service}', example: 'Gauge; target = 1.0 (all 17 factors)' },
      { name: 'ai_extension_adoption{extension}', example: 'Gauge per extension' },
    ],
    tradeoffs: [
      { decision: 'KISS vs needed abstraction', tradeoff: 'Simple = readable; complex = scalable' },
      { decision: 'YAGNI vs platform build', tradeoff: 'Build when needed = lean; platform = leverage' },
      { decision: 'DRY vs coupling', tradeoff: 'Single source = reuse; coupling = brittle' },
    ],
    decisionMatrix: [
      { option: '17-factor (this)', whenToUse: 'Production AI services' },
      { option: '12-factor only', whenToUse: 'Non-AI legacy' },
      { option: 'No principles', whenToUse: 'Throwaway prototype' },
    ],
    starStory: {
      situation: 'New AI service skipped Factor VI; couldn\'t scale beyond 1 replica.',
      task: 'Apply chassis discipline.',
      action: '17-factor compliance check; refactored sessions to Redis. Adopted as service-chassis template.',
      result: 'Service scaled horizontally; chassis adopted by 8 sister services. Onboarding time 8 weeks → 4 weeks.',
    },
    interviewTraps: ['Twelve-factor only (no AI extensions)', 'Dogmatic KISS/YAGNI/DRY', 'Stateful processes', 'Hardcoded config'],
    finalScript: 'I combine twelve-factor app principles with AI extensions and KISS/YAGNI/DRY heuristics. Twelve-factor codifies cloud-native: one codebase, locked deps, env config, replaceable backing services, separated build-release-run, stateless processes, port binding, horizontal scale, disposability, dev-prod parity, structured logs, pipeline admin. AI extensions add the five things 2011 couldn\'t see: model versioned, prompt versioned, data governed, evaluation continuous, cost monitored. KISS/YAGNI/DRY are heuristics I break when they conflict — DRY breaks when coupling increases; KISS breaks when system requires abstraction; YAGNI breaks when future is predictable platform need. Folder structure: backend layer-and-feature hybrid (domain / application / infrastructure / api / ai), frontend feature-first.',
  },
];

export default function PrinciplesDeep() {
  return (
    <div className="design-areas-page">
      <header className="design-areas-header">
        <h1 className="section-title">Architecture principles (deep dive)</h1>
        <p className="design-areas-sub">
          SOLID applied to AI-SDLC + microservices (the lint that prevents Copilot
          god-class swamp at velocity). Twelve-factor app extended with 5 AI factors
          (model + prompt + data + evaluation + cost). KISS / YAGNI / DRY as
          heuristics with explicit counter-rules. Folder structure conventions for
          backend (DDD layer + feature hybrid) + frontend (feature-first).
        </p>
      </header>
      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
      <DeepDiveCrossRefs
        refs={[
          { href: '/admin/microservices/deep', label: 'Microservices design', why: 'SRP = bounded context per service; DIP = LLMProvider interface; ISP = split EmbedderInterface from ChatInterface' },
          { href: '/admin/tracing/deep#baggage-propagation', label: 'Factor XI logs + tracing', why: '17-factor extension: structured logs pull baggage_get_all() so every log line is tenant-filterable' },
          { href: '/admin/llmops/deep', label: 'AI factors 13–17', why: 'models / prompts / evaluation / cost — the AI-specific extensions to 12-factor live here' },
          { href: '/admin/cicd/deep#tdd-framework-ai', label: 'TDD enforces SOLID', why: 'hard-to-test code = SRP / DIP violation; TDD red phase makes design problems visible' },
          { href: '/admin/checklist/deep#lifecycle-checklist', label: 'Checklist §4 Coding', why: 'SOLID + 17-factor + DDD folders + type hints + no N+1 are direct checklist rows' },
        ]}
      />
    </div>
  );
}
