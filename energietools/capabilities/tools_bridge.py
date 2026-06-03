# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Bestehende ``tools/``-Funktionen als Capabilities ans Rückgrat hängen.

Dünne ``FunctionCapability``-Wrapper mit Lazy-Import — so erscheinen die
deterministischen Analyse-Tools einheitlich in Registry, CLI und Agent, ohne
umgeschrieben zu werden und ohne ihre Schwer-Abhängigkeiten (numpy …) schon
beim Registrieren zu laden.

Bewusst (noch) NICHT hier: ``smartmeter`` (Live-Credentials), ``switching``
(erzeugt PDF-Datei, Seiteneffekt).
"""

from __future__ import annotations

from energietools.capabilities.base import CapabilityRegistry, FunctionCapability

_CONSUMPTION_SERIES = {
    "type": "array",
    "items": {"type": "object"},
    "description": "15-min-Verbrauch: [{ts, kwh}, …]",
}


def register_tool_capabilities(registry: CapabilityRegistry) -> CapabilityRegistry:
    """Registriert die deterministischen ``tools/``-Funktionen als Capabilities.

    Hinweis: Die Heimspeicher-Simulation ist als eigenständige ``scenarios``-Capability
    in die Struktur überführt (siehe capabilities/scenarios/) und ersetzt das frühere,
    hier gebridgete ``battery_sim`` (tools/battery_sim.py gelöscht).
    """
    registry.register(FunctionCapability(
        name="pv_sim",
        summary="PV-/Balkonkraftwerk-Simulation via PVGIS für eine PLZ.",
        target="energietools.tools.pv_sim:simulate_pv",
        input_schema={
            "type": "object",
            "properties": {
                "plz": {"type": "string"},
                "anlage_kwp": {"type": "number"},
                "ausrichtung": {"type": "string"},
                "neigung": {"type": "integer"},
                "jahresverbrauch_kwh": {"type": "number"},
                "strompreis_ct": {"type": "number"},
            },
            "required": ["plz"],
        },
    ))
    registry.register(FunctionCapability(
        name="beg_advisor",
        summary="Bürgerenergiegemeinschaft (BEG) — Beitrittsoptionen bewerten.",
        target="energietools.tools.beg_advisor:compare_beg_options",
        input_schema={
            "type": "object",
            "properties": {
                "jahresverbrauch_kwh": {"type": "number"},
                "aktueller_energiepreis_ct_kwh": {"type": "number"},
            },
            "required": ["jahresverbrauch_kwh", "aktueller_energiepreis_ct_kwh"],
        },
    ))
    registry.register(FunctionCapability(
        name="spot_analysis",
        summary="Spot-/Stundentarif-Analyse (Profilkostenfaktor) aus Verbrauch + Spotpreisen.",
        target="energietools.tools.spot_analysis:analyze_spot_tariff",
        input_schema={
            "type": "object",
            "properties": {
                "consumption_data": _CONSUMPTION_SERIES,
                "fix_preis_ct": {"type": "number"},
                "aufschlag_ct": {"type": "number"},
            },
            "required": ["consumption_data"],
        },
    ))
    registry.register(FunctionCapability(
        name="load_profile",
        summary="Lastprofil-Analyse (Grundlast, Spitzen, Anomalien) aus 15-min-Daten oder CSV.",
        target="energietools.tools.load_profile:analyze_load_profile",
        input_schema={
            "type": "object",
            "properties": {
                "consumption_data": _CONSUMPTION_SERIES,
                "csv_text": {"type": "string"},
                "price_per_kwh": {"type": "number"},
            },
        },
    ))
    registry.register(FunctionCapability(
        name="energy_monitor",
        summary="Energie-News + Förderungen-Katalog (RSS, PLZ-/Interessen-gefiltert).",
        target="energietools.tools.energy_monitor:monitor_energy_news",
        input_schema={
            "type": "object",
            "properties": {
                "user_plz": {"type": "string"},
                "user_interests": {"type": "array", "items": {"type": "string"}},
                "heating_type": {"type": "string"},
            },
        },
    ))
    registry.register(FunctionCapability(
        name="web_search",
        summary="Websuche zu Energiethemen (DuckDuckGo, AT-Region).",
        target="energietools.tools.web_search:web_search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    ))
    return registry
