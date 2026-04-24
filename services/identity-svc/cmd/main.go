// identity-svc — tenants, users, roles, JWT issuance, API keys.
//
// Design Area 22. This file is a skeleton showing the class structure; the
// full implementation (JWT minting with RS256, RBAC, API-key lifecycle) is
// documented in docs/design-areas/22-identity.md.
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// --- Domain models (would live in internal/model) -------------------------

type Tenant struct {
	ID   uuid.UUID `json:"id"`
	Name string    `json:"name"`
	Tier string    `json:"tier"` // free | pro | enterprise
}

type User struct {
	ID       uuid.UUID `json:"id"`
	TenantID uuid.UUID `json:"tenant_id"`
	Email    string    `json:"email"`
	Roles    []string  `json:"roles"` // platform_admin | tenant_admin | tenant_user | evaluator | viewer
}

// --- Service layer (would live in internal/service) -----------------------

type IdentityService struct {
	// pgxpool.Pool, jwt private key, etc. — injected in constructor.
}

func (*IdentityService) Login(_ string, _ string) (string, error) { return "stub-jwt", nil }
func (*IdentityService) CreateTenant(_ string) Tenant {
	return Tenant{ID: uuid.New(), Name: "demo", Tier: "pro"}
}

// --- HTTP router ----------------------------------------------------------

func main() {
	port := os.Getenv("IDENTITY_HTTP_PORT")
	if port == "" {
		port = "8081"
	}
	svc := &IdentityService{}

	r := chi.NewRouter()
	r.Get("/health", health)

	r.Post("/api/v1/auth/login", func(w http.ResponseWriter, r *http.Request) {
		tok, _ := svc.Login("", "")
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": tok})
	})
	r.Post("/api/v1/tenants", func(w http.ResponseWriter, _ *http.Request) {
		t := svc.CreateTenant("demo")
		_ = json.NewEncoder(w).Encode(t)
	})

	log.Printf("identity-svc starting addr=:%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatal(err)
	}
}

func health(w http.ResponseWriter, _ *http.Request) {
	_, _ = w.Write([]byte(`{"status":"ok","service":"identity-svc"}`))
}
