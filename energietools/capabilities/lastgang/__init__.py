# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Lastgang-Capabilities — Ursachen-Hypothesen, Mehrjahres-Trend, Attribution
und Kosten-Backtest aus einem Verbrauchs-Lastgang (Q15, offline testbar).

``lastgang_signals`` (L.1, WP2-L Durchstich 2): elektrische Heizung,
PV-Eigenverbrauch, Dauerläufer + die dazu passenden Rückfragen, mit
PV-bedingten Netzbezug-Guards gegen die False-Positives eines Prosumer-
Lastgangs (Ledger F3/F14/F24).

``load_trend`` (L.2, WP2-L Durchstich 2): Mehrjahres-Trend (YoY) mit
Coverage-Guard — Kalender-YoY nur bei >=2 vollen Kalenderjahren, sonst
Fenster-YoY über deckungsgleiche (Monat,Tag,Std,Min)-Slots (Ledger F4/F11/F12).

``trend_attribution`` (L.3, WP2-L Durchstich 2, HARTES DoD-Gate 15): Zerlegung
des YoY-Deltas nach Leistungsband × Tageszeit → Geräte-KLASSE als Hypothese
(nie Gerätename), mit 15-min-Auflösungs-Caveat.

``spot_backtest`` (L.4, WP2-L Durchstich 2): profilgewichteter Spot-Backtest
(echter Verbrauchs-Shape × EPEX-Stundenpreise) vs. aktueller Fixpreis, plus
Tarifwechsel-Ersparnis (dünne Sicht auf ``tariff_compare``) — beide Blöcke
unabhängig optional, NIE eine stille 0 bei fehlender Datenlage.

Jede Capability liefert Rechenweg + Caveats IM Result (Zielbild-Prinzip 3).
Die Analyse-Methoden sind MIT-Neuimplementierungen nach dokumentierter Methode,
nicht 1:1-Ports proprietären gridbert-Codes.
"""

from __future__ import annotations

from energietools.capabilities.lastgang.attribution import compute_trend_attribution
from energietools.capabilities.lastgang.attribution_capability import (
    TrendAttributionCapability,
)
from energietools.capabilities.lastgang.capability import (
    LastgangSignalsCapability,
    LoadTrendCapability,
    SpotBacktestCapability,
)
from energietools.capabilities.lastgang.signals import Signal

__all__ = [
    "LastgangSignalsCapability",
    "LoadTrendCapability",
    "Signal",
    "SpotBacktestCapability",
    "TrendAttributionCapability",
    "compute_trend_attribution",
]
