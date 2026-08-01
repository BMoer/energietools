# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodell für die publizierten Solar/Speicher-Marktdaten (offline, auditierbar).

Rein informativ (Vermittler, Hersteller/Händler, Speicherpreis-Referenz,
Balkonkraftwerk-Regeln, Ausschluss-Liste) — **keine Empfehlungs-, Ranking- oder
Provisionslogik**, daher (noch) keine eigene Capability (B1-Spec listet nur
``foerderungen``/``beratung``/``energiegemeinschaften`` als Capabilities).

Die einzelnen Kategorien sind untereinander stark heterogen (unterschiedliche
Felder je Anbieter-Typ) — wie ``Abgaben.federal`` im Netz-Package bleiben sie
bewusst als ``dict[str, object]`` statt in starre Submodelle gezwungen zu
werden. Der Snapshot selbst ist ``frozen`` (immutable).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SolarSpeicherDaten(BaseModel):
    """Der komplette Solar/Speicher-Marktdaten-Snapshot (1:1 aus solar_speicher.json)."""

    model_config = ConfigDict(frozen=True)

    vermittler: tuple[dict[str, object], ...] = Field(default=())
    energieversorger_pv_pakete: tuple[dict[str, object], ...] = Field(default=())
    hersteller_haendler_speicher: tuple[dict[str, object], ...] = Field(default=())
    speicherpreis_referenz: dict[str, object] = Field(default_factory=dict)
    balkonkraftwerk_regeln: dict[str, object] = Field(default_factory=dict)
    balkonkraftwerk_anbieter: dict[str, object] = Field(default_factory=dict)
    ausgeschlossen: tuple[dict[str, object], ...] = Field(default=())


class MarktdatenManifest(BaseModel):
    """Metadaten des Marktdaten-Snapshots (Provenance, Coverage, Lizenz)."""

    model_config = ConfigDict(frozen=True)

    data_version: str = Field(default="")
    generated_at: str = Field(default="")
    market: str = Field(default="AT")
    domain: str = Field(default="marktdaten_solar_speicher")
    stand_recherche: str = Field(default="")
    coverage: dict[str, object] = Field(default_factory=dict)
    provenance: str = Field(default="")
    source_repo: str = Field(default="")
    methodik: str = Field(default="")
    license: str = Field(default="")
    disclaimer: str = Field(default="")
