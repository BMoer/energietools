"""
Sensitivity analysis — tornado chart for NPV.

Uses Scenario 1 (self-consumption) as the reference case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BatteryConfig, MarketConfig


def compute_npv(
    capacity_kwh: float,
    annual_benefit: float,
    battery_cfg: BatteryConfig | None = None,
    market_cfg: MarketConfig | None = None,
    battery_cost: float | None = None,
    lifetime: int | None = None,
    discount: float | None = None,
    degradation: float | None = None,
) -> float:
    """
    Compute NPV for a given battery size and annual benefit, with optional
    parameter overrides for sensitivity analysis.

    Parameters
    ----------
    capacity_kwh : float
    annual_benefit : float   — year-1 gross revenue/savings (EUR)
    battery_cfg, market_cfg  — base configs (defaults if None)
    battery_cost, lifetime, discount, degradation
        Override specific parameters for sensitivity sweeps.
    """
    cfg = battery_cfg or BatteryConfig()
    mkt = market_cfg or MarketConfig()

    battery_cost = battery_cost if battery_cost is not None else cfg.cost_eur_per_kwh
    lifetime = lifetime if lifetime is not None else cfg.lifetime_years
    discount = discount if discount is not None else mkt.discount_rate_pct
    degradation = degradation if degradation is not None else cfg.degradation_pct_per_year

    inverter_kw = capacity_kwh * cfg.c_rate
    total_invest = (
        capacity_kwh * battery_cost
        + inverter_kw * cfg.inverter_cost_eur_per_kw
        + cfg.installation_fixed_eur
    )
    dr = discount / 100.0
    deg = degradation / 100.0
    npv = -total_invest
    for y in range(1, int(lifetime) + 1):
        cf = annual_benefit * (1 - deg) ** (y - 1) - cfg.annual_maintenance_eur
        npv += cf / (1 + dr) ** y
    return npv


def sensitivity_sweep(
    capacity_kwh: float,
    base_annual_benefit: float,
    battery_cfg: BatteryConfig | None = None,
    market_cfg: MarketConfig | None = None,
    saved_purchase_kwh: float = 0.0,
    lost_feedin_kwh: float = 0.0,
) -> pd.DataFrame:
    """
    Run a ±20-30% sweep on key parameters and return a DataFrame
    suitable for plotting a tornado chart.

    Parameters
    ----------
    capacity_kwh : float
    base_annual_benefit : float
    battery_cfg, market_cfg
    saved_purchase_kwh, lost_feedin_kwh
        Used to recompute benefit when electricity prices change.
    """
    cfg = battery_cfg or BatteryConfig()
    mkt = market_cfg or MarketConfig()

    base_npv = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt)

    params = {
        "Battery cost (EUR/kWh)": {
            "base": cfg.cost_eur_per_kwh,
            "low": cfg.cost_eur_per_kwh * 0.7,
            "high": cfg.cost_eur_per_kwh * 1.3,
        },
        "Grid buy price (EUR/kWh)": {
            "base": mkt.grid_buy_price_eur,
            "low": mkt.grid_buy_price_eur * 0.8,
            "high": mkt.grid_buy_price_eur * 1.2,
        },
        "Feed-in tariff (EUR/kWh)": {
            "base": mkt.feedin_tariff_eur,
            "low": mkt.feedin_tariff_eur * 0.5,
            "high": mkt.feedin_tariff_eur * 2.0,
        },
        "Battery lifetime (years)": {
            "base": cfg.lifetime_years,
            "low": 10,
            "high": 20,
        },
        "Discount rate (%)": {
            "base": mkt.discount_rate_pct,
            "low": 2.0,
            "high": 6.0,
        },
    }

    rows = []
    for param_name, vals in params.items():
        if param_name == "Battery cost (EUR/kWh)":
            npv_low = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, battery_cost=vals["low"])
            npv_high = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, battery_cost=vals["high"])
        elif param_name == "Grid buy price (EUR/kWh)":
            ab_low = saved_purchase_kwh * vals["low"] - lost_feedin_kwh * mkt.feedin_tariff_eur
            ab_high = saved_purchase_kwh * vals["high"] - lost_feedin_kwh * mkt.feedin_tariff_eur
            npv_low = compute_npv(capacity_kwh, ab_low, cfg, mkt)
            npv_high = compute_npv(capacity_kwh, ab_high, cfg, mkt)
        elif param_name == "Feed-in tariff (EUR/kWh)":
            ab_low = saved_purchase_kwh * mkt.grid_buy_price_eur - lost_feedin_kwh * vals["low"]
            ab_high = saved_purchase_kwh * mkt.grid_buy_price_eur - lost_feedin_kwh * vals["high"]
            npv_low = compute_npv(capacity_kwh, ab_low, cfg, mkt)
            npv_high = compute_npv(capacity_kwh, ab_high, cfg, mkt)
        elif param_name == "Battery lifetime (years)":
            npv_low = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, lifetime=vals["low"])
            npv_high = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, lifetime=vals["high"])
        elif param_name == "Discount rate (%)":
            npv_low = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, discount=vals["low"])
            npv_high = compute_npv(capacity_kwh, base_annual_benefit, cfg, mkt, discount=vals["high"])

        rows.append({
            "param": param_name,
            "base_npv": base_npv,
            "npv_low": npv_low,
            "npv_high": npv_high,
            "range": abs(npv_high - npv_low),
            "low_label": str(vals["low"]),
            "high_label": str(vals["high"]),
        })

    return pd.DataFrame(rows).sort_values("range", ascending=True).reset_index(drop=True)
