# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodelle für die publizierten Energieberatungsstellen-Daten (offline, auditierbar)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BeratungQuelle(BaseModel):
    """Eine Quellenangabe (URL + Abrufdatum + Typ)."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(default="")
    abrufdatum: str = Field(default="")
    typ: str = Field(default="", description="'primaer' oder 'sekundaer'")


class BeratungsstelleEntry(BaseModel):
    """Die (kostenlose, produktneutrale) Energieberatungsstelle eines Bundeslands."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Eindeutiger Schlüssel (z.B. 'beratung-wien')")
    bundesland: str = Field(description="Eines der 9 österreichischen Bundesländer")
    name: str = Field(description="Name der Beratungsstelle")
    traeger: str = Field(default="", description="Träger-Organisation(en)")
    kosten: str = Field(default="", description="z.B. 'kostenlos'")
    url: str | None = Field(default=None)
    quellen: tuple[BeratungQuelle, ...] = Field(default=())
    verlaesslichkeit: str = Field(default="verifiziert", description="'verifiziert'|'unsicher'")
    unsicher_grund: str | None = Field(default=None)


class BeratungManifest(BaseModel):
    """Metadaten des Beratungsstellen-Daten-Snapshots (Provenance, Coverage, Lizenz)."""

    model_config = ConfigDict(frozen=True)

    data_version: str = Field(default="")
    generated_at: str = Field(default="")
    market: str = Field(default="AT")
    domain: str = Field(default="beratung")
    stand_recherche: str = Field(default="")
    coverage: dict[str, object] = Field(default_factory=dict)
    provenance: str = Field(default="")
    source_repo: str = Field(default="")
    methodik: str = Field(default="")
    license: str = Field(default="")
    disclaimer: str = Field(default="")
