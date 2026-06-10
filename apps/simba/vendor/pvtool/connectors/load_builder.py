"""
Composable load profile builder.

Generates a synthetic consumption profile by combining modular load components:
- Base household (H0 profile, scaled to annual kWh)
- Heat pump (Carnot-fraction COP model, degree-day thermal demand)
- EV charging (configurable daily km, battery size, charging window)
- Domestic hot water (flat profile with morning/evening peaks)

Each component can be enabled/disabled independently. The combined profile
is returned in BaseConnector-compatible format (timestamp, production_kWh,
consumption_kWh, surplus_kWh) for direct use in battery simulations.

Example
-------
>>> from pvtool.connectors.load_builder import LoadBuilder, LoadProfile
>>> profile = LoadProfile(
...     household_annual_kwh=4500,
...     has_heatpump=True,
...     hp_annual_thermal_kwh=20000,
...     hp_inlet_temp_c=45,
... )
>>> builder = LoadBuilder()
>>> df = builder.generate(profile, year=2025)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .load_profiles import LoadProfileGenerator
from .heatpump_profile import HeatPumpProfile
from ..config import HeatPumpConfig


@dataclass
class EVProfile:
    """EV charging parameters.

    Models a simple daily charging pattern with configurable window.
    """

    daily_km: float = 40.0              # average daily driving distance
    consumption_kwh_per_100km: float = 18.0  # EV efficiency (kWh/100km)
    battery_kwh: float = 60.0           # EV battery capacity
    charging_power_kw: float = 11.0     # home wallbox power (kW)
    charging_start_hour: float = 18.0   # start charging (hour of day)
    charging_end_hour: float = 6.0      # stop charging (next morning)
    weekend_factor: float = 0.6         # weekend driving is typically less


@dataclass
class LoadProfile:
    """Combined load profile configuration.

    Enable/disable components and set their parameters.
    """

    # Base household
    household_annual_kwh: float = 4500.0
    household_persons: int = 0  # 0 = use annual_kwh directly

    # Heat pump
    has_heatpump: bool = False
    hp_annual_thermal_kwh: float = 20_000.0  # typical single-family house
    hp_inlet_temp_c: float = 45.0            # floor heating = 35-40, radiators = 55-65
    hp_bivalent_point_c: float | None = None  # None = monovalent
    hp_heating_threshold_c: float = 15.0

    # EV charging
    has_ev: bool = False
    ev: EVProfile = field(default_factory=EVProfile)

    # Domestic hot water (electric, separate from HP)
    has_dhw: bool = False
    dhw_annual_kwh: float = 2000.0  # typical: 1500-2500 kWh/year for 2-4 persons

    # Resolution
    interval_minutes: int = 5

    @property
    def total_annual_kwh(self) -> float:
        """Estimated total annual consumption across all components."""
        total = self.household_annual_kwh
        if self.has_heatpump:
            # Rough estimate — actual depends on COP
            total += self.hp_annual_thermal_kwh / 3.0
        if self.has_ev:
            daily_kwh = self.ev.daily_km * self.ev.consumption_kwh_per_100km / 100
            total += daily_kwh * 365 * 0.85  # ~85% accounting for weekends
        if self.has_dhw:
            total += self.dhw_annual_kwh
        return total


class LoadBuilder:
    """Build a composite load profile from individual components.

    Each component generates its own consumption series, then all are
    summed into a single consumption_kWh column.
    """

    def generate(self, profile: LoadProfile, year: int = 2025) -> pd.DataFrame:
        """Generate combined load profile for a full year.

        Parameters
        ----------
        profile : LoadProfile
            Configuration for all load components.
        year : int
            Target year.

        Returns
        -------
        pd.DataFrame
            Columns: timestamp, consumption_kWh, plus per-component columns:
            household_kWh, hp_electricity_kWh, ev_kWh, dhw_kWh (if enabled).
        """
        timestamps = pd.date_range(
            f"{year}-01-01", f"{year + 1}-01-01",
            freq=f"{profile.interval_minutes}min",
            tz="UTC",
            inclusive="left",
        )

        result = pd.DataFrame({"timestamp": timestamps})
        total_consumption = np.zeros(len(timestamps))

        # --- Base household ---
        household = self._generate_household(profile, year)
        result["household_kWh"] = household
        total_consumption += household

        # --- Heat pump ---
        if profile.has_heatpump:
            hp = self._generate_heatpump(profile, timestamps)
            result["hp_electricity_kWh"] = hp
            total_consumption += hp

        # --- EV charging ---
        if profile.has_ev:
            ev = self._generate_ev(profile, timestamps)
            result["ev_kWh"] = ev
            total_consumption += ev

        # --- Domestic hot water ---
        if profile.has_dhw:
            dhw = self._generate_dhw(profile, timestamps)
            result["dhw_kWh"] = dhw
            total_consumption += dhw

        result["consumption_kWh"] = total_consumption
        result["production_kWh"] = 0.0
        result["surplus_kWh"] = -total_consumption

        return result

    def _generate_household(
        self, profile: LoadProfile, year: int
    ) -> np.ndarray:
        """Generate base household consumption using H0 profile."""
        gen = LoadProfileGenerator(
            annual_kwh=profile.household_annual_kwh,
            interval_minutes=profile.interval_minutes,
        )
        df_h0 = gen.generate_h0(year)
        return df_h0["consumption_kWh"].values

    def _generate_heatpump(
        self, profile: LoadProfile, timestamps: pd.DatetimeIndex
    ) -> np.ndarray:
        """Generate heat pump electrical load."""
        hp_cfg = HeatPumpConfig(
            annual_thermal_kwh=profile.hp_annual_thermal_kwh,
            inlet_temp_c=profile.hp_inlet_temp_c,
            heating_threshold_c=profile.hp_heating_threshold_c,
            bivalent_point_c=profile.hp_bivalent_point_c,
        )
        hp = HeatPumpProfile(hp_cfg)
        df_hp = hp.generate(timestamps, inlet_temp_c=profile.hp_inlet_temp_c)
        return df_hp["hp_electricity_kwh"].values

    def _generate_ev(
        self, profile: LoadProfile, timestamps: pd.DatetimeIndex
    ) -> np.ndarray:
        """Generate EV charging load.

        Models a daily charging session within a configurable time window.
        Energy needed per day = daily_km * consumption_per_100km / 100.
        Charging is distributed evenly within the window at up to charging_power_kw.
        """
        ev = profile.ev
        interval_hours = profile.interval_minutes / 60.0
        n = len(timestamps)

        hours = np.asarray(timestamps.hour + timestamps.minute / 60.0, dtype=float)
        is_weekend = np.asarray(timestamps.dayofweek >= 5)

        # Daily energy need
        daily_kwh = ev.daily_km * ev.consumption_kwh_per_100km / 100.0

        # Charging window mask
        if ev.charging_start_hour > ev.charging_end_hour:
            # Overnight: e.g. 18:00-06:00
            in_window = (hours >= ev.charging_start_hour) | (hours < ev.charging_end_hour)
        else:
            # Same day: e.g. 08:00-16:00
            in_window = (hours >= ev.charging_start_hour) & (hours < ev.charging_end_hour)

        # Max energy per interval
        max_per_interval = ev.charging_power_kw * interval_hours

        # Build daily consumption
        consumption = np.zeros(n)
        dates = timestamps.date
        unique_dates = np.unique(dates)

        for d in unique_dates:
            day_mask = dates == d
            window_mask = day_mask & in_window

            n_intervals = window_mask.sum()
            if n_intervals == 0:
                continue

            # Weekend adjustment
            day_date = pd.Timestamp(d)
            is_we = day_date.dayofweek >= 5
            factor = ev.weekend_factor if is_we else 1.0
            needed = daily_kwh * factor

            # Distribute evenly across window, capped at max power
            per_interval = min(needed / n_intervals, max_per_interval)
            consumption[window_mask] = per_interval

        return consumption

    def _generate_dhw(
        self, profile: LoadProfile, timestamps: pd.DatetimeIndex
    ) -> np.ndarray:
        """Generate domestic hot water load.

        Morning peak (6-9h) and evening peak (18-21h) pattern,
        with lower baseline throughout the day. Scaled to annual_kwh.
        """
        interval_hours = profile.interval_minutes / 60.0
        hours = np.asarray(timestamps.hour + timestamps.minute / 60.0, dtype=float)

        # DHW pattern: morning and evening peaks
        morning = np.exp(-0.5 * ((hours - 7.0) / 1.0) ** 2)
        evening = np.exp(-0.5 * ((hours - 19.5) / 1.0) ** 2)
        baseline = 0.1
        pattern = baseline + 0.5 * morning + 0.4 * evening

        # Scale to annual consumption
        raw_annual = pattern.sum() * interval_hours
        scale_factor = profile.dhw_annual_kwh / raw_annual
        return pattern * scale_factor * interval_hours

    def summary(self, profile: LoadProfile, year: int = 2025) -> dict:
        """Return annual energy summary per component without generating full profile."""
        df = self.generate(profile, year)
        result = {
            "total_annual_kwh": round(df["consumption_kWh"].sum(), 0),
            "household_kwh": round(df["household_kWh"].sum(), 0),
        }
        if profile.has_heatpump:
            result["hp_electricity_kwh"] = round(df["hp_electricity_kWh"].sum(), 0)
        if profile.has_ev:
            result["ev_kwh"] = round(df["ev_kWh"].sum(), 0)
        if profile.has_dhw:
            result["dhw_kwh"] = round(df["dhw_kWh"].sum(), 0)
        return result
