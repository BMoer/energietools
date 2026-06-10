"""Simulation service — re-wired auf energietools.

Die Batterie-Strategien (self_consumption / spot_optimized / arbitrage),
Peak-Shaving und die ROI-Kennzahlen laufen über die MIT-Library ``energietools``
(capabilities.scenarios + finance). Die volle Wärmepumpen-Summary (2-Pass-
Thermalspeicher) bleibt übergangsweise hybrid bei ``pvtool`` (lazy importiert),
bis sie nach energietools portiert ist. UI-Schemas + API-Vertrag bleiben gleich;
die Einheiten-Konvertierung (EUR ↔ ct) passiert nur hier im Service-Layer —
energietools' MarketTerms sprechen EUR/kWh, daher reicht 1:1-Durchreichen.
"""

from __future__ import annotations

import pandas as pd

from app.models.schemas import (
    BatteryParams,
    HeatPumpParams,
    HeatPumpSummary,
    MarketParams,
    PeakShavingParams,
    ROIResult,
    ScenarioResult,
)
from energietools.capabilities.finance.capability import FinanceCapability
from energietools.capabilities.scenarios.dispatch import MarketTerms, simulate_battery
from energietools.capabilities.scenarios.peak_shaving import run_peak_shaving
from energietools.components.battery import Battery

_BATTERY_STRATEGIES = ("self_consumption", "spot_optimized", "arbitrage")
_FINANCE = FinanceCapability()


def _battery(bp: BatteryParams, size: float) -> Battery:
    return Battery.new(
        float(size),
        c_rate=bp.c_rate,
        charge_efficiency=bp.charge_efficiency,
        discharge_efficiency=bp.discharge_efficiency,
        min_soc_pct=bp.min_soc_pct,
        max_soc_pct=bp.max_soc_pct,
    )


def _terms(mp: MarketParams) -> MarketTerms:
    return MarketTerms(
        grid_buy_price_eur=mp.grid_buy_price_eur,
        feedin_tariff_eur=mp.feedin_tariff_eur,
        grid_fees_eur_per_kwh=mp.grid_fees_eur_per_kwh,
        feedin_spot_discount=mp.feedin_spot_discount,
        charging_grid_fee_eur_per_kwh=mp.charging_grid_fees_eur_per_kwh,
    )


def _baseline(rows: list) -> float:
    return next((r.net_benefit_eur for size, r in rows if size == 0), 0.0)


def _run_battery_strategy(
    name: str,
    surplus: list[float],
    prices: list[float] | None,
    day_index: list,
    dt_hours: float,
    bp: BatteryParams,
    mp: MarketParams,
    terms: MarketTerms,
) -> list[ScenarioResult]:
    rows = [
        (
            size,
            simulate_battery(
                surplus, _battery(bp, size), terms,
                strategy=name, dt_hours=dt_hours,
                spot_price_eur=prices, day_index=day_index,
                # fcr_soc_reserve_pct ist nicht im UI-Schema → pvtool-Default 20 %
                fcr_soc_reserve_pct=getattr(mp, "fcr_soc_reserve_pct", 20.0),
            ),
        )
        for size in bp.sizes_kwh
    ]
    baseline = _baseline(rows)
    return [
        ScenarioResult(
            capacity_kwh=size,
            strategy=res.strategy,
            grid_purchase_kwh=res.grid_purchase_kwh,
            grid_feedin_kwh=res.grid_feedin_kwh,
            batt_charged_kwh=res.battery_charge_kwh,
            batt_discharged_kwh=res.battery_discharge_kwh,
            cycles=res.cycles,
            revenue_eur=res.revenue_eur,
            cost_eur=res.cost_eur,
            net_benefit_eur=res.net_benefit_eur,
            annual_savings_eur=round(res.net_benefit_eur - baseline, 2),
        )
        for size, res in rows
    ]


def _run_peak_shaving(
    df: pd.DataFrame,
    bp: BatteryParams,
    mp: MarketParams,
    ps_params: PeakShavingParams | None,
) -> list[ScenarioResult]:
    ps = ps_params or PeakShavingParams()
    net_demand = (df["consumption_kWh"] - df["production_kWh"]).tolist()
    month_index = df["timestamp"].dt.to_period("M").astype(str).tolist()
    rows = [
        (
            size,
            run_peak_shaving(
                net_demand, month_index, _battery(bp, size),
                peak_threshold_kw=ps.peak_threshold_kw,
                demand_charge_eur_per_kw_year=ps.demand_charge_eur_per_kw_year,
                grid_buy_price_eur=mp.grid_buy_price_eur,
                dt_hours=bp.dt_hours,
                combine_self_consumption=ps.combine_self_consumption,
                baseline_peak_kw=getattr(ps, "baseline_peak_kw", None),
            ),
        )
        for size in bp.sizes_kwh
    ]
    baseline = _baseline(rows)
    return [
        ScenarioResult(
            capacity_kwh=size,
            strategy="peak_shaving_greedy",
            grid_purchase_kwh=res.grid_purchase_kwh,
            grid_feedin_kwh=0.0,
            batt_charged_kwh=res.battery_charge_kwh,
            batt_discharged_kwh=res.battery_discharge_kwh,
            cycles=res.cycles,
            revenue_eur=0.0,
            cost_eur=0.0,
            net_benefit_eur=res.net_benefit_eur,
            annual_savings_eur=round(res.net_benefit_eur - baseline, 2),
            peak_reduction_kw=res.peak_reduction_kw,
        )
        for size, res in rows
    ]


def _run_heatpump(
    df: pd.DataFrame,
    bp: BatteryParams,
    mp: MarketParams,
    heatpump_params: HeatPumpParams | None,
) -> tuple[list[ScenarioResult], HeatPumpSummary | None]:
    """Hybrid: volle WP-Summary (2-Pass-Thermalspeicher) noch über pvtool (lazy).

    Wird nur importiert, wenn das heatpump-Szenario angefragt ist — so bootet die
    App ohne pvtool, solange nur die auf energietools re-wirten Strategien laufen.
    """
    from pvtool.config import BatteryConfig, HeatPumpConfig, MarketConfig
    from pvtool.scenarios.heatpump import HeatPumpScenario

    hp_cfg = HeatPumpConfig(**(heatpump_params or HeatPumpParams()).model_dump())
    bat_cfg = BatteryConfig(**bp.model_dump())
    mkt_cfg = MarketConfig(**mp.model_dump())
    scenario = HeatPumpScenario(hp_cfg=hp_cfg, battery_cfg=bat_cfg, market_cfg=mkt_cfg)

    runs, first, baseline = [], None, None
    for size in bat_cfg.sizes_kwh:
        r = scenario.run(
            df, inlet_temp_c=hp_cfg.inlet_temp_c,
            thermal_storage_kwh=hp_cfg.thermal_storage_kwh, battery_kwh=size,
        )
        first = first or r
        baseline = r["total_annual_savings_eur"] if baseline is None else baseline
        runs.append((size, r))

    results = [
        ScenarioResult(
            capacity_kwh=size, strategy="heatpump",
            grid_purchase_kwh=r.get("grid_purchase_kwh", 0), grid_feedin_kwh=r.get("grid_feedin_kwh", 0),
            batt_charged_kwh=0, batt_discharged_kwh=0, cycles=r.get("battery_cycles", 0),
            revenue_eur=r.get("gas_cost_baseline_eur", 0), cost_eur=r.get("hp_electricity_cost_eur", 0),
            net_benefit_eur=r.get("total_annual_savings_eur", 0),
            annual_savings_eur=r["total_annual_savings_eur"] - baseline,
        )
        for size, r in runs
    ]
    hp_summary = HeatPumpSummary(
        inlet_temp_c=first["inlet_temp_c"], thermal_storage_kwh=first["thermal_storage_kwh"],
        average_cop=first["average_cop"], gas_cost_baseline_eur=first["gas_cost_baseline_eur"],
        hp_annual_electricity_kwh=first["hp_annual_electricity_kwh"],
        residual_gas_kwh=first.get("residual_gas_kwh", 0), residual_gas_cost_eur=first.get("residual_gas_cost_eur", 0),
        hp_covered_thermal_kwh=first.get("hp_covered_thermal_kwh", 0),
        pv_to_hp_kwh=first.get("pv_to_hp_kwh", 0), grid_to_hp_kwh=first.get("grid_to_hp_kwh", 0),
        self_consumption_rate_before=first.get("self_consumption_rate_before", 0),
        self_consumption_rate_after=first.get("self_consumption_rate_after", 0),
    ) if first else None
    return results, hp_summary


def run_scenarios(
    df: pd.DataFrame,
    scenarios: list[str],
    battery_params: BatteryParams,
    market_params: MarketParams,
    peak_shaving_params: PeakShavingParams | None = None,
    heatpump_params: HeatPumpParams | None = None,
) -> tuple[dict[str, list[ScenarioResult]], HeatPumpSummary | None]:
    """Führt die angefragten Szenarien aus (Ergebnisse je Szenarioname)."""
    surplus = df["surplus_kWh"].tolist()
    prices = df["price_eur_kwh"].tolist() if "price_eur_kwh" in df.columns else None
    day_index = df["timestamp"].dt.date.tolist()
    terms = _terms(market_params)

    results: dict[str, list[ScenarioResult]] = {}
    hp_summary: HeatPumpSummary | None = None

    for name in scenarios:
        if name == "heatpump":
            results[name], hp_summary = _run_heatpump(df, battery_params, market_params, heatpump_params)
        elif name in _BATTERY_STRATEGIES:
            results[name] = _run_battery_strategy(
                name, surplus, prices, day_index, battery_params.dt_hours,
                battery_params, market_params, terms,
            )
        elif name == "peak_shaving":
            results[name] = _run_peak_shaving(df, battery_params, market_params, peak_shaving_params)

    return results, hp_summary


def _heatpump_roi(
    results: list[ScenarioResult], bp: BatteryParams, mp: MarketParams,
    heatpump_params: HeatPumpParams | None,
) -> list[ROIResult]:
    from pvtool.config import HeatPumpConfig

    hp_cfg = HeatPumpConfig(**(heatpump_params or HeatPumpParams()).model_dump())
    discount = mp.discount_rate_pct / 100.0
    out = []
    for r in results:
        capex = hp_cfg.hp_capex_eur + r.capacity_kwh * bp.cost_eur_per_kwh
        benefit = r.net_benefit_eur
        payback = capex / benefit if benefit > 0 else None
        npv = -capex + sum(benefit / (1 + discount) ** y for y in range(1, hp_cfg.hp_lifetime_years + 1))
        out.append(ROIResult(
            capacity_kwh=r.capacity_kwh, label=f"heatpump_{r.capacity_kwh:g}kWh",
            capex_eur=capex, annual_savings_eur=benefit,
            payback_years=round(payback, 1) if payback else None, npv_eur=round(npv, 2),
        ))
    return out


def compute_roi(
    scenario_results: dict[str, list[ScenarioResult]],
    battery_params: BatteryParams,
    market_params: MarketParams,
    heatpump_params: HeatPumpParams | None = None,
) -> list[ROIResult]:
    """ROI je Szenario + Speichergröße über energietools' FinanceCapability."""
    bp, mp = battery_params, market_params
    out: list[ROIResult] = []
    for name, results in scenario_results.items():
        if name == "heatpump":
            out.extend(_heatpump_roi(results, bp, mp, heatpump_params))
            continue
        for r in results:
            if r.capacity_kwh == 0:
                continue
            invest = r.capacity_kwh * bp.cost_eur_per_kwh
            fin = _FINANCE.run(
                investition_eur=invest, jaehrlicher_ertrag_eur=r.annual_savings_eur,
                nutzungsdauer_jahre=bp.lifetime_years, diskontrate=mp.discount_rate_pct / 100.0,
                degradation_pct_jahr=bp.degradation_pct_per_year,
            )
            d = fin.data if fin.ok else {}
            payback = d.get("simple_payback_years")
            if payback == float("inf"):
                payback = None
            out.append(ROIResult(
                capacity_kwh=r.capacity_kwh, label=f"{name}_{r.capacity_kwh:g}kWh",
                capex_eur=invest, annual_savings_eur=r.annual_savings_eur,
                payback_years=round(payback, 1) if payback is not None else None,
                npv_eur=d.get("npv_eur", 0.0), lcoe_eur_per_kwh=d.get("lcoe_eur_kwh"),
            ))
    return out
