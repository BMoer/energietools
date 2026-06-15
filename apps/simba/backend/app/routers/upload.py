"""CSV/Excel upload endpoint."""

import os
import uuid

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings

router = APIRouter(tags=["upload"])


@router.post("/upload")
async def upload_data(file: UploadFile = File(...)):
    """Upload a CSV or Excel file with PV/load data.

    Returns a data_id that can be used in POST /api/simulate.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xls", ".ods"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Use .csv, .xlsx, .xls, or .ods.",
        )

    # Generate unique filename to avoid collisions
    data_id = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(settings.upload_dir, data_id)

    os.makedirs(settings.upload_dir, exist_ok=True)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # Validate: try to read and check for required columns
    try:
        if ext == ".csv":
            df = pd.read_csv(save_path)
        else:
            df = pd.read_excel(save_path)
    except Exception as e:
        os.remove(save_path)
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    required = {"timestamp"}
    missing = required - set(df.columns)
    if missing:
        os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {missing}. Found: {list(df.columns)}",
        )

    return {
        "data_id": data_id,
        "rows": len(df),
        "columns": list(df.columns),
        "message": f"Upload successful. Use data_source='{data_id}' in /api/simulate.",
    }
