"""SolisCloud API connector — HMAC-SHA1 authenticated data fetcher."""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import time
from datetime import date

import pandas as pd
import requests
from dotenv import load_dotenv

from pvtool.connectors.base import BaseConnector

# .env lives two levels up from this file: pvtool/connectors/ → pvtool/ → Solis_API/
_ENV_PATH = pathlib.Path(__file__).resolve().parents[2] / ".env"

API_BASE = "https://www.soliscloud.com:13333"
INVERTER_PATH = "/v1/api/inverterDay"
EPM_PATH = "/v1/api/epm/day"
TIME_ZONE = 0
REQUEST_DELAY = 0.6  # seconds between API calls to stay under rate limit


class SolisConnector(BaseConnector):
    """
    Fetches 5-minute interval data from the SolisCloud API.

    Credentials are loaded from .env (SOLIS_KEY_ID, SOLIS_KEY_SECRET,
    SOLIS_SN_EAST, SOLIS_SN_WEST, SOLIS_SN_EPM).

    fetch_day() returns a DataFrame with columns:

        timestamp            datetime64[ns, UTC]
        east_production_kW   float  — East inverter pac W → kW
        west_production_kW   float  — West inverter pac W → kW
        total_production_kW  float  — East + West
        p_load_kW            float  — EPM household load W → kW
        p_epm_total_kW       float  — EPM grid total W → kW

    Plus BaseConnector standard columns (5-min interval → kWh = kW / 12):

        production_kWh       float
        consumption_kWh      float
        surplus_kWh          float  — production − consumption
    """

    def __init__(self, env_path: pathlib.Path | None = None):
        env_file = env_path or _ENV_PATH
        load_dotenv(env_file)

        self.key_id  = os.environ["SOLIS_KEY_ID"]
        self.secret  = os.environ["SOLIS_KEY_SECRET"]
        self.sn_east = os.environ["SOLIS_SN_EAST"]
        self.sn_west = os.environ["SOLIS_SN_WEST"]
        self.sn_epm  = os.environ["SOLIS_SN_EPM"]

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _gmt_date(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

    def _sign(self, body_str: str, gmt_date_str: str, api_path: str) -> tuple[str, str]:
        """Return (content_md5, signature) for a signed request."""
        content_md5 = base64.b64encode(
            hashlib.md5(body_str.encode()).digest()
        ).decode()
        string_to_sign = "\n".join([
            "POST",
            content_md5,
            "application/json",
            gmt_date_str,
            api_path,
        ])
        signature = base64.b64encode(
            hmac.new(self.secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        return content_md5, signature

    def _post(self, api_path: str, body: dict) -> dict:
        """POST to SolisCloud and return parsed JSON response."""
        body_str = json.dumps(body)
        date_hdr = self._gmt_date()
        content_md5, sig = self._sign(body_str, date_hdr, api_path)

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Date": date_hdr,
            "Content-MD5": content_md5,
            "Authorization": f"API {self.key_id}:{sig}",
        }
        r = requests.post(API_BASE + api_path, headers=headers, data=body_str, timeout=30)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Raw fetchers
    # ------------------------------------------------------------------

    def _fetch_inverter_day(self, sn: str, day: date) -> list[dict]:
        """Fetch one inverter's 5-min records for a day. Returns raw data list."""
        body = {"sn": sn, "time": day.isoformat(), "timeZone": TIME_ZONE}
        try:
            data = self._post(INVERTER_PATH, body)
            if not data.get("success"):
                print(f"API error [{sn}] {day}: {data}")
                return []
            return data.get("data", [])
        except Exception as e:
            print(f"Request failed [{sn}] {day}: {e}")
            return []

    def _fetch_epm_day(self, day: date) -> pd.DataFrame:
        """Fetch EPM data for a day. Returns tidy DataFrame or empty DataFrame on failure."""
        body = {
            "sn": self.sn_epm,
            "time": day.isoformat(),
            "timeZone": TIME_ZONE,
            "searchinfo": "p_load,p_epm_total,e_total_buy,e_total_sell",
        }
        try:
            data = self._post(EPM_PATH, body)
            if not data.get("success"):
                print(f"EPM API error {day}: {data}")
                return pd.DataFrame()
            d = data.get("data", {})
            times = d.get("timeStr", [])
            if not times:
                return pd.DataFrame()
            df = pd.DataFrame({
                "timestamp":     times,
                "p_load_W":      d.get("p_load",      [0] * len(times)),
                "p_epm_total_W": d.get("p_epm_total", [0] * len(times)),
            })
            df["p_load_kW"]      = pd.to_numeric(df["p_load_W"],      errors="coerce").fillna(0) / 1000
            df["p_epm_total_kW"] = pd.to_numeric(df["p_epm_total_W"], errors="coerce").fillna(0) / 1000
            return df[["timestamp", "p_load_kW", "p_epm_total_kW"]]
        except Exception as e:
            print(f"EPM request failed {day}: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def fetch_day(self, day: date) -> pd.DataFrame:
        """
        Fetch East + West inverters and EPM for one day.

        Makes three API calls (East, West, EPM) with REQUEST_DELAY between each.
        Returns a merged DataFrame with raw kW columns and BaseConnector standard
        columns (production_kWh, consumption_kWh, surplus_kWh).
        """
        east_data = self._fetch_inverter_day(self.sn_east, day)
        time.sleep(REQUEST_DELAY)
        west_data = self._fetch_inverter_day(self.sn_west, day)
        time.sleep(REQUEST_DELAY)
        epm_df = self._fetch_epm_day(day)
        time.sleep(REQUEST_DELAY)

        rows = []
        for e, w in zip(east_data, west_data):
            east_kw = e.get("pac", 0) / 1000
            west_kw = w.get("pac", 0) / 1000
            rows.append({
                "timestamp":           e.get("timeStr"),
                "east_production_kW":  east_kw,
                "west_production_kW":  west_kw,
                "total_production_kW": east_kw + west_kw,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        if not epm_df.empty:
            epm_df["timestamp"] = pd.to_datetime(epm_df["timestamp"], utc=True)
            # Round both to nearest 5 min — inverter and EPM timestamps are offset
            # by a few seconds and may have duplicate bins, so deduplicate after rounding.
            df["timestamp"] = df["timestamp"].dt.round("5min")
            epm_df["timestamp"] = epm_df["timestamp"].dt.round("5min")
            epm_df = epm_df.drop_duplicates(subset="timestamp", keep="first")
            df = df.drop_duplicates(subset="timestamp", keep="first")
            df = df.merge(epm_df, on="timestamp", how="left")
            df["p_load_kW"]      = df["p_load_kW"].fillna(0)
            df["p_epm_total_kW"] = df["p_epm_total_kW"].fillna(0)
        else:
            df["p_load_kW"]      = 0.0
            df["p_epm_total_kW"] = 0.0

        # BaseConnector standard columns — 5-min interval: kW / 12 = kWh
        df["production_kWh"]  = df["total_production_kW"] / 12
        df["consumption_kWh"] = df["p_load_kW"] / 12
        df["surplus_kWh"]     = df["production_kWh"] - df["consumption_kWh"]

        return df

    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Fetch and concatenate all days in [start, end]."""
        frames = []
        current = start
        while current <= end:
            print(f"Fetching {current}…")
            df_day = self.fetch_day(current)
            if not df_day.empty:
                frames.append(df_day)
            current += datetime.timedelta(days=1)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
