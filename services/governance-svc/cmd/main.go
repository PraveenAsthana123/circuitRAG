// governance-svc — policy engine, HITL queue, audit log, feature flags.
//
// Design Areas 27, 56, 57, 63, 55.
//
// Policy-as-code uses CEL (Common Expression Language) so rules can be
// updated at runtime without code deploys. Audit log is append-only with
// hash-chained entries for tamper detection.
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// Policy is a single CEL rule stored in governance.policies.
type Policy struct {
	ID        uuid.UUID `json:"id"`
	Name      string    `json:"name"`
	Condition string    `json:"condition"` // CEL expression
	Action    string    `json:"action"`    // flag | block | log | notify
	Severity  string    `json:"severity"`
	Enabled   bool      `json:"enabled"`
	Version   int       `json:"version"`
}

// HITLItem — a flagged response awaiting human review.
type HITLItem struct {
	ID           uuid.UUID `json:"id"`
	TenantID     uuid.UUID `json:"tenant_id"`
	Question     string    `json:"question"`
	Answer       string    `json:"answer"`
	Confidence   float64   `json:"confidence"`
	FlagReason   string    `json:"flag_reason"`
	ReviewStatus string    `json:"review_status"` // pending | approved | rejected | edited
}

// --- Services (stubbed) ---

type PolicyEngine struct{ /* CEL env, policy cache */ }

func (*PolicyEngine) Evaluate(_ string, _ map[string]any) (action string, passed bool) {
	return "pass", true
}

type HITLService struct{}

func (*HITLService) Enqueue(_ HITLItem) {}

type AuditLog struct{}

func (*AuditLog) Record(_ string, _ map[string]any) {}

// --- HTTP router ---

func main() {
	port := os.Getenv("GOVERNANCE_HTTP_PORT")
	if port == "" {
		port = "8086"
	}
	r := chi.NewRouter()
	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok","service":"governance-svc"}`))
	})
	r.Get("/api/v1/admin/policies", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode([]Policy{{
			ID: uuid.New(), Name: "low_confidence_flag", Condition: "response.confidence < 0.6",
			Action: "flag", Severity: "medium", Enabled: true, Version: 1,
		}})
	})
	r.Get("/api/v1/admin/hitl/queue", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode([]HITLItem{})
	})
	log.Printf("governance-svc starting addr=:%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatal(err)
	}
}
