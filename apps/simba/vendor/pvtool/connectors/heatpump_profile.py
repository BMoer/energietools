"""
Heat pump electrical load profile generator.

Generates a synthetic heat pump electricity consumption profile from thermal
demand using a Carnot-fraction COP model. The COP depends on both the outdoor
temperature and the heating system inlet (supply) temperature.

All parameters are configurable via HeatPumpConfig — Austrian lowlands defaults,
but any site can override for the web tool.

Example
-------
>>> from pvtool.config import HeatPumpConfig
>>> from pvtool.connectors.heatpump_profile import HeatPumpProfile
>>> hp = HeatPumpProfile(HeatPumpConfig(annual_thermal_kwh=120_000, inlet_temp_c=65))
>>> df_hp = hp.generate(timestamps)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HeatPumpConfig


class HeatPumpProfile:
    """Generate heat pump electrical load from thermal demand.

    Uses a Carnot-fraction COP model::

        T_hot_K  = inlet_temp + 273.15 + condenser_approach
        T_cold_K = outdoor_temp + 273.15 - evaporator_approach
        COP = eta_carnot * T_hot_K / (T_hot_K - T_cold_K)

    Clamped to [cop_min, cop_max].

    Parameters
    ----------
    hp_cfg : HeatPumpConfig, optional
        All heat pump parameters. Defaults used when None.
    """

    # Heat exchanger approach temperatures (K)
    CONDENSER_APPROACH = 5.0
    EVAPORATOR_APPROACH = 5.0

    def __init__(self, hp_cfg: HeatPumpConfig | None = None):
        self.cfg = hp_cfg or HeatPumpConfig()

    def outdoor_temperature(self, timestamps: pd.DatetimeIndex) -> np.ndarray:
        """Synthetic outdoor temperature model.

        Default: Austrian lowlands (~47°N), configurable via
        ``HeatPumpConfig.mean_outdoor_temp_c`` and ``outdoor_temp_amplitude_c``.

        Mean temperature with seasonal cosine and ±3°C diurnal variation.
        """
        day_of_year = np.asarray(timestamps.dayofyear, dtype=float)
        hours = np.asarray(timestamps.hour + timestamps.minute / 60.0, dtype=float)

        mean = self.cfg.mean_outdoor_temp_c
        amp = self.cfg.outdoor_temp_amplitude_c

        # Seasonal: coldest mid-January (day 15), warmest mid-July
        temp_daily = mean - amp * np.cos(2 * np.pi * (day_of_year - 15) / 365)
        # Diurnal: ±3°C, peak at 14:00
        temp = temp_daily - 3 * np.cos(2 * np.pi * (hours - 14) / 24)
        return temp

    def compute_cop(
        self,
        outdoor_temp: np.ndarray,
        inlet_temp_c: float | None = None,
    ) -> np.ndarray:
        """Carnot-fraction COP for each interval.

        Parameters
        ----------
        outdoor_temp : array
            Outdoor temperature in °C per interval.
        inlet_temp_c : float, optional
            Heating system supply temperature. Defaults to ``cfg.inlet_temp_c``.

        Returns
        -------
        np.ndarray
            COP per interval, clamped to [cop_min, cop_max].
        """
        inlet = inlet_temp_c if inlet_temp_c is not None else self.cfg.inlet_temp_c

        t_hot_k = inlet + 273.15 + self.CONDENSER_APPROACH
        t_cold_k = outdoor_temp + 273.15 - self.EVAPORATOR_APPROACH

        delta_t = t_hot_k - t_cold_k
        # Avoid division by zero / negative (hot weather edge case)
        delta_t_safe = np.maximum(delta_t, 1.0)

        cop = self.cfg.cop_carnot_efficiency * t_hot_k / delta_t_safe
        return np.clip(cop, self.cfg.cop_min, self.cfg.cop_max)

    def generate(
        self,
        timestamps: pd.DatetimeIndex,
        inlet_temp_c: float | None = None,
    ) -> pd.DataFrame:
        """Generate HP electrical load profile for given timestamps.

        Distributes ``annual_thermal_kwh`` via degree-day weighting,
        then converts thermal → electrical via interval COP.

        Parameters
        ----------
        timestamps : pd.DatetimeIndex
            Timestamps at the desired resolution (e.g. 5-min from PV data).
        inlet_temp_c : float, optional
            Override inlet temperature for this run.

        Returns
        -------
        pd.DataFrame
            Columns: outdoor_temp_c, thermal_demand_kwh, cop, hp_electricity_kwh
        """
        outdoor_temp = self.outdoor_temperature(timestamps)
        cop = self.compute_cop(outdoor_temp, inlet_temp_c)

        # Full degree-day heating demand profile
        full_heating_need = np.maximum(self.cfg.heating_threshold_c - outdoor_temp, 0.0)
        full_dd = full_heating_need.sum()

        # Bivalent mask: HP only runs when outdoor_temp >= bivalent_point_c.
        # Below that threshold the gas boiler takes over, so HP electricity = 0.
        # The HP covers its proportional share of degree-days → annual thermal demand.
        if self.cfg.bivalent_point_c is not None:
            hp_mask = outdoor_temp >= self.cfg.bivalent_point_c
            hp_heating_need = full_heating_need * hp_mask
        else:
            hp_heating_need = full_heating_need

        hp_dd = hp_heating_need.sum()

        # Scale HP thermal to its share of annual_thermal_kwh
        if full_dd > 0 and hp_dd > 0:
            hp_fraction = hp_dd / full_dd
            thermal_demand = hp_heating_need * (self.cfg.annual_thermal_kwh * hp_fraction / hp_dd)
        else:
            thermal_demand = np.zeros_like(full_heating_need)

        hp_electricity = thermal_demand / cop

        return pd.DataFrame({
            "outdoor_temp_c": outdoor_temp,
            "thermal_demand_kwh": thermal_demand,
            "cop": cop,
            "hp_electricity_kwh": hp_electricity,
        }, index=timestamps)

    def generate_multi_inlet(
        self,
        timestamps: pd.DatetimeIndex,
        inlet_temps: list[float] | None = None,
    ) -> dict[float, pd.DataFrame]:
        """Generate HP profiles for multiple inlet temperatures.

        Parameters
        ----------
        inlet_temps : list of float, optional
            Inlet temperatures to compare. Default: [45, 55, 65].

        Returns
        -------
        dict
            {inlet_temp_c: DataFrame} for each temperature.
        """
        if inlet_temps is None:
            inlet_temps = [45.0, 55.0, 65.0]
        return {t: self.generate(timestamps, inlet_temp_c=t) for t in inlet_temps}
