// Command api-gateway is the DocuMind edge service.
//
// Responsibilities (Design Areas 1, 3, 14, 45):
//   - HTTPS termination (in dev: plain HTTP on :8080)
//   - JWT validation against identity-svc
//   - Per-tenant rate limiting (forwards X-RateLimit-* headers)
//   - Correlation ID propagation
//   - Request routing to internal Python services (ingestion/retrieval/inference/evaluation)
//   - Admin endpoint isolation under /api/v1/admin/*
//
// This is a SKELETON for the demo: it boots, serves a health endpoint,
// proxies to local ingestion-svc/inference-svc over HTTP, and demonstrates
// the middleware structure. Full JWT + policy-aware routing would slot into
// internal/middleware/ without changing the shape.
package main

import (
	"log"
	"net/http"
	"os"

	"github.com/documind/api-gateway/internal/config"
	"github.com/documind/api-gateway/internal/middleware"
	"github.com/documind/api-gateway/internal/proxy"
	"github.com/go-chi/chi/v5"
)

func main() {
	cfg := config.Load()

	r := chi.NewRouter()

	// Middleware is applied in ORDER: CorrelationID first so every log has it
	r.Use(middleware.CorrelationID)
	r.Use(middleware.SecurityHeaders)
	r.Use(middleware.Logger)
	r.Use(middleware.CORS(cfg.CORSOrigins))

	// Health endpoints (must come BEFORE rate-limit / auth)
	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok","service":"api-gateway"}`))
	})

	// User-facing routes — JWT required + user-tier rate limit
	r.Group(func(api chi.Router) {
		api.Use(middleware.JWTAuth(cfg.JWTPublicKeyPath))
		api.Use(middleware.RateLimit(cfg.RedisURL, cfg.UserLimitPerMin, "api"))
		// Proxy by prefix; in production these resolve through service discovery.
		api.Handle("/api/v1/documents/*", proxy.NewReverseProxy(cfg.IngestionSvcURL))
		api.Handle("/api/v1/retrieve", proxy.NewReverseProxy(cfg.RetrievalSvcURL))
		api.Handle("/api/v1/ask", proxy.NewReverseProxy(cfg.InferenceSvcURL))
	})

	// Admin path isolation (Design Area 14)
	r.Group(func(admin chi.Router) {
		admin.Use(middleware.JWTAuth(cfg.JWTPublicKeyPath))
		admin.Use(middleware.RequireRole("tenant_admin", "platform_admin"))
		admin.Use(middleware.RateLimit(cfg.RedisURL, cfg.AdminLimitPerMin, "admin"))
		admin.Handle("/api/v1/admin/*", proxy.NewReverseProxy(cfg.GovernanceSvcURL))
	})

	log.Printf("api-gateway starting addr=:%s\n", cfg.HTTPPort)
	if err := http.ListenAndServe(":"+cfg.HTTPPort, r); err != nil {
		log.Printf("api-gateway exit: %v\n", err)
		os.Exit(1)
	}
}
