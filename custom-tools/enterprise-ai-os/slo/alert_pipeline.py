# Added Iter 39 (2026-05-17) — wires AlertRules + BurnRateAlerts
# to a Notifier so the evaluator's output actually reaches an
# inbox/queue. Pre-fix the two rule engines returned alert dicts
# and the caller had to remember to fan them out to whatever
# notifier — the wiring step was on the operator.

from typing import Dict, Any, List, Optional

from slo.alert_rules import AlertRules
from slo.burn_rate import BurnRateAlerts
from slo.notifier import Notifier, LogNotifier


class AlertPipeline:
    """Composes AlertRules + BurnRateAlerts and routes their output
    through a Notifier. Returns the alerts that fired for tests +
    observability."""

    def __init__(
        self,
        notifier: Optional[Notifier] = None,
        alert_rules: Optional[AlertRules] = None,
        burn_rate_alerts: Optional[BurnRateAlerts] = None,
    ):
        self.notifier = notifier or LogNotifier()
        self.alert_rules = alert_rules or AlertRules()
        self.burn_rate_alerts = burn_rate_alerts or BurnRateAlerts()

    def evaluate_and_notify(
        self,
        slo_report: Dict[str, Any],
        short_window_error_rates: Optional[Dict[int, float]] = None,
        slo_target_error_rate: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Run both rule engines on the inputs, fan their output to
        the notifier, return the consolidated alert list."""
        alerts: List[Dict[str, Any]] = list(self.alert_rules.evaluate(slo_report))

        if (short_window_error_rates is not None
                and slo_target_error_rate is not None):
            alerts.extend(self.burn_rate_alerts.evaluate(
                short_window_error_rates, slo_target_error_rate,
            ))

        if alerts:
            self.notifier.notify_all(alerts)

        return alerts
