from __future__ import annotations

from documind_core.config import BaseServiceSettings


class AgentOrchestratorSettings(BaseServiceSettings):
    service_name: str = "agent-orchestrator-svc"
    ollama_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 60.0
    agent_coder_model: str = "deepseek-coder:6.7b-instruct"
    agent_reviewer_model: str = "starcoder2:7b"
    agent_advisor_model: str = "kimi-k2:1t-cloud"
    agent_security_advisor_model: str = "codellama:7b-instruct"
    mcp_hr_url: str = ""
    mcp_itsm_url: str = ""
    mcp_drills_url: str = ""
    default_require_human_approval: bool = False
    default_approval_mode: str = "plan_once"
    default_auto_advance: bool = True
    default_require_for_high_risk: bool = True
    default_require_for_low_confidence: bool = True
    default_confidence_threshold: float = 0.8
    default_require_for_risk_flags: bool = True
    default_require_for_destructive_tools: bool = True
    default_require_for_tool_namespaces: str = "identity,finops,itsm"
    # E1: pipeline-v2 default. Override via DOCUMIND_PIPELINE_V2_ENABLED.
    # True = service builds the LlmClientPool + 5 new agents + adds 4
    # new graph nodes (strategist/researcher/tester/deployer_preflight).
    # False = legacy 4-agent flow (pre-D1 behaviour, 100% backward
    # compatible — operators can flip back instantly).
    pipeline_v2_enabled: bool = True
    # MCP upstream URLs for the v2 pipeline.
    mcp_research_url: str = "http://localhost:8094"
    mcp_tests_url: str = "http://localhost:8095"
    mcp_deploy_url: str = "http://localhost:8096"
    mcp_observe_url: str = "http://localhost:8097"
