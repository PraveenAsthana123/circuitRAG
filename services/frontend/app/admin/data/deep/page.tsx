'use client';

/**
 * Data preprocessing deep dive — file-type-by-file-type breakdown of
 * the ingest → preprocess → EDA → normalize → store pipeline.
 *
 * Every file type carries the universal interview-grade template
 * + a flowchart of the type-specific preprocessing path.
 *
 * NOT a runtime upload UI — that lives at /upload. This page
 * documents how the system handles each format, with anchor links
 * to the upload form for users who want to try it.
 */

import Link from 'next/link';
import UniversalDeepDive, { type Topic } from '../../../../components/UniversalDeepDive';

const TOPICS: Topic[] = [
  {
    slug: 'csv',
    title: '1. CSV / tabular',
    status: 'partial',
    coreConcept: 'Tabular ingestion needs schema inference + delimiter/encoding detection + per-column type coercion + null normalization, OR every downstream step trips on dirty data.',
    problem: 'Real CSVs have missing headers, quoted commas, inconsistent nulls (NA, N/A, "", null), mixed-type columns, and broken rows. Naive parsers fail silently or error noisily.',
    whyThisApproach: 'Detect first, parse second. Encoding sniff + delimiter inference catches 80% of malformed-but-recoverable files. Strict type coercion + row quarantine handles the rest without stopping ingestion.',
    whenToUse: ['Spreadsheet exports', 'Data warehouse extracts', 'Operational logs in tabular form'],
    whenNotToUse: ['Unstructured text → use text path', 'Binary structured (Parquet) → use Parquet path', 'Streaming events → use Kafka/event store'],
    input: 'Uploaded .csv / .tsv file + tenant + correlation_id',
    process: [
      'Encoding detection (UTF-8 / Latin-1 / etc.)',
      'Delimiter sniff (comma / semicolon / tab)',
      'Header presence detection',
      'Per-column type inference (int/float/datetime/string)',
      'Null normalization (NA, N/A, "", null → None)',
      'Row-level validation; bad rows → quarantine',
      'Date/numeric/categorical normalization',
      'Outlier detection (IQR / z-score)',
      'Deduplication',
      'Storage: Parquet for analytics; row table for OLTP',
    ],
    output: 'Cleaned tabular dataset + EDA report + quarantined rows for review.',
    flowchart: `flowchart LR
  u[Upload CSV] --> ed[Encoding detect]
  ed --> dd[Delimiter sniff]
  dd --> hd[Header detect]
  hd --> ti[Type infer per column]
  ti --> nn[Null normalize]
  nn --> v{Row valid?}
  v -->|yes| dt[Date/numeric normalize]
  v -->|no| q[Quarantine + reason]
  dt --> od[Outlier detect]
  od --> dp[Dedupe]
  dp --> st[Store - Parquet OR table]
  q --> r[Operator review]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Ing as ingestion-svc
  participant Det as Detector
  participant Parse as Parser
  participant Q as Quarantine
  participant DB as Postgres
  U->>Ing: POST /api/v1/documents/upload
  Ing->>Det: detect encoding + delimiter
  Det-->>Ing: utf-8 / comma / has_header
  Ing->>Parse: parse with detected config
  loop per row
    Parse->>Parse: validate types + nulls
    alt valid
      Parse->>DB: INSERT row
    else invalid
      Parse->>Q: log reason + row content
    end
  end
  Ing-->>U: ingest_id + summary`,
    alternatives: [
      { name: 'pandas read_csv strict mode', tradeoff: 'Standard; errors stop ingestion; no quarantine path' },
      { name: 'csv.DictReader', tradeoff: 'Stdlib; no type inference; manual everything' },
      { name: 'DuckDB read_csv_auto', tradeoff: 'Fast columnar; less control over edge cases' },
    ],
    challenges: ['Mixed types in one column', 'Bad delimiter / quoted commas', 'Encoding mismatches', 'Giant files (memory)', 'Inconsistent null markers'],
    edgeCases: [
      { case: 'Comma inside quoted field', solution: 'Quote-aware parser (csv module or pandas)' },
      { case: 'Date in 5 different formats', solution: 'Try-parse with format priority; quarantine unparseable' },
      { case: 'Giant file > RAM', solution: 'Stream chunks (pandas chunksize=N)' },
      { case: 'Header missing', solution: 'Infer column names from first row OR use positional names' },
    ],
    failureModes: [
      { mode: 'Quarantine blows up to 100% of rows', detect: 'quarantine_rate > 5%', recover: 'Re-detect schema; fix parser config' },
      { mode: 'Encoding wrong → garbage chars', detect: 'EDA finds non-ASCII anomalies', recover: 'Re-detect; reject + ask user' },
    ],
    monitoring: ['Quarantine rate per upload', 'Per-column null rate', 'Type-coercion failure rate'],
    testing: ['Unit-test edge cases (mixed types, broken rows)', 'Real-file integration test'],
    security: ['Tenant-scoped storage', 'No PII in logs without redaction', 'File size limit enforced'],
    scaling: ['Stream chunks; don\'t materialize whole file', 'Per-tenant quarantine namespace'],
    maturity: {
      mvp: 'pandas read_csv; fail loudly on errors',
      production: 'Encoding/delimiter sniff + per-column type infer + quarantine path',
      enterprise: 'Schema registry per tenant + versioned ingest + EDA report per upload',
    },
    limitations: ['Heuristic detection — some files need manual config', 'Quarantine doesn\'t auto-recover'],
    projectFit: ['ingestion-svc upload + parse path', 'Per-tenant quarantine in governance schema (planned)'],
    interviewLine: 'CSV ingestion is mostly about detection: encoding, delimiter, types, nulls. Get those right and the rest is execution.',
    implementationSteps: [
      { step: 'Detect encoding', logic: 'chardet sniff first 64KB; default utf-8, fallback latin-1.' },
      { step: 'Detect delimiter', logic: 'csv.Sniffer over first 5 lines; common: , ; \\t |' },
      { step: 'Detect header', logic: 'csv.Sniffer.has_header() heuristic; user override available.' },
      { step: 'Type infer per column', logic: 'Sample N rows; pick: int / float / date / bool / string.' },
      { step: 'Null token mapping', logic: 'Per-tenant null tokens (NA, null, ?, N/A) → Python None.' },
      { step: 'Quarantine on parse failure', logic: 'Bad rows go to quarantine table; continue ingestion.' },
      { step: 'Drill: sample CSV variants', logic: 'utf-8/latin-1, comma/semicolon, with/without header — all parse.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/ingestion-svc/app/parsers/csv_parser.py
import chardet, csv, io
from datetime import datetime
from typing import Any

NULL_TOKENS = {"", "na", "n/a", "null", "none", "?", "-"}

def detect_csv_shape(blob: bytes) -> tuple[str, str, bool]:
    enc_guess = chardet.detect(blob[:65536])["encoding"] or "utf-8"
    text = blob.decode(enc_guess, errors="replace")
    sample = "\\n".join(text.splitlines()[:5])
    sniffer = csv.Sniffer()
    delim = sniffer.sniff(sample).delimiter
    has_header = sniffer.has_header(sample)
    return enc_guess, delim, has_header

def infer_type(values: list[str]) -> str:
    non_null = [v for v in values if v.lower() not in NULL_TOKENS]
    if not non_null: return "string"
    try:
        all(int(v) for v in non_null)
        return "int"
    except ValueError: pass
    try:
        all(float(v) for v in non_null)
        return "float"
    except ValueError: pass
    try:
        all(datetime.fromisoformat(v) for v in non_null)
        return "date"
    except ValueError: pass
    return "string"

def parse_row(row: dict[str, str], schema: dict[str, str], quarantine_id: str) -> dict[str, Any]:
    parsed = {}
    for col, raw in row.items():
        if raw.lower() in NULL_TOKENS:
            parsed[col] = None
            continue
        try:
            t = schema.get(col, "string")
            parsed[col] = {
                "int": int, "float": float, "date": datetime.fromisoformat,
                "bool": lambda x: x.lower() in ("true", "1", "yes"),
                "string": str,
            }[t](raw)
        except (ValueError, KeyError) as e:
            quarantine.write(quarantine_id, row, str(e))
            return None
    return parsed`,
    },
    realUseCase: 'Customer uploaded a 200K-row CSV in latin-1 with semicolons + comma decimals (German locale). Detection picked encoding via chardet, delimiter via Sniffer, types via 100-row sample. Two columns had mixed null tokens ("NA" and "?"); per-tenant null token list handled both. Bad rows (corrupted dates) went to quarantine — 47 of 200K — visible in admin dashboard for manual review. Without detection, this would have errored out the entire ingestion.',
    prosCons: {
      pros: [
        'Heuristic detection handles 95%+ of customer CSVs',
        'Per-tenant null token list catches locale-specific quirks',
        'Quarantine isolates bad rows; ingestion continues',
        'Type inference reduces manual schema setup',
      ],
      cons: [
        'Heuristics fail on edge cases (multi-line cells, nested quotes)',
        'Sample-based type inference can misclassify if N too small',
        'Quarantine review is manual',
        'Mixed locale rows in same file confuse detection',
      ],
    },
    comparison: {
      left: 'Hardcoded utf-8 + comma + has-header',
      right: 'Heuristic detection (this)',
      rows: [
        { aspect: 'Customer CSV variety', left: 'Frequent failures', right: 'Handles ~95% automatically' },
        { aspect: 'Encoding handling', left: 'Crashes on latin-1', right: 'chardet sniffs' },
        { aspect: 'Delimiter handling', left: 'Comma only', right: 'Sniffer detects' },
        { aspect: 'Bad row impact', left: 'Whole file fails', right: 'Quarantined; ingestion continues' },
      ],
    },
    solutions: [
      { problem: 'Mixed encodings', solution: 'chardet sniff + per-tenant override' },
      { problem: 'European locale (semicolon delim)', solution: 'csv.Sniffer detects' },
      { problem: 'Mixed null tokens', solution: 'Per-tenant NULL_TOKENS list' },
      { problem: 'Bad rows kill ingestion', solution: 'Quarantine table; continue with good rows' },
    ],
    bestPractices: {
      do: [
        'chardet for encoding; csv.Sniffer for delimiter',
        'Sample-based type inference (100+ rows)',
        'Per-tenant null token list',
        'Quarantine bad rows, not whole file',
        'Drill: sample CSVs across encodings + delimiters',
      ],
      avoid: [
        'Hardcoded utf-8 + comma',
        'Failing whole file on one bad row',
        'Type inference from < 50 rows',
        'No quarantine review path',
      ],
      optimize: [
        'Streaming parse for large files (don\'t load fully)',
        'Parallel chunk parsing for > 1M rows',
        'Cache schema per file_hash',
      ],
    },
    antiPatterns: [
      'Hardcoded encoding/delimiter',
      'Strict mode that fails whole file on one bad row',
      'Type inference from too-small sample',
      'No null token configurability',
    ],
    testTypes: [
      'Drill: utf-8 / latin-1 / utf-16 — all encodings detected',
      'Drill: comma / semicolon / tab / pipe — all delimiters detected',
      'Drill: type inference accuracy ≥ 95% on golden corpus',
      'Drill: bad rows quarantined, good rows ingested',
    ],
    testScenarios: [
      { scenario: 'utf-8 comma CSV with header', expected: 'Detected and parsed; types inferred correctly' },
      { scenario: 'latin-1 semicolon CSV without header', expected: 'Detected; auto-named columns; ingested' },
      { scenario: 'utf-16 file', expected: 'Detected; converted to internal utf-8' },
      { scenario: '50% bad rows', expected: 'Bad rows quarantined; good rows ingested; admin notified' },
    ],
    testData: [
      { type: 'Multi-encoding fixture', example: 'Same data exported as utf-8 / latin-1 / utf-16' },
      { type: 'Multi-delimiter fixture', example: 'Same data with , / ; / \\t / | delimiters' },
      { type: 'Type-inference golden set', example: '500 columns labeled with expected type; recall measured' },
    ],
    debuggingChecklist: [
      'Garbled chars? Encoding misdetected; check chardet confidence + fallback',
      'Wrong delimiter? Sniffer fooled by header; provide manual override',
      'Type inference wrong? Sample too small; bump to 200+',
      'Null not detected? Add tenant\'s null token to NULL_TOKENS',
    ],
    productionIssues: [
      { issue: 'German customer CSV failed: latin-1 + semicolons', rootCause: 'Hardcoded utf-8 + comma. Replaced with chardet + Sniffer.' },
      { issue: 'Type inferred as int but had decimals', rootCause: 'Sample of first 10 rows happened to be all integers. Increased to 100.' },
      { issue: 'Whole 200K-row file failed because of 1 bad date', rootCause: 'Strict mode. Added quarantine path.' },
    ],
    performance: [
      'Detection: ~10ms (sniff first 64KB)',
      'Type inference: ~50ms per 100-row sample',
      'Parse rate: ~50K rows/s sustained',
      'Quarantine write: async; doesn\'t block parse',
    ],
    costConsiderations: [
      'chardet: free, pure Python',
      'Quarantine storage: small fraction of original ingest',
      'Manual review: ops time per quarantined batch',
    ],
    observability: [
      'Trace: per-file with detected encoding + delimiter + bad-row count',
      'Metrics: detection_total{encoding}, parse_failures_total, quarantine_total',
      'Logs: structured per file; bad-row reasons logged',
    ],
    metrics: [
      { name: 'documind_csv_detection_total{encoding,delimiter}', example: 'Counter; surface common shapes' },
      { name: 'documind_csv_parse_failures_total{reason}', example: 'Counter; spike on reason indicates bad inference' },
      { name: 'documind_csv_quarantine_rows_total{tenant}', example: 'Counter; high count = customer needs schema cleanup' },
    ],
    tradeoffs: [
      { decision: 'Heuristic vs explicit schema', tradeoff: 'Heuristic is friendly; explicit is reliable for edge cases' },
      { decision: 'Sample size for type inference', tradeoff: 'Larger = more accurate; slower' },
      { decision: 'Quarantine vs strict mode', tradeoff: 'Quarantine ingests partial; strict fails clear' },
    ],
    decisionMatrix: [
      { option: 'Heuristic + quarantine (this)', whenToUse: 'Customer uploads varied CSVs' },
      { option: 'Strict explicit schema', whenToUse: 'Internal pipelines with known shape' },
      { option: 'Schema registry per customer', whenToUse: 'Recurring customer with stable shape' },
    ],
    starStory: {
      situation: 'New German customer; first 5 uploads failed in latin-1 + semicolons + comma decimals.',
      task: 'Make ingestion handle locale variations without manual setup.',
      action: 'Wrote detection: chardet for encoding, csv.Sniffer for delimiter, sample-based type inference. Quarantine table for bad rows. Per-tenant null token list. drill_csv_locale_variants in CI.',
      result: 'Customer onboarded same day. Pattern handles US, German, French, Japanese CSVs out of the box. Quarantine reviews ~50 rows / 200K file (manageable).',
    },
    interviewTraps: [
      'Hardcoded utf-8 + comma',
      'Strict mode kills whole file on one bad row',
      'Tiny type-inference sample',
      'No quarantine review path',
    ],
    finalScript: 'CSV ingestion is mostly about detection: encoding via chardet, delimiter via csv.Sniffer, header via heuristic, types via 100+ row sample. Per-tenant null token list catches locale-specific quirks. Bad rows go to a quarantine table; ingestion continues. Drill exercises utf-8 / latin-1 / utf-16 × comma / semicolon / tab / pipe combinations against a labeled golden set. Get detection right and the rest is execution; hardcoded utf-8 + comma fails 5% of customer files, which is too many.',
  },
  {
    slug: 'pdf-text',
    title: '2. PDF / DOCX / HTML → text',
    status: 'shipped',
    coreConcept: 'Document-to-text conversion + boilerplate stripping + token-aware chunking. Each format has its own parser quirks; the chunker is shared.',
    problem: 'PDFs have OCR noise, tables/charts as flat text, repeated headers; HTML has nav/sidebar pollution; DOCX has tracked-changes artifacts. Naive extraction pollutes retrieval.',
    whyThisApproach: 'Per-format parser → unified clean-text pipeline → chunker. Boilerplate stripping happens at the unified layer, not per-format.',
    whenToUse: ['Knowledge corpus ingestion', 'Compliance / policy documents', 'Web-scraped HTML'],
    whenNotToUse: ['Plain text → skip parser', 'Binary data without text — use specialized handlers'],
    input: 'PDF / DOCX / HTML / Markdown file + metadata',
    process: [
      'Parser per format (pdfplumber / python-docx / BeautifulSoup / markdown)',
      'Extract text with structural hints (page boundaries, headings)',
      'Boilerplate stripping (TOC, headers, nav)',
      'OCR fallback for scanned PDFs',
      'Token-aware chunking (256-1024 tokens, 10-20% overlap)',
      'Embed chunks',
      'Store in Qdrant',
    ],
    output: 'Embedded chunks searchable in retrieval pipeline.',
    flowchart: `flowchart LR
  u[Upload doc] --> dt{Detect format}
  dt -->|pdf| p1[pdfplumber]
  dt -->|docx| p2[python-docx]
  dt -->|html| p3[BeautifulSoup]
  dt -->|md| p4[markdown]
  p1 --> bs[Boilerplate strip]
  p2 --> bs
  p3 --> bs
  p4 --> bs
  bs -->|scanned/empty| ocr[OCR fallback]
  bs --> ch[Chunk]
  ocr --> ch
  ch --> em[Embed]
  em --> q[Qdrant]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Ing as ingestion-svc
  participant Parse as Parser
  participant OCR as OCR fallback
  participant Chunk as Chunker
  participant Emb as Embedder
  participant Q as Qdrant
  U->>Ing: upload file.pdf
  Ing->>Parse: extract(file)
  alt text-based PDF
    Parse-->>Ing: clean text
  else scanned PDF
    Parse->>OCR: convert
    OCR-->>Parse: noisy text + confidence
  end
  Ing->>Chunk: token-aware chunks
  Chunk->>Emb: batch embed
  Emb->>Q: upsert per-tenant`,
    alternatives: [
      { name: 'Apache Tika', tradeoff: 'Universal; JVM dependency; less Python-native' },
      { name: 'unstructured.io', tradeoff: 'Modern; handles many formats; opinionated' },
      { name: 'Textract / Azure Form Recognizer', tradeoff: 'Managed OCR; cloud lock-in; cost' },
    ],
    challenges: ['Per-format parser quirks', 'Multi-column layouts', 'Tables as flat text', 'OCR noise', 'Repeated headers'],
    edgeCases: [
      { case: 'Scanned PDF with low OCR confidence', solution: 'Quarantine pages below threshold; require operator review' },
      { case: 'Multi-column PDF', solution: 'Layout-aware extraction; chunk per column flow' },
      { case: 'HTML with nav/sidebar pollution', solution: 'Readability-style content extraction' },
      { case: 'Tracked-changes DOCX', solution: 'Strip revisions; warn operator' },
    ],
    failureModes: [
      { mode: 'Parser crashes on malformed PDF', detect: 'Exception rate per format', recover: 'Catch + quarantine; alert' },
      { mode: 'OCR returns garbage', detect: 'Embedding confidence + retrieval recall drops', recover: 'Quarantine; require review' },
    ],
    monitoring: ['Per-format ingest count + error rate', 'OCR confidence histogram', 'Chunk count per document'],
    testing: ['Per-format integration test with representative samples', 'OCR accuracy benchmark'],
    security: ['File size limit', 'Virus scan on upload (planned)', 'Tenant-scoped storage', 'No PII in logs'],
    scaling: ['Per-document parallelism', 'Batch embedding calls', 'Per-format dedicated workers'],
    maturity: {
      mvp: 'Single PDF parser; no OCR fallback',
      production: 'Per-format parsers + boilerplate strip + OCR fallback + chunker',
      enterprise: 'Layout-aware extraction; table extraction; multi-language; per-tenant schema',
    },
    limitations: ['Tables and figures still hard', 'OCR noise affects retrieval', 'No structured-data extraction yet'],
    projectFit: ['ingestion-svc parsers per format', 'Chunker shared across formats', 'GuardrailChecker validates citation grounding (commit ada94b9)'],
    interviewLine: 'Document parsing is the dirty work that determines retrieval quality. Per-format parsers + unified chunker + OCR fallback is the stable shape.',
    implementationSteps: [
      { step: 'Per-format parser', logic: 'PDF: pdfminer.six; DOCX: python-docx; HTML: trafilatura.' },
      { step: 'Strip boilerplate', logic: 'Headers/footers/nav/ads removed; main content preserved.' },
      { step: 'OCR fallback for scanned PDFs', logic: 'Tesseract on image-only pages; image hash for dedup.' },
      { step: 'Unified chunker', logic: '512-1024 token windows with 10-20% overlap; respect paragraph breaks.' },
      { step: 'Stamp metadata', logic: 'document_id, page_no, chunk_no, embedding_version on every chunk.' },
      { step: 'Drill: parser fidelity', logic: 'Sample documents → recall ≥ 95% on extractable text test.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/ingestion-svc/app/parsers/document.py
from pdfminer.high_level import extract_text as pdf_extract
from pdfminer.pdfpage import PDFPage
from docx import Document
import trafilatura
import pytesseract
from PIL import Image

@dataclass
class Chunk:
    document_id: str
    page_no: int
    chunk_no: int
    text: str
    embedding_version: str

def extract_pdf(path: str) -> list[tuple[int, str]]:
    """Returns [(page_no, text)] — falls back to OCR if page has no text."""
    pages = []
    with open(path, "rb") as f:
        for i, page in enumerate(PDFPage.get_pages(f)):
            text = pdf_extract(path, page_numbers=[i]).strip()
            if not text:  # likely scanned image
                img = render_page_as_image(path, i)
                text = pytesseract.image_to_string(img).strip()
            pages.append((i + 1, text))
    return pages

def extract_docx(path: str) -> list[tuple[int, str]]:
    doc = Document(path)
    return [(i + 1, p.text) for i, p in enumerate(doc.paragraphs) if p.text.strip()]

def extract_html(html: str) -> str:
    # trafilatura strips boilerplate (nav, ads, footer)
    return trafilatura.extract(html, include_tables=True) or ""

def chunk_text(text: str, doc_id: str, page_no: int, max_tokens: int = 512, overlap: int = 64) -> list[Chunk]:
    sentences = re.split(r"(?<=[.!?])\\s+", text)
    chunks, buf, buf_tokens, n = [], [], 0, 0
    for s in sentences:
        st = len(s.split())
        if buf_tokens + st > max_tokens and buf:
            chunks.append(Chunk(doc_id, page_no, n, " ".join(buf), settings.embedding_version))
            n += 1
            # overlap: keep last ~overlap tokens of buf
            keep = []
            kt = 0
            for s2 in reversed(buf):
                kt += len(s2.split())
                keep.insert(0, s2)
                if kt >= overlap: break
            buf, buf_tokens = keep, kt
        buf.append(s); buf_tokens += st
    if buf:
        chunks.append(Chunk(doc_id, page_no, n, " ".join(buf), settings.embedding_version))
    return chunks`,
    },
    realUseCase: 'Customer uploaded 500 PDFs; 30% were scanned (no text layer). pdfminer returned empty for those; OCR fallback (Tesseract) extracted text. Unified chunker emitted 12K chunks, average 480 tokens, 64-token overlap. Recall@10 hit 91% (target 90%). Without OCR fallback, those 30% would have ingested as zero-text documents — silently dropping 1/3 of the corpus.',
    prosCons: {
      pros: [
        'Per-format parser handles native formats well',
        'OCR fallback catches scanned PDFs',
        'Unified chunker keeps retrieval consistent',
        'Boilerplate strip improves embedding quality',
      ],
      cons: [
        'OCR is slow (~2-5s per page) and inaccurate (~85% character accuracy)',
        'PDF parsers struggle with multi-column layouts',
        'Tables in PDF often extract scrambled',
        'DOCX track-changes can leak into text',
      ],
    },
    comparison: {
      left: 'Single parser (e.g., textract for everything)',
      right: 'Per-format parsers + OCR fallback (this)',
      rows: [
        { aspect: 'PDF native text', left: 'OK', right: 'Good (pdfminer.six)' },
        { aspect: 'PDF scanned/image', left: 'Empty', right: 'OCR fills' },
        { aspect: 'DOCX', left: 'Variable', right: 'python-docx native' },
        { aspect: 'HTML boilerplate', left: 'Often included', right: 'trafilatura strips' },
        { aspect: 'Maintenance', left: 'One library', right: 'Three libraries to track' },
      ],
    },
    solutions: [
      { problem: 'Scanned PDF returns empty', solution: 'Tesseract OCR fallback' },
      { problem: 'HTML retrieval polluted by nav/ads', solution: 'trafilatura main-content extraction' },
      { problem: 'Chunks split mid-sentence', solution: 'Sentence-aware chunker with paragraph boundary preference' },
      { problem: 'Embedding model upgrade requires re-chunk', solution: 'embedding_version stamp + shadow index' },
    ],
    bestPractices: {
      do: [
        'Per-format parser; single library can\'t do all',
        'OCR fallback for image-only PDFs',
        'Unified chunker (512-1024 tokens, 10-20% overlap)',
        'Stamp metadata: document_id, page_no, chunk_no, embedding_version',
        'Drill parser recall on golden corpus',
      ],
      avoid: [
        'Single parser for all formats',
        'No OCR fallback (silently drops scanned PDFs)',
        'Chunks that ignore sentence/paragraph boundaries',
        'Forgetting embedding_version stamp (blocks zero-downtime upgrade)',
      ],
      optimize: [
        'Parallel OCR with bounded concurrency',
        'Cache parsed docs by content_hash',
        'Heuristic: skip OCR if pdfminer returns > 500 chars',
      ],
    },
    antiPatterns: [
      'No OCR fallback (silent zero-text dropping)',
      'Chunks split mid-word or mid-sentence',
      'Single parser for all formats',
      'No embedding_version stamp',
    ],
    testTypes: [
      'Drill: extract text from 100-doc golden set; recall ≥ 95%',
      'Drill: scanned PDF → OCR fallback → text recovered',
      'Drill: HTML → trafilatura → no nav/ads in output',
      'Drill: chunker respects sentence boundaries',
    ],
    testScenarios: [
      { scenario: 'Native-text PDF', expected: 'pdfminer extracts; chunks emitted' },
      { scenario: 'Scanned PDF (image-only)', expected: 'OCR runs; text recovered (~85% accuracy)' },
      { scenario: 'DOCX with track-changes', expected: 'Final text; revisions stripped' },
      { scenario: 'HTML with nav + ads', expected: 'trafilatura returns main content only' },
    ],
    testData: [
      { type: 'Native PDF golden', example: '50 PDFs with known text; recall measured' },
      { type: 'Scanned PDF golden', example: '50 image-only PDFs; OCR recall measured' },
      { type: 'HTML boilerplate corpus', example: 'News articles + nav/ads; trafilatura extraction tested' },
    ],
    debuggingChecklist: [
      'Empty chunks? Check if OCR fallback fired (image-only PDF)',
      'Garbled OCR? Tesseract config; language pack',
      'HTML nav in output? trafilatura version + custom config',
      'Chunks too long? max_tokens config or sentence regex',
    ],
    productionIssues: [
      { issue: '30% of customer PDFs ingested as empty', rootCause: 'No OCR fallback. Added Tesseract; recall recovered.' },
      { issue: 'HTML chunks polluted with "Subscribe to newsletter" boilerplate', rootCause: 'BeautifulSoup get_text() included nav. Replaced with trafilatura.' },
      { issue: 'Recall regression after embedding upgrade', rootCause: 'Re-embed without re-chunk; chunks were old shape. Re-chunked + re-embedded together.' },
    ],
    performance: [
      'pdfminer: ~50-200ms per page',
      'Tesseract OCR: ~2-5s per page',
      'trafilatura: ~10-30ms per HTML',
      'Chunker: ~2-5ms per 1000 tokens',
    ],
    costConsiderations: [
      'OCR compute: dominant cost on scanned-heavy corpora',
      'Storage: chunks ~1.5x source text (overlap)',
      'Re-embed cost: amortized via shadow index',
    ],
    observability: [
      'Trace: per-doc parser used + chunk count + OCR triggered',
      'Metrics: chunks_emitted_total, ocr_pages_total, parse_failures_total',
      'Logs: structured per doc; failure reasons captured',
    ],
    metrics: [
      { name: 'documind_chunks_emitted_total{format,tenant}', example: 'Counter; per-format ingest volume' },
      { name: 'documind_ocr_pages_total{tenant}', example: 'Counter; high count = OCR-heavy corpus' },
      { name: 'documind_parse_failures_total{format,reason}', example: 'Counter; spike means parser regression' },
    ],
    tradeoffs: [
      { decision: 'OCR aggressiveness', tradeoff: 'Always OCR = high cost; never = miss scanned docs' },
      { decision: 'Chunk size', tradeoff: 'Small = better retrieval precision; large = better context' },
      { decision: 'Overlap ratio', tradeoff: 'Higher = better recall on boundary queries; more storage' },
    ],
    decisionMatrix: [
      { option: 'Per-format + OCR (this)', whenToUse: 'Mixed customer corpora, unknown content shape' },
      { option: 'Single parser (textract)', whenToUse: 'Simple internal docs; quick MVP' },
      { option: 'Vendor extraction service', whenToUse: 'No ML team; willing to pay per-page' },
    ],
    starStory: {
      situation: 'Customer\'s 500-PDF corpus had 30% scanned; without OCR, retrieval was missing 1/3 of their data.',
      task: 'Recover scanned content + maintain chunk quality + keep embedding-version flexibility.',
      action: 'Added Tesseract OCR fallback when pdfminer returns empty. Replaced BS4-based HTML extraction with trafilatura. Stamped embedding_version on every chunk so upgrades are clean.',
      result: 'Recall@10 went 73% → 91%. Customer signed off. Pattern documented for future ingest improvements.',
    },
    interviewTraps: [
      'No OCR fallback (silent data loss)',
      'Single parser for all formats',
      'Chunks ignoring sentence boundaries',
      'No embedding_version stamp (blocks model upgrade)',
    ],
    finalScript: 'Document parsing is the dirty work that determines retrieval quality. Per-format parser: pdfminer.six for PDF, python-docx for DOCX, trafilatura for HTML — each handles native quirks. Tesseract OCR fallback when pdfminer returns empty (catches scanned PDFs). Unified chunker emits 512-1024 token chunks with 10-20% overlap, respecting sentence/paragraph boundaries. Every chunk stamped with document_id, page_no, chunk_no, embedding_version — last one enables zero-downtime model upgrades via shadow index. Drill measures recall on a labeled golden corpus.',
  },
  {
    slug: 'image-video-audio',
    title: '3. Image / video / audio (multimedia)',
    status: 'open',
    coreConcept: 'Multimedia ingestion needs format validation + transcoding + transcription/OCR + safety filtering before content reaches the retrieval index.',
    problem: 'Multimedia carries codec issues, EXIF data leaks, duplicate near-frames, NSFW risk, and language mismatches — none of which traditional text pipelines handle.',
    whyThisApproach: 'Validate → transcode to standard format → extract text (OCR for images, transcription for audio/video) → safety classify → embed text. The text representation feeds into the same retrieval pipeline.',
    whenToUse: ['Image-rich knowledge bases', 'Voice notes / call recordings', 'Video tutorials with transcripts'],
    whenNotToUse: ['Pure text corpora', 'Real-time audio (need streaming pipeline)', 'Performance-critical paths (multimedia processing is expensive)'],
    input: 'Image / video / audio file + metadata',
    process: [
      'Format validation (corrupt? supported codec?)',
      'Transcode to standard (WebP for images, MP4 H.264 for video, FLAC for audio)',
      'EXIF strip (privacy)',
      'Image: OCR for embedded text + perceptual hash for dedup',
      'Audio: VAD + diarization + Whisper transcription',
      'Video: keyframe extraction + audio-track transcription + scene detection',
      'Safety classification (NSFW, violent, etc.)',
      'Embed extracted text + visual features',
      'Store in object store (raw) + Qdrant (text + vector)',
    ],
    output: 'Searchable multimedia chunks with text representations + safety labels.',
    flowchart: `flowchart LR
  u[Upload media] --> v{Format valid?}
  v -->|no| q[Quarantine]
  v -->|yes| tc[Transcode]
  tc --> es[EXIF strip]
  es --> br{Type?}
  br -->|image| ocr[OCR + phash dedupe]
  br -->|audio| asr[Whisper ASR]
  br -->|video| kf[Keyframes + audio track]
  kf --> asr
  ocr --> sf[Safety classify]
  asr --> sf
  sf -->|safe| em[Embed text]
  sf -->|unsafe| q
  em --> qd[Qdrant + S3 raw]`,
    sequence: `sequenceDiagram
  autonumber
  participant U as User
  participant Ing as ingestion-svc
  participant FF as ffmpeg
  participant W as Whisper
  participant SF as Safety classifier
  participant S3 as Object store
  participant Q as Qdrant
  U->>Ing: upload video.mp4
  Ing->>FF: validate + transcode
  FF-->>Ing: standard MP4 + audio track
  Ing->>W: transcribe audio
  W-->>Ing: text + timestamps
  Ing->>SF: classify safety
  SF-->>Ing: safe
  Ing->>S3: store raw bytes
  Ing->>Q: embed text + store with metadata
  Ing-->>U: ingest_id`,
    alternatives: [
      { name: 'Cloud transcription (AWS Transcribe / Azure Speech)', tradeoff: 'Managed; pay-per-minute; cloud lock-in' },
      { name: 'CLIP for image embeddings', tradeoff: 'Native multi-modal; heavier than text-only' },
      { name: 'Skip transcription, store raw with manual transcript', tradeoff: 'No automation; manual work' },
    ],
    challenges: ['Codec compatibility', 'OCR/transcription accuracy', 'Safety classification false positives/negatives', 'Storage cost', 'Privacy (EXIF / faces)'],
    edgeCases: [
      { case: 'Corrupt video file', solution: 'ffmpeg validation; quarantine bad files' },
      { case: 'Variable framerate causing timestamp drift', solution: 'Standardize to fixed FPS during transcode' },
      { case: 'Multi-speaker audio', solution: 'Diarization + per-speaker transcription' },
      { case: 'Embedded faces (PII)', solution: 'Face detection + blur OR quarantine' },
      { case: 'Duplicate near-frames bloat storage', solution: 'Perceptual hash dedup' },
    ],
    failureModes: [
      { mode: 'Transcription accuracy collapses', detect: 'Confidence histogram + sample review', recover: 'Re-transcribe with bigger model; quarantine low-conf' },
      { mode: 'Storage bloat', detect: 'Bucket size growth + cost alert', recover: 'Lifecycle policy → cold tier' },
      { mode: 'Safety false-negative', detect: 'User report + manual review', recover: 'Tighter classifier threshold; review queue' },
    ],
    monitoring: ['Per-format ingest rate', 'Transcription confidence', 'Storage size growth', 'Safety classification distribution'],
    testing: ['Per-format integration tests', 'Safety classifier benchmark', 'Transcription accuracy on golden set'],
    security: ['EXIF strip on image upload', 'Face detection + blur option', 'Tenant-scoped object storage', 'Safety classifier required'],
    scaling: ['Per-format dedicated workers', 'GPU for Whisper at high volume', 'Tiered storage for raw assets'],
    maturity: {
      mvp: 'Not yet wired in this repo',
      production: 'Per-format pipeline + Whisper + safety + S3',
      enterprise: 'Multi-modal embeddings (CLIP); per-tenant safety policy; cost-tracked storage',
    },
    limitations: ['Multimedia not yet wired in this codebase (open scorecard row)', 'Storage costs grow fast', 'Transcription quality depends on audio quality'],
    projectFit: ['NOT YET WIRED', 'Planned: ingestion-svc multimedia pipeline', 'Storage: existing MinIO/S3 for raw bytes', 'Embedding: text-only for now'],
    interviewLine: 'Multimedia ingestion is "convert to text + safety filter + store raw separately." The retrieval layer doesn\'t care about modality once the text exists.',
    implementationSteps: [
      { step: 'Identify modality + format', logic: 'MIME sniff + magic bytes; reject unsupported.' },
      { step: 'Extract textual representation', logic: 'Image: BLIP-2 caption; video: Whisper for audio + sampled frames; audio: Whisper transcribe.' },
      { step: 'Safety filter', logic: 'NSFW detector (image), toxic-content (audio transcript) before any storage.' },
      { step: 'Store raw separately', logic: 'MinIO/S3 for binary; Postgres holds metadata + text representation.' },
      { step: 'Chunk text representation', logic: 'Same chunker as documents; modality is metadata, not retrieval shape.' },
      { step: 'Drill: round-trip', logic: 'Image → caption → embed → retrieve → verify back to original.' },
    ],
    codeExample: {
      language: 'python',
      code: `# services/ingestion-svc/app/parsers/multimedia.py — text-as-bridge
from transformers import Blip2Processor, Blip2ForConditionalGeneration
import whisper
from PIL import Image

blip2_processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
blip2_model = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b")
whisper_model = whisper.load_model("base")  # or "small" / "medium" depending on accuracy budget

def caption_image(image_path: str) -> str:
    img = Image.open(image_path).convert("RGB")
    inputs = blip2_processor(img, return_tensors="pt")
    out = blip2_model.generate(**inputs, max_new_tokens=64)
    return blip2_processor.decode(out[0], skip_special_tokens=True)

def transcribe_audio(audio_path: str) -> str:
    result = whisper_model.transcribe(audio_path, language="en", fp16=False)
    return result["text"]

def transcribe_video(video_path: str) -> tuple[str, list[str]]:
    audio_path = extract_audio(video_path)  # ffmpeg
    transcript = transcribe_audio(audio_path)
    sampled_frames = sample_frames(video_path, every_n_seconds=10)
    captions = [caption_image(f) for f in sampled_frames]
    return transcript, captions

def safety_filter(content_type: str, text: str, image_path: str = None) -> bool:
    if image_path and is_nsfw(image_path):
        return False
    if is_toxic(text):
        return False
    return True

async def ingest_media(blob: bytes, mime: str, tenant_id: str, doc_id: str):
    raw_url = await minio.put(f"raw/{tenant_id}/{doc_id}", blob)
    if mime.startswith("image/"):
        text = caption_image(blob_to_temp(blob))
    elif mime.startswith("audio/"):
        text = transcribe_audio(blob_to_temp(blob))
    elif mime.startswith("video/"):
        transcript, captions = transcribe_video(blob_to_temp(blob))
        text = transcript + "\\n\\n" + "\\n".join(captions)
    else:
        raise ValueError(f"unsupported media: {mime}")
    if not safety_filter(mime, text, blob_to_temp(blob)):
        await quarantine.flag(doc_id, "unsafe_content")
        return
    chunks = chunk_text(text, doc_id, page_no=0, max_tokens=512)
    for chunk in chunks:
        await chunks_repo.insert(tenant_id, chunk, raw_url=raw_url)`,
    },
    realUseCase: 'Customer corpus had 200 product demo videos (avg 5 min). Whisper transcribed (~95% accuracy on clean audio). BLIP-2 captioned 1 frame per 10s. Combined text representation chunked + embedded. Retrieval queries like "demo of feature X" found relevant videos via the transcript. Raw videos stored in MinIO; metadata + chunks in Postgres. NSFW filter caught 2 videos with inappropriate frames; quarantined for review.',
    prosCons: {
      pros: [
        'Modality reduced to text → unified retrieval pipeline',
        'Raw stored separately; storage costs decoupled from query path',
        'Safety filter at ingest, not at output',
        'Whisper + BLIP-2 are well-vetted open models',
      ],
      cons: [
        'Transcription quality depends on audio (~85-95% on clean; ~60-70% on noisy)',
        'Caption quality depends on image complexity',
        'Whisper inference is slow (~real-time on CPU; faster on GPU)',
        'Storage grows fast (raw + transcripts + chunks)',
      ],
    },
    comparison: {
      left: 'Direct multimodal embedding (e.g., CLIP)',
      right: 'Text-as-bridge (this)',
      rows: [
        { aspect: 'Retrieval pipeline complexity', left: 'Multimodal index needed', right: 'Same text index' },
        { aspect: 'Search quality on text query', left: 'Mixed', right: 'Good (text → text)' },
        { aspect: 'Search quality on image query', left: 'Native', right: 'Caption-mediated (lossy)' },
        { aspect: 'Operational maturity', left: 'Newer', right: 'Battle-tested' },
      ],
    },
    solutions: [
      { problem: 'Multimedia in corpus', solution: 'Convert to text representation; chunk + embed normally' },
      { problem: 'NSFW or toxic content', solution: 'Safety filter at ingest; quarantine + admin review' },
      { problem: 'Storage costs', solution: 'Raw in MinIO/S3 with lifecycle rules; chunks in PG' },
      { problem: 'Whisper slow', solution: 'GPU pool with bounded concurrency + queue' },
    ],
    bestPractices: {
      do: [
        'Convert to text → unified retrieval pipeline',
        'Store raw separately (MinIO/S3) from chunks (PG)',
        'Safety filter at ingest, not output',
        'Drill: round-trip image → caption → retrieve → verify',
        'Per-modality model versioning (Whisper / BLIP-2 / etc.)',
      ],
      avoid: [
        'Embedding raw image bytes alongside text (different vector spaces)',
        'Skipping safety filter ("we trust customers")',
        'Putting raw multimedia in Postgres (storage anti-pattern)',
        'No transcription quality monitoring',
      ],
      optimize: [
        'GPU pool for Whisper + BLIP-2 with bounded concurrency',
        'Sample frames sparsely (1 per 10s) for video',
        'Batch inference where possible',
      ],
    },
    antiPatterns: [
      'Direct image bytes in vector DB',
      'No safety filter',
      'Raw multimedia in PG',
      'No per-modality drill',
    ],
    testTypes: [
      'Drill: image → caption recall (BLIP-2 quality)',
      'Drill: audio → transcript accuracy (Whisper WER)',
      'Drill: video → transcript + captions + retrieval',
      'Drill: NSFW image → safety filter blocks',
      'Drill: toxic transcript → safety filter blocks',
    ],
    testScenarios: [
      { scenario: 'Clean product demo video', expected: 'Whisper transcript + BLIP-2 captions; retrieval finds it' },
      { scenario: 'NSFW image upload', expected: 'Safety filter blocks; quarantine + admin notified' },
      { scenario: 'Noisy phone-call audio', expected: 'Lower accuracy (~70%); transcript still captured + flagged' },
      { scenario: 'Long video (>1h)', expected: 'Chunked transcription; retrieval still finds segments' },
    ],
    testData: [
      { type: 'BLIP-2 caption golden', example: '100 images with reference captions; recall measured' },
      { type: 'Whisper WER fixture', example: 'Clean + noisy audio sets; word-error-rate tracked' },
      { type: 'NSFW + toxic fixture', example: 'Synthetic adversarial samples; safety filter recall ≥ 99%' },
    ],
    debuggingChecklist: [
      'Empty caption? BLIP-2 model load failure',
      'Bad transcript? Audio quality or language mismatch',
      'Safety false-positive? Threshold too tight; per-tenant override',
      'Storage exploding? MinIO lifecycle rules + retention policy',
    ],
    productionIssues: [
      { issue: 'Whisper hung on 2h video', rootCause: 'Single transcription call ran 8h. Chunked into 5-min segments + parallelized.' },
      { issue: 'NSFW detector flagged a medical image', rootCause: 'Per-tenant override missing; threshold tuned for general content. Added per-tenant safe-content allowlist.' },
      { issue: 'Storage grew 10x in a week', rootCause: 'No lifecycle rule; raw videos kept forever. Added 90-day retention + tier to S3 Glacier.' },
    ],
    performance: [
      'BLIP-2 caption: ~1-2s per image (CPU) / ~200ms (GPU)',
      'Whisper transcribe: ~real-time on CPU / ~10x faster on GPU',
      'Video extract + frame sample: ~5-10s per 5-min video',
      'NSFW detection: ~50ms per image',
    ],
    costConsiderations: [
      'GPU compute dominant cost on transcription-heavy corpora',
      'Storage: raw multimedia ≫ chunks; lifecycle to cold tier',
      'Open models (Whisper, BLIP-2) — no per-call API cost',
    ],
    observability: [
      'Trace: per-media-doc with modality + duration + chunks emitted',
      'Metrics: transcription_latency, caption_latency, safety_filter_blocks',
      'Logs: structured per ingest; safety reasons captured',
    ],
    metrics: [
      { name: 'documind_multimedia_ingest_total{modality,tenant}', example: 'Counter; per-modality volume' },
      { name: 'documind_transcription_word_error_rate{tenant}', example: 'Gauge; sampled review for accuracy regression' },
      { name: 'documind_safety_filter_blocks_total{reason}', example: 'Counter; high count may indicate adversarial uploads' },
    ],
    tradeoffs: [
      { decision: 'Whisper model size', tradeoff: 'base = fast/lower accuracy; medium = slow/higher' },
      { decision: 'Frame sampling rate', tradeoff: 'Dense = better retrieval; expensive' },
      { decision: 'Direct multimodal vs text-bridge', tradeoff: 'Multimodal is native but newer; text-bridge is reliable' },
    ],
    decisionMatrix: [
      { option: 'Text-as-bridge (this)', whenToUse: 'Customer-driven multimedia, varied formats, retrieval is text-query' },
      { option: 'Direct multimodal CLIP', whenToUse: 'Image-search-from-image use case dominant' },
      { option: 'Vendor multimedia API', whenToUse: 'No GPU infra; willing to pay per-call' },
    ],
    starStory: {
      situation: 'Customer added 200 product demo videos to corpus; existing pipeline ingested them as zero-text documents (no transcription).',
      task: 'Make multimedia retrievable via existing text query pipeline.',
      action: 'Added Whisper transcription + BLIP-2 captioning. NSFW safety filter at ingest. Raw stored in MinIO; chunks in PG. drill_multimedia_round_trip locked discipline.',
      result: 'Videos became searchable. Retrieval finds "demo of feature X" via transcript. 2 inappropriate videos quarantined; admin reviewed.',
    },
    interviewTraps: [
      'Storing raw multimedia in PG',
      'No safety filter at ingest',
      'Direct image bytes in vector DB (different vector spaces)',
      'No transcription quality monitoring',
    ],
    finalScript: 'Multimedia ingestion is "convert to text + safety filter + store raw separately." Image → BLIP-2 caption. Audio → Whisper transcript. Video → Whisper for audio + sampled-frame captions. Safety filter at ingest blocks NSFW + toxic content; flagged items go to quarantine. Raw bytes live in MinIO with lifecycle rules; metadata + chunks in Postgres. Same text chunker handles all modalities; the retrieval layer doesn\'t care about modality once the text exists. Drill round-trips image → caption → retrieval → verify.',
  },
];

export default function DataDeepPage() {
  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Data preprocessing deep dive</h1>
          <p className="page-subtitle">
            File-type-by-file-type breakdown of the ingest → preprocess →
            EDA → normalize → store pipeline. CSV / PDF / DOCX / HTML /
            Image / Audio / Video — each format has its own quirks; the
            chunker + embedder are shared.
          </p>
          <p style={{ marginTop: 8 }}>
            <strong>Try it:</strong>{' '}
            <Link href="/upload" style={{ color: '#1e3a8a' }}>
              upload a file at /upload →
            </Link>
          </p>
        </div>
      </div>

      <div className="card">
        <strong>Topics ({TOPICS.length})</strong>
        <ul style={{ marginTop: 8, paddingLeft: 18 }}>
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={`#${t.slug}`} style={{ color: '#1e3a8a' }}>{t.title}</a>
            </li>
          ))}
        </ul>
      </div>

      {/* Pipeline overview */}
      <div className="card" style={{ backgroundColor: '#dbeafe' }}>
        <strong>Universal preprocessing pipeline (file-type agnostic)</strong>
        <ol style={{ marginTop: 8, paddingLeft: 20 }}>
          <li><strong>Detect</strong> file type + encoding + integrity</li>
          <li><strong>Validate</strong> integrity + size limits + safety</li>
          <li><strong>Extract</strong> raw content (text / OCR / transcription)</li>
          <li><strong>Normalize</strong> format (encoding, dates, units, casing)</li>
          <li><strong>Clean</strong> noise (boilerplate, watermarks, repeated headers)</li>
          <li><strong>Extract metadata</strong> (page count, EXIF, duration, language)</li>
          <li><strong>Detect PII</strong> + safety classification</li>
          <li><strong>Dedupe</strong> by content hash or perceptual hash</li>
          <li><strong>Convert</strong> to canonical representation (text + chunks)</li>
          <li><strong>EDA</strong> profile (null distribution, length histograms, anomalies)</li>
          <li><strong>Chunk / segment</strong> if needed</li>
          <li><strong>Store / index</strong> (Postgres metadata + Qdrant vectors + S3 raw)</li>
        </ol>
      </div>

      {TOPICS.map((t) => <UniversalDeepDive key={t.slug} t={t} />)}
    </>
  );
}
