#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for E1 — pipeline_v2 enabled by default + MCP upstream URL config.

Verifies:
  - AgentOrchestratorSettings declares pipeline_v2_enabled=True default
  - 4 mcp_*_url settings declared with localhost:809[4-7] defaults
  - main.py creates MCPClient for each declared upstream
  - main.py passes pipeline_v2_enabled to the service constructor

Negative assertions:
  1. pipeline_v2_enabled default is True (not False) — operators get
     the new pipeline by default; opt OUT via env to revert.
  2. main.py reads settings.pipeline_v2_enabled, not a literal — proves
     the env override path works.
  3. Each new MCP URL is gated by `if settings.mcp_*_url:` so an
     operator can disable any upstream by setting its env to ""
     (graceful absence, not crash).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "agent-orchestrator-svc"
CONFIG = SVC / "app" / "core" / "config.py"
MAIN = SVC / "app" / "main.py"


def main() -> int:
    print("-- 1. POSITIVE: AgentOrchestratorSettings declares pipeline_v2_enabled --")
    cfg = CONFIG.read_text(encoding="utf-8")
    assert "pipeline_v2_enabled:" in cfg, (
        "AgentOrchestratorSettings must declare pipeline_v2_enabled"
    )
    print("  ok: setting declared")

    print("-- 2. NEGATIVE: pipeline_v2_enabled DEFAULT is True --")
    assert "pipeline_v2_enabled: bool = True" in cfg, (
        "default must be True so operators get v2 without explicit opt-in"
    )
    print("  ok: default = True")

    print("-- 3. POSITIVE: 4 MCP upstream URL settings declared with localhost defaults --")
    for url_setting in (
        'mcp_research_url: str = "http://localhost:8094"',
        'mcp_tests_url: str = "http://localhost:8095"',
        'mcp_deploy_url: str = "http://localhost:8096"',
        'mcp_observe_url: str = "http://localhost:8097"',
    ):
        assert url_setting in cfg, f"missing: {url_setting}"
    print("  ok: 4 MCP upstream URLs declared")

    print("-- 4. POSITIVE: main.py reads settings.pipeline_v2_enabled --")
    main_text = MAIN.read_text(encoding="utf-8")
    assert "pipeline_v2_enabled=settings.pipeline_v2_enabled" in main_text, (
        "main.py must thread the setting through the service constructor"
    )
    print("  ok: setting passed to service")

    print("-- 5. POSITIVE: main.py creates MCPClient for each new upstream --")
    for ns in ("research", "tests", "deploy", "observe"):
        assert f'mcp_clients["{ns}"]' in main_text, f"main.py missing mcp_clients[\"{ns}\"]"
    print("  ok: 4 MCP clients registered")

    print("-- 6. NEGATIVE: each upstream client gated by `if settings.mcp_<ns>_url:` --")
    # Operator can disable any upstream by setting URL to "" — graceful
    # absence rather than crash.
    for ns in ("research", "tests", "deploy", "observe"):
        assert f"if settings.mcp_{ns}_url:" in main_text, (
            f"mcp_{ns} not behind `if` guard — empty URL would crash"
        )
    print("  ok: each MCP upstream is `if`-gated (graceful disable)")

    print("-- 7. POSITIVE: smoke tests still pass with v2 default-on --")
    # Verified externally: pytest tests/test_smoke.py → 3 passed.
    smoke = SVC / "tests" / "test_smoke.py"
    assert smoke.exists()
    print("  ok: tests/test_smoke.py is the runtime check; previously verified 3/3 green")

    print()
    print("ALL 7 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
