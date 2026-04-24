# C4 — Component view (Python services)

## ingestion-svc

```mermaid
graph TB
    router[routers/documents.py]
    svc[services/IngestionService]
    saga[saga/DocumentIngestionSaga]
    parsers[parsers/*]
    chunker[chunking/RecursiveChunker]
    embedder[embedding/OllamaEmbedder]
    doc_repo[repositories/DocumentRepo]
    chunk_repo[repositories/ChunkRepo]
    qdrant_repo[repositories/QdrantRepo]
    neo4j_repo[repositories/Neo4jRepo]
    saga_repo[repositories/SagaRepo]
    blob[services/BlobService]

    router --> svc
    svc --> saga
    svc --> doc_repo
    svc --> blob
    saga --> parsers
    saga --> chunker
    saga --> embedder
    saga --> doc_repo
    saga --> chunk_repo
    saga --> qdrant_repo
    saga --> neo4j_repo
    saga --> saga_repo
```

## retrieval-svc

```mermaid
graph LR
    router[routers/*]
    retr[services/HybridRetriever]
    emb[services/OllamaEmbedderClient]
    vec[services/VectorSearcher]
    grp[services/GraphSearcher]
    rrf[services/ReciprocalRankFusion]
    cache[documind_core.cache.Cache]

    router --> retr
    retr --> emb
    retr --> vec
    retr --> grp
    retr --> rrf
    retr --> cache
```

## inference-svc

```mermaid
graph LR
    router[routers/*]
    rag[services/RagInferenceService]
    rcli[services/RetrievalClient]
    prompt[services/PromptBuilder]
    olm[services/OllamaClient]
    guards[services/GuardrailChecker]

    router --> rag
    rag --> rcli
    rag --> prompt
    rag --> olm
    rag --> guards
```

Each component is one class file. Every constructor takes its dependencies
so you can pass fakes in tests. Re-read the saga from top to bottom and
you'll see exactly how the 67 design areas wire together in code.
