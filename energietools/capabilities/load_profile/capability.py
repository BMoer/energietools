# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Capability-Hülle der Lastprofil-Analyse (WP2-S 2/3, Durchstich 2).

Übersetzt den in-band-Fehlerpfad von ``tools.load_profile.analyze_load_profile``
(``analyse_erfolgreich=False`` + ``fehler``) in die einheitliche ok/error-Envelope-
Semantik (``CapabilityError`` → ``Capability.run()`` setzt ``ok=False`` automatisch).
Die Tool-Funktion selbst bleibt unverändert (öffentliche MIT-API) — ausschließlich
diese Capability-Klasse mappt.

WICHTIG: ``analyze_load_profile`` importiert numpy/pandas auf Modulebene
(``tools/load_profile.py:20-21``). Lazy-Import HIER (innerhalb ``_run``, nicht auf
Modulebene dieser Datei) erhält das in ``tools_bridge.py`` dokumentierte Ziel, diese
Importkosten nicht schon beim Registry-Aufbau zu zahlen.
"""

from __future__ import annotations

from datetime import datetime
from importlib import metadata
from typing import Any

from energietools.capabilities.base import Capability, CapabilityError

_CONSUMPTION_SERIES = {
    "type": "array",
    "items": {"type": "object"},
    "description": "15-min-Verbrauch: [{ts, kwh}, …]",
}


def _paket_version() -> str:
    try:
        return metadata.version("energietools")
    except metadata.PackageNotFoundError:
        return "dev"


def _zeitraum_aus_consumption_data(consumption_data: Any) -> str | None:
    """Bestes-Aufwand Datenstand aus der rohen Eingabe — KEIN pandas/numpy, nur
    stdlib (``_meta`` läuft VOR ``_run``, darf die schweren Deps also gar nicht
    brauchen, siehe Lazy-Import-Begründung im Modul-Docstring)."""
    if not isinstance(consumption_data, list) or not consumption_data:
        return None
    zeitstempel: list[datetime] = []
    for eintrag in consumption_data:
        roh = eintrag.get("timestamp") if isinstance(eintrag, dict) else None
        if not roh:
            continue
        try:
            zeitstempel.append(datetime.fromisoformat(str(roh)))
        except ValueError:
            continue  # einzelner kaputter Zeitstempel darf _meta nie kippen
    if not zeitstempel:
        return None
    return f"{min(zeitstempel).isoformat()}…{max(zeitstempel).isoformat()}"


class LoadProfileCapability(Capability):
    """Lastprofil-Analyse (Grundlast, Spitzen, Anomalien) aus 15-min-Daten oder CSV."""

    name = "load_profile"
    summary = (
        "Lastprofil-Analyse (Grundlast, Spitzen, Anomalien) aus 15-min-Daten oder CSV."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "consumption_data": _CONSUMPTION_SERIES,
            "csv_text": {"type": "string"},
            "price_per_kwh": {"type": "number"},
        },
    }

    def _meta(self, **kwargs: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "quelle": "Nutzer-Zeitreihe (consumption_data/csv_text) — kein externer Datensatz",
            "snapshot_version": _paket_version(),
        }
        zeitraum = _zeitraum_aus_consumption_data(kwargs.get("consumption_data"))
        if zeitraum:
            meta["stand"] = zeitraum
        return meta

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        from energietools.tools.load_profile import analyze_load_profile  # lazy: numpy/pandas

        analysis = analyze_load_profile(
            consumption_data=kwargs.get("consumption_data"),
            csv_text=kwargs.get("csv_text", ""),
            price_per_kwh=kwargs.get("price_per_kwh", 0.20),
        )
        if not analysis.analyse_erfolgreich:
            raise CapabilityError(
                analysis.fehler or "Lastprofil-Analyse fehlgeschlagen (kein Fehlertext)."
            )
        # mode="json": date -> ISO-String (AnomalyResult.datum, models/load_profile.py:34).
        # Explizit nötig — bei einer dedizierten Capability (anders als bei
        # FunctionCapability) gibt es KEINE automatische _to_jsonable-Stufe.
        return analysis.model_dump(mode="json")
