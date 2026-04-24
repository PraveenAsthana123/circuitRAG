// Package proxy provides a reverse-proxy helper used by the gateway to
// forward user-facing REST calls to internal Python services.
package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

// NewReverseProxy builds a httputil.ReverseProxy targeting the given base URL.
//
// We preserve correlation IDs and tenant headers — those are the contract
// between the gateway and internal services.
func NewReverseProxy(target string) http.Handler {
	u, err := url.Parse(strings.TrimRight(target, "/"))
	if err != nil {
		panic("invalid proxy target: " + target)
	}

	rp := httputil.NewSingleHostReverseProxy(u)

	// Strip the "/api/v1" prefix the public sees if the internal service
	// doesn't expect it — each service here does, so pass through as-is.
	origDirector := rp.Director
	rp.Director = func(r *http.Request) {
		origDirector(r)
		r.Host = u.Host
	}
	return rp
}
