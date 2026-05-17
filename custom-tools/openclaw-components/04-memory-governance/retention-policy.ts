import { MemoryRecord } from "./types";

export class RetentionPolicy {
  isExpired(record: MemoryRecord): boolean {
    if (!record.expiresAt) return false;
    return new Date(record.expiresAt).getTime() < Date.now();
  }

  calculateExpiry(days: number): string {
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + days);
    return expiry.toISOString();
  }
}
