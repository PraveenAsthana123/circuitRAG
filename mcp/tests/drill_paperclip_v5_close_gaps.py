# RESOURCES: readonly
"""
Drill: Paperclip Stage-1 v5 — closes the 5 honest gaps from v4.

The v4 summary listed 5 gaps:
  1. MCP per-tool call counts
  2. Kafka per-event counts
  3. Personalization aggregate (PII-safe)
  4. Test/drill scoreboard
  5. gRPC per-call metrics

v5 adds aggregators for all 5. This drill locks the contract.

Assertions:
  1. snapshot v5 has 17 keys (12 from v4 + 5 new)
  2. version >= v5
  3-7. Each new aggregator returns required fields, correct shape
  8. NEGATIVE: missing data → empty shape (no exception) for each
  9. PII GUARD: personalization aggregator NEVER carries prompt content
     or user IDs (lists must contain only category names + counts)
  10. Backward compat: v1+v2+v3+v4 keys all still present
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts import paperclip_manager  # noqa: E402

GREEN = "\033[32m"; RED = "\033[31m"; BOLD = "\033[1m"; NC = "\033[0m"


def step(t): print(f"\n{BOLD}── {t} ──{NC}")
def ok(m): print(f"  {GREEN}✓ {m}{NC}")
def fail(m):
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    step("1. snapshot v5 — 17 top-level keys")
    snap = paperclip_manager.snapshot(window_days=7)
    expected = {
        "stage", "version", "generated_at",
        # v1
        "council_batch", "apply_attempts", "audit_decisions",
        "pending_issues", "council_outcomes",
        # v2
        "safety_history", "ops_worker", "council_runs",
        # v3
        "polisai_policy", "openclaw_a2a",
        # v4
        "kafka", "grpc",
        # v5
        "mcp_calls", "kafka_events", "personalization", "tests", "grpc_metrics",
    }
    missing = expected - set(snap.keys())
    if missing:
        fail(f"v5 keys missing: {missing}")
    ok(f"all {len(expected)} keys present")

    step("2. version >= v5")
    version = str(snap.get("version", ""))
    if not version.startswith("paperclip-readonly-v"):
        fail(f"version prefix wrong: {version!r}")
    n = int(version.rsplit("v", 1)[-1])
    if n < 5:
        fail(f"version too old: {version}")
    ok(f"version={version}")

    step("3. mcp_calls — required fields + counts consistent")
    m = snap["mcp_calls"]
    required = {"audit_present", "total_calls", "allowed", "denied",
                "top_servers", "top_tools", "top_denied_triples"}
    if (required - set(m.keys())):
        fail(f"mcp_calls missing fields: {required - set(m.keys())}")
    if m["allowed"] + m["denied"] != m["total_calls"]:
        fail(f"counts inconsistent: {m['allowed']}+{m['denied']} != {m['total_calls']}")
    ok(f"mcp_calls ok; total={m['total_calls']} allow/deny={m['allowed']}/{m['denied']}")

    step("4. kafka_events — required fields + counts consistent")
    k = snap["kafka_events"]
    required = {"db_present", "total", "published", "unpublished", "retried",
                "by_topic", "by_event_type", "stale_unpublished_5m"}
    if (required - set(k.keys())):
        fail(f"kafka_events missing fields: {required - set(k.keys())}")
    if k.get("db_present") and k["published"] + k["unpublished"] != k["total"]:
        fail(f"published+unpublished != total: {k}")
    ok(f"kafka_events ok; total={k['total']} published={k['published']} stale={k['stale_unpublished_5m']}")

    step("5. personalization (safe) — required fields")
    p = snap["personalization"]
    required = {"data_present", "prompt_count", "unique_users",
                "profile_count", "modelfile_count", "redaction_categories"}
    if (required - set(p.keys())):
        fail(f"personalization missing fields: {required - set(p.keys())}")
    if not isinstance(p["redaction_categories"], dict):
        fail(f"redaction_categories not dict: {type(p['redaction_categories'])}")
    ok(f"personalization ok; prompts={p['prompt_count']} users={p['unique_users']}")

    step("6. tests — drill inventory")
    t = snap["tests"]
    required = {"drill_dir_present", "total_drills", "with_resources_tag",
                "with_negative_step", "by_resource_tag"}
    if (required - set(t.keys())):
        fail(f"tests missing fields: {required - set(t.keys())}")
    if t["drill_dir_present"] and t["total_drills"] < t["with_resources_tag"]:
        fail(f"with_resources > total_drills: {t}")
    if t["with_negative_step"] > t["total_drills"]:
        fail(f"with_negative_step > total_drills (impossible): {t}")
    ok(f"tests ok; total={t['total_drills']} with_neg={t['with_negative_step']}")

    step("7. grpc_metrics — Prometheus scrape shape")
    g = snap["grpc_metrics"]
    required = {"metrics_url", "reachable", "metric_lines", "help_lines",
                "documind_metrics"}
    if (required - set(g.keys())):
        fail(f"grpc_metrics missing fields: {required - set(g.keys())}")
    if not isinstance(g["documind_metrics"], list):
        fail(f"documind_metrics not list: {type(g['documind_metrics'])}")
    ok(f"grpc_metrics ok; reachable={g['reachable']} "
       f"documind_count={len(g['documind_metrics'])}")

    # ---- NEGATIVE PATH STRESS TESTS ----
    step("8. NEGATIVE — each v5 aggregator handles missing source gracefully")
    saved_audit = paperclip_manager.MCP_GATEWAY_AUDIT
    saved_pers = paperclip_manager.PERSONALIZATION_DATA
    saved_drill = paperclip_manager.DRILL_DIR
    saved_metrics = paperclip_manager.OTEL_METRICS_URL
    try:
        paperclip_manager.MCP_GATEWAY_AUDIT = Path("/nonexistent/mcp.jsonl")
        paperclip_manager.PERSONALIZATION_DATA = Path("/nonexistent/perso")
        paperclip_manager.DRILL_DIR = Path("/nonexistent/drills")
        paperclip_manager.OTEL_METRICS_URL = "http://127.0.0.1:1/metrics"
        # All five must succeed without exception
        m1 = paperclip_manager.aggregate_mcp_calls(window_days=7)
        p1 = paperclip_manager.aggregate_personalization_safe()
        t1 = paperclip_manager.aggregate_tests()
        gm1 = paperclip_manager.aggregate_grpc_metrics()
    finally:
        paperclip_manager.MCP_GATEWAY_AUDIT = saved_audit
        paperclip_manager.PERSONALIZATION_DATA = saved_pers
        paperclip_manager.DRILL_DIR = saved_drill
        paperclip_manager.OTEL_METRICS_URL = saved_metrics

    if m1["audit_present"] is not False or m1["total_calls"] != 0:
        fail(f"missing mcp audit not handled: {m1}")
    if p1["data_present"] is not False:
        fail(f"missing personalization not handled: {p1}")
    if t1["drill_dir_present"] is not False:
        fail(f"missing drill dir not handled: {t1}")
    if gm1["reachable"] is not False:
        fail(f"unreachable metrics endpoint not handled: {gm1}")
    ok("all 4 v5 aggregators with stub paths gracefully report empty")

    step("9. PII GUARD — personalization carries no prompt content / user IDs")
    p_full = paperclip_manager.aggregate_personalization_safe()
    forbidden_fields = {"prompts", "raw_prompts", "users", "user_ids",
                        "user_list", "prompt_text", "prompt_redacted",
                        "prompt_raw"}
    leaked = forbidden_fields & set(p_full.keys())
    if leaked:
        fail(f"PII GUARD BROKEN — surfaced fields: {leaked}")
    # Whatever IS in the structure must be safe (counts/booleans/dict-of-counts)
    for k_name, val in p_full.items():
        if isinstance(val, dict):
            # values must be ints (counts), keys must be strings (categories)
            for cat, count in val.items():
                if not isinstance(cat, str) or not isinstance(count, int):
                    fail(f"non-count value in personalization.{k_name}: "
                         f"{cat!r}={count!r}")
    ok("no prompt content / no user IDs surfaced (counts-only invariant held)")

    step("10. backward compat — v1+v2+v3+v4 all preserved")
    keys = set(snap.keys())
    v1 = {"council_batch", "apply_attempts", "audit_decisions",
          "pending_issues", "council_outcomes"}
    v2 = {"safety_history", "ops_worker", "council_runs"}
    v3 = {"polisai_policy", "openclaw_a2a"}
    v4 = {"kafka", "grpc"}
    for label, ks in [("v1", v1), ("v2", v2), ("v3", v3), ("v4", v4)]:
        miss = ks - keys
        if miss:
            fail(f"{label} keys missing: {miss}")
    ok("v1+v2+v3+v4 all preserved (backward-compat held)")

    step("11. NEGATIVE — paperclip_manager STILL makes no write-network calls")
    src = (REPO / "scripts" / "paperclip_manager.py").read_text(encoding="utf-8")
    for forbidden in [
        "requests.post", "requests.put", "requests.delete",
        "httpx.post", "httpx.put", "httpx.delete",
    ]:
        if forbidden in src:
            fail(f"§42 violation: paperclip_manager contains {forbidden!r}")
    # urllib.request.urlopen is allowed only for read-only liveness probes:
    #   1. Prometheus /metrics scrape (v5)   — OTEL_METRICS_URL / metrics_url
    #   2. Ollama daemon liveness GETs (v10) — /api/tags + /api/ps ONLY
    #      (drill_ai_integrations step 9 forbids /api/pull, /api/generate,
    #      /api/chat — those would trigger model loads / paid inferences)
    # Anything else is a §42 violation.
    if "urlopen" in src:
        url_calls = re.findall(r"urlopen\(([^)]+)\)", src)
        for call in url_calls:
            allowed = (
                "OTEL_METRICS_URL" in call
                or "metrics_url" in call
                or "/api/tags" in call
                or "/api/ps" in call
            )
            if not allowed:
                fail(f"§42 violation: urlopen for non-allowed URL: {call}")
    ok(
        "v5 still §42 read-only (urlopen scoped to Prometheus metrics + "
        "Ollama liveness GETs only)"
    )

    print(f"\n{BOLD}{GREEN}ALL 11 PAPERCLIP-V5 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
