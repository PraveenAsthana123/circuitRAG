// Iter 71 (2026-05-17) — request_id baggage propagation drill.
//
// Pre-fix: Gateway already mints `requestId` per inbound call
// (gateway.ts line 52) and embeds it in BOTH success response AND
// error envelope, BUT no drill PROVES the full propagation
// contract. Per CLAUDE.md §47.6 baggage propagation rule, every
// response (success AND error) AND every logged error event for the
// same request MUST carry the same requestId — so an operator
// chasing an incident can trace the request envelope → log line
// → upstream trace by that single ID.
//
// What this drill locks:
//   - requestId in success envelope
//   - requestId in error envelope (the "error path also propagates"
//     property; trivial to silently regress by forgetting to mint
//     in a new error branch)
//   - requestId is unique per call (no recycling)
//   - requestId in the error envelope MATCHES the requestId in the
//     gateway_error log event for that same call (the actual
//     baggage propagation property — operator can join the two)
//   - requestId format is a valid UUID v4
//
// Composes with: CLAUDE.md §43 (drill pattern), §47.6 (baggage
//                propagation / OTel correlation), §57.6 (required
//                logging fields — request_id is canonical).

import { describe, it, expect, vi } from "vitest";
import { Gateway } from "./gateway";
import { SessionManager } from "./session-manager";
import { RateLimiter } from "./rate-limiter";
import { NoOpAuthMiddleware } from "./auth";
import { UserMessage, GatewayError } from "./types";

// UUID v4 format: 8-4-4-4-12 hex chars, with 13th char = '4'
// and 17th char in [89ab]. Node's randomUUID() emits v4 strings.
const UUID_V4_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function newMessage(over: Partial<UserMessage> = {}): UserMessage {
  return {
    messageId: "m",
    userId: "u",
    channel: "web",
    text: "hello",
    timestamp: "2026-05-17T00:00:00.000Z",
    ...over,
  };
}

// Auth middleware that opens the gate so we exercise the
// success path; for the error-path tests we explicitly throw.
const devAuth = () => new NoOpAuthMiddleware(true);

describe("Gateway — requestId baggage propagation (Iter 71, P1)", () => {
  it("BACKDOOR CHECK: successful response carries requestId (non-empty, present)", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(), devAuth());
    const r = await gw.handleMessage(newMessage());
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.response.requestId).toBeTruthy();
      expect(typeof r.response.requestId).toBe("string");
      expect(r.response.requestId.length).toBeGreaterThan(0);
    }
  });

  it("BACKDOOR CHECK: error response also carries requestId (error-path propagation)", async () => {
    // Trigger the rate-limit error branch — limit=1 then second call
    // overflows.
    const gw = new Gateway(new SessionManager(), new RateLimiter(1, 60_000), devAuth());
    const r1 = await gw.handleMessage(newMessage({ userId: "alice" }));
    const r2 = await gw.handleMessage(newMessage({ userId: "alice" }));
    expect(r1.ok).toBe(true);
    expect(r2.ok).toBe(false);
    if (!r2.ok) {
      // The negative this locks: if a future error branch is added
      // that returns `{ detail, errorCode }` without `requestId`,
      // this assertion fails — preventing silent loss of baggage.
      expect(r2.error.requestId).toBeTruthy();
      expect(typeof r2.error.requestId).toBe("string");
      expect(r2.error.requestId.length).toBeGreaterThan(0);
    }
  });

  it("BACKDOOR CHECK: each request gets a UNIQUE requestId (no recycling across two consecutive calls)", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(), devAuth());
    const r1 = await gw.handleMessage(newMessage({ text: "first" }));
    const r2 = await gw.handleMessage(newMessage({ text: "second" }));
    const r3 = await gw.handleMessage(newMessage({ text: "third" }));
    expect(r1.ok && r2.ok && r3.ok).toBe(true);
    if (r1.ok && r2.ok && r3.ok) {
      const ids = [r1.response.requestId, r2.response.requestId, r3.response.requestId];
      // All three distinct — proves no module-level cached id and
      // no accidental id reuse.
      expect(new Set(ids).size).toBe(3);
    }
  });

  it("requestId in the error envelope matches the requestId logged for that same request", async () => {
    // Spy on console.error to capture the gateway_error log event.
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    try {
      // Auth that always throws so we land in the error branch.
      const throwingAuth = {
        async authenticate(): Promise<never> {
          throw new GatewayError("nope", "UNAUTHORIZED", 401);
        },
      };
      const gw = new Gateway(new SessionManager(), new RateLimiter(), throwingAuth);
      const r = await gw.handleMessage(newMessage());

      expect(r.ok).toBe(false);
      if (!r.ok) {
        const envelopeId = r.error.requestId;
        expect(envelopeId).toBeTruthy();

        // Find the gateway_error log event for this call.
        const loggedEvents = errorSpy.mock.calls
          .map((args) => args[0])
          .filter((s): s is string => typeof s === "string")
          .map((s) => {
            try {
              return JSON.parse(s);
            } catch {
              return null;
            }
          })
          .filter((o): o is Record<string, unknown> =>
            o !== null && typeof o === "object" && o.type === "gateway_error",
          );

        // Exactly one such event for this single request.
        expect(loggedEvents.length).toBe(1);
        // And its requestId matches the envelope's — operator can
        // join (envelope ↔ log) by requestId.
        expect(loggedEvents[0].requestId).toBe(envelopeId);
        // Sanity: the log event carries the same errorCode as well,
        // so the join is unambiguous.
        expect(loggedEvents[0].errorCode).toBe("UNAUTHORIZED");
      }
    } finally {
      errorSpy.mockRestore();
    }
  });

  it("requestId format is a valid UUID v4 (regex check)", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(), devAuth());
    const r = await gw.handleMessage(newMessage());
    expect(r.ok).toBe(true);
    if (r.ok) {
      // randomUUID() emits v4 strings; this drill locks the format
      // so anyone swapping to a non-UUID generator (sequential int,
      // ulid, etc.) trips this and has to update downstream
      // log-parsers + tracing systems intentionally.
      expect(r.response.requestId).toMatch(UUID_V4_RE);
    }
  });
});
