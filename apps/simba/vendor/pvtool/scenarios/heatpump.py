"""
Heat pump integration scenario.

Evaluates replacing gas heating with a heat pump, combined with an existing
PV system and optional battery + thermal storage.

NOT a BaseScenario subclass — the sweep dimensions (inlet temp, thermal
storage, battery size) differ from the standard battery-only scenarios.
Follows the same standalone pattern as RegelenergieEstimator.

Example
-------
>>> from pvtool.scenarios.heatpump import HeatPumpScenario
>>> scenario = HeatPumpScenario()
>>> result = scenario.run(df, inlet_temp_c=65, thermal_storage_kwh=70, battery_kwh=50)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HeatPumpConfig, BatteryConfig, MarketConfig, DataConfig
from ..battery import simulate_battery
from ..connectors.heatpump_profile import HeatPumpProfile


class HeatPumpScenario:
    """Heat pump + PV + battery + thermal storage scenario.

    Two-pass simulation:
      1. Generate HP electrical load (with optional thermal storage shifting)
      2. Merge into PV DataFrame, run battery self-consumption

    Parameters
    ----------
    hp_cfg : HeatPumpConfig, optional
    battery_cfg : BatteryConfig, optional
    market_cfg : MarketConfig, optional
    data_cfg : DataConfig, optional
    """

    def __init__(
        self,
        hp_cfg: HeatPumpConfig | None = None,
        battery_cfg: BatteryConfig | None = None,
        market_cfg: MarketConfig | None = None,
        data_cfg: DataConfig | None = None,
    ):
        self.hp_cfg = hp_cfg or HeatPumpConfig()
        self.battery_cfg = battery_cfg or BatteryConfig()
        self.market_cfg = market_cfg or MarketConfig()
        self.data_cfg = data_cfg or DataConfig()
        self._profile = HeatPumpProfile(self.hp_cfg)

    def gas_baseline_cost(self) -> float:
        """Annual gas cost: thermal_demand / boiler_efficiency * gas_price."""
        cfg = self.hp_cfg
        return cfg.annual_thermal_kwh / cfg.gas_boiler_efficiency * cfg.gas_price_eur_per_kwh

    def _apply_thermal_storage(
        self,
        hp_elec_kwh: np.ndarray,
        thermal_demand_kwh: np.ndarray,
        cop: np.ndarray,
        surplus_kwh: np.ndarray,
        thermal_storage_kwh: float,
    ) -> np.ndarray:
        """Shift HP runtime toward PV surplus hours using a thermal buffer.

        Greedy single-pass algorithm:
        - When PV surplus available: run HP extra to fill thermal store
        - When no PV surplus: drain thermal store, reduce HP electricity

        Parameters
        ----------
        hp_elec_kwh : array
            Original HP electricity per interval (before shifting).
        thermal_demand_kwh : array
            Thermal demand per interval.
        cop : array
            COP per interval.
        surplus_kwh : array
            PV surplus per interval (production - original consumption, before HP).
        thermal_storage_kwh : float
            Buffer tank capacity in kWh thermal.

        Returns
        -------
        np.ndarray
            Modified HP electricity profile (same total thermal, shifted timing).
        """
        n = len(hp_elec_kwh)
        modified = np.zeros(n)
        thermal_soc = 0.0
        dt_hours = self.battery_cfg.dt_hours
        loss_rate = self.hp_cfg.thermal_storage_loss_pct_per_hour / 100.0

        for i in range(n):
            # Standby loss
            thermal_soc *= (1.0 - loss_rate * dt_hours)

            # Drain buffer to meet thermal demand first
            from_buffer = min(thermal_demand_kwh[i], thermal_soc)
            thermal_soc -= from_buffer
            remaining_thermal = thermal_demand_kwh[i] - from_buffer

            # HP runs for remaining thermal demand
            if cop[i] > 0:
                base_hp_elec = remaining_thermal / cop[i]
            else:
                base_hp_elec = 0.0

            # If PV surplus: over-produce heat into buffer
            if surplus_kwh[i] > 0 and thermal_soc < thermal_storage_kwh:
                headroom = thermal_storage_kwh - thermal_soc
                # Extra thermal we can store, limited by PV surplus and tank headroom
                extra_elec = min(surplus_kwh[i], headroom / cop[i] if cop[i] > 0 else 0)
                extra_thermal = extra_elec * cop[i]
                thermal_soc += extra_thermal
                modified[i] = base_hp_elec + extra_elec
            else:
                modified[i] = base_hp_elec

        return modified

    def run(
        self,
        df: pd.DataFrame,
        inlet_temp_c: float | None = None,
        thermal_storage_kwh: float | None = None,
        battery_kwh: float = 0.0,
    ) -> dict:
        """Run a single HP scenario combination.

        Parameters
        ----------
        df : pd.DataFrame
            PV data with standard columns (production_kWh, consumption_kWh, etc.).
        inlet_temp_c : float, optional
            Heating system inlet temperature. Default: from hp_cfg.
        thermal_storage_kwh : float, optional
            Thermal buffer size. Default: from hp_cfg.
        battery_kwh : float
            Battery capacity in kWh (0 = no battery).

        Returns
        -------
        dict
            Comprehensive metrics including HP electricity, economics, self-consumption.
        """
        dcfg = self.data_cfg
        inlet = inlet_temp_c if inlet_temp_c is not None else self.hp_cfg.inlet_temp_c
        storage = thermal_storage_kwh if thermal_storage_kwh is not None else self.hp_cfg.thermal_storage_kwh

        # --- Step 1: Generate HP electrical profile ---
        timestamps = pd.DatetimeIndex(df[dcfg.timestamp_col])
        hp_df = self._profile.generate(timestamps, inlet_temp_c=inlet)

        hp_elec = hp_df["hp_electricity_kwh"].values
        thermal_demand = hp_df["thermal_demand_kwh"].values
        cop = hp_df["cop"].values
        avg_cop = np.average(cop, weights=thermal_demand) if thermal_demand.sum() > 0 else 0.0

        # Bivalent: gas covers whatever the HP doesn't
        hp_covered_thermal = float(thermal_demand.sum())
        residual_thermal = max(0.0, self.hp_cfg.annual_thermal_kwh - hp_covered_thermal)
        residual_gas_cost = (
            residual_thermal / self.hp_cfg.gas_boiler_efficiency * self.hp_cfg.gas_price_eur_per_kwh
        )

        # --- Step 2: Apply thermal storage shifting ---
        original_surplus = df[dcfg.surplus_col].values
        if storage > 0:
            hp_elec = self._apply_thermal_storage(
                hp_elec, thermal_demand, cop, original_surplus, storage,
            )

        hp_annual_kwh = float(hp_elec.sum())

        # --- Step 3: Merge HP load into PV DataFrame ---
        df_modified = df.copy()
        original_consumption = df[dcfg.consumption_col].values
        original_production = df[dcfg.production_col].values

        new_consumption = original_consumption + hp_elec
        new_surplus = original_production - new_consumption

        df_modified[dcfg.consumption_col] = new_consumption
        df_modified[dcfg.surplus_col] = new_surplus

        # --- Step 4: Run battery self-consumption on modified data ---
        batt_result = simulate_battery(
            df_modified, battery_kwh,
            strategy="self_consumption",
            battery_cfg=self.battery_cfg,
            market_cfg=self.market_cfg,
            data_cfg=self.data_cfg,
        )

        # --- Step 5: Compute economics ---
        gas_cost = self.gas_baseline_cost()
        mkt = self.market_cfg

        # HP electricity cost: grid portion at grid_buy_price
        hp_electricity_cost = batt_result["cost_eur"]

        # Also run baseline (no HP, no battery) for self-consumption comparison
        baseline_result = simulate_battery(
            df, 0, strategy="self_consumption",
            battery_cfg=self.battery_cfg,
            market_cfg=self.market_cfg,
            data_cfg=self.data_cfg,
        )

        total_prod = float(original_production.sum())
        sc_before = 1.0 - (baseline_result["grid_feedin_kwh"] / total_prod) if total_prod > 0 else 0.0
        sc_after = 1.0 - (batt_result["grid_feedin_kwh"] / total_prod) if total_prod > 0 else 0.0

        # PV directly covering HP load (approximate: surplus reduction)
        pv_to_hp = max(0, baseline_result["grid_feedin_kwh"] - batt_result["grid_feedin_kwh"])
        grid_to_hp = hp_annual_kwh - pv_to_hp

        # Savings vs gas
        # With HP: we pay hp_electricity_cost + residual_gas_cost (bivalent backup)
        # Net annual benefit = gas_cost - incremental_electricity_cost - residual_gas_cost - maintenance
        baseline_cost_no_hp = baseline_result["cost_eur"]
        incremental_electricity_cost = hp_electricity_cost - baseline_cost_no_hp
        annual_savings = (
            gas_cost
            - incremental_electricity_cost
            - residual_gas_cost
            - self.hp_cfg.hp_annual_maintenance_eur
        )

        # CAPEX
        hp_capex = self.hp_cfg.hp_capex_eur
        batt_capex = battery_kwh * self.battery_cfg.cost_eur_per_kwh if battery_kwh > 0 else 0.0
        total_capex = hp_capex + batt_capex

        # Payback
        if annual_savings > 0:
            payback = total_capex / annual_savings
        else:
            payback = float("inf")

        # NPV (simple discounting over HP lifetime)
        discount = mkt.discount_rate_pct / 100.0
        lifetime = self.hp_cfg.hp_lifetime_years
        npv = -total_capex + sum(
            annual_savings / (1 + discount) ** y for y in range(1, lifetime + 1)
        )

        return {
            "inlet_temp_c": inlet,
            "thermal_storage_kwh": storage,
            "battery_kwh": battery_kwh,
            "hp_annual_electricity_kwh": round(hp_annual_kwh, 1),
            "hp_covered_thermal_kwh": round(hp_covered_thermal, 1),
            "residual_gas_kwh": round(residual_thermal, 1),
            "average_cop": round(avg_cop, 2),
            "gas_cost_baseline_eur": round(gas_cost, 2),
            "residual_gas_cost_eur": round(residual_gas_cost, 2),
            "hp_electricity_cost_eur": round(incremental_electricity_cost, 2),
            "annual_savings_vs_gas_eur": round(annual_savings, 2),
            "self_consumption_rate_before": round(sc_before, 4),
            "self_consumption_rate_after": round(sc_after, 4),
            "pv_to_hp_kwh": round(pv_to_hp, 1),
            "grid_to_hp_kwh": round(grid_to_hp, 1),
            "battery_cycles": batt_result["cycles"],
            "grid_purchase_kwh": batt_result["grid_purchase_kwh"],
            "grid_feedin_kwh": batt_result["grid_feedin_kwh"],
            "total_capex_eur": round(total_capex, 2),
            "total_annual_savings_eur": round(annual_savings, 2),
            "simple_payback_years": round(payback, 1),
            "npv_eur": round(npv, 2),
        }

    def run_inlet_sweep(
        self,
        df: pd.DataFrame,
        inlet_temps: list[float] | None = None,
        thermal_storage_kwh: float = 0.0,
        battery_kwh: float = 0.0,
    ) -> pd.DataFrame:
        """Sweep inlet temperatures, return comparison table."""
        if inlet_temps is None:
            inlet_temps = [45.0, 55.0, 65.0]
        rows = [
            self.run(df, inlet_temp_c=t, thermal_storage_kwh=thermal_storage_kwh,
                     battery_kwh=battery_kwh)
            for t in inlet_temps
        ]
        return pd.DataFrame(rows)

    def run_thermal_storage_sweep(
        self,
        df: pd.DataFrame,
        inlet_temp_c: float | None = None,
        storage_sizes_kwh: list[float] | None = None,
        battery_kwh: float = 0.0,
    ) -> pd.DataFrame:
        """Sweep thermal storage sizes."""
        if storage_sizes_kwh is None:
            storage_sizes_kwh = [0, 35, 70, 105, 140]
        rows = [
            self.run(df, inlet_temp_c=inlet_temp_c,
                     thermal_storage_kwh=s, battery_kwh=battery_kwh)
            for s in storage_sizes_kwh
        ]
        return pd.DataFrame(rows)

    def run_full_sweep(
        self,
        df: pd.DataFrame,
        inlet_temps: list[float] | None = None,
        storage_sizes_kwh: list[float] | None = None,
        battery_sizes_kwh: list[float] | None = None,
    ) -> pd.DataFrame:
        """Full combinatorial sweep: inlet x storage x battery.

        Parameters
        ----------
        inlet_temps : list, optional
            Default: [45, 55, 65]
        storage_sizes_kwh : list, optional
            Default: [0, 35, 70]
        battery_sizes_kwh : list, optional
            Default: from battery_cfg.sizes_kwh

        Returns
        -------
        pd.DataFrame
            One row per combination.
        """
        if inlet_temps is None:
            inlet_temps = [45.0, 55.0, 65.0]
        if storage_sizes_kwh is None:
            storage_sizes_kwh = [0, 35, 70]
        if battery_sizes_kwh is None:
            battery_sizes_kwh = self.battery_cfg.sizes_kwh

        rows = []
        for t in inlet_temps:
            for s in storage_sizes_kwh:
                for b in battery_sizes_kwh:
                    rows.append(self.run(df, inlet_temp_c=t,
                                        thermal_storage_kwh=s, battery_kwh=b))
        return pd.DataFrame(rows)
