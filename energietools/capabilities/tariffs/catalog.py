# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Open-Data-Tarifkatalog — Laden und Filtern.

Lädt den versionierten Snapshot ``data/tariffs/catalog.json`` (first-party
gescrapte österreichische Stromtarife) und bietet deterministische Filter.
Kein Netzwerk, keine externe Tarif-API — der Katalog ist offline auditierbar.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import date
from functools import lru_cache
from importlib import resources

from energietools.capabilities.base import CapabilityError
from energietools.capabilities.tariffs.models import CatalogManifest, CatalogTariff

log = logging.getLogger(__name__)

_DATA_PACKAGE = "energietools.data.tariffs"

# Tariftyp-Erkennung aus dem Produktnamen (Fallback, falls der Katalog-Eintrag
# keinen strukturierten Typ trägt).
_FLOATER_KEYWORDS = ("floater", "flex", "float", "monatsfloater", "variable")
_SPOT_KEYWORDS = ("spot", "stundenfloater", "hourly", "dynamic", "dynamisch")

# --- Gas-Schutz: der Open-Data-Katalog ist Strom-only (MANIFEST.energy_type=POWER).
# Der Scraper-Stack mischt vereinzelt Gas-Produkte ein (z.B. "go green gas",
# "E1 Gas Fix", Gas-Spot mit EEX-THE-Index). Die werden beim Laden gefiltert, damit
# ein 5-ct-Gas-Arbeitspreis nie als "günstigster Stromtarif" rankt.
_GAS_SPOT_INDEX = {"eex the"}  # Trading Hub Europe = Gas-Großhandelsindex
# Fixer Strom-Arbeitspreis unter dieser Schwelle ist in AT nicht plausibel
# (Großhandel ~9 ct + Netz/Abgaben/Marge) → solche Fixpreise sind faktisch Gas.
_STROM_FIXPREIS_UNTERGRENZE_CT = 8.5
_GAS_NAME = re.compile(r"\bgas\b")  # "gas" als WORT (matcht NICHT Marken wie "goldgas"/"redgas")


def _ist_gas_eintrag(entry: dict) -> bool:
    """True, wenn ein Roh-Katalogeintrag ein Gas-Produkt ist (≠ Strom).

    Signale in Reihenfolge (robust gegen Firmennamen mit "gas"):
    1. explizites ``energy_type`` ≠ POWER → vertrauen (zukunftssicher).
    2. Gas-Börsenindex (EEX THE).
    3. "gas" als eigenes Wort im **Tarifnamen** (nicht Lieferant — "goldgas"/"redgas"
       verkaufen auch Strom: "goldgas strom: derFixe" bleibt Strom).
    4. fixer Arbeitspreis unter der Strom-Plausibilitätsgrenze (Gas ist deutlich billiger).
    """
    et = str(entry.get("energy_type", "")).strip().upper()
    if et:
        return et != "POWER"
    if str(entry.get("spot_index", "")).strip().lower() in _GAS_SPOT_INDEX:
        return True
    if _GAS_NAME.search(str(entry.get("tarif_name", "")).lower()):
        return True
    ep = entry.get("energiepreis_ct_kwh", 0.0) or 0.0
    return 0.0 < ep < _STROM_FIXPREIS_UNTERGRENZE_CT


def _ist_gueltig_am(tariff: CatalogTariff, stand: str) -> bool:
    """True, wenn die Tarif-Version am Stichtag ``stand`` (ISO-Datum) gültig ist.

    ISO-Datums-Strings vergleichen lexikografisch = chronologisch. Leeres
    ``gueltig_ab`` = seit Beginn gültig; leeres ``gueltig_bis`` = aktuell offen.
    """
    ab_ok = not tariff.gueltig_ab or tariff.gueltig_ab <= stand
    bis_ok = not tariff.gueltig_bis or stand <= tariff.gueltig_bis
    return ab_ok and bis_ok


def detect_tariftyp(tarif_name: str) -> str:
    """Tariftyp aus dem Produktnamen ableiten (Stundenfloater/Monatsfloater/Fixpreis)."""
    name_lower = tarif_name.lower()
    if any(kw in name_lower for kw in _SPOT_KEYWORDS):
        return "Stundenfloater"
    if any(kw in name_lower for kw in _FLOATER_KEYWORDS):
        return "Monatsfloater"
    return "Fixpreis"


def _read_data(filename: str) -> str:
    """Liest eine Datei aus dem ``energietools.data.tariffs``-Package."""
    try:
        return resources.files(_DATA_PACKAGE).joinpath(filename).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise CapabilityError(
            f"Tarifkatalog-Datei '{filename}' nicht gefunden — "
            "ist data/tariffs/ im Package?",
        ) from exc


@lru_cache(maxsize=1)
def _load_raw() -> tuple[CatalogTariff, ...]:
    """Lädt + parst catalog.json (gecacht; Tupel = immutable).

    Gas-Einträge werden hier gefiltert (Strom-only-Katalog). Kein stilles
    Verwerfen: die übersprungenen Produkte werden geloggt.
    """
    raw = json.loads(_read_data("catalog.json"))
    if not isinstance(raw, list):
        raise CapabilityError("catalog.json: erwartet eine Liste von Tarifen")
    strom = [e for e in raw if not _ist_gas_eintrag(e)]
    if len(strom) != len(raw):
        gas = [f"{e.get('lieferant', '?')} — {e.get('tarif_name', '?')}" for e in raw if _ist_gas_eintrag(e)]
        log.warning(
            "catalog.json: %d Nicht-Strom-Tarife (Gas) übersprungen — Strom-only-Katalog: %s",
            len(gas), ", ".join(gas),
        )
    return tuple(CatalogTariff(**entry) for entry in strom)


@lru_cache(maxsize=1)
def load_manifest() -> CatalogManifest:
    """Lädt das MANIFEST (Version, Provenance, Coverage, Lizenz)."""
    return CatalogManifest(**json.loads(_read_data("MANIFEST.json")))


class TariffCatalog:
    """Geladener Tarifkatalog mit deterministischen Filtern.

    Immutable: jede Filter-Methode gibt eine **neue** ``TariffCatalog``-Instanz
    zurück, mutiert nie die bestehende Tarifliste.
    """

    def __init__(self, tariffs: Iterable[CatalogTariff], manifest: CatalogManifest | None = None):
        self._tariffs: tuple[CatalogTariff, ...] = tuple(tariffs)
        self._manifest = manifest

    @classmethod
    def load(cls, stand: str | None = None) -> TariffCatalog:
        """Lädt den gebündelten Open-Data-Snapshot, gefiltert auf einen Stichtag.

        ``stand=None`` (Default) → die **aktuell gültigen** Versionen (heute). Ein
        ISO-Datum (z.B. ``"2026-04-01"``) → die zu diesem Stichtag gültige Sicht
        (Tarif-Historie). Bestehende Caller ohne Argument bekommen wie bisher den
        aktuellen Stand (alte Snapshots ohne Gültigkeitsfelder = alle aktuell).
        """
        stichtag = stand or date.today().isoformat()
        return cls(_load_raw(), load_manifest()).gueltig_am(stichtag)

    def gueltig_am(self, stand: str) -> TariffCatalog:
        """Nur die am Stichtag ``stand`` (ISO-Datum) gültigen Tarif-Versionen."""
        aktiv = tuple(t for t in self._tariffs if _ist_gueltig_am(t, stand))
        return TariffCatalog(aktiv, self._manifest)

    @property
    def manifest(self) -> CatalogManifest | None:
        return self._manifest

    def all(self) -> list[CatalogTariff]:
        return list(self._tariffs)

    def __len__(self) -> int:
        return len(self._tariffs)

    def filter(
        self,
        *,
        tariftyp: str | None = None,
        oekostrom: bool | None = None,
        lieferant: str | None = None,
        ohne_bindung: bool | None = None,
        nur_fixpreis: bool = False,
    ) -> TariffCatalog:
        """Gefilterte Teilmenge als neuer Katalog.

        - ``tariftyp``: exakter Typ (z.B. "Fixpreis").
        - ``oekostrom``: nur (oder nur nicht) zertifizierter Ökostrom.
        - ``lieferant``: Teilstring-Match auf den Lieferantennamen (case-insensitiv).
        - ``ohne_bindung``: True → nur jederzeit kündbare Tarife. False/None →
          keine Filterung auf dieser Achse (kein invertierter "nur mit Bindung").
        - ``nur_fixpreis``: True → Spot/Floater ausschließen.
        """
        result = self._tariffs
        if tariftyp is not None:
            result = tuple(t for t in result if t.tariftyp == tariftyp)
        if oekostrom is not None:
            result = tuple(t for t in result if t.ist_oekostrom is oekostrom)
        if lieferant is not None:
            needle = lieferant.lower()
            result = tuple(t for t in result if needle in t.lieferant.lower())
        if ohne_bindung:
            result = tuple(t for t in result if not t.hat_bindung)
        if nur_fixpreis:
            result = tuple(t for t in result if not t.ist_spot)
        return TariffCatalog(result, self._manifest)
