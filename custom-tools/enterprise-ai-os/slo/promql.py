# Added Iter 49 (2026-05-17) — translates an SLOPolicy into a
# Prometheus PromQL query string. Pre-fix the SLO module evaluated
# pre-computed scalar values that someone else had to query out of
# Prometheus; the policy → PromQL bridge was the operator's
# responsibility. With this layer, callers can render the PromQL,
# feed it to a real Prometheus client, and pass the result back
# to SLOPolicyRegistry.evaluate().
#
# This is a code-only translation — actually CALLING Prometheus
# still needs an HTTP client + auth, which is operator infra.

from dataclasses import dataclass
from typing import Optional


# Convention: every histogram metric is named with the _seconds or _ms
# suffix and is a *_bucket vec. This file uses _ms.
LATENCY_METRIC_TEMPLATE = "histogram_quantile({quantile}, sum(rate({metric}_bucket[{window}])) by (le))"


@dataclass
class PromQLQuery:
    """A rendered PromQL string + the time-window it represents.
    Caller hands `query` to prometheus_api_client.PrometheusConnect.custom_query()
    (or HTTP POST to /api/v1/query) and feeds the scalar into
    SLOPolicyRegistry.evaluate()."""
    metric_name: str  # which SLO this is for (e.g. "p95_latency")
    query: str
    window: str       # e.g. "30d"


def render(policy_name: str, window: str = "30d") -> Optional[PromQLQuery]:
    """Render the canonical PromQL for a known SLO policy name.
    Returns None for an unknown policy_name so the caller can decide
    whether to fall back."""
    # Pre-fix SLOPolicyRegistry exposed these metric_names:
    #   availability_percent, p95_latency_ms, p99_latency_ms,
    #   error_rate_percent, grounding_score, citation_coverage,
    #   cost_usd
    # The translation below maps each to a canonical PromQL.

    if policy_name == "availability":
        # 1 - (5xx_rate / total_rate) * 100  → availability_percent
        q = (
            f"(1 - (sum(rate(http_requests_total{{status=~\"5..\"}}[{window}])) "
            f"/ clamp_min(sum(rate(http_requests_total[{window}])), 1))) * 100"
        )
        return PromQLQuery("availability_percent", q, window)

    if policy_name == "p95_latency":
        q = LATENCY_METRIC_TEMPLATE.format(
            quantile=0.95, metric="http_request_duration_ms", window=window,
        )
        return PromQLQuery("p95_latency_ms", q, window)

    if policy_name == "p99_latency":
        q = LATENCY_METRIC_TEMPLATE.format(
            quantile=0.99, metric="http_request_duration_ms", window=window,
        )
        return PromQLQuery("p99_latency_ms", q, window)

    if policy_name == "error_rate":
        q = (
            f"(sum(rate(http_requests_total{{status=~\"5..\"}}[{window}])) "
            f"/ clamp_min(sum(rate(http_requests_total[{window}])), 1)) * 100"
        )
        return PromQLQuery("error_rate_percent", q, window)

    if policy_name == "grounding_score":
        q = f"avg_over_time(rag_grounding_score[{window}])"
        return PromQLQuery("grounding_score", q, window)

    if policy_name == "citation_coverage":
        q = f"avg_over_time(rag_citation_coverage[{window}])"
        return PromQLQuery("citation_coverage", q, window)

    if policy_name == "cost_per_request":
        # Cost USD per request, averaged over the window.
        q = (
            f"sum(rate(llm_cost_usd_total[{window}])) "
            f"/ clamp_min(sum(rate(http_requests_total[{window}])), 1)"
        )
        return PromQLQuery("cost_usd", q, window)

    return None


def render_burn_rate(short_window_minutes: int) -> str:
    """PromQL for the short-window error rate used by BurnRateAlerts."""
    return (
        f"sum(rate(http_requests_total{{status=~\"5..\"}}[{short_window_minutes}m])) "
        f"/ clamp_min(sum(rate(http_requests_total[{short_window_minutes}m])), 1)"
    )
