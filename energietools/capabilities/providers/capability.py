# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hülle für die Versorger-Abdeckung je Netzgebiet."""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.providers.abdeckung import (
    lade_providers_manifest,
    versorger_abdeckung,
)


class VersorgerAbdeckungCapability(Capability):
    """Listet die an einer PLZ verfügbaren Stromlieferanten (bundesweit + regional)."""

    name = "versorger_abdeckung"
    summary = (
        "Welche Stromlieferanten sind an einer PLZ verfügbar? Bundesweite Anbieter "
        "überall, Landesversorger/Stadtwerke nur in ihrem Bundesland. Zeigt zusätzlich, "
        "welche regional ausgeschlossen sind und welche im Open-Data-Tarifkatalog stecken."
    )
    input_schema = {
        "type": "object",
        "properties": {"plz": {"type": "string", "description": "Postleitzahl"}},
        "required": ["plz"],
    }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        # B.6: Provenance des Snapshots im Result-Envelope (stand/quelle/version).
        manifest = lade_providers_manifest()
        return {
            "stand": manifest.get("stand", ""),
            "quelle": "anbieter.json (energietools.data.providers)",
            "snapshot_version": manifest.get("data_version", ""),
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        plz = kwargs.get("plz")
        if not plz:
            raise CapabilityError("plz ist erforderlich")
        a = versorger_abdeckung(str(plz))
        return {
            "plz": a.plz,
            "bundeslaender": list(a.bundeslaender),
            "netzbetreiber": a.netzbetreiber,
            "anzahl_verfuegbar": a.anzahl_verfuegbar,
            "anzahl_bundesweit": a.anzahl_bundesweit,
            "anzahl_regional": a.anzahl_regional,
            "verfuegbar": [v.brand for v in a.verfuegbar],
            "regional_ausgeschlossen": [
                {"brand": v.brand, "region": list(v.region)} for v in a.nicht_verfuegbar
            ],
            "im_katalog": a.im_katalog,
        }
