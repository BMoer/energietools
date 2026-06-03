# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Heatpump-Capability — Heizkostenvergleich Wärmepumpe vs. Gas (diskret).

Nutzt das reale Carnot-COP-Modell der :class:`HeatPump`-Komponente für einen
diskreten Jahres-Kostenvergleich. Der volle 2-Pass-Dispatch (Lastgang, thermischer
Speicher, Bivalenzpunkt, PV-Deckung) ist Platzhalter (siehe TODO.md).
"""

from __future__ import annotations

from energietools.capabilities.heatpump.capability import HeatPumpCapability

__all__ = ["HeatPumpCapability"]
