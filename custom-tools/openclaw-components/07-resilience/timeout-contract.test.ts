// Negative drills for Iter 86 (2026-05-18): Timeout class contract.
// Per CLAUDE.md §10/§29/§47, every external call must have a
// timeout that ACTUALLY CANCELS the underlying work (AbortController),
// not just one that "wins" the race and leaks the operation.

import { describe, it, expect } from "vitest";
import { Timeout, TimeoutError } from "./timeout";

const T = new Timeout();

describe("Iter 86 — Timeout contract (P1)", () => {
  it("BACKDOOR: operation that resolves BEFORE deadline returns its value", async () => {
    const result = await T.run(
      async () => "ok",
      1000,
    );
    expect(result).toBe("ok");
  });

  it("BACKDOOR: operation that exceeds deadline rejects with TimeoutError", async () => {
    await expect(T.run(
      (signal) => new Promise<string>((resolve) => {
        const id = setTimeout(() => resolve("late"), 200);
        signal.addEventListener("abort", () => {
          clearTimeout(id);
        });
      }),
      50,
    )).rejects.toBeInstanceOf(TimeoutError);
  });

  it("BACKDOOR: AbortSignal is fired on timeout (operation can clean up)", async () => {
    let aborted = false;
    try {
      await T.run(
        (signal) => new Promise<string>((_, reject) => {
          signal.addEventListener("abort", () => {
            aborted = true;
            reject(new Error("aborted by signal"));
          });
        }),
        50,
      );
    } catch {
      // expected
    }
    expect(aborted).toBe(true);
  });

  it("AbortSignal.aborted reflects the timeout state after fire", async () => {
    let capturedSignal: AbortSignal | undefined;
    try {
      await T.run(
        (signal) => {
          capturedSignal = signal;
          return new Promise<string>(() => { /* never resolve */ });
        },
        50,
      );
    } catch {
      // expected timeout
    }
    expect(capturedSignal).toBeDefined();
    expect(capturedSignal!.aborted).toBe(true);
  });

  it("AbortSignal.aborted is FALSE before timeout fires", async () => {
    let capturedSignal: AbortSignal | undefined;
    await T.run(
      (signal) => {
        capturedSignal = signal;
        return Promise.resolve("done");
      },
      1000,
    );
    expect(capturedSignal!.aborted).toBe(false);
  });

  it("TimeoutError message names the deadline (audit visibility)", async () => {
    try {
      await T.run(() => new Promise(() => { /* hang */ }), 75);
      throw new Error("expected timeout");
    } catch (e) {
      expect(e).toBeInstanceOf(TimeoutError);
      expect((e as TimeoutError).message).toContain("75");
    }
  });

  it("BACKDOOR: error from operation propagates (NOT swallowed by timeout)", async () => {
    await expect(T.run(
      async () => { throw new Error("operation failed"); },
      1000,
    )).rejects.toThrow("operation failed");
  });

  it("operation that synchronously throws still propagates", async () => {
    await expect(T.run(
      // eslint-disable-next-line @typescript-eslint/require-await
      async () => { throw new Error("sync throw"); },
      1000,
    )).rejects.toThrow("sync throw");
  });

  it("default timeout (no override) is reasonable (5s)", async () => {
    // Confirm default doesn't fire on a fast operation.
    const result = await T.run(async () => "fast");
    expect(result).toBe("fast");
  });

  it("repeated calls do not share AbortControllers (no cross-call leak)", async () => {
    const signals: AbortSignal[] = [];
    await T.run((s) => { signals.push(s); return Promise.resolve("a"); }, 1000);
    await T.run((s) => { signals.push(s); return Promise.resolve("b"); }, 1000);
    expect(signals.length).toBe(2);
    expect(signals[0]).not.toBe(signals[1]);  // different instances
  });

  it("a successful early-return operation does NOT leave a pending timer", async () => {
    // If clearTimeout isn't called on success, a setTimeout fires
    // later — potentially calling controller.abort() on a finished
    // operation. We can't observe the timer directly, but we can
    // observe that the signal is NOT aborted on the next tick.
    let signalCaptured: AbortSignal | undefined;
    await T.run(
      (s) => { signalCaptured = s; return Promise.resolve("done"); },
      30,
    );
    // Wait past the timeout window. If the timer wasn't cleared,
    // the signal would become aborted.
    await new Promise((r) => setTimeout(r, 60));
    expect(signalCaptured!.aborted).toBe(false);
  });

  it("BOUNDARY: 0ms timeout fires immediately (or near-immediately)", async () => {
    await expect(T.run(
      () => new Promise(() => { /* never resolve */ }),
      1,  // 1ms — basically immediate
    )).rejects.toBeInstanceOf(TimeoutError);
  });
});
