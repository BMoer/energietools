# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarifvergleich (B.1-Move): Vergleichs-Kern + Daten-Protocols.

Der Vergleichs-Kern (Loop, Differenz, Ranking, best-per-category) lebt hier;
die per-Szenario-Kosten kommen aus ``energietools.cost.gesamtkosten_szenario``.
Die proprietäre Datenbeschaffung bleibt Sache des Konsumenten — der Vertrag
dazu sind die schmalen Protocols ``TariffSource``/``SpotPriceSource``.

Schnitt (Durchstich 1): die VNB-Auflösung (Zählpunkt → VKZ → Netzbetreiber)
und die ``service_area``-Vorfilterung bleiben beim Konsumenten; der Kern nimmt
einen **vorgelösten** ``nb_key`` als Parameter entgegen.
"""

from energietools.capabilities.tariff_compare.capability import TariffCompareCapability
from energietools.capabilities.tariff_compare.compare import vergleiche_tarife
from energietools.capabilities.tariff_compare.protocols import SpotPriceSource, TariffSource
from energietools.capabilities.tariff_compare.sources import (
    CatalogTariffSource,
    SnapshotSpotPriceSource,
)

__all__ = [
    "CatalogTariffSource",
    "SnapshotSpotPriceSource",
    "SpotPriceSource",
    "TariffCompareCapability",
    "TariffSource",
    "vergleiche_tarife",
]
