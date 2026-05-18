// Negative drills for Iter 81 (2026-05-18): RetryableError contract.
// The engine's catch block uses `instanceof RetryableError` to
// distinguish transient vs permanent failures. Subclassing,
// cross-module imports, and message-preservation must all hold.

import { describe, it, expect } from "vitest";
import { RetryableError } from "./types";

describe("Iter 81 — RetryableError contract (P2)", () => {
  it("BACKDOOR: instanceof check works on direct construction", () => {
    const e = new RetryableError("blip");
    expect(e).toBeInstanceOf(RetryableError);
    expect(e).toBeInstanceOf(Error);
  });

  it("preserves the message", () => {
    const e = new RetryableError("network timeout 504");
    expect(e.message).toBe("network timeout 504");
  });

  it("name === 'RetryableError' (engine + audit envelope read this)", () => {
    const e = new RetryableError("x");
    expect(e.name).toBe("RetryableError");
  });

  it("subclass of RetryableError is also instanceof RetryableError", () => {
    class HttpTimeoutError extends RetryableError {
      constructor(public readonly url: string) {
        super(`HTTP timeout: ${url}`);
        this.name = "HttpTimeoutError";
      }
    }
    const e = new HttpTimeoutError("https://api/x");
    expect(e).toBeInstanceOf(RetryableError);  // crucial — engine retries it
    expect(e).toBeInstanceOf(Error);
    expect(e.name).toBe("HttpTimeoutError");
    expect(e.message).toBe("HTTP timeout: https://api/x");
    expect(e.url).toBe("https://api/x");
  });

  it("BACKDOOR: plain Error is NOT instanceof RetryableError", () => {
    const e = new Error("permanent: schema mismatch");
    expect(e).not.toBeInstanceOf(RetryableError);
  });

  it("BACKDOOR: TypeError / SyntaxError are NOT instanceof RetryableError", () => {
    expect(new TypeError("x")).not.toBeInstanceOf(RetryableError);
    expect(new SyntaxError("x")).not.toBeInstanceOf(RetryableError);
  });

  it("stack trace is populated (debug visibility regression)", () => {
    const e = new RetryableError("traced");
    expect(e.stack).toBeDefined();
    expect(e.stack).toContain("RetryableError");
  });

  it("throw/catch round trip preserves instanceof", () => {
    try {
      throw new RetryableError("thrown");
    } catch (caught) {
      expect(caught).toBeInstanceOf(RetryableError);
      expect((caught as RetryableError).message).toBe("thrown");
    }
  });

  it("JSON.stringify of RetryableError only yields the name (regression)", () => {
    // The constructor sets `this.name = "RetryableError"` as an
    // own enumerable property, so JSON.stringify captures it; but
    // Error's `message` and `stack` are non-enumerable so they're
    // dropped. The engine's iter 57 toErrorEnvelope intentionally
    // extracts message + stack by hand — this drill locks WHY:
    // JSON.stringify alone would lose them.
    const e = new RetryableError("not in stringify");
    const stringified = JSON.parse(JSON.stringify(e));
    expect(stringified).toEqual({ name: "RetryableError" });
    expect(stringified.message).toBeUndefined();
    expect(stringified.stack).toBeUndefined();
  });
});
