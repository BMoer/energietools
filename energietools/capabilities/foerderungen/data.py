# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der publizierten Förderungs-Daten aus ``energietools.data.foerderungen``.

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
from energietools.capabilities.foerderungen.models import (
    FoerderungenManifest,
    FoerderungEntry,
)

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.foerderungen"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.foerderungen``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Förderungs-Daten-Datei '{filename}' nicht gefunden — "
            "ist data/foerderungen/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def load_foerderungen() -> tuple[FoerderungEntry, ...]:
    """Lädt + parst foerderungen.json (gecacht; Tupel = immutable)."""
    raw = json.loads(_read_data("foerderungen.json"))
    if not isinstance(raw, list):
        raise CapabilityError("foerderungen.json: erwartet eine Liste von Förderungen")
    return tuple(FoerderungEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_manifest() -> FoerderungenManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return FoerderungenManifest(**json.loads(_read_data("MANIFEST.json")))
