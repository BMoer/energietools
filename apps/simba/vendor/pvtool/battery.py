"""
Battery simulation engine.

Three dispatch strategies
-------------------------
self_consumption  — charge from PV surplus, discharge to cover deficit (fixed tariffs)
spot_optimized    — price-aware PV dispatch (charge when cheap, discharge when expensive)
arbitrage         — grid-only buy-low/sell-high with optional FCR reserve
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BatteryConfig, MarketConfig, DataConfig


def simulate_battery(
    df: pd.DataFrame,
    capacity_kwh: float,
    strategy: str = "self_consumption",
    battery_cfg: BatteryConfig | None = None,
    market_cfg: MarketConfig | None = None,
    data_cfg: DataConfig | None = None,
) -> dict:
    """
    Simulate battery operation over a time-series DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        5-minute interval data with columns as defined in DataConfig.
    capacity_kwh : float
        Usable battery capacity in kWh (0 = no-battery baseline).
    strategy : str
        One of 'self_consumption', 'spot_optimized', 'arbitrage'.
    battery_cfg, market_cfg, data_cfg
        Config objects; defaults used when None.

    Returns
    -------
    dict
        Annual metrics plus 'soc_timeseries' numpy array.
    """
    cfg = battery_cfg or BatteryConfig()
    mkt = market_cfg or MarketConfig()
    dcfg = data_cfg or DataConfig()

    max_charge_kw = capacity_kwh * cfg.c_rate
    max_discharge_kw = capacity_kwh * cfg.c_rate

    # ------------------------------------------------------------------ #
    #  Zero-capacity baseline
    # ------------------------------------------------------------------ #
    if capacity_kwh == 0:
        surplus_col = df[dcfg.surplus_col]
        surplus_total = surplus_col.clip(lower=0).sum()
        deficit_total = (-surplus_col.clip(upper=0)).sum()

        if strategy == "arbitrage":
            return {
                "capacity_kwh": 0, "strategy": strategy,
                "grid_purchase_kwh": 0, "grid_feedin_kwh": 0,
                "batt_charged_kwh": 0, "batt_discharged_kwh": 0,
                "cycles": 0, "revenue_eur": 0, "cost_eur": 0,
                "net_benefit_eur": 0,
                "soc_timeseries": np.zeros(len(df)),
            }

        if strategy == "spot_optimized":
            spot = df[dcfg.spot_price_col]
            costs = ((-surplus_col.clip(upper=0)) * (spot + mkt.grid_fees_eur_per_kwh)).sum()
            revenue = (surplus_col.clip(lower=0) * (spot - mkt.feedin_spot_discount)).sum()
        else:
            costs = deficit_total * mkt.grid_buy_price_eur
            revenue = surplus_total * mkt.feedin_tariff_eur

        return {
            "capacity_kwh": 0, "strategy": strategy,
            "grid_purchase_kwh": round(deficit_total, 1),
            "grid_feedin_kwh": round(surplus_total, 1),
            "batt_charged_kwh": 0, "batt_discharged_kwh": 0,
            "cycles": 0,
            "revenue_eur": round(revenue, 2),
            "cost_eur": round(costs, 2),
            "net_benefit_eur": round(revenue - costs, 2),
            "soc_timeseries": np.zeros(len(df)),
        }

    # ------------------------------------------------------------------ #
    #  Derived limits
    # ------------------------------------------------------------------ #
    min_soc = capacity_kwh * cfg.min_soc_pct / 100.0
    max_soc = capacity_kwh * cfg.max_soc_pct / 100.0
    max_charge_interval = max_charge_kw * cfg.dt_hours
    max_discharge_interval = max_discharge_kw * cfg.dt_hours

    n = len(df)
    soc = min_soc
    soc_ts = np.zeros(n)

    total_grid_purchase = 0.0
    total_grid_feedin = 0.0
    total_batt_charged = 0.0
    total_batt_discharged = 0.0
    total_revenue = 0.0
    total_cost = 0.0

    surplus = df[dcfg.surplus_col].values
    spot_price = df[dcfg.spot_price_col].values if dcfg.spot_price_col in df.columns else None

    charge_eff = cfg.charge_efficiency
    discharge_eff = cfg.discharge_efficiency

    # Grid fee for charging from the grid — may be zero under ElWG storage exemption.
    # Falls back to the standard consumption grid fee if not explicitly set.
    charging_grid_fee = (
        mkt.charging_grid_fees_eur_per_kwh
        if mkt.charging_grid_fees_eur_per_kwh is not None
        else mkt.grid_fees_eur_per_kwh
    )

    # ------------------------------------------------------------------ #
    #  Strategy: self_consumption
    # ------------------------------------------------------------------ #
    if strategy == "self_consumption":
        for i in range(n):
            s = surplus[i]
            if s >= 0:
                can_store = min(
                    s * charge_eff,
                    max_soc - soc,
                    max_charge_interval * charge_eff,
                )
                soc += can_store
                total_batt_charged += can_store
                used = can_store / charge_eff if charge_eff > 0 else 0
                grid_export = s - used
                total_grid_feedin += grid_export
                total_revenue += grid_export * mkt.feedin_tariff_eur
            else:
                deficit = -s
                can_discharge = min(
                    soc - min_soc,
                    deficit / discharge_eff,
                    max_discharge_interval,
                )
                delivered = can_discharge * discharge_eff
                soc -= can_discharge
                total_batt_discharged += delivered
                grid_buy = deficit - delivered
                total_grid_purchase += grid_buy
                total_cost += grid_buy * mkt.grid_buy_price_eur
            soc_ts[i] = soc

    # ------------------------------------------------------------------ #
    #  Strategy: spot_optimized
    # ------------------------------------------------------------------ #
    elif strategy == "spot_optimized":
        dates = df[dcfg.timestamp_col].dt.date.values
        unique_dates = np.unique(dates)
        daily_p25 = {}
        daily_p75 = {}
        for d in unique_dates:
            mask = dates == d
            prices_day = spot_price[mask]
            daily_p25[d] = np.percentile(prices_day, 25)
            daily_p75[d] = np.percentile(prices_day, 75)

        for i in range(n):
            s = surplus[i]
            price = spot_price[i]
            buy_price = price + mkt.grid_fees_eur_per_kwh
            sell_price = price - mkt.feedin_spot_discount
            d = dates[i]
            p25 = daily_p25[d]
            p75 = daily_p75[d]

            if s >= 0:
                if price <= p25:
                    can_store = min(s * charge_eff, max_soc - soc, max_charge_interval * charge_eff)
                    soc += can_store
                    total_batt_charged += can_store
                    used = can_store / charge_eff if charge_eff > 0 else 0
                    grid_export = s - used
                    total_grid_feedin += grid_export
                    total_revenue += grid_export * sell_price
                elif price >= p75 and soc > min_soc:
                    total_grid_feedin += s
                    total_revenue += s * sell_price
                    can_discharge = min(soc - min_soc, max_discharge_interval)
                    delivered = can_discharge * discharge_eff
                    soc -= can_discharge
                    total_batt_discharged += delivered
                    total_grid_feedin += delivered
                    total_revenue += delivered * sell_price
                else:
                    can_store = min(s * charge_eff, max_soc - soc, max_charge_interval * charge_eff)
                    soc += can_store
                    total_batt_charged += can_store
                    used = can_store / charge_eff if charge_eff > 0 else 0
                    grid_export = s - used
                    total_grid_feedin += grid_export
                    total_revenue += grid_export * sell_price
            else:
                deficit = -s
                if price >= p75 and soc > min_soc:
                    can_discharge = min(soc - min_soc, deficit / discharge_eff, max_discharge_interval)
                    delivered = can_discharge * discharge_eff
                    soc -= can_discharge
                    total_batt_discharged += delivered
                    grid_buy = deficit - delivered
                    total_grid_purchase += grid_buy
                    total_cost += grid_buy * buy_price
                elif price <= p25 and soc < max_soc:
                    total_grid_purchase += deficit
                    total_cost += deficit * buy_price
                    can_store = min(max_soc - soc, max_charge_interval * charge_eff)
                    grid_charge = can_store / charge_eff if charge_eff > 0 else 0
                    soc += can_store
                    total_batt_charged += can_store
                    total_grid_purchase += grid_charge
                    total_cost += grid_charge * (price + charging_grid_fee)
                else:
                    can_discharge = min(soc - min_soc, deficit / discharge_eff, max_discharge_interval)
                    delivered = can_discharge * discharge_eff
                    soc -= can_discharge
                    total_batt_discharged += delivered
                    grid_buy = deficit - delivered
                    total_grid_purchase += grid_buy
                    total_cost += grid_buy * buy_price
            soc_ts[i] = soc

    # ------------------------------------------------------------------ #
    #  Strategy: arbitrage
    # ------------------------------------------------------------------ #
    elif strategy == "arbitrage":
        dates = df[dcfg.timestamp_col].dt.date.values
        unique_dates = np.unique(dates)
        daily_p30 = {}
        daily_p70 = {}
        for d in unique_dates:
            mask = dates == d
            prices_day = spot_price[mask]
            daily_p30[d] = np.percentile(prices_day, 30)
            daily_p70[d] = np.percentile(prices_day, 70)

        fcr_reserve = capacity_kwh * mkt.fcr_soc_reserve_pct / 100.0
        arb_min_soc = min_soc + fcr_reserve
        arb_max_soc = max_soc - fcr_reserve
        soc = arb_min_soc

        for i in range(n):
            price = spot_price[i]
            buy_price = price + mkt.grid_fees_eur_per_kwh
            sell_price = price - mkt.feedin_spot_discount
            d = dates[i]
            p30 = daily_p30[d]
            p70 = daily_p70[d]

            if price <= p30 and soc < arb_max_soc:
                can_store = min(arb_max_soc - soc, max_charge_interval * charge_eff)
                grid_buy = can_store / charge_eff if charge_eff > 0 else 0
                soc += can_store
                total_batt_charged += can_store
                total_grid_purchase += grid_buy
                total_cost += grid_buy * (price + charging_grid_fee)
            elif price >= p70 and soc > arb_min_soc:
                can_discharge = min(soc - arb_min_soc, max_discharge_interval)
                delivered = can_discharge * discharge_eff
                soc -= can_discharge
                total_batt_discharged += delivered
                total_grid_feedin += delivered
                total_revenue += delivered * sell_price
            soc_ts[i] = soc

    else:
        raise ValueError(f"Unknown strategy: {strategy!r}. Use 'self_consumption', 'spot_optimized', or 'arbitrage'.")

    cycles = total_batt_charged / capacity_kwh if capacity_kwh > 0 else 0

    return {
        "capacity_kwh": capacity_kwh,
        "strategy": strategy,
        "grid_purchase_kwh": round(total_grid_purchase, 1),
        "grid_feedin_kwh": round(total_grid_feedin, 1),
        "batt_charged_kwh": round(total_batt_charged, 1),
        "batt_discharged_kwh": round(total_batt_discharged, 1),
        "cycles": round(cycles, 1),
        "revenue_eur": round(total_revenue, 2),
        "cost_eur": round(total_cost, 2),
        "net_benefit_eur": round(total_revenue - total_cost, 2),
        "soc_timeseries": soc_ts,
    }
