-- 009_research_artifacts.sql
-- Phase B2: research artifacts produced by ResearchAgent.
--
-- Per §48.5 (RAG explainability four-part contract): every claim a
-- researcher contributes to a downstream node must trace back to a
-- chunk in the retrieval set. This table stores the retrieval trail
-- + summary + suggested approach + risks per task.
--
-- Backward compat (per §28.2): table created empty; existing tasks
-- have no rows here. Researcher node populates rows when active.
--
-- Service.py reads via list_research_artifacts(task_id) and includes
-- them in the §48 explainability row (extending C4's row schema).

CREATE TABLE IF NOT EXISTS orchestration.research_artifacts (
  artifact_id        TEXT PRIMARY KEY,
  task_id            TEXT NOT NULL REFERENCES orchestration.agent_tasks(task_id) ON DELETE CASCADE,
  tenant_id          TEXT NOT NULL,
  topic              TEXT NOT NULL,
  summary            TEXT NULL,
  sources_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
  suggested_approach TEXT NULL,
  risks_json         JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_origin      TEXT NULL,  -- 'mcp_research' | 'heuristic_fallback' | 'llm_routed'
  routing_decision   JSONB NULL, -- C4 §48.4 routing trail when LLM-routed
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_task
  ON orchestration.research_artifacts (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_tenant
  ON orchestration.research_artifacts (tenant_id, created_at DESC);

ALTER TABLE orchestration.research_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.research_artifacts FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS research_artifacts_isolation ON orchestration.research_artifacts;
CREATE POLICY research_artifacts_isolation
  ON orchestration.research_artifacts
  USING (tenant_id = current_setting('app.current_tenant', true));

COMMENT ON TABLE orchestration.research_artifacts IS
  'Per-task research output (sources + summary + suggested approach + risks). '
  'Read by ResearchAgent at task start and surfaced in §48 explain row.';
