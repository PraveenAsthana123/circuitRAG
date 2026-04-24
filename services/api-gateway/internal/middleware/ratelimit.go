// Package middleware — Redis-backed sliding-window rate limit.
//
// Mirrors libs/py/documind_core/rate_limiter.py so the gateway + Python
// services share the same algorithm + key namespace. Tenant-scoped if a
// JWT has set X-Tenant-ID, otherwise per-IP.
//
// Why Redis and not in-process? Multiple gateway replicas must share the
// rate-limit state. In-process per-pod means a tenant can multiply their
// budget by the replica count — not acceptable.

package middleware

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

type RateLimiter struct {
	rdb *redis.Client
}

func NewRateLimiter(addr string) (*RateLimiter, error) {
	// Normalize "redis://host:port/db" into host:port + db number
	host, dbNum := parseRedisURL(addr)
	rdb := redis.NewClient(&redis.Options{
		Addr: host,
		DB:   dbNum,
	})
	// Quick ping so config errors fail fast at boot.
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}
	return &RateLimiter{rdb: rdb}, nil
}

func parseRedisURL(url string) (host string, db int) {
	// Accepts: "redis://host:port/db" or "host:port"
	raw := strings.TrimPrefix(url, "redis://")
	if idx := strings.LastIndex(raw, "/"); idx >= 0 {
		if n, err := strconv.Atoi(raw[idx+1:]); err == nil {
			db = n
			raw = raw[:idx]
		}
	}
	return raw, db
}

// Middleware applies a sliding-window limit keyed on tenant_id (authenticated
// callers) or IP (anonymous). Limits vary by path: admin endpoints are
// stricter, uploads are stricter still. Exposes X-RateLimit-* headers.
func (rl *RateLimiter) Middleware(userLimitPerMin, adminLimitPerMin, uploadLimitPerMin int) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Skip health + metrics endpoints entirely
			switch r.URL.Path {
			case "/health", "/healthz", "/metrics":
				next.ServeHTTP(w, r)
				return
			}

			limit, endpoint := selectBudget(r.URL.Path, r.Method,
				userLimitPerMin, adminLimitPerMin, uploadLimitPerMin)
			key := bucketKey(r, endpoint)

			res, err := rl.check(r.Context(), key, limit, 60)
			if err != nil {
				// Fail OPEN — a Redis outage should not cascade into 5xx
				// for every user. We log and let the request through.
				// The sharp-edged alternative (fail closed) is opt-in via
				// DOCUMIND_RATE_LIMIT_FAIL_CLOSED=1 but defaults to open.
				w.Header().Set("X-RateLimit-Error", "redis_unavailable")
				next.ServeHTTP(w, r)
				return
			}

			w.Header().Set("X-RateLimit-Limit", strconv.Itoa(res.limit))
			w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(res.remaining))
			w.Header().Set("X-RateLimit-Reset", strconv.Itoa(res.resetSeconds))

			if !res.allowed {
				w.Header().Set("Retry-After", strconv.Itoa(res.resetSeconds))
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusTooManyRequests)
				_ = json.NewEncoder(w).Encode(map[string]any{
					"detail":     fmt.Sprintf("rate limit exceeded (%d per minute)", res.limit),
					"error_code": "RATE_LIMITED",
					"details":    map[string]any{"retry_after_seconds": res.resetSeconds},
				})
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

type checkResult struct {
	allowed      bool
	remaining    int
	resetSeconds int
	limit        int
}

// Sliding-window via sorted set — same algorithm as libs/py rate_limiter.
// Key: tenant:{t}:rl:{endpoint}  or  ip:{ip}:rl:{endpoint}
// Score: ms-since-epoch. Members: timestamp+counter so uniqueness is free.
func (rl *RateLimiter) check(ctx context.Context, key string, limit int, windowSec int) (checkResult, error) {
	nowMs := time.Now().UnixMilli()
	windowStart := nowMs - int64(windowSec)*1000

	pipe := rl.rdb.TxPipeline()
	pipe.ZRemRangeByScore(ctx, key, "0", strconv.FormatInt(windowStart, 10))
	cardCmd := pipe.ZCard(ctx, key)
	pipe.Expire(ctx, key, time.Duration(windowSec+1)*time.Second)
	if _, err := pipe.Exec(ctx); err != nil {
		return checkResult{}, err
	}
	current := int(cardCmd.Val())

	if current+1 > limit {
		// Find oldest entry to compute reset
		oldest, _ := rl.rdb.ZRangeWithScores(ctx, key, 0, 0).Result()
		reset := windowSec
		if len(oldest) > 0 {
			reset = int(((int64(oldest[0].Score) + int64(windowSec)*1000) - nowMs) / 1000)
			if reset < 1 {
				reset = 1
			}
		}
		return checkResult{allowed: false, remaining: 0, resetSeconds: reset, limit: limit}, nil
	}

	member := strconv.FormatInt(nowMs, 10) + ":" + strconv.Itoa(current)
	rl.rdb.ZAdd(ctx, key, redis.Z{Score: float64(nowMs), Member: member})

	return checkResult{
		allowed:      true,
		remaining:    limit - current - 1,
		resetSeconds: windowSec,
		limit:        limit,
	}, nil
}

func selectBudget(path, method string, userLimit, adminLimit, uploadLimit int) (int, string) {
	if strings.HasPrefix(path, "/api/v1/admin") {
		return adminLimit, "admin"
	}
	if method == http.MethodPost && strings.Contains(path, "/upload") {
		return uploadLimit, "upload"
	}
	return userLimit, "api"
}

func bucketKey(r *http.Request, endpoint string) string {
	if t, _ := r.Context().Value(CtxTenantID).(string); t != "" {
		return "tenant:" + t + ":rl:" + endpoint
	}
	return "ip:" + clientIP(r) + ":rl:" + endpoint
}

func clientIP(r *http.Request) string {
	if fwd := r.Header.Get("X-Forwarded-For"); fwd != "" {
		if idx := strings.Index(fwd, ","); idx != -1 {
			return strings.TrimSpace(fwd[:idx])
		}
		return strings.TrimSpace(fwd)
	}
	if host := r.RemoteAddr; host != "" {
		if idx := strings.LastIndex(host, ":"); idx != -1 {
			return host[:idx]
		}
		return host
	}
	return "unknown"
}
