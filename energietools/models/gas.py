# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Pydantic Models für Gas-Tarife."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class GasRechenweg(BaseModel):
    """Transparenter Rechenweg für Gas-Tarif-Jahreskosten."""

    gaspreis_netto_ct_kwh: float = 0.0
    grundgebuehr_netto_eur_monat: float = 0.0
    netto_energie_eur: float = 0.0
    netto_grund_eur: float = 0.0
    netto_gesamt_eur: float = 0.0
    co2_bepreisung_eur: float = 0.0
    gebrauchsabgabe_rate: float = 0.0
    gebrauchsabgabe_eur: float = 0.0
    netto_inkl_abgaben_eur: float = 0.0
    ust_eur: float = 0.0
    brutto_jahreskosten_eur: float = 0.0
    quelle: str = ""
    hinweis: str = ""


class GasTariff(BaseModel):
    """Ein einzelner Gas-Tarif."""

    anbieter: str
    tarif_name: str
    gaspreis_ct_kwh: float  # brutto
    grundgebuehr_eur_monat: float = 0.0
    jahreskosten_eur: float = 0.0  # brutto inkl. aller Abgaben
    ersparnis_eur: float = 0.0
    ist_biogas: bool = False
    tariftyp: str = ""  # "Fixpreis" | "Monatsfloater"
    quelle: str = "e-control"
    rechenweg: GasRechenweg | None = None

    def jahreskosten(self, verbrauch_kwh: float) -> float:
        """Jahreskosten berechnen (Fallback wenn jahreskosten_eur nicht gesetzt)."""
        if self.jahreskosten_eur > 0:
            return self.jahreskosten_eur
        return (verbrauch_kwh * self.gaspreis_ct_kwh / 100) + (self.grundgebuehr_eur_monat * 12)


class GasTariffComparison(BaseModel):
    """Ergebnis eines Gas-Tarifvergleichs."""

    plz: str
    jahresverbrauch_kwh: float
    tarife: list[GasTariff] = Field(default_factory=list)
    aktueller_tarif: GasTariff | None = None
    netzkosten_eur_jahr: float = 0.0
    netzbetreiber: str = ""
    gebrauchsabgabe_rate: float = 0.0

    @computed_field
    @property
    def bester_tarif(self) -> GasTariff | None:
        """Günstigster Tarif."""
        if not self.tarife:
            return None
        return min(self.tarife, key=lambda t: t.jahreskosten_eur if t.jahreskosten_eur > 0 else t.jahreskosten(self.jahresverbrauch_kwh))

    @computed_field
    @property
    def max_ersparnis_eur(self) -> float:
        """Maximale Ersparnis gegenüber aktuellem Tarif."""
        if not self.aktueller_tarif or not self.tarife:
            return 0.0
        aktuelle_kosten = self.aktueller_tarif.jahreskosten(self.jahresverbrauch_kwh)
        best = self.bester_tarif
        if not best:
            return 0.0
        return max(0.0, aktuelle_kosten - best.jahreskosten(self.jahresverbrauch_kwh))
