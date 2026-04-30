'use client';

/**
 * Universal interview-grade explanation card for any architecture
 * topic. Implements the project's MASTER 36-section interview
 * framework + HLD + LLD diagrams. Backwards-compatible: every new
 * section is rendered only when the matching field is present, so
 * pages that adopted the prior 20-dimension shape still render
 * cleanly without modification.
 *
 *  Section list (numbers match the master template):
 *   1.  Topic definition (title + coreConcept + oneLiner)
 *   2.  5W (what / why / where / when / who)
 *   3.  Interview explanation (30-60s spoken answer)
 *   4.  Core concepts / building blocks
 *   5.  Architecture relevance (backend / RAG / AI / microservices)
 *   6.  Flowchart (mermaid)
 *   7.  Sequence flow (mermaid)
 *   8.  Logical implementation steps (step + logic)
 *   9.  Code example
 *   10. Real use case
 *   11. Pros & cons
 *   12. Limitations
 *   13. When NOT to use
 *   14. Comparison
 *   15. Challenges
 *   16. Edge cases
 *   17. Solutions / fixes
 *   18. Best practices (do / avoid / optimize)
 *   19. Anti-patterns
 *   20. Testing strategy (test types)
 *   21. Test scenarios
 *   22. Test data
 *   23. Debugging checklist
 *   24. Production issues
 *   25. Security considerations
 *   26. Performance considerations
 *   27. Cost considerations
 *   28. Scalability considerations
 *   29. Observability
 *   30. Metrics to track
 *   31. Failure modes
 *   32. Trade-offs
 *   33. Decision matrix
 *   34. STAR story
 *   35. Interview traps
 *   36. Final interview script
 *   +   HLD diagram (high-level / system view, mermaid)
 *   +   LLD diagram (low-level / component view, mermaid)
 *
 *  Existing fields kept for backwards compatibility:
 *    problem, whyThisApproach, whenToUse, input, process, output,
 *    alternatives, monitoring, scaling, maturity, projectFit,
 *    interviewLine, failureModes (these map to specific master
 *    sections — see comments inline).
 */

import Mermaid from './Mermaid';
import SpeechReader from './SpeechReader';

export interface Topic {
  // ---- §1. Problem / Context (START HERE) ---------------------
  slug: string;
  title: string;
  status?: 'shipped' | 'partial' | 'open' | 'planned';
  level?: { label: string; tone: string };
  coreConcept: string;
  oneLiner?: string;
  businessContext?: string;  // "We need to design/implement..."

  // ---- §2. 5W -------------------------------------------------
  fiveW?: {
    what: string;
    why: string;
    where: string;
    when: string;
    who: string;
  };

  // ---- §3. Interview answer (30-60s) -------------------------
  interview30s?: string;

  // ---- §4. High-Level Architecture (HLD) ---------------------
  hld?: string;

  // ---- §5. Network Flow (system boundaries + communication) --
  networkFlow?: string;

  // ---- §6. Sequence Flow + execution flowchart ---------------
  flowchart?: string;
  sequence?: string;

  // ---- §7. Core Components / Layers (+ LLD diagram) ----------
  coreLayers?: { layer: string; responsibility: string }[];
  lld?: string;
  // Legacy: kept rendered as supplementary list inside §7.
  coreBuildingBlocks?: string[];

  // ---- Architecture relevance (kept, unnumbered legacy block) -
  architectureRelevance?: {
    backend: string;
    rag: string;
    ai: string;
    microservices: string;
  };

  // ---- Existing problem/why/IPO blocks -----------------------
  // (Renders inside section 1 / 8 alongside new fields.)
  problem: string;
  whyThisApproach: string;
  whenToUse: string[];
  whenNotToUse: string[];
  input: string;
  process: string[];
  output: string;

  // ---- 8. Logical implementation steps -----------------------
  implementationSteps?: { step: string; logic: string }[];

  // ---- 9. Code example ---------------------------------------
  codeExample?: { language: string; code: string };

  // ---- 10. Real use case -------------------------------------
  realUseCase?: string;

  // ---- 11. Pros & cons ---------------------------------------
  prosCons?: { pros: string[]; cons: string[] };

  // ---- 12. Limitations (existing) ----------------------------
  limitations: string[];

  // ---- 13. When NOT to use (existing whenNotToUse) -----------

  // ---- 14. Comparison ----------------------------------------
  comparison?: {
    left: string;
    right: string;
    rows: { aspect: string; left: string; right: string }[];
  };

  // ---- 15 & 16. Challenges + edge cases (existing) ----------
  challenges: string[];
  edgeCases: { case: string; solution: string }[];

  // ---- 17. Solutions / fixes ---------------------------------
  solutions?: { problem: string; solution: string }[];

  // ---- 18. Best practices ------------------------------------
  bestPractices?: { do: string[]; avoid: string[]; optimize: string[] };

  // ---- 19. Anti-patterns -------------------------------------
  antiPatterns?: string[];

  // ---- 20-22. Testing ---------------------------------------
  testing: string[]; // existing: testing strategy summary
  testTypes?: string[];
  testScenarios?: { scenario: string; expected: string }[];
  testData?: { type: string; example: string }[];

  // ---- 23. Debugging checklist -------------------------------
  debuggingChecklist?: string[];

  // ---- 24. Production issues ---------------------------------
  productionIssues?: { issue: string; rootCause: string }[];

  // ---- 25. Security (existing) -------------------------------
  security: string[];

  // ---- 26. Performance considerations ------------------------
  performance?: string[];

  // ---- 27. Cost considerations -------------------------------
  costConsiderations?: string[];

  // ---- 28. Scaling (existing) --------------------------------
  scaling: string[];

  // ---- 29. Observability -------------------------------------
  observability?: string[];

  // ---- 30. Metrics to track ----------------------------------
  metrics?: { name: string; example: string }[];

  // ---- 31. Failure modes (existing) -------------------------
  failureModes: { mode: string; detect: string; recover: string }[];

  // ---- 32. Trade-offs ----------------------------------------
  tradeoffs?: { decision: string; tradeoff: string }[];

  // ---- 33. Decision matrix -----------------------------------
  decisionMatrix?: { option: string; whenToUse: string }[];

  // ---- 34. STAR story ----------------------------------------
  starStory?: { situation: string; task: string; action: string; result: string };

  // ---- 35. Interview traps -----------------------------------
  interviewTraps?: string[];

  // ---- 36. Final interview script ----------------------------
  finalScript?: string;

  // ---- Maturity + monitoring + alternatives + projectFit -----
  alternatives: { name: string; tradeoff: string }[];
  monitoring: string[];
  maturity: { mvp: string; production: string; enterprise: string };
  projectFit: string[];
  interviewLine: string;
}

function statusBadgeClass(status?: Topic['status']): string {
  if (status === 'shipped') return 'badge badge-active';
  if (status === 'partial') return 'badge badge-parsing';
  if (status === 'open') return 'badge badge-failed';
  return '';
}

function H({ n, t }: { n: number | string; t: string }) {
  // Render the section marker as a single string so the SSR'd HTML
  // contains "§N." as one contiguous text node. React inserts an
  // empty comment between adjacent text expressions otherwise,
  // which breaks substring sniffs in drills.
  const marker = `§${n}.`;
  return (
    <h3
      style={{
        marginTop: 18,
        marginBottom: 8,
        fontSize: 16,
        color: '#000000',
        borderBottom: '1px solid #e5e7eb',
        paddingBottom: 4,
      }}
    >
      <span style={{ color: '#1e3a8a', marginRight: 6 }}>{marker}</span>
      {' '}
      {t}
    </h3>
  );
}

export default function UniversalDeepDive({ t }: { t: Topic }) {
  // Compose the spoken text from the topic's most informative fields.
  // The reader will get an audio briefing of the topic in ~30-60 seconds.
  const spokenText = [
    t.title,
    t.coreConcept,
    t.oneLiner,
    t.businessContext,
    t.interview30s,
    t.finalScript || t.interviewLine,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <article id={t.slug} className="card" style={{ marginBottom: 32 }}>
      {/* ====== §1. Problem / Context (START HERE) ====== */}
      <header style={{ marginBottom: 12 }}>
        <h2 className="section-title" style={{ marginBottom: 6 }}>
          {t.title}{' '}
          {t.status && <span className={statusBadgeClass(t.status)}>{t.status}</span>}
          {t.level && (
            <span
              className="badge"
              style={{ backgroundColor: t.level.tone, color: '#ffffff', marginLeft: 6 }}
            >
              {t.level.label}
            </span>
          )}
        </h2>
        {/* Read-aloud button with per-word highlight + voice/speed picker */}
        <div style={{ marginTop: 6, marginBottom: 10 }}>
          <SpeechReader text={spokenText} compact />
        </div>
        <H n={1} t="Problem / Context" />
        <p style={{ fontStyle: 'italic', color: '#000000' }}>{t.coreConcept}</p>
        {t.oneLiner && (
          <p style={{ color: '#000000', marginTop: 4 }}>
            <strong>One-liner:</strong> {t.oneLiner}
          </p>
        )}
        {t.businessContext && (
          <p style={{ color: '#000000', marginTop: 4 }}>
            <strong>Business context:</strong> {t.businessContext}
          </p>
        )}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
            marginTop: 12,
          }}
        >
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <strong>Problem it solves</strong>
            <p style={{ marginTop: 4 }}>{t.problem}</p>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <strong>Why this approach</strong>
            <p style={{ marginTop: 4 }}>{t.whyThisApproach}</p>
          </div>
        </div>
      </header>

      {/* ====== §2. 5W ====== */}
      {t.fiveW && (
        <div style={{ marginBottom: 12 }}>
          <H n={2} t="5W" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr>
                <th style={{ width: 80 }}>W</th>
                <th>Answer</th>
              </tr>
            </thead>
            <tbody>
              <tr><td><strong>What</strong></td><td>{t.fiveW.what}</td></tr>
              <tr><td><strong>Why</strong></td><td>{t.fiveW.why}</td></tr>
              <tr><td><strong>Where</strong></td><td>{t.fiveW.where}</td></tr>
              <tr><td><strong>When</strong></td><td>{t.fiveW.when}</td></tr>
              <tr><td><strong>Who</strong></td><td>{t.fiveW.who}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §3. Interview answer (30-60s) ====== */}
      {t.interview30s && (
        <div style={{ marginBottom: 12 }}>
          <H n={3} t="Interview answer (30-60 sec)" />
          <div className="card" style={{ padding: 12, backgroundColor: '#dbeafe' }}>
            <p style={{ margin: 0 }}>{t.interview30s}</p>
          </div>
        </div>
      )}

      {/* ====== §4. High-Level Architecture (HLD) ====== */}
      {t.hld && (
        <div style={{ marginBottom: 12 }}>
          <H n={4} t="High-Level Architecture (HLD)" />
          <Mermaid chart={t.hld} />
        </div>
      )}

      {/* ====== §5. Network Flow (system view: boundaries + comms) ====== */}
      {t.networkFlow && (
        <div style={{ marginBottom: 12 }}>
          <H n={5} t="Network Flow (system view)" />
          <Mermaid chart={t.networkFlow} />
        </div>
      )}

      {/* ====== §6. Sequence Flow (runtime view) — flowchart + sequence ====== */}
      {(t.flowchart || t.sequence) && (
        <div style={{ marginBottom: 12 }}>
          <H n={6} t="Sequence Flow (runtime view)" />
          {t.flowchart && (
            <div style={{ marginBottom: 12 }}>
              <strong>Execution flow</strong>
              <Mermaid chart={t.flowchart} />
            </div>
          )}
          {t.sequence && (
            <div>
              <strong>Sequence diagram</strong>
              <Mermaid chart={t.sequence} />
            </div>
          )}
        </div>
      )}

      {/* ====== §7. Core Components / Layers (+ LLD diagram) ====== */}
      {(t.coreLayers || t.lld || t.coreBuildingBlocks) && (
        <div style={{ marginBottom: 12 }}>
          <H n={7} t="Core Components / Layers" />
          {t.coreLayers && t.coreLayers.length > 0 && (
            <table className="table" style={{ marginTop: 6 }}>
              <thead>
                <tr>
                  <th style={{ width: 200 }}>Layer</th>
                  <th>Responsibility</th>
                </tr>
              </thead>
              <tbody>
                {t.coreLayers.map((l, i) => (
                  <tr key={i}>
                    <td><strong>{l.layer}</strong></td>
                    <td>{l.responsibility}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {t.coreBuildingBlocks && t.coreBuildingBlocks.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong>Building blocks</strong>
              <ul style={{ paddingLeft: 18 }}>
                {t.coreBuildingBlocks.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          {t.lld && (
            <div style={{ marginTop: 8 }}>
              <strong>Low-level design (LLD) diagram</strong>
              <Mermaid chart={t.lld} />
            </div>
          )}
        </div>
      )}

      {/* Architecture relevance (kept as backwards-compat unnumbered block) */}
      {t.architectureRelevance && (
        <div style={{ marginBottom: 12 }}>
          <strong>Architecture relevance</strong>
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th style={{ width: 160 }}>Layer</th><th>Usage</th></tr>
            </thead>
            <tbody>
              <tr><td><strong>Backend</strong></td><td>{t.architectureRelevance.backend}</td></tr>
              <tr><td><strong>RAG</strong></td><td>{t.architectureRelevance.rag}</td></tr>
              <tr><td><strong>AI system</strong></td><td>{t.architectureRelevance.ai}</td></tr>
              <tr><td><strong>Microservices</strong></td><td>{t.architectureRelevance.microservices}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §8. Logical implementation steps ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n={8} t="Logical implementation steps" />
        {t.implementationSteps && t.implementationSteps.length > 0 ? (
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th style={{ width: 80 }}>Step</th><th>Logic</th></tr>
            </thead>
            <tbody>
              {t.implementationSteps.map((s, i) => (
                <tr key={i}><td><strong>{s.step}</strong></td><td>{s.logic}</td></tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 2fr 1fr',
              gap: 12,
              marginTop: 6,
            }}
          >
            <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
              <div className="field-help">Input</div>
              <div>{t.input}</div>
            </div>
            <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
              <div className="field-help">Process</div>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {t.process.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
            <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
              <div className="field-help">Output</div>
              <div>{t.output}</div>
            </div>
          </div>
        )}
      </div>

      {/* ====== §9. Code example ====== */}
      {t.codeExample && (
        <div style={{ marginBottom: 12 }}>
          <H n={9} t="Code example" />
          <pre
            style={{
              background: '#f9fafb',
              border: '1px solid #e5e7eb',
              padding: 12,
              borderRadius: 6,
              overflowX: 'auto',
              fontSize: 13,
              color: '#000000',
            }}
          >
            <code>{t.codeExample.code}</code>
          </pre>
        </div>
      )}

      {/* ====== §10. Real use case ====== */}
      {t.realUseCase && (
        <div style={{ marginBottom: 12 }}>
          <H n={10} t="Real use case" />
          <div className="card" style={{ padding: 12, backgroundColor: '#f9fafb' }}>
            <p style={{ margin: 0 }}>{t.realUseCase}</p>
          </div>
        </div>
      )}

      {/* ====== §11. Pros & cons ====== */}
      {t.prosCons && (
        <div style={{ marginBottom: 12 }}>
          <H n={11} t="Pros & cons" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
              <strong>Pros</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.prosCons.pros.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
            <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
              <strong>Cons</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.prosCons.cons.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ====== §12. Limitations ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n={12} t="Limitations" />
        <ul style={{ paddingLeft: 18 }}>
          {t.limitations.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>

      {/* ====== §13. When NOT to use + when-to-use ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n={13} t="When to use vs when NOT to use" />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
            <strong>When to use</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {t.whenToUse.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
            <strong>When NOT to use</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {t.whenNotToUse.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        </div>
      </div>

      {/* ====== §14. Comparison ====== */}
      {t.comparison && (
        <div style={{ marginBottom: 12 }}>
          <H n={14} t={`Comparison: ${t.comparison.left} vs ${t.comparison.right}`} />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr>
                <th>Aspect</th>
                <th>{t.comparison.left}</th>
                <th>{t.comparison.right}</th>
              </tr>
            </thead>
            <tbody>
              {t.comparison.rows.map((r, i) => (
                <tr key={i}>
                  <td><strong>{r.aspect}</strong></td>
                  <td>{r.left}</td>
                  <td>{r.right}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §15-16. Challenges + edge cases ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n="15-16" t="Challenges + edge cases" />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
            <strong>Challenges</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {t.challenges.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
          <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
            <strong>Edge cases + solutions</strong>
            <table className="table" style={{ marginTop: 6, fontSize: 13 }}>
              <tbody>
                {t.edgeCases.map((ec, i) => (
                  <tr key={i}>
                    <td style={{ width: '50%' }}>{ec.case}</td>
                    <td>→ {ec.solution}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ====== §17. Solutions / fixes ====== */}
      {t.solutions && t.solutions.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={17} t="Solutions / fixes" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th style={{ width: '40%' }}>Problem</th><th>Solution</th></tr>
            </thead>
            <tbody>
              {t.solutions.map((s, i) => (
                <tr key={i}><td>{s.problem}</td><td>{s.solution}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §18. Best practices ====== */}
      {t.bestPractices && (
        <div style={{ marginBottom: 12 }}>
          <H n={18} t="Best practices (production level)" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <div className="card" style={{ padding: 12, backgroundColor: '#dcfce7' }}>
              <strong>Do</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.bestPractices.do.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
            <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
              <strong>Avoid</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.bestPractices.avoid.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
            <div className="card" style={{ padding: 12, backgroundColor: '#dbeafe' }}>
              <strong>Optimize</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.bestPractices.optimize.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ====== §19. Anti-patterns ====== */}
      {t.antiPatterns && t.antiPatterns.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={19} t="Anti-patterns" />
          <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {t.antiPatterns.map((a, i) => <li key={i}>❌ {a}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* ====== §20. Testing strategy ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n={20} t="Testing strategy" />
        {t.testTypes && t.testTypes.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <strong>Test types</strong>
            <ul style={{ paddingLeft: 18 }}>
              {t.testTypes.map((tt, i) => <li key={i}>{tt}</li>)}
            </ul>
          </div>
        )}
        <strong>Strategy</strong>
        <ul style={{ paddingLeft: 18 }}>
          {t.testing.map((te, i) => <li key={i}>{te}</li>)}
        </ul>
      </div>

      {/* ====== §21. Test scenarios ====== */}
      {t.testScenarios && t.testScenarios.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={21} t="Test scenarios" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th>Scenario</th><th>Expected output</th></tr>
            </thead>
            <tbody>
              {t.testScenarios.map((s, i) => (
                <tr key={i}><td>{s.scenario}</td><td>{s.expected}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §22. Test data ====== */}
      {t.testData && t.testData.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={22} t="Test data" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th style={{ width: 140 }}>Input type</th><th>Example</th></tr>
            </thead>
            <tbody>
              {t.testData.map((d, i) => (
                <tr key={i}><td><strong>{d.type}</strong></td><td>{d.example}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §23. Debugging checklist ====== */}
      {t.debuggingChecklist && t.debuggingChecklist.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={23} t="Debugging checklist" />
          <ol style={{ paddingLeft: 18 }}>
            {t.debuggingChecklist.map((d, i) => <li key={i}>{d}</li>)}
          </ol>
        </div>
      )}

      {/* ====== §24. Production issues ====== */}
      {t.productionIssues && t.productionIssues.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={24} t="Production issues (real)" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th style={{ width: '40%' }}>Issue</th><th>Root cause</th></tr>
            </thead>
            <tbody>
              {t.productionIssues.map((p, i) => (
                <tr key={i}><td>{p.issue}</td><td>{p.rootCause}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §25-28. Security / performance / cost / scaling ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n="25-28" t="Security · performance · cost · scaling" />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="card" style={{ padding: 12, backgroundColor: '#ede9fe' }}>
            <strong>§25 Security</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {t.security.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
          {t.performance && t.performance.length > 0 && (
            <div className="card" style={{ padding: 12, backgroundColor: '#fef3c7' }}>
              <strong>§26 Performance</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.performance.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}
          {t.costConsiderations && t.costConsiderations.length > 0 && (
            <div className="card" style={{ padding: 12, backgroundColor: '#fce7f3' }}>
              <strong>§27 Cost</strong>
              <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
                {t.costConsiderations.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          <div className="card" style={{ padding: 12, backgroundColor: '#ecfdf5' }}>
            <strong>§28 Scaling</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {t.scaling.map((sc, i) => <li key={i}>{sc}</li>)}
            </ul>
          </div>
        </div>
      </div>

      {/* ====== §29. Observability ====== */}
      {((t.observability && t.observability.length > 0) || t.monitoring.length > 0) && (
        <div style={{ marginBottom: 12 }}>
          <H n={29} t="Observability" />
          <div className="card" style={{ padding: 12, backgroundColor: '#dbeafe' }}>
            <strong>Logs · traces · metrics</strong>
            <ul style={{ margin: '6px 0 0 0', paddingLeft: 18 }}>
              {(t.observability || t.monitoring).map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* ====== §30. Metrics to track ====== */}
      {t.metrics && t.metrics.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={30} t="Metrics to track" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th>Metric</th><th>Example</th></tr>
            </thead>
            <tbody>
              {t.metrics.map((m, i) => (
                <tr key={i}><td><strong>{m.name}</strong></td><td>{m.example}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §31. Failure modes ====== */}
      <div style={{ marginBottom: 12 }}>
        <H n={31} t="Failure modes" />
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr><th>Mode</th><th>Detect</th><th>Recover</th></tr>
          </thead>
          <tbody>
            {t.failureModes.map((fm, i) => (
              <tr key={i}>
                <td>{fm.mode}</td><td>{fm.detect}</td><td>{fm.recover}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ====== §32. Trade-offs ====== */}
      {t.tradeoffs && t.tradeoffs.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={32} t="Trade-offs (interview gold)" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th>Decision</th><th>Trade-off</th></tr>
            </thead>
            <tbody>
              {t.tradeoffs.map((tr, i) => (
                <tr key={i}><td>{tr.decision}</td><td>{tr.tradeoff}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §33. Decision matrix ====== */}
      {t.decisionMatrix && t.decisionMatrix.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={33} t="Decision matrix" />
          <table className="table" style={{ marginTop: 6 }}>
            <thead>
              <tr><th>Option</th><th>When to use</th></tr>
            </thead>
            <tbody>
              {t.decisionMatrix.map((d, i) => (
                <tr key={i}>
                  <td><strong>{d.option}</strong></td>
                  <td>{d.whenToUse}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ====== Alternatives (legacy block, kept for backwards compat) ====== */}
      <div style={{ marginBottom: 12 }}>
        <strong>Alternatives + tradeoffs (legacy)</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr><th style={{ width: 220 }}>Alternative</th><th>Tradeoff</th></tr>
          </thead>
          <tbody>
            {t.alternatives.map((a, i) => (
              <tr key={i}>
                <td><code>{a.name}</code></td>
                <td>{a.tradeoff}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ====== §34. STAR story ====== */}
      {t.starStory && (
        <div style={{ marginBottom: 12 }}>
          <H n={34} t="STAR story" />
          <table className="table" style={{ marginTop: 6 }}>
            <tbody>
              <tr><td style={{ width: 120 }}><strong>Situation</strong></td><td>{t.starStory.situation}</td></tr>
              <tr><td><strong>Task</strong></td><td>{t.starStory.task}</td></tr>
              <tr><td><strong>Action</strong></td><td>{t.starStory.action}</td></tr>
              <tr><td><strong>Result</strong></td><td>{t.starStory.result}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {/* ====== §35. Interview traps ====== */}
      {t.interviewTraps && t.interviewTraps.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <H n={35} t="Interview traps" />
          <div className="card" style={{ padding: 12, backgroundColor: '#fee2e2' }}>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {t.interviewTraps.map((tr, i) => <li key={i}>❌ {tr}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* ====== Maturity model + project fit (kept) ====== */}
      <div style={{ marginBottom: 12 }}>
        <strong>Maturity model</strong>
        <table className="table" style={{ marginTop: 6 }}>
          <thead>
            <tr><th style={{ width: 130 }}>Stage</th><th>Looks like</th></tr>
          </thead>
          <tbody>
            <tr><td><strong>MVP</strong></td><td>{t.maturity.mvp}</td></tr>
            <tr><td><strong>Production</strong></td><td>{t.maturity.production}</td></tr>
            <tr><td><strong>Enterprise</strong></td><td>{t.maturity.enterprise}</td></tr>
          </tbody>
        </table>
      </div>

      <div style={{ marginBottom: 12 }}>
        <strong>Where it fits in this project</strong>
        <ul style={{ marginTop: 6, paddingLeft: 18 }}>
          {t.projectFit.map((p, i) => (
            <li key={i}><code style={{ fontSize: 13 }}>{p}</code></li>
          ))}
        </ul>
      </div>

      {/* ====== §36. Final interview script ====== */}
      <div
        className="card"
        style={{ padding: 12, backgroundColor: '#dbeafe', borderColor: '#1e3a8a' }}
      >
        <H n={36} t="Final interview script (ready to speak)" />
        <p style={{ margin: '6px 0 0 0', fontStyle: 'italic' }}>
          &ldquo;{t.finalScript || t.interviewLine}&rdquo;
        </p>
      </div>
    </article>
  );
}
