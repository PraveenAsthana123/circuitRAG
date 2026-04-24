// observability-svc — aggregates Prometheus metrics + SLO tracking.
//
// Design Areas 28, 43, 62, 64. Scrapes services, evaluates SLO burn rate,
// exposes /api/v1/admin/slo and /api/v1/admin/capacity for the frontend.
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
)

// SLOTarget — as in spec Area 64.
type SLOTarget struct {
	Name          string  `json:"name"`
	SLI           string  `json:"sli"`
	TargetPercent float64 `json:"target_percent"`
	WindowDays    int     `json:"window_days"`
}

var defaultSLOs = []SLOTarget{
	{Name: "availability", SLI: "successful_requests / total_requests", TargetPercent: 99.5, WindowDays: 30},
	{Name: "query_latency_p95", SLI: "p95(query_duration_ms)", TargetPercent: 3000, WindowDays: 30},
	{Name: "retrieval_precision", SLI: "eval_precision_at_5", TargetPercent: 80, WindowDays: 7},
	{Name: "answer_faithfulness", SLI: "eval_faithfulness", TargetPercent: 90, WindowDays: 7},
}

// --- HTTP router ---

func main() {
	port := os.Getenv("OBSERVABILITY_HTTP_PORT")
	if port == "" {
		port = "8088"
	}
	r := chi.NewRouter()
	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok","service":"observability-svc"}`))
	})
	r.Get("/api/v1/admin/slo", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(defaultSLOs)
	})
	r.Get("/api/v1/admin/capacity", func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"queries_per_second":  0.0,
			"ingestion_per_min":   0.0,
			"vector_count":        0,
			"cache_hit_rate":      0.0,
		})
	})
	log.Printf("observability-svc starting addr=:%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatal(err)
	}
}
