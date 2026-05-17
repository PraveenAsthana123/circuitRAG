# Negative drills for Iter 19 (2026-05-17): SLO multi-window
# multi-burn-rate alerts.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slo.burn_rate import BurnRateAlerts, BurnRateWindow, DEFAULT_WINDOWS


# 99.9% availability SLO → 0.001 error budget rate.
SLO_TARGET = 0.001


def test_no_alerts_when_below_all_thresholds():
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.0005, 360: 0.0005, 4320: 0.0005},
        slo_target_error_rate=SLO_TARGET,
    )
    assert out == []


def test_fast_page_fires_at_15x_burn():
    """BACKDOOR CHECK: a 15× burn over 1h must page (>14.4× threshold)."""
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.015, 360: 0.001, 4320: 0.001},
        slo_target_error_rate=SLO_TARGET,
    )
    paging = [a for a in out if a["severity"] == "page" and a["window"] == "fast_page"]
    assert len(paging) == 1
    assert paging[0]["burn_rate_observed"] >= 14.4


def test_slow_page_fires_at_7x_burn_over_6h():
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.001, 360: 0.007, 4320: 0.001},
        slo_target_error_rate=SLO_TARGET,
    )
    slow = [a for a in out if a["window"] == "slow_page"]
    assert len(slow) == 1
    assert slow[0]["severity"] == "page"


def test_ticket_fires_at_2x_burn_over_3d():
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.001, 360: 0.001, 4320: 0.002},
        slo_target_error_rate=SLO_TARGET,
    )
    tickets = [a for a in out if a["severity"] == "ticket"]
    assert len(tickets) == 1


def test_sustained_high_burn_fires_multiple_windows():
    """A 20× burn that's been going for hours should fire fast AND slow."""
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.02, 360: 0.02, 4320: 0.02},
        slo_target_error_rate=SLO_TARGET,
    )
    severities = {a["severity"] for a in out}
    assert "page" in severities
    assert "ticket" in severities


def test_missing_window_data_is_skipped_not_assumed_zero():
    """If we don't have data for a window, don't fire OR suppress."""
    alerts = BurnRateAlerts()
    out = alerts.evaluate(
        short_window_error_rate={60: 0.02},  # no 6h or 3d data
        slo_target_error_rate=SLO_TARGET,
    )
    # Only fast_page should fire — slow_page + ticket have no data.
    windows = {a["window"] for a in out}
    assert windows == {"fast_page"}


def test_invalid_slo_target_rejected():
    alerts = BurnRateAlerts()
    with pytest.raises(ValueError):
        alerts.evaluate({60: 0.001}, slo_target_error_rate=0)
    with pytest.raises(ValueError):
        alerts.evaluate({60: 0.001}, slo_target_error_rate=-0.5)


def test_custom_windows():
    custom = [BurnRateWindow("custom_tight", 100.0, 5, "page")]
    alerts = BurnRateAlerts(custom)
    out = alerts.evaluate(
        short_window_error_rate={5: 0.5},  # 500× burn at 99.9% SLO
        slo_target_error_rate=SLO_TARGET,
    )
    assert len(out) == 1
    assert out[0]["window"] == "custom_tight"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
