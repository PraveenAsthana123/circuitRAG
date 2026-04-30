# CDN integration — operator runbook

> Wires a real CDN provider (Cloudflare / Fastly / CloudFront) in
> front of NGINX without breaking the per-route cache invariants
> already enforced at origin.
>
> Locked by `mcp/tests/drill_cdn_cache_invariants.py`.

## Default state (out of the box)

`infra/nginx/nginx.conf` enforces per-route cache headers AT ORIGIN:

| Route | Cache-Control | Why |
| --- | --- | --- |
| `/api/` | `no-store, private` | Responses are tenant-scoped by JWT; never cacheable |
| `/api/v1/documents/upload` | `no-store, private` | User-bound data; never cacheable |
| `/_next/static/` | `public` + `expires 7d` (~604800s) | Hashed asset paths; safe to cache 7 days |
| `/healthz` | (no add_header; default) | Health probe; ephemeral; no cache benefit |
| `/` (Next.js SSR) | (none; defers to Next.js response) | SSR may set its own cache headers per page |

The `add_header Cache-Control "..." always;` directive sets the
header even on 4xx/5xx responses — critical so a CDN provider doesn't
cache an error page from `/api/` and serve it as if successful.

`proxy_no_cache 1; proxy_cache_bypass 1;` ensures NGINX itself doesn't
cache these routes (additional defense in depth — even if a CDN
misbehaves, the origin will not return stale tenant data).

## Choosing a CDN provider

| Provider | Best for | Operator setup |
| --- | --- | --- |
| **Cloudflare** | Global edge + free tier + WAF | DNS-based; orange-cloud the apex |
| **Fastly** | Programmable edge (VCL); fast purge | DNS-based; service config |
| **CloudFront** | AWS-native; integrates with ACM | DNS-based; distribution + behaviors |
| **No CDN** | Single-region traffic; admin-only apps | Skip — NGINX is sufficient |

This project's traffic profile (multi-tenant SaaS with sensitive API
data + small static surface) means the CDN is mainly for `/_next/static/`
and TLS-termination geo-distribution, not API caching.

## Setup procedure (Cloudflare canonical example)

### 1. Provision the CDN account (operator action)

```bash
# 1a. Create Cloudflare account (free tier OK for Phase 1)
# 1b. Add the project domain (documind.example.com)
# 1c. Cloudflare gives you 2 nameservers
# 1d. Update DNS at your registrar to point to those nameservers
# 1e. Wait for propagation (~5 min to 24h)
```

### 2. Add a Cloudflare API token to local secrets

```bash
mkdir -p .loop
cat > .loop/cdn.env <<'EOF'
# Cloudflare API token with Zone:Cache Purge + Zone:Read scopes
# Generate at: https://dash.cloudflare.com/profile/api-tokens
CLOUDFLARE_API_TOKEN="REPLACE_ME"
CLOUDFLARE_ZONE_ID="REPLACE_ME"
CLOUDFLARE_API_BASE="https://api.cloudflare.com/client/v4"
EOF
chmod 600 .loop/cdn.env
```

This mirrors the `.loop/<service>.env` chmod-600 pattern from
`alertmanager-webhook.md` and `council-stats.env`.

### 3. Configure CDN cache rules

At the CDN provider, create exactly THREE cache rules in order:

```
Rule 1 (priority 1) — Bypass cache for /api/*
  Match:   URL path starts with "/api/"
  Action:  Bypass cache; forward all headers
  Why:     Origin returns Cache-Control: no-store, private. CDN MUST
           honor this. Defense in depth: explicit bypass rule.

Rule 2 (priority 2) — Long cache for /_next/static/*
  Match:   URL path starts with "/_next/static/"
  Action:  Cache 7 days; cache key includes Accept-Encoding
  Why:     Hashed asset paths. Origin sets expires 7d already.

Rule 3 (priority 3, default) — No cache for everything else
  Match:   *
  Action:  Bypass cache (defer to origin)
  Why:     SSR pages from Next.js may include user-specific HTML.
           Conservative default; loosen per-page when needed.
```

### 4. Update DNS

Point the apex (`documind.example.com`) at NGINX's public IP.
Cloudflare orange-clouds it, terminating TLS at edge and forwarding
to NGINX over HTTPS.

### 5. Verify cache invariants

```bash
# 5a. API endpoint must NEVER be cached
curl -sI https://documind.example.com/api/v1/sidecar/events | grep -iE "cache-control|cf-cache"
# Expected: cache-control: no-store, private
# Expected: cf-cache-status: BYPASS  (or DYNAMIC; never HIT)

# 5b. Static asset must be cached
curl -sI https://documind.example.com/_next/static/abc123.js | grep -iE "cache-control|cf-cache|x-cache-status"
# Expected: cache-control: public ... max-age=604800
# Expected: cf-cache-status: HIT (after warmup)

# 5c. Run the drill that locks the contract
python3 mcp/tests/drill_cdn_cache_invariants.py
```

### 6. Purge on deploy

After every deploy that changes `_next/static/` content:

```bash
# Sourced from .loop/cdn.env at deploy time
set -a; . .loop/cdn.env; set +a
curl -X POST "$CLOUDFLARE_API_BASE/zones/$CLOUDFLARE_ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prefixes":["https://documind.example.com/_next/static/"]}'
```

Hashed asset filenames usually make this purge unnecessary, but
explicit purge is harmless and useful when rolling back.

## Failure modes & detection

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| API response stale (user A sees user B's data) | CDN cached `/api/` response despite `no-store` | Check Rule 1 priority + provider's per-account override; purge cache; investigate |
| Static asset 404 after deploy | CDN cached old asset name; new path not yet hot | Run purge command; CDN re-fetches |
| `cf-cache-status: HIT` on `/api/` | CDN ignoring origin `Cache-Control` | Provider misconfiguration; escalate; emergency: orange-cloud OFF |
| `cf-cache-status: MISS` on `/_next/static/` | First request after deploy or short TTL | Expected; subsequent requests should HIT |
| Drill fails (origin no longer sets `no-store`) | nginx.conf regression | Revert nginx.conf change; re-run drill |

## Why this lives outside `.env`

`.loop/cdn.env` is the project's secret-side-channel, mirroring
`council-stats.env` + `alertmanager.env`. CDN tokens must NOT leak
into git — they grant the ability to purge or reconfigure the CDN.
chmod 600 is the access discipline; gitignored is the storage
discipline.

## Drill — what it locks

`mcp/tests/drill_cdn_cache_invariants.py` asserts AT ORIGIN (no live
CDN required for verification):

1. nginx.conf `/api/` location has `Cache-Control: no-store, private`
2. nginx.conf upload location has `Cache-Control: no-store, private`
3. nginx.conf static location has `expires 7d` (or equivalent
   `max-age` + `public`)
4. NEGATIVE: nginx.conf `/api/` MUST NOT contain `max-age` or `public`
5. NEGATIVE: nginx.conf MUST NOT have a global default
   `add_header Cache-Control "public ..."` that would override per-route
6. NEGATIVE: scenario doc citation present

Drift in any of those fires the drill. Operator restores nginx.conf
before merging; CDN provider config is operator-owned and
out-of-scope for the drill.

## Composes with

- `docs/runbooks/alertmanager-webhook.md` — same `.loop/<service>.env`
  + chmod 600 pattern
- `docs/runbooks/issue-dispatcher.md` — same audit-row + safety-gate
  discipline
- `/admin/api-gateway/deep` — gateway + edge story; CDN sits ahead of
  edge LB (NGINX) in the request path
- `/admin/scaling-patterns/deep#load-balancing` — CDN as the geo-LB
  layer; NGINX as the service-LB layer
- `docs/scenarios/phase-01-edge-traffic-security.md` §2 — canonical
  CDN scenario this runbook implements
- §50 (global) — same secret pattern + drill discipline applied to a
  different operational surface

## Brutal rule

> A CDN that caches `/api/` responses is a security incident waiting
> to happen — one tenant's data served to another. The drill exists
> because origin headers are the LAST line of defense; if origin
> doesn't say `no-store`, no provider rule will save you.
