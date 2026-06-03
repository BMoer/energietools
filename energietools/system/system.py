# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Verschaltung + Energiebilanz — der eigentliche Baukasten.

Ein :class:`EnergySystem` steckt Komponenten zusammen und bilanziert pro Intervall
den elektrischen Energiefluss. Bilanz-Reihenfolge am Bus:

1. **Quellen** (PV) speisen ihren Ertrag ein → Überschuss steigt.
2. **Lasten** (E-Auto, Wärmepumpe) beziehen ihren Bedarf → Überschuss sinkt.
3. **Speicher** (Batterie) laden aus positivem, entladen in negativen Überschuss.
4. Der **Rest** ist Netzbezug (Überschuss < 0) bzw. Netzeinspeisung (> 0).

Die Haushalts-Grundlast wird als Verbrauchs-Profil übergeben (sie kommt aus einem
Lastgang); die fünf benannten Komponenten sind die konfigurierbaren Bausteine.
Konverter (Gaskessel) bilanzieren auf dem Wärme-Bus und werden hier (elektrisch)
übersprungen — der Wärme-Bus ist ein TODO.

**Diskret, Zeitreihe als Superset:** ``run`` läuft über eine Folge von Punkten;
ein Skalar ist die Folge der Länge 1. Der (immutable) Komponenten-Zustand wird
zwischen den Schritten weitergereicht.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from energietools.components.base import (
    KIND_LOAD,
    KIND_SOURCE,
    KIND_STORAGE,
    Component,
    StepContext,
)


@dataclass(frozen=True)
class StepBalance:
    """Energiebilanz eines Intervalls (kWh)."""

    consumption_kwh: float
    production_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    grid_import_kwh: float
    grid_feed_in_kwh: float


@dataclass(frozen=True)
class SystemResult:
    """Aggregiertes Bilanz-Ergebnis eines :meth:`EnergySystem.run` + Kennzahlen."""

    steps: tuple[StepBalance, ...]
    total_consumption_kwh: float
    total_production_kwh: float
    total_battery_charge_kwh: float
    total_battery_discharge_kwh: float
    total_grid_import_kwh: float
    total_grid_feed_in_kwh: float
    self_consumption_rate: float
    self_sufficiency_rate: float


class EnergySystem:
    """Ein verschaltetes Energiesystem aus Komponenten (Eigenverbrauchs-Bilanz)."""

    def __init__(self, components: Sequence[Component]) -> None:
        self.components = tuple(components)

    def run(
        self,
        consumption_kwh: Sequence[float],
        contexts: Sequence[StepContext] | None = None,
    ) -> SystemResult:
        """Bilanziert das System über das Verbrauchs-Profil.

        Args:
            consumption_kwh: Haushalts-Grundlast je Intervall (Skalar = Liste der Länge 1).
            contexts: passende :class:`StepContext` je Intervall (Default: 1 h je Punkt).
        """
        n = len(consumption_kwh)
        if contexts is None:
            contexts = [StepContext(dt_hours=1.0)] * n
        if len(contexts) != n:
            raise ValueError("consumption_kwh und contexts müssen gleich lang sein")

        sources = [c for c in self.components if c.kind == KIND_SOURCE]
        loads = [c for c in self.components if c.kind == KIND_LOAD]
        storages = [c for c in self.components if c.kind == KIND_STORAGE]

        steps: list[StepBalance] = []
        tot_cons = tot_prod = tot_charge = tot_discharge = tot_imp = tot_feed = 0.0

        for i in range(n):
            ctx = contexts[i]
            base_demand = float(consumption_kwh[i])
            step_consumption = base_demand
            production = charge = discharge = 0.0
            surplus = -base_demand

            for idx, comp in enumerate(sources):
                cs, sources[idx] = comp.step(surplus, ctx)
                production += cs.produced_kwh
                surplus += cs.produced_kwh

            for idx, comp in enumerate(loads):
                cs, loads[idx] = comp.step(surplus, ctx)
                step_consumption += cs.consumed_kwh
                surplus -= cs.consumed_kwh

            for idx, comp in enumerate(storages):
                cs, storages[idx] = comp.step(surplus, ctx)
                charge += cs.consumed_kwh
                discharge += cs.produced_kwh
                surplus += cs.produced_kwh - cs.consumed_kwh

            grid_import = max(-surplus, 0.0)
            grid_feed_in = max(surplus, 0.0)

            steps.append(
                StepBalance(
                    consumption_kwh=round(step_consumption, 6),
                    production_kwh=round(production, 6),
                    battery_charge_kwh=round(charge, 6),
                    battery_discharge_kwh=round(discharge, 6),
                    grid_import_kwh=round(grid_import, 6),
                    grid_feed_in_kwh=round(grid_feed_in, 6),
                )
            )
            tot_cons += step_consumption
            tot_prod += production
            tot_charge += charge
            tot_discharge += discharge
            tot_imp += grid_import
            tot_feed += grid_feed_in

        self_consumption_rate = (tot_prod - tot_feed) / tot_prod if tot_prod > 0 else 0.0
        self_sufficiency_rate = (tot_cons - tot_imp) / tot_cons if tot_cons > 0 else 0.0

        return SystemResult(
            steps=tuple(steps),
            total_consumption_kwh=round(tot_cons, 4),
            total_production_kwh=round(tot_prod, 4),
            total_battery_charge_kwh=round(tot_charge, 4),
            total_battery_discharge_kwh=round(tot_discharge, 4),
            total_grid_import_kwh=round(tot_imp, 4),
            total_grid_feed_in_kwh=round(tot_feed, 4),
            self_consumption_rate=round(self_consumption_rate, 4),
            self_sufficiency_rate=round(self_sufficiency_rate, 4),
        )

    def with_component(self, component: Component) -> EnergySystem:
        """Neues System mit einer zusätzlichen Komponente (immutable)."""
        return EnergySystem((*self.components, component))
