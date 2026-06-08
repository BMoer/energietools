# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""PV-Anlage — Erzeugungs-Komponente (Quelle).

Echtes Verhalten (kein Platzhalter), bewusst schlank: die Anlage ist über
installierte Leistung (kWp) und spezifischen Jahresertrag (kWh/kWp) parametrisiert
und speist pro Intervall den anteiligen Ertrag ein. „Ein Skalar ist ein
Ein-Punkt-Profil“: bei ``dt_hours = 8760`` (ein Jahres-Punkt) liefert ein Schritt
den vollen Jahresertrag; feinere Intervalle skalieren linear über die Zeit.

Das tatsächliche Ertragsprofil (Tag/Nacht, Saison, Wetter) ist hier *nicht*
abgebildet — dafür liefert eine spätere Zeitreihen-Variante ein echtes Profil
(z.B. aus PVGIS, siehe ``tools/pv_sim``). Für die diskrete Erstrechnung genügt der
zeitanteilige Mittelwert; die Aufschlüsselung steht als Profil-TODO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from energietools.components.base import (
    KIND_SOURCE,
    Component,
    ComponentStep,
    StepContext,
)

_HOURS_PER_YEAR = 8760.0


@dataclass(frozen=True)
class PVSystem(Component):
    """PV-Anlage als Quelle (zustandslos; Ertrag skaliert mit der Intervalllänge)."""

    kind: ClassVar[str] = KIND_SOURCE

    kwp: float
    specific_yield_kwh_per_kwp: float = 1000.0  # AT-Mittel ~950-1100 kWh/kWp/Jahr
    name: str = "pv"

    @property
    def annual_production_kwh(self) -> float:
        return self.kwp * self.specific_yield_kwh_per_kwp

    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, PVSystem]:
        """Speist den zeitanteiligen Ertrag ein (Quelle ignoriert den Bus-Überschuss)."""
        produced = self.annual_production_kwh * (ctx.dt_hours / _HOURS_PER_YEAR)
        produced = max(produced, 0.0)
        return ComponentStep(produced_kwh=produced), self
