import { randomUUID } from "crypto";
import { Chunk, DocumentInput } from "./types";

export class Chunker {
  chunk(document: DocumentInput, maxChars = 800): Chunk[] {
    const chunks: Chunk[] = [];
    const paragraphs = document.text.split(/\n\s*\n/);

    let buffer = "";

    for (const paragraph of paragraphs) {
      if ((buffer + paragraph).length > maxChars && buffer.length > 0) {
        chunks.push(this.createChunk(document, buffer));
        buffer = "";
      }

      buffer += paragraph + "\n\n";
    }

    if (buffer.trim()) {
      chunks.push(this.createChunk(document, buffer));
    }

    return chunks;
  }

  private createChunk(document: DocumentInput, text: string): Chunk {
    return {
      chunkId: randomUUID(),
      documentId: document.documentId,
      tenantId: document.tenantId,
      text: text.trim(),
      metadata: document.metadata,
    };
  }
}
