// §8 smoke test for finops-svc.
//
// Closes the structural gap from the 2026-04-30 audit: the service
// had a Dockerfile but no test files. Tests the production
// CostAggregator.ComputeShadowCost — real production data
// (shadowRates table) + real branches (matched/unmatched model).
package main

import (
	"testing"
)

func TestComputeShadowCostMatchedModel(t *testing.T) {
	a := &CostAggregator{}
	// llama3.1:8b → input $0.0001/1k + completion $0.0003/1k.
	// 1000 prompt tokens + 1000 completion tokens = $0.0001 + $0.0003 = $0.0004.
	got := a.ComputeShadowCost(1000, 1000, "llama3.1:8b")
	want := 0.0004
	if abs(got-want) > 1e-9 {
		t.Errorf("ComputeShadowCost matched: want %f, got %f", want, got)
	}
}

func TestComputeShadowCostUnmatchedModel(t *testing.T) {
	// Negative: unknown model returns 0 (don't crash, don't fabricate).
	a := &CostAggregator{}
	got := a.ComputeShadowCost(1000, 1000, "phantom-model-xyz")
	if got != 0 {
		t.Errorf("unknown model should return 0, got %f", got)
	}
}

func TestComputeShadowCostScales(t *testing.T) {
	// 10x tokens → 10x cost. Catches integer truncation regressions.
	a := &CostAggregator{}
	one := a.ComputeShadowCost(100, 100, "mistral:7b")
	ten := a.ComputeShadowCost(1000, 1000, "mistral:7b")
	if abs(ten-10*one) > 1e-9 {
		t.Errorf("scaling broken: 10× tokens != 10× cost (1×=%f, 10×=%f)", one, ten)
	}
}

func TestShadowRatesNonEmpty(t *testing.T) {
	if len(shadowRates) == 0 {
		t.Fatal("shadowRates table must have at least one entry — finops can't price anything otherwise")
	}
	for _, r := range shadowRates {
		if r.Model == "" {
			t.Errorf("shadowRate entry has empty Model: %+v", r)
		}
		if r.InputPerK < 0 || r.CompletionPerK < 0 {
			t.Errorf("shadowRate %s has negative pricing: %+v", r.Model, r)
		}
	}
}

func abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
