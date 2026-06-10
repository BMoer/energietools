"""Market data endpoints.

Netzentgelte + Netzbetreiber laufen über energietools (auditierter data/netz-
Snapshot). Die Live-Beschaffung (aWATTar-Spot, ENTSO-E-Balancing) bleibt bei
pvtool und wird LAZY importiert — so bootet die App auch ohne pvtool, solange nur
die auf energietools re-wirten Endpunkte genutzt werden. Die Balancing-Auswertung
(Summary) macht energietools.
"""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query

from energietools.capabilities.netz.data import load_alle_vnb
from energietools.capabilities.netz.per_kwh import (
    charging_fee_ct_kwh,
    consumption_fee_ct_kwh,
    total_fee_breakdown,
)
from energietools.tools.regelenergie import summarise_balancing_prices

router = APIRouter(tags=["market"])


@router.get("/spot-prices")
def get_spot_prices(
    start: datetime = Query(..., description="Start datetime (ISO 8601, UTC)"),
    end: datetime = Query(..., description="End datetime (ISO 8601, UTC)"),
):
    """Österreichische EPEX-Spotpreise (Live, aWATTar — Beschaffung via pvtool)."""
    from pvtool.market.spot_prices import fetch_awattar_prices

    df = fetch_awattar_prices(start, end)
    return {"count": len(df), "prices": df.to_dict(orient="records")}


@router.get("/balancing-prices")
def get_balancing_prices(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Österreichische Regelenergie-Preise (Live-Fetch pvtool, Summary energietools)."""
    from pvtool.market.regelenergie import fetch_balancing_prices

    try:
        df = fetch_balancing_prices(start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ENTSO-E API error: {e}") from e

    summary = summarise_balancing_prices(
        df["price_eur_mwh"].tolist(), df["timestamp"].tolist()
    ) if len(df) else {"days": 0, "count": 0}
    return {"count": len(df), "summary": summary, "prices": df.to_dict(orient="records")}


@router.get("/grid-fees")
def get_grid_fees(
    ne_level: int = Query(default=7, ge=3, le=7, description="Network level (energietools: NE7-Haushalt)"),
    storage_exemption: bool = Query(default=False, description="ElWG § 16b exemption"),
):
    """Netzentgelt-Aufschlüsselung aus dem energietools-Snapshot (NE7-Haushalt, brutto)."""
    cons = consumption_fee_ct_kwh()
    charge = charging_fee_ct_kwh(storage_exemption=storage_exemption)
    breakdown = total_fee_breakdown(storage_exemption=storage_exemption)
    if cons is None or breakdown is None:
        raise HTTPException(status_code=404, detail="Netzentgelt-Snapshot nicht auflösbar.")
    note = None if ne_level == 7 else f"energietools deckt nur NE7-Haushalt ab; NE{ne_level} auf NE7 abgebildet."
    return {
        "ne_level": ne_level,
        "level": "NE7",
        "storage_exemption": storage_exemption,
        "consumption_fee_eur_kwh": round(cons / 100.0, 6),
        "charging_fee_eur_kwh": round((charge or 0.0) / 100.0, 6),
        "feedin_fee_eur_kwh": 0.0,  # energietools führt keinen Einspeise-Netztarif (= 0,0)
        "breakdown": breakdown,
        "note": note,
    }


@router.get("/grid-operators")
def get_grid_operators():
    """Alle österreichischen Netzbetreiber mit NE7-Arbeitspreis (energietools-Snapshot)."""
    return [
        {
            "key": e.key,
            "name": e.name,
            "bundesland": e.bundesland,
            "ne7_fee_ct_kwh": consumption_fee_ct_kwh(e.key),
        }
        for e in load_alle_vnb()
    ]
