# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodelle für die publizierten Energiegemeinschafts-Daten (offline, auditierbar).

Spiegelt 1:1 die Form der JSON-Dateien in ``data/energiegemeinschaften/``:
Rechtsformen-Fakten (``fakten.json``), Verzeichnis-Snapshot (``verzeichnis.json``,
initial leer — wird vom Quellen-Wächter-Scraper befüllt) und BEG-Anbieter
(``beg_providers.json``, migriert aus dem alten ``data/beg_providers.json``).

Weniger strukturierte, stark verschachtelte Blöcke (``elwg_aenderung``,
``marktstand``, ``netzentgelt_reduktion``) bleiben bewusst als
``dict[str, object]`` (wie ``Abgaben.federal`` im Netz-Package) statt sie in
tief verschachtelte Submodelle zu zwingen — die Rechtsform selbst (das, was
die Capability tatsächlich filtert) ist strukturiert.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EgQuelle(BaseModel):
    """Eine Quellenangabe (URL + Abrufdatum + Typ)."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(default="")
    abrufdatum: str = Field(default="")
    typ: str = Field(default="", description="'primaer' oder 'sekundaer'")


class Rechtsform(BaseModel):
    """Eine Energiegemeinschafts-Rechtsform (GEA, EEG lokal/regional, BEG)."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Name der Rechtsform")
    raeumliche_grenze: str = Field(default="")
    energiequelle: str = Field(default="")
    energieform: str = Field(default="")
    rechtsform_noetig: bool = Field(default=False)
    rechtsform_hinweis: str = Field(default="")
    wer_darf_mitmachen: str = Field(default="")
    netzentgelt_reduktion: dict[str, object] = Field(default_factory=dict)
    abgabenbefreiung: str = Field(default="")
    automatische_verrechnung: str = Field(default="")
    quellen: tuple[EgQuelle, ...] = Field(default=())
    verlaesslichkeit: str = Field(default="verifiziert", description="'verifiziert'|'unsicher'")
    unsicher_grund: str | None = Field(default=None)


class BeitrittsSchritt(BaseModel):
    """Ein Schritt im Beitrittsprozess zu einer Energiegemeinschaft."""

    model_config = ConfigDict(frozen=True)

    schritt: int
    titel: str = Field(default="")
    beschreibung: str = Field(default="")


class EnergiegemeinschaftenFakten(BaseModel):
    """Die Rechtsformen-/ElWG-/Markt-Fakten aus ``fakten.json``."""

    model_config = ConfigDict(frozen=True)

    rechtsformen: dict[str, Rechtsform] = Field(default_factory=dict)
    elwg_aenderung: dict[str, object] = Field(default_factory=dict)
    marktstand: dict[str, object] = Field(default_factory=dict)
    beitrittsschritte: tuple[BeitrittsSchritt, ...] = Field(default=())
    beitrittsschritte_quellen: tuple[EgQuelle, ...] = Field(default=())
    fazit_haushalt: str = Field(default="")
    offene_punkte: tuple[str, ...] = Field(default=())
    verzeichnis_quellen_info: dict[str, object] = Field(default_factory=dict)


class VerzeichnisEintrag(BaseModel):
    """Ein Eintrag im Energiegemeinschafts-Verzeichnis-Snapshot.

    ``verzeichnis.json`` wird nächtlich aus der amtlichen Landkarte
    (energiegemeinschaften.gv.at/landkarte/) befüllt —
    ``gridbert/scrapers/eeg_verzeichnis.py`` über den ``publish``-Job von
    ``tariff-refresh.yml``. Die Landkarte ist BEG-only und freiwillig befüllt
    (~18 % der amtlich gezählten BEG), deshalb trägt jede Ausspielung den
    Unvollständigkeits-Hinweis mit. Kontaktdaten sind bewusst kein Feld: die
    Nutzungsbedingung der Koordinierungsstelle untersagt Werbenutzung.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    bundesland: str | None = Field(default=None)
    plz: str | None = Field(default=None)
    typ: str = Field(default="")
    quelle: str = Field(default="")
    stand: str = Field(default="")


class BegProviderEntry(BaseModel):
    """Ein bundesweit beitretbarer BEG-Anbieter (migriert aus beg_providers.json)."""

    model_config = ConfigDict(frozen=True)

    name: str
    preis_ct_kwh: float = Field(default=0.0)
    einmalkosten_eur: float = Field(default=0.0)
    versorgungsanteil: float = Field(default=0.5)
    typ: str = Field(default="")
    url: str = Field(default="")
    notiz: str = Field(default="")


class EnergiegemeinschaftenManifest(BaseModel):
    """Metadaten des Energiegemeinschafts-Daten-Snapshots (Provenance, Coverage, Lizenz)."""

    model_config = ConfigDict(frozen=True)

    data_version: str = Field(default="")
    generated_at: str = Field(default="")
    market: str = Field(default="AT")
    domain: str = Field(default="energiegemeinschaften")
    stand_recherche: str = Field(default="")
    coverage: dict[str, object] = Field(default_factory=dict)
    provenance: str = Field(default="")
    source_repo: str = Field(default="")
    methodik: str = Field(default="")
    license: str = Field(default="")
    disclaimer: str = Field(default="")
