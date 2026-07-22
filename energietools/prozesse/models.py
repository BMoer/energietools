# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Das Prozess-Format (D7): sieben Blöcke, YAML als Quelle.

Ein Prozess ist ein Gesprächsleitfaden für einen konkreten Anwendungsfall
(„was kann Gridbert", „Rechnung → Tarifvergleich") — kein Freitext-Prompt,
sondern eine strukturierte, lintbare Definition: ``meta``, ``ziel``,
``benoetigte_daten``, ``fragen``, ``tool_mapping``, ``datenqualitaet_abbruch``,
``caveats``. Siehe ARCHITECTURE-2.0.md D7 für die volle Herleitung.

``quelle`` bei ``ToolMappingSchritt`` unterscheidet, wogegen der Struktur-
Linter eine referenzierte Capability prüft: ``"energietools"`` (Default) sind
echte Capabilities dieses Repos — gelintet gegen ``default_registry()``.
``"extern"`` sind Tools, die NICHT in energietools leben (Engram-Vault-Tools
wie ``search_pages``, Gridbert-Domänen-Tools wie ``submit_invoice_facts``) —
gelintet gegen die dokumentierte v1-Gateway-Katalog-Liste in
``external_tools.py``. Ohne diese Unterscheidung könnte ein Prozess keine
Tools referenzieren, die zwar Teil des v1-MCP-Katalogs (ARCHITECTURE-2.0.md
§3.3 WP-G1) sind, aber außerhalb dieses Repos implementiert werden.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ProzessMeta(BaseModel):
    """Block 1: Identität + Version (analog zum data/-MANIFEST-Muster)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    prozess_version: str
    stand: date
    market: str = "AT"
    license: str = "MIT"

    @field_validator("prozess_version")
    @classmethod
    def _validiere_semver(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(
                f"prozess_version '{v}' ist kein SemVer (erwartet z.B. '1.0.0')",
            )
        return v


class BenoetigtesDatum(BaseModel):
    """Ein Eintrag im Block ``benoetigte_daten``."""

    model_config = ConfigDict(extra="forbid")

    feld: str = Field(min_length=1)
    quelle: str = Field(min_length=1)  # z.B. "rechnung", "rechnung|frage", "instanz"
    pflicht: bool
    format: str | None = None


class Frage(BaseModel):
    """Ein Eintrag im Block ``fragen`` — Reihenfolge nach Hebel (D7)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    hebel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    feld: str | None = None  # welches benoetigte_daten-Feld diese Frage füllt
    bedingung: str | None = None  # nur stellen, wenn diese Bedingung zutrifft
    ableitung: str | None = None  # wie unscharfe Antworten in Parameter überführt werden


class ToolMappingSchritt(BaseModel):
    """Ein Eintrag im Block ``tool_mapping`` — das lintbare Herzstück (D7)."""

    model_config = ConfigDict(extra="forbid")

    schritt: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    quelle: Literal["energietools", "extern"] = "energietools"
    # "aktiv" = wird in diesem Prozess wirklich aufgerufen (Pflicht-Input-Deckung
    # wird geprüft). "ausblick" = wird nur als nächster Schritt genannt, nicht
    # aufgerufen (z.B. tariff_compare/get_switch_info im Erstkontakt) — Existenz
    # wird trotzdem geprüft (Stale-Doku-Risiko), Pflicht-Input-Deckung nicht.
    rolle: Literal["aktiv", "ausblick"] = "aktiv"
    pflicht_inputs: list[str] = Field(default_factory=list)
    # Capability-Inputs, die der Prozess/das LLM zur Aufrufzeit wählt (z.B. ein
    # Enum-Parameter wie 'thema' bei get_knowledge) statt vom Haushalt zu
    # erfragen — deshalb bewusst NICHT in benoetigte_daten/fragen und von der
    # Pflicht-Input-Deckungsprüfung ausgenommen (nur für 'aktiv'-Schritte relevant).
    nicht_benutzerdaten: list[str] = Field(default_factory=list)
    regeln: list[str] = Field(default_factory=list)


class Caveat(BaseModel):
    """Ein Eintrag im Block ``caveats`` — Textbausteine, die in die Antwort MÜSSEN."""

    model_config = ConfigDict(extra="forbid")

    trigger: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SignalPraezedenz(BaseModel):
    """Ein Eintrag im optionalen Block ``signale`` — gelintete SICHT auf die
    SSOT-Präzedenz-Tabelle ``lastgang.reconcile.PRAEZEDENZ`` (Fakt vor
    Heuristik). Deklariert, dass ein Lastgang-Signal NUR eine Heuristik für
    ein Profil-Feld ist — ein gespeicherter Fakt schlägt es deterministisch."""

    model_config = ConfigDict(extra="forbid")

    fakt: str = Field(min_length=1)
    rolle: Literal["heuristik_fuer"]


class Prozess(BaseModel):
    """Ein vollständiger Prozess: die sieben D7-Blöcke + der optionale
    ``signale``-Block (Fakt-vor-Heuristik-Deklaration, nach ``fragen``)."""

    model_config = ConfigDict(extra="forbid")

    meta: ProzessMeta
    ziel: str = Field(min_length=1)
    benoetigte_daten: list[BenoetigtesDatum] = Field(default_factory=list)
    fragen: list[Frage] = Field(default_factory=list)
    signale: dict[str, SignalPraezedenz] = Field(default_factory=dict)
    tool_mapping: list[ToolMappingSchritt] = Field(min_length=1)
    datenqualitaet_abbruch: list[str] = Field(default_factory=list)
    caveats: list[Caveat] = Field(min_length=1)

    @property
    def gedeckte_felder(self) -> set[str]:
        """Felder, die per ``benoetigte_daten`` ODER einer ``frage`` gedeckt sind."""
        aus_daten = {d.feld for d in self.benoetigte_daten}
        aus_fragen = {f.feld for f in self.fragen if f.feld}
        return aus_daten | aus_fragen
