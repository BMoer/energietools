"""
Regelenergie (balancing reserve) revenue estimation for battery storage.

Estimates annual revenue from providing FCR/aFRR capacity, based on:
1. **Capacity revenue** — fixed price per MW of reserved capacity (from
   MarketConfig.fcr_revenue_eur_per_kw_year or user override).
2. **Balancing energy revenue** — additional income from actual activations,
   estimated from historical ENTSO-E settlement prices.

This is an *estimation* module (Phase 2).  Full dispatch simulation with
SOC management and 4h-block bidding comes in Phase 4.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RegelenergieConfig


class RegelenergieEstimator:
    """
    Estimate annual Regelenergie revenue for different battery sizes.

    Uses a simple model:
      total_revenue = capacity_revenue + energy_margin_estimate

    Where:
      capacity_revenue = inverter_kw * capacity_price * availability
      energy_margin    = estimated from historical balancing price volatility
    """

    def __init__(self, config: RegelenergieConfig | None = None):
        self.cfg = config or RegelenergieConfig()

    def estimate_capacity_revenue(self, capacity_kwh: float) -> dict:
        """
        Estimate annual FCR + aFRR capacity revenue for a given battery size.

        Returns dict with capacity_kw, fcr_revenue_eur, afrr_revenue_eur, total.
        """
        if capacity_kwh <= 0:
            return {
                "capacity_kwh": 0,
                "capacity_kw": 0,
                "fcr_revenue_eur": 0.0,
                "afrr_revenue_eur": 0.0,
                "total_capacity_revenue_eur": 0.0,
            }

        kw = capacity_kwh * self.cfg.c_rate

        if kw < self.cfg.min_pool_kw:
            return {
                "capacity_kwh": capacity_kwh,
                "capacity_kw": kw,
                "fcr_revenue_eur": 0.0,
                "afrr_revenue_eur": 0.0,
                "total_capacity_revenue_eur": 0.0,
                "note": f"Below minimum pool size ({self.cfg.min_pool_kw} kW)",
            }

        fcr = kw * self.cfg.fcr_capacity_eur_per_kw_year * self.cfg.availability
        afrr = kw * self.cfg.afrr_capacity_eur_per_kw_year * self.cfg.availability

        return {
            "capacity_kwh": capacity_kwh,
            "capacity_kw": kw,
            "fcr_revenue_eur": round(fcr, 2),
            "afrr_revenue_eur": round(afrr, 2),
            "total_capacity_revenue_eur": round(fcr + afrr, 2),
        }

    def estimate_energy_margin(
        self,
        df_balancing: pd.DataFrame,
        capacity_kwh: float,
    ) -> dict:
        """
        Estimate additional energy revenue from balancing activations.

        Uses a simplified model: the battery captures a fraction of the
        spread between high and low balancing prices through symmetric
        FCR response.

        Parameters
        ----------
        df_balancing : pd.DataFrame
            Balancing prices with 'timestamp' and 'price_eur_mwh' columns
            (from fetch_balancing_prices).
        capacity_kwh : float
            Battery capacity.

        Returns
        -------
        dict with energy margin estimates.
        """
        if capacity_kwh <= 0 or df_balancing.empty:
            return {
                "capacity_kwh": capacity_kwh,
                "energy_margin_eur": 0.0,
                "activation_hours": 0,
            }

        kw = capacity_kwh * self.cfg.c_rate
        prices = df_balancing["price_eur_mwh"].values

        # Estimate: battery earns from price deviations around the mean
        mean_price = np.mean(prices)
        # Revenue comes from deviations — charge when price < mean, discharge when > mean
        positive_dev = np.maximum(prices - mean_price, 0)
        negative_dev = np.maximum(mean_price - prices, 0)

        # Battery can capture a fraction of the spread (limited by SOC, efficiency)
        capture_rate = 0.3  # conservative: 30% of theoretical spread
        n_hours = len(prices)
        n_days = (df_balancing["timestamp"].max() - df_balancing["timestamp"].min()).days + 1

        # Scale to annual estimate
        annual_factor = 365.0 / max(n_days, 1)

        # Energy margin per MW from price deviations
        margin_per_mw = (positive_dev.sum() + negative_dev.sum()) * capture_rate / 1000
        margin_annual = margin_per_mw * annual_factor * (kw / 1000) * self.cfg.availability

        # Count hours where price deviates significantly (>20% from mean)
        activation_hours = int(np.sum(np.abs(prices - mean_price) > mean_price * 0.2))

        return {
            "capacity_kwh": capacity_kwh,
            "energy_margin_eur": round(margin_annual, 2),
            "activation_hours": activation_hours,
            "mean_price_eur_mwh": round(mean_price, 2),
            "price_std_eur_mwh": round(float(np.std(prices)), 2),
        }

    def run_all_sizes(
        self,
        df_balancing: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Estimate revenue for all battery sizes in config.

        Parameters
        ----------
        df_balancing : pd.DataFrame, optional
            Historical balancing prices. If provided, energy margin is estimated.

        Returns
        -------
        pd.DataFrame with one row per battery size.
        """
        rows = []
        for cap in self.cfg.sizes_kwh:
            result = self.estimate_capacity_revenue(cap)

            if df_balancing is not None and not df_balancing.empty:
                energy = self.estimate_energy_margin(df_balancing, cap)
                result["energy_margin_eur"] = energy["energy_margin_eur"]
                result["total_revenue_eur"] = round(
                    result["total_capacity_revenue_eur"] + energy["energy_margin_eur"], 2
                )
            else:
                result["energy_margin_eur"] = 0.0
                result["total_revenue_eur"] = result["total_capacity_revenue_eur"]

            # Add economics
            if cap > 0:
                capex = cap * self.cfg.cost_eur_per_kwh
                annual_revenue = result["total_revenue_eur"]
                annual_net = annual_revenue - self.cfg.annual_maintenance_eur

                # Simple payback
                if annual_net > 0:
                    result["payback_years"] = round(capex / annual_net, 1)
                else:
                    result["payback_years"] = float("inf")

                # NPV
                r = self.cfg.discount_rate_pct / 100
                npv_factor = sum(1 / (1 + r) ** t for t in range(1, self.cfg.lifetime_years + 1))
                result["npv_eur"] = round(-capex + annual_net * npv_factor, 2)
                result["capex_eur"] = capex
            else:
                result["payback_years"] = 0.0
                result["npv_eur"] = 0.0
                result["capex_eur"] = 0.0

            rows.append(result)

        return pd.DataFrame(rows)
