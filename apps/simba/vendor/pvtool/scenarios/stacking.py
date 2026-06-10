"""
Revenue stacking simulator — combines FCR and aFRR in a single battery.

For each 4-hour block, the simulator allocates the battery to whichever product
yields the highest expected revenue (greedy block-by-block allocation):

  - **FCR**: symmetric reserve, capacity price per block
  - **aFRR-up**: discharge reserve, capacity price per block
  - **aFRR-down**: charge reserve, capacity price per block

SOC state carries over between blocks. The allocation decision considers
both the capacity price and the SOC-feasibility of each product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RegelenergieConfig

BLOCK_HOURS = 4


class RevenueStackingSimulator:
    """
    Block-level product allocation for standalone battery storage.

    For each 4h block, greedily picks the highest-revenue product (FCR, aFRR-up,
    aFRR-down) considering current SOC constraints.

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
        Run stacking simulation for a single battery size.

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
                "fcr_blocks": 0,
                "afrr_up_blocks": 0,
                "afrr_down_blocks": 0,
                "idle_blocks": n // BLOCK_HOURS,
                "fcr_revenue_eur": 0.0,
                "afrr_up_revenue_eur": 0.0,
                "afrr_down_revenue_eur": 0.0,
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

        contracted_kw = capacity_kwh * cfg.c_rate
        if contracted_kw < cfg.min_pool_kw:
            n = len(df_balancing)
            return {
                "capacity_kwh": capacity_kwh,
                "contracted_kw": contracted_kw,
                "contracted_mw": contracted_kw / 1000.0,
                "total_blocks": n // BLOCK_HOURS,
                "available_blocks": 0,
                "fcr_blocks": 0,
                "afrr_up_blocks": 0,
                "afrr_down_blocks": 0,
                "idle_blocks": n // BLOCK_HOURS,
                "fcr_revenue_eur": 0.0,
                "afrr_up_revenue_eur": 0.0,
                "afrr_down_revenue_eur": 0.0,
                "capacity_revenue_eur": 0.0,
                "energy_revenue_eur": 0.0,
                "energy_cost_eur": 0.0,
                "rebalance_cost_eur": 0.0,
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
        """Core stacking dispatch loop."""
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
        available_blocks = 0
        fcr_blocks = 0
        afrr_up_blocks = 0
        afrr_down_blocks = 0
        fcr_revenue = 0.0
        afrr_up_revenue = 0.0
        afrr_down_revenue = 0.0
        energy_revenue = 0.0
        energy_cost = 0.0
        rebalance_cost = 0.0
        total_charged = 0.0
        total_discharged = 0.0

        for block_idx in range(n_blocks):
            h_start = block_idx * BLOCK_HOURS
            h_end = h_start + BLOCK_HOURS

            # Availability check
            if rng.random() > cfg.availability:
                soc_ts[h_start:h_end] = soc
                continue

            available_blocks += 1
            soc_pct = (soc / capacity_kwh) * 100

            # Greedy product allocation based on capacity price + SOC feasibility
            # FCR requires symmetric response — SOC should be near center
            fcr_feasible = cfg.min_soc_pct + 20 < soc_pct < cfg.max_soc_pct - 20
            up_feasible = soc_pct > cfg.min_soc_pct + 10  # enough to discharge
            down_feasible = soc_pct < cfg.max_soc_pct - 10  # enough to charge

            # Expected revenue per block for each product
            fcr_expected = cfg.fcr_block_price_eur_per_mw * contracted_mw if fcr_feasible else 0.0
            up_expected = cfg.afrr_up_block_price_eur_per_mw * contracted_mw if up_feasible else 0.0
            down_expected = cfg.afrr_down_block_price_eur_per_mw * contracted_mw if down_feasible else 0.0

            # Pick best product
            best = max(
                ("fcr", fcr_expected),
                ("afrr_up", up_expected),
                ("afrr_down", down_expected),
                key=lambda x: x[1],
            )
            product, cap_rev = best

            if cap_rev == 0:
                # No feasible product — idle
                soc_ts[h_start:h_end] = soc
                continue

            if product == "fcr":
                fcr_blocks += 1
                fcr_revenue += cap_rev
            elif product == "afrr_up":
                afrr_up_blocks += 1
                afrr_up_revenue += cap_rev
            else:
                afrr_down_blocks += 1
                afrr_down_revenue += cap_rev

            # Dispatch hours within block
            for h in range(h_start, h_end):
                price = prices_eur_kwh[h]

                if product == "fcr":
                    # FCR: symmetric activation (zero-mean, magnitude from half-normal)
                    magnitude = abs(rng.normal(0, cfg.fcr_mean_activation_fraction))
                    magnitude = min(magnitude, 1.0)
                    sign = 1 if rng.random() < 0.5 else -1
                    activation_kw = contracted_kw * magnitude * sign

                    if activation_kw > 0:
                        max_dis = (soc - min_soc) * cfg.discharge_efficiency
                        e = min(activation_kw, max_dis)
                        e = max(e, 0.0)
                        soc -= e / cfg.discharge_efficiency
                        energy_revenue += e * abs(price)
                        total_discharged += e
                    else:
                        max_chg = (max_soc - soc) / cfg.charge_efficiency
                        e = min(abs(activation_kw), max_chg)
                        e = max(e, 0.0)
                        soc += e * cfg.charge_efficiency
                        energy_cost += e * abs(price)
                        total_charged += e

                elif product == "afrr_up":
                    # aFRR UP: discharge when activated
                    if rng.random() <= cfg.afrr_activation_probability:
                        act_frac = np.clip(
                            rng.normal(cfg.afrr_mean_activation_fraction, 0.15),
                            0.0, 1.0,
                        )
                        activation_kw = contracted_kw * act_frac
                        max_dis = (soc - min_soc) * cfg.discharge_efficiency
                        e = min(activation_kw, max_dis)
                        e = max(e, 0.0)
                        soc -= e / cfg.discharge_efficiency
                        energy_revenue += e * price
                        total_discharged += e

                else:
                    # aFRR DOWN: charge when activated
                    if rng.random() <= cfg.afrr_activation_probability:
                        act_frac = np.clip(
                            rng.normal(cfg.afrr_mean_activation_fraction, 0.15),
                            0.0, 1.0,
                        )
                        activation_kw = contracted_kw * act_frac
                        max_chg = (max_soc - soc) / cfg.charge_efficiency
                        e = min(activation_kw, max_chg)
                        e = max(e, 0.0)
                        soc += e * cfg.charge_efficiency
                        energy_cost += e * price
                        total_charged += e

                soc_ts[h] = soc

            # End-of-block SOC rebalancing (trade energy at market to re-center)
            if abs(soc - target_soc) > deadband:
                delta = abs(soc - target_soc)
                rebalance_cost += delta * cfg.fcr_rebalance_cost_eur_per_kwh
                soc = target_soc

        # Fill remaining hours
        remainder = n_hours - n_blocks * BLOCK_HOURS
        if remainder > 0:
            soc_ts[n_blocks * BLOCK_HOURS:] = soc

        cap_total = fcr_revenue + afrr_up_revenue + afrr_down_revenue
        net_energy = energy_revenue - energy_cost
        total_revenue = cap_total + net_energy - rebalance_cost
        idle_blocks = n_blocks - available_blocks + (
            available_blocks - fcr_blocks - afrr_up_blocks - afrr_down_blocks
        )
        cycles = (total_charged + total_discharged) / (2 * capacity_kwh) if capacity_kwh > 0 else 0.0

        return {
            "capacity_kwh": capacity_kwh,
            "contracted_kw": contracted_kw,
            "contracted_mw": contracted_mw,
            "total_blocks": n_blocks,
            "available_blocks": available_blocks,
            "fcr_blocks": fcr_blocks,
            "afrr_up_blocks": afrr_up_blocks,
            "afrr_down_blocks": afrr_down_blocks,
            "idle_blocks": idle_blocks,
            "fcr_revenue_eur": round(fcr_revenue, 2),
            "afrr_up_revenue_eur": round(afrr_up_revenue, 2),
            "afrr_down_revenue_eur": round(afrr_down_revenue, 2),
            "capacity_revenue_eur": round(cap_total, 2),
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
        Run stacking simulation for all battery sizes in config.

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
