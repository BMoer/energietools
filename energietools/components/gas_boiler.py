# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Gaskessel — Wärmeerzeuger (Konverter). PLATZHALTER (Struktur vorhanden, Verhalten offen)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from energietools.components.base import (
    KIND_CONVERTER,
    Component,
    ComponentStep,
    StepContext,
)


@dataclass(frozen=True)
class GasBoiler(Component):
    """Gaskessel als Wärmeerzeuger/Backup (Platzhalter).

    Deckt Wärmebedarf aus Gas (Wirkungsgrad, Gaspreis) und dient als Baseline bzw.
    bivalenter Backup zur Wärmepumpe. Kein Beitrag am elektrischen Bus.
    """

    kind: ClassVar[str] = KIND_CONVERTER

    thermal_power_kw: float = 0.0
    efficiency: float = 0.90
    gas_price_eur_per_kwh: float = 0.0
    name: str = "gas_boiler"

    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, GasBoiler]:
        raise NotImplementedError(
            "PLATZHALTER: Der Gaskessel deckt Wärmebedarf aus Gas (Wirkungsgrad, Gaspreis) "
            "und liefert die Gas-Baseline/den bivalenten Backup zur Wärmepumpe — er bilanziert "
            "auf dem Wärme-, nicht dem Strom-Bus. Siehe TODO.md."
        )
