"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check():
    """Liveness/Readiness: energietools (Engine) importierbar; pvtool nur Info (hybrid)."""
    try:
        import energietools

        engine_ok = True
        engine_version = getattr(energietools, "__version__", "unknown")
    except ImportError:
        engine_ok = False
        engine_version = None

    try:
        import importlib.util

        pvtool_available = importlib.util.find_spec("pvtool") is not None
    except (ImportError, ValueError):
        pvtool_available = False

    return {
        "status": "ok" if engine_ok else "degraded",
        "engine": "energietools",
        "engine_version": engine_version,
        # Rückwärtskompatibel fürs Frontend: pvtool ist jetzt nur noch hybrider
        # Beistand für Live-Connectoren, nicht mehr der Rechenkern.
        "pvtool": pvtool_available,
    }
