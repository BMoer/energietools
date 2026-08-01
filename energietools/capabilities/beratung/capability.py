# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Beratungsstellen-Capability — die (kostenlose) Energieberatungsstelle je Bundesland."""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability
from energietools.capabilities.beratung.data import load_beratungsstellen, load_manifest
from energietools.capabilities.beratung.models import BeratungsstelleEntry
from energietools.capabilities.bundesland import resolve_bundesland


def _entry_dict(entry: BeratungsstelleEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "bundesland": entry.bundesland,
        "name": entry.name,
        "traeger": entry.traeger,
        "kosten": entry.kosten,
        "url": entry.url,
        "quellen": [
            {"url": q.url, "abrufdatum": q.abrufdatum, "typ": q.typ} for q in entry.quellen
        ],
        "verlaesslichkeit": entry.verlaesslichkeit,
        "unsicher_grund": entry.unsicher_grund,
    }


class BeratungsstellenCapability(Capability):
    """Die produktneutrale Energieberatungsstelle für ein Bundesland oder eine PLZ."""

    name = "beratungsstellen"
    summary = (
        "Die kostenlose, produktneutrale Energieberatungsstelle eines Bundeslands "
        "(Trägerorganisation, Kontakt-URL, Quelle). Bundesland direkt angeben oder "
        "aus einer PLZ ableiten lassen."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bundesland": {
                "type": "string",
                "description": "z.B. 'Wien', 'Tirol' — eines der 9 österreichischen Bundesländer",
            },
            "plz": {
                "type": "string",
                "description": (
                    "Alternative zu bundesland: Postleitzahl, aus der das Bundesland "
                    "abgeleitet wird"
                ),
            },
            "inkl_unsicher": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Auch verlaesslichkeit='unsicher'-Einträge einschließen (Default false)"
                ),
            },
        },
    }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        manifest = load_manifest()
        return {
            "stand": manifest.stand_recherche or manifest.generated_at,
            "quelle": "energietools.data.beratung (beratungsstellen.json)",
            "snapshot_version": manifest.data_version,
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        bundesland = resolve_bundesland(kwargs.get("bundesland"), kwargs.get("plz"))
        inkl_unsicher = bool(kwargs.get("inkl_unsicher", False))

        treffer = [
            e
            for e in load_beratungsstellen()
            if e.bundesland == bundesland and (inkl_unsicher or e.verlaesslichkeit == "verifiziert")
        ]
        manifest = load_manifest()
        return {
            "bundesland": bundesland,
            "anzahl": len(treffer),
            "beratungsstellen": [_entry_dict(e) for e in treffer],
            "stand": manifest.stand_recherche or manifest.generated_at,
        }
