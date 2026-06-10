# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
"""Preis-getriebener Dispatch — Golden-Tests gegen die pvtool-Referenz.

Die erwarteten Werte stammen aus ``pvtool.battery.simulate_battery``
(batterystorage-sim, Jakob/holzjfk-a11y) auf demselben Datensatz — sie sichern
ab, dass der pandas-freie energietools-Port bit-genau dieselbe Bilanz + Ökonomie
liefert (self_consumption / spot_optimized / arbitrage, mit/ohne Speicher).
"""

import pytest

from energietools.capabilities.scenarios.dispatch import (
    EconomicDispatchResult,
    MarketTerms,
    simulate_battery,
)
from energietools.components.battery import Battery

# 16 stündliche Intervalle (ein Tag), deterministisch.
SURPLUS = [2, -1, 3, -2, 1, -3, 4, -1, -2, 2, -1, 3, -2, 1, -3, 4]
SPOT = [0.05, 0.20, 0.04, 0.30, 0.10, 0.25, 0.03, 0.28,
        0.22, 0.06, 0.24, 0.05, 0.27, 0.09, 0.26, 0.04]
DAY = [0] * 16
TERMS = MarketTerms(
    grid_buy_price_eur=0.25, feedin_tariff_eur=0.08,
    grid_fees_eur_per_kwh=0.13, feedin_spot_discount=0.0,
    charging_grid_fee_eur_per_kwh=None,
)


def _battery(cap: float) -> Battery:
    return Battery.new(
        cap, c_rate=0.5, charge_efficiency=0.95, discharge_efficiency=0.95,
        min_soc_pct=5.0, max_soc_pct=95.0,
    )


def _run(strategy: str, cap: float) -> EconomicDispatchResult:
    return simulate_battery(
        SURPLUS, _battery(cap), TERMS,
        strategy=strategy, dt_hours=1.0,
        spot_price_eur=SPOT, day_index=DAY, fcr_soc_reserve_pct=20.0,
    )


# (strategy, cap) -> golden dict aus pvtool.battery.simulate_battery
GOLDEN = {
    ("self_consumption", 0.0): dict(grid_purchase_kwh=15.0, grid_feedin_kwh=20.0,
        battery_charge_kwh=0.0, battery_discharge_kwh=0.0, cycles=0.0,
        revenue_eur=1.60, cost_eur=3.75, net_benefit_eur=-2.15),
    ("self_consumption", 10.0): dict(grid_purchase_kwh=0.6, grid_feedin_kwh=0.0,
        battery_charge_kwh=19.0, battery_discharge_kwh=14.4, cycles=1.9,
        revenue_eur=0.0, cost_eur=0.15, net_benefit_eur=-0.15),
    ("spot_optimized", 0.0): dict(grid_purchase_kwh=15.0, grid_feedin_kwh=20.0,
        battery_charge_kwh=0.0, battery_discharge_kwh=0.0, cycles=0.0,
        revenue_eur=0.96, cost_eur=5.78, net_benefit_eur=-4.82),
    ("spot_optimized", 10.0): dict(grid_purchase_kwh=0.6, grid_feedin_kwh=0.0,
        battery_charge_kwh=19.0, battery_discharge_kwh=14.4, cycles=1.9,
        revenue_eur=0.0, cost_eur=0.22, net_benefit_eur=-0.22),
    ("arbitrage", 0.0): dict(grid_purchase_kwh=0.0, grid_feedin_kwh=0.0,
        battery_charge_kwh=0.0, battery_discharge_kwh=0.0, cycles=0.0,
        revenue_eur=0.0, cost_eur=0.0, net_benefit_eur=0.0),
    ("arbitrage", 10.0): dict(grid_purchase_kwh=20.3, grid_feedin_kwh=13.8,
        battery_charge_kwh=19.2, battery_discharge_kwh=13.8, cycles=1.9,
        revenue_eur=3.91, cost_eur=3.49, net_benefit_eur=0.41),
}


@pytest.mark.parametrize(("strategy", "cap"), list(GOLDEN.keys()))
def test_matches_pvtool_golden(strategy: str, cap: float):
    res = _run(strategy, cap)
    expected = GOLDEN[(strategy, cap)]
    for field, want in expected.items():
        got = getattr(res, field)
        assert got == pytest.approx(want, abs=0.051), f"{strategy} cap={cap} {field}: {got} != {want}"


def test_net_benefit_is_revenue_minus_cost():
    res = _run("arbitrage", 10.0)
    assert res.net_benefit_eur == pytest.approx(res.revenue_eur - res.cost_eur, abs=0.01)


def test_unknown_strategy_raises():
    with pytest.raises(ValueError, match="Unbekannte Strategie"):
        simulate_battery(SURPLUS, _battery(10.0), TERMS, strategy="nonsense")


def test_spot_requires_prices():
    with pytest.raises(ValueError, match="spot_price_eur"):
        simulate_battery(SURPLUS, _battery(10.0), TERMS, strategy="spot_optimized")
