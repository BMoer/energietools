"""
PVGIS connector — synthetic PV generation data from the EU Joint Research Centre.

Free API, no key required. Provides typical-year hourly PV output for any
location in Europe, Africa, and parts of Asia.

API documentation: https://re.jrc.ec.europa.eu/pvg_tools/en/

Example
-------
>>> from pvtool.connectors.pvgis import PvgisConnector
>>> conn = PvgisConnector(lat=47.07, lon=15.44, peakpower=10)  # Graz, 10 kWp
>>> df = conn.fetch_typical_year()
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from .base import BaseConnector

PVGIS_API_URL = "https://re.jrc.ec.europa.eu/api/v5_2"


class PvgisConnector(BaseConnector):
    """
    Fetch synthetic PV generation data from EU PVGIS API.

    Parameters
    ----------
    lat, lon : float
        Location coordinates (decimal degrees).
    peakpower : float
        Installed PV peak power in kWp.
    loss : float
        System losses in % (default: 14 — typical for residential).
    angle : float
        Panel tilt angle in degrees (default: 35).
    aspect : float
        Panel azimuth: 0=south, -90=east, 90=west (default: 0).
    pvtechwear : str
        PV technology: 'crystSi', 'CIS', 'CdTe' (default: 'crystSi').
    database : str
        Solar radiation database: 'PVGIS-SARAH2' (default), 'PVGIS-ERA5'.
    """

    def __init__(
        self,
        lat: float = 47.07,
        lon: float = 15.44,
        peakpower: float = 10.0,
        loss: float = 14.0,
        angle: float = 35.0,
        aspect: float = 0.0,
        pvtechwear: str = "crystSi",
        database: str = "PVGIS-SARAH2",
    ):
        self.lat = lat
        self.lon = lon
        self.peakpower = peakpower
        self.loss = loss
        self.angle = angle
        self.aspect = aspect
        self.pvtechwear = pvtechwear
        self.database = database

    def fetch_typical_year(self) -> pd.DataFrame:
        """
        Fetch a typical meteorological year of hourly PV output.

        Returns
        -------
        pd.DataFrame with columns:
            timestamp        datetime64[ns, UTC]
            production_kWh   float  — PV output per hour (kWh)
            consumption_kWh  float  — zero (no load data from PVGIS)
            surplus_kWh      float  — same as production_kWh
            ghi_wm2          float  — Global Horizontal Irradiance (W/m²)
            temperature_c    float  — ambient temperature (°C)
        """
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "peakpower": self.peakpower,
            "loss": self.loss,
            "angle": self.angle,
            "aspect": self.aspect,
            "pvtechwear": self.pvtechwear,
            "raddatabase": self.database,
            "outputformat": "json",
        }

        resp = requests.get(f"{PVGIS_API_URL}/seriescalc", params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        hourly = data["outputs"]["hourly"]
        rows = []
        for item in hourly:
            # PVGIS returns timestamps like "20050101:0010"
            raw_time = item["time"]
            if len(raw_time) == 13 and raw_time[8] == ":":
                raw_time = f"{raw_time[:4]}-{raw_time[4:6]}-{raw_time[6:8]} {raw_time[9:11]}:{raw_time[11:13]}"
            ts = pd.Timestamp(raw_time, tz="UTC")
            # P = direct PV output (W) if available, else compute from irradiance
            if "P" in item and item["P"] > 0:
                pv_kwh = item["P"] / 1000.0
            else:
                # G(i) = irradiance on tilted plane (W/m²)
                # PV output = peakpower * G(i)/1000 * (1 - loss/100)
                gi = item.get("G(i)", 0)
                pv_kwh = self.peakpower * gi / 1000.0 * (1 - self.loss / 100.0)
            rows.append({
                "timestamp": ts,
                "production_kWh": pv_kwh,
                "consumption_kWh": 0.0,
                "surplus_kWh": pv_kwh,
                "ghi_wm2": item.get("G(i)", 0),
                "temperature_c": item.get("T2m", 0),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    def fetch_day(self, day: date) -> pd.DataFrame:
        """Fetch typical year, then filter to matching month+day."""
        df = self.fetch_typical_year()
        mask = (df["timestamp"].dt.month == day.month) & (df["timestamp"].dt.day == day.day)
        return df[mask].reset_index(drop=True)

    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Fetch typical year, then filter to a date range by month+day."""
        df = self.fetch_typical_year()
        # Map to month-day for typical year matching
        md = df["timestamp"].dt.strftime("%m-%d")
        start_md = f"{start.month:02d}-{start.day:02d}"
        end_md = f"{end.month:02d}-{end.day:02d}"
        if start_md <= end_md:
            mask = (md >= start_md) & (md <= end_md)
        else:
            # Wraps around year boundary (e.g., Nov to Feb)
            mask = (md >= start_md) | (md <= end_md)
        return df[mask].reset_index(drop=True)

    def fetch_monthly_summary(self) -> pd.DataFrame:
        """
        Fetch monthly average PV production summary.

        Returns
        -------
        pd.DataFrame with columns: month, production_kwh_per_day,
        irradiance_kwh_m2_per_day
        """
        params = {
            "lat": self.lat,
            "lon": self.lon,
            "peakpower": self.peakpower,
            "loss": self.loss,
            "angle": self.angle,
            "aspect": self.aspect,
            "raddatabase": self.database,
            "outputformat": "json",
        }

        resp = requests.get(f"{PVGIS_API_URL}/PVcalc", params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        months = data["outputs"]["monthly"]["fixed"]
        rows = []
        for m in months:
            rows.append({
                "month": m["month"],
                "production_kwh_per_day": m["E_d"],
                "production_kwh_per_month": m["E_m"],
                "irradiance_kwh_m2_per_day": m["H(i)_d"],
                "irradiance_kwh_m2_per_month": m["H(i)_m"],
            })

        return pd.DataFrame(rows)

    def system_info(self) -> dict:
        """Return a summary of the configured PV system."""
        return {
            "location": f"{self.lat}°N, {self.lon}°E",
            "peakpower_kwp": self.peakpower,
            "tilt_deg": self.angle,
            "azimuth_deg": self.aspect,
            "technology": self.pvtechwear,
            "losses_pct": self.loss,
            "database": self.database,
        }
