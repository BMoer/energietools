# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Pydantic-Result-Modelle der Lastgang-Capabilities (L.1.7).

Typsicher + selbstdokumentierend (Schema-Doku über die Feldbeschreibungen).
``LastgangSignalsCapability._run`` gibt ``LastgangSignalsResult.model_dump(
mode="json")`` zurück — siehe Spec §0.2 (native ``Capability._run``-Rückgaben
werden NICHT automatisch normalisiert).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RueckfrageModel(BaseModel):
    """Eine signal-motivierte Rückfrage an den Haushalt (L.1.6)."""

    feld: str = Field(description="Datenmodell-Feld, das die Antwort befüllt")
    frage: str = Field(description="Die an den Haushalt gestellte Frage")
    motiviert_durch: str = Field(description="Welches Signal/Werte die Frage auslösen")


class LastgangSignalsResult(BaseModel):
    """Ergebnis von ``lastgang_signals`` (L.1) — Signale + Guards + Rückfragen.

    Jede Zahl trägt ihr Fenster/ihre Einheit als Begleitfeld (F7); jede
    Anteils-/Verhältnis-Kennzahl ihre Nenner-Definition in ``nenner`` (L.6).
    """

    # Signale (dreiwertig, str-Enum-Werte "likely"|"unlikely"|"unknown")
    electric_heating: str = Field(
        description="Elektrische Heizung wahrscheinlich? Bei PV-Guard ggf. auf "
        "'unknown' herabgestuft — siehe electric_heating_guarded/roh_ws_ratio."
    )
    pv_self_consumption: str = Field(description="PV-Eigenverbrauch wahrscheinlich?")
    high_continuous_load: str = Field(
        description="Dauerläufer (hohe Nacht-Grundlast) wahrscheinlich?"
    )

    # Rohkennzahlen MIT Fenster/Einheit (F7)
    winter_summer_ratio: float | None = Field(
        default=None, description="Ø Wintertag-kWh / Ø Sommertag-kWh"
    )
    night_base_w: int = Field(description="Median Nacht-Grundlast in Watt (Fenster: night_fenster)")
    night_fenster: str = Field(
        default="00:00–04:59", description="Fenster von night_base_w (F9-Entscheidung, L.1.5)"
    )
    midday_dip_ratio: float | None = Field(
        default=None,
        description="Median Mittag / Median Nacht (Fenster: midday_fenster im Rechenweg)",
    )
    evening_peak_hour: int = Field(description="Stunde (0-23) mit dem höchsten Ø-Bezug")
    weekday_weekend_ratio: float | None = Field(
        default=None, description="Ø Werktag-kWh / Ø Wochenendtag-kWh"
    )
    pv_feedin_kwh: float | None = Field(default=None, description="Eingespeiste Überschuss-Energie")

    # Guards (L.1.4)
    is_pv: bool = Field(description="PV-Flag der Eingabe (ggf. aus pv_feedin_kwh abgeleitet)")
    basis_label: str = Field(description="'Netzbezug' (is_pv=True) oder 'Verbrauch' (is_pv=False)")
    electric_heating_guarded: bool = Field(
        description="True, wenn ein LIKELY-Heizungssignal wegen PV auf 'unknown' herabgestuft wurde"
    )
    roh_ws_ratio: float | None = Field(
        default=None, description="Ungeguardetes winter_summer_ratio — nur gesetzt, wenn geguardet"
    )
    grundlast_p15_pv_artefakt: bool = Field(
        description="True, wenn eine übergebene grundlast_kw bei PV als Artefakt markiert wurde"
    )
    pv_flag_widerspruch: bool = Field(
        description="Warnfeld: Mittag > Nacht ist untypisch für PV-Bezug — kein Hard-Fail"
    )

    # Rückfragen (L.1.6)
    rueckfragen: list[RueckfrageModel] = Field(default_factory=list)

    # Rechenweg + Caveats (Zielbild-Prinzip 3)
    rechenweg: dict = Field(default_factory=dict, description="Schwellen, Fenster, Formeln")
    caveats: list[str] = Field(default_factory=list)
    nenner: dict[str, str] = Field(
        default_factory=dict, description="L.6: Nenner-Definition je Anteils-/Verhältnis-Kennzahl"
    )
