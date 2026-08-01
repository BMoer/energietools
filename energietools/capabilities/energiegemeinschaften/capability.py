# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Energiegemeinschaften-Info-Capability — Rechtsformen, ElWG-Stand, Beitrittsschritte.

Nicht zu verwechseln mit der bestehenden ``community_metrics``-Capability
(SSR/SCR-Kennzahlenrechner aus Erzeugungs-/Verbrauchsreihen) — diese
Capability liefert reine Fakten/Info, keine Zeitreihen-Berechnung.

``bundesland`` ist hier optional (anders als bei ``foerderungen_check``/
``beratungsstellen``): die Rechtsformen-Fakten gelten bundesweit, ein
Bundesland grenzt nur zusätzlich die Verzeichnis-Einträge ein.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability
from energietools.capabilities.bundesland import BEKANNTE_BUNDESLAENDER, bundesland_aus_plz
from energietools.capabilities.energiegemeinschaften.data import (
    load_fakten,
    load_manifest,
    load_verzeichnis,
)
from energietools.capabilities.energiegemeinschaften.models import Rechtsform, VerzeichnisEintrag


def _rechtsform_dict(key: str, r: Rechtsform) -> dict[str, Any]:
    return {
        "key": key,
        "name": r.name,
        "raeumliche_grenze": r.raeumliche_grenze,
        "energiequelle": r.energiequelle,
        "energieform": r.energieform,
        "rechtsform_noetig": r.rechtsform_noetig,
        "rechtsform_hinweis": r.rechtsform_hinweis,
        "wer_darf_mitmachen": r.wer_darf_mitmachen,
        "netzentgelt_reduktion": r.netzentgelt_reduktion,
        "abgabenbefreiung": r.abgabenbefreiung,
        "automatische_verrechnung": r.automatische_verrechnung,
        "quellen": [{"url": q.url, "abrufdatum": q.abrufdatum, "typ": q.typ} for q in r.quellen],
        "verlaesslichkeit": r.verlaesslichkeit,
        "unsicher_grund": r.unsicher_grund,
    }


def _verzeichnis_dict(e: VerzeichnisEintrag) -> dict[str, Any]:
    return {
        "name": e.name,
        "bundesland": e.bundesland,
        "plz": e.plz,
        "typ": e.typ,
        "quelle": e.quelle,
        "stand": e.stand,
    }


class EnergiegemeinschaftenInfoCapability(Capability):
    """Fakten zu Energiegemeinschaften: Rechtsformen, ElWG-Stand, Beitrittsschritte."""

    name = "energiegemeinschaften_info"
    summary = (
        "Fakten zu Energiegemeinschaften (GEA/EEG lokal/EEG regional/BEG): "
        "Netzentgelt-Reduktionen mit Rechtsquelle, ElWG-Änderung (Inkrafttreten-"
        "Termine), Marktstand, Beitrittsschritte. Optional Verzeichnis-Einträge "
        "für ein Bundesland (aktuell leer — wird laufend befüllt)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bundesland": {
                "type": "string",
                "description": (
                    "Optional — grenzt nur die Verzeichnis-Einträge ein, nicht die "
                    "Rechtsformen-Fakten"
                ),
            },
            "plz": {
                "type": "string",
                "description": "Alternative zu bundesland",
            },
            "inkl_unsicher": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Auch verlaesslichkeit='unsicher'-Rechtsformen einschließen "
                    "(Default false — betrifft aktuell nur 'beg', deren "
                    "Netzentgelt-Prozentsatz noch nicht feststeht)"
                ),
            },
        },
    }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        manifest = load_manifest()
        return {
            "stand": manifest.stand_recherche or manifest.generated_at,
            "quelle": "energietools.data.energiegemeinschaften (fakten.json)",
            "snapshot_version": manifest.data_version,
        }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        inkl_unsicher = bool(kwargs.get("inkl_unsicher", False))
        bundesland = kwargs.get("bundesland")
        plz = kwargs.get("plz")
        if not bundesland and plz:
            bundesland = bundesland_aus_plz(str(plz).strip())
        if bundesland and bundesland not in BEKANNTE_BUNDESLAENDER:
            # Fail-open: unbekanntes Bundesland ignoriert den Filter, kein Hard-Fail.
            bundesland = None

        fakten = load_fakten()
        rechtsformen = {
            key: _rechtsform_dict(key, r)
            for key, r in fakten.rechtsformen.items()
            if inkl_unsicher or r.verlaesslichkeit == "verifiziert"
        }

        verzeichnis = load_verzeichnis()
        if bundesland:
            verzeichnis = tuple(e for e in verzeichnis if e.bundesland == bundesland)

        manifest = load_manifest()
        return {
            "bundesland": bundesland,
            "rechtsformen": rechtsformen,
            "elwg_aenderung": fakten.elwg_aenderung,
            "marktstand": fakten.marktstand,
            "beitrittsschritte": [
                {"schritt": s.schritt, "titel": s.titel, "beschreibung": s.beschreibung}
                for s in fakten.beitrittsschritte
            ],
            "fazit_haushalt": fakten.fazit_haushalt,
            "verzeichnis": [_verzeichnis_dict(e) for e in verzeichnis],
            "verzeichnis_anzahl": len(verzeichnis),
            "verzeichnis_hinweis": (
                "Kein vollständiges amtliches Verzeichnis verfügbar (siehe "
                "verzeichnis_quellen_info); dieser Snapshot wird laufend vom "
                "Quellen-Wächter aus der amtlichen Landkarte ergänzt."
            ),
            "stand": manifest.stand_recherche or manifest.generated_at,
        }
