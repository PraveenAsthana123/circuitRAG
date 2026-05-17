// Added Iter 20 (2026-05-17) — AES-256-GCM authenticated encryption
// for memory values. Closes the GAPS Component 4 P1 row
// "No encryption at rest" (CLAUDE.md §4.2 equivalent).
//
// Why AES-GCM (over CBC, CTR, etc.):
//   - Authenticated: ciphertext + tag detect tampering on decrypt.
//   - Random nonce per encryption — no need to track a counter.
//   - Wide hardware support (AES-NI), fast on every platform.
//
// Key management:
//   - Caller provides a 32-byte key (typically loaded from Vault /
//     KMS / OpenBao at app startup).
//   - Sentinel-prefixed ciphertext so decrypt() can detect a value
//     that was stored before encryption was enabled and pass it
//     through unchanged (migration path).
//   - Key rotation: store the key id alongside the ciphertext so
//     callers can route to the right key during a rotation window.
//     (Stubbed: this file accepts a single key. Real prod needs a
//     keyring abstraction. See GAPS row.)

import { randomBytes, createCipheriv, createDecipheriv } from "crypto";

const SENTINEL = "v1.aesgcm:";  // version + algo prefix
const KEY_LENGTH = 32;          // AES-256
const NONCE_LENGTH = 12;        // GCM standard
const TAG_LENGTH = 16;          // GCM standard

export class EncryptionKeyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EncryptionKeyError";
  }
}

export class DecryptionFailedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DecryptionFailedError";
  }
}

export class ValueEncryptor {
  private readonly key: Buffer;

  constructor(key: Buffer | string) {
    const buf = typeof key === "string" ? Buffer.from(key, "base64") : key;
    if (buf.length !== KEY_LENGTH) {
      throw new EncryptionKeyError(
        `key must be ${KEY_LENGTH} bytes (AES-256); got ${buf.length}`,
      );
    }
    this.key = buf;
  }

  encrypt(plaintext: string): string {
    const nonce = randomBytes(NONCE_LENGTH);
    const cipher = createCipheriv("aes-256-gcm", this.key, nonce);
    const encrypted = Buffer.concat([
      cipher.update(plaintext, "utf8"),
      cipher.final(),
    ]);
    const tag = cipher.getAuthTag();
    // Layout: SENTINEL + base64( nonce || tag || ciphertext )
    const blob = Buffer.concat([nonce, tag, encrypted]);
    return SENTINEL + blob.toString("base64");
  }

  /**
   * decrypt() is forgiving toward plaintext that lacks the sentinel
   * — it returns the input unchanged so existing in-memory records
   * from before encryption was enabled keep working (migration path).
   * It is NOT forgiving toward sentinel-prefixed input that fails
   * the GCM authentication tag — that's tampering and must surface.
   */
  decrypt(value: string): string {
    if (!value.startsWith(SENTINEL)) {
      return value; // pre-encryption record; pass through
    }
    const blob = Buffer.from(value.slice(SENTINEL.length), "base64");
    if (blob.length < NONCE_LENGTH + TAG_LENGTH + 1) {
      throw new DecryptionFailedError("ciphertext too short");
    }
    const nonce = blob.subarray(0, NONCE_LENGTH);
    const tag = blob.subarray(NONCE_LENGTH, NONCE_LENGTH + TAG_LENGTH);
    const ciphertext = blob.subarray(NONCE_LENGTH + TAG_LENGTH);
    try {
      const decipher = createDecipheriv("aes-256-gcm", this.key, nonce);
      decipher.setAuthTag(tag);
      const plaintext = Buffer.concat([
        decipher.update(ciphertext),
        decipher.final(),
      ]);
      return plaintext.toString("utf8");
    } catch (e) {
      throw new DecryptionFailedError(
        `GCM authentication failed: ${e instanceof Error ? e.message : "unknown"}`,
      );
    }
  }

  /** Test helper / startup helper — generate a fresh key. */
  static generateKey(): Buffer {
    return randomBytes(KEY_LENGTH);
  }
}
