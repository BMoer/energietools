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

from datetime import date, datetime

from pydantic import BaseModel, Field


# Ab wann ein Katalogpreis als „nicht mehr bestätigt" gilt. 14 Tage, weil der
# Katalog nächtlich erhoben wird: ein Anbieter, der zwei Wochen lang an keinem
# einzigen Tag nachprüfbar war, hat ein Quellenproblem und keine ruhige
# Preisphase. Der Wert wird KENNZEICHNEND verwendet, nie ausschließend — ein
# Tarif verschwindet nie aus dem Vergleich, er trägt sein Datum sichtbar.
PREIS_MAX_ALTER_TAGE = 14


def _tage_seit(iso_datum: str) -> int | None:
    """Kalendertage seit einem ISO-Datum. ``None``, wenn unlesbar oder leer.

    Akzeptiert reine Datumsteile und volle Zeitstempel (der Exporter liefert
    letztere). Ein Zukunftsdatum ergibt 0, nicht negativ — sonst könnte eine
    schiefe Uhr einen Preis „frischer als heute" aussehen lassen.
    """
    roh = (iso_datum or "").strip()
    if not roh:
        return None
    try:
        stand = datetime.fromisoformat(roh).date()
    except ValueError:
        try:
            stand = date.fromisoformat(roh[:10])
        except ValueError:
            return None
    return max((date.today() - stand).days, 0)


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

    # Wann dieser Preis zuletzt an der Quelle BESTÄTIGT werden konnte — eine
    # andere Frage als gueltig_ab („seit wann gilt er"). Ein Anbieter, dessen
    # Preisblatt seit Wochen nicht erreichbar ist, behält seinen Preis
    # unverändert im Katalog und sieht dort so gültig aus wie ein täglich
    # bestätigter. Additiv/defaulted: ältere Snapshots ohne das Feld gelten als
    # „nie gemessen", nicht als veraltet.
    zuletzt_bestaetigt: str = Field(
        default="", description="Zuletzt an der Quelle bestätigt (ISO); leer = nie gemessen",
    )

    def preis_alter_tage(self) -> int | None:
        """Tage seit der letzten Bestätigung. ``None`` = nie gemessen."""
        return _tage_seit(self.zuletzt_bestaetigt)

    @property
    def preis_veraltet(self) -> bool:
        """Konnte der Preis seit mehr als ``PREIS_MAX_ALTER_TAGE`` nicht bestätigt werden?

        Ein Hinweis, kein Ausschluss. Ohne Datum ``False`` — ungemessen ist
        nicht dasselbe wie veraltet, und ein Hinweis, der auf jeden Tarif eines
        älteren Snapshots zutrifft, wäre wertlos.
        """
        alter = self.preis_alter_tage()
        return alter is not None and alter > PREIS_MAX_ALTER_TAGE

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
