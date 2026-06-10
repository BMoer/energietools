"""FastAPI application — Solar PV Battery Simulator."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import connectors, health, market, simulation, upload

app = FastAPI(
    title="Simba — Solar PV Simulator",
    description="Austrian PV + battery storage simulation API, powered by energietools.",
    version="0.2.0",
)

# CORS: konkrete Origins statt '*' (Wildcard + allow_credentials ist ungültig/riskant).
# Per SIMBA_CORS_ORIGINS (komma-separiert) überschreibbar; Default = lokale Entwicklung.
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_origins = [o.strip() for o in os.environ.get("SIMBA_CORS_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(simulation.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(connectors.router, prefix="/api")

# Serve frontend
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def frontend():
    """Serve the frontend."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
