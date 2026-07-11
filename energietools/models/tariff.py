# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


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
    """Ein Energietarif (Strom oder Gas; Quelle: Katalog, Datenquelle oder eigene Rechnung)."""

    lieferant: str
    tarif_name: str
    energy_type: str = Field(default="POWER", description="POWER | GAS")
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
    # Präsentations-/Vertragsfelder (B.1-Port des Vergleichskerns; additiv/defaulted).
    neukundenrabatt_name: str = Field(
        default="", description="Name des Neukundenrabatts (z.B. '3 Cent/kWh Bonus')",
    )
    energiequellen_erneuerbar_pct: float = Field(
        default=0.0, description="Anteil erneuerbare Energie in %",
    )
    preisgarantie_monate: int | None = Field(
        default=None, description="Preisgarantie in Monaten (z.B. 12)",
    )
    preisanpassung: str = Field(
        default="", description="Preisanpassung: 'monatliche', 'quartalsweise', '' (=fix)",
    )
    # Zielgruppe: steuert NUR die Sichtbarkeit im jeweiligen Vergleich, nicht das
    # Ranking. Default "standard" = Haushaltsstrom; Heizstrom-Gruppen setzen einen
    # separaten Zählpunkt + Unterbrechbarkeit voraus.
    zielgruppe: str = Field(
        default="standard",
        description="standard | waermepumpe | elektroheizung | unterbrechbar",
    )
    unterbrechbar: bool = Field(
        default=False,
        description="True = eigener Zählpunkt + Unterbrechbarkeit erforderlich",
    )


class RegionalAusgeschlossen(BaseModel):
    """Ein regional ausgeschlossener Lieferant (Landesversorger fremdes Bundesland)."""

    brand: str
    region: list[str] = Field(default_factory=list, description="Bundesländer des Versorgers")


class VersorgerAbdeckungBlock(BaseModel):
    """Abdeckungs-Output-Block des Tarifvergleichs (B.2).

    Weist für die Vergleichs-PLZ aus, welche bekannten Lieferanten dort
    verfügbar sind, welche regional ausgeschlossen wurden und welche
    verfügbaren Lieferanten im verglichenen Katalog FEHLEN — damit ein
    Konsument (LLM/UI) die Grenzen des Vergleichs ehrlich benennen kann.
    """

    verfuegbar: list[str] = Field(
        default_factory=list, description="An der PLZ verfügbare Lieferanten (Brands)",
    )
    nicht_verfuegbar: list[RegionalAusgeschlossen] = Field(
        default_factory=list,
        description="Regional ausgeschlossene Lieferanten (mit ihrem Versorgungsgebiet)",
    )
    im_katalog_fehlend: list[str] = Field(
        default_factory=list,
        description="Verfügbare Lieferanten OHNE Tarif im verglichenen Katalog (Abdeckungslücke)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def im_katalog_fehlend_anzahl(self) -> int:
        """Skalarer Zähler der Abdeckungslücke — für numerische Caveat-Trigger
        (ein '> 0'-Vergleich auf der Liste selbst wäre ein Typfehler)."""
        return len(self.im_katalog_fehlend)


class TariffComparison(BaseModel):
    """Ergebnis eines Tarifvergleichs — vollständig deterministisch sortiert.

    Hinweis: der Vergleichs-Kern (Loop/Differenz/Ranking) lebt seit dem
    B.1-Move in ``energietools.capabilities.tariff_compare``; die proprietäre
    Datenbeschaffung bleibt beim Konsumenten (TariffSource/SpotPriceSource).
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
    versorger_abdeckung: VersorgerAbdeckungBlock | None = Field(
        default=None,
        description="Abdeckungs-Block (B.2): verfuegbar / nicht_verfuegbar / im_katalog_fehlend; "
        "None bei GAS (Abdeckungsdaten sind Strom-only)",
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
