# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Datenmodelle für die publizierten Förderungs-Daten (offline, auditierbar).

Alle Modelle sind ``frozen`` (immutable) — spiegeln 1:1 die Form der
JSON-Einträge in ``data/foerderungen/foerderungen.json``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FoerderQuelle(BaseModel):
    """Eine Quellenangabe (URL + Abrufdatum + Typ)."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(default="", description="Quell-URL")
    abrufdatum: str = Field(default="", description="Abrufdatum (ISO-Datum)")
    typ: str = Field(default="", description="'primaer' oder 'sekundaer'")


class FoerderhoeheWert(BaseModel):
    """Ein einzelner beschrifteter Fördersatz-Wert (z.B. eine Kategorie-Stufe)."""

    model_config = ConfigDict(frozen=True)

    bezeichnung: str = Field(default="", description="Bezeichnung dieses Werts")
    wert: str = Field(default="", description="Der Wert als Text (z.B. '150 €/kWp')")


class Foerderhoehe(BaseModel):
    """Die Förderhöhe eines Eintrags — strukturiert (werte) + lesbarer Text."""

    model_config = ConfigDict(frozen=True)

    typ: str = Field(
        default="",
        description="'pauschale'|'prozent'|'satz_pro_kwp'|'satz_pro_kwh'|'gemischt'",
    )
    werte: tuple[FoerderhoeheWert, ...] = Field(default=())
    text: str = Field(default="", description="Lesbare Zusammenfassung der Förderhöhe")


class FoerderungEntry(BaseModel):
    """Eine einzelne Förderung (Bund oder Land), mit Status, Höhe und Quellen.

    ``verlaesslichkeit: "unsicher"`` bleibt Teil des Datensatzes (transparent,
    mit ``unsicher_grund``), wird aber von der Capability standardmäßig
    ausgefiltert (Parameter ``inkl_unsicher=False``) — Rohdaten-Grundsatz:
    unsichere Einträge nie stillschweigend als Fakt ausspielen.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Eindeutiger Schlüssel (z.B. 'bund-eag-invest-pv-speicher')")
    ebene: str = Field(description="'bund' oder 'land'")
    bundesland: str | None = Field(default=None, description="Bundesland (None bei ebene='bund')")
    kategorie: str = Field(description="z.B. 'pv', 'speicher', 'heizungstausch', 'sanierung'")
    name: str = Field(description="Name der Förderung")
    foerderstelle: str = Field(default="", description="Abwickelnde Stelle")
    status: str = Field(description="'offen'|'geschlossen'|'unsicher'")
    status_seit: str | None = Field(default=None, description="Status gilt seit (ISO-Datum)")
    status_detail: str = Field(default="", description="Ausführlicher Status-/Kontext-Text")
    foerderhoehe: Foerderhoehe = Field(default_factory=Foerderhoehe)
    bedingungen: tuple[str, ...] = Field(default=())
    zielgruppe: str = Field(default="")
    antrags_url: str | None = Field(default=None)
    quellen: tuple[FoerderQuelle, ...] = Field(default=())
    verlaesslichkeit: str = Field(default="verifiziert", description="'verifiziert'|'unsicher'")
    unsicher_grund: str | None = Field(default=None)
    naechstes_fenster: str | None = Field(
        default=None, description="ISO-Datumsspanne 'YYYY-MM-DD/YYYY-MM-DD', z.B. nächster Call"
    )


class FoerderungenManifest(BaseModel):
    """Metadaten des Förderungs-Daten-Snapshots (Provenance, Coverage, Lizenz)."""

    model_config = ConfigDict(frozen=True)

    data_version: str = Field(default="")
    generated_at: str = Field(default="")
    market: str = Field(default="AT")
    domain: str = Field(default="foerderungen")
    stand_recherche: str = Field(default="")
    coverage: dict[str, object] = Field(default_factory=dict)
    provenance: str = Field(default="")
    source_repo: str = Field(default="")
    methodik: str = Field(default="")
    license: str = Field(default="")
    disclaimer: str = Field(default="")
