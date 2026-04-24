// Command api-gateway is the DocuMind edge service.
//
// Design Areas 1 (System Boundary), 3 (Trust Boundary), 14 (Admin Path
// Isolation), 45 (Backpressure), 62 (Observability).
//
// Hardened pipeline (outer → inner):
//   1. CorrelationID       — stamp X-Correlation-ID, bind to ctx
//   2. SecurityHeaders     — CSP, HSTS, X-Frame-Options, etc.
//   3. Logger              — structured log per request
//   4. CORS                — from config
//   5. BodyLimit(1MB)      — default cap; upload endpoints use 50MB
//   6. JWT (RS256)         — parse + verify; populate tenant/user/roles
//   7. RateLimit           — Redis sliding-window per tenant/IP
//   8. RequireRole         — on admin routes only
//   9. Reverse proxy       — dispatch to internal services
//
// Production notes:
//   - We sit BEHIND nginx (see infra/nginx/nginx.conf) which terminates
//     TLS + does L4 rate limiting + edge caching.
//   - Internal services trust the X-Tenant-ID / X-User-ID / X-User-Roles
//     headers we forward because Istio AuthorizationPolicy allows only
//     the gateway's service account to call them.
package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/documind/api-gateway/internal/config"
	"github.com/documind/api-gateway/internal/middleware"
	"github.com/documind/api-gateway/internal/proxy"
	"github.com/go-chi/chi/v5"
)

const (
	defaultBodyLimit   = 1 << 20      // 1MB for JSON APIs
	uploadBodyLimit    = 50 * 1 << 20 // 50MB for file uploads
	readHeaderTimeout  = 5 * time.Second
	readTimeout        = 30 * time.Second
	writeTimeout       = 120 * time.Second
	idleTimeout        = 120 * time.Second
	shutdownGracePeriod = 30 * time.Second
)

func main() {
	cfg := config.Load()

	// -- Dependencies (fail fast if boot deps are broken) ------------------
	pub, err := middleware.LoadPublicKey(cfg.JWTPublicKeyPath)
	if err != nil {
		log.Fatalf("jwt_public_key load failed: %v (path=%s)", err, cfg.JWTPublicKeyPath)
	}
	rl, err := middleware.NewRateLimiter(cfg.RedisURL)
	if err != nil {
		log.Fatalf("rate_limiter init failed: %v", err)
	}

	devPermissive := os.Getenv("DOCUMIND_JWT_DEV_PERMISSIVE") == "1"
	if devPermissive {
		log.Println("[WARN] JWT dev-permissive mode ON — never use in production")
	}

	// -- Router ------------------------------------------------------------
	r := chi.NewRouter()

	// Order matters: first-added runs first (chi is outer-to-inner).
	r.Use(middleware.CorrelationID)
	r.Use(middleware.SecurityHeaders)
	r.Use(middleware.Logger)
	r.Use(middleware.CORS(cfg.CORSOrigins))
	r.Use(middleware.BodyLimit(defaultBodyLimit))

	// Health/metrics — unauthenticated, un-rate-limited.
	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprintf(w, `{"status":"ok","service":"api-gateway"}`)
	})
	r.Get("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok\n"))
	})

	// -- Authenticated user surface ---------------------------------------
	r.Group(func(api chi.Router) {
		api.Use(middleware.JWTAuth(pub, cfg.JWTIssuer, cfg.JWTAudience, devPermissive))
		api.Use(rl.Middleware(cfg.UserLimitPerMin, cfg.AdminLimitPerMin, cfg.UploadLimitPerMin))

		// Uploads get a bigger body cap — override the default 1MB.
		api.With(middleware.BodyLimit(uploadBodyLimit)).
			Handle("/api/v1/documents/upload", proxy.NewReverseProxy(cfg.IngestionSvcURL))

		api.Handle("/api/v1/documents/*", proxy.NewReverseProxy(cfg.IngestionSvcURL))
		api.Handle("/api/v1/documents",   proxy.NewReverseProxy(cfg.IngestionSvcURL))
		api.Handle("/api/v1/retrieve",    proxy.NewReverseProxy(cfg.RetrievalSvcURL))
		api.Handle("/api/v1/ask",         proxy.NewReverseProxy(cfg.InferenceSvcURL))
		api.Handle("/api/v1/evaluation/*", proxy.NewReverseProxy(cfg.EvaluationSvcURL))
	})

	// -- Admin surface (RBAC + separate rate bucket) ----------------------
	r.Group(func(admin chi.Router) {
		admin.Use(middleware.JWTAuth(pub, cfg.JWTIssuer, cfg.JWTAudience, devPermissive))
		admin.Use(middleware.RequireRole("tenant_admin", "platform_admin"))
		admin.Use(rl.Middleware(cfg.UserLimitPerMin, cfg.AdminLimitPerMin, cfg.UploadLimitPerMin))
		admin.Handle("/api/v1/admin/*", proxy.NewReverseProxy(cfg.GovernanceSvcURL))
	})

	// -- HTTP server with explicit timeouts -------------------------------
	srv := &http.Server{
		Addr:              ":" + cfg.HTTPPort,
		Handler:           r,
		ReadHeaderTimeout: readHeaderTimeout,
		ReadTimeout:       readTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}

	// Graceful shutdown on SIGTERM (K8s rolling updates).
	go func() {
		log.Printf("api-gateway listening addr=%s jwt_dev_permissive=%v\n",
			srv.Addr, devPermissive)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("api-gateway listen error: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	log.Println("api-gateway shutting down...")
	ctx, cancel := context.WithTimeout(context.Background(), shutdownGracePeriod)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("api-gateway shutdown error: %v", err)
	}
	log.Println("api-gateway stopped")
}

// Keep unused import from lint complaints when devPermissive isn't wired
// on all paths.
var _ = time.Second
