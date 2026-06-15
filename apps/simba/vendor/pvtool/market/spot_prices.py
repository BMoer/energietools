"""
Austrian EPEX spot prices via aWATTar API.

Free, no API key required.
Base URL: https://api.awattar.at/v1/marketdata
Returns hourly prices in EUR/MWh for the Austrian bidding zone.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import requests


AWATTAR_URL = "https://api.awattar.at/v1/marketdata"


def fetch_awattar_prices(start: date, end: date) -> pd.DataFrame:
    """
    Fetch hourly EPEX spot prices from aWATTar for Austria.

    Parameters
    ----------
    start, end : date
        Inclusive date range.

    Returns
    -------
    pd.DataFrame with columns:
        timestamp       datetime64[ns, UTC]
        price_eur_mwh   float   — EUR/MWh
        price_eur_kwh   float   — EUR/kWh (÷ 1000)
    """
    start_ms = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    end_ms = int(end_dt.timestamp() * 1000)

    resp = requests.get(AWATTAR_URL, params={"start": start_ms, "end": end_ms}, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    rows = [
        {
            "timestamp": pd.Timestamp(item["start_timestamp"], unit="ms", tz="UTC"),
            "price_eur_mwh": item["marketprice"],
            "price_eur_kwh": item["marketprice"] / 1000.0,
        }
        for item in data
    ]
    return pd.DataFrame(rows)


def merge_spot_prices(df_pv: pd.DataFrame, df_spot: pd.DataFrame) -> pd.DataFrame:
    """
    Merge 5-minute PV data with hourly spot prices.

    Spot prices are forward-filled to match 5-minute intervals.

    Parameters
    ----------
    df_pv : pd.DataFrame
        5-minute PV data with a 'timestamp' column (timezone-aware or naive UTC).
    df_spot : pd.DataFrame
        Hourly spot prices from fetch_awattar_prices().

    Returns
    -------
    pd.DataFrame — df_pv with price_eur_mwh and price_eur_kwh columns added.
    """
    df_spot_sorted = df_spot.sort_values("timestamp").copy()

    # Normalise timezone handling
    if df_pv["timestamp"].dt.tz is None:
        df_pv = df_pv.copy()
        df_pv["timestamp"] = df_pv["timestamp"].dt.tz_localize("UTC")

    merged = pd.merge_asof(
        df_pv.sort_values("timestamp"),
        df_spot_sorted[["timestamp", "price_eur_mwh", "price_eur_kwh"]],
        on="timestamp",
        direction="backward",
    )
    return merged
