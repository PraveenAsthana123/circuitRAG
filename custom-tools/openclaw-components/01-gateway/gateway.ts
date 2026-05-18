// ✅ MULTIPLE FIXES (Iter 11): requestId + rate limit + tenant
//     sessions + error envelope.
// ✅ P0 FIXED (Iter 50, 2026-05-17): auth middleware hook.
//     Pre-fix: Gateway accepted message.tenantId/userId on trust.
//     Now: AuthMiddleware.authenticate() runs first; its claims
//     OVERRIDE the message's self-asserted identity so a malicious
//     caller cannot forge tenant/user by submitting different
//     values in the body. Same trust-boundary lesson as iter 2's
//     /auth/token fix.
//
//     Default: NoOpAuthMiddleware() refuses to authenticate
//     anything → Gateway 401s every request. Caller MUST pass a
//     real AuthMiddleware to ship.
//     For local dev: NoOpAuthMiddleware({ allowUnauthenticated: true })
//     opens the gate (with a clear, audit-visible choice).

import { randomUUID } from "crypto";
import { SessionManager } from "./session-manager";
import { RateLimiter } from "./rate-limiter";
import { AuthMiddleware, NoOpAuthMiddleware } from "./auth";
import {
  UserMessage,
  AgentResponse,
  ErrorEnvelope,
  GatewayError,
} from "./types";

export type GatewayResult =
  | { ok: true; response: AgentResponse }
  | { ok: false; error: ErrorEnvelope; statusHint: number };

export class Gateway {
  constructor(
    private readonly sessionManager: SessionManager,
    private readonly rateLimiter: RateLimiter = new RateLimiter(),
    // Iter 50: AuthMiddleware default refuses everything; tests
    // and dev pass NoOpAuthMiddleware({ allowUnauthenticated: true }).
    private readonly auth: AuthMiddleware = new NoOpAuthMiddleware(),
  ) {}

  async handleMessage(message: UserMessage): Promise<GatewayResult> {
    const requestId = randomUUID();

    try {
      // Iter 50: auth FIRST. Authenticated claims override what
      // the message body claimed about user / tenant / roles.
      const claims = await this.auth.authenticate(message);
      const authedMessage: UserMessage = {
        ...message,
        userId: claims.userId,
        tenantId: claims.tenantId,
      };

      const rlKey = `${claims.tenantId}:${claims.userId}`;
      if (!this.rateLimiter.tryAcquire(rlKey)) {
        throw new GatewayError(
          `Rate limit exceeded for ${rlKey}`,
          "RATE_LIMITED",
          429,
        );
      }

      const session = this.sessionManager.getOrCreateSession(authedMessage);

      // Later this will call Agent Runtime via Component 2.
      const response: AgentResponse = {
        sessionId: session.sessionId,
        requestId,
        reply: `Received: ${message.text}`,
      };
      return { ok: true, response };
    } catch (error) {
      const envelope: ErrorEnvelope =
        error instanceof GatewayError
          ? {
              detail: error.message,
              errorCode: error.errorCode,
              requestId,
            }
          : {
              detail: error instanceof Error ? error.message : "Unknown error",
              errorCode: "INTERNAL",
              requestId,
            };
      const statusHint =
        error instanceof GatewayError ? error.statusHint : 500;

      console.error(JSON.stringify({
        type: "gateway_error",
        requestId,
        errorCode: envelope.errorCode,
        detail: envelope.detail,
        timestamp: new Date().toISOString(),
      }));

      return { ok: false, error: envelope, statusHint };
    }
  }
}
