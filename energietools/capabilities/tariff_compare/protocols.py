# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Daten-Protocols des Tarifvergleichs — der Vertrag zur (proprietären) Quelle.

Der Vergleichs-Kern (:func:`~energietools.capabilities.tariff_compare.compare.
vergleiche_tarife`) ist storage-agnostisch: er spricht ausschließlich diese
beiden schmalen Protocols an. Konsumenten bringen ihre eigenen Adapter mit
(z.B. eine Postgres-Tariftabelle + EPEX-Repo); für den Standalone-Betrieb
liefert ``sources.py`` Adapter auf die gebündelten Open-Data-Snapshots.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class TariffSource(Protocol):
    """Quelle der Tarif-Zeilen (netto Listenpreise) für den Vergleich."""

    def get_latest(self, *, status: str, energy_type: str) -> list[dict]: ...


class SpotPriceSource(Protocol):
    """Quelle der EPEX-Stundenpreise (Spot/Floater-Effektivpreis).

    ``get_prices`` liefert ``[{"timestamp": ISO-String, "price_ct": float}, …]``
    (netto ct/kWh), aufsteigend sortiert.
    """

    def available_years(self) -> list[int]: ...

    def get_prices(self, start: datetime, end: datetime) -> list[dict]: ...
