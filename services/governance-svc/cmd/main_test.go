// §8 smoke test for governance-svc.
//
// Closes the structural gap from the 2026-04-30 audit. Tests the
// PolicyEngine + HITLService stubs at the data-shape level — when
// the full implementation lands, these stubs grow real assertions
// without changing the test surface.
package main

import (
	"testing"

	"github.com/google/uuid"
)

func TestPolicyEngineEvaluateNoCrash(t *testing.T) {
	// Stub returns ("approve", true) for any input — verify it
	// doesn't crash and the contract holds.
	e := &PolicyEngine{}
	action, passed := e.Evaluate("any-policy", map[string]any{"key": "value"})
	if action == "" {
		t.Error("PolicyEngine.Evaluate must return a non-empty action string")
	}
	_ = passed // contract is shape-only at the stub stage
}

func TestHITLServiceEnqueueAcceptsValidItem(t *testing.T) {
	// Negative: panic on enqueue would be a regression.
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("HITLService.Enqueue panicked: %v", r)
		}
	}()
	s := &HITLService{}
	s.Enqueue(HITLItem{
		ID:           uuid.New(),
		TenantID:     uuid.New(),
		Question:     "is this prediction approved?",
		Answer:       "yes",
		Confidence:   0.42,
		FlagReason:   "low_confidence",
		ReviewStatus: "pending",
	})
}

func TestAuditLogRecordAcceptsValidPayload(t *testing.T) {
	// Audit log is fail-open at the stub stage but must accept any
	// map[string]any — empty included.
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("AuditLog.Record panicked on empty payload: %v", r)
		}
	}()
	a := &AuditLog{}
	a.Record("test-event", map[string]any{})
	a.Record("test-event-with-fields", map[string]any{
		"tenant_id": uuid.New(),
		"actor":     "test",
	})
}
