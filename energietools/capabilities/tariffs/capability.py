# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Tarif-Capabilities — der Open-Data-Katalog als auditierbare Fähigkeit.

Zwei Capabilities:
- ``tariff_catalog``  — den Open-Data-Tarifkatalog abfragen/filtern.
- ``tariff_compare``  — den aktuellen Tarif gegen den Katalog vergleichen,
                        mit vollständigem Rechenweg pro Tarif.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.tariffs.catalog import TariffCatalog
from energietools.capabilities.tariffs.compare import compare_against_catalog


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


class TariffCompareCapability(Capability):
    """Aktuellen Tarif gegen den Open-Data-Katalog vergleichen (auditierbarer Rechenweg)."""

    name = "tariff_compare"
    summary = (
        "Vergleiche einen aktuellen Stromtarif (Brutto-Preise von der Rechnung) "
        "gegen den Open-Data-Katalog. Liefert sortierte Alternativen mit "
        "lückenlosem Rechenweg (netto → Rabatt → Gebrauchsabgabe → USt → brutto)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "verbrauch_kwh": {"type": "number", "description": "Jahresverbrauch in kWh"},
            "aktueller_lieferant": {"type": "string"},
            "aktueller_energiepreis_ct_kwh": {"type": "number", "description": "Brutto ct/kWh"},
            "aktuelle_grundgebuehr_eur_monat": {
                "type": "number", "description": "Brutto EUR/Monat",
            },
            "gebrauchsabgabe_rate": {"type": "number", "description": "z.B. 0.07 für Wien"},
            "netzkosten_eur_jahr": {"type": "number", "description": "Optional, brutto"},
            "netzbetreiber": {"type": "string"},
            "spot_baseline_ct": {
                "type": "number",
                "description": "Optional: Börsen-Baseline ct/kWh, um Spot-Tarife zu bepreisen",
            },
            "plz": {"type": "string"},
        },
        "required": [
            "verbrauch_kwh",
            "aktueller_energiepreis_ct_kwh",
            "aktuelle_grundgebuehr_eur_monat",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("verbrauch_kwh", 0) <= 0:
            raise CapabilityError("verbrauch_kwh muss > 0 sein")
        comparison = compare_against_catalog(
            verbrauch_kwh=float(kwargs["verbrauch_kwh"]),
            aktueller_lieferant=kwargs.get("aktueller_lieferant", "Aktueller Anbieter"),
            aktueller_energiepreis_ct_kwh=float(kwargs["aktueller_energiepreis_ct_kwh"]),
            aktuelle_grundgebuehr_eur_monat=float(kwargs["aktuelle_grundgebuehr_eur_monat"]),
            gebrauchsabgabe_rate=float(kwargs.get("gebrauchsabgabe_rate", 0.0)),
            netzkosten_eur_jahr=float(kwargs.get("netzkosten_eur_jahr", 0.0)),
            netzbetreiber=kwargs.get("netzbetreiber", ""),
            spot_baseline_ct=kwargs.get("spot_baseline_ct"),
            plz=kwargs.get("plz", ""),
        )
        return comparison.model_dump()
