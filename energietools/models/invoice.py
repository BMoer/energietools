# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EnergieBlock(BaseModel):
    """Extrahierte Daten für einen Energieträger (Strom oder Gas)."""

    lieferant: str = Field(default="", description="Name des Lieferanten")
    tarif_name: str = Field(default="", description="Name des Tarifs")
    energiepreis_ct_kwh: float = Field(default=0.0, description="Energiepreis in ct/kWh brutto")
    grundgebuehr_eur_monat: float = Field(default=0.0, description="Grundgebühr in €/Monat brutto")
    energiekosten_eur: float = Field(default=0.0, description="Energiekosten in €/Jahr brutto")
    jahresverbrauch_kwh: float = Field(default=0.0, description="Jahresverbrauch in kWh")
    zaehlpunkt: str = Field(default="", description="Zählpunktnummer (AT00...)")
    netzkosten_eur_jahr: float | None = Field(
        default=None, description="Netzkosten in €/Jahr falls auf Rechnung"
    )


class Invoice(BaseModel):
    """Extrahierte Daten aus einer Energierechnung (Strom, Gas oder Kombi)."""

    # --- Energietyp-Erkennung -------------------------------------------------
    energieart: Literal["strom", "gas", "kombi"] = Field(
        default="strom",
        description="Erkannter Energieträger: strom, gas, oder kombi (Strom+Gas auf einer Rechnung)",
    )

    # --- Haupt-Daten (bei strom/gas: die extrahierten Daten, bei kombi: Strom-Daten) ---
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

    # --- Gas-Block (nur befüllt bei energieart="kombi") -----------------------
    gas: EnergieBlock | None = Field(
        default=None,
        description="Gas-Daten bei Kombi-Rechnungen. None wenn reine Strom- oder Gas-Rechnung.",
    )

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
