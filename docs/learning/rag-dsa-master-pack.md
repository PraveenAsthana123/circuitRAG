# RAG + DSA Master Pack

This document consolidates:

- end-to-end RAG architecture with DSA mapping
- minimal Python example
- top interview questions and answers
- optimization techniques for latency, cost, and accuracy
- real production issues and solutions
- deep dives on caching and agent workflow control

The goal is to make the content usable in three ways:

1. as architecture documentation
2. as interview preparation
3. as an engineering design reference

## 1. Core Concept

RAG is not just:

- embeddings
- vector DB
- prompt + LLM

RAG is a combination of:

- search
- retrieval
- ranking
- constrained context selection
- caching
- workflow orchestration
- safety and evaluation

That is why DSA matters.

## 2. 5W

| Dimension | Explanation |
| --- | --- |
| What | RAG is a retrieval and ranking system wrapped around an LLM |
| Why | Quality, cost, and latency depend on search and selection, not just model choice |
| Where | Ingestion, indexing, retrieval, ranking, caching, context packing, orchestration |
| When | Every time documents are processed, indexed, queried, reranked, cached, or evaluated |
| Who | Backend engineers, AI engineers, search engineers, platform engineers, architects |

## 3. End-To-End RAG Architecture With DSA

```text
User Query
   ↓
Query Preprocessing
   ↓
Embedding
   ↓
Retriever
   ├── Vector Search: HNSW Graph
   ├── Keyword Search: Inverted Index
   └── Metadata Filter: HashMap
   ↓
Top-K Selection: Heap / Priority Queue
   ↓
Re-ranking: Sorting / Scoring
   ↓
Context Selection: Greedy / Knapsack
   ↓
Prompt Builder
   ↓
LLM
   ↓
Evaluation + Guardrails
   ↓
Response
```

## 4. DSA Mapping Table

| RAG Step | DSA Used | Why |
| --- | --- | --- |
| Chunking | Sliding Window | Preserve context overlap |
| Metadata filter | HashMap | Fast lookup |
| Vector search | HNSW Graph | Fast approximate nearest neighbor |
| Keyword search | Inverted Index | Traditional search |
| Top-K | Heap | Efficient ranking |
| Re-ranking | Sorting | Order by relevance |
| Context selection | Greedy / Knapsack | Fit best chunks into token limit |
| Cache | LRU Cache | Reduce cost and latency |
| Agent workflow | DAG / State Machine | Controlled multi-step execution |

## 5. Sequence Flow

```text
Client
  -> query preprocessing
  -> embedding model
  -> retrieval orchestrator
     -> vector DB
     -> lexical index
     -> metadata filter
  -> top-k heap
  -> reranker
  -> context selector
  -> prompt builder
  -> LLM
  -> guardrails / evaluation
  -> response
```

## 6. Network Flow

```text
Client
  -> API Gateway
  -> Inference Service
  -> Retrieval Service
     -> Vector DB
     -> Lexical / metadata index
     -> Cache
  -> Prompt Assembly
  -> LLM runtime
  -> Guardrail / evaluation layer
  -> Response
```

## 7. Minimal Python Example

```python
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import heapq

docs = [
    "RAG combines retrieval with generation.",
    "HNSW is used for approximate nearest neighbor search.",
    "Heap is useful for Top-K retrieval.",
    "Chunking uses sliding windows to preserve context."
]

model = SentenceTransformer("all-MiniLM-L6-v2")

embeddings = model.encode(docs)
embeddings = np.array(embeddings).astype("float32")

index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)

query = "How is DSA used in RAG?"
query_vec = model.encode([query]).astype("float32")

distances, indices = index.search(query_vec, k=3)

results = []
for dist, idx in zip(distances[0], indices[0]):
    score = 1 / (1 + dist)
    heapq.heappush(results, (-score, docs[idx]))

print("Top Results:")
while results:
    score, doc = heapq.heappop(results)
    print(abs(score), doc)
```

## 8. Top 20 Interview Q&A

| # | Question | Strong answer |
| --- | --- | --- |
| 1 | What DSA is used in RAG? | Graphs, heaps, hash maps, inverted indexes, sliding windows, sorting, caches. |
| 2 | Why HNSW in vector DB? | It uses graph-based approximate nearest-neighbor search for fast high-dimensional retrieval. |
| 3 | Why heap for Top-K? | Heap avoids sorting all documents; it efficiently keeps best K results. |
| 4 | How does chunking use DSA? | Sliding window splits documents with overlap to preserve context. |
| 5 | What is inverted index? | A map from keyword to document list, useful for keyword or hybrid search. |
| 6 | How do you optimize token limit? | Use greedy or knapsack-style selection to fit high-value chunks. |
| 7 | How do you remove duplicate chunks? | Use set/hashing or semantic similarity threshold. |
| 8 | How is cache used? | LRU cache stores repeated query, embedding, retrieval, or response results. |
| 9 | How does metadata filtering work? | HashMap or indexed filters by tenant, role, document type, date, and policy. |
| 10 | How does re-ranking work? | Score results and sort by relevance, freshness, authority, or cross-encoder score. |
| 11 | What causes bad retrieval? | Bad chunking, poor embeddings, missing metadata, weak query rewriting. |
| 12 | How do you debug hallucination? | Check retrieved docs, prompt, model output, and faithfulness score. |
| 13 | RAG vs fine-tuning? | RAG is for fresh or domain facts; fine-tuning is for behavior, tone, or structure. |
| 14 | How do you improve accuracy? | Better chunking, hybrid search, re-ranking, metadata filtering, evaluation loop. |
| 15 | How do you reduce latency? | Cache, reduce Top-K, parallel retrieval, smaller model, streaming. |
| 16 | How do you reduce cost? | Token compression, model routing, caching, quantization, smaller model. |
| 17 | How do you handle multi-hop queries? | Use graph traversal, query decomposition, agentic retrieval. |
| 18 | How do you prevent cross-tenant leakage? | tenant_id filters, namespace isolation, RBAC/ABAC, audit logs. |
| 19 | What is retrieval evaluation? | Measure context precision, recall, relevance, faithfulness. |
| 20 | What is production-ready RAG? | Secure, observable, evaluated, cost-controlled, feedback-driven system. |

## 9. Optimization Techniques

| Goal | Technique | DSA / architecture |
| --- | --- | --- |
| Lower latency | Cache repeated queries | LRU Cache |
| Lower latency | Reduce Top-K | Heap tuning |
| Lower latency | Parallel retrieval | Async execution |
| Lower cost | Compress context | Summarization / greedy selection |
| Lower cost | Model routing | Decision tree |
| Better accuracy | Hybrid search | Vector + inverted index |
| Better accuracy | Re-ranking | Sorting / scoring |
| Better accuracy | Metadata filtering | HashMap |
| Better accuracy | Query rewrite | NLP preprocessing + trie / graph support |
| Better safety | Guardrails | Rule engine |
| Better scalability | Queue-based processing | Kafka / worker queue |
| Better reliability | Retry + fallback | Circuit breaker |

## 10. Real Production Issues + Solutions

| Production issue | Root cause | Solution |
| --- | --- | --- |
| Wrong answer | Wrong documents retrieved | Improve chunking, embeddings, filtering, and reranking |
| Hallucination | Model answered beyond context | Add faithfulness checks and context-only prompting |
| Slow response | Large context plus heavy model | Reduce Top-K, cache, stream, route to smaller models |
| High cost | Too many tokens | Context compression, smaller model, caching |
| No answer | Index missing data | Re-index, fix ingestion, improve retrieval coverage |
| Duplicate answers | Duplicate chunks | Deduplicate using hashing or similarity threshold |
| Cross-tenant leak | Weak filtering | Tenant namespace, metadata filters, RBAC/ABAC |
| Poor voice agent response | Latency too high | Smaller model, streaming, local cache |
| Agent infinite loop | No step limit | Max iterations, timeout, budget cap |
| Bad evaluation | No gold dataset | Create golden QA plus edge-case dataset |

## 11. Brutal Final View

A weak answer is:

> I used LangChain and a vector DB.

A strong answer is:

> I designed a retrieval, ranking, evaluation, caching, and control system using DSA patterns like graphs, heaps, hash maps, sliding windows, and state machines.

## 12. Deep Dive: Caching Using LRU

### Why caching is critical

In real systems, 30 to 60 percent of queries repeat.

Without caching:
- same retrieval work repeats
- same LLM work repeats
- latency stays high
- cost stays high

With caching:
- instant response
- near-zero marginal cost for repeated work

### What to cache in RAG

| Layer | What to cache |
| --- | --- |
| Query | Same normalized user question |
| Embedding | Same query embedding |
| Retrieval | Same Top-K docs |
| Response | Final LLM answer |

### LRU cache flowchart

```text
User Query
   ↓
Normalize Query
   ↓
Check Cache (HashMap)
   ├── Hit → Return instantly
   └── Miss
         ↓
Run RAG pipeline
         ↓
Store in Cache
         ↓
If cache full:
   Remove Least Recently Used (LRU)
```

### DSA design

LRU Cache =

- HashMap for O(1) lookup
- Doubly Linked List for usage order

| Structure | Role |
| --- | --- |
| HashMap | O(1) lookup |
| Doubly linked list | Track usage order |
| Head | Most recently used |
| Tail | Least recently used |

### Sequence flow

```text
Request
  -> normalize key
  -> hashmap lookup
  -> if hit: move node to front, return value
  -> if miss: compute result
  -> add node to front
  -> if full: evict tail
```

### Python implementation

```python
class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None


class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = {}

        self.head = Node(0, 0)
        self.tail = Node(0, 0)

        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node):
        prev = node.prev
        nxt = node.next
        prev.next = nxt
        nxt.prev = prev

    def _add(self, node):
        nxt = self.head.next
        self.head.next = node
        node.prev = self.head
        node.next = nxt
        nxt.prev = node

    def get(self, key):
        if key in self.cache:
            node = self.cache[key]
            self._remove(node)
            self._add(node)
            return node.value
        return -1

    def put(self, key, value):
        if key in self.cache:
            self._remove(self.cache[key])

        node = Node(key, value)
        self._add(node)
        self.cache[key] = node

        if len(self.cache) > self.capacity:
            lru = self.tail.prev
            self._remove(lru)
            del self.cache[lru.key]
```

### Advanced caching strategies

| Strategy | Description |
| --- | --- |
| Semantic cache | Query A approximately equals Query B, reuse answer by similarity |
| Multi-level cache | In-memory -> Redis -> edge |
| TTL expiry | Time-based freshness control |

### Trade-offs

| Benefit | Risk |
| --- | --- |
| Fast response | Stale data |
| Low cost | Invalidation complexity |
| Better scalability | Cache inconsistency risk |

### Common failures

| Problem | Cause | Fix |
| --- | --- | --- |
| Wrong answer reused | No TTL | Add expiry |
| Low hit rate | Poor normalization | Normalize queries |
| Memory overflow | No limit | Set capacity |
| Duplicate cache entries | No deterministic key | Normalize and hash input |

### Interview answer

> I use LRU cache to store repeated queries and responses. It combines HashMap for O(1) lookup and a doubly linked list to track usage. I also use semantic caching and TTL to balance performance and freshness.

### Brutal insight

Most engineers optimize the model.
Smart engineers optimize retrieval.
Architects eliminate repeated work using caching.

## 13. Deep Dive: Agent Workflow As DAG / State Machine

### Why this is critical

RAG alone is a QA system.
Agents introduce planning, control flow, retries, and tool use.

Without structure:
- agents loop
- execution becomes hard to predict
- cost grows uncontrollably

With DAG plus state machine:
- execution is bounded
- behavior is observable
- recovery is debuggable

### Core idea

Agent workflow =

- states
- transitions
- rules

### High-level flow

```text
User Query
   ↓
Planner Agent
   ↓
State Machine / DAG
   ↓
Execution Steps
   ↓
Decision Nodes
   ↓
Final Output
```

### DAG flowchart

```text
Start
 ↓
Parse Query
 ↓
Decision Node:
   ├── Need Retrieval → RAG Node
   ├── Need Tool → API Node
   ├── Simple → LLM Node
 ↓
Process Node
 ↓
Evaluate Output
 ↓
Decision:
   ├── Good → End
   ├── Retry → Loop
   ├── Fail → Human
```

### DSA concepts

| Concept | Usage |
| --- | --- |
| Graph (DAG) | Workflow structure |
| Nodes | Tasks such as RAG, API, LLM |
| Edges | Flow between steps |
| State machine | Control transitions |
| Queue | Manage tasks |
| Stack | Optional backtracking |

### State machine model

```text
STATE: START
   ↓
STATE: PLAN
   ↓
STATE: EXECUTE
   ↓
STATE: EVALUATE
   ↓
STATE: DECISION
   ├── SUCCESS → END
   ├── RETRY → EXECUTE
   ├── FAIL → HUMAN
```

### Node types

| Node | Role |
| --- | --- |
| Planner node | Break task |
| Retrieval node | RAG |
| Tool node | API call |
| LLM node | Generate |
| Evaluation node | Score |
| Decision node | Control flow |
| Human node | Escalation |

### Control logic

```text
Task Execution
   ↓
Check:
   - iteration count
   - cost budget
   - time limit
   ↓
Execute node
   ↓
Evaluate
   ↓
Transition to next node
```

### Simplified Python

```python
class State:
    def __init__(self, name):
        self.name = name

def planner(state):
    return "retrieval"

def retrieval(state):
    return "llm"

def llm(state):
    return "evaluate"

def evaluate(state):
    score = 0.7
    if score > 0.8:
        return "end"
    else:
        return "retry"

states = {
    "start": planner,
    "retrieval": retrieval,
    "llm": llm,
    "evaluate": evaluate,
}

current = "start"

for _ in range(5):
    print("Current:", current)
    if current == "end":
        break
    current = states[current](current)
```

### DAG vs state machine

| Feature | DAG | State machine |
| --- | --- | --- |
| Structure | Graph | States |
| Flexibility | High | Controlled |
| Debugging | Moderate | Easier |
| Best use | Complex workflows | Agent control |

Best practice:

> Use a state machine on top of a DAG.

### Failure control

- if iterations > 5 -> stop
- if cost > limit -> stop
- if invalid output -> retry
- if low confidence -> human

### Interview answer

> I model agent workflows as a DAG combined with a state machine. Each node represents a task like retrieval or API execution, and transitions are controlled by evaluation and policy rules. This ensures bounded execution, prevents loops, and makes the system observable and debuggable.

### Brutal insight

Most people build agents.
Strong engineers build workflows.
Architects build controlled execution graphs.

## 14. Final Architect View

If you understand:

- sliding window for chunking
- HNSW for vector search
- heap for Top-K
- knapsack-style context selection
- LRU caching
- DAG plus state machine orchestration

then you understand that RAG is not a wrapper around an LLM.

It is a search, ranking, optimization, caching, and control system with an LLM at the end.
