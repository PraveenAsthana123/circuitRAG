// Package middleware — JWT verification.
//
// Design Area 3 (Trust Boundary). The gateway is the single place that
// verifies RS256 JWTs. Downstream services trust the signed headers
// (X-Tenant-ID, X-User-ID, X-User-Roles) that the gateway forwards.
//
// Token rotation: we load the public key ONCE at startup. A production
// deployment would hot-reload on SIGHUP or poll an OIDC JWKS endpoint.

package middleware

import (
	"context"
	"crypto/rsa"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// Claims we expect in every DocuMind JWT.
type DocuMindClaims struct {
	TenantID string   `json:"tenant_id"`
	UserID   string   `json:"sub"`
	Email    string   `json:"email"`
	Roles    []string `json:"roles"`
	jwt.RegisteredClaims
}

func LoadPublicKey(path string) (*rsa.PublicKey, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read public key: %w", err)
	}
	return jwt.ParseRSAPublicKeyFromPEM(raw)
}

// JWTAuth returns a middleware that verifies the Authorization bearer token
// against the given RSA public key and sets tenant/user/roles in ctx.
//
// Public paths (health, metrics) can be bypassed by wrapping this middleware
// only on the routes that need auth.
//
// If `devPermissive` is true (development only), requests WITHOUT a bearer
// fall back to reading X-Tenant-ID / X-User-ID from headers. This is how
// curl smoke tests can still hit the gateway without minting a JWT every
// time. NEVER set devPermissive=true in production.
func JWTAuth(pub *rsa.PublicKey, issuer, audience string, devPermissive bool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authz := r.Header.Get("Authorization")
			if authz == "" {
				if devPermissive {
					// Pass along the dev headers as if a JWT had just been verified.
					next.ServeHTTP(w, r.WithContext(contextFromDevHeaders(r)))
					return
				}
				unauthorized(w, "missing_authorization_header")
				return
			}
			raw := strings.TrimPrefix(authz, "Bearer ")
			if raw == authz {
				unauthorized(w, "bad_authorization_scheme")
				return
			}

			claims := &DocuMindClaims{}
			tok, err := jwt.ParseWithClaims(raw, claims, func(t *jwt.Token) (interface{}, error) {
				if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
					return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
				}
				return pub, nil
			},
				jwt.WithIssuer(issuer),
				jwt.WithAudience(audience),
				jwt.WithExpirationRequired(),
				jwt.WithValidMethods([]string{"RS256"}),
			)
			if err != nil || !tok.Valid {
				unauthorized(w, fmt.Sprintf("invalid_token: %v", err))
				return
			}
			if claims.TenantID == "" {
				unauthorized(w, "tenant_id_missing_in_claim")
				return
			}

			// Forward signed principal as trusted headers to downstream
			// services. The mesh (Istio) enforces that services only
			// accept traffic from the gateway's service account, so
			// downstream services can trust these headers.
			ctx := r.Context()
			ctx = context.WithValue(ctx, CtxTenantID, claims.TenantID)
			ctx = context.WithValue(ctx, CtxUserID, claims.UserID)
			ctx = context.WithValue(ctx, CtxRoles, claims.Roles)
			r2 := r.WithContext(ctx)
			r2.Header.Set("X-Tenant-ID", claims.TenantID)
			r2.Header.Set("X-User-ID", claims.UserID)
			r2.Header.Set("X-User-Roles", strings.Join(claims.Roles, ","))

			next.ServeHTTP(w, r2)
		})
	}
}

func contextFromDevHeaders(r *http.Request) context.Context {
	ctx := r.Context()
	if t := r.Header.Get("X-Tenant-ID"); t != "" {
		ctx = context.WithValue(ctx, CtxTenantID, t)
	}
	if u := r.Header.Get("X-User-ID"); u != "" {
		ctx = context.WithValue(ctx, CtxUserID, u)
	}
	if roles := r.Header.Get("X-User-Roles"); roles != "" {
		ctx = context.WithValue(ctx, CtxRoles, strings.Split(roles, ","))
	}
	return ctx
}

func unauthorized(w http.ResponseWriter, code string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"detail":     "authentication failed",
		"error_code": code,
	})
}

// RequireRole gates a handler to callers whose claims include at least one
// of the given roles.
func RequireRole(roles ...string) func(http.Handler) http.Handler {
	want := make(map[string]bool, len(roles))
	for _, r := range roles {
		want[r] = true
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			got, _ := r.Context().Value(CtxRoles).([]string)
			for _, role := range got {
				if want[role] {
					next.ServeHTTP(w, r)
					return
				}
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"detail":     "insufficient_role",
				"error_code": "FORBIDDEN",
				"required":   roles,
				"have":       got,
			})
		})
	}
}
