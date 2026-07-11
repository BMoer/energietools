# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Rechnungs-Fakten: validierendes Schema (D2.2) + deterministische Aufbereitung.

``validate_invoice_facts`` prüft von einem (User-)LLM transkribierte
Rechnungs-Fakten strikt (Rejection-Semantik: Garbage wird abgelehnt, nie zu
0.0 koerziert); ``finalize_invoice`` rechnet auf validierten Fakten
deterministisch weiter (Arbeitspreis-Pläne, Hochrechnung, Hauptmetrik) — mit
lückenlosem Rechenweg. Strom, Gas und Kombi (§6 F6).
"""

from energietools.capabilities.invoice.capability import (
    FinalizeInvoiceCapability,
    ValidateInvoiceFactsCapability,
)
from energietools.capabilities.invoice.facts import (
    Betrag,
    Grundgebuehr,
    InvoiceFacts,
    PreisCtKwh,
    QuellenAnker,
    pruefe_invoice_facts,
)

__all__ = [
    "Betrag",
    "FinalizeInvoiceCapability",
    "Grundgebuehr",
    "InvoiceFacts",
    "PreisCtKwh",
    "QuellenAnker",
    "ValidateInvoiceFactsCapability",
    "pruefe_invoice_facts",
]
