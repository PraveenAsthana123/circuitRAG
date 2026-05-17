# Negative drills for Iter 49 (2026-05-17): SLO → PromQL renderer.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slo.promql import render, render_burn_rate


def test_unknown_policy_returns_none():
    assert render("does-not-exist") is None


def test_availability_query_uses_rate_ratio():
    q = render("availability")
    assert q is not None
    assert q.metric_name == "availability_percent"
    assert "http_requests_total" in q.query
    # Defends against div-by-zero with clamp_min.
    assert "clamp_min" in q.query
    # Multiplies by 100 to get percent.
    assert "* 100" in q.query


def test_p95_uses_histogram_quantile():
    q = render("p95_latency")
    assert "histogram_quantile(0.95" in q.query
    assert "http_request_duration_ms_bucket" in q.query
    assert q.metric_name == "p95_latency_ms"


def test_p99_uses_histogram_quantile():
    q = render("p99_latency")
    assert "histogram_quantile(0.99" in q.query


def test_window_is_propagated_into_query():
    q = render("error_rate", window="5m")
    assert "[5m]" in q.query
    assert q.window == "5m"


def test_grounding_and_citation_average_over_time():
    g = render("grounding_score")
    assert "avg_over_time(rag_grounding_score" in g.query
    c = render("citation_coverage")
    assert "avg_over_time(rag_citation_coverage" in c.query


def test_cost_per_request_is_ratio():
    q = render("cost_per_request")
    assert "llm_cost_usd_total" in q.query
    assert "http_requests_total" in q.query
    assert "clamp_min" in q.query  # defensive divide


def test_BACKDOOR_CHECK_render_is_pure_no_side_effects():
    """Calling render twice produces identical output (no shared
    mutable state — important for thread-safety in real prod)."""
    q1 = render("p95_latency", window="1h")
    q2 = render("p95_latency", window="1h")
    assert q1.query == q2.query


def test_render_burn_rate_uses_correct_window():
    out = render_burn_rate(60)
    assert "[60m]" in out
    assert "clamp_min" in out


def test_render_burn_rate_with_minutes():
    out = render_burn_rate(1440)  # 24h
    assert "[1440m]" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
