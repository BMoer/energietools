# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Der dritte Auditability-Pfeiler: Rechnung → Tarifvergleich, in einem Fluss.

``invoice_parser`` scannt eine österreichische Energierechnung zu strukturierten
Feldern; dieser Modul führt diese Felder mit dem Open-Data-Katalog zusammen und
liefert einen vollständig nachvollziehbaren Vergleich. Der Scan (OCR) ist
LLM-gestützt; die **Zusammenführung und Rechnung** sind deterministisch und von
außen reproduzierbar — genau die Grenze, die open source sein soll.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.tariffs.catalog import TariffCatalog
from energietools.capabilities.tariffs.compare import compare_against_catalog
from energietools.models import TariffComparison
from energietools.models.invoice import Invoice


def advise_from_invoice(
    invoice: Invoice,
    *,
    gebrauchsabgabe_rate: float = 0.0,
    spot_baseline_ct: float | None = None,
    catalog: TariffCatalog | None = None,
) -> TariffComparison:
    """Vergleicht den Tarif einer gescannten Rechnung gegen den Katalog.

    Die Rechnungspreise sind brutto (so extrahiert); sie werden im Vergleich
    identisch zum Katalog behandelt. Netzkosten von der Rechnung (falls vorhanden)
    fließen in die Gesamtkosten ein.
    """
    if invoice.jahresverbrauch_kwh <= 0:
        raise CapabilityError("Jahresverbrauch muss > 0 kWh sein — Vergleich nicht möglich")
    if invoice.energiepreis_ct_kwh <= 0:
        raise CapabilityError("Energiepreis muss > 0 ct/kWh sein — Vergleich nicht möglich")

    return compare_against_catalog(
        verbrauch_kwh=invoice.jahresverbrauch_kwh,
        aktueller_lieferant=invoice.lieferant or "Aktueller Anbieter",
        aktueller_energiepreis_ct_kwh=invoice.energiepreis_ct_kwh,
        aktuelle_grundgebuehr_eur_monat=invoice.grundgebuehr_eur_monat,
        gebrauchsabgabe_rate=gebrauchsabgabe_rate,
        netzkosten_eur_jahr=invoice.netzkosten_eur_jahr or 0.0,
        spot_baseline_ct=spot_baseline_ct,
        catalog=catalog,
        plz=invoice.plz,
    )


class TariffAdviceCapability(Capability):
    """Rechnungsdaten gegen den Open-Data-Katalog vergleichen (auditierbarer Fluss)."""

    name = "tariff_advice"
    summary = (
        "Führe gescannte Rechnungsdaten (Verbrauch, Energiepreis, Grundgebühr, PLZ) "
        "mit dem Open-Data-Tarifkatalog zusammen und liefere einen auditierbaren "
        "Vergleich inkl. Ersparnis und Rechenweg pro Tarif."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "jahresverbrauch_kwh": {"type": "number"},
            "lieferant": {"type": "string"},
            "energiepreis_ct_kwh": {"type": "number", "description": "Brutto ct/kWh"},
            "grundgebuehr_eur_monat": {"type": "number", "description": "Brutto EUR/Monat"},
            "plz": {"type": "string"},
            "netzkosten_eur_jahr": {"type": "number", "description": "Optional, von der Rechnung"},
            "gebrauchsabgabe_rate": {"type": "number", "description": "z.B. 0.07 für Wien"},
            "spot_baseline_ct": {"type": "number", "description": "Optional: Spot-Baseline ct/kWh"},
        },
        "required": ["jahresverbrauch_kwh", "energiepreis_ct_kwh", "grundgebuehr_eur_monat"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        invoice = Invoice(
            lieferant=kwargs.get("lieferant", ""),
            energiepreis_ct_kwh=float(kwargs["energiepreis_ct_kwh"]),
            grundgebuehr_eur_monat=float(kwargs.get("grundgebuehr_eur_monat", 0.0)),
            jahresverbrauch_kwh=float(kwargs["jahresverbrauch_kwh"]),
            plz=kwargs.get("plz", ""),
            netzkosten_eur_jahr=kwargs.get("netzkosten_eur_jahr"),
        )
        comparison = advise_from_invoice(
            invoice,
            gebrauchsabgabe_rate=float(kwargs.get("gebrauchsabgabe_rate", 0.0)),
            spot_baseline_ct=kwargs.get("spot_baseline_ct"),
        )
        return comparison.model_dump()
