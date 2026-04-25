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
