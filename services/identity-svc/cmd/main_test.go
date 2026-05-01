// §8 smoke test for identity-svc.
//
// Closes the structural gap from the 2026-04-30 audit. Tests the
// stub IdentityService surface — Login + CreateTenant — at the
// data-shape level.
package main

import (
	"testing"

	"github.com/google/uuid"
)

func TestIdentityServiceLoginReturnsToken(t *testing.T) {
	s := &IdentityService{}
	token, err := s.Login("alice@example.com", "secret")
	if err != nil {
		t.Errorf("Login returned unexpected error: %v", err)
	}
	if token == "" {
		t.Error("Login must return a non-empty token (stub returns 'stub-jwt')")
	}
}

func TestIdentityServiceCreateTenantShape(t *testing.T) {
	s := &IdentityService{}
	tenant := s.CreateTenant("Acme Corp")
	if tenant.ID == uuid.Nil {
		t.Error("CreateTenant must return non-nil UUID")
	}
	if tenant.Tier == "" {
		t.Error("CreateTenant must populate Tier")
	}
	// Negative: Tier must be one of the documented values.
	allowed := map[string]bool{"free": true, "pro": true, "enterprise": true}
	if !allowed[tenant.Tier] {
		t.Errorf("Tier %q not in allowed set {free,pro,enterprise}", tenant.Tier)
	}
}

func TestUserStructHasRolesField(t *testing.T) {
	u := User{
		ID:       uuid.New(),
		TenantID: uuid.New(),
		Email:    "alice@example.com",
		Roles:    []string{"tenant_admin"},
	}
	if len(u.Roles) == 0 {
		t.Error("User struct must support roles assignment")
	}
}
