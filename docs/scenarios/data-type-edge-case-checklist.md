# Data Type Edge-Case Checklist

Use this checklist when designing ingestion and preprocessing flows.

## 1. CSV / tabular

### Edge cases
- missing headers
- duplicate headers
- bad delimiter
- encoding mismatch
- embedded commas/newlines
- mixed types in one column
- inconsistent null values
- malformed rows
- invalid date/time formats
- giant files

### Questions
- can schema be inferred safely
- should malformed rows be dropped or quarantined
- are type coercion rules explicit
- is row-level provenance preserved

## 2. Text / document

### Edge cases
- encoding issues
- OCR noise
- repeated boilerplate
- mixed language
- script or HTML noise
- giant document
- duplicate content blocks
- PII in free text
- prompt injection content

### Questions
- how is text cleaned before chunking
- how are repeated headers/footers removed
- how is language detected
- how is malicious or irrelevant instruction text handled

## 3. PDF / DOCX / HTML

### Edge cases
- parser fails
- broken file structure
- hidden text
- tables extracted badly
- scanned PDF vs text PDF
- malformed HTML
- style/content mixing

### Questions
- which parser is authoritative
- how are unsupported layouts handled
- how is parser quality measured
- what gets stored as provenance

## 4. Image

### Edge cases
- corrupted image
- orientation mismatch
- low quality
- huge dimensions
- duplicate or near-duplicate image
- OCR text embedded
- unsafe content

### Questions
- do we need OCR
- do we preserve or strip EXIF
- do we resize before indexing
- do we dedupe by perceptual hash

## 5. Audio

### Edge cases
- heavy noise
- multiple speakers
- unsupported codec
- clipped or partial file
- silence-heavy content
- language mismatch

### Questions
- do we resample
- do we run diarization
- how do we handle low-confidence transcript segments
- what metadata is stored

## 6. Video

### Edge cases
- bad codec
- corrupted container
- missing audio
- huge duration
- duplicate frames
- subtitle mismatch
- unsafe content

### Questions
- are we indexing full video or extracted artifacts
- do we use keyframes
- do we keep transcript plus frame metadata
- do we cap processing time or file size

## 7. Cross-type governance edge cases

- PII inside content
- tenant-mismapped source
- unsupported but accepted file extension
- duplicate payload across sources
- unsafe content that should not be indexed
- stale source version after re-sync

## 8. Cross-type quality checks

- parse success rate
- dedupe rate
- extraction confidence
- preprocessing latency
- content length / token distribution
- rejection count by reason
- stale index lag

## 9. Bottom line

Every data type has its own edge cases, but the common failure pattern is the same:

- bad validation
- weak normalization
- poor provenance
- no policy checks
- no quality profiling
