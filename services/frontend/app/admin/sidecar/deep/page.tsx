'use client';

/**
 * Sidecar Advisor — C4 + scenario data-flow deep-dive.
 *
 * Per the user's "add c4 model for each UI for each scenario" +
 * "data flow form one class to other call or other component"
 * directives: this page documents the architecture of the Sidecar
 * Advisor at C4 levels 1-2 plus per-scenario sequence diagrams
 * showing CLASS-TO-CLASS / COMPONENT-TO-COMPONENT data flow.
 *
 * Four scenarios covered:
 *   1. Auto-feed: commit -> hook -> council -> dashboard
 *   2. Backlog drain: --no-council events -> batched replay
 *   3. Verdict + revert: drill fail -> REJECT -> revert
 *   4. Retention: weekly prune cycle
 *
 * Each scenario shows the components involved + the message order
 * + the persistence touchpoints. Operator reads this to answer:
 *   "Which class do I touch to change behaviour X?"
 *   "Which component owns retention semantics?"
 *   "What's the failure isolation boundary at each layer?"
 */
import Mermaid from '../../../../components/Mermaid';

const C4_CONTEXT = `flowchart TB
  subgraph actors["Actors"]
    OP["Operator"]
    AUTOLOOP["Autonomous Loop"]
  end
  subgraph sidecar["Sidecar Advisor (THIS UI)"]
    NEXTUI["Next.js Server Component<br/>app/admin/sidecar/page.tsx"]
  end
  subgraph backend["Backend (pre-approved scope)"]
    PYAPI["Python lib: AdvisorMemory + Advisor + Council"]
    DB[("advisor.db<br/>(SQLite)")]
    LOGS[(".loop/*.log<br/>(JSONL)")]
  end
  subgraph extdeps["External"]
    OLLAMA["Ollama localhost:11434<br/>(council LLMs)"]
  end
  OP --> NEXTUI
  AUTOLOOP --> PYAPI
  NEXTUI --> LOGS
  NEXTUI --> DB
  PYAPI --> DB
  PYAPI --> LOGS
  PYAPI --> OLLAMA
  classDef ui fill:#e0f2ff,stroke:#0066cc
  classDef be fill:#fef3c7,stroke:#b45309
  class NEXTUI ui
  class PYAPI,DB,LOGS be`;

const C4_CONTAINER = `flowchart LR
  subgraph next["services/frontend"]
    P["page.tsx<br/>(Server Component)"]
    DEEP["deep/page.tsx<br/>(this page)"]
    M["Mermaid<br/>(client renderer)"]
  end
  subgraph scripts["scripts/"]
    HOOK["loop_watcher_hook.py"]
    CAPT["capture_and_review.py"]
    REND["render_dashboard.py"]
    REPLAY["replay_verdict_log.py"]
    PRUNE["prune_council_runs.py"]
    REPLAY2["replay_council_against_events.py"]
    DSTATUS["write_drill_status.py"]
  end
  subgraph lib["services/sidecar-advisor/"]
    MEM["AdvisorMemory<br/>(memory.py)"]
    ADV["Advisor<br/>(advisor.py)"]
    COUNCIL["PrReviewCouncil<br/>(council.py)"]
    GIT["capture_diff<br/>(git_capture.py)"]
    LW["LoopWatcher<br/>(loop_watcher.py)"]
    BULK["BulkPrReview<br/>(bulk_pr_review.py)"]
  end
  subgraph store["Persistence"]
    DB[("advisor.db")]
    WLOG[(".loop/watcher.log")]
    CLOG[(".loop/council_runs.log")]
    DSFILE[(".loop/last_drill_outcome.json")]
    DASHHTML[(".loop/dashboard.html")]
  end
  P --> DASHHTML
  DEEP --> M
  HOOK --> LW
  HOOK --> WLOG
  CAPT --> GIT
  CAPT --> ADV
  CAPT --> MEM
  CAPT --> CLOG
  ADV --> COUNCIL
  COUNCIL --> MEM
  REND --> MEM
  REND --> WLOG
  REND --> CLOG
  REND --> DASHHTML
  REPLAY --> WLOG
  PRUNE --> MEM
  REPLAY2 --> MEM
  REPLAY2 --> ADV
  DSTATUS --> DSFILE
  MEM --> DB
  classDef ui fill:#e0f2ff,stroke:#0066cc
  classDef sc fill:#dcfce7,stroke:#15803d
  classDef lb fill:#fef3c7,stroke:#b45309
  classDef st fill:#f3e8ff,stroke:#7c3aed
  class P,DEEP,M ui
  class HOOK,CAPT,REND,REPLAY,PRUNE,REPLAY2,DSTATUS sc
  class MEM,ADV,COUNCIL,GIT,LW,BULK lb
  class DB,WLOG,CLOG,DSFILE,DASHHTML st`;

const SCENARIO_1 = `sequenceDiagram
  autonumber
  actor OP as Operator
  participant GIT as git
  participant HOOK as scripts/git-hooks/post-commit
  participant LW as loop_watcher_hook.py
  participant CAP as capture_and_review.py
  participant GC as git_capture.capture_diff
  participant AD as Advisor.review
  participant CO as PrReviewCouncil.review
  participant MEM as AdvisorMemory
  participant DB as advisor.db
  participant CL as .loop/council_runs.log
  OP->>GIT: git commit -m "..."
  GIT->>HOOK: post-commit fires
  HOOK->>LW: subprocess (verdict)
  LW->>MEM: read recent events
  HOOK->>CAP: subprocess (review)
  CAP->>GC: capture HEAD diff
  GC-->>CAP: DiffCapture(content, files)
  CAP->>MEM: record_event(advisor_output=None)
  MEM->>DB: INSERT advisor_events
  CAP->>AD: review(event_type=pr_review, content)
  AD->>CO: council.review(content)
  CO->>CO: 3 authors + 1 reviewer + chair (parallel via AgentBoard)
  CO-->>AD: (parsed, raw_board)
  AD-->>CAP: (parsed, raw_board, model, dur, telemetry)
  CAP->>MEM: record_council_run(event_id, telemetry)
  MEM->>DB: INSERT advisor_council_runs
  CAP->>MEM: update_event_advisor_output(event_id, parsed)
  MEM->>DB: UPDATE advisor_events SET advisor_output=...
  CAP->>CL: append JSON line`;

const SCENARIO_2 = `sequenceDiagram
  autonumber
  actor CRON as Cron 05:00 UTC
  participant SH as scripts/replay_council_against_events.py
  participant MEM as AdvisorMemory
  participant DB as advisor.db
  participant DP as DispatchPool
  participant ADV as Advisor
  participant COUNCIL as PrReviewCouncil
  participant LOG as .loop/replay_council.log
  CRON->>SH: --apply --limit 200
  SH->>MEM: find_events_without_council_run(limit=200)
  MEM->>DB: SELECT events LEFT JOIN council_runs WHERE c.id IS NULL
  DB-->>MEM: pending events
  MEM-->>SH: list[event]
  SH->>DP: DispatchPool(max_parallel=4)
  loop for each event (bounded by max_parallel)
    DP->>ADV: review(event_type=pr_review, content)
    ADV->>COUNCIL: review(content)
    COUNCIL-->>ADV: (parsed, raw_board)
    ADV-->>DP: (parsed, ..., telemetry)
    DP->>MEM: record_council_run(event_id, telemetry)
    MEM->>DB: INSERT advisor_council_runs
  end
  DP-->>SH: results + stats
  SH->>LOG: append summary JSON line`;

const SCENARIO_3 = `sequenceDiagram
  autonumber
  actor LOOP as Autonomous Loop
  participant DS as write_drill_status.py
  participant SF as .loop/last_drill_outcome.json
  participant GIT as git commit
  participant LW as LoopWatcher
  participant WL as .loop/watcher.log
  participant OP as Operator
  participant RP as replay_verdict_log.py
  participant RPLOG as .loop/replayed.log
  LOOP->>DS: run drill suite -> JSON status
  DS->>SF: write {failed_drills:[drill_xyz], total:30}
  LOOP->>GIT: commit feature
  GIT->>LW: post-commit hook fires
  LW->>SF: read drill status
  SF-->>LW: failed_drills=[drill_xyz]
  LW->>LW: rule 1: drill_failed -> REJECT
  LW->>WL: append verdict REJECT
  Note over OP: morning review
  OP->>RP: replay_verdict_log.py (dry-run)
  RP->>WL: parse_watcher_log
  WL-->>RP: list[VerdictEntry]
  RP->>RPLOG: load_replayed_set
  RP-->>OP: list pending REJECTs + revert commands
  OP->>RP: --apply
  RP->>GIT: git revert --no-edit <sha>
  RP->>RPLOG: append <sha>`;

const SCENARIO_4 = `sequenceDiagram
  autonumber
  actor CRON as Cron Sunday 04:00
  participant PR as prune_council_runs.py
  participant MEM as AdvisorMemory
  participant DB as advisor.db
  CRON->>PR: --apply --vacuum
  PR->>MEM: prune_council_runs(older_than_days=90, dry_run=False)
  MEM->>DB: SELECT COUNT(*) WHERE created_at < threshold
  DB-->>MEM: to_delete = N
  MEM->>DB: DELETE WHERE created_at < threshold
  Note over MEM,DB: advisor_events rows NOT touched<br/>(separate retention horizons)
  MEM-->>PR: {deleted, kept, threshold_iso}
  PR->>DB: VACUUM (reclaim disk)
  PR-->>CRON: stdout JSON report`;

const SCENARIO_5 = `sequenceDiagram
  autonumber
  actor OP as Operator
  actor CRON as Cron Daily 00:05
  participant LOG as council_runs.log
  participant SNAP as council_stats_snapshot.py
  participant JSONL as council_stats_daily.jsonl
  participant STATS as council_filter_stats.py
  participant PROM as node_exporter textfile
  participant UI as /admin/sidecar/telemetry
  CRON->>SNAP: 5 0 * * *
  SNAP->>LOG: read yesterday's entries by UTC date prefix
  SNAP->>JSONL: append one row {date, total, fired, filtered, ...}
  CRON->>STATS: --prometheus --from-snapshot --prometheus-out file.prom
  STATS->>JSONL: read deduped (latest snapshot_taken_at per date)
  STATS->>PROM: atomic write date-keyed samples (tmp + rename)
  OP->>UI: GET /admin/sidecar/telemetry
  UI->>JSONL: fs.readFile at request time
  UI-->>OP: daily table (deduped, newest first)
  Note over JSONL,UI: 5N writes → 5W exports → 5S renders<br/>same source of truth, three consumption paths`;

const SCENARIO_6 = `sequenceDiagram
  autonumber
  actor DEV1 as Iteration 5S
  participant HOOK as pre-commit hook
  participant DRILLS as readonly drill suite
  participant STATUS as last_drill_outcome.json
  participant POST as post-commit hook
  participant WATCHER as LoopWatcher rule 1
  participant LOG as watcher.log
  actor DEV2 as Iteration 5Z
  actor DEV3 as Iteration 5Y
  DEV1->>HOOK: git commit (sidecar/ changes)
  HOOK->>DRILLS: 5F refresh
  DRILLS->>STATUS: failed=[deep_page, nextjs_page]
  Note over HOOK,STATUS: Phase 5F was silent on failures — operator missed it
  HOOK-->>DEV1: exit 0 (advisory contract preserved)
  POST->>WATCHER: read STATUS
  WATCHER->>LOG: verdict=REJECT, rule_fired=1
  DEV2->>LOG: tail → discover REJECT
  DEV2->>DRILLS: update assertions (4→5 scenarios; whitelist + telemetry/)
  DEV2->>STATUS: 53/53 green
  DEV3->>HOOK: extend with HBR detection (sidecar/, mcp/server*.py, sidecar-advisor/)
  Note over HOOK,DRILLS: Phase 5Y: future HBR commits<br/>get loud === banner naming failing drills<br/>BEFORE the commit lands
  DEV3->>STATUS: 54/54 green`;

const CSS = `
.section { background: white; border-radius: 8px;
  padding: 20px; margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,.1); }
.section h2 { margin-top: 0; color: #1b1b32; }
.scenario { margin-top: 16px; }
.scenario h3 { color: #16162a; margin-bottom: 4px; }
.scenario p { font-size: 14px; color: #555; margin: 4px 0 12px; }
body { font-family: ui-monospace, Menlo, Consolas, monospace;
  background: #f6f7f9; margin: 0; padding: 24px;
  color: #16162a; }
h1 { color: #1b1b32; }
.compose-footer { margin-top: 24px; padding: 16px;
  background: #f0f4f8; border-radius: 8px; font-size: 13px; }
.compose-footer h3 { margin-top: 0; color: #16162a; }
.compose-footer ul { margin: 8px 0; padding-left: 20px; }
.compose-footer li { margin: 4px 0; }
`;

export default function SidecarDeepPage() {
  return (
    <>
      <style>{CSS}</style>
      <h1>Sidecar Advisor — C4 + Scenario Data Flow</h1>
      <p style={{ color: '#666' }}>
        Architecture across C4 levels 1-2 plus per-scenario class-to-class
        data-flow sequences. Read top-to-bottom on first visit; bookmark
        a scenario for ongoing reference.
      </p>

      <div className="section">
        <h2>1. System Context (C4 L1)</h2>
        <p>
          Operators use the Next.js UI ({"app/admin/sidecar/page.tsx"});
          the autonomous loop calls the Python library directly. Both
          paths converge on advisor.db + .loop/*.log as the single
          source of truth. External: Ollama (council LLMs).
        </p>
        <Mermaid chart={C4_CONTEXT} />
      </div>

      <div className="section">
        <h2>2. Container View (C4 L2)</h2>
        <p>
          Three tiers — Next.js components (UI), scripts (operator
          entry points), library (sidecar-advisor/). Persistence is
          the boundary between in-memory state and durable audit.
        </p>
        <Mermaid chart={C4_CONTAINER} />
      </div>

      <div className="section">
        <h2>3. Scenarios (Class-to-Class Data Flow)</h2>

        <div className="scenario">
          <h3>3.1 — Auto-feed: commit → council → dashboard</h3>
          <p>
            Phase-2A2 chain. Operator commits; the post-commit hook
            fires LoopWatcher (verdict) AND capture_and_review (council).
            Council telemetry persists; event row backfills with
            advisor_output (Phase 5A bug fix).
          </p>
          <Mermaid chart={SCENARIO_1} />
        </div>

        <div className="scenario">
          <h3>3.2 — Backlog drain: --no-council events → batched replay</h3>
          <p>
            Phase-2A3 chain. Cron runs the replay script;
            find_events_without_council_run yields the worklist;
            DispatchPool fires the council with bounded LLM concurrency.
          </p>
          <Mermaid chart={SCENARIO_2} />
        </div>

        <div className="scenario">
          <h3>3.3 — Verdict + revert: drill fails → REJECT → revert</h3>
          <p>
            Phase-4B + 4C + 4D chain. Rule 1 of LoopWatcher catches
            failed drills; verdict log feeds replay_verdict_log; operator
            decides --apply (default dry-run) for actual reverts.
          </p>
          <Mermaid chart={SCENARIO_3} />
        </div>

        <div className="scenario">
          <h3>3.4 — Retention: weekly prune cycle</h3>
          <p>
            Phase-2F chain. advisor_council_runs grow unbounded (10-50KB
            JSON each); weekly prune deletes older-than-90-days rows.
            advisor_events stays — separate retention horizons.
          </p>
          <Mermaid chart={SCENARIO_4} />
        </div>

        <div className="scenario">
          <h3>3.5 — Telemetry: daily snapshot → prom export → live page</h3>
          <p>
            Phase 5K-5W chain. council_filter_stats names filters,
            council_stats_snapshot writes one row per UTC date,
            --from-snapshot exports to Prometheus, /admin/sidecar/telemetry
            renders the deduped daily table. Three consumption paths
            (Grafana / live page / CLI alerts) on one source of truth.
          </p>
          <Mermaid chart={SCENARIO_5} />
        </div>

        <div className="scenario">
          <h3>3.6 — Self-healing arc: 5S regression → 5Z fix → 5Y prevention</h3>
          <p>
            Phase 5S landed with two pre-existing drills silently failing.
            LoopWatcher caught it as REJECT in watcher.log; the advisory
            contract (ADR-014) let the commit land but flagged it. Phase
            5Z reconciled the drift; Phase 5Y encoded the prevention so
            the next time a high-blast-radius surface is staged, the
            pre-commit hook prints a loud banner naming the failing
            drills BEFORE the commit lands.
          </p>
          <Mermaid chart={SCENARIO_6} />
        </div>
      </div>

      <div className="compose-footer">
        <h3>Composes with</h3>
        <ul>
          <li>
            <a href="/admin/sidecar">/admin/sidecar</a> — the live
            dashboard rendered by render_dashboard.py
          </li>
          <li>
            <a href="/admin/sidecar/telemetry">/admin/sidecar/telemetry</a>{" "}
            — daily-snapshot table reading council_stats_daily.jsonl
          </li>
          <li>
            <a href="/admin/c4-model/deep">/admin/c4-model/deep</a> —
            the canonical 7-level C4 reference
          </li>
          <li>
            <a href="/admin/checklist/deep">/admin/checklist/deep</a> —
            the production-readiness gates these scenarios pass
          </li>
        </ul>
        <p style={{ fontSize: '12px', color: '#666', marginTop: '12px' }}>
          Why each scenario shows class-to-class data flow rather than
          generic boxes-and-arrows: the operator&apos;s question is
          &quot;which class do I touch to change behaviour X?&quot; —
          a sequence diagram with concrete class names answers it
          directly.
        </p>
      </div>
    </>
  );
}
