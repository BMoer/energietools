# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pydantic import BaseModel, Field


class Rechenweg(BaseModel):
    """Transparenter Berechnungsweg für einen Tarif — ermöglicht Nachvollziehbarkeit.

    Gebrauchsabgabe ist ein EIGENER Brutto-Block (``gebrauchsabgabe_eur``), NICHT in
    ``brutto_jahreskosten_eur`` enthalten; USt liegt nur auf Energie+Grund nach Rabatt
    (separate-Block-Modell, 1:1 wie gridbert.models.Rechenweg).
    """

    energiepreis_netto_ct_kwh: float = Field(description="Netto-Energiepreis ct/kWh (ohne USt)")
    grundgebuehr_netto_eur_monat: float = Field(description="Netto-Grundgebühr EUR/Monat")
    netto_energie_eur: float = Field(description="Verbrauch × Netto-Energiepreis")
    netto_grund_eur: float = Field(description="Netto-Grundgebühr × 12 Monate")
    netto_gesamt_eur: float = Field(description="Netto-Energie + Netto-Grund")
    neukundenrabatt_netto_eur: float = Field(
        default=0.0, description="Neukundenrabatt netto EUR (Jahr 1, vor Steuer)",
    )
    netto_nach_rabatt_eur: float = Field(
        default=0.0, description="Netto-Gesamt nach Abzug Neukundenrabatt (= netto_gesamt ohne Rabatt)",
    )
    gebrauchsabgabe_rate: float = Field(
        description="Gebrauchsabgabe-Satz (Prozent-Regeln z.B. 0.07; 0 bei ct/kWh-Regeln)"
    )
    gebrauchsabgabe_eur: float = Field(
        description="Gebrauchsabgabe BRUTTO, eigener Block (NICHT in brutto_jahreskosten_eur)"
    )
    ust_eur: float = Field(description="Umsatzsteuer 20% auf Energie+Grund nach Rabatt")
    brutto_jahreskosten_eur: float = Field(
        description="Endwert Energie: netto_nach_rabatt × 1,20 (ohne Netz, ohne Gebrauchsabgabe)"
    )
    quelle: str = Field(default="berechnet", description="Datenquelle des Rechenwegs (z.B. 'katalog', 'berechnet')")
    hinweis: str = Field(
        default="",
        description="Zusätzliche Info (z.B. 'Gebrauchsabgabe nicht verfügbar')",
    )


class Tariff(BaseModel):
    """Ein Stromtarif (Quelle: Open-Data-Katalog oder eigene Rechnung)."""

    lieferant: str
    tarif_name: str
    energiepreis_ct_kwh: float
    grundgebuehr_eur_monat: float
    jahreskosten_eur: float = Field(
        description="Energiekosten €/Jahr Jahr 1 inkl. Rabatt (Energie + Grundgebühr, OHNE Netz und Gebrauchsabgabe)"
    )
    jahreskosten_ohne_rabatt_eur: float = Field(default=0.0, description="Energiekosten €/Jahr ab Jahr 2 (ohne Neukundenrabatt)")
    gesamtkosten_eur: float = Field(default=0.0, description="Gesamtkosten €/Jahr inkl. Netzkosten")
    ersparnis_eur: float = Field(default=0.0, description="Ersparnis vs. aktueller Tarif in €/Jahr")
    ist_oekostrom: bool = False
    tariftyp: str = Field(default="Fixpreis", description="Fixpreis, Monatsfloater oder Stundenfloater")
    preismodell: str = Field(default="", description="Festpreis | Festpreis mit Garantie | Floater")
    hat_bindung: bool = Field(default=False, description="True = Mindestvertragsdauer")
    kategorie: str = Field(default="fix", description="Kategorie: fix, floater, gruen")
    quelle: str = Field(default="katalog", description="Datenquelle")
    wechsel_link: str = Field(default="", description="Direktlink zur Anbieter-Anmeldung")
    # Kosten-relevante Felder (S4: an gridbert angeglichen, defaulted/additiv).
    gebrauchsabgabe_eur: float = Field(
        default=0.0,
        description="Gebrauchsabgabe €/Jahr brutto — eigener Block (NICHT in jahreskosten_eur)",
    )
    neukundenrabatt_eur: float = Field(
        default=0.0, description="Neukundenrabatt brutto EUR (Pauschale, Jahr 1)",
    )
    neukundenrabatt_ct_kwh: float = Field(
        default=0.0, description="Neukundenrabatt netto ct/kWh (Jahr 1, falls per-kWh statt Pauschale)",
    )
    spot_aufschlag_ct: float = Field(
        default=0.0, description="Lieferanten-Aufschlag auf den Spot-Index (netto ct/kWh)",
    )
    spot_index: str = Field(default="", description="Börsenindex des Spot-Tarifs, z.B. 'EPEX AT'")
    ist_biogas: bool = Field(default=False, description="Gas-Ökoflag (Biogas-Anteil)")
    rechenweg: Rechenweg | None = Field(default=None, description="Transparenter Berechnungsweg")


class TariffComparison(BaseModel):
    """Container eines Tarifvergleichs (Datenmodell).

    Hinweis: die Vergleichs-LOGIK (Ersparnis/Ranking/Kategorien) lebt seit S4 im
    Produkt (gridbert), nicht in energietools — et ist die reine Kosten-Engine.
    Dieses Modell bleibt als Datencontainer für Konsumenten erhalten.
    """

    aktueller_tarif: Tariff
    alternativen: list[Tariff] = Field(default_factory=list)
    plz: str = ""
    jahresverbrauch_kwh: float = 0.0
    netzkosten_eur_jahr: float = Field(default=0.0, description="Regulierte Netzkosten €/Jahr brutto")
    netzbetreiber: str = Field(default="", description="Name des Netzbetreibers")
    gebrauchsabgabe_rate: float = Field(
        default=0.0,
        description="Gebrauchsabgabe-Satz für diese PLZ (z.B. 0.07 für Wien)",
    )

    # Pre-sorted category lists (vom Konsumenten befüllt)
    beste_fix: list[Tariff] = Field(default_factory=list)
    beste_floater: list[Tariff] = Field(default_factory=list)
    beste_gruen: list[Tariff] = Field(default_factory=list)
    bester_gesamt: Tariff | None = None
    max_ersparnis_eur: float = 0.0

    @property
    def bester_tarif(self) -> Tariff | None:
        """Backward-compat: cheapest alternative overall."""
        return self.bester_gesamt
