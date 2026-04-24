package middleware

import (
	"encoding/json"
	"net/http"
)

// BodyLimit caps request-body size at the gateway. Upload endpoints use a
// larger cap (applied via a second middleware instance on those routes).
func BodyLimit(maxBytes int64) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Cheap header check first — rejects obvious offenders without buffering.
			if r.ContentLength > maxBytes {
				rejectOversize(w, maxBytes)
				return
			}
			// Defense in depth: cap the actual read.
			r.Body = http.MaxBytesReader(w, r.Body, maxBytes)
			next.ServeHTTP(w, r)
		})
	}
}

func rejectOversize(w http.ResponseWriter, limit int64) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusRequestEntityTooLarge)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"detail":     "request body too large",
		"error_code": "BODY_TOO_LARGE",
		"details":    map[string]any{"max_bytes": limit},
	})
}
