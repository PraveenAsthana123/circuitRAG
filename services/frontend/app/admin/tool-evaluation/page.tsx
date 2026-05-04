/**
 * /admin/tool-evaluation — usefulness + safety analysis of 13 candidate tools.
 *
 * Per CLAUDE.md §16 (dependency mgmt) + §28 (security) + §47.6 (DevSecOps
 * shift-left). This is a Server Component (static analysis page) — no
 * runtime queries, just documented evaluation per tool.
 *
 * Verdicts use a 3-color scheme:
 *   ✅ green  = useful + safe; integrate when use case matches
 *   ⚠️ amber  = case-by-case; sandbox-only or specific-use-only
 *   ❌ red    = skip; either unsafe, deprecated, or out-of-scope for our stack
 */

import Link from 'next/link';

type Verdict = 'integrate' | 'sandbox-only' | 'specific-use' | 'skip';

const VERDICT_STYLE: Record<Verdict, { bg: string; fg: string; icon: string }> = {
  integrate:    { bg: '#dff2dd', fg: '#1f8a4c', icon: '✅' },
  'sandbox-only': { bg: '#fef3e1', fg: '#c47a1a', icon: '⚠️' },
  'specific-use': { bg: '#fef3e1', fg: '#c47a1a', icon: '⚠️' },
  skip:         { bg: '#fdeaea', fg: '#a4262c', icon: '❌' },
};

type ToolEval = {
  name: string;
  category: 'ai-framework' | 'minecraft';
  purpose: string;
  license: string;
  maintenance: string;
  useful: { score: 'high' | 'medium' | 'low'; reason: string };
  safe: { score: 'high' | 'medium' | 'low'; concerns: string };
  verdict: Verdict;
  recommendation: string;
};

const TOOLS: ToolEval[] = [
  // ── AI agent frameworks ───────────────────────────────────────────────
  {
    name: 'LiteLLM',
    category: 'ai-framework',
    purpose: 'Unified LLM gateway — single API for OpenAI / Anthropic / Ollama / 100+ providers. Drop-in replacement for native SDKs.',
    license: 'MIT',
    maintenance: 'Active (BerriAI). Daily commits. ~13k stars.',
    useful: {
      score: 'high',
      reason: 'Replaces direct curl/httpx to Ollama with provider-agnostic interface. Adds cost tracking, retry logic, fallback chains, caching out of the box. Could simplify scripts/local_council.py call_ollama by ~50 lines.',
    },
    safe: {
      score: 'high',
      concerns: 'Pure-Python; respects PolisAI scope tokens (we own the wrapper). No data persistence on its side — pass-through. Single Python dep with permissive license.',
    },
    verdict: 'integrate',
    recommendation: 'Stage-2 swap: replace call_ollama() body with litellm.completion(model="ollama/<name>", ...). Keeps PolisAI gate intact. Adds telemetry + fallback. ~4hr work + drill update.',
  },
  {
    name: 'PydanticAI',
    category: 'ai-framework',
    purpose: 'Type-safe agent framework from Pydantic team. Schemas = function signatures; tools = validated dataclasses.',
    license: 'MIT',
    maintenance: 'Active (Pydantic team). v0.x — API still evolving. ~6k stars.',
    useful: {
      score: 'high',
      reason: 'Already use Pydantic for CouncilProposal + RouterDecision. PydanticAI extends the schema-as-contract discipline to agent tools. Natural fit for §55 Tier 1 (schema-as-contract upgrade).',
    },
    safe: {
      score: 'high',
      concerns: 'Pydantic itself is rock-solid (used at every boundary). API churn at v0.x is the only risk — pin minor version + drill the contract.',
    },
    verdict: 'integrate',
    recommendation: 'Stage-2 candidate for the AUTHOR role specifically. Schema validation already happens; PydanticAI would formalize the tool-call contract. Lower priority than LiteLLM but architecturally cleaner.',
  },
  {
    name: 'CrewAI',
    category: 'ai-framework',
    purpose: 'Multi-agent orchestrator — Crew of role-based agents (Manager/Researcher/Writer) with task delegation.',
    license: 'MIT',
    maintenance: 'Active (CrewAI Inc.). Frequent commits. ~25k stars.',
    useful: {
      score: 'medium',
      reason: 'Conceptually overlaps with our local_council (4-role) + OpenClaw (A2A). CrewAI is more opinionated — could be a Stage-2 reference for council role names + delegation patterns. Not a drop-in replacement; rebuild cost is high.',
    },
    safe: {
      score: 'medium',
      concerns: 'Heavy dep tree (langchain + many integrations). Recent reports of telemetry-by-default — verify opt-out works before adoption. Not on PolisAI scope tokens out-of-the-box.',
    },
    verdict: 'specific-use',
    recommendation: 'Use as REFERENCE architecture (read their patterns) but do NOT add as dep. Our local_council + LangGraph already covers the same shape with stricter PolisAI gating.',
  },
  {
    name: 'Agno (formerly Phidata)',
    category: 'ai-framework',
    purpose: 'Production-grade multimodal agents with built-in memory, knowledge, and tool-use. Recent rebrand from Phidata.',
    license: 'MPL-2.0',
    maintenance: 'Active. Rebrand happened in 2024 — check naming consistency in their docs before pinning.',
    useful: {
      score: 'medium',
      reason: 'Strong on production patterns (logging, monitoring, persistent memory). Overlaps with our Langfuse + audit logs + agent_orchestrator-svc. Their persistent memory is more sophisticated than our .loop/*.jsonl.',
    },
    safe: {
      score: 'medium',
      concerns: 'MPL-2.0 (file-level copyleft) requires carrying their license headers in modified files. Telemetry phones home by default — must opt out explicitly. Newer than CrewAI; smaller community.',
    },
    verdict: 'specific-use',
    recommendation: 'Skip wholesale adoption. Borrow their persistent-memory pattern for our Stage-3 Paperclip loop (Goal→Plan→Execute→Evaluate→Improve needs durable state).',
  },
  {
    name: 'PraisonAI',
    category: 'ai-framework',
    purpose: 'Multi-agent framework that wraps CrewAI + AutoGen with simpler YAML config.',
    license: 'MIT',
    maintenance: 'Active but smaller community (~3k stars). Single primary maintainer.',
    useful: {
      score: 'low',
      reason: 'YAML-config layer over CrewAI/AutoGen. Adds a hop to the stack without much new capability. Our existing config/policies/agent_dispatch.json already does declarative agent routing.',
    },
    safe: {
      score: 'medium',
      concerns: 'Bus-factor risk (small team). Inherits CrewAI/AutoGen dep trees + their telemetry concerns. YAML-driven AI is hard to drill-test without a runtime harness.',
    },
    verdict: 'skip',
    recommendation: 'Do not adopt. Our PolisAI rules + agent_dispatch.json achieve the same declarative routing with first-class drill discipline.',
  },

  // ── Minecraft AI sandbox stack ────────────────────────────────────────
  {
    name: 'MineRL',
    category: 'minecraft',
    purpose: 'Minecraft Reinforcement Learning environment from Microsoft Research. Provides Gym-like interface for training RL agents in MC.',
    license: 'MIT (some assets BSD-3)',
    maintenance: 'Maintenance mode. Last release ~2022. Python 3.8 era — incompatible with modern stacks without effort.',
    useful: {
      score: 'low',
      reason: 'No use case in our RAG/code-fix stack. Could serve as a Stage-3 RL eval sandbox for the council (train agent to navigate MC, eval generalization), but that\'s a research project, not a production need.',
    },
    safe: {
      score: 'medium',
      concerns: 'Pulls Java + JVM + Minecraft binaries. Network sockets to a running MC server. Ships with old vulnerable deps (gym==0.21).',
    },
    verdict: 'skip',
    recommendation: 'Skip unless we explicitly research RL agent generalization. Not worth the deploy complexity for our current goals.',
  },
  {
    name: 'Project Malmo',
    category: 'minecraft',
    purpose: 'Microsoft Research\'s original Minecraft AI platform. PRECURSOR to MineRL — superseded.',
    license: 'MIT',
    maintenance: 'Deprecated. Frozen since 2018. No ongoing development.',
    useful: {
      score: 'low',
      reason: 'Superseded by MineRL. No reason to use this when MineRL exists, and even MineRL we are skipping.',
    },
    safe: {
      score: 'low',
      concerns: 'Frozen 2018; CVE-prone deps. Java + Minecraft 1.11.2 (5+ years old, known CVEs).',
    },
    verdict: 'skip',
    recommendation: 'Hard skip. Anything Malmo could do, MineRL does better; anything MineRL does, we don\'t need yet.',
  },
  {
    name: 'mineflayer',
    category: 'minecraft',
    purpose: 'JavaScript Minecraft bot framework. High-level API for controlling a player programmatically (movement, mining, chat).',
    license: 'MIT',
    maintenance: 'Active. PrismarineJS org. ~5k stars. Modern Node.js.',
    useful: {
      score: 'medium',
      reason: 'Useful ONLY if we want a creative agent-sandbox demo (e.g., "agent debugs by playing MC tutorials"). Not relevant to RAG/code-fix. Could be a fun experiment for the agent-orchestrator-svc Stage-3 LangGraph node.',
    },
    safe: {
      score: 'medium',
      concerns: 'Connects to live MC servers — same firewall/network surface as any external client. Don\'t connect to public servers without an isolated VLAN.',
    },
    verdict: 'sandbox-only',
    recommendation: 'Useful for one specific demo: "operator can dispatch an agent to a contained MC sandbox, watch it execute a multi-step plan, observe failure modes." Stage-3 research, not production.',
  },
  {
    name: 'PaperMC + plugin stack',
    category: 'minecraft',
    purpose: 'Performance-optimized Minecraft server (Paper) + Bukkit plugin ecosystem. The de facto standard for production MC servers.',
    license: 'GPL-3.0 (Paper) + various per plugin',
    maintenance: 'Very active. Production-grade. Backwards-compat across MC versions.',
    useful: {
      score: 'medium',
      reason: 'Required IF we run our own MC sandbox for mineflayer/MineRL. Plugins (LuckPerms, ProtocolLib, etc.) provide the control surfaces an agent would need.',
    },
    safe: {
      score: 'medium',
      concerns: 'GPL-3.0 means linking restrictions if we ship it. Plugin ecosystem is third-party — vet each plugin. Network-exposed by default; firewall accordingly.',
    },
    verdict: 'sandbox-only',
    recommendation: 'Only if we adopt mineflayer for the Stage-3 sandbox demo. Self-host on isolated network; don\'t accept external connections.',
  },
  {
    name: 'Crafty Controller',
    category: 'minecraft',
    purpose: 'Web-based Minecraft server management dashboard. Start/stop/configure MC servers via UI.',
    license: 'GPL-3.0',
    maintenance: 'Active. Primary use is hobbyist server admins.',
    useful: {
      score: 'low',
      reason: 'Useful only for non-technical operators managing MC servers. We have docker-compose; we don\'t need a separate dashboard.',
    },
    safe: {
      score: 'medium',
      concerns: 'Web UI exposes server-control surface. Auth must be properly configured. Audit trail varies by version.',
    },
    verdict: 'skip',
    recommendation: 'Skip. Our docker-compose + scripts/run.sh launcher already covers server lifecycle.',
  },
  {
    name: 'mc-control',
    category: 'minecraft',
    purpose: 'CLI tool for Minecraft server control. Wrapper around RCON/server commands.',
    license: 'Varies (often MIT)',
    maintenance: 'Multiple unrelated projects share this name. Bus-factor unclear. Pin to a specific repo if adopting.',
    useful: {
      score: 'low',
      reason: 'Same role as Crafty (server lifecycle) but CLI. Marginal value over `papermc-server` direct invocation.',
    },
    safe: {
      score: 'low',
      concerns: 'Name ambiguity is a supply-chain red flag — multiple repos. Without specifying which one, can\'t evaluate.',
    },
    verdict: 'skip',
    recommendation: 'Skip without a specific repo URL. Even with one, prefer direct papermc invocation.',
  },
  {
    name: 'mc-server-wrapper',
    category: 'minecraft',
    purpose: 'Process wrapper around Minecraft server jar. Handles stdin/stdout, restarts, RCON.',
    license: 'Varies per implementation',
    maintenance: 'Multiple implementations exist; quality varies.',
    useful: {
      score: 'low',
      reason: 'Solves a problem we don\'t have. systemd / docker-compose handle restart-on-fail equivalently.',
    },
    safe: {
      score: 'medium',
      concerns: 'Same name-ambiguity concern as mc-control. Operates on stdin of the JVM — if the wrapper has a bug, it breaks the server.',
    },
    verdict: 'skip',
    recommendation: 'Skip. docker-compose restart=always policies cover the restart use case.',
  },
  {
    name: 'minerl.io',
    category: 'minecraft',
    purpose: 'Website hosting MineRL competition data + datasets. Not a tool; a data source.',
    license: 'Datasets: research-use; check per-dataset terms',
    maintenance: 'Static site; competition cycles ended ~2022.',
    useful: {
      score: 'low',
      reason: 'Useful only if we run RL eval on MineRL agents. Same low-priority as MineRL itself.',
    },
    safe: {
      score: 'medium',
      concerns: 'Pure data; safe to download but verify per-dataset license before using in training.',
    },
    verdict: 'skip',
    recommendation: 'Skip unless we adopt MineRL. Even then, prefer rolling our own eval set (we control the licensing).',
  },
];

export default function ToolEvaluationPage() {
  const aiTools = TOOLS.filter((t) => t.category === 'ai-framework');
  const mcTools = TOOLS.filter((t) => t.category === 'minecraft');

  const summary = {
    integrate: TOOLS.filter((t) => t.verdict === 'integrate').length,
    sandbox: TOOLS.filter((t) => t.verdict === 'sandbox-only').length,
    specific: TOOLS.filter((t) => t.verdict === 'specific-use').length,
    skip: TOOLS.filter((t) => t.verdict === 'skip').length,
  };

  return (
    <div style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Tool Evaluation — useful + safe analysis</h1>
        <p style={{ color: '#666', marginTop: 8 }}>
          Per CLAUDE.md §16 + §28 + §47.6. Honest assessment of 13 candidate
          tools (5 AI agent frameworks + 8 Minecraft AI sandbox tools): each
          rated for usefulness, safety, and integration recommendation.
          Verdict matrix: <strong>integrate</strong> (✅), <strong>sandbox/specific-use</strong>{' '}
          (⚠️), <strong>skip</strong> (❌).
        </p>
      </header>

      {/* Summary box */}
      <section
        style={{
          padding: 16,
          border: '2px solid #ddd',
          borderRadius: 8,
          marginBottom: 24,
          background: '#fafafa',
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
        }}
      >
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            ✅ Integrate
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#1f8a4c' }}>
            {summary.integrate}
          </div>
          <div style={{ fontSize: '0.8rem', color: '#666' }}>useful + safe + fits stack</div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            ⚠️ Sandbox-only
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#c47a1a' }}>
            {summary.sandbox}
          </div>
          <div style={{ fontSize: '0.8rem', color: '#666' }}>research / experiment scope</div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            ⚠️ Specific-use
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#c47a1a' }}>
            {summary.specific}
          </div>
          <div style={{ fontSize: '0.8rem', color: '#666' }}>borrow patterns, not dep</div>
        </div>
        <div>
          <div style={{ fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>
            ❌ Skip
          </div>
          <div style={{ fontWeight: 600, fontSize: '1.5rem', color: '#a4262c' }}>
            {summary.skip}
          </div>
          <div style={{ fontSize: '0.8rem', color: '#666' }}>not for our stack</div>
        </div>
      </section>

      {/* AI agent frameworks */}
      <section style={{ marginBottom: 24 }}>
        <h2>AI agent frameworks ({aiTools.length})</h2>
        {aiTools.map((t) => {
          const v = VERDICT_STYLE[t.verdict];
          return (
            <div
              key={t.name}
              style={{
                padding: 16,
                border: '1px solid #ddd',
                borderRadius: 4,
                marginBottom: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <h3 style={{ margin: 0 }}>{t.name}</h3>
                <span
                  style={{
                    background: v.bg,
                    color: v.fg,
                    padding: '4px 12px',
                    borderRadius: 3,
                    fontWeight: 600,
                  }}
                >
                  {v.icon} {t.verdict}
                </span>
              </div>
              <p style={{ margin: '4px 0' }}>{t.purpose}</p>
              <div style={{ fontSize: '0.85rem', color: '#666', marginBottom: 8 }}>
                <strong>License:</strong> {t.license} · <strong>Maintenance:</strong>{' '}
                {t.maintenance}
              </div>
              <div style={{ marginBottom: 6 }}>
                <strong>Useful ({t.useful.score}):</strong> {t.useful.reason}
              </div>
              <div style={{ marginBottom: 6 }}>
                <strong>Safe ({t.safe.score}):</strong> {t.safe.concerns}
              </div>
              <div
                style={{
                  background: '#f8f8f8',
                  padding: 8,
                  borderRadius: 3,
                  borderLeft: `4px solid ${v.fg}`,
                }}
              >
                <strong>Recommendation:</strong> {t.recommendation}
              </div>
            </div>
          );
        })}
      </section>

      {/* Minecraft tools */}
      <section style={{ marginBottom: 24 }}>
        <h2>Minecraft AI sandbox stack ({mcTools.length})</h2>
        {mcTools.map((t) => {
          const v = VERDICT_STYLE[t.verdict];
          return (
            <div
              key={t.name}
              style={{
                padding: 16,
                border: '1px solid #ddd',
                borderRadius: 4,
                marginBottom: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <h3 style={{ margin: 0 }}>{t.name}</h3>
                <span
                  style={{
                    background: v.bg,
                    color: v.fg,
                    padding: '4px 12px',
                    borderRadius: 3,
                    fontWeight: 600,
                  }}
                >
                  {v.icon} {t.verdict}
                </span>
              </div>
              <p style={{ margin: '4px 0' }}>{t.purpose}</p>
              <div style={{ fontSize: '0.85rem', color: '#666', marginBottom: 8 }}>
                <strong>License:</strong> {t.license} · <strong>Maintenance:</strong>{' '}
                {t.maintenance}
              </div>
              <div style={{ marginBottom: 6 }}>
                <strong>Useful ({t.useful.score}):</strong> {t.useful.reason}
              </div>
              <div style={{ marginBottom: 6 }}>
                <strong>Safe ({t.safe.score}):</strong> {t.safe.concerns}
              </div>
              <div
                style={{
                  background: '#f8f8f8',
                  padding: 8,
                  borderRadius: 3,
                  borderLeft: `4px solid ${v.fg}`,
                }}
              >
                <strong>Recommendation:</strong> {t.recommendation}
              </div>
            </div>
          );
        })}
      </section>

      {/* Bottom-line */}
      <section
        style={{
          padding: 16,
          border: '2px solid #1f8a4c',
          borderRadius: 4,
          background: '#dff2dd',
          marginBottom: 16,
        }}
      >
        <h3 style={{ marginTop: 0, color: '#1f8a4c' }}>Bottom line — actionable next moves</h3>
        <ol>
          <li>
            <strong>Adopt LiteLLM</strong> as the unified LLM gateway —
            replace direct curl calls in <code>scripts/local_council.py call_ollama</code> with
            litellm. Adds cost tracking + retry + fallback. ~4hr work.
          </li>
          <li>
            <strong>Adopt PydanticAI for AUTHOR role</strong> — formalize the
            tool-call contract using PydanticAI tool definitions. Pin minor
            version. ~6hr work.
          </li>
          <li>
            <strong>Read CrewAI + Agno patterns</strong>; do NOT adopt as
            deps. Borrow their persistent-memory + role-based delegation
            patterns for our Stage-3 Paperclip loop.
          </li>
          <li>
            <strong>Skip all 8 Minecraft tools</strong> as production
            integrations. They\'re research/sandbox tools for RL agent
            experiments — out of scope for our RAG/code-fix mission.
          </li>
          <li>
            <strong>Skip PraisonAI</strong> — adds a YAML-config layer over
            CrewAI that we don\'t need (PolisAI rules already do declarative
            routing).
          </li>
        </ol>
      </section>

      {/* §49 compose footer */}
      <section
        style={{
          padding: 16,
          border: '1px dashed #999',
          borderRadius: 4,
          background: '#f8f8f8',
          fontSize: '0.85rem',
        }}
      >
        <strong>Composes with</strong> (per §49):
        <ul style={{ marginTop: 8 }}>
          <li>
            <Link href="/admin/local-models">Local models</Link> — LiteLLM
            would replace direct Ollama HTTP calls here.
          </li>
          <li>
            <Link href="/admin/agentic">Agentic framework</Link> — CrewAI /
            PydanticAI / Agno are reference architectures for this layer.
          </li>
          <li>
            <Link href="/admin/policy">PolisAI policy</Link> — any new
            framework we adopt must respect our scope tokens (drill-locked).
          </li>
          <li>
            <Link href="/admin/eval-harness">Eval harness</Link> — new
            adoptions need eval coverage before promotion (Stage-2 wiring).
          </li>
          <li>
            <Link href="/admin/explainability">Explainability</Link> — every
            framework swap must preserve the §48.4 audit row schema.
          </li>
        </ul>
      </section>
    </div>
  );
}
