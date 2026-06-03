# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""E-Auto — Lade-Komponente (Last). PLATZHALTER (Struktur vorhanden, Verhalten offen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from energietools.components.base import (
    KIND_LOAD,
    Component,
    ComponentStep,
    StepContext,
)


@dataclass(frozen=True)
class ElectricVehicle(Component):
    """E-Auto als steuerbare Last (Platzhalter).

    Parameter sind angelegt; das Lade-Verhalten ist noch nicht implementiert.
    """

    kind: ClassVar[str] = KIND_LOAD

    battery_kwh: float = 0.0
    max_charge_kw: float = 11.0
    target_soc_pct: float = 80.0
    name: str = "ev"

    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, ElectricVehicle]:
        raise NotImplementedError(
            "PLATZHALTER: Das E-Auto meldet je Intervall seinen Ladebedarf als Last — "
            "ungesteuert vs. PV-/preisgesteuertes Laden, mit Anwesenheits-/Fahrprofil und "
            "Ziel-SOC. Siehe TODO.md."
        )
