// §8 smoke test for observability-svc.
//
// Closes the structural gap from the 2026-04-30 audit. Tests the
// defaultSLOs table — real production data shipped with the binary.
package main

import (
	"testing"
)

func TestDefaultSLOsAreNonEmpty(t *testing.T) {
	if len(defaultSLOs) == 0 {
		t.Fatal("defaultSLOs must have at least one target — observability-svc must ship with default SLOs")
	}
}

func TestDefaultSLOsHaveValidTargets(t *testing.T) {
	for _, slo := range defaultSLOs {
		if slo.Name == "" {
			t.Errorf("SLO has empty Name: %+v", slo)
		}
		if slo.SLI == "" {
			t.Errorf("SLO %q has empty SLI", slo.Name)
		}
		if slo.WindowDays <= 0 {
			t.Errorf("SLO %q has non-positive WindowDays=%d", slo.Name, slo.WindowDays)
		}
		// Negative: target_percent must be > 0; an SLO with zero
		// target is meaningless.
		if slo.TargetPercent <= 0 {
			t.Errorf("SLO %q has non-positive TargetPercent=%f", slo.Name, slo.TargetPercent)
		}
	}
}

func TestDefaultSLOsHaveAvailability(t *testing.T) {
	// Negative-style: every observability service MUST track
	// availability. Catches a regression where someone removes it
	// from defaults.
	found := false
	for _, slo := range defaultSLOs {
		if slo.Name == "availability" {
			found = true
			if slo.TargetPercent < 95 {
				t.Errorf("availability target_percent=%f is suspiciously low", slo.TargetPercent)
			}
		}
	}
	if !found {
		t.Error("defaultSLOs must include an 'availability' target")
	}
}
