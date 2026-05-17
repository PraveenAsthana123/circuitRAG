// ✅ MULTIPLE FIXES (Iter 11, 2026-05-17):
//     - P0: requestId is now minted per inbound message and propagated
//       to the AgentResponse (CLAUDE.md §47 baggage rule).
//     - P0: per-tenant + per-user rate limit (in-memory sliding
//       window; real prod needs Redis — see RateLimiter file).
//     - P0: structured error envelope on any failure (CLAUDE.md §6.2).
//     - P1: session manager now uses TTL + LRU + tenant scoping
//       (see SessionManager).
//
//     Authentication / RBAC is still NOT implemented in this stub;
//     real deployments must front the Gateway with an OIDC-aware
//     reverse proxy or middleware that validates a Bearer token
//     and sets req.tenantId from token claims BEFORE handing off
//     to handleMessage. The Gateway accepts message.tenantId on
//     trust — that trust must be enforced by the layer above.

import { randomUUID } from "crypto";
import { SessionManager } from "./session-manager";
import { RateLimiter } from "./rate-limiter";
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
  ) {}

  async handleMessage(message: UserMessage): Promise<GatewayResult> {
    const requestId = randomUUID();

    try {
      // Rate-limit key: tenant:user. Real prod adds per-IP as well.
      const tenantId = message.tenantId ?? "default";
      const rlKey = `${tenantId}:${message.userId}`;
      if (!this.rateLimiter.tryAcquire(rlKey)) {
        throw new GatewayError(
          `Rate limit exceeded for ${rlKey}`,
          "RATE_LIMITED",
          429,
        );
      }

      const session = this.sessionManager.getOrCreateSession(message);

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
