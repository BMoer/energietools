# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Simulationsbausteine (Schicht „Rechnen“) — verschaltbare Energiekomponenten.

Jede Komponente teilt die Schnittstelle aus :mod:`energietools.components.base`
(Energie rein/raus + Zustand, ein diskreter ``step`` = ein Intervall). Echtes
Verhalten: :class:`PVSystem` (Quelle) und :class:`Battery` (Eigenverbrauchs-
Speicher). Platzhalter mit erkennbarer Struktur: :class:`ElectricVehicle`,
:class:`GasBoiler` und der Dispatch der :class:`HeatPump` (deren COP-Modell ist
real). Verschaltet werden die Komponenten in :mod:`energietools.system`.
"""

from __future__ import annotations

from energietools.components.base import (
    KIND_CONVERTER,
    KIND_LOAD,
    KIND_SOURCE,
    KIND_STORAGE,
    Component,
    ComponentStep,
    StepContext,
)
from energietools.components.battery import Battery
from energietools.components.ev import ElectricVehicle
from energietools.components.gas_boiler import GasBoiler
from energietools.components.heatpump import HeatPump
from energietools.components.pv import PVSystem

__all__ = [
    "KIND_CONVERTER",
    "KIND_LOAD",
    "KIND_SOURCE",
    "KIND_STORAGE",
    "Battery",
    "Component",
    "ComponentStep",
    "ElectricVehicle",
    "GasBoiler",
    "HeatPump",
    "PVSystem",
    "StepContext",
]
