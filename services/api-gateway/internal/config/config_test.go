// §8 smoke test for api-gateway config loading.
//
// Closes the structural gap from the 2026-04-30 audit: the service
// had a Dockerfile but no test files. Tests that Load() returns
// sensible defaults — no env vars set means safe fallbacks — and
// that env-driven overrides are respected.
package config

import (
	"os"
	"testing"
)

func TestLoadReturnsDefaults(t *testing.T) {
	// Clean env for this test — defaults should kick in.
	for _, k := range []string{
		"API_GATEWAY_HTTP_PORT",
		"DOCUMIND_REDIS_URL",
		"DOCUMIND_JWT_ISSUER",
		"DOCUMIND_RATE_LIMIT_API_PER_MIN",
	} {
		t.Setenv(k, "")
	}

	cfg := Load()
	if cfg == nil {
		t.Fatal("Load() returned nil")
	}
	if cfg.HTTPPort != "8080" {
		t.Errorf("HTTPPort default expected 8080, got %q", cfg.HTTPPort)
	}
	if cfg.UserLimitPerMin != 100 {
		t.Errorf("UserLimitPerMin default expected 100, got %d", cfg.UserLimitPerMin)
	}
	if cfg.RedisURL == "" {
		t.Error("RedisURL default must not be empty")
	}
	if len(cfg.CORSOrigins) == 0 {
		t.Error("CORSOrigins default must not be empty (CSP requires at least one origin)")
	}
	// Negative: ensure no localhost wildcard leaked through (would be
	// a real security regression — §4.5 forbids allow_origins=['*']).
	for _, origin := range cfg.CORSOrigins {
		if origin == "*" {
			t.Errorf("CORSOrigins must not contain '*' (security regression)")
		}
	}
}

func TestLoadRespectsEnvOverrides(t *testing.T) {
	t.Setenv("API_GATEWAY_HTTP_PORT", "9999")
	t.Setenv("DOCUMIND_RATE_LIMIT_API_PER_MIN", "42")

	cfg := Load()
	if cfg.HTTPPort != "9999" {
		t.Errorf("HTTPPort env override expected 9999, got %q", cfg.HTTPPort)
	}
	if cfg.UserLimitPerMin != 42 {
		t.Errorf("UserLimitPerMin env override expected 42, got %d", cfg.UserLimitPerMin)
	}
}

func TestLoadRejectsMalformedInt(t *testing.T) {
	// Negative: a malformed int env var must NOT crash the loader.
	// Go's envInt helper falls back to default on parse error.
	t.Setenv("DOCUMIND_RATE_LIMIT_API_PER_MIN", "not-a-number")
	cfg := Load()
	if cfg.UserLimitPerMin != 100 {
		t.Errorf(
			"malformed int should fall back to default 100, got %d",
			cfg.UserLimitPerMin,
		)
	}
}

func _unused() { _ = os.Getenv("") }
