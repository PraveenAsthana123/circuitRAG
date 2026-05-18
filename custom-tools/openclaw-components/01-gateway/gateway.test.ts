// Negative drills for Iteration 11 (2026-05-17):
//   - request_id minted per inbound message
//   - tenant-scoped session keying (no cross-tenant collision)
//   - session TTL pruning
//   - rate limiter denies on overage
//   - structured error envelope on failure

import { describe, it, expect } from "vitest";
import { Gateway } from "./gateway";
import { SessionManager } from "./session-manager";
import { RateLimiter } from "./rate-limiter";
import { NoOpAuthMiddleware } from "./auth";
import { UserMessage } from "./types";

// Iter 50 added a default-deny auth middleware. Existing gateway
// tests construct Gateway without auth, which would now 401 every
// request. devAuth here opts into the unauthenticated-dev path so
// the iter 11 assertions keep their behavior.
const devAuth = () => new NoOpAuthMiddleware(true);

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

describe("Gateway — request_id propagation (P0)", () => {
  it("mints a request_id per call; two calls get distinct IDs", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(), devAuth());
    const r1 = await gw.handleMessage(newMessage({ text: "first" }));
    const r2 = await gw.handleMessage(newMessage({ text: "second" }));
    expect(r1.ok && r1.response.requestId).toBeTruthy();
    expect(r2.ok && r2.response.requestId).toBeTruthy();
    if (r1.ok && r2.ok) {
      expect(r1.response.requestId).not.toBe(r2.response.requestId);
    }
  });
});

describe("SessionManager — tenant isolation + TTL (P0/P1)", () => {
  it("BACKDOOR CHECK: same userId+channel in different tenants gets different sessions", () => {
    const sm = new SessionManager();
    const sA = sm.getOrCreateSession(newMessage({ tenantId: "tenant-A" }));
    const sB = sm.getOrCreateSession(newMessage({ tenantId: "tenant-B" }));
    expect(sA.sessionId).not.toBe(sB.sessionId);
    // History must NOT have leaked across tenants.
    expect(sA.history.length).toBe(1);
    expect(sB.history.length).toBe(1);
  });

  it("TTL prunes idle sessions", async () => {
    const sm = new SessionManager(50 /* ttlMs */);
    sm.getOrCreateSession(newMessage());
    expect(sm.size()).toBe(1);
    await new Promise((r) => setTimeout(r, 80));
    // Next operation triggers prune.
    sm.getOrCreateSession(newMessage({ userId: "other" }));
    expect(sm.size()).toBe(1); // the first one was pruned, second was added
  });

  it("LRU cap evicts oldest when full", () => {
    const sm = new SessionManager(60_000, 2);
    sm.getOrCreateSession(newMessage({ userId: "u1" }));
    sm.getOrCreateSession(newMessage({ userId: "u2" }));
    sm.getOrCreateSession(newMessage({ userId: "u3" }));
    expect(sm.size()).toBeLessThanOrEqual(2);
  });
});

describe("RateLimiter (P0)", () => {
  it("allows under limit, denies at/over limit", () => {
    const rl = new RateLimiter(3, 60_000);
    expect(rl.tryAcquire("k")).toBe(true);
    expect(rl.tryAcquire("k")).toBe(true);
    expect(rl.tryAcquire("k")).toBe(true);
    expect(rl.tryAcquire("k")).toBe(false);
    expect(rl.tryAcquire("k")).toBe(false);
  });

  it("separate keys have separate buckets", () => {
    const rl = new RateLimiter(1, 60_000);
    expect(rl.tryAcquire("a")).toBe(true);
    expect(rl.tryAcquire("a")).toBe(false);
    // Different key has fresh budget.
    expect(rl.tryAcquire("b")).toBe(true);
  });

  it("window slide allows refill", async () => {
    const rl = new RateLimiter(1, 30);
    expect(rl.tryAcquire("k")).toBe(true);
    expect(rl.tryAcquire("k")).toBe(false);
    await new Promise((r) => setTimeout(r, 50));
    expect(rl.tryAcquire("k")).toBe(true);
  });
});

describe("Gateway — error envelope (P0)", () => {
  it("rate-limit overflow returns structured error with request_id", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(1, 60_000), devAuth());
    const r1 = await gw.handleMessage(newMessage({ userId: "x" }));
    const r2 = await gw.handleMessage(newMessage({ userId: "x" }));
    expect(r1.ok).toBe(true);
    expect(r2.ok).toBe(false);
    if (!r2.ok) {
      expect(r2.error.errorCode).toBe("RATE_LIMITED");
      expect(r2.error.requestId).toBeTruthy();
      expect(r2.error.detail).toContain("Rate limit exceeded");
      expect(r2.statusHint).toBe(429);
    }
  });
});


describe("Gateway — auth middleware (Iter 50, P0)", () => {
  it("BACKDOOR CHECK: default Gateway construction 401s without auth opt-in", async () => {
    const gw = new Gateway(new SessionManager());  // default NoOpAuthMiddleware()
    const r = await gw.handleMessage(newMessage());
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.errorCode).toBe("UNAUTHORIZED");
      expect(r.statusHint).toBe(401);
    }
  });

  it("BACKDOOR CHECK: auth claims OVERRIDE message-claimed identity", async () => {
    // Real-world attack: client sends { userId: 'admin', tenantId: 'rich' }
    // in the message body. The auth middleware authoritatively returns
    // a DIFFERENT identity from the verified token. Gateway must use
    // the auth claims, not the body.
    const fakeAuth = {
      async authenticate(): Promise<any> {
        return { userId: "real-user", tenantId: "real-tenant", roles: ["user"] };
      },
    };
    const sm = new SessionManager();
    const gw = new Gateway(sm, new RateLimiter(), fakeAuth);
    const r = await gw.handleMessage(newMessage({
      userId: "attacker-claims-admin",
      tenantId: "attacker-claims-other-tenant",
    }));
    expect(r.ok).toBe(true);
    if (r.ok) {
      // sessionId format is `${tenant}:${channel}:${user}` per session-manager
      expect(r.response.sessionId).toContain("real-tenant");
      expect(r.response.sessionId).toContain("real-user");
      expect(r.response.sessionId).not.toContain("attacker");
    }
  });

  it("auth middleware throwing GatewayError surfaces as proper 401", async () => {
    const failAuth = {
      async authenticate(): Promise<any> {
        const { GatewayError } = await import("./types");
        throw new GatewayError("Bad token", "UNAUTHORIZED", 401);
      },
    };
    const gw = new Gateway(new SessionManager(), new RateLimiter(), failAuth);
    const r = await gw.handleMessage(newMessage());
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.errorCode).toBe("UNAUTHORIZED");
      expect(r.error.detail).toContain("Bad token");
      expect(r.statusHint).toBe(401);
    }
  });

  it("NoOpAuthMiddleware(allowUnauthenticated=true) passes through", async () => {
    const gw = new Gateway(new SessionManager(), new RateLimiter(), new NoOpAuthMiddleware(true));
    const r = await gw.handleMessage(newMessage());
    expect(r.ok).toBe(true);
  });
});
