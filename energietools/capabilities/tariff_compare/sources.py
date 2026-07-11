# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Snapshot-Adapter für die Tarifvergleichs-Protocols (Standalone-Betrieb).

``CatalogTariffSource`` bedient :class:`TariffSource` aus dem gebündelten
Open-Data-Tarifkatalog; ``SnapshotSpotPriceSource`` bedient
:class:`SpotPriceSource` aus dem gebündelten EPEX-Snapshot. Beide sind offline
und deterministisch. Produkt-Konsumenten (z.B. ein MCP-Gateway mit eigener
Tarif-DB) ersetzen sie durch eigene Adapter — das ist der ganze Zweck der
Protocols.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from energietools.capabilities.spot.data import load_epex_prices, load_spot_manifest
from energietools.capabilities.tariffs.catalog import TariffCatalog


class CatalogTariffSource:
    """``TariffSource`` über den gebündelten Open-Data-Tarifkatalog.

    Der Katalog ist Strom-only (``energy_type="POWER"``); GAS liefert eine
    leere Liste. ``status`` ist im Katalog bereits vor-gefiltert (nur aktive
    Einträge werden publiziert) und wird deshalb nicht weiter ausgewertet.
    """

    def __init__(self, catalog: TariffCatalog | None = None) -> None:
        self._catalog = catalog if catalog is not None else TariffCatalog.load()

    def get_latest(self, *, status: str, energy_type: str) -> list[dict]:
        if energy_type != "POWER":
            return []
        return [t.model_dump() for t in self._catalog.all()]

    @property
    def meta(self) -> dict[str, Any]:
        """Provenance des Snapshots (stand/quelle/snapshot_version) fürs Result-meta."""
        manifest = self._catalog.manifest
        if manifest is None:
            return {"quelle": "open-data-katalog"}
        return {
            "stand": manifest.stand or manifest.generated_at,
            "quelle": "open-data-katalog (energietools.data.tariffs)",
            "snapshot_version": manifest.catalog_version,
        }


class SnapshotSpotPriceSource:
    """``SpotPriceSource`` über den gebündelten EPEX-Snapshot (offline)."""

    def __init__(self) -> None:
        self._prices = load_epex_prices()

    def available_years(self) -> list[int]:
        years = {
            datetime.fromisoformat(str(p["timestamp"])).year
            for p in self._prices
            if p.get("timestamp")
        }
        return sorted(years)

    def get_prices(self, start: datetime, end: datetime) -> list[dict]:
        return [
            dict(p)
            for p in self._prices
            if p.get("timestamp")
            and start <= datetime.fromisoformat(str(p["timestamp"])) < end
        ]

    @property
    def meta(self) -> dict[str, Any]:
        manifest = load_spot_manifest()
        return {
            "stand": manifest.get("generated_at", ""),
            "quelle": "epex-snapshot (energietools.data.spot)",
            "snapshot_version": manifest.get("spot_version", ""),
        }
