// Package jwt handles RS256 access-token issuance + refresh + verification.
//
// Keys are loaded at startup from disk (DOCUMIND_JWT_PRIVATE_KEY_PATH /
// DOCUMIND_JWT_PUBLIC_KEY_PATH). Access tokens are 15 minutes; refresh
// tokens are 7 days. Revocation is via a Redis deny-list: `deny:<jti>`.
//
// NEVER hardcode secrets; `.env.template` points at `scripts/dev-keys/`
// which is gitignored.
package jwt

import (
	"context"
	"crypto/rsa"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

type Claims struct {
	TenantID string   `json:"tenant_id"`
	UserID   string   `json:"sub"`
	Email    string   `json:"email"`
	Roles    []string `json:"roles"`
	TokenKind string  `json:"kind"` // "access" | "refresh"
	jwt.RegisteredClaims
}

type Issuer struct {
	priv       *rsa.PrivateKey
	pub        *rsa.PublicKey
	iss        string
	aud        string
	accessTTL  time.Duration
	refreshTTL time.Duration
	denylist   Denylist
}

type Denylist interface {
	IsDenied(ctx context.Context, jti string) (bool, error)
	Deny(ctx context.Context, jti string, ttl time.Duration) error
}

// NewIssuer loads the keypair from disk + returns an Issuer. Caller is
// expected to wire a Redis-backed Denylist; an in-memory noop is provided
// for dev.
func NewIssuer(
	privPath, pubPath, issuer, audience string,
	accessTTL, refreshTTL time.Duration,
	denylist Denylist,
) (*Issuer, error) {
	privBytes, err := os.ReadFile(privPath)
	if err != nil {
		return nil, fmt.Errorf("read private key: %w", err)
	}
	priv, err := jwt.ParseRSAPrivateKeyFromPEM(privBytes)
	if err != nil {
		return nil, fmt.Errorf("parse private key: %w", err)
	}
	pubBytes, err := os.ReadFile(pubPath)
	if err != nil {
		return nil, fmt.Errorf("read public key: %w", err)
	}
	pub, err := jwt.ParseRSAPublicKeyFromPEM(pubBytes)
	if err != nil {
		return nil, fmt.Errorf("parse public key: %w", err)
	}
	if denylist == nil {
		denylist = NoopDenylist{}
	}
	return &Issuer{
		priv:       priv,
		pub:        pub,
		iss:        issuer,
		aud:        audience,
		accessTTL:  accessTTL,
		refreshTTL: refreshTTL,
		denylist:   denylist,
	}, nil
}

// Mint returns (access, refresh, error). Each token has a unique jti.
func (i *Issuer) Mint(tenantID, userID, email string, roles []string) (string, string, error) {
	access, err := i.sign(tenantID, userID, email, roles, "access", i.accessTTL)
	if err != nil {
		return "", "", err
	}
	refresh, err := i.sign(tenantID, userID, email, roles, "refresh", i.refreshTTL)
	if err != nil {
		return "", "", err
	}
	return access, refresh, nil
}

func (i *Issuer) sign(tenantID, userID, email string, roles []string, kind string, ttl time.Duration) (string, error) {
	now := time.Now().UTC()
	claims := Claims{
		TenantID:  tenantID,
		UserID:    userID,
		Email:     email,
		Roles:     roles,
		TokenKind: kind,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    i.iss,
			Audience:  jwt.ClaimStrings{i.aud},
			IssuedAt:  jwt.NewNumericDate(now),
			NotBefore: jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
			ID:        uuid.NewString(),
			Subject:   userID,
		},
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	return tok.SignedString(i.priv)
}

// Verify parses + validates. Returns claims on success; error on invalid,
// expired, wrong kind, or deny-listed.
func (i *Issuer) Verify(ctx context.Context, raw, expectKind string) (*Claims, error) {
	claims := &Claims{}
	tok, err := jwt.ParseWithClaims(raw, claims, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected alg %v", t.Header["alg"])
		}
		return i.pub, nil
	},
		jwt.WithIssuer(i.iss),
		jwt.WithAudience(i.aud),
		jwt.WithExpirationRequired(),
		jwt.WithValidMethods([]string{"RS256"}),
	)
	if err != nil || !tok.Valid {
		return nil, fmt.Errorf("invalid token: %w", err)
	}
	if expectKind != "" && claims.TokenKind != expectKind {
		return nil, fmt.Errorf("wrong token kind: got %q want %q", claims.TokenKind, expectKind)
	}
	if claims.ID != "" {
		denied, derr := i.denylist.IsDenied(ctx, claims.ID)
		if derr != nil {
			return nil, fmt.Errorf("denylist check: %w", derr)
		}
		if denied {
			return nil, errors.New("token revoked")
		}
	}
	return claims, nil
}

// Revoke adds a jti to the deny-list until token natural expiry.
func (i *Issuer) Revoke(ctx context.Context, jti string, expiresAt time.Time) error {
	ttl := time.Until(expiresAt)
	if ttl <= 0 {
		return nil
	}
	return i.denylist.Deny(ctx, jti, ttl)
}

// NoopDenylist is a dev-mode fallback. DO NOT ship to prod.
type NoopDenylist struct{}

func (NoopDenylist) IsDenied(context.Context, string) (bool, error)           { return false, nil }
func (NoopDenylist) Deny(context.Context, string, time.Duration) error        { return nil }
