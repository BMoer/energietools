# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Heatpump-Capability — diskreter Heizkostenvergleich Wärmepumpe vs. Gaskessel.

Echtes Verhalten: COP über das Carnot-Fraktion-Modell der HeatPump-Komponente bei
einer repräsentativen Außentemperatur; daraus Strombedarf, WP-Kosten und Ersparnis
gegenüber der Gas-Baseline. Keine Magic-Numbers: Wärmebedarf, Temperaturen und
Preise sind Pflicht.

Der COP bei *einer* repräsentativen Temperatur ist eine **Schätzung** (real ist er
last-/temperaturgewichtet über die Heizsaison) — so gekennzeichnet. Der volle
2-Pass-Dispatch (Lastgang, thermischer Speicher, Bivalenzpunkt, PV-Deckung) ist
Platzhalter (TODO.md).
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.components.heatpump import HeatPump


def _require_number(kwargs: dict[str, Any], feld: str, *, positiv: bool = True) -> float:
    wert = kwargs.get(feld)
    if wert is None:
        raise CapabilityError(f"{feld} ist erforderlich (keine erfundenen Annahmen)")
    wert = float(wert)
    if positiv and wert <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return wert


class HeatPumpCapability(Capability):
    """Wärmepumpe vs. Gaskessel: COP, Strombedarf, Jahreskosten, Ersparnis (diskret)."""

    name = "heatpump"
    summary = (
        "Heizkostenvergleich Wärmepumpe vs. Gaskessel (diskret): COP über das Carnot-Modell "
        "bei repräsentativer Außentemperatur, daraus Strombedarf, Jahreskosten und Ersparnis. "
        "COP bei einer Temperatur ist eine Schätzung; voller Lastgang-Dispatch ist Platzhalter."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "waermebedarf_kwh_jahr": {
                "type": "number",
                "description": "Jährlicher Wärmebedarf in kWh",
            },
            "vorlauftemperatur_c": {
                "type": "number",
                "description": "Heizungs-Vorlauftemperatur in °C",
            },
            "aussentemperatur_c": {
                "type": "number",
                "description": "Repräsentative Außentemperatur der Heizsaison in °C",
            },
            "strompreis_ct_kwh": {"type": "number", "description": "Strompreis brutto ct/kWh"},
            "gaspreis_ct_kwh": {
                "type": "number",
                "description": "Gaspreis brutto ct/kWh (thermisch)",
            },
            "gas_wirkungsgrad": {
                "type": "number",
                "description": "Wirkungsgrad des Gaskessels (Default 0.9)",
            },
        },
        "required": [
            "waermebedarf_kwh_jahr",
            "vorlauftemperatur_c",
            "aussentemperatur_c",
            "strompreis_ct_kwh",
            "gaspreis_ct_kwh",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        waermebedarf = _require_number(kwargs, "waermebedarf_kwh_jahr")
        vorlauf = _require_number(kwargs, "vorlauftemperatur_c", positiv=False)
        aussentemp = _require_number(kwargs, "aussentemperatur_c", positiv=False)
        strompreis = _require_number(kwargs, "strompreis_ct_kwh") / 100.0
        gaspreis = _require_number(kwargs, "gaspreis_ct_kwh") / 100.0
        gas_eff = float(kwargs.get("gas_wirkungsgrad", 0.9) or 0.9)
        if not 0 < gas_eff <= 1:
            raise CapabilityError("gas_wirkungsgrad muss in (0, 1] liegen")

        hp = HeatPump(inlet_temp_c=vorlauf)
        cop = hp.cop(outdoor_temp_c=aussentemp)
        hp_strom_kwh = waermebedarf / cop
        hp_kosten = hp_strom_kwh * strompreis
        gas_kosten = (waermebedarf / gas_eff) * gaspreis
        ersparnis = gas_kosten - hp_kosten

        return {
            "cop_schaetzung": round(cop, 3),
            "waermebedarf_kwh_jahr": waermebedarf,
            "wp_strombedarf_kwh_jahr": round(hp_strom_kwh, 1),
            "wp_kosten_eur_jahr": round(hp_kosten, 2),
            "gas_kosten_eur_jahr": round(gas_kosten, 2),
            "ersparnis_eur_jahr": round(ersparnis, 2),
            "rechenweg": {
                "vorlauftemperatur_c": vorlauf,
                "aussentemperatur_c": aussentemp,
                "cop": round(cop, 3),
                "wp_strom_kwh": round(hp_strom_kwh, 1),
                "strompreis_ct_kwh": round(strompreis * 100, 2),
                "gaspreis_ct_kwh": round(gaspreis * 100, 2),
                "gas_wirkungsgrad": gas_eff,
            },
            "hinweis": (
                "COP bei einer repräsentativen Außentemperatur ist eine Schätzung "
                "(real last-/temperaturgewichtet); voller Lastgang-Dispatch ist Platzhalter."
            ),
        }
