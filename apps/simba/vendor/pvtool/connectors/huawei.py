"""Huawei FusionSolar Northbound API connector — session-based data fetcher.

Authentication
--------------
POST /thirdData/login with userName + systemCode.
The server returns an ``xsrf-token`` in the response headers; this token
is included as a header in every subsequent request.
Token has a 30-minute idle timeout.  Error code 305 triggers automatic
re-login (single retry).

Device discovery
----------------
On the first fetch_day() call the connector auto-discovers:
  - Station code (HUAWEI_STATION_CODE in .env, or first station returned)
  - Inverter device ID (devTypeId 1)
  - Grid meter / power sensor device ID (devTypeId 17 or 47)

You can skip discovery by setting HUAWEI_STATION_CODE,
HUAWEI_INVERTER_DEV_ID, HUAWEI_INVERTER_DEV_TYPE,
HUAWEI_METER_DEV_ID, HUAWEI_METER_DEV_TYPE in .env.

Output columns (BaseConnector standard)
----------------------------------------
timestamp           datetime64[ns, UTC]
production_kWh      float  — inverter active_power kW * dt_hours
consumption_kWh     float  — meter load kW * dt_hours
surplus_kWh         float  — production - consumption
active_power_kw     float  — inverter active power (kW)
meter_power_kw      float  — grid meter active power (+import, -export)
"""

from __future__ import annotations

import datetime
import os
import pathlib
import time
from datetime import date

import pandas as pd
import requests
from dotenv import load_dotenv

from pvtool.connectors.base import BaseConnector

# .env lives two levels up from this file: pvtool/connectors/ -> pvtool/ -> Solis_API/
_ENV_PATH = pathlib.Path(__file__).resolve().parents[2] / ".env"

REQUEST_DELAY = 0.6   # seconds between API calls
_DEV_TYPE_INVERTER = 1   # String inverter
_DEV_TYPE_METER    = 17  # Grid meter (also try 47 = power sensor if 17 absent)
_DEV_TYPE_SENSOR   = 47  # Power sensor / smart energy sensor


class HuaweiConnector(BaseConnector):
    """
    Fetches 5-minute interval data from the FusionSolar Northbound API.

    Credentials are loaded from .env:
        HUAWEI_USER              — Northbound API username
        HUAWEI_SYSTEM_CODE       — Northbound API password
        HUAWEI_BASE_URL          — e.g. https://eu5.fusionsolar.huawei.com
        HUAWEI_STATION_CODE      — (optional) station code; auto-discovered if absent
        HUAWEI_INVERTER_DEV_ID   — (optional) inverter device ID; auto-discovered
        HUAWEI_INVERTER_DEV_TYPE — (optional) inverter devTypeId; default 1
        HUAWEI_METER_DEV_ID      — (optional) meter/sensor device ID; auto-discovered
        HUAWEI_METER_DEV_TYPE    — (optional) meter devTypeId; default 17
    """

    _PATH = "/thirdData"

    def __init__(self, env_path: pathlib.Path | None = None):
        env_file = env_path or _ENV_PATH
        load_dotenv(env_file)

        self._user         = os.environ["HUAWEI_USER"]
        self._system_code  = os.environ["HUAWEI_SYSTEM_CODE"]
        self._base_url     = os.environ["HUAWEI_BASE_URL"].rstrip("/")

        # Optional pre-configured IDs (skip auto-discovery if set)
        self._station_code      = os.environ.get("HUAWEI_STATION_CODE")
        self._inverter_dev_id   = os.environ.get("HUAWEI_INVERTER_DEV_ID")
        self._inverter_dev_type = int(os.environ.get("HUAWEI_INVERTER_DEV_TYPE", _DEV_TYPE_INVERTER))
        self._meter_dev_id      = os.environ.get("HUAWEI_METER_DEV_ID")
        self._meter_dev_type    = int(os.environ.get("HUAWEI_METER_DEV_TYPE", _DEV_TYPE_METER))

        self._token: str | None = None
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _login(self) -> None:
        """Log in and store the xsrf-token from the response header."""
        url = f"{self._base_url}{self._PATH}/login"
        payload = {"userName": self._user, "systemCode": self._system_code}
        try:
            r = self._session.post(url, json=payload, timeout=30)
            r.raise_for_status()
            body = r.json()
            if not body.get("success", True) and body.get("failCode") not in (None, 0):
                raise RuntimeError(f"FusionSolar login failed: {body}")
            # Token arrives in response headers (case-insensitive)
            token = r.headers.get("xsrf-token") or r.headers.get("XSRF-TOKEN")
            if not token:
                raise RuntimeError("FusionSolar login succeeded but xsrf-token not found in headers.")
            self._token = token
            self._session.headers.update({"xsrf-token": token})
        except requests.RequestException as e:
            raise RuntimeError(f"FusionSolar login request failed: {e}") from e

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, body: dict, *, _retry: bool = True) -> dict:
        """POST to a /thirdData endpoint.  Auto-logins and retries once on 305."""
        if self._token is None:
            self._login()

        url = f"{self._base_url}{self._PATH}/{endpoint}"
        r = self._session.post(url, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()

        # Error code 305 = session expired; re-login and retry once
        if data.get("failCode") == 305 and _retry:
            self._token = None
            self._login()
            return self._post(endpoint, body, _retry=False)

        if not data.get("success", True):
            print(f"FusionSolar API warning [{endpoint}]: {data.get('message', data)}")

        return data

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def _ensure_station(self) -> None:
        """Resolve station code if not already set."""
        if self._station_code:
            return
        data = self._post("getStationList", {})
        stations = data.get("data", {}).get("list", [])
        if not stations:
            raise RuntimeError("FusionSolar: no stations returned. Check account permissions.")
        self._station_code = stations[0]["stationCode"]
        print(f"FusionSolar: auto-discovered station {self._station_code}")

    def _ensure_devices(self) -> None:
        """Resolve inverter and meter device IDs from the device list."""
        if self._inverter_dev_id and self._meter_dev_id:
            return

        self._ensure_station()
        data = self._post("getDevList", {"stationCodes": self._station_code})
        devices = data.get("data", [])

        inverters = [d for d in devices if d.get("devTypeId") == _DEV_TYPE_INVERTER]
        meters    = [d for d in devices if d.get("devTypeId") in (_DEV_TYPE_METER, _DEV_TYPE_SENSOR)]

        if not self._inverter_dev_id:
            if not inverters:
                raise RuntimeError("FusionSolar: no inverter (devTypeId=1) found on this station.")
            # Combine all inverter IDs if multiple (comma-separated for the API)
            self._inverter_dev_id   = ",".join(str(d["devDn"]) for d in inverters)
            self._inverter_dev_type = inverters[0]["devTypeId"]
            print(f"FusionSolar: auto-discovered inverter(s) {self._inverter_dev_id}")

        if not self._meter_dev_id:
            if not meters:
                print("FusionSolar: no grid meter found — consumption data will be unavailable.")
                self._meter_dev_id   = None
                self._meter_dev_type = _DEV_TYPE_METER
            else:
                self._meter_dev_id   = str(meters[0]["devDn"])
                self._meter_dev_type = meters[0]["devTypeId"]
                print(f"FusionSolar: auto-discovered meter {self._meter_dev_id} (devTypeId={self._meter_dev_type})")

    # ------------------------------------------------------------------
    # Raw KPI fetch
    # ------------------------------------------------------------------

    @staticmethod
    def _day_to_ms(day: date) -> int:
        """Convert a date to milliseconds since epoch (midnight UTC)."""
        dt = datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1000)

    def _fetch_dev_history_kpi(
        self, dev_id: str, dev_type_id: int, day: date
    ) -> list[dict]:
        """
        Fetch 5-minute historical KPI for a device.

        Returns a list of records:
            {"collectTime": <ms>, "dataItemMap": {"active_power": ..., ...}}
        """
        body = {
            "devIds":    dev_id,
            "devTypeId": dev_type_id,
            "collectTime": self._day_to_ms(day),
        }
        data = self._post("getDevHistoryKpi", body)
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Data parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_kw(record: dict, *keys: str) -> float:
        """Extract a power value (kW) from dataItemMap, trying keys in order."""
        item = record.get("dataItemMap", {})
        for k in keys:
            v = item.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0

    @staticmethod
    def _ms_to_utc(ms: int) -> pd.Timestamp:
        return pd.Timestamp(ms, unit="ms", tz="UTC")

    def _parse_inverter_records(self, records: list[dict]) -> pd.DataFrame:
        rows = []
        for r in records:
            ts = self._ms_to_utc(r["collectTime"])
            kw = self._extract_kw(r, "active_power", "activePower", "mppt_power", "currentPower")
            rows.append({"timestamp": ts, "active_power_kw": kw})
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["timestamp", "active_power_kw"])

    def _parse_meter_records(self, records: list[dict]) -> pd.DataFrame:
        """
        Meter active_power: positive = importing from grid, negative = exporting.
        Consumption = max(0, meter_power).
        """
        rows = []
        for r in records:
            ts = self._ms_to_utc(r["collectTime"])
            kw = self._extract_kw(r, "active_power", "activePower", "p_load", "currentPower")
            rows.append({"timestamp": ts, "meter_power_kw": kw})
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["timestamp", "meter_power_kw"])

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def fetch_day(self, day: date) -> pd.DataFrame:
        """
        Fetch inverter + meter data for one calendar day.

        Returns a DataFrame with standard BaseConnector columns plus raw kW columns.
        5-minute interval: kW / 12 = kWh.
        """
        self._ensure_devices()

        inv_records = self._fetch_dev_history_kpi(
            self._inverter_dev_id, self._inverter_dev_type, day
        )
        time.sleep(REQUEST_DELAY)

        df_inv = self._parse_inverter_records(inv_records)

        if self._meter_dev_id:
            meter_records = self._fetch_dev_history_kpi(
                self._meter_dev_id, self._meter_dev_type, day
            )
            time.sleep(REQUEST_DELAY)
            df_meter = self._parse_meter_records(meter_records)
        else:
            df_meter = pd.DataFrame(columns=["timestamp", "meter_power_kw"])

        if df_inv.empty:
            return pd.DataFrame()

        # Merge on timestamp (left join — inverter is primary)
        if not df_meter.empty:
            df = df_inv.merge(df_meter, on="timestamp", how="left")
            df["meter_power_kw"] = df["meter_power_kw"].fillna(0.0)
        else:
            df = df_inv.copy()
            df["meter_power_kw"] = 0.0

        # BaseConnector standard columns — 5-min interval: kW / 12 = kWh
        dt_hours = 5.0 / 60.0
        df["production_kWh"]  = df["active_power_kw"].clip(lower=0) * dt_hours
        # Consumption = grid import + inverter production - grid export
        # Approximation when meter shows net grid flow:
        #   consumption = production + max(meter_power, 0)  [import case]
        # For net metering: consumption = production + meter_power (can be negative = export)
        # We model: consumption_kW = production_kW + meter_power_kW (net import)
        # Then clip to >=0 in case of measurement noise
        df["consumption_kWh"] = (
            (df["active_power_kw"] + df["meter_power_kw"]).clip(lower=0) * dt_hours
        )
        df["surplus_kWh"] = df["production_kWh"] - df["consumption_kWh"]

        return df[["timestamp", "production_kWh", "consumption_kWh", "surplus_kWh",
                   "active_power_kw", "meter_power_kw"]]

    def fetch_range(self, start: date, end: date) -> pd.DataFrame:
        """Fetch and concatenate all days in [start, end]."""
        frames = []
        current = start
        while current <= end:
            print(f"Fetching {current}...")
            df_day = self.fetch_day(current)
            if not df_day.empty:
                frames.append(df_day)
            current += datetime.timedelta(days=1)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
