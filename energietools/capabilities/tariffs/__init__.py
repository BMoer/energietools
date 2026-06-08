# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarif-Capability — Open-Data-Katalog + Kosten-Rechenweg eines Tarifs.

et ist die reine Kosten-Engine: Katalog-Daten (``tariff_catalog``) +
``kosten_rechenweg`` (Energie-Rechenweg eines Tarifs). Der Tarif-VERGLEICH
(Loop/Differenz/Ranking) lebt seit S4 im Produkt (gridbert).
"""

from __future__ import annotations

from energietools.capabilities.tariffs.capability import TariffCatalogCapability
from energietools.capabilities.tariffs.catalog import TariffCatalog, detect_tariftyp
from energietools.capabilities.tariffs.compare import kosten_rechenweg
from energietools.capabilities.tariffs.models import CatalogManifest, CatalogTariff

__all__ = [
    "CatalogManifest",
    "CatalogTariff",
    "TariffCatalog",
    "TariffCatalogCapability",
    "detect_tariftyp",
    "kosten_rechenweg",
]
