# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Lastgang-Capabilities — Ursachen-Hypothesen aus einem Verbrauchs-Lastgang.

``lastgang_signals`` (L.1, WP2-L Durchstich 2): elektrische Heizung,
PV-Eigenverbrauch, Dauerläufer + die dazu passenden Rückfragen, mit
PV-bedingten Netzbezug-Guards gegen die False-Positives eines Prosumer-
Lastgangs (Ledger F3/F14/F24).
"""

from __future__ import annotations

from energietools.capabilities.lastgang.capability import LastgangSignalsCapability
from energietools.capabilities.lastgang.signals import Signal

__all__ = ["LastgangSignalsCapability", "Signal"]
