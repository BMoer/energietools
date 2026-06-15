"""
Austrian standard load profiles (Standardlastprofile).

Generates synthetic household (H0) and heat pump (WP) consumption profiles
based on the E-Control / APCS standard load profile methodology.

The profiles are normalised to 1000 kWh/year — scale by your actual
annual consumption to get realistic values.

Example
-------
>>> from pvtool.connectors.load_profiles import LoadProfileGenerator
>>> gen = LoadProfileGenerator(annual_kwh=4500)  # typical Austrian household
>>> df = gen.generate_h0(year=2025)
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .base import BaseConnector


class LoadProfileGenerator(BaseConnector):
    """
    Generate synthetic load profiles for Austrian households.

    Parameters
    ----------
    annual_kwh : float
        Total annual consumption in kWh (default: 4500 — typical Austrian household).
    interval_minutes : int
        Output interval in minutes (default: 5 — matches PV data resolution).
    """

    def __init__(self, annual_kwh: float = 4500.0, interval_minutes: int = 5):
        self.annual_kwh = annual_kwh
        self.interval_minutes = interval_minutes

    def generate_h0(self, year: int = 2025) -> pd.DataFrame:
        """
        Generate a household (H0) load profile for a full year.

        Uses a simplified model based on:
        - Daily pattern: morning peak (7-9h), evening peak (17-21h), low at night
        - Seasonal variation: ~30% higher in winter than summer
        - Weekend effect: slightly shifted morning peak

        Returns
        -------
        pd.DataFrame with columns: timestamp, production_kWh (=0),
        consumption_kWh, surplus_kWh (= -consumption).
        """
        timestamps = pd.date_range(
            f"{year}-01-01", f"{year + 1}-01-01",
            freq=f"{self.interval_minutes}min",
            tz="UTC",
            inclusive="left",
        )

        n = len(timestamps)
        hours = np.asarray(timestamps.hour + timestamps.minute / 60.0, dtype=float)
        day_of_year = np.asarray(timestamps.dayofyear, dtype=float)
        is_weekend = np.asarray(timestamps.dayofweek >= 5)

        # Base daily profile (normalised)
        # Two peaks: morning (7-9) and evening (18-21)
        morning = np.exp(-0.5 * ((hours - 7.5) / 1.0) ** 2)
        evening = np.exp(-0.5 * ((hours - 19.0) / 1.5) ** 2)
        baseline = 0.3  # night-time base load
        daily = baseline + 0.4 * morning + 0.6 * evening

        # Weekend: shift morning peak later, reduce amplitude
        morning_we = np.exp(-0.5 * ((hours - 9.5) / 1.5) ** 2)
        daily_we = baseline + 0.3 * morning_we + 0.5 * evening
        daily = np.where(is_weekend, daily_we, daily)

        # Seasonal factor: higher in winter (peak Dec/Jan), lower in summer
        seasonal = 1.0 + 0.15 * np.cos(2 * np.pi * (day_of_year - 15) / 365)

        # Combined profile
        profile = daily * seasonal

        # Scale to annual consumption
        interval_hours = self.interval_minutes / 60.0
        raw_annual = profile.sum() * interval_hours
        scale_factor = self.annual_kwh / raw_annual
        consumption = profile * scale_factor * interval_hours

        return pd.DataFrame({
            "timestamp": timestamps,
            "production_kWh": 0.0,
            "consumption_kWh": consumption,
            "surplus_kWh": -consumption,
        })

    def generate_wp(self, year: int = 2025) -> pd.DataFrame:
        """
        Generate a heat pump (WP) load profile for a full year.

        Uses a degree-day model:
        - No heating above 15°C (assumed from seasonal temperature model)
        - Linear heating demand below 15°C
        - COP = 3.0 average (electricity = heat / COP)

        Parameters
        ----------
        year : int
            Target year.

        Returns
        -------
        pd.DataFrame with same format as generate_h0().
        """
        timestamps = pd.date_range(
            f"{year}-01-01", f"{year + 1}-01-01",
            freq=f"{self.interval_minutes}min",
            tz="UTC",
            inclusive="left",
        )

        day_of_year = np.asarray(timestamps.dayofyear, dtype=float)
        hours = np.asarray(timestamps.hour + timestamps.minute / 60.0, dtype=float)

        # Simplified temperature model for Austrian lowlands (~47°N)
        # Mean ~10°C, amplitude ~12°C, coldest mid-January
        temp_daily = 10 - 12 * np.cos(2 * np.pi * (day_of_year - 15) / 365)
        # Diurnal variation: ±3°C
        temp = temp_daily - 3 * np.cos(2 * np.pi * (hours - 14) / 24)

        # Heating demand: degree-days below 15°C
        heating_threshold = 15.0
        heat_demand = np.maximum(heating_threshold - temp, 0)

        # COP: better in mild weather, worse when cold
        cop = np.clip(2.5 + 0.05 * temp, 2.0, 4.5)
        electricity = heat_demand / cop

        # Scale to annual consumption
        interval_hours = self.interval_minutes / 60.0
        raw_annual = electricity.sum() * interval_hours
        if raw_annual > 0:
            scale_factor = self.annual_kwh / raw_annual
        else:
            scale_factor = 0
        consumption = electricity * scale_factor * interval_hours

        return pd.DataFrame({
            "timestamp": timestamps,
            "production_kWh": 0.0,
            "consumption_kWh": consumption,
            "surplus_kWh": -consumption,
        })

    def fetch_day(self, day: date) -> pd.DataFrame:
        """Generate H0 profile for a single day."""
        df = self.generate_h0(day.year)
        mask = df["timestamp"].dt.date == day
        return df[mask].reset_index(drop=True)

    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Generate H0 profile for a date range."""
        df = self.generate_h0(start.year)
        mask = (df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)
        return df[mask].reset_index(drop=True)
