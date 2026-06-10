"""Simulation endpoints."""

import os

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.schemas import SimulationRequest, SimulationResponse
from app.services.simulation import compute_roi, run_scenarios

router = APIRouter(tags=["simulation"])

# Path to bundled sample data (small demo dataset)
SAMPLE_DATA_PATH = os.path.join(settings.data_dir, "sample.csv")


def _load_data(data_source: str) -> pd.DataFrame:
    """Load DataFrame from the specified data source."""
    if data_source == "sample":
        if not os.path.exists(SAMPLE_DATA_PATH):
            raise HTTPException(
                status_code=404,
                detail="Sample data not found. Bundle a sample.csv in the data directory.",
            )
        path = SAMPLE_DATA_PATH
    else:
        # data_source is a filename from a previous upload
        path = os.path.join(settings.upload_dir, data_source)
        if not os.path.exists(path):
            raise HTTPException(
                status_code=404, detail=f"Uploaded data '{data_source}' not found."
            )

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


@router.post("/simulate", response_model=SimulationResponse)
def simulate(req: SimulationRequest):
    """Run battery simulation scenarios on the specified data."""
    df = _load_data(req.data_source)

    # Auto-detect interval from data timestamps
    if len(df) > 1:
        dt_seconds = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds()
        req.battery.dt_hours = dt_seconds / 3600.0

    scenario_results, hp_summary = run_scenarios(
        df=df,
        scenarios=req.scenarios,
        battery_params=req.battery,
        market_params=req.market,
        peak_shaving_params=req.peak_shaving,
        heatpump_params=req.heatpump,
    )

    roi = compute_roi(scenario_results, req.battery, req.market, req.heatpump)

    warnings = []
    if "peak_shaving" in req.scenarios and req.peak_shaving and req.peak_shaving.mode == "optimal":
        warnings.append("Optimal mode may take 30-90s per battery size.")

    return SimulationResponse(
        scenarios=scenario_results,
        roi=roi,
        heatpump_summary=hp_summary,
        warnings=warnings,
    )
