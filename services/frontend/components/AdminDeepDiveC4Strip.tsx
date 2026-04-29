'use client';

import { usePathname } from 'next/navigation';
import C4PageLinks from './C4PageLinks';

type DeepDiveConfig = {
  title: string;
  summary: string;
  focus: string;
  levels: Array<'context' | 'containers' | 'components' | 'code' | 'governance' | 'observability' | 'lifecycle'>;
};

const CONFIG: Record<string, DeepDiveConfig> = {
  adr: {
    title: 'ADR deep dive — C4 view',
    summary: 'ADRs explain why the design exists. Use C4 here to connect each decision back to system context, service boundaries, and the code or governance layer the decision actually changes.',
    focus: 'Governance first, then context and containers so each decision stays attached to a real architecture boundary.',
    levels: ['context', 'containers', 'governance', 'lifecycle'],
  },
  'ai-orchestration': {
    title: 'AI orchestration deep dive — C4 view',
    summary: 'This page sits between service architecture and AI runtime control flow. The useful C4 lens is how policy, planner, worker, and guardrail containers break apart, then how their internal components cooperate.',
    focus: 'Containers and components are the primary lens; governance matters because orchestration decisions can trigger tools and policy checks.',
    levels: ['containers', 'components', 'governance', 'observability'],
  },
  architect: {
    title: 'Architect deep dive — C4 view',
    summary: 'The architect lens spans every abstraction level. Use this strip to move from system scope and trust boundaries down to deployable services, internal components, and lifecycle controls.',
    focus: 'Context and containers first, then governance and lifecycle for the operating model.',
    levels: ['context', 'containers', 'components', 'governance', 'lifecycle'],
  },
  breakers: {
    title: 'Circuit breakers deep dive — C4 view',
    summary: 'Breakers are not business-context diagrams; they live inside service boundaries and dependency calls. Use C4 here to separate where breakers are deployed from the code and observability needed to run them safely.',
    focus: 'Components and code first, then observability for thresholds, states, and alerting.',
    levels: ['containers', 'components', 'code', 'observability'],
  },
  checklist: {
    title: 'Production-readiness checklist — C4 view',
    summary: 'This checklist is a lifecycle artifact that spans the entire C4 model. Use it to verify that context, containers, components, code, governance, observability, and rollout are all represented in release evidence.',
    focus: 'Lifecycle and governance first, then use the lower levels to find missing evidence.',
    levels: ['context', 'containers', 'components', 'governance', 'observability', 'lifecycle'],
  },
  cicd: {
    title: 'CI/CD deep dive — C4 view',
    summary: 'CI/CD mostly lives at lifecycle and code level, but it still depends on container boundaries, rollback strategy, and operational evidence.',
    focus: 'Lifecycle first, then code and observability for gates, artifacts, rollback, and verification.',
    levels: ['containers', 'code', 'observability', 'lifecycle'],
  },
  'code-quality': {
    title: 'Code quality deep dive — C4 view',
    summary: 'This page is closest to the code level of C4, but it still benefits from understanding which containers and components the code belongs to so standards do not become abstract.',
    focus: 'Code is the main lens, with components as the structural frame.',
    levels: ['components', 'code', 'governance'],
  },
  data: {
    title: 'Data preprocessing deep dive — C4 view',
    summary: 'Preprocessing crosses ingestion lifecycle, retrieval quality, and storage design. Use C4 to separate data-flow lifecycle concerns from the components and code that implement them.',
    focus: 'Components and lifecycle are the strongest lens here.',
    levels: ['containers', 'components', 'code', 'lifecycle'],
  },
  database: {
    title: 'Database deep dive — C4 view',
    summary: 'Datastore design appears at multiple abstraction levels: store placement, service ownership, repository code, governance, and data lifecycle. This page uses all of them.',
    focus: 'Containers for placement, then components/code for RLS, repositories, indexing, and store-specific mechanics.',
    levels: ['containers', 'components', 'code', 'governance', 'lifecycle'],
  },
  'eng-manager': {
    title: 'Engineering manager deep dive — C4 view',
    summary: 'The EM lens is less about code and more about governance, delivery, and lifecycle ownership across teams. C4 still helps by tying delivery responsibilities back to real system boundaries.',
    focus: 'Governance and lifecycle are the main lens, with context for org and stakeholder scope.',
    levels: ['context', 'governance', 'lifecycle'],
  },
  explainability: {
    title: 'Explainability deep dive — C4 view',
    summary: 'Explainability is a cross-cutting AI concern. Use C4 to see which containers and components must expose evidence, and which governance controls make that evidence trustworthy.',
    focus: 'Components and governance first, then observability for evidence trails.',
    levels: ['containers', 'components', 'governance', 'observability'],
  },
  'fine-tuning': {
    title: 'Fine-tuning deep dive — C4 view',
    summary: 'Fine-tuning spans data lifecycle, model governance, evaluation, and deployment controls. C4 helps keep training, registry, and serving responsibilities separate.',
    focus: 'Lifecycle and governance are primary, with containers and components for training/eval/serving boundaries.',
    levels: ['containers', 'components', 'governance', 'observability', 'lifecycle'],
  },
  guardrails: {
    title: 'Guardrails deep dive — C4 view',
    summary: 'Guardrails sit inside request flow but are governed by policy and audit. C4 helps separate guardrail placement from the policy, logging, and enforcement code behind it.',
    focus: 'Components and governance first, then code and observability.',
    levels: ['containers', 'components', 'code', 'governance', 'observability'],
  },
  jad: {
    title: 'JAD deep dive — C4 view',
    summary: 'JAD is a planning and collaboration method, but the output feeds directly into system context, container boundaries, and architecture decisions.',
    focus: 'Context and governance first, then containers as the output of good discovery.',
    levels: ['context', 'containers', 'governance', 'lifecycle'],
  },
  ldap: {
    title: 'LDAP deep dive — C4 view',
    summary: 'Directory integration is mostly a boundary and trust-zone concern. Use C4 here to reason about identity system context, service boundaries, and auth component placement.',
    focus: 'Context and containers first, then components and governance for identity flows.',
    levels: ['context', 'containers', 'components', 'governance'],
  },
  llmops: {
    title: 'LLMOps deep dive — C4 view',
    summary: 'LLMOps stretches beyond model serving into governance, experiments, evaluation, deployment, and observability. The C4 extension levels are especially relevant here.',
    focus: 'Governance, observability, and lifecycle are the primary lens for LLMOps.',
    levels: ['containers', 'components', 'governance', 'observability', 'lifecycle'],
  },
  'load-testing': {
    title: 'Load testing deep dive — C4 view',
    summary: 'Load testing validates whether the container and component design survives real pressure. It also feeds lifecycle and observability decisions around release gating.',
    focus: 'Observability and lifecycle first, with containers/components as the pressure targets.',
    levels: ['containers', 'components', 'observability', 'lifecycle'],
  },
  mcp: {
    title: 'MCP deep dive — C4 view',
    summary: 'MCP is a protocol and integration boundary. Use C4 to separate system context and trust boundaries from the actual deployable MCP servers, internal components, and audit controls.',
    focus: 'Context and containers first, then governance and observability for protocol safety.',
    levels: ['context', 'containers', 'components', 'governance', 'observability'],
  },
  microservices: {
    title: 'Microservices deep dive — C4 view',
    summary: 'This page is almost a textbook C4 Level 2 and 3 surface: service boundaries, deployable units, and internal patterns such as saga, outbox, retries, and breakers.',
    focus: 'Containers first, then components, code, and observability.',
    levels: ['containers', 'components', 'code', 'observability'],
  },
  pii: {
    title: 'PII deep dive — C4 view',
    summary: 'PII handling is primarily a trust-boundary and governance problem, but it still needs component placement and lifecycle controls across ingestion, retrieval, and logging.',
    focus: 'Governance first, then context and lifecycle.',
    levels: ['context', 'components', 'governance', 'observability', 'lifecycle'],
  },
  'post-release': {
    title: 'Post-release deep dive — C4 view',
    summary: 'This page lives in the operational half of the C4 extension. Use it to connect deployable architecture to runtime evidence, rollback, and ongoing lifecycle discipline.',
    focus: 'Observability and lifecycle first, then containers for rollout scope.',
    levels: ['containers', 'observability', 'lifecycle'],
  },
  principles: {
    title: 'Architecture principles deep dive — C4 view',
    summary: 'Principles shape code and component design, but they also constrain service boundaries and governance. C4 keeps them tied to real architecture, not slogans.',
    focus: 'Components and code first, with governance to enforce principles consistently.',
    levels: ['containers', 'components', 'code', 'governance'],
  },
  python: {
    title: 'Python deep dive — C4 view',
    summary: 'Python concepts mostly live at the code level, but this page becomes more useful when you tie language choices back to the components and services they power.',
    focus: 'Code first, then components for where the language patterns actually matter.',
    levels: ['components', 'code', 'observability'],
  },
  rag: {
    title: 'RAG deep dive — C4 view',
    summary: 'RAG spans the full AI-extended C4 model: user/system context, retrieval containers, chunking and ranking components, prompt/runtime code, governance, observability, and lifecycle.',
    focus: 'Containers and components first, then governance and lifecycle for evaluation, drift, and release readiness.',
    levels: ['context', 'containers', 'components', 'governance', 'observability', 'lifecycle'],
  },
  rbac: {
    title: 'RBAC / ABAC deep dive — C4 view',
    summary: 'Authorization design starts at trust boundaries and identity context, then flows into policy components, enforcement code, and audit evidence.',
    focus: 'Context and governance first, then components and code for policy enforcement.',
    levels: ['context', 'components', 'code', 'governance', 'observability'],
  },
  rollout: {
    title: 'Rollout deep dive — C4 view',
    summary: 'Rollout, rollback, and health probes are lifecycle controls layered on top of container architecture and code artifacts.',
    focus: 'Lifecycle first, then containers and observability for safe deployment.',
    levels: ['containers', 'code', 'observability', 'lifecycle'],
  },
  security: {
    title: 'Security deep dive — C4 view',
    summary: 'Security is where the AI-extended C4 model matters most: trust boundaries, deployable zones, policy components, secure code, governance, and observable controls.',
    focus: 'Context and governance first, then containers and code for practical enforcement.',
    levels: ['context', 'containers', 'code', 'governance', 'observability'],
  },
  sidecar: {
    title: 'Sidecar deep dive — C4 view',
    summary: 'Sidecar architecture is a container-boundary pattern. Use C4 to separate container deployment, internal advisory components, and the lifecycle/observability trail they create.',
    focus: 'Containers first, then components and observability.',
    levels: ['containers', 'components', 'observability', 'lifecycle'],
  },
  sso: {
    title: 'SSO deep dive — C4 view',
    summary: 'SSO is primarily about external trust boundaries and identity integration, then internal authorization components and governance controls.',
    focus: 'Context first, then containers and governance.',
    levels: ['context', 'containers', 'components', 'governance'],
  },
  'tech-evolution': {
    title: 'Technical evolution deep dive — C4 view',
    summary: 'Technical evolution is about how the architecture changes over time. That makes lifecycle and governance the main lens, grounded in the context and container boundaries that are evolving.',
    focus: 'Lifecycle and governance first, then context and containers.',
    levels: ['context', 'containers', 'governance', 'lifecycle'],
  },
  techlead: {
    title: 'Tech lead deep dive — C4 view',
    summary: 'The tech lead lens spans service boundaries, contract design, rollout gates, and release evidence. C4 helps tie API contracts and checklist discipline back to real architecture layers.',
    focus: 'Containers and governance first, then code and lifecycle for release control.',
    levels: ['containers', 'components', 'code', 'governance', 'lifecycle'],
  },
  'technical-plan': {
    title: 'Technical plan deep dive — C4 view',
    summary: 'A technical plan translates business intent into context, containers, components, code changes, and rollout steps. The C4 model is the structural backbone of that translation.',
    focus: 'Context and containers first, then lifecycle for execution sequencing.',
    levels: ['context', 'containers', 'components', 'lifecycle'],
  },
  tracing: {
    title: 'Tracing deep dive — C4 view',
    summary: 'Tracing is an operational concern, but it maps directly to container boundaries, internal request-flow components, and code-level propagation mechanisms.',
    focus: 'Observability first, then components and code for propagation details.',
    levels: ['containers', 'components', 'code', 'observability'],
  },
  'voice-ai': {
    title: 'Voice AI deep dive — C4 view',
    summary: 'Voice AI combines external identity or voice systems, internal speech and auth components, and governance controls around biometric data and operational evidence.',
    focus: 'Context and components first, then governance and observability.',
    levels: ['context', 'containers', 'components', 'governance', 'observability'],
  },
};

const FALLBACK: DeepDiveConfig = {
  title: 'Admin deep dive — C4 view',
  summary: 'This deep-dive page belongs somewhere on the C4 ladder. Use the strip to decide whether you are reasoning about business context, deployable containers, internal components, code, governance, observability, or lifecycle.',
  focus: 'Start with containers and components, then jump to governance or lifecycle if the topic is operational or policy-heavy.',
  levels: ['containers', 'components', 'code', 'governance', 'observability'],
};

export default function AdminDeepDiveC4Strip() {
  const pathname = usePathname();
  if (!pathname) return null;
  if (!pathname.startsWith('/admin/')) return null;
  if (!pathname.endsWith('/deep')) return null;
  if (pathname === '/admin/c4-model/deep') return null;

  const parts = pathname.split('/').filter(Boolean);
  const key = parts[1];
  const config = CONFIG[key] ?? FALLBACK;

  return (
    <C4PageLinks
      title={config.title}
      summary={config.summary}
      focus={config.focus}
      levels={config.levels}
    />
  );
}
