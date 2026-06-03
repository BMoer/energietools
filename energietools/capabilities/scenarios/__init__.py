# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Scenarios-Capability — Batterie-Dispatch-Szenarien (ersetzt das alte battery_sim).

Größen-Sweep mit Eigenverbrauchs-Dispatch (portiert, über die Battery-Komponente)
und ROI-Bewertung (finance). Die Abbildung der Szenarien auf den allgemeinen
Optimierer (als Strategien) ist als TODO erfasst.
"""

from __future__ import annotations

from energietools.capabilities.scenarios.capability import ScenariosCapability
from energietools.capabilities.scenarios.dispatch import DispatchResult, run_self_consumption

__all__ = ["DispatchResult", "ScenariosCapability", "run_self_consumption"]
