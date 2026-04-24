# vLLM GPU deployment

Swap Ollama for vLLM (OpenAI-compatible inference server) on a GPU host.

## Why

| | Ollama | vLLM |
|---|---|---|
| Setup | single binary, CPU-ok | GPU required, CUDA toolchain |
| Throughput on same GPU | 1x | 5-20x (PagedAttention + continuous batching) |
| OpenAI-compatible endpoint | yes | yes |
| Multi-GPU tensor-parallel | limited | first-class (`--tensor-parallel-size N`) |
| Best for | dev + CPU-only demos | prod + cost-efficient scale |

## Requirements

- NVIDIA GPU, compute capability ≥ 7.0 (V100 / T4 / A10 / A100 / H100)
- NVIDIA driver ≥ 535
- `nvidia-container-toolkit` installed; verify with `docker info | grep -i nvidia`
- For gated HF models, a `HF_TOKEN` environment variable

## Run

```bash
# From repo root
docker compose -f docker-compose.yml -f infra/vllm/docker-compose.gpu.yml up -d

# Tail the vLLM startup — it downloads the model weights on first run
docker logs -f documind-vllm

# Smoke test (vLLM exposes the Ollama-compatible path as /v1/chat/completions)
curl http://localhost:11434/v1/models
```

## Pointing DocuMind at vLLM

No code changes in inference-svc. The vllm container reuses port 11434, so
`DOCUMIND_OLLAMA_URL=http://localhost:11434` continues to work — the `/api/chat`
and `/api/embed` paths resolve to vLLM's OpenAI-compatible endpoints.

For model switch, update:

```bash
DOCUMIND_OLLAMA_LLM_MODEL=llama3.1:8b     # name MUST match --served-model-name
DOCUMIND_OLLAMA_EMBED_MODEL=nomic-embed-text
```

## K8s production deployment

`infra/k8s/data-stores/vllm.yaml` is out of scope for this demo; for production
see the [vLLM K8s deployment guide](https://docs.vllm.ai/en/latest/serving/deploying_with_k8s.html).
The core requirements map 1:1: GPU nodepool, gpu-operator, shared-memory `emptyDir`
for NCCL, anti-affinity across nodes for HA.

## Autoscaling

HPA on pods alone won't fill a GPU — an under-loaded GPU pod still occupies a
full card. Two options:

1. **GPU-per-pod**: keep replicas at 1 or tensor-parallelism; scale by adding
   GPU nodes (cluster autoscaler) when `inference_inflight` metric rises.
2. **Multi-tenancy per GPU**: share one pod across tenants (vLLM already
   batches efficiently). Scale only when p95 latency crosses SLO.

DocuMind's `inference-svc-hpa` already uses the custom `inference_inflight`
metric — wire that to the vLLM pod's metrics endpoint in prod.
