'use client';

import DeepDiveCrossRefs from '../../../../components/DeepDiveCrossRefs';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'sidecar-event-memory',
    title: '1. Sidecar event memory (paste → advice → rating)',
    status: 'shipped',
    coreConcept: 'A SQLite-backed event store that persists every PR-review paste, the advice the council produced, the operator rating, and rating metadata (review_kind, agreement, comment). One row per event; one source of truth for the operator dashboard.',
    problem: 'Council advice is forgotten as soon as the user closes the tab. Without persistence, there is no way to: retrain on past judgements, surface prior advice to disambiguate a new paste, audit what an operator saw at decision time, or compute reviewer-agreement metrics.',
    whyThisApproach: 'SQLite WAL + busy_timeout fits the Phase-1 volume (one event per paste, not high-throughput). Migrations are numbered SQL files; runner is minimal — `CREATE TABLE IF NOT EXISTS` makes re-applies idempotent. No ORM overhead.',
    whenToUse: ['Per-event audit + rating', 'Operator dashboard event history', 'Reviewer-agreement metrics', 'Retraining advisory prompts on past pastes'],
    whenNotToUse: ['High-write throughput (>100 ev/s) — switch to Postgres', 'Multi-region operation — needs replication', 'Cross-tenant isolation enforced at storage layer — RLS not available'],
    input: 'event row: { event_id, content, paste_hash, advice_json, rating, review_kind, agreement, comment, created_at }',
    process: [
      'Paste arrives → content_hash computed (sha256[:16])',
      'Advisor runs council → advice JSON returned',
      'Insert into events with paste_hash; UNIQUE on (paste_hash, advisor_version)',
      'Operator rates → UPDATE events SET rating, review_kind, agreement, comment',
      'Frontend queries with offset/limit + filters → SELECT with WHERE',
    ],
    output: 'Persistent event row + queryable history. Rating metadata exposed via /api/v1/sidecar/events/[id]/rating.',
    flowchart: `flowchart LR
  paste[User paste] -->|sha256[:16]| h[paste_hash]
  h --> ev[(events table)]
  council[Council run] --> ev
  ev --> dash[/admin/sidecar/]
  rate[Operator rating] -->|UPDATE| ev
  ev --> drill[/[id]/page.tsx event view/]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant FE as /admin/sidecar
  participant SC as sidecar-advisor
  participant DB as advisor.db (SQLite)
  U->>FE: paste PR diff
  FE->>SC: POST /events { content }
  SC->>SC: hash + run council
  SC->>DB: INSERT events
  DB-->>SC: event_id
  SC-->>FE: { event_id, advice }
  U->>FE: rate event (👍 / ✓ / ✗)
  FE->>SC: POST /events/{id}/rating
  SC->>DB: UPDATE events SET rating, review_kind
  DB-->>SC: ok
  SC-->>FE: 200`,
    alternatives: [
      { name: 'Postgres from day 1', tradeoff: 'Heavier; requires DB; overkill for Phase-1 single-process advisor' },
      { name: 'In-memory dict', tradeoff: 'Lost on restart; no audit trail; cannot meet ADR-013 audit retention' },
      { name: 'Append-only JSON log', tradeoff: 'Cheap; no query/UPDATE for rating; no concurrent reads' },
    ],
    challenges: [
      'WAL contention on concurrent UI + CLI access',
      'paste_hash collisions (truncated SHA prefix)',
      'Schema evolution via numbered SQL with no rollback',
      'Event volume growth — no automatic archival yet',
    ],
    edgeCases: [
      { case: 'Same paste rated twice', solution: 'UPDATE not INSERT; rating audit log captures revisions' },
      { case: 'Rating without prior content', solution: 'Foreign-key check on event_id; 404 if missing' },
      { case: 'Operator changes mind on review_kind', solution: 'Last-write-wins; comment field preserves rationale' },
      { case: 'WAL file growth in long sessions', solution: 'PRAGMA wal_checkpoint on advisor restart' },
    ],
    failureModes: [
      { mode: 'Schema migration fails mid-startup', detect: '_migrations table out of sync with files in migrations/', recover: 'Apply remaining migrations manually; re-run; idempotent' },
      { mode: 'SQLite file corrupts under concurrent writers', detect: 'BUSY errors despite busy_timeout', recover: 'Restart advisor; SQLite recovers from WAL; backup before' },
      { mode: 'paste_hash truncation collision', detect: 'UNIQUE constraint violation on insert with different content', recover: 'Increase hash length to sha256[:32]; backfill' },
    ],
    monitoring: [
      'documind_advisor_events_total{rating,kind}',
      'documind_advisor_rating_latency_p95',
      '_migrations table content (every advisor restart logs applied versions)',
      '/admin/sidecar event count + rating distribution panel',
    ],
    testing: [
      'drill_sidecar_advisor_record_rating (round-trip insert + update)',
      'drill_sidecar_rating_metadata (review_kind/agreement/comment columns)',
      'drill_sidecar_rating_route (Next.js BFF endpoint contract)',
      'drill_sidecar_rating_surface (UI event list + drill-down)',
    ],
    security: ['Paste content may contain code secrets — rely on §38 redaction at advisor layer, not at DB', 'No PII column labels (event_id is opaque UUID)', 'WAL file inherits parent dir perms; chmod 600 on advisor.db'],
    scaling: [
      '10x: SQLite WAL handles ~10 events/s comfortably',
      '100x: switch to Postgres + connection pool; migrations port directly',
      'Cost driver: paste content size; consider compression at >1MB pastes',
    ],
    maturity: {
      mvp: 'In-memory dict — lost on restart',
      production: 'SQLite WAL + numbered migrations + rating metadata + UI queries',
      enterprise: 'Postgres + RLS per tenant + automatic archival + cross-region replication',
    },
    limitations: [
      'No tenant isolation at storage layer (single-tenant deployment)',
      'No automatic archival — event volume grows unbounded',
      'No full-text search on paste content',
    ],
    projectFit: [
      'services/sidecar-advisor/memory.py — SQLite wrapper',
      'services/sidecar-advisor/migrations/{001-003}.sql — schema evolution',
      'services/frontend/lib/sidecar.ts — query layer',
      'services/frontend/app/admin/sidecar/[eventId]/page.tsx — drill-down',
      'drill_sidecar_advisor_record_rating + 3 sibling drills lock the contract',
    ],
    interviewLine: 'Sidecar memory is the difference between a chatbot and an advisory system — once you can recall what was said, you can rate it, retrain on it, and audit it. SQLite was the right tool for Phase-1 because volume is one paste per user, not RPS.',
    implementationSteps: [
      { step: 'Numbered migrations', logic: 'migrations/NNN_*.sql files; runner applies in order; tracked in _migrations table.' },
      { step: 'SQLite WAL mode', logic: 'PRAGMA journal_mode=WAL + busy_timeout=5000 → safe concurrent UI + CLI reads.' },
      { step: 'Paste hash dedup', logic: 'sha256[:16] of content + advisor_version; UNIQUE → idempotent inserts.' },
      { step: 'Rating UPDATE path', logic: 'Separate endpoint; UPDATE not INSERT; rating + review_kind + agreement + comment columns.' },
      { step: 'Query layer', logic: 'sidecar.ts in BFF wraps SELECT with offset/limit + filters; pagination + totals in one round-trip.' },
      { step: 'Drill the contract', logic: 'Four drills: insert, metadata columns, BFF route, UI surface — locks every layer.' },
      { step: 'Drill-down view', logic: '/admin/sidecar/[eventId] renders one event with full advice JSON + rating audit.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/sidecar-advisor/memory.py — Phase-1 SQLite event store
import hashlib, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

class AdvisorMemory:
    def __init__(self, db_path="advisor.db"):
        self._db_path = str(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def record_event(self, content: str, advice: dict, advisor_version: str) -> str:
        paste_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        event_id = f"ev_{paste_hash}_{advisor_version[:8]}"
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO events "
                "(event_id, paste_hash, content, advice_json, advisor_version, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (event_id, paste_hash, content, json.dumps(advice),
                 advisor_version, datetime.now(timezone.utc).isoformat()),
            )
        return event_id

    def record_rating(self, event_id: str, rating: int,
                      review_kind: str, agreement: str, comment: str) -> None:
        with self._connect() as c:
            c.execute(
                "UPDATE events SET rating=?, review_kind=?, agreement=?, "
                "comment=?, rated_at=? WHERE event_id=?",
                (rating, review_kind, agreement, comment,
                 datetime.now(timezone.utc).isoformat(), event_id),
            )`,
    },
    starStory: {
      situation: 'Council advice was vanishing as soon as the user closed the tab. Operators wanted to compare a new paste against prior reviews and rate the council\'s judgement.',
      task: 'Persistent event memory + rating metadata + drill-down view, without breaking the single-process Phase-1 footprint.',
      action: 'Built memory.py on SQLite WAL + numbered migrations. Added rating columns in 003_event_rating_metadata.sql. BFF query layer in sidecar.ts. Four drills: insert, metadata, route, UI.',
      result: 'Operator dashboard now shows event history with filters, totals, and reviewer-agreement counts. Rating audit trail preserved. ADR-013 audit-retention obligation met.',
    },
    interviewTraps: [
      'Suggesting Postgres at Phase 1 (over-engineered; SQLite WAL is sufficient)',
      'Putting paste content in metric labels (cardinality bomb + PII risk)',
      'Skipping numbered migrations (Alembic is overkill but ad-hoc DDL is worse)',
    ],
    finalScript: 'The sidecar event memory turned the council from a one-shot advisor into a learning system. SQLite WAL handles the Phase-1 volume; numbered migrations evolve schema safely; rating metadata captures operator judgement; four drills lock the contract end-to-end. The BFF queries pagination + totals in one round-trip, so the operator dashboard scales without N+1. When volume grows past ~10 ev/s, the migrations port to Postgres untouched. That is what makes SQLite a Phase-1 choice, not a Phase-1 trap.',
  },
  {
    slug: 'orchestrator-project-memory',
    title: '2. Orchestrator project memory (LangGraph state + Postgres)',
    status: 'shipped',
    coreConcept: 'Postgres-backed project store for the agent-orchestrator service. Holds: project metadata, plan steps, agent state, approval history, policy scenarios, and project memory rows. LangGraph reads + writes this between agent turns so state survives restarts and crashes.',
    problem: 'LangGraph in-memory state vanishes on process restart. For multi-step agentic workflows that span human approval gates, the orchestrator MUST resume mid-flight. Without durable storage, every restart resets the plan; approval history is lost; agent decisions become irreproducible.',
    whyThisApproach: 'Postgres gives ACID guarantees + JSONB flexibility for evolving agent payloads. Numbered migrations under migrations/ keep schema reproducible. The store boundary (postgres_store.py) is the single SQL surface — agents never touch SQL.',
    whenToUse: ['Multi-step agentic workflows with approval gates', 'Long-running plans (hours to days)', 'Human-in-the-loop with audit trail', 'Anything requiring restart-resume semantics'],
    whenNotToUse: ['Single-shot LLM calls (no state)', 'Stateless RAG retrieval (vector + cache only)', 'Sub-second latency requirements where Postgres round-trip dominates'],
    input: 'project_id + agent step + decision payload + actor + timestamp',
    process: [
      'Project created → INSERT projects + INSERT project_plan',
      'Agent picks next step → SELECT plan WHERE status=pending ORDER BY step_no',
      'Agent runs → produces decision + audit row → INSERT agentic_project_memory',
      'Approval gate → blocks until row in approval_automation has decision',
      'On approval → UPDATE plan status; LangGraph resumes',
    ],
    output: 'Durable project state + audit trail + resumable plan execution.',
    flowchart: `flowchart LR
  cli[Operator] -->|create project| api[/POST /projects/]
  api --> pg[(Postgres: projects, plan, memory)]
  agent[LangGraph agent] -->|read state| pg
  agent -->|write decision| pg
  agent --> gate{approval needed?}
  gate -->|yes| approve[(approval_automation)]
  approve -.user signs off.-> resume[LangGraph resume]
  resume --> agent`,
    sequence: `sequenceDiagram
  autonumber
  participant Op as Operator
  participant API as orchestrator API
  participant LG as LangGraph
  participant PG as Postgres
  Op->>API: POST /projects { spec }
  API->>PG: INSERT projects + plan
  API-->>Op: { project_id }
  loop until plan complete
    LG->>PG: SELECT next pending step
    LG->>LG: run agent
    LG->>PG: INSERT agentic_project_memory + UPDATE plan
    alt approval gate
      LG->>PG: INSERT approval_automation pending
      Op->>API: POST /projects/:id/approve
      API->>PG: UPDATE approval_automation
      LG->>PG: SELECT approval; resume
    end
  end
  LG->>PG: UPDATE plan status=complete`,
    alternatives: [
      { name: 'In-memory LangGraph state', tradeoff: 'Lost on restart; no human-in-loop possible across sessions' },
      { name: 'Redis state', tradeoff: 'Faster but no JSONB queryability; durability requires AOF' },
      { name: 'Event sourcing (Kafka)', tradeoff: 'Maximum auditability but heavy; needs replay engine' },
    ],
    challenges: [
      'Schema evolution while LangGraph flows are mid-run',
      'Approval gate timeouts (operator never returns)',
      'Idempotent agent step execution under restart',
      'Memory growth across long-running projects',
    ],
    edgeCases: [
      { case: 'Restart during agent step', solution: 'Step-level idempotency key; agent checks before re-executing tool' },
      { case: 'Approval never granted', solution: 'TTL on approval rows; auto-reject after N hours per ADR-009' },
      { case: 'Concurrent agent updates to same project', solution: 'Postgres row-level lock on project; only one agent advances plan' },
      { case: 'Migration during running project', solution: 'Backwards-compatible additions only; never DROP COLUMN; expand-migrate-contract per global §28' },
    ],
    failureModes: [
      { mode: 'PG connection lost mid-step', detect: 'agent tool calls return 5xx; no plan progress', recover: 'connection pool retries; agent step is idempotent so safe to retry' },
      { mode: 'Approval gate stuck', detect: 'plan rows in pending > N hours', recover: 'ADR-009 worker auto-reject after threshold; alert operator' },
      { mode: 'Plan order corrupted', detect: 'step_no skipped or duplicate', recover: 'rebuild from agentic_project_memory append-only log' },
    ],
    monitoring: [
      'documind_orchestrator_plan_steps_total{status}',
      'documind_orchestrator_approval_pending_seconds (histogram)',
      'documind_orchestrator_agent_runtime_seconds (per agent)',
      '/admin/agentic project list with plan progress',
    ],
    testing: [
      'drill_orchestrator_plan_lifecycle (insert → run → complete)',
      'drill_orchestrator_memory_persistence (restart → resume)',
      'drill_orchestrator_approval_flow (pending → approve → resume)',
    ],
    security: [
      'Project scope enforced at API layer + Postgres RLS by tenant_id',
      'Agent payloads in JSONB may contain user input — guardrails layer redacts',
      'Approval audit trail immutable (no UPDATE on approval_automation rows)',
    ],
    scaling: [
      '10x: single Postgres handles ~100 concurrent projects',
      '100x: read replicas for SELECT-heavy LangGraph reads; primary for writes',
      'Cost driver: agentic_project_memory row count; archive completed projects to cold storage',
    ],
    maturity: {
      mvp: 'LangGraph in-memory only — works once, dies on restart',
      production: 'Postgres-backed plan + memory + approval + 7 numbered migrations',
      enterprise: 'Multi-tenant RLS + cross-region read replicas + cold-storage archive + saga compensation',
    },
    limitations: [
      'No saga / compensation for partial-failure rollback',
      'No event-sourced replay (state is mutable per row)',
      'Schema is single-tenant; RLS planned but not active',
    ],
    projectFit: [
      'services/agent-orchestrator-svc/app/postgres_store.py — single SQL surface',
      'services/agent-orchestrator-svc/migrations/{001-007}.sql — 7 schema migrations including agentic_project_memory',
      'services/agent-orchestrator-svc/app/langgraph_flow.py — LangGraph wiring that reads/writes state',
      '/admin/agentic + /admin/agentic/control-plane — operator surface',
    ],
    interviewLine: 'LangGraph state is in-memory by default. Wrap it in Postgres + numbered migrations and you turn a one-shot agent into a multi-step plan that survives restarts, supports human-in-the-loop, and produces an audit trail. The migration discipline is what makes it survive a year of feature drift.',
    implementationSteps: [
      { step: 'Numbered migrations', logic: '7 migrations including 007_agentic_project_memory.sql; runner applies + tracks via _migrations.' },
      { step: 'Single SQL surface', logic: 'postgres_store.py wraps every read/write; agents never write SQL.' },
      { step: 'Plan lifecycle', logic: 'projects → project_plan → status state-machine (pending → running → complete / failed).' },
      { step: 'Memory append', logic: 'agentic_project_memory append-only; one row per agent decision; full audit.' },
      { step: 'Approval gates', logic: 'approval_automation rows; LangGraph blocks SELECTing approved=true.' },
      { step: 'Idempotent steps', logic: 'Each agent step has idempotency_key; re-execution after restart is safe.' },
      { step: 'Drill the resume', logic: 'drill_orchestrator_memory_persistence forces a restart, verifies plan resumes from correct step.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/agent-orchestrator-svc/app/postgres_store.py
import json, psycopg
from datetime import datetime, timezone

class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def append_memory(self, project_id: str, step_no: int,
                      agent: str, decision: dict,
                      idempotency_key: str) -> None:
        """Append-only — never UPDATE; full audit trail."""
        with psycopg.connect(self._dsn) as conn, conn.cursor() as c:
            c.execute(
                """INSERT INTO agentic_project_memory
                   (project_id, step_no, agent_name, decision, idempotency_key, created_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s)
                   ON CONFLICT (project_id, idempotency_key) DO NOTHING""",
                (project_id, step_no, agent, json.dumps(decision),
                 idempotency_key, datetime.now(timezone.utc)),
            )

    def next_pending_step(self, project_id: str) -> dict | None:
        with psycopg.connect(self._dsn) as conn, conn.cursor() as c:
            c.execute(
                """SELECT step_no, agent_name, payload
                   FROM project_plan
                   WHERE project_id=%s AND status='pending'
                   ORDER BY step_no LIMIT 1
                   FOR UPDATE SKIP LOCKED""",
                (project_id,),
            )
            row = c.fetchone()
            if row is None:
                return None
            return {"step_no": row[0], "agent": row[1], "payload": row[2]}`,
    },
    starStory: {
      situation: 'LangGraph agents lost all state on restart. Operators couldn\'t pause an agentic plan for human approval; multi-step workflows had to complete in one process lifetime.',
      task: 'Postgres-backed durable state + approval gates + idempotent agent steps, without rewriting LangGraph.',
      action: 'Built postgres_store.py as the single SQL surface. 7 numbered migrations covering projects, plan, memory, approval, scenarios. langgraph_flow.py reads + writes via the store between agent turns. Idempotency keys per step.',
      result: 'Agents now resume mid-flight after restarts. Approval gates block plans for hours/days without state loss. /admin/agentic shows live plan progress. ADR-009 worker-auto-reject prevents stuck approvals from haunting the queue.',
    },
    interviewTraps: [
      'Storing LangGraph state as an opaque blob (no migrability; debug nightmare)',
      'No idempotency on agent steps (restart re-executes side effects)',
      'Saga / compensation as an afterthought (better to design rollback up-front)',
    ],
    finalScript: 'Orchestrator memory is the difference between a demo agent and an enterprise one. Postgres + numbered migrations + idempotent steps + approval gates is the minimum durable substrate. The agent never sees SQL — postgres_store.py is the boundary. LangGraph reads state between turns and writes decisions append-only. When approval gates the plan, the row in approval_automation blocks resume until the operator signs off. That is what makes a multi-day human-in-loop workflow work.',
  },
];

export default function MemoryDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Memory deep dive</h1>
          <p className="page-subtitle">
            Two persistence surfaces — sidecar event memory (SQLite, paste +
            advice + rating) and orchestrator project memory (Postgres,
            LangGraph state + plan + approvals) — explained through the
            universal 20-dimension framework.
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
          { href: '/admin/sidecar/deep', label: 'Sidecar deep-dive', why: 'event memory is the sidecar advisor\'s persistence layer; this page details its schema + lifecycle' },
          { href: '/admin/agentic/control-plane', label: 'Agentic control plane', why: 'orchestrator project memory is what the control plane reads to render plan progress + approvals' },
          { href: '/admin/database/deep#postgres-rls', label: 'Postgres + RLS', why: 'the orchestrator store is the canonical Postgres consumer; RLS is the next-step tenant boundary' },
          { href: '/admin/explainability/deep', label: 'Explainability evidence', why: 'agentic_project_memory is the append-only decision audit trail explainability requires per §48' },
          { href: '/admin/checklist/deep#governance-ops-checklist', label: 'Governance gate', why: 'memory must persist agent decisions or the audit row is incomplete — release-blocking per §38' },
        ]}
      />
    </>
  );
}
