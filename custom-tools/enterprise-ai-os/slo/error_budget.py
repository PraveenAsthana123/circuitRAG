class ErrorBudget:
    def calculate(
        self,
        total_requests: int,
        failed_requests: int,
        allowed_error_rate_percent: float = 1.0
    ) -> dict:

        if total_requests <= 0:
            return {
                "total_requests": 0,
                "failed_requests": 0,
                "error_rate_percent": 0.0,
                "budget_remaining_percent": 100.0,
                "status": "no_traffic",
            }

        error_rate = (failed_requests / total_requests) * 100
        budget_remaining = max(allowed_error_rate_percent - error_rate, 0)

        return {
            "total_requests": total_requests,
            "failed_requests": failed_requests,
            "error_rate_percent": round(error_rate, 3),
            "allowed_error_rate_percent": allowed_error_rate_percent,
            "budget_remaining_percent": round(budget_remaining, 3),
            "budget_exhausted": error_rate > allowed_error_rate_percent,
        }
