"""
FCR (Frequency Containment Reserve) dispatch simulation for standalone battery storage.

Simulates a grid-connected battery providing symmetric FCR in 4-hour product blocks.
Uses a synthetic activation model (configurable) since real sub-second frequency data
is not freely available.

Revenue sources:
  1. **Capacity payment** — EUR/MW per 4h block (from regelleistung.net auctions)
  2. **Energy settlement** — EUR/MWh for actual activations (from ENTSO-E prices)

SOC management is critical: the battery must stay near 50% to allow symmetric
±response. End-of-block rebalancing trades energy to re-center SOC.

Austrian/German FCR cooperation: joint tendering DE/AT/NL/BE/FR/CH, weekly auctions.
Minimum bid size: 1 MW (pooling allowed for smaller units).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RegelenergieConfig

# 4-hour block duration (FCR/aFRR standard product)
BLOCK_HOURS = 4


class FCRSimulator:
    """
    Time-step FCR dispatch simulation for standalone battery storage.

    Parameters
    ----------
    config : RegelenergieConfig, optional
        All simulation parameters. Uses defaults if not provided.
    """

    def __init__(self, config: RegelenergieConfig | None = None):
        self.cfg = config or RegelenergieConfig()

    def run(
        self,
        df_balancing: pd.DataFrame,
        capacity_kwh: float,
        seed: int = 42,
    ) -> dict:
        """
        Run FCR simulation for a single battery size.

        Parameters
        ----------
        df_balancing : pd.DataFrame
            Hourly balancing prices with 'timestamp' and 'price_eur_mwh' columns.
        capacity_kwh : float
            Battery capacity in kWh.
        seed : int
            Random seed for reproducible activation signals.

        Returns
        -------
        dict with simulation results including 'soc_timeseries'.
        """
        cfg = self.cfg

        # Zero capacity baseline
        if capacity_kwh <= 0:
            n = len(df_balancing)
            return {
                "capacity_kwh": 0,
                "contracted_kw": 0.0,
                "contracted_mw": 0.0,
                "total_blocks": n // BLOCK_HOURS,
                "available_blocks": 0,
                "capacity_revenue_eur": 0.0,
                "energy_revenue_eur": 0.0,
                "energy_cost_eur": 0.0,
                "rebalance_cost_eur": 0.0,
                "total_revenue_eur": 0.0,
                "total_charged_kwh": 0.0,
                "total_discharged_kwh": 0.0,
                "cycles": 0.0,
                "soc_timeseries": np.zeros(n),
            }

        # Check minimum pool size
        contracted_kw = capacity_kwh * cfg.c_rate
        contracted_mw = contracted_kw / 1000.0
        if contracted_kw < cfg.min_pool_kw:
            n = len(df_balancing)
            return {
                "capacity_kwh": capacity_kwh,
                "contracted_kw": contracted_kw,
                "contracted_mw": contracted_mw,
                "total_blocks": n // BLOCK_HOURS,
                "available_blocks": 0,
                "capacity_revenue_eur": 0.0,
                "energy_revenue_eur": 0.0,
                "energy_cost_eur": 0.0,
                "rebalance_cost_eur": 0.0,
                "total_revenue_eur": 0.0,
                "total_charged_kwh": 0.0,
                "total_discharged_kwh": 0.0,
                "cycles": 0.0,
                "note": f"Below minimum pool size ({cfg.min_pool_kw} kW)",
                "soc_timeseries": np.full(n, capacity_kwh * cfg.fcr_target_soc_pct / 100),
            }

        return self._simulate(df_balancing, capacity_kwh, seed)

    def _simulate(
        self,
        df_balancing: pd.DataFrame,
        capacity_kwh: float,
        seed: int,
    ) -> dict:
        """Core FCR dispatch loop."""
        cfg = self.cfg
        rng = np.random.default_rng(seed)

        contracted_kw = capacity_kwh * cfg.c_rate
        contracted_mw = contracted_kw / 1000.0
        min_soc = capacity_kwh * cfg.min_soc_pct / 100.0
        max_soc = capacity_kwh * cfg.max_soc_pct / 100.0
        target_soc = capacity_kwh * cfg.fcr_target_soc_pct / 100.0
        deadband = capacity_kwh * cfg.fcr_soc_deadband_pct / 100.0

        prices_eur_kwh = df_balancing["price_eur_mwh"].values / 1000.0
        n_hours = len(prices_eur_kwh)
        n_blocks = n_hours // BLOCK_HOURS

        # State
        soc = target_soc
        soc_ts = np.zeros(n_hours)
        capacity_revenue = 0.0
        energy_revenue = 0.0
        energy_cost = 0.0
        rebalance_cost = 0.0
        total_charged = 0.0
        total_discharged = 0.0
        available_blocks = 0

        for block_idx in range(n_blocks):
            h_start = block_idx * BLOCK_HOURS
            h_end = h_start + BLOCK_HOURS

            # Availability check
            if rng.random() > cfg.availability:
                # Unavailable — SOC stays constant
                soc_ts[h_start:h_end] = soc
                continue

            available_blocks += 1
            capacity_revenue += contracted_mw * cfg.fcr_block_price_eur_per_mw

            # Hourly dispatch within block
            for h in range(h_start, h_end):
                # Synthetic FCR activation signal: symmetric around 0
                # FCR responds to frequency deviation (centered at 50 Hz).
                # Magnitude ~ |N(0, std)|, direction is random ±1.
                # fcr_mean_activation_fraction controls the typical magnitude.
                magnitude = abs(rng.normal(0, cfg.fcr_mean_activation_fraction))
                magnitude = min(magnitude, 1.0)
                sign = 1 if rng.random() < 0.5 else -1
                activation_frac = magnitude * sign

                activation_kw = contracted_kw * activation_frac
                price = prices_eur_kwh[h]

                if activation_kw > 0:
                    # Discharge (inject to grid) — earn energy revenue
                    max_discharge_kwh = (soc - min_soc) * cfg.discharge_efficiency
                    energy_kwh = min(activation_kw * 1.0, max_discharge_kwh)
                    energy_kwh = max(energy_kwh, 0.0)
                    soc -= energy_kwh / cfg.discharge_efficiency
                    energy_revenue += energy_kwh * abs(price)
                    total_discharged += energy_kwh
                else:
                    # Charge (absorb from grid) — FCR earns from both directions
                    # at the absolute settlement price
                    charge_kw = abs(activation_kw)
                    max_charge_kwh = (max_soc - soc) / cfg.charge_efficiency
                    energy_kwh = min(charge_kw * 1.0, max_charge_kwh)
                    energy_kwh = max(energy_kwh, 0.0)
                    soc += energy_kwh * cfg.charge_efficiency
                    energy_cost += energy_kwh * abs(price)
                    total_charged += energy_kwh

                soc_ts[h] = soc

            # End-of-block SOC rebalancing (trade energy at market to re-center)
            if abs(soc - target_soc) > deadband:
                delta = abs(soc - target_soc)
                rebalance_cost += delta * cfg.fcr_rebalance_cost_eur_per_kwh
                soc = target_soc

        # Fill remaining hours (partial block at end)
        remainder = n_hours - n_blocks * BLOCK_HOURS
        if remainder > 0:
            soc_ts[n_blocks * BLOCK_HOURS:] = soc

        # Economics
        net_energy = energy_revenue - energy_cost
        total_revenue = capacity_revenue + net_energy - rebalance_cost
        cycles = (total_charged + total_discharged) / (2 * capacity_kwh) if capacity_kwh > 0 else 0.0

        return {
            "capacity_kwh": capacity_kwh,
            "contracted_kw": contracted_kw,
            "contracted_mw": contracted_mw,
            "total_blocks": n_blocks,
            "available_blocks": available_blocks,
            "capacity_revenue_eur": round(capacity_revenue, 2),
            "energy_revenue_eur": round(energy_revenue, 2),
            "energy_cost_eur": round(energy_cost, 2),
            "rebalance_cost_eur": round(rebalance_cost, 2),
            "total_revenue_eur": round(total_revenue, 2),
            "total_charged_kwh": round(total_charged, 2),
            "total_discharged_kwh": round(total_discharged, 2),
            "cycles": round(cycles, 1),
            "soc_timeseries": soc_ts,
        }

    def run_all_sizes(
        self,
        df_balancing: pd.DataFrame,
        seed: int = 42,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Run FCR simulation for all battery sizes in config.

        Returns
        -------
        (pd.DataFrame, dict)
            DataFrame with one row per size (metrics + economics).
            Dict mapping capacity_kwh → soc_timeseries (non-zero sizes only).
        """
        cfg = self.cfg
        rows = []
        soc_data = {}

        for cap in cfg.sizes_kwh:
            result = self.run(df_balancing, cap, seed=seed)
            soc_ts = result.pop("soc_timeseries")
            if cap > 0:
                soc_data[cap] = soc_ts

            # Add economics
            if cap > 0:
                capex = cap * cfg.cost_eur_per_kwh
                # Annualise if data < 1 year
                n_days = (df_balancing["timestamp"].max() - df_balancing["timestamp"].min()).days + 1
                annual_factor = 365.0 / max(n_days, 1)
                annual_revenue = result["total_revenue_eur"] * annual_factor
                annual_net = annual_revenue - cfg.annual_maintenance_eur

                result["capex_eur"] = round(capex, 2)
                result["annual_revenue_eur"] = round(annual_revenue, 2)
                result["annual_net_eur"] = round(annual_net, 2)

                if annual_net > 0:
                    result["payback_years"] = round(capex / annual_net, 1)
                else:
                    result["payback_years"] = float("inf")

                r = cfg.discount_rate_pct / 100
                npv_factor = sum(1 / (1 + r) ** t for t in range(1, cfg.lifetime_years + 1))
                result["npv_eur"] = round(-capex + annual_net * npv_factor, 2)
            else:
                result["capex_eur"] = 0.0
                result["annual_revenue_eur"] = 0.0
                result["annual_net_eur"] = 0.0
                result["payback_years"] = 0.0
                result["npv_eur"] = 0.0

            rows.append(result)

        return pd.DataFrame(rows), soc_data
