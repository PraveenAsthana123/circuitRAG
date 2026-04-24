// Package middleware holds the gateway's HTTP middleware stack.
//
// Each middleware is one small function that wraps an http.Handler — that's
// the idiomatic Go way. No framework, just chi's router + standard http.
package middleware

import (
	"context"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

type ctxKey string

const (
	CorrelationIDHeader = "X-Correlation-ID"
	TenantIDHeader      = "X-Tenant-ID"
	UserIDHeader        = "X-User-ID"
	RolesHeader         = "X-User-Roles"

	CtxCorrelationID ctxKey = "correlation_id"
	CtxTenantID      ctxKey = "tenant_id"
	CtxUserID        ctxKey = "user_id"
	CtxRoles         ctxKey = "roles"
)

// CorrelationID reads or generates X-Correlation-ID and stashes it in ctx.
func CorrelationID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cid := r.Header.Get(CorrelationIDHeader)
		if cid == "" {
			cid = uuid.NewString()
		}
		w.Header().Set(CorrelationIDHeader, cid)
		ctx := context.WithValue(r.Context(), CtxCorrelationID, cid)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// SecurityHeaders matches libs/py/documind_core/middleware.py.
func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "DENY")
		h.Set("X-XSS-Protection", "1; mode=block")
		h.Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		h.Set("Content-Security-Policy", "default-src 'self'")
		h.Set("Referrer-Policy", "strict-origin-when-cross-origin")
		h.Set("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
		next.ServeHTTP(w, r)
	})
}

// Logger emits a structured-ish line per request (real prod wires zap).
func Logger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &statusRecorder{ResponseWriter: w, status: 200}
		next.ServeHTTP(rw, r)
		cid, _ := r.Context().Value(CtxCorrelationID).(string)
		log.Printf(
			"request_complete method=%s path=%s status=%d duration_ms=%d correlation_id=%s",
			r.Method, r.URL.Path, rw.status, time.Since(start).Milliseconds(), cid,
		)
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(s int) { r.status = s; r.ResponseWriter.WriteHeader(s) }

// CORS adds permissive CORS headers for the configured origins.
func CORS(allowed []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if contains(allowed, origin) {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Access-Control-Allow-Credentials", "true")
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Tenant-ID, X-Correlation-ID")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
			}
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// JWTAuth is a stub — in production, this verifies the JWT against the
// identity-svc's published public key. See docs/design-areas/22-identity.md.
//
// For the demo, we trust X-Tenant-ID + X-User-ID headers if present.
func JWTAuth(_ string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Pass tenant + user through to downstream services
			if t := r.Header.Get(TenantIDHeader); t != "" {
				ctx := context.WithValue(r.Context(), CtxTenantID, t)
				r = r.WithContext(ctx)
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RequireRole is a placeholder for RBAC enforcement.
func RequireRole(_ ...string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// TODO: check JWT claims against required roles; 403 otherwise.
			next.ServeHTTP(w, r)
		})
	}
}

// RateLimit is a placeholder — the Python services implement full
// sliding-window limiting; the gateway's version would talk to the same
// Redis. See libs/py/documind_core/rate_limiter.py for the shape.
func RateLimit(_ string, _ int, _ string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			next.ServeHTTP(w, r)
		})
	}
}

func contains(list []string, s string) bool {
	for _, x := range list {
		if strings.EqualFold(strings.TrimSpace(x), strings.TrimSpace(s)) {
			return true
		}
	}
	return false
}
