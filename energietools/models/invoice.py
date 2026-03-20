# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pydantic import BaseModel, Field


class Invoice(BaseModel):
    """Extrahierte Daten aus einer Stromrechnung."""

    lieferant: str = Field(description="Name des Stromlieferanten")
    tarif_name: str = Field(default="", description="Name des Tarifs")
    energiepreis_ct_kwh: float = Field(description="Energiepreis in ct/kWh brutto")
    grundgebuehr_eur_monat: float = Field(default=0.0, description="Grundgebühr in €/Monat brutto")
    energiekosten_eur: float = Field(default=0.0, description="Gesamte Energiekosten in €/Jahr brutto (Arbeitspreis + Grundgebühr)")
    jahresverbrauch_kwh: float = Field(description="Jahresverbrauch in kWh")
    plz: str = Field(description="Postleitzahl")
    zaehlpunkt: str = Field(default="", description="Zählpunktnummer (AT00...)")
    netzkosten_eur_jahr: float | None = Field(
        default=None, description="Netzkosten in €/Jahr falls auf Rechnung"
    )
    kunde_name: str = Field(default="", description="Name des Kunden (von der Rechnung)")
    adresse: str = Field(default="", description="Vollständige Adresse des Kunden")

    # --- Abrechnungszeitraum (Period tracking) --------------------------------
    zeitraum_von: str = Field(
        default="", description="Beginn des Abrechnungszeitraums (TT.MM.JJJJ oder ISO)"
    )
    zeitraum_bis: str = Field(
        default="", description="Ende des Abrechnungszeitraums (TT.MM.JJJJ oder ISO)"
    )
    zeitraum_tage: int | None = Field(
        default=None, description="Dauer des Abrechnungszeitraums in Tagen"
    )
    ist_hochgerechnet: bool = Field(
        default=False,
        description="True wenn Verbrauch/Kosten von Teilzeitraum auf 365 Tage hochgerechnet",
    )
    original_verbrauch_kwh: float | None = Field(
        default=None,
        description="Originalverbrauch vor Hochrechnung (nur bei ist_hochgerechnet=True)",
    )
    original_energiekosten_eur: float | None = Field(
        default=None,
        description="Original-Energiekosten vor Hochrechnung (nur bei ist_hochgerechnet=True)",
    )
