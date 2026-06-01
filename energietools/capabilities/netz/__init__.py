# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Netz-Capability — Open-Data-Netzkosten, Abgaben und Verfügbarkeit (offline).

Macht die publizierten Netz-Daten (``data/netz/``: Netzkosten je Netzbereich,
PLZ→Netzbereich-Index, föderale Abgaben + Gebrauchsabgabe-Regeln) als
auditierbare Capabilities nutzbar — **ohne Netzwerk, ohne externe Rechner-API**.

Vier Capabilities:
- ``netzkosten``               — Brutto-Jahres-Netzkosten je PLZ.
- ``gesamtkosten``             — echte Brutto-Jahreskosten (Energie + Netz + USt).
- ``netz_verfuegbar``          — Verfügbarkeit eines Tarifs in einer Region.
- ``tarifvergleich_inkl_netz`` — Tarifvergleich mit aus der PLZ gefüllten Netz-Inputs.

**FAIL-OPEN überall:** Wo Daten fehlen oder mehrdeutig sind, wird nie hart
ausgeschlossen — lieber ein Tarif mit Netzkosten 0 als ein fälschlich
unterdrückter Tarif.
"""

from __future__ import annotations

from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    TarifvergleichInklNetzCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.netz.models import (
    Abgaben,
    NetzkostenEntry,
    NetzManifest,
    PlzInfo,
)
from energietools.capabilities.netz.resolve import (
    gebrauchsabgabe_rate,
    ist_verfuegbar,
    netzkosten_brutto_eur,
    plz_info,
    resolve_netzbetreiber,
)

__all__ = [
    "Abgaben",
    "GesamtkostenCapability",
    "NetzManifest",
    "NetzkostenCapability",
    "NetzkostenEntry",
    "PlzInfo",
    "TarifvergleichInklNetzCapability",
    "VerfuegbarkeitCapability",
    "gebrauchsabgabe_rate",
    "ist_verfuegbar",
    "netzkosten_brutto_eur",
    "plz_info",
    "resolve_netzbetreiber",
]
