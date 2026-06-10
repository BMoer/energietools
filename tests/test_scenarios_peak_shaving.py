# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Greedy Peak-Shaving — Golden-Tests gegen die pvtool-Referenz."""

import pytest

from energietools.capabilities.scenarios.peak_shaving import (
    run_peak_shaving,
)
from energietools.components.battery import Battery

# 5 Intervalle Januar + 5 Februar (stündlich), Netto-Last mit Spitzen.
CONS = [1, 2, 5, 4, 1, 2, 6, 3, 1, 2]
PROD = [0, 0, 0, 0, 3, 0, 0, 0, 0, 1]
NET = [c - p for c, p in zip(CONS, PROD)]  # [1,2,5,4,-2, 2,6,3,1,1]
MONTH = ["2025-01"] * 5 + ["2025-02"] * 5


def _battery(cap: float) -> Battery:
    return Battery.new(
        cap, c_rate=0.5, charge_efficiency=0.95, discharge_efficiency=0.95,
        min_soc_pct=5.0, max_soc_pct=95.0,
    )


def _run(cap: float, combine: bool):
    return run_peak_shaving(
        NET, MONTH, _battery(cap),
        peak_threshold_kw=3.0, demand_charge_eur_per_kw_year=63.0,
        grid_buy_price_eur=0.25, dt_hours=1.0, combine_self_consumption=combine,
    )


GOLDEN = {
    ("cap0",): dict(baseline_peak_kw=6.0, achieved_peak_kw=6.0, peak_reduction_kw=0.0,
        demand_savings_eur=0.0, energy_savings_eur=0.0, net_benefit_eur=0.0,
        grid_purchase_kwh=25.0, battery_charge_kwh=0.0, battery_discharge_kwh=0.0, cycles=0.0),
    ("combine_true",): dict(baseline_peak_kw=6.0, achieved_peak_kw=6.0, peak_reduction_kw=0.0,
        demand_savings_eur=5.25, energy_savings_eur=0.45, net_benefit_eur=5.7,
        grid_purchase_kwh=23.2, battery_charge_kwh=1.9, battery_discharge_kwh=1.8, cycles=0.2),
    ("combine_false",): dict(baseline_peak_kw=6.0, achieved_peak_kw=5.0, peak_reduction_kw=1.0,
        demand_savings_eur=14.73, energy_savings_eur=0.45, net_benefit_eur=15.18,
        grid_purchase_kwh=23.2, battery_charge_kwh=1.9, battery_discharge_kwh=1.8, cycles=0.2),
}


def _assert(res, expected):
    for field, want in expected.items():
        got = getattr(res, field)
        assert got == pytest.approx(want, abs=0.051), f"{field}: {got} != {want}"


def test_cap0_baseline():
    _assert(_run(0.0, True), GOLDEN[("cap0",)])


def test_combine_true():
    _assert(_run(10.0, True), GOLDEN[("combine_true",)])


def test_combine_false_shaves_peak():
    res = _run(10.0, False)
    _assert(res, GOLDEN[("combine_false",)])
    assert res.peak_reduction_kw == pytest.approx(1.0, abs=0.01)


def test_invalid_threshold():
    with pytest.raises(ValueError, match="peak_threshold_kw"):
        run_peak_shaving(NET, MONTH, _battery(10.0), peak_threshold_kw=0.0)
