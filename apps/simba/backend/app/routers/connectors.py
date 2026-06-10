"""Data connector endpoints — Solis, PVGIS, data summary, profile analysis."""

import datetime
import json
import os
from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import LoadProfileParams

router = APIRouter(tags=["connectors"])


# --- Solis Cloud ---


class SolisCredentials(BaseModel):
    """SolisCloud API credentials."""
    key_id: str
    key_secret: str
    sn_east: str
    sn_west: str
    sn_epm: str
    start_date: date
    end_date: date


@router.get("/connect/solis/defaults")
def solis_defaults():
    """Vorbefüllung des Solis-Formulars — OHNE das Secret im Klartext zurückzugeben.

    Sicherheitsfix: ``key_secret`` wird nie ausgeliefert; das Frontend erfährt nur,
    OB ein Secret hinterlegt ist (``has_key_secret``) und füllt das Feld sonst leer.
    """
    return {
        "key_id": os.environ.get("SOLIS_KEY_ID", ""),
        "has_key_secret": bool(os.environ.get("SOLIS_KEY_SECRET", "")),
        "sn_east": os.environ.get("SOLIS_SN_EAST", ""),
        "sn_west": os.environ.get("SOLIS_SN_WEST", ""),
        "sn_epm": os.environ.get("SOLIS_SN_EPM", ""),
    }


def _validate_solis_data(df: pd.DataFrame, start: date, end: date) -> dict:
    """Validate fetched Solis data and return quality report."""
    total_days = (end - start).days + 1
    df["_date"] = pd.to_datetime(df["timestamp"]).dt.date
    fetched_dates = set(df["_date"].unique())
    expected_dates = {start + datetime.timedelta(days=i) for i in range(total_days)}
    missing_dates = sorted(expected_dates - fetched_dates)
    intervals_per_day = 288  # 5-min intervals = 24*60/5

    # Per-day row counts
    day_counts = df.groupby("_date").size()
    sparse_days = sorted(
        str(d) for d, c in day_counts.items() if c < intervals_per_day * 0.5
    )

    # Column quality
    col_quality = {}
    for col in ["production_kWh", "consumption_kWh", "total_production_kW", "p_load_kW"]:
        if col not in df.columns:
            continue
        s = df[col]
        col_quality[col] = {
            "null_count": int(s.isna().sum()),
            "zero_pct": round((s == 0).sum() / len(s) * 100, 1),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "mean": round(float(s.mean()), 4),
        }

    # Energy totals
    total_prod = round(df["production_kWh"].sum(), 1) if "production_kWh" in df.columns else 0
    total_cons = round(df["consumption_kWh"].sum(), 1) if "consumption_kWh" in df.columns else 0

    df.drop(columns=["_date"], inplace=True)

    return {
        "total_days_requested": total_days,
        "days_with_data": len(fetched_dates),
        "missing_days": [str(d) for d in missing_dates],
        "sparse_days": sparse_days,
        "total_rows": len(df),
        "expected_rows": total_days * intervals_per_day,
        "coverage_pct": round(len(df) / (total_days * intervals_per_day) * 100, 1),
        "total_production_kwh": total_prod,
        "total_consumption_kwh": total_cons,
        "column_quality": col_quality,
    }


@router.post("/connect/solis")
def fetch_solis(creds: SolisCredentials):
    """Fetch data from SolisCloud API with SSE progress streaming."""
    # Set env vars for SolisConnector
    os.environ["SOLIS_KEY_ID"] = creds.key_id
    os.environ["SOLIS_KEY_SECRET"] = creds.key_secret
    os.environ["SOLIS_SN_EAST"] = creds.sn_east
    os.environ["SOLIS_SN_WEST"] = creds.sn_west
    os.environ["SOLIS_SN_EPM"] = creds.sn_epm

    def event_stream():
        from pvtool.connectors.solis import SolisConnector

        try:
            connector = SolisConnector()
        except KeyError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Missing credential: {e}'})}\n\n"
            return

        total_days = (creds.end_date - creds.start_date).days + 1
        frames = []
        current = creds.start_date

        yield f"data: {json.dumps({'type': 'start', 'total_days': total_days})}\n\n"

        day_num = 0
        while current <= creds.end_date:
            day_num += 1
            yield f"data: {json.dumps({'type': 'progress', 'day': day_num, 'total': total_days, 'date': str(current)})}\n\n"

            try:
                df_day = connector.fetch_day(current)
                rows = len(df_day) if not df_day.empty else 0
                if not df_day.empty:
                    frames.append(df_day)
                yield f"data: {json.dumps({'type': 'day_done', 'day': day_num, 'date': str(current), 'rows': rows})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'day_error', 'day': day_num, 'date': str(current), 'error': str(e)})}\n\n"

            current += datetime.timedelta(days=1)

        if not frames:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No data returned for the given date range.'})}\n\n"
            return

        df = pd.concat(frames, ignore_index=True)

        # Validate
        validation = _validate_solis_data(df, creds.start_date, creds.end_date)

        # Save
        data_id = f"solis_{creds.start_date}_{creds.end_date}.csv"
        save_path = os.path.join(settings.upload_dir, data_id)
        os.makedirs(settings.upload_dir, exist_ok=True)
        df.to_csv(save_path, index=False)

        yield f"data: {json.dumps({'type': 'complete', 'data_id': data_id, 'rows': len(df), 'columns': list(df.columns), 'date_range': f'{creds.start_date} to {creds.end_date}', 'validation': validation})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- ENTSO-E (balancing prices as data source) ---


class EntsoeRequest(BaseModel):
    """Request to fetch and save ENTSO-E balancing prices."""
    start_date: date
    end_date: date


@router.post("/connect/entsoe")
def fetch_entsoe(req: EntsoeRequest):
    """Fetch balancing prices from ENTSO-E and save as dataset."""
    try:
        from pvtool.market.regelenergie import fetch_balancing_prices

        df = fetch_balancing_prices(req.start_date, req.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ENTSO-E API error: {e}")

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail="No data returned. Settlement prices are published with a 1-2 day delay.",
        )

    data_id = f"entsoe_{req.start_date}_{req.end_date}.csv"
    save_path = os.path.join(settings.upload_dir, data_id)
    os.makedirs(settings.upload_dir, exist_ok=True)
    df.to_csv(save_path, index=False)

    return {
        "data_id": data_id,
        "rows": len(df),
        "columns": list(df.columns),
        "date_range": f"{req.start_date} to {req.end_date}",
        "message": f"Fetched {len(df)} rows.",
    }


# --- PVGIS (synthetic PV data) ---


class PvgisRequest(BaseModel):
    """Request for synthetic PV generation + composable load profile."""
    # PV system
    lat: float = Field(default=47.07, description="Latitude")
    lon: float = Field(default=15.44, description="Longitude")
    peakpower: float = Field(default=10.0, description="PV peak power in kWp")
    angle: float = Field(default=35.0, description="Panel tilt angle")
    aspect: float = Field(default=0.0, description="Azimuth: 0=south, -90=east, 90=west")

    # Load profile (composable)
    load: LoadProfileParams = Field(default_factory=LoadProfileParams)


@router.post("/connect/pvgis")
def fetch_pvgis(req: PvgisRequest):
    """Generate synthetic PV + composable load data via EU PVGIS API."""
    try:
        from pvtool.connectors.load_builder import EVProfile, LoadBuilder, LoadProfile
        from pvtool.connectors.pvgis import PvgisConnector

        # --- PV production from PVGIS ---
        pvgis = PvgisConnector(
            lat=req.lat, lon=req.lon,
            peakpower=req.peakpower,
            angle=req.angle, aspect=req.aspect,
        )
        df_pv = pvgis.fetch_typical_year()

        # PVGIS returns multiple years — use the most recent complete year
        df_pv["year"] = df_pv["timestamp"].dt.year
        available_years = sorted(df_pv["year"].unique())
        # Use second-to-last year (last may be incomplete)
        use_year = available_years[-2] if len(available_years) > 1 else available_years[0]
        df_pv = df_pv[df_pv["year"] == use_year].drop(columns=["year"]).reset_index(drop=True)

        # Detect PVGIS interval (typically 10-min or hourly)
        if len(df_pv) > 1:
            dt_minutes = int((df_pv["timestamp"].iloc[1] - df_pv["timestamp"].iloc[0]).total_seconds() / 60)
        else:
            dt_minutes = 60

        # --- Composable load profile ---
        lp = req.load
        ev_profile = EVProfile(
            daily_km=lp.ev.daily_km,
            consumption_kwh_per_100km=lp.ev.consumption_kwh_per_100km,
            battery_kwh=lp.ev.battery_kwh,
            charging_power_kw=lp.ev.charging_power_kw,
            charging_start_hour=lp.ev.charging_start_hour,
            charging_end_hour=lp.ev.charging_end_hour,
            weekend_factor=lp.ev.weekend_factor,
        )
        load_profile = LoadProfile(
            household_annual_kwh=lp.household_annual_kwh,
            has_heatpump=lp.has_heatpump,
            hp_annual_thermal_kwh=lp.hp_annual_thermal_kwh,
            hp_inlet_temp_c=lp.hp_inlet_temp_c,
            hp_bivalent_point_c=lp.hp_bivalent_point_c,
            has_ev=lp.has_ev,
            ev=ev_profile,
            has_dhw=lp.has_dhw,
            dhw_annual_kwh=lp.dhw_annual_kwh,
            interval_minutes=dt_minutes,
        )

        builder = LoadBuilder()
        df_load = builder.generate(load_profile, year=use_year)

        # Merge PV production + load consumption (with per-component columns)
        # PVGIS timestamps may be offset (e.g. :10 instead of :00) — round both to nearest hour
        df_pv = df_pv.copy()
        df_pv["merge_ts"] = df_pv["timestamp"].dt.round("h")
        df_load = df_load.copy()
        df_load["merge_ts"] = df_load["timestamp"].dt.round("h")

        # Include per-component columns in the merge
        load_cols = ["merge_ts", "consumption_kWh", "household_kWh"]
        if load_profile.has_heatpump:
            load_cols.append("hp_electricity_kWh")
        if load_profile.has_ev:
            load_cols.append("ev_kWh")
        if load_profile.has_dhw:
            load_cols.append("dhw_kWh")

        df = pd.merge(
            df_pv[["timestamp", "production_kWh", "merge_ts"]],
            df_load[load_cols],
            on="merge_ts", how="left",
        ).drop(columns=["merge_ts"])
        df["consumption_kWh"] = df["consumption_kWh"].fillna(0)
        df["surplus_kWh"] = df["production_kWh"] - df["consumption_kWh"]

        # Get load summary
        load_summary = builder.summary(load_profile, year=use_year)

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PVGIS error: {e}")

    # Save
    components = ["pv"]
    if lp.has_heatpump:
        components.append("hp")
    if lp.has_ev:
        components.append("ev")
    if lp.has_dhw:
        components.append("dhw")
    data_id = f"pvgis_{req.lat:.2f}_{req.lon:.2f}_{req.peakpower}kWp_{'_'.join(components)}.csv"
    save_path = os.path.join(settings.upload_dir, data_id)
    os.makedirs(settings.upload_dir, exist_ok=True)
    df.to_csv(save_path, index=False)

    return {
        "data_id": data_id,
        "rows": len(df),
        "columns": list(df.columns),
        "location": f"{req.lat:.2f}N, {req.lon:.2f}E",
        "peakpower_kwp": req.peakpower,
        "load_summary": load_summary,
        "message": f"Generated {len(df)} rows. Use data_source='{data_id}' in /api/simulate.",
    }


# --- Data summary ---


@router.get("/data/summary")
def data_summary(data_source: str = "sample"):
    """Return summary statistics for a loaded dataset."""
    if data_source == "sample":
        path = os.path.join(settings.data_dir, "sample.csv")
    else:
        path = os.path.join(settings.upload_dir, data_source)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Data '{data_source}' not found.")

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    summary = {
        "data_source": data_source,
        "rows": len(df),
        "columns": list(df.columns),
        "date_range": {
            "start": str(df["timestamp"].min()),
            "end": str(df["timestamp"].max()),
            "days": (df["timestamp"].max() - df["timestamp"].min()).days,
        },
    }

    # Add energy totals if columns exist
    if "production_kWh" in df.columns:
        summary["total_production_kwh"] = round(df["production_kWh"].sum(), 1)
    if "consumption_kWh" in df.columns:
        summary["total_consumption_kwh"] = round(df["consumption_kWh"].sum(), 1)
    if "grid_purchase_kWh" in df.columns:
        summary["total_grid_purchase_kwh"] = round(df["grid_purchase_kWh"].sum(), 1)
    if "grid_feedin_kWh" in df.columns:
        summary["total_grid_feedin_kwh"] = round(df["grid_feedin_kWh"].sum(), 1)
    if "price_eur_kwh" in df.columns:
        summary["avg_spot_price_eur_kwh"] = round(df["price_eur_kwh"].mean(), 4)

    # Per-component load breakdown
    load_breakdown = {}
    for col, key in [
        ("household_kWh", "household_kwh"),
        ("hp_electricity_kWh", "heatpump_kwh"),
        ("ev_kWh", "ev_kwh"),
        ("dhw_kWh", "dhw_kwh"),
    ]:
        if col in df.columns:
            load_breakdown[key] = round(df[col].sum(), 1)
    if load_breakdown:
        summary["load_breakdown"] = load_breakdown

    return summary


# --- Profile analysis (monthly + PV coverage) ---


@router.get("/data/profile")
def data_profile(data_source: str = "sample"):
    """Return monthly energy profile with PV coverage per load component.

    Computes how much of each load component is covered by PV at each timestep,
    then aggregates monthly. Also returns typical day profiles for summer/winter.
    """
    if data_source == "sample":
        path = os.path.join(settings.data_dir, "sample.csv")
    else:
        path = os.path.join(settings.upload_dir, data_source)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Data '{data_source}' not found.")

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    if "production_kWh" not in df.columns or "consumption_kWh" not in df.columns:
        raise HTTPException(status_code=400, detail="Dataset must have production_kWh and consumption_kWh.")

    # Identify load components present in data
    component_cols = []
    component_names = []
    for col, name in [
        ("household_kWh", "household"),
        ("hp_electricity_kWh", "heatpump"),
        ("ev_kWh", "ev"),
        ("dhw_kWh", "dhw"),
    ]:
        if col in df.columns:
            component_cols.append(col)
            component_names.append(name)

    # --- PV coverage allocation per timestep ---
    # Priority: household → HP → EV → DHW (covers base load first)
    pv_avail = df["production_kWh"].values.copy()
    coverage = {}  # name -> array of PV-covered kWh per timestep

    for col, name in zip(component_cols, component_names):
        load = df[col].values
        covered = np.minimum(pv_avail, load)
        coverage[name] = covered
        pv_avail = pv_avail - covered  # remaining PV after covering this component

    grid_feedin = pv_avail  # leftover PV → grid

    # --- Monthly aggregation ---
    df["month"] = df["timestamp"].dt.month
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    monthly = {"months": month_names}

    # Production & consumption totals
    monthly["production"] = [round(g["production_kWh"].sum(), 1)
                             for _, g in df.groupby("month")]
    monthly["consumption"] = [round(g["consumption_kWh"].sum(), 1)
                              for _, g in df.groupby("month")]

    # Per-component monthly consumption
    for col, name in zip(component_cols, component_names):
        monthly[name] = [round(g[col].sum(), 1) for _, g in df.groupby("month")]

    # Per-component monthly PV coverage
    for name in component_names:
        df[f"_pv_{name}"] = coverage[name]
        monthly[f"{name}_from_pv"] = [round(g[f"_pv_{name}"].sum(), 1)
                                      for _, g in df.groupby("month")]

    monthly["grid_feedin"] = [round(v, 1) for v in
                              df.assign(_gf=grid_feedin).groupby("month")["_gf"].sum()]

    # Self-consumption total
    total_self = sum(np.array(coverage[n]).sum() for n in component_names)
    monthly["self_consumption_total"] = round(total_self, 1)

    # --- PV coverage summary per component ---
    pv_coverage = {}
    for col, name in zip(component_cols, component_names):
        total_load = df[col].sum()
        total_covered = coverage[name].sum()
        pv_coverage[name] = {
            "total_kwh": round(total_load, 1),
            "from_pv_kwh": round(total_covered, 1),
            "from_grid_kwh": round(total_load - total_covered, 1),
            "pv_coverage_pct": round(total_covered / total_load * 100, 1) if total_load > 0 else 0,
        }

    # --- Typical day (hourly average) for summer (Jun-Aug) and winter (Dec-Feb) ---
    df["hour"] = df["timestamp"].dt.hour
    df["month_num"] = df["timestamp"].dt.month

    typical_day = {}
    for season, months in [("summer", [6, 7, 8]), ("winter", [12, 1, 2])]:
        season_df = df[df["month_num"].isin(months)]
        if season_df.empty:
            continue
        hourly = season_df.groupby("hour").mean(numeric_only=True)
        day = {"hours": list(range(24))}
        day["production"] = [round(hourly.loc[h, "production_kWh"] * 1000, 1)
                             if h in hourly.index else 0 for h in range(24)]  # scale to Wh for readability
        day["consumption"] = [round(hourly.loc[h, "consumption_kWh"] * 1000, 1)
                              if h in hourly.index else 0 for h in range(24)]
        for col, name in zip(component_cols, component_names):
            day[name] = [round(hourly.loc[h, col] * 1000, 1)
                         if h in hourly.index else 0 for h in range(24)]
        typical_day[season] = day

    return {
        "monthly": monthly,
        "pv_coverage": pv_coverage,
        "typical_day": typical_day,
        "components": component_names,
    }
