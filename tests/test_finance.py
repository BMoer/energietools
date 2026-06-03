# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für die finance-Capability (ROI/NPV/LCOE, Standard-Finanzformeln)."""

from __future__ import annotations

from math import inf

from energietools.capabilities.finance import capex, lcoe, npv, simple_payback_years
from energietools.capabilities.finance.capability import FinanceCapability


def test_capex_composition() -> None:
    # 10 kWh @ 300 + 5 kW @ 100 + 500 fix = 3000 + 500 + 500
    assert capex(
        capacity_kwh=10, cost_eur_per_kwh=300, power_kw=5, cost_eur_per_kw=100, fixed_eur=500
    ) == 4000.0


def test_simple_payback_basic_and_never() -> None:
    assert simple_payback_years(6000, 600) == 10.0
    assert simple_payback_years(6000, 0) == inf
    assert simple_payback_years(6000, -50) == inf


def test_npv_zero_discount_no_degradation() -> None:
    # No discount, no degradation: NPV = -I + L*(benefit - cost)
    val = npv(
        total_investment_eur=1000,
        annual_benefit_year1_eur=200,
        lifetime_years=10,
        discount_rate=0.0,
        annual_cost_eur=0.0,
        degradation_rate=0.0,
    )
    assert val == 1000.0  # -1000 + 10*200


def test_npv_discount_reduces_value() -> None:
    with_discount = npv(
        total_investment_eur=1000, annual_benefit_year1_eur=200,
        lifetime_years=10, discount_rate=0.05,
    )
    without = npv(
        total_investment_eur=1000, annual_benefit_year1_eur=200,
        lifetime_years=10, discount_rate=0.0,
    )
    assert with_discount < without


def test_lcoe_discounts_both_flows() -> None:
    # With zero O&M and zero discount/degradation: LCOE = I / (L * energy)
    val = lcoe(
        total_investment_eur=3000, annual_cost_eur=0.0, lifetime_years=10,
        annual_energy_kwh_year1=1000, discount_rate=0.0, degradation_rate=0.0,
    )
    assert round(val, 4) == round(3000 / (10 * 1000), 4)
    # No energy -> inf, not crash.
    assert lcoe(
        total_investment_eur=3000, annual_cost_eur=0, lifetime_years=10,
        annual_energy_kwh_year1=0,
    ) == inf


def test_capability_full_result_with_lcoe() -> None:
    res = FinanceCapability().run(
        investition_eur=6000,
        jaehrlicher_ertrag_eur=700,
        nutzungsdauer_jahre=15,
        diskontrate=0.04,
        betriebskosten_eur_jahr=100,
        degradation_pct_jahr=2.0,
        jahresenergie_kwh=2500,
    )
    assert res.ok
    d = res.data
    assert d["total_investment_eur"] == 6000.0
    assert d["annual_net_benefit_eur"] == 600.0  # 700 - 100
    assert d["lcoe_eur_kwh"] is not None
    assert d["annahmen"]["diskontrate"] == 0.04


def test_capability_omits_lcoe_without_energy() -> None:
    res = FinanceCapability().run(
        investition_eur=6000, jaehrlicher_ertrag_eur=700,
        nutzungsdauer_jahre=15, diskontrate=0.04,
    )
    assert res.ok
    assert res.data["lcoe_eur_kwh"] is None  # not faked


def test_capability_requires_inputs_no_magic_defaults() -> None:
    res = FinanceCapability().run(investition_eur=6000, jaehrlicher_ertrag_eur=700)
    assert not res.ok
    assert "nutzungsdauer_jahre" in (res.error or "")
