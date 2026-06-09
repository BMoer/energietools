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
    GebrauchsabgabeRegelDetail,
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
    """Lädt + parst netzkosten.json (gecacht; Tupel = immutable).

    Das sind die **Tarif-Netzbereiche** (die 14 mit eigenem NE7-Tarif).
    """
    raw = json.loads(_read_data("netzkosten.json"))
    if not isinstance(raw, list):
        raise CapabilityError("netzkosten.json: erwartet eine Liste von Netzbereichen")
    return tuple(NetzkostenEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_attribution() -> tuple[NetzkostenEntry, ...]:
    """Lädt vnb_attribution.json (Attributions-VNB: realer Name + tarif_referenz).

    Fail-open: fehlt die Datei (älterer Snapshot), wird ein leeres Tupel
    zurückgegeben — die Tarif-Auflösung funktioniert dann ohne Namens-Attribution.
    """
    try:
        raw = json.loads(_read_data("vnb_attribution.json"))
    except CapabilityError:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(NetzkostenEntry(**entry) for entry in raw)


@lru_cache(maxsize=1)
def load_alle_vnb() -> tuple[NetzkostenEntry, ...]:
    """Alle VNB für die Auflösung: Tarif-Netzbereiche + Attributions-VNB."""
    return load_netzkosten() + load_attribution()


def _normalize_plz_entry(entry: dict) -> dict:
    """Akzeptiert auch das alte Skalar-Schema und mappt es auf Schema v2.

    Schema v2 = ``{plz, ort, gemeinden:[{name,bundesland}], bundeslaender:[str]}``.
    Ein alter Snapshot (``gemeinde``/``bundesland`` skalar) wird defensiv auf eine
    1-Element-Liste abgebildet, damit Daten-Regen + Loader-Change nicht hart
    brechen, falls sie getrennt landen.
    """
    if "gemeinden" in entry:
        return entry
    gemeinde = str(entry.get("gemeinde", "")).strip()
    bundesland = str(entry.get("bundesland", "")).strip()
    gemeinden = [{"name": gemeinde, "bundesland": bundesland}] if gemeinde else []
    return {
        "plz": entry.get("plz", ""),
        "ort": entry.get("ort", gemeinde),
        "gemeinden": gemeinden,
        "bundeslaender": [bundesland] if bundesland else [],
    }


@lru_cache(maxsize=1)
def load_plz_index() -> dict[str, PlzInfo]:
    """Lädt plz_netzbereich.json als ``{plz: PlzInfo}`` (gecacht, Schema v2)."""
    raw = json.loads(_read_data("plz_netzbereich.json"))
    if not isinstance(raw, list):
        raise CapabilityError("plz_netzbereich.json: erwartet eine Liste von PLZ-Einträgen")
    return {entry["plz"]: PlzInfo(**_normalize_plz_entry(entry)) for entry in raw}


@lru_cache(maxsize=1)
def load_abgaben() -> Abgaben:
    """Lädt abgaben.json (föderale Konstanten + Gebrauchsabgabe-Regeln; gecacht)."""
    raw = json.loads(_read_data("abgaben.json"))
    if not isinstance(raw, dict):
        raise CapabilityError("abgaben.json: erwartet ein Objekt")
    # S6: der alte energie-only Flat-Pfad (gebrauchsabgabe.{basis,regeln,default}) wird
    # nicht mehr gelesen — die basisgenaue GA lebt in gebrauchsabgabe_je_vnb/_longtail_plz.
    je_vnb = {
        key: GebrauchsabgabeRegelDetail(**regel)
        for key, regel in raw.get("gebrauchsabgabe_je_vnb", {}).items()
    }
    longtail = {
        plz: GebrauchsabgabeRegelDetail(**regel)
        for plz, regel in raw.get("gebrauchsabgabe_longtail_plz", {}).items()
    }
    return Abgaben(
        gueltig_ab=raw.get("gueltig_ab", ""),
        federal=raw.get("federal", {}),
        gebrauchsabgabe_je_vnb=je_vnb,
        gebrauchsabgabe_longtail_plz=longtail,
    )


@lru_cache(maxsize=1)
def load_manifest() -> NetzManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return NetzManifest(**json.loads(_read_data("MANIFEST.json")))
