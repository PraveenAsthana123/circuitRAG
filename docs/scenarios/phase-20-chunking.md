# Phase 20 — Chunking (Deep Dive)

**Status:** Specified. Section + window + sentence chunkers exist; semantic / AST / table-aware chunkers + full metadata tagging are gaps.

Chunking is where RAG accuracy is made or lost. Most teams spend on LLMs; the real leverage is here.

---

## 1. Chunking types

### A. Basic
| Type | When |
| --- | --- |
| Fixed-size (tokens/chars) | baseline / unstructured dumps |
| Sliding window | recall-sensitive tasks |
| Sentence-based | FAQ / short docs |

### B. Structural (best for enterprise)
| Type | Use |
| --- | --- |
| Section / heading | policies, manuals |
| Paragraph | reports |
| Table-aware | finance, invoices |
| Code-aware (AST) | code RAG |
| Markdown-aware | docs / wiki |

### C. Semantic (advanced)
| Type | Description |
| --- | --- |
| Embedding-similarity split | cut where topic changes |
| Topic segmentation (BERTopic / TextTiling) | NLP-based |
| LLM-based chunking | model decides boundaries |

### D. Hierarchical (recommended default)
```
Document → Section → Chunk → Sub-chunk
```
Parent/child IDs enable drill-down retrieval and parent-context inclusion.

## 2. Starter configuration

| Parameter | Default |
| --- | --- |
| Chunk size | 400–800 tokens |
| Overlap | 10–20% |
| Max | < model context |
| Min | > 100 tokens |
| Metadata | `doc_id, section, tenant_id, embedding_version, contains_pii, region, sensitivity` |

## 3. Scenario → strategy

| Scenario | Strategy |
| --- | --- |
| HR policy document | section + paragraph |
| Legal contract | clause-based |
| Financial report | table-aware |
| Code repository | AST (tree-sitter) |
| FAQ | sentence-based |
| Research paper | section + semantic |
| Logs / text dump | fixed + sliding window |
| Multi-language | language-aware (pysbd with language detection) |
| OCR document | paragraph + confidence filter |
| Mixed content | hybrid (structure + semantic) |

## 4. Failure scenarios

| Problem | Root cause | Fix |
| --- | --- | --- |
| Hallucination | chunk too small (no context) | increase size |
| Irrelevant answer | chunk too large (dilute signal) | reduce size |
| Missing context across chunks | no overlap | add 15% overlap |
| High cost | too many chunks | optimize size |
| Duplicate retrieval | too much overlap | reduce overlap |
| Poor ranking | bad boundaries | semantic split |
| Table broken | naive chunker | table-aware |
| Code broken | text split | AST-based |
| Mixed topics in one chunk | too-large span | semantic split |

## 5. Chunk metadata (mandatory)

```json
{
  "chunk_id": "chunk_001",
  "document_id": "doc_001",
  "tenant_id": "tenant_hr",
  "section": "Travel Policy",
  "chunk_index": 5,
  "parent_chunk_id": null,
  "embedding_model": "bge-m3",
  "embedding_version": "v3",
  "contains_pii": false,
  "pii_types": [],
  "sensitivity": "low",
  "region": "CA",
  "created_at": "2026-04-24T12:00:00Z"
}
```

Without this → no ABAC · no filtering · no audit · no re-index.

## 6. Engineering methodology layer

### TDD
| Test | Expected |
| --- | --- |
| `test_chunk_size_limit` | all chunks ≤ 800 tokens |
| `test_overlap_applied` | consecutive chunks share 10–20% |
| `test_metadata_present` | every chunk has required keys |
| `test_table_preserved` | rows/columns intact |
| `test_code_block_intact` | functions not split |
| `test_pii_detected` | SSN chunk flagged |
| `test_duplicate_avoided` | cosine similarity < 0.98 |
| `test_multi_tenant_tag` | wrong tenant = no leakage |

### BDD
```
Feature: Chunking HR policy documents

Scenario: Chunk HR document correctly
  Given an HR policy document
  When it is chunked
  Then each chunk represents a logical section
  And each chunk includes required metadata

Scenario: Prevent PII leakage
  Given a document containing SIN numbers
  When chunking is performed
  Then PII is detected and chunks are flagged
```

### MDD (Model-Driven)
- Define the `Chunk` JSON Schema first (§5)
- CI validates every chunker output against the schema
- Versioning + extensible fields for ABAC

### Output-first
- Start from desired answer shape (cited answer w/ confidence)
- Derive chunk requirements backward
- If the answer needs citations, the chunk MUST have `section` + `document_id` in metadata

## 7. Validation checklist

### Functional
- [ ] Document fully processed (no orphan text)
- [ ] Chunk boundaries valid (not broken sentences unless intended)
- [ ] Table integrity preserved
- [ ] Code integrity preserved
- [ ] Multi-format (PDF / DOCX / HTML) handled
- [ ] OCR fallback works
- [ ] Language detection works

### Size & tokens
- [ ] Chunk size in 400–800 range
- [ ] No chunk exceeds model context limit
- [ ] No chunk < 100 tokens
- [ ] Overlap 10–20%

### Semantic quality
- [ ] Single-topic chunks
- [ ] Self-standing context
- [ ] Section alignment correct
- [ ] No context loss across boundaries

### Metadata (critical)
- [ ] `document_id, chunk_id, tenant_id, section, version, timestamp, pii_flag` all present

### Security / governance
- [ ] PII detected before chunking
- [ ] PII tagged on chunks
- [ ] Tenant isolation enforced
- [ ] Restricted docs quarantined
- [ ] Injection content sanitized
- [ ] Audit log per ingestion

### Performance
- [ ] Chunking latency per doc acceptable
- [ ] Parallel processing supported
- [ ] Large file doesn't crash
- [ ] Incremental re-chunking supported

### Versioning
- [ ] `chunk_version` tagged
- [ ] `embedding_version` linked
- [ ] Rollback supported

### Retrieval impact
- [ ] Precision + recall measured on golden set
- [ ] Duplicate rate < threshold
- [ ] Ranking stable

## 8. Observability metrics

| Metric | Purpose |
| --- | --- |
| `chunking_total_chunks` | ingestion volume |
| `chunking_avg_chunk_size` | tuning |
| `chunking_failure_rate` | stability |
| `chunking_latency_seconds` | performance |
| `chunking_duplicate_rate` | dedup optimization |
| `chunking_pii_chunk_count` | security |
| `chunking_version_usage` | migration tracking |

## 9. Tools

| Need | Tools |
| --- | --- |
| Basic | LangChain, LlamaIndex |
| Semantic | BERTopic, spaCy, sentence-transformers |
| Tables | Camelot, Tabula, LayoutLMv3 |
| Code | tree-sitter |
| OCR | Tesseract, Azure OCR, AWS Textract |

## 10. Exit criteria

- [ ] `test_chunk_quality.py` + `test_chunk_metadata.py` + `test_chunk_size.py` + `test_chunk_security.py` + `test_chunk_regression.py` green.
- [ ] JSON Schema for `Chunk` in `schemas/chunk.v1.json`; CI-validated.
- [ ] Per-doc strategy override table in `governance.chunking_policies`.
- [ ] Observability metrics (§8) exported to Prometheus.
- [ ] Demo: HR policy → chunk → retrieve → cited answer with `section` in citation.

## 11. Brutal checklist

| Question | Required |
| --- | --- |
| Is chunk size configurable per tenant / doc type? | Yes |
| Is overlap used? | Yes |
| Are tables handled correctly? | Yes |
| Are chunks tagged with full metadata (§5)? | Yes |
| Can chunking be re-run with versioning? | Yes |
| Can chunking handle mixed documents? | Yes |
| Is chunking tested (TDD + BDD)? | Yes |
| Is PII detected pre-chunking? | Yes |
| Is duplicate detection running? | Yes |
