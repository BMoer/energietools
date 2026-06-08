# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Der Eigenverbrauchs-Dispatch stammt aus `pvtool` (batterystorage-sim,
# Jakob/holzjfk-a11y), MIT-Zusage liegt vor — siehe CREDITS.md. Er läuft hier über
# die portierte Battery-Komponente (energietools.components.battery), die den
# SOC/Wirkungsgrad-Kern trägt.

"""Dispatch-Runner: Eigenverbrauchs-Lade-/Entlade-Logik über eine Zeitreihe.

Reicht die (immutable) :class:`Battery`-Komponente über eine Folge von
Überschuss-Punkten (Produktion - Verbrauch) und bilanziert Netzbezug,
Einspeisung, Lade-/Entlademenge und die Kennzahlen Eigenverbrauchsquote +
Autarkiegrad. Das ist die erste funktionierende Referenz unter der neuen Struktur;
die Abbildung auf den allgemeinen Optimierer (scenarios als Strategie) ist als
TODO erfasst.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from energietools.components.base import StepContext
from energietools.components.battery import Battery


@dataclass(frozen=True)
class DispatchResult:
    """Bilanz eines Eigenverbrauchs-Durchlaufs (kWh + Kennzahlen)."""

    capacity_kwh: float
    production_kwh: float
    consumption_kwh: float
    grid_import_kwh: float
    grid_feed_in_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    self_consumption_rate: float
    self_sufficiency_rate: float
    cycles: float


def run_self_consumption(
    production_kwh: Sequence[float],
    consumption_kwh: Sequence[float],
    battery: Battery,
    dt_hours: float = 0.25,
) -> DispatchResult:
    """Eigenverbrauchs-Dispatch über die Zeitreihe (Produktion/Verbrauch je Intervall).

    Args:
        production_kwh: PV-Erzeugung je Intervall.
        consumption_kwh: Verbrauch je Intervall (gleiche Länge wie ``production_kwh``).
        battery: Start-Batterie (wird nicht mutiert; der Zustand wird intern fortgeführt).
        dt_hours: Intervalllänge (Default 0,25 h = 15-min-Raster).
    """
    if len(production_kwh) != len(consumption_kwh):
        raise ValueError("production_kwh und consumption_kwh müssen gleich lang sein")

    ctx = StepContext(dt_hours=dt_hours)
    bat = battery
    tot_prod = tot_cons = charge = discharge = grid_import = grid_feed = 0.0

    for prod, cons in zip(production_kwh, consumption_kwh, strict=True):
        surplus = prod - cons
        step, bat = bat.step(surplus, ctx)
        if surplus >= 0:
            charge += step.consumed_kwh
            grid_feed += max(surplus - step.consumed_kwh, 0.0)
        else:
            discharge += step.produced_kwh
            grid_import += max(-surplus - step.produced_kwh, 0.0)
        tot_prod += prod
        tot_cons += cons

    self_consumption_rate = (tot_prod - grid_feed) / tot_prod if tot_prod > 0 else 0.0
    self_sufficiency_rate = (tot_cons - grid_import) / tot_cons if tot_cons > 0 else 0.0
    cycles = charge / battery.capacity_kwh if battery.capacity_kwh > 0 else 0.0

    return DispatchResult(
        capacity_kwh=battery.capacity_kwh,
        production_kwh=round(tot_prod, 4),
        consumption_kwh=round(tot_cons, 4),
        grid_import_kwh=round(grid_import, 4),
        grid_feed_in_kwh=round(grid_feed, 4),
        battery_charge_kwh=round(charge, 4),
        battery_discharge_kwh=round(discharge, 4),
        self_consumption_rate=round(self_consumption_rate, 4),
        self_sufficiency_rate=round(self_sufficiency_rate, 4),
        cycles=round(cycles, 2),
    )
