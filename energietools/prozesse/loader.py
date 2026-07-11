# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Laden der Prozess-YAMLs aus ``energietools.prozesse`` (Package-Data).

Spiegelt das Daten-Lade-Muster der netz-/tariffs-/wiki-Schicht:
``importlib.resources`` aus dem gebündelten Package, ``CapabilityError`` bei
fehlenden/kaputten Dateien. YAML statt JSON, weil D7 YAML explizit als Quelle
festlegt (Bens Review/Pflege einfacher als reines JSON, aber lintbar gegen die
Registry — anders als reines Markdown).
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

from energietools.capabilities.base import CapabilityError
from energietools.prozesse.models import Prozess

_PROZESSE_PACKAGE = "energietools.prozesse"
_BEISPIELE_SUBDIR = "beispiele"

# D7-Kanon: die sieben Blöcke in genau dieser Reihenfolge (fehlende optionale
# Blöcke sind erlaubt; die VORHANDENEN müssen relativ zueinander so stehen —
# u.a. damit 'fragen' strukturell vor 'tool_mapping' steht, D7-Checker (b)
# „Pflichtfragen vor Tool-Aufruf").
KANONISCHE_BLOCKREIHENFOLGE = (
    "meta",
    "ziel",
    "benoetigte_daten",
    "fragen",
    "tool_mapping",
    "datenqualitaet_abbruch",
    "caveats",
)


def _read_prozesse_datei(filename: str) -> str:
    try:
        return resources.files(_PROZESSE_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Prozess-Datei '{filename}' nicht gefunden — ist prozesse/ im Package?",
        ) from exc


def load_prozess_raw(filename: str) -> dict[str, Any]:
    """Lädt eine ``prozesse/<id>.yaml`` als rohes Dict (Key-Reihenfolge = Datei-Reihenfolge)."""
    text = _read_prozesse_datei(filename)
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise CapabilityError(f"{filename}: YAML-Wurzel muss ein Mapping sein")
    return raw


def pruefe_blockreihenfolge(raw: dict[str, Any]) -> list[str]:
    """Prüft die D7-kanonische Reihenfolge der vorhandenen Top-Level-Blöcke.

    Gibt eine Liste von Fehlermeldungen zurück (leer = ok). Unbekannte
    Zusatz-Keys werden hier ignoriert (Pydantic schlägt bei ``extra="forbid"``
    ohnehin beim Validieren zu).
    """
    vorhanden = [k for k in raw if k in KANONISCHE_BLOCKREIHENFOLGE]
    erwartet = [k for k in KANONISCHE_BLOCKREIHENFOLGE if k in vorhanden]
    if vorhanden != erwartet:
        return [
            f"Block-Reihenfolge verletzt: gefunden {vorhanden}, erwartet {erwartet} "
            "(D7-Kanon: meta, ziel, benoetigte_daten, fragen, tool_mapping, "
            "datenqualitaet_abbruch, caveats)",
        ]
    return []


def load_prozess(filename: str) -> Prozess:
    """Lädt + validiert eine ``prozesse/<id>.yaml`` als :class:`Prozess`."""
    raw = load_prozess_raw(filename)
    try:
        return Prozess.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError -> einheitliches CapabilityError
        raise CapabilityError(f"{filename}: {exc}") from exc


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    """Lädt ``prozesse/MANIFEST.json`` (analog zum data/-MANIFEST-Muster)."""
    raw = json.loads(_read_prozesse_datei("MANIFEST.json"))
    if not isinstance(raw, dict):
        raise CapabilityError("prozesse/MANIFEST.json: erwartet ein Objekt")
    return raw


def manifest_dateien() -> list[str]:
    """Dateinamen aller im MANIFEST gelisteten Prozesse (Reihenfolge = MANIFEST)."""
    return [eintrag["datei"] for eintrag in load_manifest().get("prozesse", [])]


def load_beispiel(filename: str) -> dict[str, Any]:
    """Lädt einen anonymisierten Beispiel-Dialog aus ``prozesse/beispiele/``."""
    try:
        text = (
            resources.files(_PROZESSE_PACKAGE)
            .joinpath(_BEISPIELE_SUBDIR)
            .joinpath(filename)
            .read_text("utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(f"Beispiel-Dialog '{filename}' nicht gefunden") from exc
    return json.loads(text)


def list_beispiele() -> list[str]:
    """Alle Beispiel-Dialog-Dateinamen (sortiert)."""
    ordner = resources.files(_PROZESSE_PACKAGE).joinpath(_BEISPIELE_SUBDIR)
    return sorted(p.name for p in ordner.iterdir() if p.name.endswith(".json"))
