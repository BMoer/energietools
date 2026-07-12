# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Lastgang-Capabilities — Analyse von 15-min-Verbrauchsserien (offline).

Auditierbare Fähigkeiten über einen Verbrauchs-Lastgang (Q15). Jede liefert
Rechenweg + Caveats IM Result (Zielbild-Prinzip 3) und ist ohne DB/Netz testbar.

Aktuell in diesem Package (weitere folgen aus der WP2-L-Zusammenführung):
- ``trend_attribution`` — Zerlegung des YoY-Deltas nach Leistungsband × Tageszeit
  → Geräte-KLASSE als Hypothese (nie Gerätename). L.3, HARTES DoD-Gate 15.

Die Analyse-Methoden sind MIT-Neuimplementierungen nach dokumentierter Methode
(CASE_09), nicht 1:1-Ports proprietären gridbert-Codes.
"""

from __future__ import annotations

from energietools.capabilities.lastgang.attribution import compute_trend_attribution
from energietools.capabilities.lastgang.attribution_capability import (
    TrendAttributionCapability,
)

__all__ = [
    "TrendAttributionCapability",
    "compute_trend_attribution",
]
