"""
aFRR (automatic Frequency Restoration Reserve) dispatch simulation for standalone battery.

Unlike FCR (symmetric), aFRR allows **asymmetric bidding**: the battery can bid
separately for upward regulation (discharge) and downward regulation (charge)
in each 4-hour product block.

Revenue sources:
  1. **Capacity payment** — EUR/MW per 4h block for up and/or down availability
  2. **Energy settlement** — EUR/MWh for actual activations (ENTSO-E settlement prices)

Bid direction is SOC-driven:
  - High SOC (>60%): prefer UP bids (discharge to earn from high prices)
  - Low SOC (<40%): prefer DOWN bids (charge to earn from low/negative prices)
  - Mid SOC (40–60%): bid both directions

Austrian market: APG is the TSO, aFRR auctions via regelleistung.net.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RegelenergieConfig

BLOCK_HOURS = 4


class AFRRSimulator:
    """
    Time-step aFRR dispatch simulation for standalone battery storage.

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
        Run aFRR simulation for a single battery size.

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
                "up_blocks": 0,
                "down_blocks": 0,
                "both_blocks": 0,
                "capacity_revenue_up_eur": 0.0,
                "capacity_revenue_down_eur": 0.0,
                "capacity_revenue_eur": 0.0,
                "energy_revenue_eur": 0.0,
                "energy_cost_eur": 0.0,
                "total_revenue_eur": 0.0,
                "total_charged_kwh": 0.0,
                "total_discharged_kwh": 0.0,
                "cycles": 0.0,
                "soc_timeseries": np.zeros(n),
            }

        contracted_kw = capacity_kwh * cfg.c_rate
        if contracted_kw < cfg.min_pool_kw:
            n = len(df_balancing)
            return {
                "capacity_kwh": capacity_kwh,
                "contracted_kw": contracted_kw,
                "contracted_mw": contracted_kw / 1000.0,
                "total_blocks": n // BLOCK_HOURS,
                "available_blocks": 0,
                "up_blocks": 0,
                "down_blocks": 0,
                "both_blocks": 0,
                "capacity_revenue_up_eur": 0.0,
                "capacity_revenue_down_eur": 0.0,
                "capacity_revenue_eur": 0.0,
                "energy_revenue_eur": 0.0,
                "energy_cost_eur": 0.0,
                "total_revenue_eur": 0.0,
                "total_charged_kwh": 0.0,
                "total_discharged_kwh": 0.0,
                "cycles": 0.0,
                "note": f"Below minimum pool size ({cfg.min_pool_kw} kW)",
                "soc_timeseries": np.full(n, capacity_kwh * 0.5),
            }

        return self._simulate(df_balancing, capacity_kwh, seed)

    def _simulate(
        self,
        df_balancing: pd.DataFrame,
        capacity_kwh: float,
        seed: int,
    ) -> dict:
        """Core aFRR dispatch loop."""
        cfg = self.cfg
        rng = np.random.default_rng(seed)

        contracted_kw = capacity_kwh * cfg.c_rate
        contracted_mw = contracted_kw / 1000.0
        min_soc = capacity_kwh * cfg.min_soc_pct / 100.0
        max_soc = capacity_kwh * cfg.max_soc_pct / 100.0

        prices_eur_kwh = df_balancing["price_eur_mwh"].values / 1000.0
        n_hours = len(prices_eur_kwh)
        n_blocks = n_hours // BLOCK_HOURS

        # State
        soc = capacity_kwh * 0.5  # start at 50%
        soc_ts = np.zeros(n_hours)
        cap_revenue_up = 0.0
        cap_revenue_down = 0.0
        energy_revenue = 0.0
        energy_cost = 0.0
        total_charged = 0.0
        total_discharged = 0.0
        available_blocks = 0
        up_blocks = 0
        down_blocks = 0
        both_blocks = 0

        for block_idx in range(n_blocks):
            h_start = block_idx * BLOCK_HOURS
            h_end = h_start + BLOCK_HOURS

            # Availability check
            if rng.random() > cfg.availability:
                soc_ts[h_start:h_end] = soc
                continue

            available_blocks += 1

            # Determine bid direction based on SOC
            soc_pct = (soc / capacity_kwh) * 100
            if soc_pct > 60:
                bid_direction = "up"
                up_blocks += 1
                cap_revenue_up += contracted_mw * cfg.afrr_up_block_price_eur_per_mw
            elif soc_pct < 40:
                bid_direction = "down"
                down_blocks += 1
                cap_revenue_down += contracted_mw * cfg.afrr_down_block_price_eur_per_mw
            else:
                bid_direction = "both"
                both_blocks += 1
                cap_revenue_up += contracted_mw * cfg.afrr_up_block_price_eur_per_mw * 0.5
                cap_revenue_down += contracted_mw * cfg.afrr_down_block_price_eur_per_mw * 0.5

            # Hourly dispatch within block
            for h in range(h_start, h_end):
                price = prices_eur_kwh[h]

                # Activation check — aFRR is intermittent
                if rng.random() > cfg.afrr_activation_probability:
                    soc_ts[h] = soc
                    continue

                # Activation magnitude
                act_frac = np.clip(
                    rng.normal(cfg.afrr_mean_activation_fraction, 0.15),
                    0.0,
                    1.0,
                )
                activation_kw = contracted_kw * act_frac

                # Determine activation direction
                if bid_direction == "up":
                    # Discharge (inject to grid)
                    max_discharge_kwh = (soc - min_soc) * cfg.discharge_efficiency
                    energy_kwh = min(activation_kw * 1.0, max_discharge_kwh)
                    energy_kwh = max(energy_kwh, 0.0)
                    soc -= energy_kwh / cfg.discharge_efficiency
                    energy_revenue += energy_kwh * price
                    total_discharged += energy_kwh
                elif bid_direction == "down":
                    # Charge (absorb from grid)
                    max_charge_kwh = (max_soc - soc) / cfg.charge_efficiency
                    energy_kwh = min(activation_kw * 1.0, max_charge_kwh)
                    energy_kwh = max(energy_kwh, 0.0)
                    soc += energy_kwh * cfg.charge_efficiency
                    energy_cost += energy_kwh * price
                    total_charged += energy_kwh
                else:
                    # Both directions — decide based on settlement price
                    if price > 0:
                        # High price → discharge (sell)
                        max_discharge_kwh = (soc - min_soc) * cfg.discharge_efficiency
                        energy_kwh = min(activation_kw * 1.0, max_discharge_kwh)
                        energy_kwh = max(energy_kwh, 0.0)
                        soc -= energy_kwh / cfg.discharge_efficiency
                        energy_revenue += energy_kwh * price
                        total_discharged += energy_kwh
                    else:
                        # Negative price → charge (get paid to absorb)
                        max_charge_kwh = (max_soc - soc) / cfg.charge_efficiency
                        energy_kwh = min(activation_kw * 1.0, max_charge_kwh)
                        energy_kwh = max(energy_kwh, 0.0)
                        soc += energy_kwh * cfg.charge_efficiency
                        # Negative price means we earn by charging
                        energy_revenue += energy_kwh * abs(price)
                        total_charged += energy_kwh

                soc_ts[h] = soc

        # Fill remaining hours
        remainder = n_hours - n_blocks * BLOCK_HOURS
        if remainder > 0:
            soc_ts[n_blocks * BLOCK_HOURS:] = soc

        cap_revenue_total = cap_revenue_up + cap_revenue_down
        net_energy = energy_revenue - energy_cost
        total_revenue = cap_revenue_total + net_energy
        cycles = (total_charged + total_discharged) / (2 * capacity_kwh) if capacity_kwh > 0 else 0.0

        return {
            "capacity_kwh": capacity_kwh,
            "contracted_kw": contracted_kw,
            "contracted_mw": contracted_mw,
            "total_blocks": n_blocks,
            "available_blocks": available_blocks,
            "up_blocks": up_blocks,
            "down_blocks": down_blocks,
            "both_blocks": both_blocks,
            "capacity_revenue_up_eur": round(cap_revenue_up, 2),
            "capacity_revenue_down_eur": round(cap_revenue_down, 2),
            "capacity_revenue_eur": round(cap_revenue_total, 2),
            "energy_revenue_eur": round(energy_revenue, 2),
            "energy_cost_eur": round(energy_cost, 2),
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
        Run aFRR simulation for all battery sizes in config.

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
