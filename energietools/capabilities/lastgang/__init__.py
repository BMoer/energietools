# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Lastgang-Capabilities — Ursachen-Hypothesen + Mehrjahres-Trend aus einem
Verbrauchs-Lastgang.

``lastgang_signals`` (L.1, WP2-L Durchstich 2): elektrische Heizung,
PV-Eigenverbrauch, Dauerläufer + die dazu passenden Rückfragen, mit
PV-bedingten Netzbezug-Guards gegen die False-Positives eines Prosumer-
Lastgangs (Ledger F3/F14/F24).

``load_trend`` (L.2, WP2-L Durchstich 2): Mehrjahres-Trend (YoY) mit
Coverage-Guard — Kalender-YoY nur bei >=2 vollen Kalenderjahren, sonst
Fenster-YoY über deckungsgleiche (Monat,Tag,Std,Min)-Slots (Ledger F4/F11/F12).
"""

from __future__ import annotations

from energietools.capabilities.lastgang.capability import (
    LastgangSignalsCapability,
    LoadTrendCapability,
)
from energietools.capabilities.lastgang.signals import Signal

__all__ = ["LastgangSignalsCapability", "LoadTrendCapability", "Signal"]
