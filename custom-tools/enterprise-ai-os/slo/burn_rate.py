# Added Iter 19 (2026-05-17) — multi-window multi-burn-rate alerts
# per the Google SRE Workbook (Ch. 5, "Alerting on SLOs").
#
# Pre-fix: alert_rules.py only fired when an SLO had already failed
# OR the error budget for the WHOLE WINDOW was exhausted. Both are
# lagging — by the time they fire the budget is already gone.
#
# Burn-rate alerts fire when the SHORT-WINDOW error rate exceeds a
# threshold high enough that, if sustained, it would exhaust the
# WINDOW budget in less than the configured horizon. They give the
# operator a chance to react before the SLO violates.
#
# Standard Google SRE multi-window pairs:
#   - Page (fast):  14.4× burn over 1h  → burns 2% of 30d budget
#   - Page (slow):   6× burn over 6h    → burns 5% of 30d budget
#   - Ticket (slow): 1× burn over 3d    → burns 10% of 30d budget

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class BurnRateWindow:
    name: str
    burn_rate: float        # how many "budgets per period" we're burning
    short_window_minutes: int
    severity: str           # "page" | "ticket" | "info"


DEFAULT_WINDOWS: List[BurnRateWindow] = [
    BurnRateWindow("fast_page",  14.4, 60,     "page"),    # 1h window
    BurnRateWindow("slow_page",   6.0, 60 * 6, "page"),    # 6h window
    BurnRateWindow("ticket",      1.0, 60 * 72, "ticket"), # 3d window
]


class BurnRateAlerts:
    """
    Computes burn-rate alerts given the short-window error rate and
    the budget-rate (the error rate that exactly consumes the SLO
    budget over the full 30d period).
    """

    def __init__(self, windows: List[BurnRateWindow] = None):
        self.windows = windows if windows is not None else DEFAULT_WINDOWS

    def evaluate(
        self,
        short_window_error_rate: Dict[int, float],
        slo_target_error_rate: float,
    ) -> List[Dict[str, Any]]:
        """
        short_window_error_rate: {window_minutes -> observed error rate}
          Example: {60: 0.012, 360: 0.008, 4320: 0.002}
        slo_target_error_rate: the error rate the SLO budget allows
          across the full window (e.g. 0.001 = 99.9%-availability SLO).
        Returns: list of alert dicts for windows where observed rate
          exceeds burn_rate * slo_target_error_rate.
        """
        if slo_target_error_rate <= 0:
            raise ValueError("slo_target_error_rate must be > 0")

        alerts = []
        for w in self.windows:
            observed = short_window_error_rate.get(w.short_window_minutes)
            if observed is None:
                continue
            burn_threshold = w.burn_rate * slo_target_error_rate
            if observed > burn_threshold:
                alerts.append({
                    "severity": w.severity,
                    "type": "burn_rate",
                    "window": w.name,
                    "short_window_minutes": w.short_window_minutes,
                    "burn_rate_required": w.burn_rate,
                    "burn_rate_observed": (
                        observed / slo_target_error_rate
                    ),
                    "observed_error_rate": observed,
                    "slo_target_error_rate": slo_target_error_rate,
                    "message": (
                        f"Burn-rate {observed / slo_target_error_rate:.1f}× "
                        f"observed over {w.short_window_minutes}min — exceeds "
                        f"{w.burn_rate}× threshold for {w.severity} alert"
                    ),
                })
        return alerts
