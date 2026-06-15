"""
Austrian balancing energy prices from ENTSO-E Transparency Platform.

Fetches historical settlement prices for activated balancing energy in the
Austrian control area (APG — 10YAT-APG------L).

These are the prices paid/received for actual energy delivered during
balancing activations.  For FCR/aFRR/mFRR **capacity** prices (what
providers earn for availability), use the configurable
``fcr_revenue_eur_per_kw_year`` in ``MarketConfig`` — those come from
the FCR cooperation platform (regelleistung.net) and are not available
via the standard ENTSO-E REST API.

Requires a free API key from https://transparency.entsoe.eu/

ENTSO-E REST API details
------------------------
Base URL : https://web-api.tp.entsoe.eu/api
Auth     : securityToken query parameter
Response : XML (Publication_MarketDocument)

Endpoint used:
  documentType = A44  (Price of activated balancing energy)
  in_Domain / out_Domain = 10YAT-APG------L
  processType  = A16  (Realised — actual settlement prices)

The response contains TimeSeries with:
  classificationSequence position=1 → hourly prices (PT60M)
  classificationSequence position=2 → quarter-hourly prices (PT15M)
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pandas as pd
import requests

ENTSOE_BASE_URL = "https://web-api.tp.entsoe.eu/api"
AUSTRIA_DOMAIN = "10YAT-APG------L"  # APG control area EIC

# Max date range per ENTSO-E query (~1 year)
_MAX_QUERY_DAYS = 366


def _fmt_dt(d: date) -> str:
    """Format a date as ENTSO-E periodStart/periodEnd (YYYYMMdd0000)."""
    return f"{d.year:04d}{d.month:02d}{d.day:02d}0000"


def _iso_duration_to_timedelta(iso: str) -> pd.Timedelta:
    """Convert ISO 8601 duration to Timedelta."""
    iso = iso.strip()
    mapping = {
        "PT15M": pd.Timedelta(minutes=15),
        "PT30M": pd.Timedelta(minutes=30),
        "PT60M": pd.Timedelta(hours=1),
        "PT1H": pd.Timedelta(hours=1),
        "PT4H": pd.Timedelta(hours=4),
        "P1D": pd.Timedelta(days=1),
    }
    return mapping.get(iso, pd.Timedelta(hours=1))


def _parse_publication_xml(xml_text: str, resolution_filter: str | None = None) -> list[dict]:
    """
    Parse ENTSO-E Publication_MarketDocument XML into price rows.

    Parameters
    ----------
    xml_text : str
        Raw XML response.
    resolution_filter : str, optional
        If set (e.g. 'PT60M'), only include TimeSeries with this resolution.
        Default: include all.

    Returns
    -------
    list of {timestamp, price_eur_mwh, resolution} dicts.
    """
    rows = []
    root = ET.fromstring(xml_text)

    # Use wildcard namespace — ENTSO-E uses varying namespace URIs
    for ts in root.findall(".//{*}TimeSeries"):
        # Get classification position (1=hourly, 2=quarter-hourly)
        cls_elem = ts.find("{*}classificationSequence_AttributeInstanceComponent.position")
        cls_pos = int(cls_elem.text) if cls_elem is not None else 0

        for period in ts.findall(".//{*}Period"):
            # Parse interval start
            start_elem = period.find(".//{*}start")
            if start_elem is None:
                continue
            period_start = pd.Timestamp(start_elem.text)

            # Parse resolution
            res_elem = period.find("{*}resolution")
            resolution = res_elem.text.strip() if res_elem is not None else "PT60M"

            if resolution_filter and resolution != resolution_filter:
                continue

            freq = _iso_duration_to_timedelta(resolution)

            # Parse price points
            for point in period.findall("{*}Point"):
                pos_elem = point.find("{*}position")
                price_elem = point.find("{*}price.amount")
                if pos_elem is None or price_elem is None:
                    continue
                position = int(pos_elem.text)
                price = float(price_elem.text)
                timestamp = period_start + (position - 1) * freq
                rows.append({
                    "timestamp": timestamp,
                    "price_eur_mwh": price,
                    "resolution": resolution,
                    "classification": cls_pos,
                })

    return rows


def fetch_balancing_prices(
    start: date,
    end: date,
    api_key: str | None = None,
    domain: str = AUSTRIA_DOMAIN,
    resolution: str = "PT60M",
) -> pd.DataFrame:
    """
    Fetch Austrian balancing energy settlement prices from ENTSO-E.

    Parameters
    ----------
    start, end : date
        Inclusive date range.
    api_key : str, optional
        ENTSO-E security token. Falls back to ENTSOE_API_KEY env var.
    domain : str
        Control area EIC code (default: Austrian APG).
    resolution : str
        'PT60M' for hourly (default) or 'PT15M' for quarter-hourly.

    Returns
    -------
    pd.DataFrame with columns:
        timestamp        datetime64[ns, UTC]
        price_eur_mwh    float  — settlement price in EUR/MWh
        price_eur_kwh    float  — EUR/kWh (÷ 1000)
    """
    if api_key is None:
        api_key = os.environ.get("ENTSOE_API_KEY")
    if not api_key:
        raise ValueError(
            "No ENTSO-E API key. Set ENTSOE_API_KEY in .env or pass api_key=."
        )

    # Split into chunks if range exceeds max query size
    chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=_MAX_QUERY_DAYS), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end

    all_rows = []
    for c_start, c_end in chunks:
        # ENTSO-E periodEnd is exclusive, add 1 day
        params = {
            "securityToken": api_key,
            "documentType": "A44",
            "processType": "A16",
            "in_Domain": domain,
            "out_Domain": domain,
            "periodStart": _fmt_dt(c_start),
            "periodEnd": _fmt_dt(c_end + timedelta(days=1)),
        }

        resp = requests.get(ENTSOE_BASE_URL, params=params, timeout=60)

        if resp.status_code == 401:
            raise PermissionError(
                "ENTSO-E API key rejected (401). Check your key or wait for activation."
            )
        if resp.status_code == 400:
            if "No matching data found" in resp.text:
                continue
            _raise_entsoe_error(resp)
        resp.raise_for_status()

        all_rows.extend(_parse_publication_xml(resp.text, resolution_filter=resolution))

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "price_eur_mwh", "price_eur_kwh"])

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["price_eur_kwh"] = df["price_eur_mwh"] / 1000.0
    df = df.drop(columns=["resolution", "classification"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _raise_entsoe_error(resp: requests.Response) -> None:
    """Extract error reason from ENTSO-E XML and raise."""
    try:
        root = ET.fromstring(resp.text)
        reason = root.find(".//{*}text")
        msg = reason.text if reason is not None else resp.text[:500]
    except ET.ParseError:
        msg = resp.text[:500]
    raise requests.HTTPError(f"ENTSO-E returned {resp.status_code}: {msg}", response=resp)


def summarise_balancing_prices(df: pd.DataFrame) -> dict:
    """
    Compute summary statistics from a balancing-price DataFrame.

    Returns
    -------
    dict with keys: days, count, mean_eur_mwh, median_eur_mwh,
    min_eur_mwh, max_eur_mwh, std_eur_mwh
    """
    if df.empty:
        return {"days": 0, "count": 0}

    prices = df["price_eur_mwh"]
    n_days = (df["timestamp"].max() - df["timestamp"].min()).days + 1

    return {
        "days": n_days,
        "count": len(df),
        "mean_eur_mwh": round(prices.mean(), 2),
        "median_eur_mwh": round(prices.median(), 2),
        "min_eur_mwh": round(prices.min(), 2),
        "max_eur_mwh": round(prices.max(), 2),
        "std_eur_mwh": round(prices.std(), 2),
    }
