# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der publizierten Solar/Speicher-Marktdaten aus ``energietools.data.marktdaten``.

Spiegelt das Daten-Lade-Muster des Netz-Packages: ``importlib.resources`` aus
dem gebündelten Daten-Package, ``lru_cache`` für Idempotenz, ``CapabilityError``
bei fehlenden/kaputten Dateien. **Kein Netzwerk** — offline auditierbar.

Kein eigenes ``capability.py``: die B1-Spec listet für dieses Package keine
Capability (rein informative Daten, keine Empfehlungslogik) — Konsumenten
(Website, ein künftiges MCP-Tool) lesen direkt über diesen Loader.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.marktdaten.models import MarktdatenManifest, SolarSpeicherDaten

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.marktdaten"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.marktdaten``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Marktdaten-Datei '{filename}' nicht gefunden — ist data/marktdaten/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def load_solar_speicher() -> SolarSpeicherDaten:
    """Lädt + parst solar_speicher.json (gecacht)."""
    raw = json.loads(_read_data("solar_speicher.json"))
    if not isinstance(raw, dict):
        raise CapabilityError("solar_speicher.json: erwartet ein Objekt")
    return SolarSpeicherDaten(**raw)


@lru_cache(maxsize=1)
def load_manifest() -> MarktdatenManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return MarktdatenManifest(**json.loads(_read_data("MANIFEST.json")))
