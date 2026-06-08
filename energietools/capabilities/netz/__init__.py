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
    GemeindeInfo,
    NetzkostenEntry,
    NetzManifest,
    PlzInfo,
)
from energietools.capabilities.netz.per_kwh import (
    DEFAULT_OPERATOR_AT,
    charging_fee_ct_kwh,
    consumption_fee_ct_kwh,
    default_network_fee_ct_kwh,
    network_fee_ct_kwh,
    resolve_operator,
    total_fee_breakdown,
)
from energietools.capabilities.netz.per_kwh_capability import GridFeesCapability
from energietools.capabilities.netz.resolve import (
    gebrauchsabgabe_rate,
    ist_verfuegbar,
    netzkosten_brutto_eur,
    plz_info,
    resolve_netzbetreiber,
)

__all__ = [
    "DEFAULT_OPERATOR_AT",
    "Abgaben",
    "GemeindeInfo",
    "GesamtkostenCapability",
    "GridFeesCapability",
    "NetzManifest",
    "NetzkostenCapability",
    "NetzkostenEntry",
    "PlzInfo",
    "TarifvergleichInklNetzCapability",
    "VerfuegbarkeitCapability",
    "charging_fee_ct_kwh",
    "consumption_fee_ct_kwh",
    "default_network_fee_ct_kwh",
    "gebrauchsabgabe_rate",
    "ist_verfuegbar",
    "network_fee_ct_kwh",
    "netzkosten_brutto_eur",
    "plz_info",
    "resolve_netzbetreiber",
    "resolve_operator",
    "total_fee_breakdown",
]
