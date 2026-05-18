// Added Iter 50 (2026-05-17) — auth contract for the Gateway.
// Real production replaces this with an OIDC-aware reverse proxy
// or a fastify/express middleware that validates a Bearer token
// and sets the claims on the request. The Gateway accepts the
// resolved claims via this interface so it can enforce that
// every inbound message carries an authenticated identity.
//
// The contract:
//   AuthMiddleware.authenticate(message) returns AuthClaims OR
//   throws GatewayError("UNAUTHORIZED" | "FORBIDDEN").
//
// Gateway uses the claims to OVERRIDE message.tenantId/userId/roles
// so a malicious caller cannot forge identity in the message body
// (same trust-boundary lesson as iter 2's /auth/token fix).

import { UserMessage, GatewayError } from "./types";

export interface AuthClaims {
  userId: string;
  tenantId: string;
  roles: string[];
  /** When the token expires. Gateway can compare to clock for
   *  freshness checks beyond what the upstream validator did. */
  expiresAt?: string;
}

export interface AuthMiddleware {
  authenticate(message: UserMessage): Promise<AuthClaims>;
}

/**
 * Default for non-auth scenarios (local dev, CLI). REFUSES to
 * authenticate any production-like request — refuses if no
 * explicit `allowUnauthenticated: true` flag is passed.
 *
 * This is the safe default: if a Gateway is constructed without
 * an auth middleware AND it's not explicitly opted into the unsafe
 * mode, every request 401s. Iter 11's note ("must front the
 * Gateway with auth") is now enforced by code.
 */
export class NoOpAuthMiddleware implements AuthMiddleware {
  constructor(private readonly allowUnauthenticated: boolean = false) {}

  async authenticate(message: UserMessage): Promise<AuthClaims> {
    if (!this.allowUnauthenticated) {
      throw new GatewayError(
        "Gateway has no auth middleware configured. Construct " +
        "the Gateway with a real AuthMiddleware (OIDC-aware) " +
        "OR pass NoOpAuthMiddleware({ allowUnauthenticated: true }) " +
        "for local/dev only.",
        "UNAUTHORIZED",
        401,
      );
    }
    return {
      userId: message.userId,
      tenantId: message.tenantId ?? "default",
      roles: ["user"],
    };
  }
}
