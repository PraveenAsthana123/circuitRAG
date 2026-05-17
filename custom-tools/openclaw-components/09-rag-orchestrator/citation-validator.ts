// ✅ P0 IMPROVED (Iter 21, 2026-05-17): real span-level citation
//     verification. Pre-fix: validate() ignored the answer entirely
//     and just formatted the IDs of every retrieved chunk —
//     pretending those WERE the citations. So an LLM that
//     hallucinated facts without ever referencing the retrieval
//     would still appear "fully cited".
//
//     Now: validate(answer, chunks):
//       - parses [doc:chunk] markers (and [n] / [^n] / [chunk-N])
//         that the LLM emitted in the answer text
//       - cross-checks each marker against the retrieval set
//       - returns:
//           cited:       markers that match a retrieved chunk
//           uncited:     markers in the answer that DON'T match
//                        (hallucination signal — refer to chunks
//                        the retrieval never returned)
//           unreferenced: chunks that were retrieved but never cited
//                        (irrelevant retrieval signal)
//       - hallucinationFlag: true if any uncited marker is present
//
//     Real production needs LLM-side enforcement (system prompt asks
//     for [doc:chunk] markers) + NLI verification of each claim
//     against the cited chunk. This stub handles the citation layer;
//     the semantic-grounding layer is GroundingChecker (separate).

import { RetrievedChunk } from "./types";

export interface CitationValidation {
  cited: string[];          // markers that resolve to a retrieved chunk
  uncited: string[];        // markers in answer with no matching chunk
  unreferenced: string[];   // retrieved chunks never cited in answer
  hallucinationFlag: boolean;
}

// Three accepted citation styles:
//   [doc-123:chunk-7]   "compound" — preferred for precision
//   [chunk-7]            "chunk-only" — when doc is contextually obvious
//   [^7]                 "numbered" — bibliographic style (1-based index
//                        into the retrieval set)
const COMPOUND_RE = /\[([A-Za-z0-9_-]+):([A-Za-z0-9_-]+)\]/g;
const CHUNK_ONLY_RE = /\[(chunk-[A-Za-z0-9_-]+|[A-Za-z0-9-]{8,})\]/g;
const NUMBERED_RE = /\[\^(\d+)\]/g;

export class CitationValidator {
  validate(answer: string, chunks: RetrievedChunk[]): CitationValidation {
    const retrievedIds = new Set(
      chunks.map((c) => `${c.documentId}#${c.chunkId}`),
    );
    const retrievedChunkIds = new Set(chunks.map((c) => c.chunkId));

    const cited = new Set<string>();
    const uncited: string[] = [];

    // Compound [doc:chunk]
    for (const m of answer.matchAll(COMPOUND_RE)) {
      const id = `${m[1]}#${m[2]}`;
      if (retrievedIds.has(id)) cited.add(id);
      else uncited.push(m[0]);
    }

    // Chunk-only [chunk-X]
    for (const m of answer.matchAll(CHUNK_ONLY_RE)) {
      const chunkId = m[1];
      const match = chunks.find((c) => c.chunkId === chunkId);
      if (match) {
        cited.add(`${match.documentId}#${match.chunkId}`);
      } else if (retrievedChunkIds.size > 0) {
        uncited.push(m[0]);
      }
    }

    // Numbered [^N]
    for (const m of answer.matchAll(NUMBERED_RE)) {
      const idx = parseInt(m[1], 10) - 1;
      if (idx >= 0 && idx < chunks.length) {
        cited.add(`${chunks[idx].documentId}#${chunks[idx].chunkId}`);
      } else {
        uncited.push(m[0]);
      }
    }

    const unreferenced = Array.from(retrievedIds).filter(
      (id) => !cited.has(id),
    );

    return {
      cited: Array.from(cited),
      uncited,
      unreferenced,
      hallucinationFlag: uncited.length > 0,
    };
  }
}
