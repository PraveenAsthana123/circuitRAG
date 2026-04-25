# Repo Ingestion and Preprocessing Architecture

This document maps data preprocessing concepts to this repo's ingestion-oriented architecture.

## 1. Where preprocessing fits in this repo

The repo already has the right high-level shape for preprocessing:

- upload entrypoint
- parser layer
- chunking layer
- embedding layer
- repository layer
- saga and recovery layer

Relevant areas include:

- `services/ingestion-svc/app/parsers/`
- `services/ingestion-svc/app/chunking/`
- `services/ingestion-svc/app/embedding/`
- `services/ingestion-svc/app/services/ingestion_service.py`
- `services/ingestion-svc/app/saga/`

## 2. Current preprocessing stages in repo terms

### Entry and validation
- upload route receives file
- content type and file metadata are available
- service decides how to process

### Parsing
- parser registry routes file to parser
- parser extracts canonical text or structured content

### Chunking
- text is segmented into chunks
- token-aware counting supports chunk sizing

### Embedding
- chunks are converted into vector-ready representations

### Storage/indexing
- document metadata, chunks, vectors, and graph links are persisted

### Recovery
- sagas and recovery paths address partial failures

## 3. Repo-relevant preprocessing concerns

### Validation concerns
- wrong content type vs actual file type
- oversized document
- unsupported parser path
- parse failure

### Normalization concerns
- whitespace normalization
- document-title normalization
- metadata consistency
- token-aware chunk shape consistency

### Filtering concerns
- duplicate documents
- poisonous or malicious content
- tenant scope mistakes
- bad parse results that should not be indexed

### Conversion concerns
- PDF/DOCX/HTML into canonical extracted text
- canonical text into chunk records
- chunk records into embeddings

## 4. What is strong in the current repo direction

- parser abstraction exists
- chunking is explicit
- embedding layer is explicit
- recovery and saga thinking are present
- repository boundaries are separate from routes

## 5. What is likely still missing or thinner

- richer ingestion-time quality profiling
- stronger duplicate detection
- broader multimodal preprocessing
- clearer preprocessing metrics by file type
- richer policy checks during ingestion
- more explicit extraction-confidence handling

## 6. Best monitoring for preprocessing

Track at least:

- uploads accepted
- parse success/failure by type
- parse latency by type
- chunk count distribution
- token length distribution
- embedding latency and failures
- duplicate detection count
- rejected document count by reason
- backlog and recovery counts

## 7. Best next architectural improvements

1. add stronger preprocessing metrics by file type
2. add explicit duplicate and near-duplicate detection strategy
3. add richer quality profiling before indexing
4. add clearer rejection and quarantine paths
5. extend multimodal support only after core text/document path is fully measured

## 8. Bottom line

This repo already has the right ingestion architecture shape.

The main remaining work is not inventing preprocessing from scratch.

It is making preprocessing:

- more measurable
- more policy-aware
- more explicit about edge cases
- more operationally visible
