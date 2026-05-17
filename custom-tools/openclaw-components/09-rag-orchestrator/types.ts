export interface DocumentInput {
  documentId: string;
  tenantId: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface Chunk {
  chunkId: string;
  documentId: string;
  tenantId: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface RetrievedChunk extends Chunk {
  score: number;
}

export interface RAGRequest {
  requestId: string;
  tenantId: string;
  userId: string;
  query: string;
  traceId: string;
}

export interface RAGResponse {
  answer: string;
  citations: string[];
  grounded: boolean;
  qualityScore: number;
  /** Markers in the answer that don't resolve to a retrieved chunk
   *  (hallucination signal). Set by Iter 21. */
  uncited?: string[];
  /** Retrieved chunks the answer never cited (irrelevant retrieval). */
  unreferenced?: string[];
  hallucinationFlag?: boolean;
}
