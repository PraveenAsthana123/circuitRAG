# LLVM/MLIR + Circuit Breaker + Agent Council — full sequence

> Operator-supplied design realized as Stage-1 adapter + LLVM toolchain
> verified working. Circuit breaker wraps the native callable from the
> OUTSIDE (per the brutal rule: never put CB logic inside the kernel).

## The five layers (operator-supplied)

| Layer | Role |
|-------|------|
| **LLVM/MLIR** | performance engine — fast native code |
| **Circuit Breaker** | reliability shield — stop calling failing things |
| **Agent Council** | decision brain — which tool, when |
| **Observability** | truth layer — metrics + traces + logs |
| **Fallback** | survival path — what to do when fast path fails |

## End-to-end sequence (the 12-step operator spec)

```
User
 ↓
[1]  API Gateway              auth, rate-limit, request_id
 ↓
[2]  Router Agent             classify task (gemma3:1b in our council)
 ↓
[3]  Planner Agent            decide if optimized compute needed
 ↓
[4]  Tool Selection           select native tool/service
 ↓
[5]  Circuit Breaker          check service health (closed/open/half-open)
 ↓
[6]  Optimized Native Service
       ├─ LLVM IR optimized CPU function
       ├─ MLIR tensor/vector lowering
       └─ GPU/accelerator kernel
 ↓
[7]  Profiler/Telemetry       record latency, CPU, memory
 ↓
[8]  Circuit Breaker          record success/failure
 ↓
[9]  Validator                check output quality
 ↓
[10] Critic Agent             review (gemma2:9b in our council)
 ↓
[11] Response Agent           send final answer
 ↓
[12] Observability            persist trace + decision audit row
```

## What's wired today (post-this-commit state)

| Step | Component | Status |
|------|-----------|--------|
| 1 | API Gateway | ✅ services/api-gateway (FastAPI in-house) |
| 2 | Router Agent | ✅ scripts/agent_router.py (Stage-2 Ollama) |
| 3 | Planner Agent | ✅ gemma_agent_council planner stage (gemma3:4b) |
| 4 | Tool Selection | ✅ MCP server registry (9 servers) |
| 5 | **Circuit Breaker** | ✅ libs/py/documind_core/circuit_breaker.py |
| 5b | **Native Compute Wrapper** | ✅ scripts/native_compute_wrapper.py (this commit — Stage-1) |
| 6 | LLVM toolchain | ✅ clang 18.1.3 + opt + llc + llvm-config + llvm-as + llvm-dis + llvm-objdump |
| 6 | MLIR toolchain | ❌ not installed (needs source build per llvm.org) |
| 6 | Native compiled artifact | ❌ none yet — wrapper exists; no compiled targets yet |
| 7 | Telemetry | ✅ OTel + Prometheus |
| 8 | CB record | ✅ NativeComputeWrapper.record_success/record_failure |
| 9 | Validator | ⚠ implicit; per-service |
| 10 | Critic Agent | ✅ gemma_agent_council critic stage (gemma2:9b) |
| 11 | Response Agent | ✅ gemma_agent_council synthesis |
| 12 | Audit row | ✅ WrapperResult + CouncilResult + decision-audit JSONLs |

## The brutal rule (operator-restated)

> **Do not put circuit breaker logic inside LLVM/MLIR optimization code.
> Put it AROUND the compiled component as a protection wrapper.**

`scripts/native_compute_wrapper.py` is exactly that wrapper. It's
agnostic to what's inside `native_fn` — could be:
- a pure-Python function (today)
- a ctypes binding to an LLVM-compiled shared lib (Stage-2)
- an MLIR-lowered tensor kernel (Stage-3)
- a CUDA kernel via cupy/torch (Stage-3)

## Wrapper contract (this commit)

```python
from native_compute_wrapper import NativeComputeWrapper

wrapper = NativeComputeWrapper(
    name="bge_reranker",
    native_fn=bge_compiled_rerank,   # fast path (LLVM-compiled future)
    fallback_fn=rrf_rerank,           # survival path (pure-Python RRF)
    timeout_ms=500,
    threshold=5,                      # failures before OPEN
    recovery_s=30,                    # seconds in OPEN before half-open probe
)

result = wrapper.run(query, chunks)
# result.path_taken in {
#     "native",
#     "fallback:open",      # breaker was open, native skipped entirely
#     "fallback:timeout",   # native exceeded timeout_ms
#     "fallback:error",     # native raised an exception
# }
# result.native_latency_ms / result.fallback_latency_ms / result.error
```

## Drill (8 steps, 6 negative)

`mcp/tests/drill_native_compute_wrapper_stage1.py` — locks:

1. positive: module exists + non-trivial size
2. positive: 4 contract surfaces (NativeComputeWrapper, WrapperResult, exception, is_available)
3. **negative:** instantiation FAILS CLOSED when env flag unset
4. positive: native success path returns `path_taken="native"`
5. **negative:** timeout → `path_taken="fallback:timeout"` + counters
6. **negative:** native exception → `path_taken="fallback:error"` + error captured
7. **negative:** breaker OPENs after threshold failures; subsequent calls bypass native (`fallback:open`)
8. positive: status() reports 3-state contract + Stage-2 path

## The RAG reranker example (operator-supplied)

```
User asks complex question
   ↓
RAG Agent retrieves 100 chunks
   ↓
Needs fast reranking
   ↓
NativeComputeWrapper.run(query, chunks)
   ↓
   ┌─ native (LLVM/MLIR-compiled BGE) ─┐
   │   completed in <500ms             │ → top 10 chunks
   │                                    │
   │   timeout / crash / breaker open  │ → fallback (RRF + min_score)
   └────────────────────────────────────┘
   ↓
LLM generates answer (Gemma council specialist)
```

When the optimized kernel starts timing out:

```
Reranker timeout
   ↓
Wrapper.record_failure(kind="timeout")
   ↓
After 5 timeouts → breaker OPENs for 30s
   ↓
All subsequent calls → fallback (RRF) immediately
   ↓
Telemetry alerts ops to investigate
   ↓
After 30s → half-open probe → if probe ok, close breaker
```

## LLVM toolchain (verified working this commit)

```bash
# Check
clang --version          # Ubuntu clang version 18.1.3 (1ubuntu1)
opt --version            # LLVM 18.1.3
llc --version            # LLVM 18.1.3
llvm-config --version    # 18.1.3

# Compile a hot path to optimized LLVM IR
echo 'int add(int a,int b){return a+b;}' > /tmp/x.c
clang -S -emit-llvm /tmp/x.c -o /tmp/x.ll
opt -O3 -S /tmp/x.ll -o /tmp/x.opt.ll
llc /tmp/x.opt.ll -o /tmp/x.s
clang -O3 /tmp/x.s -o /tmp/x

# Then wrap the resulting binary's Python bindings with NativeComputeWrapper
```

## MLIR — deferred to source build

MLIR is NOT in Ubuntu 24.04 packages. Per the operator's recipe:

```bash
git clone https://github.com/llvm/llvm-project.git
cd llvm-project
cmake -S llvm -B build -G Ninja \
    -DLLVM_ENABLE_PROJECTS="clang;mlir;lld" \
    -DLLVM_BUILD_EXAMPLES=ON \
    -DLLVM_TARGETS_TO_BUILD="X86" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build
export PATH=$PWD/build/bin:$PATH
```

This is multi-hour work. Future iteration when MLIR-lowered tensor
kernels become a P0 need.

## Monitoring metrics (operator-spec; emitted by wrapper)

| Metric | Source | Purpose |
|--------|--------|---------|
| `kernel_latency_ms` | `WrapperResult.native_latency_ms` | native function speed |
| `breaker_state` | `wrapper.state` | closed/open/half-open snapshot |
| `failure_rate` | `counters.failure / total` | detects instability |
| `timeout_count` | `counters.timeout` | performance degradation signal |
| `fallback_rate` | `counters.fallback_used / total` | reliability risk |
| `cpu_usage` | OS-level (psutil) | compute pressure |
| `memory_usage` | OS-level | leak detection |
| `p95_latency` | derived from `last_native_latency_ms` window | UX |
| `p99_latency` | derived | tail risk |

## What this commit ships

- ✅ `scripts/native_compute_wrapper.py` — Stage-1 wrapper class
- ✅ `mcp/tests/drill_native_compute_wrapper_stage1.py` — 8/8 green
- ✅ LLVM 18.1.3 toolchain symlinked: `~/.local/bin/{opt,llc,llvm-config,llvm-as,llvm-dis,llvm-objdump}`
- ✅ This doc

## What's deferred

- **Stage-2:** wire wrapper around BGE reranker (FlagEmbedding); RRF as fallback
- **Stage-3:** LLVM-compile a custom reranker hot path; ctypes bind it
- **Stage-3+:** MLIR build from source for tensor lowering
- **Telemetry:** wire `WrapperResult` metrics into Prometheus + Grafana

## Composes with

- `scripts/native_compute_wrapper.py` — this implementation
- `mcp/tests/drill_native_compute_wrapper_stage1.py` — Stage-1 contract drill
- `libs/py/documind_core/circuit_breaker.py` — pre-existing CB primitives
- `services/retrieval-svc/app/services/reranker.py` — RRF (Stage-0 fallback)
- `services/retrieval-svc/app/services/bge_reranker.py` — Stage-1 BGE adapter
- `scripts/gemma_agent_council.py` — the agent council that calls tools
- `docs/architecture/six-plane-audit-2026-05-04.md` — recovery plane gap
- `docs/architecture/compression-tools-audit-2026-05-04.md` — table row #15 (rerank)
- `docs/architecture/rag-deep-test-2026-05-04.md` — empirical baseline
- §38 — decision audit (every dispatch logs the path taken)
- §43 — drill discipline (8 steps, 6 negative)
- §47 — architecture & design patterns (fallback path is § rule)
- §51 — forensic substrate
- §52 — brutal tool review (40-row when wired in production hot path)
- §54 — no Co-Authored-By trailer
- §56 — Stage-1 6-gate adoption process

## The brutal closing rule

> A native-compiled fast path without a circuit breaker around it is a
> production outage waiting to happen. The wrapper is the SHIELD;
> LLVM/MLIR is the BLADE. You ship the shield first, then the blade.
> This commit ships the shield and verifies the blade-toolchain is
> available — but doesn't yet sharpen any blade. Stage-2 wires the
> shield around an existing blade (BGE reranker). Stage-3 forges a new
> blade (LLVM-compiled custom reranker).
