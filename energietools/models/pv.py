# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Pydantic Models für PV / Balkonkraftwerk Simulation."""

from __future__ import annotations

from pydantic import BaseModel


class PVSimulation(BaseModel):
    """Ergebnis einer PV-Simulation.

    Die Amortisation/ROI wird NICHT mehr naiv im Modell gerechnet, sondern vom
    auditierbaren ``finance``-Modul (ROI/NPV/LCOE) — aus ``investition_eur``,
    ``foerderung_eur`` und ``ersparnis_jahr_eur``. Siehe capabilities/finance.
    """

    anlage_kwp: float
    ausrichtung: str  # "Süd", "Ost", "West", etc.
    neigung_grad: int = 35
    jahresertrag_kwh: float = 0.0
    eigenverbrauch_kwh: float = 0.0
    eigenverbrauch_anteil_pct: float = 0.0
    einspeisung_kwh: float = 0.0
    einspeiseverguetung_ct: float = 0.0  # OeMAG
    ersparnis_jahr_eur: float = 0.0
    investition_eur: float = 0.0
    foerderung_eur: float = 0.0
    empfehlung: str = ""
    plz: str = ""
