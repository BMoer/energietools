# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Das Carnot-Fraktion-COP-Modell ist nachgebaut nach dem Ansatz in
# `pvtool` (batterystorage-sim, Jakob/holzjfk-a11y), MIT-Zusage liegt vor — siehe
# CREDITS.md. Es ist Standard-Physik (Carnot-Wirkungsgrad × Gütegrad).

"""Wärmepumpe — Wärmeerzeuger/Last. COP real, Dispatch PLATZHALTER.

Echtes Verhalten dort, wo wir es haben: :meth:`cop` rechnet den
Leistungs-Koeffizienten über die Carnot-Fraktion (Vorlauf-/Außentemperatur,
Annäherungstemperaturen, Gütegrad), inkl. Unter-/Obergrenze. Der vollständige
2-Pass-Dispatch (Wärmebedarf → Strombedarf → thermischer Speicher → Batterie,
Bivalenzpunkt, Gas-Baseline) braucht ein Zeitprofil und ist Platzhalter.
"""

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
class HeatPump(Component):
    """Wärmepumpe (Carnot-COP real; Lastgang-Dispatch Platzhalter)."""

    kind: ClassVar[str] = KIND_LOAD

    inlet_temp_c: float = 55.0  # Heizungs-Vorlauftemperatur
    cop_carnot_efficiency: float = 0.45  # Gütegrad (Anteil des idealen Carnot-COP)
    cop_min: float = 1.5
    cop_max: float = 5.5
    name: str = "heatpump"

    #: Annäherungstemperaturen der Wärmeübertrager (K) — Klassenkonstanten.
    CONDENSER_APPROACH_K: ClassVar[float] = 5.0
    EVAPORATOR_APPROACH_K: ClassVar[float] = 5.0

    def cop(self, outdoor_temp_c: float, inlet_temp_c: float | None = None) -> float:
        """Leistungszahl (COP) über die Carnot-Fraktion — echtes, testbares Verhalten.

        ``COP = η_carnot · T_hot / (T_hot − T_cold)`` mit
        ``T_hot = Vorlauf + 273,15 + Kondensator-Approach`` und
        ``T_cold = Außentemp + 273,15 − Verdampfer-Approach``; ΔT auf ≥ 1 K
        begrenzt, Ergebnis auf ``[cop_min, cop_max]`` geklemmt. Höhere Außentemp →
        höherer COP; höhere Vorlauftemp → niedrigerer COP.
        """
        inlet = self.inlet_temp_c if inlet_temp_c is None else inlet_temp_c
        t_hot = inlet + 273.15 + self.CONDENSER_APPROACH_K
        t_cold = outdoor_temp_c + 273.15 - self.EVAPORATOR_APPROACH_K
        delta_t = max(t_hot - t_cold, 1.0)
        cop = self.cop_carnot_efficiency * t_hot / delta_t
        return min(max(cop, self.cop_min), self.cop_max)

    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, HeatPump]:
        raise NotImplementedError(
            "PLATZHALTER: Die Wärmepumpe berechnet je Intervall ihren Strombedarf aus "
            "Wärmebedarf und COP (COP ist bereits implementiert: siehe cop()) und meldet ihn "
            "als Last. Die 2-Pass-Logik (Wärmebedarf → COP → Last, thermischer Speicher, "
            "Bivalenzpunkt, Gas-Baseline) braucht ein Zeitprofil. Siehe TODO.md."
        )
