// Negative drills for Iter 29 (2026-05-17): observability sampling.

import { describe, it, expect, vi } from "vitest";
import { Tracer } from "./tracer";
import {
  AlwaysOnSampler,
  ProbabilisticSampler,
  RateLimitedSampler,
} from "./sampler";

describe("Tracer + Sampler (P1)", () => {
  it("AlwaysOnSampler emits every span (backcompat)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new AlwaysOnSampler());
    for (let i = 0; i < 5; i++) t.startSpan("op", {}).end("ok");
    expect(log).toHaveBeenCalledTimes(5);
    log.mockRestore();
  });

  it("BACKDOOR CHECK: ProbabilisticSampler(0) emits no ok spans", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new ProbabilisticSampler(0));
    for (let i = 0; i < 100; i++) t.startSpan("op", {}).end("ok");
    expect(log).toHaveBeenCalledTimes(0);
    log.mockRestore();
  });

  it("ProbabilisticSampler(0) STILL emits errors (always-on-error)", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new ProbabilisticSampler(0));
    t.startSpan("op", {}).end("error");
    expect(log).toHaveBeenCalledTimes(1);
    // Emitted span should be flagged sampledOnError.
    const payload = JSON.parse(log.mock.calls[0][0] as string);
    expect(payload.sampledOnError).toBe(true);
    log.mockRestore();
  });

  it("ProbabilisticSampler(1) emits every span", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new ProbabilisticSampler(1));
    for (let i = 0; i < 10; i++) t.startSpan("op", {}).end("ok");
    expect(log).toHaveBeenCalledTimes(10);
    log.mockRestore();
  });

  it("ProbabilisticSampler rejects out-of-range rate", () => {
    expect(() => new ProbabilisticSampler(-0.1)).toThrow();
    expect(() => new ProbabilisticSampler(1.5)).toThrow();
  });

  it("RateLimitedSampler caps emissions per span name per second", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new RateLimitedSampler(3 /* per second */));
    for (let i = 0; i < 10; i++) t.startSpan("hot-loop", {}).end("ok");
    // Only 3 ok spans should emit (rest are dropped).
    expect(log).toHaveBeenCalledTimes(3);
    log.mockRestore();
  });

  it("RateLimitedSampler — different span names have independent buckets", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const t = new Tracer(new RateLimitedSampler(2));
    for (let i = 0; i < 5; i++) t.startSpan("a", {}).end("ok");
    for (let i = 0; i < 5; i++) t.startSpan("b", {}).end("ok");
    // 2 from 'a' + 2 from 'b' = 4
    expect(log).toHaveBeenCalledTimes(4);
    log.mockRestore();
  });

  it("Deterministic random function lets tests verify exact sampling", () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    // randomFn always returns 0.05 — under rate 0.1 → always sample.
    const t1 = new Tracer(new ProbabilisticSampler(0.1, () => 0.05));
    for (let i = 0; i < 5; i++) t1.startSpan("op", {}).end("ok");
    expect(log).toHaveBeenCalledTimes(5);
    log.mockClear();
    // randomFn always returns 0.5 — above rate 0.1 → never sample.
    const t2 = new Tracer(new ProbabilisticSampler(0.1, () => 0.5));
    for (let i = 0; i < 5; i++) t2.startSpan("op", {}).end("ok");
    expect(log).toHaveBeenCalledTimes(0);
    log.mockRestore();
  });
});
