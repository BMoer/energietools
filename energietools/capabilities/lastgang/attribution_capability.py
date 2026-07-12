# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""``trend_attribution`` — YoY-Delta-Zerlegung nach Leistungsband × Tageszeit.

Capability-Wrapper um den Rechen-Kern (``attribution.py``). Liefert die
Geräte-KLASSE als Hypothese je Treiber-Zelle (nie Gerätename) samt Rechenweg,
Caveats (F21 15-min-Grenze IMMER) und Nenner-Definitionen (L.6). Offline
testbar — kein DB-/Netz-Zugriff.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from energietools.capabilities.base import Capability
from energietools.capabilities.lastgang.attribution import compute_trend_attribution


def _optionales_jahr(kwargs: dict[str, Any], feld: str) -> int | None:
    """Optionales Jahres-Argument robust nach int casten (System-Grenze)."""
    from energietools.capabilities.base import CapabilityError

    wert = kwargs.get(feld)
    if wert is None:
        return None
    try:
        return int(wert)
    except (TypeError, ValueError) as exc:
        raise CapabilityError(f"{feld} muss eine Ganzzahl (Jahr) sein, war '{wert}'") from exc


class TrendAttributionCapability(Capability):
    """Zerlegt das YoY-Delta eines Lastgangs nach Leistungsband × Tageszeit."""

    name = "trend_attribution"
    summary = (
        "Zerlegt den Mehrjahres-Verbrauchszuwachs (YoY-Delta) einer 15-min-Serie "
        "nach Leistungsband × Tageszeit × Werktag/Wochenende und benennt je Treiber "
        "eine Geräte-KLASSE als Hypothese (NIE einen Gerätenamen — 15-min-Grenze). "
        "Liefert Rechenweg, Caveats und Nenner-Definitionen im Result."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption": {
                "type": "array",
                "items": {"type": "object"},
                "description": "15-min-Verbrauch (Mehrjahres-Serie): [{ts, kwh}, …]",
            },
            "jahr_a": {
                "type": "integer",
                "description": "Basisjahr; leer → zweitjüngstes Jahr der Serie",
            },
            "jahr_b": {
                "type": "integer",
                "description": "Vergleichsjahr; leer → jüngstes Jahr der Serie",
            },
        },
        "required": ["consumption"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        consumption = kwargs.get("consumption")
        jahr_a = _optionales_jahr(kwargs, "jahr_a")
        jahr_b = _optionales_jahr(kwargs, "jahr_b")
        result = compute_trend_attribution(consumption, jahr_a=jahr_a, jahr_b=jahr_b)
        # Native _run wird nicht auto-normalisiert → selbst nach JSON serialisieren (§0.2).
        return result.model_dump(mode="json")

    def result_field_paths(self) -> dict[str, str]:
        """Reale Result-Skalare für Caveat-Trigger im Prozess-Linter (fail-closed)."""
        return {
            "anzahl_zellen": "number",
            "anzahl_treiber": "number",
            "top_treiber_klasse": "str",
            "top_treiber_delta_kwh": "number",
            "fenster.von_jahr": "number",
            "fenster.bis_jahr": "number",
            "fenster.gemeinsame_slots": "number",
            "fenster.gemeinsame_tage": "number",
            "grenzen.aufloesung_min": "number",
            "grenzen.klasse_nicht_name": "bool",
        }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "stand": _dt.date.today().isoformat(),
            "quelle": (
                "energietools.capabilities.lastgang.attribution "
                "(Neuimplementierung nach CASE_09-Methode)"
            ),
            "methode": "leistungsband_x_tageszeit",
        }
