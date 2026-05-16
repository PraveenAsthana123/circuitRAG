# 📦 `scripts` — Advanced README

🔧 **Scripts**  ·  **Path:** `scripts`  ·  **Generated:** 2026-05-16 23:26 UTC

> _Purpose not detected from docstrings — reviewer to fill._

This README is **auto-generated** by [`scripts/generate_folder_report.py`](../../scripts/generate_folder_report.py). It explains what this folder does, every file inside it, how the files link to each other, every API endpoint, every database call, every test case, and the production controls (security / reliability / performance / observability). Re-run after major changes.

---

## 🔎 Section 0 — Auto-Detected Facts

| Metric | Value |
|---|---|
| Folder | `scripts` |
| Total files | 165 |
| Python files | 120 |
| TypeScript/JS files | 0 |
| Go files | 0 |
| Shell scripts | 36 |
| Lines of code | 44,726 |
| Python classes | 127 |
| Python functions | 1092 |
| Async functions | 42 |
| Total API endpoints | 5 |
| Total DB call sites | 110 |
| DB / Storage libs | Elasticsearch, Kafka (aiokafka), MongoDB (pymongo), Neo4j, Qdrant, Redis, SQLAlchemy, asyncpg, psycopg |
| Concurrency primitives | Lock / RLock, asyncio (async/await), concurrent.futures, threading |
| Caching primitives | functools.cache, in-memory @lru_cache, redis |
| Input validation | Manual escape, Pydantic BaseModel, Pydantic validator, Zod (TS) |
| AI / LLM deps | Anthropic SDK, DeepEval, Giskard, LangChain, LangGraph, Ollama, OpenAI SDK, OpenTelemetry GenAI, Ragas, Rebuff (PI defense) |
| Test files | 3 |
| Detected test cases | 0 |
| Tests dir present | ❌ — flag |
| Dockerfile | ❌ |
| pyproject.toml | ❌ |
| go.mod | ❌ |
| package.json | ❌ |
| Top git contributors | `225	PraveenAsthana123`, `2	Praveen` |

#### Longest functions (top 5)

| Location | Name | Lines |
|---|---|---|
| `local_council.py:611` | `run_local_council` | 337 |
| `run_gepa_empirical.py:177` | `_stage3_compile` | 247 |
| `generate_folder_report.py:1713` | `section_code_logic_deep_dive` | 239 |
| `generate_brutal_reviews.py:47` | `build_review` | 238 |
| `generate_specialized_assessment.py:540` | `render_backend` | 231 |

#### Smells detected (grep heuristics — verify manually)

| Smell | Count |
|---|---|
| hardcoded localhost URL | 95 |
| hardcoded password literal | 1 |
| hardcoded API key literal | 1 |
| TODO/FIXME marker | 41 |


## 1. Purpose — Business + Technical

### Business problem this folder solves

> _Reviewer to fill: one paragraph describing the business need_

### Technical contract this folder exposes

> _Reviewer to fill: API surface, events emitted, data persisted, downstream consumers._

### Out-of-scope (what this folder does NOT do)

> _Reviewer to fill: explicit non-goals — prevents scope creep at review time._


## 🗺 How to Read This Folder (Guided Tour)

Read these files in order — by the end, you'll understand 80% of this folder's behavior. Click any path to jump straight to the source.

1. **`promote_best_config.py`** (⚙ config / settings, 278 LOC) — Every env var the service reads. Read this BEFORE running locally.
2. **`best_config_loader.py`** (⚙ config / settings, 241 LOC) — Every env var the service reads. Read this BEFORE running locally.
3. **`best_config_history.py`** (⚙ config / settings, 206 LOC) — Every env var the service reads. Read this BEFORE running locally.
4. **`agent_task_registry.py`** (🤖 agent / tool, 827 LOC) — Unified agent task registry — provider-comparison rollup.
5. **`gemma_agent_council.py`** (🤖 agent / tool, 446 LOC) — Gemma Agent Council — 5-agent orchestrator using local Gemma stack.
6. **`catalog_tools_probe.py`** (🤖 agent / tool, 445 LOC) — Probe every tool in config/agentic_observability/oss_tooling_catalog.yaml
7. **`agent_readiness_check.py`** (🤖 agent / tool, 405 LOC) — Agent readiness check — does the council actually FIX things? (iter-76).
8. **`agent_task_board.py`** (🤖 agent / tool, 404 LOC) — Agent Task Board — central status view + drill-gated apply pipeline.

Click absolute paths for direct `cat`-ability in the §2 File Inventory above.


## ⚙ Environment Variables

All env vars this folder reads, auto-extracted from `BaseSettings` field declarations and `os.environ.get` calls.

### Runtime `os.environ.get` / `os.getenv` calls

| Variable | Default | Source location |
|---|---|---|
| `PROMETHEUS_URL` | `http://localhost:9090` | `aiops_retrain_trigger.py:35` |
| `DOCUMIND_EVALUATION_URL` | `http://localhost:8085` | `aiops_retrain_trigger.py:36` |
| `NATIVE_COMPUTE_WRAPPER_ENABLED` | **required** | `native_compute_wrapper.py:61` |
| `NAME` | `default` | `generate_folder_report.py:558` |
| `PYTHON_BIN` | **required** | `write_drill_status.py:61` |
| `WHATSAPP_WEBHOOK_ENABLED` | **required** | `whatsapp_fastapi_router.py:56` |
| `WHATSAPP_PROVIDER` | `meta` | `whatsapp_fastapi_router.py:124` |
| `WHATSAPP_META_APP_SECRET` | **required** | `whatsapp_fastapi_router.py:129` |
| `PII_REDACTOR_ENABLED` | **required** | `whatsapp_fastapi_router.py:157` |
| `GEMMA_AGENT_COUNCIL_ENABLED` | **required** | `whatsapp_fastapi_router.py:173` |
| `WHATSAPP_PROVIDER` | `meta` | `whatsapp_fastapi_router.py:243` |
| `AUTORAG_OPTIMIZER_ENABLED` | **required** | `autorag_optimizer.py:57` |
| `MCP_GATEWAY_ENABLED` | **required** | `mcp_gateway.py:53` |
| `MCP_GATEWAY_STRICT` | **required** | `mcp_gateway.py:58` |
| `MCP_GATEWAY_SQL_AUDIT_ENABLED` | **required** | `mcp_gateway.py:356` |
| `DOCUMIND_PG_HOST` | `localhost` | `mcp_gateway.py:389` |
| `DOCUMIND_PG_PORT` | `55432` | `mcp_gateway.py:390` |
| `DOCUMIND_PG_USER` | `documind_app` | `mcp_gateway.py:391` |
| `DOCUMIND_PG_PASSWORD` | `documind_app` | `mcp_gateway.py:392` |
| `DOCUMIND_PG_DB` | `documind` | `mcp_gateway.py:393` |
| `PYDANTICAI_ENABLED` | **required** | `pydanticai_adapter.py:42` |
| `GEPA_TARGET_PROMPT_NAME` | **required** | `promote_gepa_prompts.py:228` |
| `CACHE_FINGERPRINT_ENABLED` | **required** | `cache_fingerprint.py:73` |
| `LANGSMITH_API_KEY` | **required** | `lang_observability_status.py:66` |
| `LANGCHAIN_API_KEY` | **required** | `lang_observability_status.py:66` |
| `LANGSMITH_ENDPOINT` | **required** | `lang_observability_status.py:67` |
| `LANGCHAIN_ENDPOINT` | **required** | `lang_observability_status.py:67` |
| `LANGFUSE_HOST` | `http://localhost:3002` | `lang_observability_status.py:87` |
| `LANGFUSE_PUBLIC_KEY` | **required** | `lang_observability_status.py:89` |
| `LANGFUSE_SECRET_KEY` | **required** | `lang_observability_status.py:90` |
| `COUNCIL_STATS_WEBHOOK` | **required** | `council_filter_stats.py:1014` |
| `MCP_INJECT_FAIL` | **required** | `build_mcp_sdlc_batch.py:271` |
| `DOCUMIND_PG_HOST` | `localhost` | `replay_action_draft.py:49` |
| `DOCUMIND_PG_PORT` | `55432` | `replay_action_draft.py:50` |
| `DOCUMIND_PG_USER` | `documind` | `replay_action_draft.py:51` |
| `DOCUMIND_PG_PASSWORD` | `documind` | `replay_action_draft.py:52` |
| `DOCUMIND_PG_DB` | `documind` | `replay_action_draft.py:53` |
| `DOCUMIND_PG_HOST` | `localhost` | `sync_tools_catalog.py:209` |
| `DOCUMIND_PG_PORT` | `55432` | `sync_tools_catalog.py:210` |
| `DOCUMIND_PG_USER` | `documind_app` | `sync_tools_catalog.py:211` |
| `DOCUMIND_PG_PASSWORD` | `documind_app` | `sync_tools_catalog.py:212` |
| `DOCUMIND_PG_DB` | `documind` | `sync_tools_catalog.py:213` |
| `MCP_TOOLS_SYNC_ENABLED` | **required** | `sync_tools_catalog.py:256` |
| `KAFKA_PUBLISH` | **required** | `event_publisher.py:57` |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | `event_publisher.py:220` |
| `SLACK_WEBHOOK_URL` | **required** | `notifications.py:100` |
| `EMAIL_SMTP_USER` | **required** | `notifications.py:139` |
| `EMAIL_SMTP_APP_PASSWORD` | **required** | `notifications.py:140` |
| `EMAIL_TO` | **required** | `notifications.py:141` |
| `EMAIL_SMTP_HOST` | `smtp.gmail.com` | `notifications.py:145` |
| `EMAIL_SMTP_PORT` | `587` | `notifications.py:146` |
| `TWILIO_ACCOUNT_SID` | **required** | `notifications.py:171` |
| `TWILIO_AUTH_TOKEN` | **required** | `notifications.py:172` |
| `TWILIO_WHATSAPP_FROM` | **required** | `notifications.py:173` |
| `WHATSAPP_TO` | **required** | `notifications.py:174` |
| `GENERIC_WEBHOOK_URL` | **required** | `notifications.py:216` |
| `LITELLM_ENABLED` | **required** | `litellm_adapter.py:40` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `litellm_adapter.py:167` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `litellm_adapter.py:190` |
| `STAGE3_EARNED_CHECK_ENABLED` | **required** | `stage3_earned_check.py:63` |
| `STAGE3_MIN_CYCLES` | `10` | `stage3_earned_check.py:65` |
| `STAGE3_MIN_SUCCESS_RATIO` | `0.8` | `stage3_earned_check.py:66` |
| `STAGE3_MIN_DISTINCT` | `2` | `stage3_earned_check.py:73` |
| `DOCUMIND_PG_OPS_USER` | `documind_ops` | `audit_verify.py:77` |
| `DOCUMIND_PG_OPS_PASSWORD` | `documind_ops` | `audit_verify.py:78` |
| `DOCUMIND_PG_HOST` | `localhost` | `audit_verify.py:79` |
| `DOCUMIND_PG_PORT` | `55432` | `audit_verify.py:80` |
| `DOCUMIND_PG_DB` | `documind` | `audit_verify.py:81` |
| `PROMOTION_GATE_ENABLED` | **required** | `promote_best_config.py:57` |
| `PROMOTION_MIN_PASS_RATE` | `0.5` | `promote_best_config.py:60` |
| `PROMOTION_MIN_MARGIN` | `0.0` | `promote_best_config.py:61` |
| `PROMOTION_MIN_EVAL_SET` | `5` | `promote_best_config.py:62` |
| `SAFETY_STORE_DB` | `str(SAFETY_DB_DEFAULT` | `paperclip_manager.py:290` |
| `SAFETY_STORE_DB` | `str(SAFETY_DB_DEFAULT` | `paperclip_manager.py:374` |
| `XAI_API_KEY` | **required** | `paperclip_manager.py:1280` |
| `XAI_API_KEY` | **required** | `paperclip_manager.py:1304` |
| `WHATSAPP_WEBHOOK_ENABLED` | **required** | `whatsapp_webhook.py:65` |
| `WHATSAPP_PROVIDER` | `meta` | `whatsapp_webhook.py:66` |
| `WHATSAPP_VERIFY_TOKEN` | **required** | `whatsapp_webhook.py:67` |
| `WHATSAPP_META_APP_SECRET` | **required** | `whatsapp_webhook.py:112` |
| `WHATSAPP_TWILIO_AUTH_TOKEN` | **required** | `whatsapp_webhook.py:113` |
| `DOCUMIND_PG_HOST` | `localhost` | `migrate.py:25` |
| `DOCUMIND_PG_PORT` | `5432` | `migrate.py:26` |
| `DOCUMIND_PG_DB` | `documind` | `migrate.py:27` |
| `DOCUMIND_PG_USER` | `documind` | `migrate.py:28` |
| `DOCUMIND_PG_PASSWORD` | `documind` | `migrate.py:29` |
| `DOCUMIND_MCP_JIRA_URL` | **required** | `mcp_fleet_health.py:149` |
| `EVAL_SET_GENERATOR_ENABLED` | **required** | `eval_set_generator.py:61` |
| `EVAL_SET_GENERATOR_MODEL` | `gemma3:4b` | `eval_set_generator.py:62` |
| `EVAL_SET_GENERATOR_TIMEOUT_S` | `30` | `eval_set_generator.py:63` |
| `EVAL_SET_MAX_PAIRS` | `50` | `eval_set_generator.py:64` |
| `OLLAMA_HOST` | `http://localhost:11434` | `eval_set_generator.py:65` |
| `AUTORAG_OPTIMIZER_ENABLED` | **required** | `run_autorag_empirical.py:163` |
| `PROMOTION_GATE_ENABLED` | **required** | `run_autorag_empirical.py:243` |
| `DOCUMIND_PG_HOST` | `localhost` | `hitl_drafts_triage.py:33` |
| `DOCUMIND_PG_PORT` | `55432` | `hitl_drafts_triage.py:34` |
| `DOCUMIND_PG_USER` | `documind` | `hitl_drafts_triage.py:35` |
| `DOCUMIND_PG_PASSWORD` | `documind` | `hitl_drafts_triage.py:36` |
| `DOCUMIND_PG_DB` | `documind` | `hitl_drafts_triage.py:37` |
| `PYTHON_BIN` | **required** | `run_drills.py:63` |
| `AGENT_ROUTER_OLLAMA_ENABLED` | **required** | `agent_router.py:60` |
| `DSPY_OPTIMIZER_ENABLED` | **required** | `dspy_optimizer.py:63` |
| `DSPY_LM_MODEL` | `ollama_chat/gemma2:9b` | `dspy_optimizer.py:64` |
| `OLLAMA_HOST` | `http://localhost:11435` | `dspy_optimizer.py:65` |
| `RAGAS_EVAL_ENABLED` | **required** | `ragas_eval_adapter.py:56` |
| `RAGAS_LM_MODEL` | `ollama_chat/gemma2:9b` | `ragas_eval_adapter.py:57` |
| `OLLAMA_HOST` | `http://localhost:11434` | `ragas_eval_adapter.py:58` |
| `RAGAS_FAITHFULNESS_THRESHOLD` | `0.7` | `ragas_eval_adapter.py:64` |
| `RAGAS_ANSWER_RELEVANCY_THRESHOLD` | `0.7` | `ragas_eval_adapter.py:65` |
| `RAGAS_CONTEXT_PRECISION_THRESHOLD` | `0.5` | `ragas_eval_adapter.py:66` |
| `RAGAS_CONTEXT_RECALL_THRESHOLD` | `0.5` | `ragas_eval_adapter.py:67` |
| `RAGAS_ANSWER_CORRECTNESS_THRESHOLD` | `0.6` | `ragas_eval_adapter.py:68` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `ollama_all_models_smoke.py:47` |
| `DSPY_OPTIMIZER_ENABLED` | `(unset` | `show_gepa_status.py:96` |
| `GEMMA_AGENT_COUNCIL_ENABLED` | `(unset` | `show_gepa_status.py:97` |
| `OLLAMA_HOST` | `(default` | `show_gepa_status.py:98` |
| `GEPA_PROMOTION_GATE_ENABLED` | `(unset` | `show_gepa_status.py:124` |
| `GEPA_PROMPT_LOADER_ENABLED` | `(unset` | `show_gepa_status.py:134` |
| `GEPA_TARGET_PROMPT_NAME` | `(unset` | `show_gepa_status.py:155` |
| `GEPA_CANARY_ENABLED` | **required** | `show_gepa_status.py:165` |
| `GEPA_CANARY_PERCENT` | `0` | `show_gepa_status.py:166` |
| `BEST_CONFIG_HISTORY_ENABLED` | **required** | `best_config_history.py:46` |
| `KUBECONFIG` | `/mnt/deepa/.kube/config` | `catalog_tools_probe.py:265` |
| `KUBECONFIG` | `/mnt/deepa/.kube/config` | `catalog_tools_probe.py:291` |
| `DSPY_OPTIMIZER_ENABLED` | **required** | `run_gepa_empirical.py:459` |
| `HYDE_ENABLED` | **required** | `hyde_adapter.py:67` |
| `HYDE_MODEL` | `gemma3:1b` | `hyde_adapter.py:68` |
| `HYDE_MAX_TOKENS` | `200` | `hyde_adapter.py:69` |
| `HYDE_TIMEOUT_S` | `10` | `hyde_adapter.py:70` |
| `OLLAMA_HOST` | `http://localhost:11434` | `hyde_adapter.py:71` |
| `DOCUMIND_PG_HOST` | `localhost` | `seed_demo.py:61` |
| `DOCUMIND_PG_PORT` | `5432` | `seed_demo.py:62` |
| `DOCUMIND_PG_DB` | `documind` | `seed_demo.py:63` |
| `DOCUMIND_PG_USER` | `documind` | `seed_demo.py:64` |
| `DOCUMIND_PG_PASSWORD` | `documind` | `seed_demo.py:65` |
| `EVAL_GATE_GROUNDEDNESS_THRESHOLD` | `0.55` | `eval_quality_status.py:87` |
| `EVAL_GATE_CONTEXT_RELEVANCE_THRESHOLD` | `0.35` | `eval_quality_status.py:88` |
| `EVAL_GATE_CORRECTNESS_THRESHOLD` | `0.60` | `eval_quality_status.py:89` |
| `RAGAS_EVAL_ENABLED` | **required** | `eval_quality_status.py:260` |
| `RAGAS_EVAL_ENABLED` | **required** | `eval_quality_status.py:261` |
| `GISKARD_SCAN_ENABLED` | **required** | `eval_quality_status.py:266` |
| `GISKARD_SCAN_ENABLED` | **required** | `eval_quality_status.py:267` |
| `DEEPEVAL_ENABLED` | **required** | `eval_quality_status.py:272` |
| `DEEPEVAL_ENABLED` | **required** | `eval_quality_status.py:273` |
| `DOCUMIND_INGESTION_URL` | `http://localhost:8082` | `smoke_test.py:24` |
| `DOCUMIND_INFERENCE_URL` | `http://localhost:8084` | `smoke_test.py:25` |
| `DOCUMIND_RETRIEVAL_URL` | `http://localhost:8083` | `smoke_test.py:26` |
| `BEST_CONFIG_LOADER_ENABLED` | `1` | `best_config_loader.py:63` |
| `BEST_CONFIG_PATH` | `.loop/best_config.json` | `best_config_loader.py:65` |
| `BEST_CONFIG_TTL_S` | `300` | `best_config_loader.py:66` |
| `REBUFF_PI_THRESHOLD` | `0.5` | `rebuff_status.py:89` |
| `REBUFF_ENABLED` | **required** | `rebuff_status.py:175` |
| `REBUFF_API_TOKEN` | **required** | `rebuff_status.py:176` |
| `REBUFF_API_URL` | `https://www.rebuff.ai` | `rebuff_status.py:177` |
| `DOCUMIND_PG_HOST` | `localhost` | `agent_task_registry.py:69` |
| `DOCUMIND_PG_PORT` | `55432` | `agent_task_registry.py:70` |
| `DOCUMIND_PG_USER` | `documind` | `agent_task_registry.py:71` |
| `DOCUMIND_PG_PASSWORD` | `documind` | `agent_task_registry.py:72` |
| `DOCUMIND_PG_DB` | `documind` | `agent_task_registry.py:73` |
| `PAPERCLIP_DISPATCH_ENABLED` | **required** | `paperclip_dispatcher.py:41` |
| `GEMMA_AGENT_COUNCIL_ENABLED` | **required** | `gemma_agent_council.py:65` |
| `OLLAMA_HOST` | `http://localhost:11435` | `gemma_agent_council.py:66` |
| `GEMMA_SAFETY_PRE_MODEL` | `shieldgemma:2b` | `gemma_agent_council.py:80` |
| `GEMMA_ROUTER_MODEL` | `gemma3:1b` | `gemma_agent_council.py:81` |
| `GEMMA_PLANNER_MODEL` | `gemma3:4b` | `gemma_agent_council.py:82` |
| `GEMMA_CODE_MODEL` | `codegemma:7b` | `gemma_agent_council.py:83` |
| `GEMMA_RAG_MODEL` | `gemma2:9b` | `gemma_agent_council.py:84` |
| `GEMMA_GENERAL_MODEL` | `gemma3:4b` | `gemma_agent_council.py:85` |
| `GEMMA_CRITIC_MODEL` | `gemma2:9b` | `gemma_agent_council.py:86` |
| `GEMMA_SAFETY_POST_MODEL` | `shieldgemma:9b` | `gemma_agent_council.py:87` |
| `OLLAMA_FALLBACK_MODEL` | `qwen2.5:latest` | `chatxai_fallback.py:38` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `chatxai_fallback.py:39` |
| `XAI_API_KEY` | **required** | `chatxai_fallback.py:44` |
| `LANGFUSE_TRACER_ENABLED` | **required** | `langfuse_tracer.py:73` |
| `LANGFUSE_HOST` | `http://localhost:3000` | `langfuse_tracer.py:74` |
| `LANGFUSE_PUBLIC_KEY` | **required** | `langfuse_tracer.py:75` |
| `LANGFUSE_SECRET_KEY` | **required** | `langfuse_tracer.py:76` |
| `DOCUMIND_NEO4J_USER` | `neo4j` | `scenario_batch_and_inference.py:54` |
| `DOCUMIND_NEO4J_PASSWORD` | `documind` | `scenario_batch_and_inference.py:55` |
| `DOCUMIND_JAEGER_API_URL` | `http://localhost:16686` | `scenario_batch_and_inference.py:499` |
| `PII_REDACTOR_ENABLED` | **required** | `pii_redactor.py:52` |
| `PII_REDACTOR_SCORE_THRESHOLD` | `0.5` | `pii_redactor.py:53` |

_Variables marked **required** must be set — missing values may raise on startup or silently default to empty strings._


## 2. File Inventory

Every Python file in this folder, with role / classes / functions / LOC / first docstring line. Full absolute paths listed below the table for easy `cat`-ability.

| Relative path | Role (inferred) | Classes | Functions | LOC | Summary |
|---|---|---|---|---|---|
| `advanced_healthcheck.py` | 📄 module | 1 | 18 | 568 | Advanced multi-layer health-check + troubleshoot + tracking tool. |
| `agent_lead.py` | 🤖 agent / tool | 1 | 3 | 249 | Agent-lead-first routing — Tier 1 #1.2 of the autonomous-fix-bot roadmap. |
| `agent_readiness_check.py` | 🤖 agent / tool | 0 | 9 | 405 | Agent readiness check — does the council actually FIX things? (iter-76). |
| `agent_router.py` | 🤖 agent / tool | 2 | 7 | 400 | Agent Router Stage-1 — intent + risk classifier (conservative-default). |
| `agent_task_board.py` | 🤖 agent / tool | 0 | 10 | 404 | Agent Task Board — central status view + drill-gated apply pipeline. |
| `agent_task_registry.py` | 🤖 agent / tool | 0 | 12 | 827 | Unified agent task registry — provider-comparison rollup. |
| `agentic_observability_audit.py` | 🤖 agent / tool | 0 | 2 | 139 | Audit the 35-scenario agentic observability catalog (iter-96). |
| `aiops_retrain_trigger.py` | 📄 module | 1 | 5 | 154 | AIops — automatic retrain-trigger driver. |
| `append_drill_history.py` | 📄 module | 0 | 4 | 120 | Append .loop/last_drill_outcome.json → .loop/drill_history.jsonl. |
| `audit_readme_scores.py` | 📄 module | 2 | 9 | 372 | Aggregate README audit-checklist scores across every folder in the repo. |
| `audit_verify.py` | 📄 module | 1 | 8 | 360 | audit_verify.py — walk governance.audit_log per tenant and detect tampering. |
| `autonomous_fix_daemon.py` | 📄 module | 0 | 21 | 616 | Autonomous Fix Daemon — always-active issue triage + drill-gated apply. |
| `autorag_optimizer.py` | 📄 module | 5 | 5 | 375 | AutoRAG optimizer — Stage-1 adapter (per CLAUDE.md §56). |
| `best_config_history.py` | ⚙ config / settings | 2 | 5 | 206 | Best-config history reader — Stage-1 audit-trail surface (per §38 + §51). |
| `best_config_loader.py` | ⚙ config / settings | 2 | 8 | 241 | Best-config registry loader — Stage-3 default-on (per ADR-024). |
| `build_doc_framework_templates.py` | 📄 module | 0 | 7 | 391 | Build skeleton + prompt template files referenced by registry.yaml. |
| `build_mcp_sdlc_batch.py` | 📄 module | 0 | 2 | 382 | Build 11 MCP server stubs (P1+P2+P3 SDLC batch) from one config map. |
| `cache_fingerprint.py` | 📄 module | 2 | 5 | 266 | Cache fingerprint helper — Stage-1 (per CLAUDE.md §56). |
| `capture_and_review.py` | 📄 module | 1 | 4 | 343 | Capture the latest git diff + send it through the Sidecar council. |
| `catalog_tools_probe.py` | 🤖 agent / tool | 0 | 11 | 445 | Probe every tool in config/agentic_observability/oss_tooling_catalog.yaml |
| `chatxai_fallback.py` | 📄 module | 0 | 5 | 166 | ChatXAI → ChatOllama fallback CLI when XAI_API_KEY absent. |
| `chunking_quality_audit.py` | 📄 module | 0 | 1 | 130 | Chunking quality catalog audit (iter-99). |
| `chunking_strategy_selector.py` | 📄 module | 2 | 5 | 300 | Chunking strategy selector — Stage-1 adapter (per CLAUDE.md §56). |
| `council_filter_stats.py` | 📄 module | 1 | 24 | 1204 | Group council_runs.log entries by outcome / filter reason / risk. |
| `council_schemas.py` | 📄 module | 1 | 3 | 291 | Pydantic schemas for the local-Ollama issue-fix council. |
| `council_stats_snapshot.py` | 📄 module | 0 | 7 | 280 | Daily council outcome snapshot — append-only JSONL for long-term trends. |
| `crewai_status.py` | 📄 module | 0 | 4 | 90 | CrewAI status gate. |
| `deep_rag_test.py` | 🧪 test | 0 | 5 | 212 | Deep RAG end-to-end test. |
| `doc_framework_registry.py` | 📄 module | 3 | 6 | 390 | Doc-framework registry loader + validator. |
| `drain_outbox.py` | 📄 module | 0 | 3 | 195 | One-shot outbox drain — publishes backlogged ingestion.outbox rows. |
| `drill_catalog_summary.py` | 📄 module | 0 | 7 | 179 | Drill catalog summary — one report for tiering, resource sets, and ratchets. |
| `dspy_optimizer.py` | 📄 module | 1 | 5 | 232 | DSPy 3 + GEPA prompt optimizer — Stage-1 adapter (per CLAUDE.md §56). |
| `e2e_per_tool_report.py` | 🤖 agent / tool | 0 | 10 | 400 | End-to-end per-tool integration test harness (iter-90). |
| `empirical_apply_test.py` | 🧪 test | 0 | 6 | 227 | Empirical apply-rate test harness — runs council on synthetic broken file. |
| `eval_quality_status.py` | 📄 module | 0 | 12 | 334 | Advanced offline-safe status for RAGAS, Giskard, and DeepEval. |
| `eval_set_generator.py` | 📄 module | 2 | 8 | 361 | Eval-set auto-generator — Stage-1 adapter (per CLAUDE.md §56). |
| `event_publisher.py` | 📄 module | 0 | 8 | 262 | Stage-1 event-publisher — pushes new-layer audit events to Kafka. |
| `experts.py` | 📄 module | 0 | 5 | 245 | Experts registry — named specialists backed by local Ollama models. |
| `gemma_agent_council.py` | 🤖 agent / tool | 3 | 11 | 446 | Gemma Agent Council — 5-agent orchestrator using local Gemma stack. |
| `generate-grafana-dashboards.py` | 📄 module | 0 | 4 | 354 | Generator for the 15 Grafana dashboards Kiali deep-links to. |
| `generate_brutal_reviews.py` | 📄 module | 0 | 6 | 331 | Generate brutal-review docs for every MCP server (iter-84). |
| `generate_folder_readme.py` | 📄 module | 1 | 18 | 491 | Folder README.md generator — pre-populated from auto-detection. |
| `generate_folder_report.py` | 💾 repository / data access | 7 | 68 | 3127 | Folder-level ADVANCED README generator. |
| `generate_folder_review_report.py` | 💾 repository / data access | 3 | 39 | 994 | Folder-level Manual Code Review Checklist generator. |
| `generate_mesh_manifests.py` | 📄 module | 0 | 5 | 318 | Generate k8s Deployment + Service manifests for each MCP/agent tool (iter-94). |
| `generate_production_review_report.py` | 💾 repository / data access | 3 | 27 | 1438 | Master Production Code Review & Architecture Assessment Checklist generator. |
| `generate_project_readme.py` | 📄 module | 1 | 51 | 1497 | Project-level README generator (writes ``README.md`` at repo root). |
| `generate_specialized_assessment.py` | 📄 module | 2 | 17 | 879 | Specialized assessment generator — frontend OR backend profile. |
| `generate_tool_catalog_entries.py` | 🤖 agent / tool | 0 | 5 | 329 | Generate config/tool_catalog/<ns>.yaml for every MCP server (iter-80). |
| `hitl_drafts_triage.py` | 📄 module | 0 | 7 | 360 | HITL drafts triage report — read-only operator-decision input. |
| `hitl_framework.py` | 📄 module | 1 | 10 | 332 | HITL framework — Human-in-the-loop scoring at every pipeline gate. |
| `human_review_router.py` | 📄 module | 1 | 4 | 265 | Human-review router — routes retry-storm ids out of the council loop. |
| `hyde_adapter.py` | 🔌 external service adapter | 2 | 3 | 215 | HyDE (Hypothetical Document Embeddings) adapter — Stage-1 (per §56). |
| `issue_dispatcher.py` | 📄 module | 0 | 9 | 334 | Issue dispatcher — routes each issue from the checklist to its assignee. |
| `issue_scanner.py` | 📄 module | 0 | 9 | 501 | Issue scanner — produces .loop/issue_checklist.jsonl from real signal sources. |
| `lang_observability_status.py` | 📄 module | 0 | 7 | 154 | Lang observability status for LangSmith and Langfuse. |
| `langfuse_tracer.py` | 📄 module | 3 | 6 | 297 | Langfuse tracer — Stage-1 adapter (per CLAUDE.md §56). |
| `litellm_adapter.py` | 🔌 external service adapter | 1 | 6 | 259 | LiteLLM adapter — Stage-1 contract for the call_ollama() swap. |
| `local_council.py` | 📄 module | 2 | 17 | 979 | Local council runner — schema-aware author + critique reviewer + advisor. |
| `loop_status.py` | 📄 module | 0 | 9 | 328 | Loop status — one-shot "is everything fine?" report. |
| `loop_watcher_hook.py` | 📄 module | 0 | 9 | 211 | Post-commit watcher hook - runs LoopWatcher on the latest commit. |
| `mcp_fleet_health.py` | 📄 module | 8 | 16 | 827 | MCP fleet health monitor — classify every installed/configured tool. |
| `mcp_gateway.py` | 🔌 external service adapter | 5 | 9 | 506 | MCP Gateway — Stage-1 allowlist + PolisAI gate + audit for MCP calls. |
| `mcp_gateway_warmup.py` | 🔌 external service adapter | 0 | 2 | 84 | MCP gateway warmup — seed audit rows with latency_ms. |
| `migrate.py` | 📄 module | 0 | 3 | 86 | Migration runner — applies numbered SQL files per service. |
| `native_compute_wrapper.py` | 📄 module | 4 | 1 | 318 | Native-compute wrapper — Stage-1 adapter for LLVM/MLIR-optimized callables. |
| `notifications.py` | 📄 module | 2 | 7 | 307 | Notifications — Tier 5 #5.13. |
| `observability_triad_status.py` | 📄 module | 0 | 10 | 175 | Offline-safe readiness checker for Jaeger, Prometheus, and Grafana. |
| `ollama_all_models_smoke.py` | 📄 module | 0 | 6 | 253 | Ollama all-models smoke test (iter-75). |
| `opa_gatekeeper_status.py` | 📄 module | 0 | 7 | 206 | Offline-safe OPA Gatekeeper readiness checker. |
| `openclaw_coordinator.py` | 📄 module | 6 | 7 | 517 | OpenClaw Stage-1 — heavy-autonomy A2A (agent-to-agent) coordinator. |
| `oss_tooling_audit.py` | 🤖 agent / tool | 0 | 1 | 154 | OSS-only tooling catalog audit (iter-97). |
| `outbox_dispatcher_doctor.py` | 📄 module | 0 | 4 | 175 | Outbox dispatcher doctor — diagnose stuck saga dispatcher. |
| `outbox_gc.py` | 📄 module | 0 | 2 | 133 | Outbox garbage collector — delete published rows older than TTL. |
| `outcome_eval.py` | 📄 module | 1 | 12 | 333 | Outcome-based evaluation framework — Tier 4 #4.5. |
| `paperclip_dispatcher.py` | 📄 module | 2 | 4 | 204 | Paperclip Stage-3 — dispatcher composes propose + openclaw.dispatch. |
| `paperclip_manager.py` | 📄 module | 0 | 32 | 1656 | Paperclip Stage-1 — read-only manager-layer aggregator. |
| `pii_redactor.py` | 📄 module | 2 | 5 | 225 | PII redactor — Stage-1 Presidio adapter (per CLAUDE.md §56). |
| `policy_check.py` | 📄 module | 2 | 5 | 349 | Policy Stage-1 — local Rego-shaped policy evaluator. |
| `pr_management.py` | 📄 module | 2 | 8 | 250 | PR management — Tier 5 #5.5. |
| `prior_fix_rag.py` | 📄 module | 1 | 9 | 272 | Prior-fix retrieval — Tier 2 #2.6. |
| `production_readiness_scorecard.py` | 📄 module | 0 | 10 | 420 | Production readiness scorecard — aggregates §38 + §47 + §52 + §53 + §55 (iter-78). |
| `promote_best_config.py` | ⚙ config / settings | 2 | 5 | 278 | Best-config promotion gate — Stage-1 adapter (per CLAUDE.md §38 + §56). |
| `promote_gepa_prompts.py` | 📄 module | 2 | 3 | 324 | GEPA-prompt promotion gate — Stage-4 adapter (per ADR-024-style chain). |
| `prune_council_runs.py` | 📄 module | 0 | 2 | 128 | Prune old advisor_council_runs rows for storage discipline. |
| `prune_loop_logs.py` | 📄 module | 0 | 5 | 212 | Prune old entries from .loop/*.log JSONL files for retention discipline. |
| `pydanticai_adapter.py` | 🔌 external service adapter | 1 | 5 | 164 | PydanticAI adapter — Stage-1 contract for the AUTHOR validator swap. |
| `ragas_eval_adapter.py` | 🔌 external service adapter | 3 | 5 | 364 | RAGAS evaluation adapter — Stage-1 (per CLAUDE.md §56). |
| `ratchet_status.py` | 📄 module | 0 | 13 | 291 | Ratchet status — one-shot survey of the current discipline ratchets. |
| `rebuff_status.py` | 📄 module | 0 | 8 | 226 | Offline-safe Rebuff readiness and prompt-injection smoke scanner. |
| `reflection_engine.py` | 📄 module | 3 | 6 | 403 | Reflection engine — periodic self-critique of recent council decisions. |
| `rego_sync_check.py` | 📄 module | 0 | 4 | 158 | Rego/JSON policy sync checker — Stage-2 scaffold for OPA swap. |
| `render_dashboard.py` | 📄 module | 0 | 7 | 333 | Render a self-contained HTML dashboard for the Sidecar Advisor. |
| `replay_action_draft.py` | 📄 module | 0 | 6 | 354 | Replay or reject governance.action_drafts entries. |
| `replay_council_against_events.py` | 📄 module | 0 | 2 | 162 | Batched replay of the Sidecar council against events captured |
| `replay_verdict_log.py` | 📄 module | 2 | 7 | 254 | Replay .loop/watcher.log: find REJECT verdicts, optionally revert. |
| `review_council.py` | 📄 module | 0 | 8 | 203 | Review tool — surfaces the latest council take per unique issue. |
| `rule_fix_strategy.py` | 📄 module | 1 | 3 | 222 | Per-rule fix-strategy table — Tier 1 #1.3 of the autonomous-fix-bot roadmap. |
| `run_autorag_empirical.py` | 📄 module | 0 | 4 | 294 | End-to-end AutoRAG empirical run — Stage-2 driver (per CLAUDE.md §56). |
| `run_council_batch.py` | 📄 module | 0 | 2 | 104 | Run the 3-model council on every medium-difficulty issue in the checklist. |
| `run_drills.py` | 📄 module | 2 | 12 | 603 | run_drills.py — resource-aware parallel drill runner. |
| `run_gepa_empirical.py` | 📄 module | 0 | 5 | 565 | End-to-end GEPA prompt-optimization run — Stage-2 driver. |
| `runtime_security_status.py` | 📄 module | 0 | 10 | 207 | Offline-safe readiness checker for Wazuh, Tetragon, and Tracee. |
| `scenario_batch_and_inference.py` | 📄 module | 0 | 17 | 834 | End-to-end scenario runner — batch + inference (iter-91). |
| `seed_demo.py` | 📄 module | 0 | 3 | 109 | Seed a demo tenant + sample documents. |
| `show_gepa_status.py` | 📄 module | 0 | 4 | 195 | GEPA chain status reporter — one operator command for the whole pipeline. |
| `smoke_test.py` | 🧪 test | 0 | 1 | 89 | End-to-end smoke test. |
| `stage3_earned_check.py` | 📄 module | 2 | 4 | 323 | Stage-3 default-flip earned-check (per CLAUDE.md §56.3). |
| `sync_tools_catalog.py` | 🤖 agent / tool | 0 | 7 | 272 | Sync MCP server TOOLS lists into governance.tools. |
| `task_manager.py` | 📄 module | 1 | 12 | 305 | Task management — Tier 5 #5.7. |
| `techstack_audit.py` | 📄 module | 0 | 10 | 327 | Empirical techstack audit — checks each tool's actual install status. |
| `tier_1_3b_empirical_validation.py` | 📄 module | 0 | 1 | 142 | Tier 1.3.b empirical validation — historical failure modes vs new gate. |
| `tier_b_fallback.py` | 📄 module | 0 | 4 | 205 | Confidence-gated Tier-B fallback — Tier 2 #2.7. |
| `tool_catalog.py` | 🤖 agent / tool | 1 | 4 | 286 | Tool catalog loader + validator (iter-74). |
| `verifiability_framework.py` | 📄 module | 2 | 4 | 322 | Verifiability framework — Tier 2 #2.11. |
| `warm_council_pool.py` | 📄 module | 0 | 7 | 169 | Warm council pool — keep all 4 Ollama council models RAM-resident. |
| `whatsapp_fastapi_router.py` | 📄 module | 0 | 4 | 260 | WhatsApp FastAPI router — Stage-2 wire (per CLAUDE.md §56). |
| `whatsapp_webhook.py` | 📄 module | 3 | 10 | 310 | WhatsApp webhook gateway — Stage-1 adapter (per CLAUDE.md §56). |
| `write_drill_status.py` | 📄 module | 1 | 5 | 297 | Run a set of drills, capture pass/fail per drill, write status JSON. |

### Absolute paths (clickable)

- `/mnt/deepa/rag/scripts/advanced_healthcheck.py`
- `/mnt/deepa/rag/scripts/agent_lead.py`
- `/mnt/deepa/rag/scripts/agent_readiness_check.py`
- `/mnt/deepa/rag/scripts/agent_router.py`
- `/mnt/deepa/rag/scripts/agent_task_board.py`
- `/mnt/deepa/rag/scripts/agent_task_registry.py`
- `/mnt/deepa/rag/scripts/agentic_observability_audit.py`
- `/mnt/deepa/rag/scripts/aiops_retrain_trigger.py`
- `/mnt/deepa/rag/scripts/append_drill_history.py`
- `/mnt/deepa/rag/scripts/audit_readme_scores.py`
- `/mnt/deepa/rag/scripts/audit_verify.py`
- `/mnt/deepa/rag/scripts/autonomous_fix_daemon.py`
- `/mnt/deepa/rag/scripts/autorag_optimizer.py`
- `/mnt/deepa/rag/scripts/best_config_history.py`
- `/mnt/deepa/rag/scripts/best_config_loader.py`
- `/mnt/deepa/rag/scripts/build_doc_framework_templates.py`
- `/mnt/deepa/rag/scripts/build_mcp_sdlc_batch.py`
- `/mnt/deepa/rag/scripts/cache_fingerprint.py`
- `/mnt/deepa/rag/scripts/capture_and_review.py`
- `/mnt/deepa/rag/scripts/catalog_tools_probe.py`
- `/mnt/deepa/rag/scripts/chatxai_fallback.py`
- `/mnt/deepa/rag/scripts/chunking_quality_audit.py`
- `/mnt/deepa/rag/scripts/chunking_strategy_selector.py`
- `/mnt/deepa/rag/scripts/council_filter_stats.py`
- `/mnt/deepa/rag/scripts/council_schemas.py`
- `/mnt/deepa/rag/scripts/council_stats_snapshot.py`
- `/mnt/deepa/rag/scripts/crewai_status.py`
- `/mnt/deepa/rag/scripts/deep_rag_test.py`
- `/mnt/deepa/rag/scripts/doc_framework_registry.py`
- `/mnt/deepa/rag/scripts/drain_outbox.py`
- `/mnt/deepa/rag/scripts/drill_catalog_summary.py`
- `/mnt/deepa/rag/scripts/dspy_optimizer.py`
- `/mnt/deepa/rag/scripts/e2e_per_tool_report.py`
- `/mnt/deepa/rag/scripts/empirical_apply_test.py`
- `/mnt/deepa/rag/scripts/eval_quality_status.py`
- `/mnt/deepa/rag/scripts/eval_set_generator.py`
- `/mnt/deepa/rag/scripts/event_publisher.py`
- `/mnt/deepa/rag/scripts/experts.py`
- `/mnt/deepa/rag/scripts/gemma_agent_council.py`
- `/mnt/deepa/rag/scripts/generate-grafana-dashboards.py`
- `/mnt/deepa/rag/scripts/generate_brutal_reviews.py`
- `/mnt/deepa/rag/scripts/generate_folder_readme.py`
- `/mnt/deepa/rag/scripts/generate_folder_report.py`
- `/mnt/deepa/rag/scripts/generate_folder_review_report.py`
- `/mnt/deepa/rag/scripts/generate_mesh_manifests.py`
- `/mnt/deepa/rag/scripts/generate_production_review_report.py`
- `/mnt/deepa/rag/scripts/generate_project_readme.py`
- `/mnt/deepa/rag/scripts/generate_specialized_assessment.py`
- `/mnt/deepa/rag/scripts/generate_tool_catalog_entries.py`
- `/mnt/deepa/rag/scripts/hitl_drafts_triage.py`
- `/mnt/deepa/rag/scripts/hitl_framework.py`
- `/mnt/deepa/rag/scripts/human_review_router.py`
- `/mnt/deepa/rag/scripts/hyde_adapter.py`
- `/mnt/deepa/rag/scripts/issue_dispatcher.py`
- `/mnt/deepa/rag/scripts/issue_scanner.py`
- `/mnt/deepa/rag/scripts/lang_observability_status.py`
- `/mnt/deepa/rag/scripts/langfuse_tracer.py`
- `/mnt/deepa/rag/scripts/litellm_adapter.py`
- `/mnt/deepa/rag/scripts/local_council.py`
- `/mnt/deepa/rag/scripts/loop_status.py`
- `/mnt/deepa/rag/scripts/loop_watcher_hook.py`
- `/mnt/deepa/rag/scripts/mcp_fleet_health.py`
- `/mnt/deepa/rag/scripts/mcp_gateway.py`
- `/mnt/deepa/rag/scripts/mcp_gateway_warmup.py`
- `/mnt/deepa/rag/scripts/migrate.py`
- `/mnt/deepa/rag/scripts/native_compute_wrapper.py`
- `/mnt/deepa/rag/scripts/notifications.py`
- `/mnt/deepa/rag/scripts/observability_triad_status.py`
- `/mnt/deepa/rag/scripts/ollama_all_models_smoke.py`
- `/mnt/deepa/rag/scripts/opa_gatekeeper_status.py`
- `/mnt/deepa/rag/scripts/openclaw_coordinator.py`
- `/mnt/deepa/rag/scripts/oss_tooling_audit.py`
- `/mnt/deepa/rag/scripts/outbox_dispatcher_doctor.py`
- `/mnt/deepa/rag/scripts/outbox_gc.py`
- `/mnt/deepa/rag/scripts/outcome_eval.py`
- `/mnt/deepa/rag/scripts/paperclip_dispatcher.py`
- `/mnt/deepa/rag/scripts/paperclip_manager.py`
- `/mnt/deepa/rag/scripts/pii_redactor.py`
- `/mnt/deepa/rag/scripts/policy_check.py`
- `/mnt/deepa/rag/scripts/pr_management.py`
- `/mnt/deepa/rag/scripts/prior_fix_rag.py`
- `/mnt/deepa/rag/scripts/production_readiness_scorecard.py`
- `/mnt/deepa/rag/scripts/promote_best_config.py`
- `/mnt/deepa/rag/scripts/promote_gepa_prompts.py`
- `/mnt/deepa/rag/scripts/prune_council_runs.py`
- `/mnt/deepa/rag/scripts/prune_loop_logs.py`
- `/mnt/deepa/rag/scripts/pydanticai_adapter.py`
- `/mnt/deepa/rag/scripts/ragas_eval_adapter.py`
- `/mnt/deepa/rag/scripts/ratchet_status.py`
- `/mnt/deepa/rag/scripts/rebuff_status.py`
- `/mnt/deepa/rag/scripts/reflection_engine.py`
- `/mnt/deepa/rag/scripts/rego_sync_check.py`
- `/mnt/deepa/rag/scripts/render_dashboard.py`
- `/mnt/deepa/rag/scripts/replay_action_draft.py`
- `/mnt/deepa/rag/scripts/replay_council_against_events.py`
- `/mnt/deepa/rag/scripts/replay_verdict_log.py`
- `/mnt/deepa/rag/scripts/review_council.py`
- `/mnt/deepa/rag/scripts/rule_fix_strategy.py`
- `/mnt/deepa/rag/scripts/run_autorag_empirical.py`
- `/mnt/deepa/rag/scripts/run_council_batch.py`
- `/mnt/deepa/rag/scripts/run_drills.py`
- `/mnt/deepa/rag/scripts/run_gepa_empirical.py`
- `/mnt/deepa/rag/scripts/runtime_security_status.py`
- `/mnt/deepa/rag/scripts/scenario_batch_and_inference.py`
- `/mnt/deepa/rag/scripts/seed_demo.py`
- `/mnt/deepa/rag/scripts/show_gepa_status.py`
- `/mnt/deepa/rag/scripts/smoke_test.py`
- `/mnt/deepa/rag/scripts/stage3_earned_check.py`
- `/mnt/deepa/rag/scripts/sync_tools_catalog.py`
- `/mnt/deepa/rag/scripts/task_manager.py`
- `/mnt/deepa/rag/scripts/techstack_audit.py`
- `/mnt/deepa/rag/scripts/tier_1_3b_empirical_validation.py`
- `/mnt/deepa/rag/scripts/tier_b_fallback.py`
- `/mnt/deepa/rag/scripts/tool_catalog.py`
- `/mnt/deepa/rag/scripts/verifiability_framework.py`
- `/mnt/deepa/rag/scripts/warm_council_pool.py`
- `/mnt/deepa/rag/scripts/whatsapp_fastapi_router.py`
- `/mnt/deepa/rag/scripts/whatsapp_webhook.py`
- `/mnt/deepa/rag/scripts/write_drill_status.py`


## 🧭 Where Does X Live? (cheat sheet)

Use this table when you're modifying this folder and need to know where new code goes.

| I want to... | Role | Touch these files |
|---|---|---|
| Add a new SQL query or DB call | 💾 repository / data access | `generate_folder_report.py`, `generate_folder_review_report.py`, `generate_production_review_report.py` |
| Add a new env var | ⚙ config / settings | `best_config_history.py`, `best_config_loader.py`, `promote_best_config.py` |
| Wrap a new external API | 🔌 external service adapter | `hyde_adapter.py`, `litellm_adapter.py`, `mcp_gateway.py` (+3 more) |
| Add a new agent / tool | 🤖 agent / tool | `agent_lead.py`, `agent_readiness_check.py`, `agent_router.py` (+10 more) |
| Add a new test | 🧪 test | `deep_rag_test.py`, `empirical_apply_test.py`, `smoke_test.py` |


## 3. C4 Model — Context / Container / Component / Code

### Level 1 — System Context

_Where does this folder sit in the broader system?_

```mermaid
flowchart LR
    Caller([External Caller]) --> This["scripts"]
    This --> libs_py[libs/py]
    This --> scripts_paperclip_manager[scripts/paperclip_manager]
    This --> app_eval_harness[app/eval_harness]
    This --> documind_core_kafka_client[documind_core/kafka_client]
    This --> scripts[scripts]
    This --> approval_agent[approval_agent]
```

### Level 2 — Container

_What external dependencies does this folder talk to?_

```mermaid
flowchart TB
    subgraph scripts
        Code[Source Code]
    end
    Code --> DB_0[("Elasticsearch")]
    Code --> DB_1[("Kafka (aiokafka)")]
    Code --> DB_2[("MongoDB (pymongo)")]
    Code --> DB_3[("Neo4j")]
    Code --> DB_4[("Qdrant")]
    Code --> DB_5[("Redis")]
    Code --> DB_6[("SQLAlchemy")]
    Code --> DB_7[("asyncpg")]
    Code --> DB_8[("psycopg")]
    Code --> AI_0{{LLM: Anthropic SDK}}
    Code --> AI_1{{LLM: DeepEval}}
    Code --> AI_2{{LLM: Giskard}}
    Code --> AI_3{{LLM: LangChain}}
    Code --> AI_4{{LLM: LangGraph}}
    Code --> AI_5{{LLM: Ollama}}
    Code --> AI_6{{LLM: OpenAI SDK}}
    Code --> AI_7{{LLM: OpenTelemetry GenAI}}
    Code --> AI_8{{LLM: Ragas}}
    Code --> AI_9{{LLM: Rebuff (PI defense)}}
```

### Level 3 — Component

_Internal files grouped by inferred role._

```mermaid
flowchart TB
    subgraph __module["📄 module"]
        advanced_healthcheck_py["advanced_healthcheck.py"]
        aiops_retrain_trigger_py["aiops_retrain_trigger.py"]
        append_drill_history_py["append_drill_history.py"]
        audit_readme_scores_py["audit_readme_scores.py"]
        audit_verify_py["audit_verify.py"]
        autonomous_fix_daemon_py["autonomous_fix_daemon.py"]
        more___module["... +85 more"]
    end
    subgraph __agent___tool["🤖 agent / tool"]
        agent_lead_py["agent_lead.py"]
        agent_readiness_check_py["agent_readiness_check.py"]
        agent_router_py["agent_router.py"]
        agent_task_board_py["agent_task_board.py"]
        agent_task_registry_py["agent_task_registry.py"]
        agentic_observability_audit_py["agentic_observability_audit.py"]
        more___agent___tool["... +7 more"]
    end
    subgraph __config___settings["⚙ config / settings"]
        best_config_history_py["best_config_history.py"]
        best_config_loader_py["best_config_loader.py"]
        promote_best_config_py["promote_best_config.py"]
    end
    subgraph __test["🧪 test"]
        deep_rag_test_py["deep_rag_test.py"]
        empirical_apply_test_py["empirical_apply_test.py"]
        smoke_test_py["smoke_test.py"]
    end
    subgraph __repository___data_access["💾 repository / data access"]
        generate_folder_report_py["generate_folder_report.py"]
        generate_folder_review_report_py["generate_folder_review_report.py"]
        generate_production_review_report_py["generate_production_review_report.py"]
    end
    subgraph __external_service_adapter["🔌 external service adapter"]
        hyde_adapter_py["hyde_adapter.py"]
        litellm_adapter_py["litellm_adapter.py"]
        mcp_gateway_py["mcp_gateway.py"]
        mcp_gateway_warmup_py["mcp_gateway_warmup.py"]
        pydanticai_adapter_py["pydanticai_adapter.py"]
        ragas_eval_adapter_py["ragas_eval_adapter.py"]
    end
```

### Level 4 — Code (top hotspots)

_Longest functions — these are the most likely refactor candidates._

```mermaid
flowchart TB
    local_council_py_611_run_local_council["run_local_council (337 lines)<br/>local_council.py:611"]
    run_gepa_empirical_py_177__stage3_compil["_stage3_compile (247 lines)<br/>run_gepa_empirical.py:177"]
    generate_folder_report_py_1713_section_c["section_code_logic_deep_dive (239 lines)<br/>generate_folder_report.py:1713"]
    generate_brutal_reviews_py_47_build_revi["build_review (238 lines)<br/>generate_brutal_reviews.py:47"]
    generate_specialized_assessment_py_540_r["render_backend (231 lines)<br/>generate_specialized_assessment.py:540"]
```


## 📐 Class Diagram (UML-style)

Top classes by method count, with inheritance arrows. Common framework bases (`BaseModel`, `BaseSettings`, `Exception`, `Enum`) use dotted lines.

```mermaid
classDiagram
    class NativeComputeWrapper {
        +8 methods
        ~native_compute_wrapper.py:95
    }
    class _ResourceTable {
        +4 methods
        ~run_drills.py:252
    }
    class AlertExpr {
        +3 methods
        ~council_filter_stats.py:98
    }
    class CouncilProposal {
        +3 methods
        ~council_schemas.py:66
    }
    BaseModel <|.. CouncilProposal
    class ToolCatalogEntry {
        +2 methods
        ~tool_catalog.py:66
    }
    class SearchAxes {
        +2 methods
        ~autorag_optimizer.py:86
    }
    class Fingerprint {
        +2 methods
        ~cache_fingerprint.py:81
    }
    class CouncilProgram {
        +2 methods
        ~dspy_optimizer.py:158
    }
    Module <|-- CouncilProgram
    class ChunkingStrategy {
        +1 methods
        ~chunking_strategy_selector.py:61
    }
    class ConfigPoint {
        +1 methods
        ~autorag_optimizer.py:65
    }
    class GatewayDecision {
        +1 methods
        ~mcp_gateway.py:62
    }
    class PromotionDecision {
        +1 methods
        ~promote_gepa_prompts.py:72
    }
    class EarnedReport {
        +1 methods
        ~stage3_earned_check.py:85
    }
    class PromotionDecision {
        +1 methods
        ~promote_best_config.py:70
    }
    class OllamaPolicyDenied {
        +1 methods
        ~local_council.py:157
    }
    RuntimeError <|-- OllamaPolicyDenied
```


_Showing top 15 of 127 classes (ranked by method count)._


## 4. Code Sequence — How Files Link to Each Other

**Import graph for files in this folder.** Reading order: start at any entry-point file (look for `🚀 entry point` role in the inventory above), then follow the arrows.

```mermaid
flowchart LR
    agent_lead_py["agent_lead.py"] --> rule_fix_strategy_py["rule_fix_strategy.py"]
    agent_router_py["agent_router.py"] --> local_council_py["local_council.py"]
    agent_router_py["agent_router.py"] --> event_publisher_py["event_publisher.py"]
    autonomous_fix_daemon_py["autonomous_fix_daemon.py"] --> agent_lead_py["agent_lead.py"]
    autorag_optimizer_py["autorag_optimizer.py"] --> ragas_eval_adapter_py["ragas_eval_adapter.py"]
    build_doc_framework_templates_py["build_doc_framework_templates.py"] --> doc_framework_registry_py["doc_framework_registry.py"]
    council_schemas_py["council_schemas.py"] --> pydanticai_adapter_py["pydanticai_adapter.py"]
    drain_outbox_py["drain_outbox.py"] --> paperclip_manager_py["paperclip_manager.py"]
    dspy_optimizer_py["dspy_optimizer.py"] --> gemma_agent_council_py["gemma_agent_council.py"]
    generate_tool_catalog_entries_py["generate_tool_catalog_entries.py"] --> tool_catalog_py["tool_catalog.py"]
    litellm_adapter_py["litellm_adapter.py"] --> policy_check_py["policy_check.py"]
    litellm_adapter_py["litellm_adapter.py"] --> local_council_py["local_council.py"]
    local_council_py["local_council.py"] --> council_schemas_py["council_schemas.py"]
    local_council_py["local_council.py"] --> rule_fix_strategy_py["rule_fix_strategy.py"]
    local_council_py["local_council.py"] --> policy_check_py["policy_check.py"]
    local_council_py["local_council.py"] --> litellm_adapter_py["litellm_adapter.py"]
    local_council_py["local_council.py"] --> prior_fix_rag_py["prior_fix_rag.py"]
    local_council_py["local_council.py"] --> agent_router_py["agent_router.py"]
    local_council_py["local_council.py"] --> tier_b_fallback_py["tier_b_fallback.py"]
    local_council_py["local_council.py"] --> hitl_framework_py["hitl_framework.py"]
    mcp_gateway_py["mcp_gateway.py"] --> policy_check_py["policy_check.py"]
    openclaw_coordinator_py["openclaw_coordinator.py"] --> policy_check_py["policy_check.py"]
    openclaw_coordinator_py["openclaw_coordinator.py"] --> event_publisher_py["event_publisher.py"]
    openclaw_coordinator_py["openclaw_coordinator.py"] --> mcp_gateway_py["mcp_gateway.py"]
    outbox_dispatcher_doctor_py["outbox_dispatcher_doctor.py"] --> paperclip_manager_py["paperclip_manager.py"]
    outbox_gc_py["outbox_gc.py"] --> paperclip_manager_py["paperclip_manager.py"]
    paperclip_dispatcher_py["paperclip_dispatcher.py"] --> openclaw_coordinator_py["openclaw_coordinator.py"]
    paperclip_dispatcher_py["paperclip_dispatcher.py"] --> paperclip_manager_py["paperclip_manager.py"]
    paperclip_manager_py["paperclip_manager.py"] --> agent_task_registry_py["agent_task_registry.py"]
    policy_check_py["policy_check.py"] --> event_publisher_py["event_publisher.py"]
    run_autorag_empirical_py["run_autorag_empirical.py"] --> autorag_optimizer_py["autorag_optimizer.py"]
    run_autorag_empirical_py["run_autorag_empirical.py"] --> promote_best_config_py["promote_best_config.py"]
    run_gepa_empirical_py["run_gepa_empirical.py"] --> dspy_optimizer_py["dspy_optimizer.py"]
    tier_1_3b_empirical_validation_py["tier_1_3b_empirical_validation.py"] --> local_council_py["local_council.py"]
    tier_b_fallback_py["tier_b_fallback.py"] --> council_schemas_py["council_schemas.py"]
    whatsapp_fastapi_router_py["whatsapp_fastapi_router.py"] --> whatsapp_webhook_py["whatsapp_webhook.py"]
    whatsapp_fastapi_router_py["whatsapp_fastapi_router.py"] --> pii_redactor_py["pii_redactor.py"]
    whatsapp_fastapi_router_py["whatsapp_fastapi_router.py"] --> gemma_agent_council_py["gemma_agent_council.py"]
```

### Edge list

| From file | To file | Import-count |
|---|---|---|
| `run_gepa_empirical.py` | `dspy_optimizer.py` | 5 |
| `whatsapp_fastapi_router.py` | `whatsapp_webhook.py` | 5 |
| `council_schemas.py` | `pydanticai_adapter.py` | 2 |
| `litellm_adapter.py` | `policy_check.py` | 2 |
| `local_council.py` | `agent_router.py` | 2 |
| `local_council.py` | `council_schemas.py` | 2 |
| `local_council.py` | `litellm_adapter.py` | 2 |
| `local_council.py` | `policy_check.py` | 2 |
| `mcp_gateway.py` | `policy_check.py` | 2 |
| `openclaw_coordinator.py` | `mcp_gateway.py` | 2 |
| `openclaw_coordinator.py` | `policy_check.py` | 2 |
| `paperclip_dispatcher.py` | `openclaw_coordinator.py` | 2 |
| `paperclip_manager.py` | `agent_task_registry.py` | 2 |
| `agent_lead.py` | `rule_fix_strategy.py` | 1 |
| `agent_router.py` | `event_publisher.py` | 1 |
| `agent_router.py` | `local_council.py` | 1 |
| `autonomous_fix_daemon.py` | `agent_lead.py` | 1 |
| `autorag_optimizer.py` | `ragas_eval_adapter.py` | 1 |
| `build_doc_framework_templates.py` | `doc_framework_registry.py` | 1 |
| `drain_outbox.py` | `paperclip_manager.py` | 1 |
| `dspy_optimizer.py` | `gemma_agent_council.py` | 1 |
| `generate_tool_catalog_entries.py` | `tool_catalog.py` | 1 |
| `litellm_adapter.py` | `local_council.py` | 1 |
| `local_council.py` | `hitl_framework.py` | 1 |
| `local_council.py` | `prior_fix_rag.py` | 1 |
| `local_council.py` | `rule_fix_strategy.py` | 1 |
| `local_council.py` | `tier_b_fallback.py` | 1 |
| `openclaw_coordinator.py` | `event_publisher.py` | 1 |
| `outbox_dispatcher_doctor.py` | `paperclip_manager.py` | 1 |
| `outbox_gc.py` | `paperclip_manager.py` | 1 |
| `paperclip_dispatcher.py` | `paperclip_manager.py` | 1 |
| `policy_check.py` | `event_publisher.py` | 1 |
| `run_autorag_empirical.py` | `autorag_optimizer.py` | 1 |
| `run_autorag_empirical.py` | `promote_best_config.py` | 1 |
| `tier_1_3b_empirical_validation.py` | `local_council.py` | 1 |
| `tier_b_fallback.py` | `council_schemas.py` | 1 |
| `whatsapp_fastapi_router.py` | `gemma_agent_council.py` | 1 |
| `whatsapp_fastapi_router.py` | `pii_redactor.py` | 1 |


## 5. Request Flowchart

Generic request lifecycle for this folder. Branches that don't apply are auto-removed based on detected dependencies (DB / cache / LLM).

```mermaid
flowchart TD
    Start([Request arrives]) --> Validate{{Validate input}}
    Validate -- invalid --> Err400[400 Bad Request]
    Validate -- ok --> Auth{{Auth + RBAC check}}
    Auth -- denied --> Err401[401/403]
    Auth -- ok --> Logic[Business logic]
    Logic --> CacheCheck{{Cache hit?}}
    CacheCheck -- yes --> Return[Return cached]
    CacheCheck -- no --> Compute[Compute / fetch]
    Compute --> DB[(Database)]
    DB --> Compute
    Compute --> LLM{{LLM / RAG call}}
    LLM --> Compute
    Compute --> Log[Emit log + metric + trace span]
    Log --> Return2[Return response]
    Err400 --> Log
    Err401 --> Log
```


## 6. API Endpoints — Input / Process / Output

**Detected endpoints:** 5

| Method | Route | Defined in | Input (schema) | Process (summary) | Output (schema) |
|---|---|---|---|---|---|
| `GET` | `/whatsapp` | `whatsapp_fastapi_router.py:79` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/whatsapp` | `whatsapp_fastapi_router.py:102` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/health` | `build_mcp_sdlc_batch.py:242` | _TBD_ | _TBD_ | _TBD_ |
| `GET` | `/tools/list` | `build_mcp_sdlc_batch.py:247` | _TBD_ | _TBD_ | _TBD_ |
| `POST` | `/tools/call` | `build_mcp_sdlc_batch.py:252` | _TBD_ | _TBD_ | _TBD_ |

_Reviewer fills the last three columns from the Pydantic models in the handler. Auto-extraction of Pydantic schemas is on the roadmap._


## 🏗 Input/Process/Output + Integration + Design Principles

### Input / Process / Output per endpoint

| Endpoint | INPUT (validation chain) | PROCESS (call chain) | OUTPUT (response chain) |
|---|---|---|---|
| `GET /whatsapp` | Pydantic schema validated at middleware | Router `whatsapp_fastapi_router.py:79` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `POST /whatsapp` | Pydantic schema validated at middleware | Router `whatsapp_fastapi_router.py:102` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /health` | Pydantic schema validated at middleware | Router `build_mcp_sdlc_batch.py:242` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `GET /tools/list` | Pydantic schema validated at middleware | Router `build_mcp_sdlc_batch.py:247` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |
| `POST /tools/call` | Pydantic schema validated at middleware | Router `build_mcp_sdlc_batch.py:252` → Service (`app/services/`) → Repository (`app/repositories/` or `documind_core/db_client.py`) → External (LLM / Vector / Kafka) | Pydantic response model serialized to JSON + headers (`X-Correlation-ID`, `X-Latency-ms`) |

### Integration sequence (ordered by import volume)

Other folders this one calls into, ordered by how heavily it depends on each:

```mermaid
sequenceDiagram
  autonumber
  participant This as scripts
  participant scripts_paperclip_manager as scripts/paperclip_manager
  participant approval_agent as approval_agent
  participant app_eval_harness as app/eval_harness
  participant documind_core_rebuff_detector as documind_core/rebuff_detector
  participant libs_py as libs/py
  participant documind_core_kafka_client as documind_core/kafka_client
  This->>scripts_paperclip_manager: call (~3 import sites)
  scripts_paperclip_manager-->>This: response
  This->>approval_agent: call (~3 import sites)
  approval_agent-->>This: response
  This->>app_eval_harness: call (~2 import sites)
  app_eval_harness-->>This: response
  This->>documind_core_rebuff_detector: call (~2 import sites)
  documind_core_rebuff_detector-->>This: response
  This->>libs_py: call (~1 import sites)
  libs_py-->>This: response
  This->>documind_core_kafka_client: call (~1 import sites)
  documind_core_kafka_client-->>This: response
```

### SOLID principles applied here

| Principle | Where it shows up in this folder |
|---|---|
| **S — Single Responsibility** | Each file has ONE role — routers route, services orchestrate, repos query, schemas describe. The §2 File Inventory shows the role per file; any file with multiple roles violates SRP. |
| **O — Open/Closed** | New endpoints add new router functions; new business cases add new service methods. Existing methods stay closed for modification. |
| **L — Liskov Substitution** | All adapter clients (Ollama / OpenAI / Anthropic) implement the same LLM-client protocol — they're interchangeable behind the circuit breaker. |
| **I — Interface Segregation** | Pydantic models split request, response, and internal state into separate schemas — no client gets a fat model with fields it doesn't use. |
| **D — Dependency Inversion** | Services receive their dependencies via FastAPI `Depends()` — they depend on abstractions (factories), not concrete repos. Swap implementations in tests via the `app.dependency_overrides` dict. |

### Microservice principles applied here

| Principle | Application |
|---|---|
| **Single business capability** | `scripts` owns ONE capability (see §1 Purpose). Cross-capability logic lives in other services. |
| **Bounded context** | Schemas + repositories are scoped to this service's bounded context — no shared DB tables with other services. |
| **DB per service** | Each service owns its tables. Cross-service reads go through HTTP or Kafka — never a direct DB join. |
| **Independent deploy** | Service is independently deployable — its container is built + released without coupling to other services. |
| **Resilience patterns** | Circuit breakers (`documind_core/breakers/`), retries with exponential backoff, bulkheads, timeouts on every external call. |
| **Observability** | Every request has a `request_id` propagated via OTel baggage; every external call emits a trace span. |

### Design-principle stack (how the principles compose)

Reading bottom-to-top — earlier principles enable later ones:

```text
┌─────────────────────────────────────────────────────────────┐
│ 7. AI Governance (§38 + §48): decision audit + explainability│
├─────────────────────────────────────────────────────────────┤
│ 6. Production Gates (§47.11): 10 gates BEFORE deploy        │
├─────────────────────────────────────────────────────────────┤
│ 5. Resilience: CB + retry + bulkhead + timeout              │
├─────────────────────────────────────────────────────────────┤
│ 4. Microservice: single capability, bounded context, DB/svc │
├─────────────────────────────────────────────────────────────┤
│ 3. SOLID: SRP + OCP + LSP + ISP + DIP                       │
├─────────────────────────────────────────────────────────────┤
│ 2. 12-factor: stateless, deps in venv, config in env        │
├─────────────────────────────────────────────────────────────┤
│ 1. KISS / YAGNI / DRY: every line earns its place           │
└─────────────────────────────────────────────────────────────┘
```

**How to use this stack:** when adding a new feature, check it from the bottom up. KISS first (simplest design that works), then SOLID (does any class violate SRP?), then microservice (does this leak the bounded context?), then resilience (what fails when the downstream is slow?), then gates (which production gate enforces this?), then governance (which audit row records this decision?).


## 🔬 Execution Sequence + Debug Tap Points

For each phase a request goes through, this section shows: **(1)** the file:line where it happens, **(2)** the log line you'll see, **(3)** the command to inspect that phase's output in real time. Use this as your debug-flow chart — start at Phase 0, move down until output stops matching the expected log line; that's where the failure is.

**Worked example:** `GET /whatsapp` (whatsapp_fastapi_router.py:79)

### Phase-by-phase debug tap table

| # | Phase | Code location | Log line to grep | Command to inspect |
|---|---|---|---|---|
| 0 | **TCP connect** | OS / docker network | `client_connected` | `curl -v http://localhost:8000/health 2>&1 \| head -15` |
| 1 | **Middleware: request_id assign** | `documind_core/middleware.py` | `request_id=...` | `docker logs documind-scripts -f \| grep request_id` |
| 2 | **Middleware: auth** | `documind_core/auth.py` | `auth_ok` or `auth_denied` | `docker logs documind-scripts -f \| grep auth_` |
| 3 | **Middleware: tenant resolution** | `documind_core/middleware.py` | `tenant_id=<id>` | `docker logs documind-scripts -f \| grep tenant_id` |
| 4 | **Pydantic validation** | `app/schemas/*.py` | `422 Unprocessable` (on fail) | `docker logs documind-scripts -f \| grep -E 'validation\|422'` |
| 5 | **Router dispatch** | `whatsapp_fastapi_router.py:79` | `GET /whatsapp` | `docker logs documind-scripts -f \| grep '/whatsapp'` |
| 6 | **Business service call** | `app/services/*.py` | `service_method_start` | `docker logs documind-scripts -f \| grep service_` |
| 7 | **DB query** | `app/repositories/*.py` or `documind_core/db_client.py` | `asyncpg.execute` or `SELECT...` | `docker logs documind-postgres -f \| grep -E 'duration:'` |
| 8 | **External call (LLM / vector)** | `app/services/*_client.py` | `llm_call_start` / `vector_search_start` | `docker logs documind-scripts -f \| grep -E 'llm_\|vector_'` |
| 9 | **Decision audit log** | `documind_core/ai_governance.py` | `decision_audit:` | `psql -p 55432 -U documind -c "SELECT * FROM decision_audit ORDER BY ts DESC LIMIT 1;"` |
| 10 | **Response shaping** | `app/schemas/*.py` (response model) | `response_ms=` | `docker logs documind-scripts -f \| grep response_ms` |
| 11 | **Trace span flush** | OTel exporter | _(async)_ | Open Jaeger UI: `http://localhost:16686/search?service=scripts` |

### Reproducible end-to-end trace

Use this script to fire ONE request and see every phase's output in a single terminal:

```bash
REQ_ID=$(uuidgen)
echo "=== Issuing GET /whatsapp with request_id=$REQ_ID ==="

# Phase 0-2: tail logs in background
docker logs documind-scripts --tail=0 -f 2>&1 | grep --line-buffered "$REQ_ID" &
TAIL_PID=$!
sleep 0.5

# Phase 3-10: fire the request
curl -X GET http://localhost:8000/whatsapp \
  -H "X-Correlation-ID: $REQ_ID" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{}' -w "\nTOTAL=%{time_total}s\n"

sleep 2  # let logs flush
kill $TAIL_PID

# Phase 9: pull the decision audit row
psql -h localhost -p 55432 -U documind -d documind \
  -c "SELECT request_id, model_version, prompt_version, decision, confidence FROM decision_audit WHERE request_id='$REQ_ID';"

# Phase 11: pull the trace span tree
open "http://localhost:16686/search?service=scripts&tags=%7B%22request_id%22%3A%22$REQ_ID%22%7D"
```

### Debug-order checklist (when something breaks)

Walk the phases IN ORDER — first phase with missing/wrong output is the failure point. Don't skip ahead:

1. **Phase 0 fail?** Service not running → `bash scripts/circuitrag-status.sh`
2. **Phase 1-3 fail?** Middleware misconfigured → check env vars + middleware order in `main.py`
3. **Phase 4 fail (422)?** Request body doesn't match schema → check Pydantic model in `app/schemas/`
4. **Phase 5 fail (404)?** Route not registered → check router import in `main.py`
5. **Phase 6 fail (500)?** Business logic exception → tail logs for stack trace
6. **Phase 7 fail?** DB unreachable → `psql -p 55432 -U documind -c "SELECT 1;"`
7. **Phase 8 fail?** External dep down → check `/health/upstreams` + circuit breaker state
8. **Phase 9 missing?** Decision audit not persisted → check Kafka consumer lag
9. **Phase 10 slow?** Response shaping bottleneck → profile the response model
10. **Phase 11 empty Jaeger?** OTel exporter misconfigured → check `OTEL_EXPORTER_OTLP_ENDPOINT`


## 🔬 Code Logic Deep Dive — Variables / DSA / Memory / Pseudocode

Auto-extracted from the hottest file in this folder: **`generate_folder_report.py`** (3127 LOC, 7 classes, 68 functions).

### Module-level variables (state map)

| Variable | Type | Mutability |
|---|---|---|
| `REPO_ROOT` | `_inferred_` | immutable |
| `IGNORE_DIRS` | `_inferred_` | ⚠ MUTABLE set |
| `CODE_EXTS` | `_inferred_` | ⚠ MUTABLE set |
| `API_DECORATOR_PATTERNS` | `_inferred_` | ⚠ MUTABLE list |
| `API_ENDPOINT_PYTHON` | `_inferred_` | immutable |
| `DB_CALL_PATTERNS` | `_inferred_` | ⚠ MUTABLE list |
| `SANITIZATION_PATTERNS` | `_inferred_` | ⚠ MUTABLE list |
| `SMELL_PATTERNS` | `_inferred_` | ⚠ MUTABLE list |
| `CONCURRENCY_PATTERNS` | `_inferred_` | ⚠ MUTABLE dict |
| `CACHE_PATTERNS` | `_inferred_` | ⚠ MUTABLE dict |
| `DB_LIB_PATTERNS` | `_inferred_` | ⚠ MUTABLE dict |
| `AI_PATTERNS` | `_inferred_` | ⚠ MUTABLE dict |
| `SERVICE_PORT_MAP` | `_inferred_` | ⚠ MUTABLE dict |

### Data structures + algorithms detected in `generate_folder_report.py`

- functools.lru_cache (memoization)
- sort / sorted (sorting algorithm)
- set comprehension
- dict comprehension
- generator expression
- recursion (function calls itself)

### Memory characteristics

- ⚠ Module-level `_cache = {}` detected — unbounded growth risk. Use `functools.lru_cache(maxsize=N)` or `OrderedDict` with explicit eviction.
- ✓ `with open(...)` context manager used — file handles auto-closed.
- ℹ `BytesIO` / `StringIO` used — in-memory buffer; verify size bounded.
- ℹ `@dataclass` used — instances are mutable by default; consider `frozen=True` if immutability needed.
- ℹ `asyncio.create_task()` used — keep a reference to prevent GC; use TaskGroup or explicit set for fire-and-forget tasks.

### Pseudocode for hottest function: `section_code_logic_deep_dive` (generate_folder_report.py:1713, 239 lines)

```text
FUNCTION section_code_logic_deep_dive(f):
   1. [CALL/EXPR] 'Variables / DSA / memory / pseudocode for the hottest service file.\n\n    AST-
   2. [BRANCH] if not f.files:
   3. [ASSIGN] service_files = [fe for fe in f.files if '🧠 business service' in fe.role or '🌐 H
   4. [BRANCH] if not service_files:
   5. [ASSIGN] target = max(service_files, key=lambda fe: fe.lines)
   6. [ASSIGN] target_path = REPO_ROOT / f.rel_path / target.rel
   7. [BRANCH] if not target_path.exists():
   8. [TRY] try:
   9. [TRY] try:
  10. [TYPED-ASSIGN] module_vars: List[Tuple[str, str, str]] = []
  11. [LOOP] for node in tree.body:
  12. [ASSIGN] dsa_signals = {'collections.defaultdict': ['\\bdefaultdict\\('], 'collections.Co
  13. [TYPED-ASSIGN] dsa_hits: List[str] = []
  14. [LOOP] for name, patterns in dsa_signals.items():
  15. [LOOP] for node in ast.walk(tree):
  16. [TYPED-ASSIGN] memory_hints: List[str] = []
  17. [BRANCH] if re.search('_cache\\s*=\\s*\\{\\}', text) or re.search('_cache\\s*:\\s*dict\\[
  18. [BRANCH] if re.search('with open\\(', text):
  19. [BRANCH] if re.search('open\\(', text) and (not re.search('with open\\(', text)):
  20. [BRANCH] if 'BytesIO' in text or 'StringIO' in text:
  ... +18 more statements truncated
```

### Reading this section

- **Module-level variables** are loaded ONCE per process. `⚠ MUTABLE` warns of state shared across requests — guard with locks or use request-scoped storage.
- **DSA detected** tells you what algorithmic patterns are in play (hash maps, priority queues, recursion). Use this to predict complexity at scale.
- **Memory characteristics** flag the leak / unbounded-growth patterns that fail under load.
- **Pseudocode** is an AST-projected outline of the hottest function. Walk it top-to-bottom to understand the control flow before reading the real source.


## 7. Sequence Diagrams per Endpoint

### Generic flow (all endpoints)

```mermaid
sequenceDiagram
  autonumber
  participant Client
  participant API as scripts
  participant MW as Middleware (auth + logging)
  participant Svc as Business Service
  participant DB as Database
  Client->>API: HTTP request
  API->>MW: pass through
  MW-->>API: validated + auth ok
  API->>Svc: call handler
  Svc->>DB: read / write
  DB-->>Svc: result
  Svc-->>API: domain object
  API-->>Client: JSON response
  Note over API: emit log + metric + span
```

### Per-endpoint sequence stubs (top 5)

### `GET /whatsapp` (whatsapp_fastapi_router.py:79)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (whatsapp_fastapi_router.py:79)
  participant S as Service
  participant D as DB / external
  C->>H: GET /whatsapp
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /whatsapp` (whatsapp_fastapi_router.py:102)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (whatsapp_fastapi_router.py:102)
  participant S as Service
  participant D as DB / external
  C->>H: POST /whatsapp
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `GET /health` (build_mcp_sdlc_batch.py:242)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (build_mcp_sdlc_batch.py:242)
  participant S as Service
  participant D as DB / external
  C->>H: GET /health
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `GET /tools/list` (build_mcp_sdlc_batch.py:247)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (build_mcp_sdlc_batch.py:247)
  participant S as Service
  participant D as DB / external
  C->>H: GET /tools/list
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```

### `POST /tools/call` (build_mcp_sdlc_batch.py:252)

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant H as Handler (build_mcp_sdlc_batch.py:252)
  participant S as Service
  participant D as DB / external
  C->>H: POST /tools/call
  H->>S: validated payload
  S->>D: read/write
  D-->>S: result
  S-->>H: domain object
  H-->>C: response
```


## 🔬 Annotated Example Request

Walk through what happens when a client calls **`GET /whatsapp`** (whatsapp_fastapi_router.py:79).

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Client sends HTTP request                                        │
│    GET /whatsapp                                                   │
│    Headers: Authorization, X-Correlation-ID, X-Tenant-ID            │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Middleware stack (auth → logging → tracing → rate-limit)         │
│    - Validate JWT / API key                                         │
│    - Resolve tenant_id from token                                   │
│    - Start span; inject request_id into baggage                     │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Pydantic validation                                              │
│    - Parse request body against schema                              │
│    - 422 on validation error (with field-level details)             │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Router handler                                                   │
│    whatsapp_fastapi_router.py:79
│    - Receive validated request + injected Depends()                 │
│    - Delegate to business service                                   │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Business service                                                 │
│    - Apply rules / orchestrate multi-step logic                     │
│    - Call repositories for DB I/O                                   │
│    - Call external services (LLM / vector DB / etc.)             │
│    - Emit metrics + log decision audit row                          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. Response shaping                                                 │
│    - Build response Pydantic model                                  │
│    - Serialize to JSON                                              │
│    - Add correlation_id, latency_ms to headers                      │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
                       Client
```

### Inspecting this in real time

```bash
# 1. Tail the service log
docker logs documind-scripts --tail=20 -f &

# 2. Issue the request with a fresh correlation_id
REQ_ID=$(uuidgen)
curl -X GET http://localhost:<PORT>/whatsapp \
  -H "X-Correlation-ID: $REQ_ID" \
  -H "Authorization: Bearer <token>" \
  -d '{}'

# 3. Find the trace in Jaeger
open http://localhost:16686/search?service=scripts&tags=%7B%22request_id%22%3A%22$REQ_ID%22%7D
```


## 8. Database Layer

**DB / storage libraries:** Elasticsearch, Kafka (aiokafka), MongoDB (pymongo), Neo4j, Qdrant, Redis, SQLAlchemy, asyncpg, psycopg

**Total DB call sites:** 110

| Pattern | Count |
|---|---|
| `execute` | 26 |
| `fetch/fetchall/fetchrow` | 34 |
| `ORM query` | 1 |
| `ORM CRUD` | 41 |
| `MongoDB` | 8 |

### Query Optimization checklist

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Indexes on every WHERE / ORDER BY column | — | EXPLAIN ANALYZE hot paths |
| Full table scans avoided | — | — |
| Batch operations used (not N writes in a loop) | — | — |
| Parameterized queries (NEVER f-string SQL) | — | — |

### Transactions (ACID)

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Transaction boundaries narrow (no HTTP / LLM inside) | — | — |
| Rollback on exception | — | — |
| Isolation level documented (READ COMMITTED / SERIALIZABLE) | — | — |
| Deadlock prevention strategy | — | — |

### N+1 Query Findings (reviewer to fill)

| Endpoint / Function | Suspect Loop | Est. Queries / Request | Fix |
|---|---|---|---|
| — | — | — | — |


## 9. Code Quality + Complexity

### Readability

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Clear variable / function / class names | — | — |
| No misleading naming (no `tmp` / `xyz` / `foo`) | — | — |
| Small focused functions (≤ 50 lines) | — | 5 > 50 lines (see Section 0) |
| Avoid deeply nested conditions (≤ 4 levels) | — | — |

### Clean code

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| No dead / commented-out code | — | — |
| No `print()` — use logger | — | — |
| No hardcoded values | — | smell count: 138 |
| Constants extracted to a settings module | — | — |

### Complexity

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Long methods broken down | — | — |
| No overengineering (premature abstractions) | — | — |
| Cyclomatic complexity ≤ 15 per function | — | run `ruff complexity` or `radon` |


## 10. Security Review

### Authentication & Authorization

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Authentication implemented correctly | — | Bearer / JWT / session |
| Authorization (RBAC / ABAC) checks | — | no client-side trust |
| Tokens validated server-side every request | — | rotate, expire, revoke |

### OWASP Top 10

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Request validation present | — | sanitization: Manual escape, Pydantic BaseModel, Pydantic validator, Zod (TS) |
| SQL injection prevention | — | DB libs: Elasticsearch, Kafka (aiokafka), MongoDB (pymongo), Neo4j, Qdrant, Redis, SQLAlchemy, asyncpg, psycopg — parameterized queries only |
| XSS / CSRF prevention | — | output encoding / CSP / SameSite |
| Path traversal prevention | — | no user input concatenated to file paths |
| Prompt injection prevention | — | Rebuff / output filter |

### Secret Management

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| No secrets in code | — | smell count: 1 password literals, 1 api key literals |
| Env vars / Vault used | — | Pydantic BaseSettings or env reader |
| Secret rotation strategy | — | documented in runbook |

### Sensitive Data

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| PII masked in logs | — | structured logger with field redaction |
| Encryption in transit (TLS) | — | — |
| Encryption at rest (DB / object store) | — | — |
| GDPR — retention + right-to-be-forgotten | — | — |


## 11. Performance Review

### Memory

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Large object retention avoided | — | — |
| Streaming for large files / data | — | — |
| Caches bounded (LRU / TTL) | — | caching: functools.cache, in-memory @lru_cache, redis |

### Concurrency

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Thread safety validated | — | primitives: Lock / RLock, asyncio (async/await), concurrent.futures, threading |
| Race conditions prevented | — | — |
| Deadlocks avoided (lock ordering) | — | — |
| Parallel processing where beneficial | — | 42 async fns |

### Latency

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| External API calls batched / cached | — | — |
| Timeouts on every external call | — | — |
| No blocking I/O inside async functions | — | — |


## 12. Reliability & Observability

### Failure Handling

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Retry (bounded + exp backoff + jitter) | — | — |
| Circuit breaker around external deps | — | — |
| Graceful degradation | — | — |

### Timeout Handling

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Timeout on every external call (HTTP / DB / subprocess) | — | — |
| No infinite waits | — | — |

### Observability

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Structured (JSON) logging | — | correlation_id + tenant_id + request_id |
| Metrics (RED: rate / errors / duration) | — | — |
| Tracing (OpenTelemetry → Jaeger / Tempo) | — | — |
| Baggage propagation across services | — | — |


## 13. Test Cases

**Test files detected:** 3
_No `test_*` functions parsed via AST. Either tests live elsewhere or names don't match the `test_*` convention._


## 14. Logging & Monitoring

### Logging

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Structured (JSON) logs | — | — |
| Correlation ID present | — | — |
| No PII / secrets in log lines | — | — |
| No excessive logging (no logs in hot loops) | — | — |

### Monitoring

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Alerts defined (SLO-burn aware) | — | — |
| Dashboards exist (Grafana) | — | — |
| On-call playbook references | — | — |


## 15. LLM / GenAI / RAG

**Detected AI deps:** Anthropic SDK, DeepEval, Giskard, LangChain, LangGraph, Ollama, OpenAI SDK, OpenTelemetry GenAI, Ragas, Rebuff (PI defense)

### Prompt Safety

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Prompt injection handling (input filter) | — | Rebuff |
| Output sanitization | — | — |
| Prompt versioning in registry | — | — |
| Toxicity / bias filtering | — | — |

### RAG Quality

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Chunking strategy validated (size + overlap) | — | — |
| Embedding model versioned (re-embed on bump) | — | — |
| Vector DB query optimized (recall@k measured) | — | — |
| Metadata filtering exists (per-tenant) | — | — |

### Cost

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Model fallback strategy defined | — | — |
| Token usage minimized (cache / truncation) | — | — |
| Per-tenant cost ceiling enforced | — | — |

### Explainability / Responsible AI

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Citation / source grounding (every claim cited) | — | — |
| Confidence scoring (Ragas / DeepEval) | — | Ragas |
| Decision audit row per prediction (§48) | — | — |
| Fairness / bias checks | — | — |


## 16. SOLID + Microservice Principles

### SOLID

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| S — Single Responsibility (one reason to change per class) | — | — |
| O — Open/Closed (extend via composition, not modification) | — | — |
| L — Liskov Substitution (subclasses honor contracts) | — | — |
| I — Interface Segregation (no fat interfaces) | — | — |
| D — Dependency Inversion (depend on abstractions) | — | — |

### Microservice

| Check | Status (✓/✗/⚠) | Notes |
|---|---|---|
| Single business capability | — | — |
| Bounded context (no domain bleed) | — | — |
| Independent deploy (no coupled releases) | — | — |
| Resilience patterns (CB / retry / bulkhead) | — | — |


## 17. Integration with Other Folders

### Internal — other folders in this repo

| Folder / Module | Import-count | Purpose |
|---|---|---|
| `scripts/paperclip_manager` | 3 | _reviewer-described_ |
| `approval_agent` | 3 | _reviewer-described_ |
| `app/eval_harness` | 2 | _reviewer-described_ |
| `documind_core/rebuff_detector` | 2 | _reviewer-described_ |
| `libs/py` | 1 | _reviewer-described_ |
| `documind_core/kafka_client` | 1 | _reviewer-described_ |
| `scripts` | 1 | _reviewer-described_ |
| `documind_core` | 1 | _reviewer-described_ |
| `app/agents` | 1 | _reviewer-described_ |
| `app/langgraph_flow` | 1 | _reviewer-described_ |
| `app/models` | 1 | _reviewer-described_ |

### External — third-party packages

| Package | Import-count |
|---|---|
| `urllib` | 29 |
| `asyncpg` | 22 |
| `importlib` | 17 |
| `yaml` | 13 |
| `httpx` | 8 |
| `policy_check` | 8 |
| `dspy` | 7 |
| `pydantic` | 6 |
| `sqlite3` | 5 |
| `ragas` | 5 |
| `dspy_optimizer` | 5 |
| `whatsapp_webhook` | 5 |
| `opentelemetry` | 4 |
| `local_council` | 3 |
| `event_publisher` | 3 |
| `langfuse` | 3 |
| `litellm` | 3 |
| `council_schemas` | 3 |
| `pydantic_ai` | 3 |
| `rule_fix_strategy` | 2 |


## 📖 Domain Glossary

Project-wide vocabulary a new developer needs. If you see a term in code you don't recognize, check here first.

| Term | Definition |
|---|---|
| **RAG** | Retrieval-Augmented Generation — the pattern of grounding LLM output in retrieved documents to reduce hallucination. |
| **Chunk** | A token-bounded slice of a source document (typically 256–1024 tokens with 10–20% overlap). Embedded + stored in the vector DB. |
| **Embedding** | Vector representation of text. Re-embed everything when the embedding model version bumps. |
| **Vector DB** | Qdrant in this project. Stores chunk embeddings + metadata, returns top-k by cosine similarity. |
| **Rerank** | Second-stage retrieval — re-scores the top-k from the vector DB with a more expensive cross-encoder for better relevance. |
| **Hybrid retrieval** | Vector + keyword (Elasticsearch / BM25) merged via reciprocal-rank-fusion. |
| **MCP** | Model Context Protocol — tool-server contract used by agents to call namespace-scoped operations (drill / ingest / etc.). |
| **Tenant** | A logical customer boundary. Every row + every cache key + every prompt context is tenant-scoped. |
| **Drill** | A runnable script that exercises real services + asserts ≥3 negative invariants (per §43). Lives under `mcp/tests/drill_*.py`. |
| **Breaker** | Circuit breaker — opens after N failures to a downstream dep, lets traffic shed instead of cascading. See `documind_core/breakers/`. |
| **Baggage** | OpenTelemetry context (request_id / tenant_id / actor) propagated across spans + service hops. |
| **Decision audit row** | Per-AI-call record persisted to Postgres with request_id, prompt_version, model_version, output, confidence, fairness_flag — per §38 + §48. |
| **Fanout** | Parallel sub-query split for multi-hop RAG (`services/inference-svc/app/agents/multi_hop_fanout.py`). |
| **Council** | 3-model author + reviewer + advisor pattern for code-fix proposals (per §50). |
| **Side-channel port** | Separate Prometheus `/metrics` port (9465–9470) per service to avoid app-port middleware interference. |
| **Trust scorecard** | 5-layer aggregate (governance + tool review + maturity stack + drill catalog + production gates) used for go/no-go. |
| **HBR** | High-Blast-Radius — file patterns that force the pre-commit hook to refresh the drill catalog. |
| **HITL** | Human-In-The-Loop — escalation path when confidence falls in the 0.5–0.8 range (per §40). |
| **Forensic substrate** | The §51-required metadata block (Date/Location/Approach/Policies/Verification) in every commit body. |


## 18. Debugging Guide

### Step-by-step when something breaks

```
1. Tail logs:        tail -50 /tmp/scripts.log   (if host-side)
                     docker logs documind-scripts --tail=50   (if container)
2. Health probe:     curl http://localhost:<PORT>/health
3. Fleet probe:      python3 scripts/advanced_healthcheck.py --layer app
4. Trace:            Open Jaeger → search request_id → see span tree
5. Metrics:          Open Grafana → service dashboard → look for spike
6. Drill:            ls mcp/tests/drill_*scripts*.py and run
```

### Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| 502 / connection refused | service down | check `circuitrag-status.sh` |
| Slow p95 latency | DB N+1 or LLM throttle | Section 8 + Section 15 |
| 5xx spike | downstream dep down | check `/health/upstreams` |
| Memory growth | unbounded cache or closure leak | Section 11 |
| Wrong-tenant data | RLS bypass | tenant isolation drill |


## 📅 Recent Activity & Open TODOs

### Last 8 commits touching this folder

| Hash | Date | Subject |
|---|---|---|
| `551405a` | 2026-05-16 | docs: regen_all_docs.sh orchestrator + complete README/REPORT regen pass |
| `0211a6c` | 2026-05-16 | docs(reports): rename to *_ASSESSMENT_REPORT.md + Code Logic Deep Dive section |
| `15eca63` | 2026-05-16 | docs(reports): frontend + backend specialized assessments + drill fix |
| `77409b7` | 2026-05-16 | docs(reports): FOLDER_REPORT.md alongside README.md per two-file convention |
| `91a5efe` | 2026-05-16 | docs(readme): enterprise 20-section root README per spec #1 |
| `3634fb7` | 2026-05-16 | docs(audit): readme audit scoreboard + drill — honest §57.7 baseline |
| `4068a70` | 2026-05-16 | docs(readme): audit checklist + drill_readme_generator + sidecar fold-in |
| `5ecd9be` | 2026-05-16 | docs(readme): 11 more sections for new-dev onboarding + bugfixes |

```bash
git log --oneline -- scripts    # see all commits
git blame <file>                       # who wrote what
```

### Open TODO / FIXME / HACK markers

#### TODO (6)

| Location | Note |
|---|---|
| `aiops_retrain_trigger.py:143` | inject kafka producer + webhook client (keep this script |
| `generate_folder_report.py:190` | / FIXME / HACK / XXX |
| `generate_folder_report.py:1275` | / FIXME / HACK markers\n\n") |
| `generate_folder_report.py:1291` | / FIXME / HACK markers\n\n" |
| `generate_folder_report.py:1292` | / FIXME markers found — folder is hygienic._\n\n" |
| `build_doc_framework_templates.py:310` | define sections for {d.doc_type})\n" |

#### FIXME (5)

| Location | Note |
|---|---|
| `generate_folder_report.py:105` | marker"), |
| `generate_folder_report.py:2741` | hygiene (≤ 5 markers) |
| `generate_folder_report.py:2742` | marker", 0) |
| `generate_folder_report.py:2744` | markers") |
| `generate_folder_report.py:2746` | markers (acceptable)") |

#### HACK (1)

| Location | Note |
|---|---|
| `production-checker.js:169` | markers in production code', |

#### XXX (1)

| Location | Note |
|---|---|
| `replay_action_draft.py:27` | \\ |


## 19. Production Gates (hard pass/fail)

| Gate | Target | Status | Evidence |
|---|---|---|---|
| Code coverage ≥ 80% | statements + branches | — | — |
| Naming convention enforced | ruff / eslint | — | — |
| Zero critical CVEs | Trivy / Bandit | — | — |
| No hardcoded secrets | gitleaks | — | — |
| No memory leaks | bounded caches | — | smells: 138 |
| No N+1 queries | hot paths reviewed | — | 110 DB call sites |
| All APIs validated | Pydantic / Zod | — | sanitization: Manual escape, Pydantic BaseModel, Pydantic validator, Zod (TS) |
| Duplicate logic eliminated | DRY check | — | — |
| Structured logging with correlation_id | — | — | — |
| Distributed tracing wired | OpenTelemetry | — | — |
| For AI: prompt injection tested | Rebuff / Garak | — | AI deps present |
| For AI: hallucination scoring ≥ 0.85 | Ragas faithfulness | — | yes |


## 📋 Reporting + Audit Checklist (10 categories × 10 rows)

**Honesty contract per §57.7:** sections that are deterministically auto-generated AND covered by a drill are pre-scored 10/10. Sections that require human judgment start at **TBD** — never auto-mark them as ✓ without evidence.

Aggregate score = sum of all 100 row scores. Target ≥ 80 for production. Each cell: ✓ (10) / ⚠ (5) / ✗ (0) / TBD.

### 1. Architecture & Design (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | C4 L1 Context diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 2 | C4 L2 Container diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 3 | C4 L3 Component diagram present | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 4 | C4 L4 Code (longest functions) | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §7 |
| 5 | ADR filed for major design decisions | TBD | `docs/architecture/adr/` |
| 6 | Bounded context documented | TBD | reviewer notes |
| 7 | Separation of concerns enforced | TBD | review §2 File Inventory roles |
| 8 | Class diagram (UML) present | **10** | ✓ §8 |
| 9 | Sequence diagram per endpoint | **10** | ✓ §15 |
| 10 | Integration graph documented | **10** | ✓ §27 |

### 2. Code Quality (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | File inventory with roles | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §5 |
| 2 | Longest-functions list | **10** | ✓ §0 |
| 3 | No function > 50 lines without justification | TBD | `radon cc -a -nc` |
| 4 | Cyclomatic complexity ≤ 15 per fn | TBD | `radon cc -nc` |
| 5 | No file > 500 lines without sub-modules | TBD | `wc -l` per file |
| 6 | Linted (ruff/eslint, zero warnings) | TBD | CI log |
| 7 | Type-checked (mypy/ts-strict) | TBD | CI log |
| 8 | No dead code (vulture / unused exports) | TBD | reviewer audit |
| 9 | DRY — no duplicate logic across files | TBD | reviewer audit |
| 10 | KISS — simplest design that works | TBD | reviewer judgment |

### 3. Security (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Input validation present (Pydantic/Zod) | **10** if detected | §20 — detected: Manual escape, Pydantic BaseModel, Pydantic validator, Zod (TS) |
| 2 | AuthN enforced (Depends-based) | TBD | — |
| 3 | OWASP Top 10 reviewed | TBD | STRIDE table per container |
| 4 | No hardcoded secrets | TBD | — |
| 5 | Secrets in Vault / env, not code | TBD | §4 Env Vars |
| 6 | SAST scan clean (bandit/semgrep) | TBD | CI log |
| 7 | Dependency CVE scan clean (pip-audit) | TBD | CI log |
| 8 | PII masked in logs | TBD | §24 |
| 9 | TLS / encryption in transit | TBD | infra config |
| 10 | For AI: prompt injection defense | **10** | Rebuff detected |

### 4. Performance (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Latency SLO documented | TBD | reviewer |
| 2 | Load tested (k6/Locust) | TBD | `tests/load/` |
| 3 | p95 measured + within SLO | TBD | Grafana panel |
| 4 | Pagination on list endpoints | TBD | — |
| 5 | Caches bounded (LRU/TTL) | **10** | detected: functools.cache, in-memory @lru_cache, redis |
| 6 | Async I/O where applicable | **10** | 42 async functions detected |
| 7 | Timeouts on all external calls | **10** | ✓ timeout= or asyncio.wait_for — detected at `aiops_retrain_trigger.py:114` |
| 8 | Memory profile clean (no growth) | TBD | py-spy / mprof |
| 9 | Capacity model documented | TBD | runbook |
| 10 | Cost per request tracked (token/cpu) | TBD | finops dashboard |

### 5. Reliability (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Retry with exp backoff | TBD | reviewer audit |
| 2 | Circuit breaker on external deps | **10** | ✓ CircuitBreaker wired — detected at `native_compute_wrapper.py:37` |
| 3 | Graceful degradation path | TBD | reviewer audit |
| 4 | Health probe (startup/liveness/readiness) | **10** | ✓ `/health` endpoint — detected at `build_mcp_sdlc_batch.py:242` |
| 5 | Rollback tested in staging | TBD | deploy runbook |
| 6 | DR plan with RTO/RPO | TBD | runbook |
| 7 | Idempotency keys for writes | TBD | reviewer audit |
| 8 | Dead-letter queue for events | TBD | Kafka config |
| 9 | Bulkhead isolation | TBD | reviewer audit |
| 10 | Chaos test passed | TBD | chaos run log |

### 6. Observability (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Execution sequence with debug taps | **10** | ✓ §13 |
| 2 | Business-logic step sequence | **10** | ✓ §14 |
| 3 | Structured JSON logs | **10** | ✓ structured logger — detected at `generate_specialized_assessment.py:278` |
| 4 | correlation_id propagated everywhere | **10** | ✓ correlation_id used — detected at `generate_folder_report.py:1200` |
| 5 | Tracing (OTel) wired | **10** | ✓ OTel imported — detected at `scenario_batch_and_inference.py:509` |
| 6 | Metrics exposed (RED: rate/errors/duration) | **10** | ✓ Prometheus instrumentation — detected at `generate_mesh_manifests.py:97` |
| 7 | Grafana dashboard exists | TBD | dashboard URL |
| 8 | Alerts defined (SLO burn) | TBD | Alertmanager config |
| 9 | Runbook references | TBD | `ops/runbook/<svc>.md` |
| 10 | Decision audit row per AI call (§38+§48) | **10** | ✓ decision_audit ref — detected at `generate_folder_report.py:1666` |

### 7. Testing (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Test files detected | **10** | 3 test files |
| 2 | Test cases auto-parsed | TBD | 0 test functions |
| 3 | Statement coverage ≥ 80% | TBD | `pytest --cov` |
| 4 | Branch coverage ≥ 70% | TBD | `pytest --cov-branch` |
| 5 | Negative-test cases (≥3 per drill) | TBD | §43 discipline |
| 6 | Drill with real services (no mocks) | TBD | `mcp/tests/drill_*.py` |
| 7 | Property-based tests (hypothesis) | TBD | reviewer audit |
| 8 | Fuzz tests (atheris/honggfuzz) | TBD | reviewer audit |
| 9 | Contract tests with downstream services | TBD | reviewer audit |
| 10 | Smoke + load + chaos in CI | TBD | CI pipeline |

### 8. Operations (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Quick Start (5-cmd boot) | **10** | ✓ §2 |
| 2 | Env vars table | **10** | ✓ §4 |
| 3 | Where-does-X-live cheat sheet | **10** | ✓ §6 |
| 4 | Debugging guide | **10** | ✓ §29 |
| 5 | Runbook for common incidents | TBD | `ops/runbook/<svc>.md` |
| 6 | On-call rotation defined | TBD | PagerDuty |
| 7 | SLO/SLA published | TBD | reviewer audit |
| 8 | Capacity headroom monitored | TBD | Grafana panel |
| 9 | Cost dashboard | TBD | FinOps dashboard |
| 10 | Backup + restore tested | TBD | DR drill log |

### 9. Governance & Compliance (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | Owner (team + on-call) defined | TBD | CODEOWNERS |
| 2 | Risk register entry | TBD | `docs/architecture/security/` |
| 3 | Change management process | TBD | PR template |
| 4 | Audit log retention ≥ 6 months | TBD | EU AI Act Art. 12 |
| 5 | Right-to-explanation supported | TBD | §48 + EU AI Act Art. 86 |
| 6 | Bias / fairness pre-deploy gate | TBD | §48 |
| 7 | Model card filed (for AI) | TBD | `docs/model-cards/` |
| 8 | SOC2 controls mapped | TBD | compliance matrix |
| 9 | GDPR — PII inventory | TBD | data lineage |
| 10 | Vendor / SaaS dependencies tracked | TBD | `docs/vendors.md` |

### 10. Documentation (10 rows)

| # | Item | Score | Evidence |
|---|---|---|---|
| 1 | README present | **10** | ✓ this file |
| 2 | README has all 33 §58 sections | **10** | ✓ drill-locked |
| 3 | README freshness < 7 days | TBD | git log mtime |
| 4 | File inventory current | **10** | ✓ `mcp/tests/drill_readme_generator.py` (12/12 ✓) → §5 |
| 5 | Recent activity tracked | **10** | ✓ §30 |
| 6 | Domain glossary present | **10** | ✓ §28 |
| 7 | ADRs cross-linked | TBD | reviewer audit |
| 8 | Runbook cross-linked | TBD | reviewer audit |
| 9 | OpenAPI spec generated + linked | TBD | `/openapi.json` URL |
| 10 | Sequence diagrams up-to-date | **10** | 5 endpoints diagrammed |

### Aggregate score

```
Auto-locked rows  : count below — drill-protected, deterministic
Reviewer-fill rows: TBD — reviewer scores honestly per evidence
Target            : ≥ 80 / 100 for production
Brutal rule       : never overwrite TBD with ✓ without evidence
```

Run `python3 mcp/tests/drill_readme_generator.py` to verify the auto-locked rows are still locked. Manually fill TBD rows during PR review using the evidence-column commands as starting point.


## 20. Final Production Readiness Score

| Area | Score (/10) |
|---|---|
| Architecture | — |
| Security | — |
| Performance | — |
| Reliability | — |
| Observability | — |
| Testing | — |
| Scalability | — |
| AI Safety | — |
| DevOps | — |
| Maintainability | — |
| **Total** | **— / 100** |

### Decision

- [ ] **GO** — Production-ready (≥80, no failed gates)
- [ ] **CONDITIONAL GO** — Ship with documented follow-ups (≥60)
- [ ] **NO-GO** — Block release (any critical-red gate, or <60)

### Critical blockers

1. _TBD_

### Follow-ups (post-ship)

| ID | Description | Owner | Due |
|---|---|---|---|
| — | — | — | — |

### Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Tech Lead | — | — | — |
| Security | — | — | — |
| SRE | — | — | — |

---

_Generated by `scripts/generate_folder_report.py`. Re-run after major folder changes:_
_`python3 scripts/generate_folder_report.py --folder <this-folder> --force`_
