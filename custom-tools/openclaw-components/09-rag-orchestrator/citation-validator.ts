import { RetrievedChunk } from "./types";

export class CitationValidator {
  validate(chunks: RetrievedChunk[]): string[] {
    return chunks.map(
      (chunk) => `${chunk.documentId}#${chunk.chunkId}`
    );
  }
}
