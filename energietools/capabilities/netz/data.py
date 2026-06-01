# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der publizierten Netz-Daten aus ``energietools.data.netz`` (offline).

Spiegelt das Daten-Lade-Muster des Tarifkatalogs: ``importlib.resources`` aus
dem gebündelten Daten-Package, ``lru_cache`` für Idempotenz, ``CapabilityError``
bei fehlenden/kaputten Dateien. **Kein Netzwerk** — die JSON-Snapshots sind
offline auditierbar.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.netz.models import (
    Abgaben,
    GebrauchsabgabeRegel,
    NetzkostenEntry,
    NetzManifest,
    PlzInfo,
)

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.netz"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.netz``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Netz-Daten-Datei '{filename}' nicht gefunden — ist data/netz/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def load_netzkosten() -> tuple[NetzkostenEntry, ...]:
    """Lädt + parst netzkosten.json (gecacht; Tupel = immutable)."""
    raw = json.loads(_read_data("netzkosten.json"))
    if not isinstance(raw, list):
        raise CapabilityError("netzkosten.json: erwartet eine Liste von Netzbereichen")
    return tuple(NetzkostenEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_plz_index() -> dict[str, PlzInfo]:
    """Lädt plz_netzbereich.json als ``{plz: PlzInfo}`` (gecacht)."""
    raw = json.loads(_read_data("plz_netzbereich.json"))
    if not isinstance(raw, list):
        raise CapabilityError("plz_netzbereich.json: erwartet eine Liste von PLZ-Einträgen")
    return {entry["plz"]: PlzInfo(**entry) for entry in raw}


@lru_cache(maxsize=1)
def load_abgaben() -> Abgaben:
    """Lädt abgaben.json (föderale Konstanten + Gebrauchsabgabe-Regeln; gecacht)."""
    raw = json.loads(_read_data("abgaben.json"))
    if not isinstance(raw, dict):
        raise CapabilityError("abgaben.json: erwartet ein Objekt")
    gab = raw.get("gebrauchsabgabe", {})
    regeln = tuple(GebrauchsabgabeRegel(**r) for r in gab.get("regeln", []))
    return Abgaben(
        gueltig_ab=raw.get("gueltig_ab", ""),
        federal=raw.get("federal", {}),
        gebrauchsabgabe_basis=gab.get("basis", "energie_netto"),
        gebrauchsabgabe_regeln=regeln,
        gebrauchsabgabe_default=float(gab.get("default", 0.0)),
    )


@lru_cache(maxsize=1)
def load_manifest() -> NetzManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return NetzManifest(**json.loads(_read_data("MANIFEST.json")))
