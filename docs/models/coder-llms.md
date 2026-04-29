# Coder-LLM Catalogue (Local, via Ollama)

Four open-weight coder models installed on the local Ollama daemon
for in-house code completion / review / synthesis. Drill enforces
parity at `mcp/tests/drill_ollama_coder_models.py`.

## Why local coder models, not just hosted

| Reason | Detail |
|---|---|
| **Cost** | Hosted code completion at scale runs $X / 1k requests; local at near-zero marginal cost beyond infra. |
| **Latency** | <5s per response vs. hosted's network RTT + queueing. Critical for inline IDE flows. |
| **Privacy** | Source code never leaves the box. Compliance-sensitive customers refuse hosted code APIs. |
| **Offline** | Air-gapped customer deployments (defence, healthcare) can't reach hosted endpoints. |
| **Mix-and-match** | Different models excel at different tasks; routing per task type is only practical with locals. |

## The catalogue (7B class — current install)

| Model | Tag (Ollama) | Disk | License | Strength | Trade-off |
|---|---|---|---|---|---|
| **Code Llama** | `codellama:7b-instruct` | 3.8 GB | Meta open-weights (custom) | Stable baseline; widest community tooling. | Older arch (Aug 2023); newer models out-perform it on HumanEval. |
| **DeepSeek Coder** | `deepseek-coder:6.7b-instruct` | 3.8 GB | DeepSeek License (research + commercial OK) | Highest HumanEval pass@1 in this size class (~73%). Best per-watt coder. | Newer ecosystem — fewer fine-tunes / merges available. |
| **StarCoder2** | `starcoder2:7b` | 4 GB | BigCode OpenRAIL-M (permissive) | Enterprise-safe license; trained on StackV2. Excellent at multi-language. | Slightly lower instruct-following than DeepSeek; better as raw code completion than chat. |
| **CodeGemma** | `codegemma:7b-instruct` | 5 GB | Apache 2.0 (most permissive) | Best license for redistribution. Solid for local dev / personal projects. | Smaller capacity; trails the others on harder tasks. |

Total disk ≈ 17 GB on top of any existing models.

## Recommended ranking and role mapping

| Model | Overall fit | License posture | Best use in this repo | Notes |
|---|---|---|---|---|
| **DeepSeek Coder** | ⭐⭐⭐⭐⭐ | Open weights | Primary coder / executor | Best local coding performance in the current installed set. |
| **StarCoder2** | ⭐⭐⭐⭐ | Permissive | Reviewer / cross-checker | Good enterprise-safe fallback; weaker than DeepSeek as the main implementer. |
| **Code Llama** | ⭐⭐⭐⭐ | Open weights | Security-focused advisor | Still useful, but no longer the best main coding default. |
| **CodeGemma** | ⭐⭐⭐ | Apache 2.0 | Test-oriented local helper | Lightweight and license-friendly; smaller capability ceiling. |
| **Kimi K2** | Cloud-tier | Modified MIT | Chair / advisor default | Strongest synthesis path; requires Ollama Cloud access. |
| **Qwen 2.5** | Local fallback | Open weights | Local chair / advisor override | Use when cloud access is unavailable and everything must stay local. |

Current live role mapping in this repo:

```text
Coder / executor           -> DeepSeek Coder
Reviewer                   -> StarCoder2
Security advisor           -> Code Llama
PR-review chair / advisor  -> Kimi K2 (default) or Qwen 2.5 (local override)
Test-focused helper        -> CodeGemma
```

## When to use which

```
Quick, default code completion          → DeepSeek Coder
License-sensitive ship-with-product     → StarCoder2 or CodeGemma
Multi-language polyglot completion      → StarCoder2
Production-stable, conservative choice  → Code Llama
Hobby / personal / Apache-2 ecosystem   → CodeGemma
```

Routing is currently manual (caller picks the model). A future
iteration could add a model-router service that classifies the
task type and picks: e.g. SQL → Code Llama, JS → DeepSeek, license
sensitive → StarCoder2.

## Hardware sizing

This box: 31 GB RAM, 11 GB VRAM (GTX 1080 Ti). At Q4 quantization
the 7B class fits comfortably in VRAM with ~3 GB headroom. The
larger variants below need either VRAM headroom or partial CPU
offload.

### Upgrade path (heavyweight variants)

If you have ≥ 16 GB VRAM (e.g. RTX 4090, A6000, dual GPU), pull
the larger checkpoints. Larger models are **slower** but produce
better answers on complex tasks. On this 11 GB / 1080 Ti box they
will partial-offload to CPU and run noticeably slower (~15-30s per
response vs. <5s for 7B).

| Model | Heavyweight tag | Disk | When it's worth it |
|---|---|---|---|
| Code Llama | `codellama:13b-instruct` or `:34b-instruct` | 7 GB / 19 GB | Multi-file refactors; long context |
| DeepSeek Coder v2 | `deepseek-coder-v2:16b` (MoE-lite) | 9 GB | Best quality available locally; large context |
| StarCoder2 | `starcoder2:15b` | 9 GB | Cross-language reasoning (Rust, Go, OCaml) |
| CodeGemma | `codegemma:7b-code` (FIM-tuned) | 5 GB | Pure infill / completion, not chat |

### Cloud tier (no local install — needs Ollama Cloud subscription)

| Model | Tag | License | Strength | Trade-off |
|---|---|---|---|---|
| Kimi K2 | `kimi-k2:1t-cloud` | Modified MIT | 1T-param MoE — flagship-tier reasoning + code synthesis | Cloud-only; no local install (would need ~100 GB VRAM); paid Ollama Cloud |
| Kimi K2.5 | `kimi-k2.5:cloud` | Modified MIT | Latest stable Kimi K-series | Same |
| Kimi K2.6 | `kimi-k2.6:cloud` | Modified MIT | Newest variant | Same |
| Kimi K2-Thinking | `kimi-k2-thinking:cloud` | Modified MIT | Chain-of-thought variant for hard reasoning | Same |

**To use Kimi (when ready):**

```
ollama signin                                         # one-time Ollama Cloud signup
ollama pull kimi-k2-thinking:cloud                    # registers cloud routing
curl http://localhost:11434/api/generate -d '{
  "model": "kimi-k2-thinking:cloud",
  "prompt": "...",
  "stream": false
}'
```

**Why Kimi isn't in `drill_ollama_coder_models`:** the drill verifies
LOCAL pull + sanity prompt. Cloud-only models would false-pass
("model registered" without testing the cloud endpoint). When Kimi-2
ships (per `docs/NEXT_POLICY.md` ledger), a separate
`drill_ollama_cloud_models.py` with `# RESOURCES: ollama_cloud` tag
will exercise the cloud-routing path.

**Where Kimi fits in the council:** Kimi-2 wires Kimi in as the chair
of the `pr_review` council — replacing DeepSeek in the chair/advisor
path. The 7B-class authors stay local (cheap, fast, parallel); the
chair upgrades to 1T cloud for synthesis quality. Live use still
depends on active Ollama Cloud access and a per-tenant token budget,
otherwise a single PR review can burn the budget.

**Local fallback / override:** if Ollama Cloud access is unavailable,
the repo can be switched back to local Qwen without another code edit:

```bash
export SIDECAR_CHAIR_MODEL="qwen2.5:latest"
export AGENT_ADVISOR_MODEL="qwen2.5:latest"
```

The first override affects the Sidecar PR-review chair. The second
affects the agent-orchestrator advisor default via service settings.

## Operational

### Daemon

```
systemctl status ollama        # status
systemctl restart ollama       # if a model gets stuck loading
journalctl -u ollama -f        # live logs (model load, gen requests)
```

### Pull / re-pull

```
ollama pull codellama:7b-instruct
ollama pull deepseek-coder:6.7b-instruct
ollama pull starcoder2:7b
ollama pull codegemma:7b-instruct
```

Re-pull is idempotent — the daemon checks layer hashes and only
downloads diffs.

### Verify

```
python3 mcp/tests/drill_ollama_coder_models.py
```

Hits each model with a one-shot Python function-completion prompt;
fails if any returns empty or exceeds 90s deadline. The drill is
tagged `# RESOURCES: ollama` so it does NOT run in tier-1 PR-time
drills (no Ollama in CI). Run locally before any model-related
change.

### One-off prompt

```
ollama run deepseek-coder:6.7b-instruct
> write a function to merge two sorted lists in O(n+m)
```

Or via the HTTP API directly (what the inference-svc uses):

```bash
curl -s http://localhost:11434/api/generate -d '{
  "model": "deepseek-coder:6.7b-instruct",
  "prompt": "Python: function to merge two sorted lists",
  "stream": false,
  "options": {"num_predict": 256, "temperature": 0.2}
}' | jq -r .response
```

## Composes with

* `services/inference-svc/app/services/ollama_client.py` — the
  HTTP client that talks to this daemon. Wraps every call in a
  CircuitBreaker + Prometheus token counter.
* `mcp/tests/drill_ollama_coder_models.py` — the parity drill.
* `services/inference-svc/app/agents/agent_board.py` — boards
  back author/reviewer/advisor agents with these models. A "code
  review board" is the natural next surface: DeepSeek as one
  reviewer, StarCoder2 as another, CodeGemma as advisor.

## Catalogue version

Update `COODER_CATALOGUE` in `mcp/tests/drill_ollama_coder_models.py`
in the same commit as any addition / removal. The drill enforces
that doc-listed models are pulled — drift fails CI for anyone with
the `ollama` resource available.
