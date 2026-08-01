# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der publizierten Energiegemeinschafts-Daten aus
``energietools.data.energiegemeinschaften``.

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
from energietools.capabilities.energiegemeinschaften.models import (
    BegProviderEntry,
    EnergiegemeinschaftenFakten,
    EnergiegemeinschaftenManifest,
    VerzeichnisEintrag,
)

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.energiegemeinschaften"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.energiegemeinschaften``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Energiegemeinschafts-Daten-Datei '{filename}' nicht gefunden — "
            "ist data/energiegemeinschaften/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def load_fakten() -> EnergiegemeinschaftenFakten:
    """Lädt + parst fakten.json (gecacht)."""
    raw = json.loads(_read_data("fakten.json"))
    if not isinstance(raw, dict):
        raise CapabilityError("fakten.json: erwartet ein Objekt")
    return EnergiegemeinschaftenFakten(**raw)


@lru_cache(maxsize=1)
def load_verzeichnis() -> tuple[VerzeichnisEintrag, ...]:
    """Lädt verzeichnis.json (gecacht; Tupel = immutable).

    Initial leer — B2 (Quellen-Wächter/EEG-Verzeichnis-Scraper) befüllt es aus
    der amtlichen Landkarte. Fail-open: fehlt die Datei, leeres Tupel.
    """
    try:
        raw = json.loads(_read_data("verzeichnis.json"))
    except CapabilityError:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(VerzeichnisEintrag(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_beg_providers() -> tuple[BegProviderEntry, ...]:
    """Lädt beg_providers.json (gecacht; Tupel = immutable)."""
    raw = json.loads(_read_data("beg_providers.json"))
    if not isinstance(raw, list):
        raise CapabilityError("beg_providers.json: erwartet eine Liste von BEG-Anbietern")
    return tuple(BegProviderEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_manifest() -> EnergiegemeinschaftenManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return EnergiegemeinschaftenManifest(**json.loads(_read_data("MANIFEST.json")))
