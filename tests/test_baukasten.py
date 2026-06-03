# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tests für den Simulationsbaukasten: Komponenten, System-Bilanz, Optimierer.

Echtes Verhalten (PV, Batterie, System-Bilanz, COP, Zielfunktions-Bewertung) wird
geprüft; Platzhalter (E-Auto/Gaskessel/HP-Dispatch, Optimierer-Löser) müssen
erkennbar ``NotImplementedError`` werfen.
"""

from __future__ import annotations

import pytest

from energietools.components import (
    Battery,
    ElectricVehicle,
    GasBoiler,
    HeatPump,
    PVSystem,
    StepContext,
)
from energietools.optimizer import (
    OBJECTIVE_AUTARKY,
    OBJECTIVE_ECONOMIC,
    OBJECTIVE_SELF_CONSUMPTION,
    EconomicPrices,
    evaluate,
    optimize,
)
from energietools.system import EnergySystem

# --- Battery (real dispatch) -------------------------------------------------

def test_battery_charges_from_surplus_with_efficiency() -> None:
    bat = Battery.new(10.0, initial_soc_kwh=0.5)  # min_soc = 0.5 kWh
    step, new_bat = bat.step(surplus_kwh=2.0, ctx=StepContext(dt_hours=1.0))
    # c_rate 0.5 → max 5 kWh/h; charge_eff 0.95 → stores 2*0.95 = 1.9 kWh
    assert round(step.consumed_kwh, 4) == 2.0  # drew the full surplus (1.9/0.95)
    assert round(new_bat.soc_kwh, 4) == round(0.5 + 1.9, 4)
    assert step.produced_kwh == 0.0


def test_battery_discharges_to_deficit_with_efficiency() -> None:
    bat = Battery.new(10.0, initial_soc_kwh=5.0)
    step, new_bat = bat.step(surplus_kwh=-1.0, ctx=StepContext(dt_hours=1.0))
    # deficit 1.0 → pull 1/0.95 from SOC, deliver 1.0 to bus
    assert round(step.produced_kwh, 4) == 1.0
    assert round(new_bat.soc_kwh, 4) == round(5.0 - 1.0 / 0.95, 4)


def test_battery_respects_soc_bounds() -> None:
    full = Battery.new(5.0, initial_soc_kwh=5.0 * 0.95)  # at max_soc
    step, _ = full.step(surplus_kwh=3.0, ctx=StepContext(dt_hours=1.0))
    assert step.consumed_kwh == 0.0  # cannot charge past max_soc


def test_battery_immutability() -> None:
    bat = Battery.new(10.0, initial_soc_kwh=5.0)
    _, new_bat = bat.step(surplus_kwh=-1.0, ctx=StepContext(dt_hours=1.0))
    assert bat.soc_kwh == 5.0  # original unchanged
    assert new_bat is not bat


# --- PV (real source) --------------------------------------------------------

def test_pv_scales_yield_with_interval() -> None:
    pv = PVSystem(kwp=5.0, specific_yield_kwh_per_kwp=1000.0)  # 5000 kWh/yr
    full_year, _ = pv.step(0.0, StepContext(dt_hours=8760.0))
    assert round(full_year.produced_kwh, 2) == 5000.0
    half_year, _ = pv.step(0.0, StepContext(dt_hours=4380.0))
    assert round(half_year.produced_kwh, 2) == 2500.0


# --- System balance (real) ---------------------------------------------------

def test_system_pv_battery_balance_and_kpis() -> None:
    # One annual point: 4000 kWh consumption, 5000 kWh PV, 10 kWh battery.
    pv = PVSystem(kwp=5.0, specific_yield_kwh_per_kwp=1000.0)
    bat = Battery.new(10.0)
    system = EnergySystem([pv, bat])
    res = system.run([4000.0], [StepContext(dt_hours=8760.0)])
    assert res.total_production_kwh == 5000.0
    assert res.total_consumption_kwh == 4000.0
    # Energy conservation: production + import = consumption + charge + feed_in (+losses)
    assert res.total_grid_feed_in_kwh > 0  # 5000 produced > 4000 used → surplus exported
    assert 0.0 <= res.self_consumption_rate <= 1.0
    assert 0.0 <= res.self_sufficiency_rate <= 1.0


def test_system_no_pv_imports_everything() -> None:
    system = EnergySystem([Battery.new(10.0)])
    res = system.run([100.0], [StepContext(dt_hours=1.0)])
    assert res.total_grid_import_kwh == 100.0  # battery empty, no PV
    assert res.self_sufficiency_rate == 0.0


# --- HeatPump COP (real) -----------------------------------------------------

def test_heatpump_cop_is_physical_and_clamped() -> None:
    hp = HeatPump(inlet_temp_c=55.0)
    cold = hp.cop(outdoor_temp_c=-10.0)
    warm = hp.cop(outdoor_temp_c=10.0)
    assert warm > cold  # warmer outside → higher COP
    assert hp.cop_min <= cold <= hp.cop_max
    assert hp.cop_min <= warm <= hp.cop_max


# --- Optimizer objectives (evaluate works, solver is placeholder) -----------

def test_optimizer_self_consumption_objective() -> None:
    system = EnergySystem([PVSystem(kwp=5.0), Battery.new(10.0)])
    ov = evaluate(system, OBJECTIVE_SELF_CONSUMPTION, [4000.0], [StepContext(dt_hours=8760.0)])
    assert ov.maximize is True
    assert 0.0 <= ov.value <= 1.0


def test_optimizer_economic_objective_uses_sourced_grid_fee() -> None:
    system = EnergySystem([PVSystem(kwp=5.0), Battery.new(10.0)])
    prices = EconomicPrices(energy_price_eur_kwh=0.20, feed_in_tariff_eur_kwh=0.08)
    ov = evaluate(
        system, OBJECTIVE_ECONOMIC, [4000.0], [StepContext(dt_hours=8760.0)], prices=prices
    )
    assert ov.maximize is False
    assert ov.detail["grid_fee_eur_kwh"] > 0  # sourced from grid_fees, not zero/magic


def test_optimizer_autarky_objective() -> None:
    system = EnergySystem([PVSystem(kwp=5.0), Battery.new(10.0)])
    ov = evaluate(system, OBJECTIVE_AUTARKY, [4000.0], [StepContext(dt_hours=8760.0)])
    assert ov.objective == OBJECTIVE_AUTARKY
    assert ov.maximize is True


def test_optimizer_solver_is_placeholder() -> None:
    with pytest.raises(NotImplementedError, match="PLATZHALTER"):
        optimize()


# --- Placeholders are recognizable ------------------------------------------

def test_ev_step_is_placeholder() -> None:
    with pytest.raises(NotImplementedError, match="PLATZHALTER"):
        ElectricVehicle(battery_kwh=60.0).step(0.0, StepContext())


def test_gas_boiler_step_is_placeholder() -> None:
    with pytest.raises(NotImplementedError, match="PLATZHALTER"):
        GasBoiler().step(0.0, StepContext())


def test_heatpump_dispatch_is_placeholder_but_cop_works() -> None:
    hp = HeatPump()
    assert hp.cop(0.0) > 0  # real
    with pytest.raises(NotImplementedError, match="PLATZHALTER"):
        hp.step(0.0, StepContext())  # dispatch placeholder
