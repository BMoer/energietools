# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Finance-Capability — Investitionskennzahlen (ROI/NPV/LCOE), offline & auditierbar.

Clean-Room-Reimplementierung der Standard-Finanzformeln (kein regulatorischer
Inhalt): Investitionssumme, einfache Amortisation, Kapitalwert (NPV) mit linearer
Degradation und Stromgestehungskosten (LCOE). Alle Annahmen (Diskontrate,
Degradation, Nutzungsdauer, Zyklen) sind **explizite Eingaben** — keine versteckten
Magic-Numbers. Steht als eigene Capability und speist die Kostenzielfunktion des
Optimierers.
"""

from __future__ import annotations

from energietools.capabilities.finance.calculations import (
    capex,
    lcoe,
    npv,
    simple_payback_years,
)
from energietools.capabilities.finance.capability import FinanceCapability
from energietools.capabilities.finance.models import ROIResult

__all__ = [
    "FinanceCapability",
    "ROIResult",
    "capex",
    "lcoe",
    "npv",
    "simple_payback_years",
]
