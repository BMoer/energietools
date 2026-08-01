# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Förderungen-Capability — offene/geschlossene Bund- + Landesförderungen je Bundesland.

**FAIL-OPEN bei der Eingabe, klar abgelehnt bei Unbekanntem:** ``bundesland``
kann direkt oder aus ``plz`` (über die bestehende netz-PLZ-Logik) kommen. Ein
unbekanntes/nicht auflösbares Bundesland führt zu einer strukturierten
:class:`CapabilityRejection` mit einer klaren Rückfrage statt eines stillen
Leer-Ergebnisses oder einer rohen Exception.

**Default: nur verifizierte, offene Einträge.** ``verlaesslichkeit='unsicher'``
Einträge werden nie ungefragt als Fakt ausgespielt (Parameter
``inkl_unsicher=False``); geschlossene Förderungen nur mit ``nur_offen=False``.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability
from energietools.capabilities.bundesland import resolve_bundesland
from energietools.capabilities.foerderungen.data import load_foerderungen, load_manifest
from energietools.capabilities.foerderungen.models import FoerderungEntry


def _entry_dict(entry: FoerderungEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "ebene": entry.ebene,
        "bundesland": entry.bundesland,
        "kategorie": entry.kategorie,
        "name": entry.name,
        "foerderstelle": entry.foerderstelle,
        "status": entry.status,
        "status_seit": entry.status_seit,
        "status_detail": entry.status_detail,
        "foerderhoehe": {
            "typ": entry.foerderhoehe.typ,
            "werte": [
                {"bezeichnung": w.bezeichnung, "wert": w.wert} for w in entry.foerderhoehe.werte
            ],
            "text": entry.foerderhoehe.text,
        },
        "bedingungen": list(entry.bedingungen),
        "zielgruppe": entry.zielgruppe,
        "antrags_url": entry.antrags_url,
        "quellen": [
            {"url": q.url, "abrufdatum": q.abrufdatum, "typ": q.typ} for q in entry.quellen
        ],
        "verlaesslichkeit": entry.verlaesslichkeit,
        "unsicher_grund": entry.unsicher_grund,
        "naechstes_fenster": entry.naechstes_fenster,
    }


class FoerderungenCheckCapability(Capability):
    """Offene (optional auch geschlossene) Förderungen für ein Bundesland."""

    name = "foerderungen_check"
    summary = (
        "Passende Förderungen (Bund + Landesförderungen) für ein Bundesland oder "
        "eine PLZ — Photovoltaik, Speicher, Heizungstausch, Sanierung u.a. Mit "
        "Status, Fördersatz, Bedingungen, Fenstern und Quellen. Default: nur "
        "offene, primärquellenverifizierte Einträge."
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
            "kategorien": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optionaler Filter, z.B. ['pv', 'speicher', 'heizungstausch']",
            },
            "nur_offen": {
                "type": "boolean",
                "default": True,
                "description": "Nur Förderungen mit status='offen' (Default true)",
            },
            "inkl_unsicher": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Auch verlaesslichkeit='unsicher'-Einträge einschließen (Default false — "
                    "unsichere Einträge werden nie ungefragt als Fakt ausgespielt)"
                ),
            },
        },
    }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        manifest = load_manifest()
        return {
            "stand": manifest.stand_recherche or manifest.generated_at,
            "quelle": "energietools.data.foerderungen (foerderungen.json)",
            "snapshot_version": manifest.data_version,
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        bundesland = resolve_bundesland(kwargs.get("bundesland"), kwargs.get("plz"))
        kategorien = kwargs.get("kategorien")
        kategorien_set = {str(k).strip().lower() for k in kategorien} if kategorien else None
        nur_offen = bool(kwargs.get("nur_offen", True))
        inkl_unsicher = bool(kwargs.get("inkl_unsicher", False))

        treffer: list[FoerderungEntry] = []
        for entry in load_foerderungen():
            if entry.ebene == "land" and entry.bundesland != bundesland:
                continue
            if not inkl_unsicher and entry.verlaesslichkeit == "unsicher":
                continue
            if nur_offen and entry.status != "offen":
                continue
            if kategorien_set and entry.kategorie.strip().lower() not in kategorien_set:
                continue
            treffer.append(entry)

        manifest = load_manifest()
        return {
            "bundesland": bundesland,
            "anzahl": len(treffer),
            "foerderungen": [_entry_dict(e) for e in treffer],
            "stand": manifest.stand_recherche or manifest.generated_at,
        }
