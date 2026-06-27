# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodelle des Open-Data-Tarifkatalogs.

``CatalogTariff`` ist ein normalisierter Eintrag aus ``data/tariffs/catalog.json``
— Netto-Listenpreise eines österreichischen Stromtarifs, first-party gescrapt.
Die Vergleichs-Ergebnismodelle (``Tariff``, ``Rechenweg``, ``TariffComparison``)
werden aus ``energietools.models`` wiederverwendet, damit der auditierbare
Rechenweg über das ganze Toolkit identisch bleibt.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogTariff(BaseModel):
    """Ein normalisierter Tarif-Eintrag aus dem Open-Data-Katalog.

    Alle Preise sind **netto Listenpreise** (ohne USt, vor Rabatt). Spot-/
    Floater-Tarife haben keinen festen ``energiepreis_ct_kwh`` (=0), sondern
    einen ``spot_aufschlag_ct`` auf einen Börsenindex.
    """

    key: str = Field(description="Anbieter-Key (Scraper-Quelle)")
    lieferant: str
    tarif_name: str
    energy_type: str = Field(
        default="POWER",
        description="POWER (Strom) | GAS — der Open-Data-Katalog ist Strom-only; "
        "Gas-Einträge werden beim Laden gefiltert (siehe catalog._ist_gas_eintrag).",
    )
    tariftyp: str = Field(
        default="Fixpreis", description="Fixpreis | Monatsfloater | Stundenfloater",
    )
    preismodell: str = Field(
        default="", description="Festpreis | Festpreis mit Garantie | Floater",
    )

    energiepreis_ct_kwh: float = Field(default=0.0, description="Netto ct/kWh (0 bei Spot/Floater)")
    grundgebuehr_eur_monat: float = Field(default=0.0, description="Netto EUR/Monat")
    spot_aufschlag_ct: float = Field(default=0.0, description="Netto Aufschlag auf den Börsenindex")
    spot_index: str = Field(default="", description="z.B. 'EPEX AT'")

    ist_oekostrom: bool = False
    energiequellen_erneuerbar_pct: float = 0.0

    neukundenrabatt_eur: float = 0.0
    neukundenrabatt_ct_kwh: float = 0.0
    neukundenrabatt_name: str = ""

    preisgarantie_monate: int | None = None
    hat_bindung: bool = False
    preisanpassung: str = ""
    wechsel_link: str = ""

    # S7 Tarif-Historie: jede Version trägt ihre Gültigkeit (ISO-Datum). Leeres
    # gueltig_bis = aktuell offen/gültig; leeres gueltig_ab = seit Snapshot-Beginn.
    # Additiv/defaulted → alte Katalog-Einträge (ohne diese Felder) bleiben "aktuell".
    gueltig_ab: str = Field(default="", description="Gültig ab (ISO-Datum); leer = seit Beginn")
    gueltig_bis: str = Field(default="", description="Gültig bis (ISO-Datum); leer = aktuell offen")

    @property
    def ist_spot(self) -> bool:
        """True, wenn der Tarif keinen festen Energiepreis hat (Spot/Floater)."""
        return self.energiepreis_ct_kwh <= 0.0 and self.spot_aufschlag_ct > 0.0


class CatalogManifest(BaseModel):
    """Metadaten des Katalog-Snapshots (Provenance, Coverage, Lizenz)."""

    catalog_version: str
    generated_at: str
    market: str = "AT"
    energy_type: str = "POWER"
    price_basis: str = "netto_listenpreis"
    tariff_count: int = 0
    # S7: Tarif-Historie. ``stand`` = Stichtag des aktuell-gültigen Schnitts;
    # ``versionen_gesamt`` = alle Versionen (inkl. geschlossener) im Snapshot.
    stand: str = Field(default="", description="Stichtag des aktuell-gültigen Schnitts (ISO-Datum)")
    versionen_gesamt: int = Field(default=0, description="Versionen gesamt (inkl. geschlossener)")
    provider_coverage: dict = Field(default_factory=dict)
    provenance: str = ""
    license: str = "MIT"
    disclaimer: str = ""
