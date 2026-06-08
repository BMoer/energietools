# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarif-Capability — der Open-Data-Katalog als auditierbare Fähigkeit.

``tariff_catalog`` — den Open-Data-Tarifkatalog abfragen/filtern. Der eigentliche
Tarif-VERGLEICH (Loop/Differenz/Ranking/Präsentation) lebt seit S4 im Produkt
(gridbert); et ist die reine Kosten-Engine und liefert die Katalog-Daten + den
Kosten-Rechenweg eines Tarifs (``tariffs.compare.kosten_rechenweg``).
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability
from energietools.capabilities.tariffs.catalog import TariffCatalog


class TariffCatalogCapability(Capability):
    """Open-Data-Tarifkatalog abfragen (Netto-Listenpreise, first-party)."""

    name = "tariff_catalog"
    summary = (
        "Liste österreichischer Stromtarife aus dem Open-Data-Katalog "
        "(Netto-Listenpreise). Filterbar nach Typ, Ökostrom, Anbieter, Bindung."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "tariftyp": {"type": "string", "enum": ["Fixpreis", "Monatsfloater", "Stundenfloater"]},
            "oekostrom": {"type": "boolean"},
            "lieferant": {"type": "string", "description": "Teilstring des Lieferantennamens"},
            "ohne_bindung": {"type": "boolean", "description": "Nur jederzeit kündbare Tarife"},
            "nur_fixpreis": {"type": "boolean", "description": "Spot/Floater ausschließen"},
        },
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        catalog = TariffCatalog.load().filter(
            tariftyp=kwargs.get("tariftyp"),
            oekostrom=kwargs.get("oekostrom"),
            lieferant=kwargs.get("lieferant"),
            ohne_bindung=kwargs.get("ohne_bindung"),
            nur_fixpreis=bool(kwargs.get("nur_fixpreis", False)),
        )
        manifest = catalog.manifest
        return {
            "manifest": manifest.model_dump() if manifest else None,
            "count": len(catalog),
            "tariffs": [t.model_dump() for t in catalog.all()],
        }
