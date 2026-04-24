// Package config reads environment variables for the API gateway.
package config

import (
	"os"
	"strconv"
)

type Config struct {
	HTTPPort         string
	GRPCPort         string
	RedisURL         string
	JWTPublicKeyPath string
	CORSOrigins      []string
	UserLimitPerMin  int
	AdminLimitPerMin int

	IngestionSvcURL  string
	RetrievalSvcURL  string
	InferenceSvcURL  string
	GovernanceSvcURL string
}

func Load() *Config {
	return &Config{
		HTTPPort:         env("API_GATEWAY_HTTP_PORT", "8080"),
		GRPCPort:         env("API_GATEWAY_GRPC_PORT", "9090"),
		RedisURL:         env("DOCUMIND_REDIS_URL", "redis://localhost:6379/0"),
		JWTPublicKeyPath: env("DOCUMIND_JWT_PUBLIC_KEY_PATH", "./scripts/dev-keys/jwt-public.pem"),
		CORSOrigins:      splitCSV(env("DOCUMIND_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")),
		UserLimitPerMin:  envInt("DOCUMIND_RATE_LIMIT_API_PER_MIN", 100),
		AdminLimitPerMin: envInt("DOCUMIND_RATE_LIMIT_ADMIN_PER_MIN", 50),
		IngestionSvcURL:  env("DOCUMIND_INGESTION_URL", "http://localhost:8082"),
		RetrievalSvcURL:  env("DOCUMIND_RETRIEVAL_URL", "http://localhost:8083"),
		InferenceSvcURL:  env("DOCUMIND_INFERENCE_URL", "http://localhost:8084"),
		GovernanceSvcURL: env("DOCUMIND_GOVERNANCE_URL", "http://localhost:8086"),
	}
}

func env(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v := env(key, ""); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func splitCSV(s string) []string {
	out := []string{}
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == ',' {
			if start < i {
				out = append(out, s[start:i])
			}
			start = i + 1
		}
	}
	if start < len(s) {
		out = append(out, s[start:])
	}
	return out
}
