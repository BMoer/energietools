# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden des publizierten EPEX-Spot-Snapshots aus ``energietools.data.spot`` (offline).

Spiegelt das Daten-Lade-Muster der netz-/tariffs-Snapshots: ``importlib.resources``
aus dem gebündelten Daten-Package, ``lru_cache`` für Idempotenz. **Kein Netzwerk** —
der EPEX-Snapshot ist offline auditierbar. Fehlt die Datei, wird **fail-open** ein
leeres Tupel geliefert: Spot-Tarife werden dann übersprungen, nie als 0 € bepreist.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.spot"


def _read_data(filename: str) -> str | None:
    """Liest eine Datei aus dem ``energietools.data.spot``-Package (fail-open: None)."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        log.warning(
            "Spot-Daten-Datei '%s' nicht gefunden — Spot-Tarife werden übersprungen.", filename,
        )
        return None


@lru_cache(maxsize=1)
def load_epex_prices() -> tuple[dict, ...]:
    """Lädt + parst den EPEX-Snapshot (gecacht; Tupel = immutable).

    Returns:
        Tupel von ``{"timestamp": ISO, "price_ct": float (netto)}``, aufsteigend.
        Leeres Tupel, wenn der Snapshot fehlt oder kaputt ist (fail-open).
    """
    raw = _read_data("epex_at.json")
    if raw is None:
        return ()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Spot-Snapshot epex_at.json nicht parsebar — Spot-Tarife werden übersprungen.")
        return ()
    if not isinstance(data, list):
        return ()
    return tuple(data)


@lru_cache(maxsize=1)
def load_spot_manifest() -> dict:
    """Lädt das Spot-Snapshot-Manifest (Provenance/Coverage); ``{}`` wenn nicht da."""
    raw = _read_data("MANIFEST.json")
    if raw is None:
        return {}
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return manifest if isinstance(manifest, dict) else {}
