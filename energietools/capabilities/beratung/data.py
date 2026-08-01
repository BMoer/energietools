# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der publizierten Energieberatungsstellen-Daten aus ``energietools.data.beratung``.

Spiegelt das Daten-Lade-Muster des Netz-Packages: ``importlib.resources`` aus
dem gebündelten Daten-Package, ``lru_cache`` für Idempotenz, ``CapabilityError``
bei fehlenden/kaputten Dateien. **Kein Netzwerk** — offline auditierbar.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.beratung.models import BeratungManifest, BeratungsstelleEntry

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.beratung"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.beratung``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Beratungs-Daten-Datei '{filename}' nicht gefunden — ist data/beratung/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def load_beratungsstellen() -> tuple[BeratungsstelleEntry, ...]:
    """Lädt + parst beratungsstellen.json (gecacht; Tupel = immutable)."""
    raw = json.loads(_read_data("beratungsstellen.json"))
    if not isinstance(raw, list):
        raise CapabilityError("beratungsstellen.json: erwartet eine Liste von Beratungsstellen")
    return tuple(BeratungsstelleEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_manifest() -> BeratungManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return BeratungManifest(**json.loads(_read_data("MANIFEST.json")))
