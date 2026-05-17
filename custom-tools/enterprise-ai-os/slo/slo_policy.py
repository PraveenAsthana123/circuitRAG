from dataclasses import dataclass


@dataclass
class SLOPolicy:
    name: str
    target: float
    metric_name: str
    comparison: str
    window: str = "30d"


class SLOPolicyRegistry:
    def default_policies(self):
        return [
            SLOPolicy("availability", 99.9, "availability_percent", ">="),
            SLOPolicy("p95_latency", 2000, "p95_latency_ms", "<="),
            SLOPolicy("p99_latency", 5000, "p99_latency_ms", "<="),
            SLOPolicy("error_rate", 1.0, "error_rate_percent", "<="),
            SLOPolicy("grounding_score", 0.90, "grounding_score", ">="),
            SLOPolicy("citation_coverage", 0.95, "citation_coverage", ">="),
            SLOPolicy("cost_per_request", 0.02, "cost_usd", "<="),
        ]

    def evaluate(self, policy: SLOPolicy, value: float) -> dict:
        if policy.comparison == ">=":
            passed = value >= policy.target
        elif policy.comparison == "<=":
            passed = value <= policy.target
        else:
            raise ValueError(f"Unsupported comparison: {policy.comparison}")

        return {
            "slo": policy.name,
            "metric": policy.metric_name,
            "target": policy.target,
            "actual": value,
            "passed": passed,
            "window": policy.window,
        }
