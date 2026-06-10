"""
ROI and investment metrics for battery scenarios.

Key outputs
-----------
- Total investment (CAPEX)
- Simple payback period
- NPV over battery lifetime with degradation
- LCOE of stored energy
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import BatteryConfig, MarketConfig


def calculate_roi(
    capacity_kwh: float,
    annual_benefit_year1: float,
    label: str = "",
    battery_cfg: BatteryConfig | None = None,
    market_cfg: MarketConfig | None = None,
) -> dict:
    """
    Calculate investment metrics for a single battery size.

    Parameters
    ----------
    capacity_kwh : float
        Usable battery capacity in kWh.
    annual_benefit_year1 : float
        Annual net revenue/savings in year 1 (EUR), before O&M.
    label : str
        Scenario name for display.
    battery_cfg, market_cfg
        Config objects; defaults used when None.

    Returns
    -------
    dict with keys: capacity_kwh, scenario, total_investment_eur,
        annual_benefit_y1_eur, net_annual_y1_eur, simple_payback_years,
        npv_eur, lcoe_stored_eur_kwh
    """
    cfg = battery_cfg or BatteryConfig()
    mkt = market_cfg or MarketConfig()

    if capacity_kwh == 0:
        return {
            "capacity_kwh": 0, "scenario": label,
            "total_investment_eur": 0, "annual_benefit_y1_eur": 0,
            "net_annual_y1_eur": 0, "simple_payback_years": np.inf,
            "npv_eur": 0, "lcoe_stored_eur_kwh": np.inf,
        }

    inverter_kw = capacity_kwh * cfg.c_rate
    total_invest = (
        capacity_kwh * cfg.cost_eur_per_kwh
        + inverter_kw * cfg.inverter_cost_eur_per_kw
        + cfg.installation_fixed_eur
    )

    net_annual = annual_benefit_year1 - cfg.annual_maintenance_eur
    simple_payback = total_invest / net_annual if net_annual > 0 else np.inf

    # NPV with degradation
    discount_rate = mkt.discount_rate_pct / 100.0
    degradation = cfg.degradation_pct_per_year / 100.0
    npv = -total_invest
    for year in range(1, cfg.lifetime_years + 1):
        degraded_benefit = annual_benefit_year1 * (1 - degradation) ** (year - 1)
        cash_flow = degraded_benefit - cfg.annual_maintenance_eur
        npv += cash_flow / (1 + discount_rate) ** year

    # LCOE of stored energy (cost per kWh discharged over lifetime)
    total_lifetime_cost = total_invest + cfg.annual_maintenance_eur * cfg.lifetime_years
    total_discharged = sum(
        capacity_kwh * 250 * (1 - degradation) ** (y - 1)
        for y in range(1, cfg.lifetime_years + 1)
    )
    lcoe = total_lifetime_cost / total_discharged if total_discharged > 0 else np.inf

    return {
        "capacity_kwh": capacity_kwh,
        "scenario": label,
        "total_investment_eur": round(total_invest, 0),
        "annual_benefit_y1_eur": round(annual_benefit_year1, 0),
        "net_annual_y1_eur": round(net_annual, 0),
        "simple_payback_years": round(simple_payback, 1),
        "npv_eur": round(npv, 0),
        "lcoe_stored_eur_kwh": round(lcoe, 3),
    }


def build_roi_table(
    df_s1: pd.DataFrame,
    df_s2: pd.DataFrame,
    df_s3: pd.DataFrame,
    battery_cfg: BatteryConfig | None = None,
    market_cfg: MarketConfig | None = None,
) -> pd.DataFrame:
    """
    Build a combined ROI table for all three scenarios and all battery sizes.

    Parameters
    ----------
    df_s1, df_s2, df_s3 : pd.DataFrame
        Simulation result DataFrames from run_all_sizes() (without soc column).
        df_s2 must have 'savings_vs_no_batt_eur'.
        df_s3 must have 'total_revenue_eur'.

    Returns
    -------
    pd.DataFrame with columns from calculate_roi for all scenarios × sizes.
    """
    cfg = battery_cfg or BatteryConfig()
    mkt = market_cfg or MarketConfig()

    rows = []
    base_s1 = df_s1[df_s1["capacity_kwh"] == 0].iloc[0]

    for cap in cfg.sizes_kwh:
        if cap == 0:
            continue

        row_s1 = df_s1[df_s1["capacity_kwh"] == cap].iloc[0]
        saved_purchase = base_s1["grid_purchase_kwh"] - row_s1["grid_purchase_kwh"]
        lost_feedin = base_s1["grid_feedin_kwh"] - row_s1["grid_feedin_kwh"]
        s1_benefit = (
            saved_purchase * mkt.grid_buy_price_eur
            - lost_feedin * mkt.feedin_tariff_eur
        )
        rows.append(calculate_roi(cap, s1_benefit, "S1: Self-Consumption", cfg, mkt))

        row_s2 = df_s2[df_s2["capacity_kwh"] == cap].iloc[0]
        rows.append(calculate_roi(cap, row_s2["savings_vs_no_batt_eur"], "S2: Spot Optimized", cfg, mkt))

        row_s3 = df_s3[df_s3["capacity_kwh"] == cap].iloc[0]
        rows.append(calculate_roi(cap, row_s3["total_revenue_eur"], "S3: Arbitrage", cfg, mkt))

    return pd.DataFrame(rows)
