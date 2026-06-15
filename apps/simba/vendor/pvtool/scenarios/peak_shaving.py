"""Scenario 4: Peak shaving — keep grid draw below threshold using the battery.

Two dispatch modes (set via PeakShavingConfig.mode)
----------------------------------------------------
greedy   Reactive loop: discharge whenever grid draw exceeds peak_threshold_kw,
         charge from PV surplus otherwise.  Fast — one pass over the data.

optimal  Linear-programming dispatch via CVXPY + HiGHS.  Minimises the true
         worst-case grid draw over the full year with perfect foresight.
         Requires: pip install cvxpy  (~30–90 s per battery size for a full year)

         LP formulation
         --------------
         Variables : p_dis[t]  discharge power at battery terminals (kW)
                     p_chg[t]  charge power at battery terminals (kW)
                     soc[t]    state of charge (kWh)
                     peak      scalar — the peak grid draw to minimise (kW)

         Grid draw : grid_kw[t] = net_demand_kw[t]
                                  − p_dis[t] · η_dis
                                  + p_chg[t] / η_chg

         Objective : minimise  peak
         s.t.        grid_kw[t] ≤ peak            ∀t
                     soc[t+1]   = soc[t] + (p_chg[t] − p_dis[t]) · Δt
                     min_soc ≤ soc[t] ≤ max_soc
                     0 ≤ p_dis[t], p_chg[t] ≤ max_power_kw

Primary economic benefit
------------------------
Reduction in the monthly demand charge (Leistungspreis, EUR/kW/year).

Secondary benefit
-----------------
Energy-cost savings when battery energy replaces peak grid purchases.

Return keys (both modes)
------------------------
capacity_kwh            usable battery size (kWh)
strategy                "peak_shaving_greedy" | "peak_shaving_optimal"
baseline_peak_kw        highest monthly peak in raw data, no battery (kW)
achieved_peak_kw        highest monthly peak after battery dispatch (kW)
peak_reduction_kw       baseline − achieved (kW)
demand_savings_eur      annual demand-charge reduction (EUR)
energy_savings_eur      annual energy-cost reduction (EUR)
net_benefit_eur         demand_savings + energy_savings (EUR)
grid_purchase_kwh       total grid energy imported with battery (kWh)
batt_charged_kwh        energy stored into battery (kWh)
batt_discharged_kwh     energy delivered from battery to load (kWh)
cycles                  full equivalent cycles per year
soc_timeseries          per-interval SOC array (kWh)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScenario
from ..config import BatteryConfig, MarketConfig, DataConfig, PeakShavingConfig


class PeakShavingScenario(BaseScenario):
    """Battery dispatch that clips grid demand spikes below a set threshold."""

    def __init__(
        self,
        battery_cfg: BatteryConfig | None = None,
        market_cfg: MarketConfig | None = None,
        data_cfg: DataConfig | None = None,
        peak_shaving_cfg: PeakShavingConfig | None = None,
    ):
        super().__init__(battery_cfg, market_cfg, data_cfg)
        self.ps_cfg = peak_shaving_cfg or PeakShavingConfig()

    # ------------------------------------------------------------------ #
    #  Public interface
    # ------------------------------------------------------------------ #

    def run(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        if self.ps_cfg.mode == "optimal":
            return self._run_optimal(df, capacity_kwh)
        return self._run_greedy(df, capacity_kwh)

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #

    def _extract(self, df: pd.DataFrame):
        """Pull arrays and timestamps from the DataFrame."""
        dcfg = self.data_cfg
        consumption = df[dcfg.consumption_col].values
        production = df[dcfg.production_col].values
        timestamps = pd.to_datetime(df[dcfg.timestamp_col])
        net_demand_kwh = consumption - production          # kWh per 5-min interval
        net_demand_kw = net_demand_kwh / self.battery_cfg.dt_hours  # instantaneous kW
        return net_demand_kwh, net_demand_kw, timestamps

    def _baseline(self, net_demand_kw: np.ndarray, timestamps: pd.Series) -> dict:
        """Compute baseline metrics (no battery) and effective billing baseline."""
        ps = self.ps_cfg
        mkt = self.market_cfg
        dt = self.battery_cfg.dt_hours

        baseline_grid_kw = np.maximum(net_demand_kw, 0.0)
        baseline_monthly_peaks = _monthly_peaks(timestamps, baseline_grid_kw)

        data_baseline_peak = max(baseline_monthly_peaks.values()) if baseline_monthly_peaks else 0.0
        # Override if set (corrects data spikes for demand-savings calculation only)
        effective_baseline_peak = (
            ps.baseline_peak_kw if ps.baseline_peak_kw is not None else data_baseline_peak
        )
        n_months = len(baseline_monthly_peaks)
        baseline_demand_charge = (
            effective_baseline_peak * ps.demand_charge_eur_per_kw_year / 12.0 * n_months
        )
        baseline_grid_purchase = float(np.maximum(net_demand_kw, 0.0).sum() * dt)

        return {
            "data_baseline_peak": data_baseline_peak,
            "baseline_demand_charge": baseline_demand_charge,
            "baseline_grid_purchase": baseline_grid_purchase,
            "n_months": n_months,
        }

    def _build_result(
        self,
        capacity_kwh: float,
        strategy: str,
        base: dict,
        actual_grid_kw: np.ndarray,
        timestamps: pd.Series,
        total_grid_purchase: float,
        total_batt_charged: float,
        total_batt_discharged: float,
        cycles: float,
        soc_ts: np.ndarray,
    ) -> dict:
        """Assemble the standard result dict from computed arrays."""
        ps = self.ps_cfg
        mkt = self.market_cfg

        achieved_monthly_peaks = _monthly_peaks(timestamps, actual_grid_kw)
        achieved_demand_charge = (
            sum(achieved_monthly_peaks.values())
            * ps.demand_charge_eur_per_kw_year
            / 12.0
        )
        demand_savings = base["baseline_demand_charge"] - achieved_demand_charge
        energy_savings = (
            (base["baseline_grid_purchase"] - total_grid_purchase)
            * mkt.grid_buy_price_eur
        )

        achieved_peak = max(achieved_monthly_peaks.values())
        data_peak = base["data_baseline_peak"]

        return {
            "capacity_kwh": capacity_kwh,
            "strategy": strategy,
            "baseline_peak_kw": round(data_peak, 2),
            "achieved_peak_kw": round(achieved_peak, 2),
            "peak_reduction_kw": round(data_peak - achieved_peak, 2),
            "demand_savings_eur": round(demand_savings, 2),
            "energy_savings_eur": round(energy_savings, 2),
            "net_benefit_eur": round(demand_savings + energy_savings, 2),
            "grid_purchase_kwh": round(total_grid_purchase, 1),
            "batt_charged_kwh": round(total_batt_charged, 1),
            "batt_discharged_kwh": round(total_batt_discharged, 1),
            "cycles": round(cycles, 1),
            "soc_timeseries": soc_ts,
        }

    # ------------------------------------------------------------------ #
    #  Greedy dispatch
    # ------------------------------------------------------------------ #

    def _run_greedy(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        cfg = self.battery_cfg
        ps = self.ps_cfg
        dt = cfg.dt_hours

        net_demand_kwh, net_demand_kw, timestamps = self._extract(df)
        base = self._baseline(net_demand_kw, timestamps)

        if capacity_kwh == 0:
            p = base["data_baseline_peak"]
            return {
                "capacity_kwh": 0, "strategy": "peak_shaving_greedy",
                "baseline_peak_kw": round(p, 2), "achieved_peak_kw": round(p, 2),
                "peak_reduction_kw": 0.0,
                "demand_savings_eur": 0.0, "energy_savings_eur": 0.0,
                "net_benefit_eur": 0.0,
                "grid_purchase_kwh": round(base["baseline_grid_purchase"], 1),
                "batt_charged_kwh": 0.0, "batt_discharged_kwh": 0.0,
                "cycles": 0.0, "soc_timeseries": np.zeros(len(df)),
            }

        max_power_kw = capacity_kwh * cfg.c_rate
        min_soc = capacity_kwh * cfg.min_soc_pct / 100.0
        max_soc = capacity_kwh * cfg.max_soc_pct / 100.0
        max_charge_interval = max_power_kw * dt * cfg.charge_efficiency
        max_discharge_interval = max_power_kw * dt
        threshold_kwh = ps.peak_threshold_kw * dt

        n = len(df)
        soc = min_soc
        soc_ts = np.zeros(n)
        actual_grid_kw = np.zeros(n)
        total_grid_purchase = total_batt_charged = total_batt_discharged = 0.0

        for i in range(n):
            nd = net_demand_kwh[i]

            if nd > threshold_kwh:
                excess = nd - threshold_kwh
                can_dis = min(soc - min_soc, excess / cfg.discharge_efficiency, max_discharge_interval)
                delivered = can_dis * cfg.discharge_efficiency
                soc -= can_dis
                total_batt_discharged += delivered
                grid_kwh = max(nd - delivered, 0.0)
                total_grid_purchase += grid_kwh
                actual_grid_kw[i] = grid_kwh / dt

            elif nd <= 0.0:
                surplus = -nd
                can_chg = min(surplus * cfg.charge_efficiency, max_soc - soc, max_charge_interval)
                soc += can_chg
                total_batt_charged += can_chg

            elif ps.combine_self_consumption:
                # Combined mode: discharge to cover demand below threshold
                can_dis = min(soc - min_soc, nd / cfg.discharge_efficiency, max_discharge_interval)
                delivered = can_dis * cfg.discharge_efficiency
                soc -= can_dis
                total_batt_discharged += delivered
                grid_kwh = max(nd - delivered, 0.0)
                total_grid_purchase += grid_kwh
                actual_grid_kw[i] = grid_kwh / dt

            else:
                total_grid_purchase += nd
                actual_grid_kw[i] = nd / dt

            soc_ts[i] = soc

        cycles = total_batt_charged / capacity_kwh

        return self._build_result(
            capacity_kwh, "peak_shaving_greedy", base,
            actual_grid_kw, timestamps,
            total_grid_purchase, total_batt_charged, total_batt_discharged,
            cycles, soc_ts,
        )

    # ------------------------------------------------------------------ #
    #  Optimal LP dispatch (CVXPY + HiGHS)
    # ------------------------------------------------------------------ #

    def _run_optimal(self, df: pd.DataFrame, capacity_kwh: float) -> dict:
        try:
            import cvxpy as cp
        except ImportError:
            raise ImportError(
                "cvxpy is required for mode='optimal'.  Install with: pip install cvxpy"
            )

        cfg = self.battery_cfg
        dt = cfg.dt_hours

        net_demand_kwh, net_demand_kw, timestamps = self._extract(df)
        base = self._baseline(net_demand_kw, timestamps)

        if capacity_kwh == 0:
            p = base["data_baseline_peak"]
            return {
                "capacity_kwh": 0, "strategy": "peak_shaving_optimal",
                "baseline_peak_kw": round(p, 2), "achieved_peak_kw": round(p, 2),
                "peak_reduction_kw": 0.0,
                "demand_savings_eur": 0.0, "energy_savings_eur": 0.0,
                "net_benefit_eur": 0.0,
                "grid_purchase_kwh": round(base["baseline_grid_purchase"], 1),
                "batt_charged_kwh": 0.0, "batt_discharged_kwh": 0.0,
                "cycles": 0.0, "soc_timeseries": np.zeros(len(df)),
            }

        max_power_kw = capacity_kwh * cfg.c_rate
        min_soc = capacity_kwh * cfg.min_soc_pct / 100.0
        max_soc = capacity_kwh * cfg.max_soc_pct / 100.0
        n = len(df)

        # ── LP variables ────────────────────────────────────────────
        peak = cp.Variable(nonneg=True)
        p_dis = cp.Variable(n, nonneg=True)   # kW from battery terminals
        p_chg = cp.Variable(n, nonneg=True)   # kW into battery terminals
        soc = cp.Variable(n + 1)

        # Grid draw at each interval (kW):
        #   net_demand_kw − p_dis·η_dis + p_chg/η_chg
        grid_kw = net_demand_kw - p_dis * cfg.discharge_efficiency + p_chg / cfg.charge_efficiency

        constraints = [
            grid_kw <= peak,                          # peak definition
            soc[1:] == soc[:-1] + (p_chg - p_dis) * dt,  # SOC dynamics
            soc >= min_soc,
            soc <= max_soc,
            p_dis <= max_power_kw,
            p_chg <= max_power_kw,
            soc[0] == min_soc,                        # start at min
            soc[n] >= min_soc,                        # end at least at min
        ]

        if self.ps_cfg.combine_self_consumption:
            # Combined: minimise peak + energy cost (grid purchases × buy price)
            # Weight energy cost so the solver reduces grid purchases too,
            # but peak reduction stays the primary objective.
            grid_purchase_kw = cp.maximum(grid_kw, 0)
            energy_cost = cp.sum(grid_purchase_kw) * dt * self.market_cfg.grid_buy_price_eur
            # Scale: demand charge per kW is ~63 EUR/kW/yr; energy is ~0.25 EUR/kWh.
            # We want peak to dominate, so energy weight = 1.0 is fine (it's already small).
            prob = cp.Problem(cp.Minimize(peak + energy_cost), constraints)
        else:
            prob = cp.Problem(cp.Minimize(peak), constraints)
        prob.solve(solver=cp.HIGHS, verbose=False)

        if prob.status not in ("optimal", "optimal_inaccurate"):
            raise RuntimeError(f"CVXPY/HiGHS solver failed: {prob.status}")

        # ── Extract results ─────────────────────────────────────────
        grid_kw_val = grid_kw.value
        actual_grid_kw = np.maximum(grid_kw_val, 0.0)

        p_dis_val = np.maximum(p_dis.value, 0.0)
        p_chg_val = np.maximum(p_chg.value, 0.0)
        soc_ts = soc.value[:-1]

        total_grid_purchase = float(np.maximum(grid_kw_val, 0.0).sum() * dt)
        # Charged/discharged at battery terminals → convert to kWh
        total_batt_charged = float((p_chg_val * dt).sum())
        total_batt_discharged = float((p_dis_val * cfg.discharge_efficiency * dt).sum())
        cycles = total_batt_charged / capacity_kwh

        return self._build_result(
            capacity_kwh, "peak_shaving_optimal", base,
            actual_grid_kw, timestamps,
            total_grid_purchase, total_batt_charged, total_batt_discharged,
            cycles, soc_ts,
        )


# ------------------------------------------------------------------ #
#  Helper
# ------------------------------------------------------------------ #

def _monthly_peaks(timestamps: pd.Series, power_kw: np.ndarray) -> dict:
    """Return {month_str: peak_kw} for every calendar month in the data."""
    ts = pd.Series(timestamps.values if hasattr(timestamps, "values") else timestamps)
    ts = pd.to_datetime(ts)
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    months = ts.dt.to_period("M").astype(str)
    return pd.Series(power_kw).groupby(months.values).max().to_dict()
