# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT
#
# Herkunft: Die Lade-/Entlade-Dispatch-Logik (Eigenverbrauch) ist portiert aus
# `pvtool` (batterystorage-sim, Jakob/holzjfk-a11y), MIT-Zusage liegt vor — siehe
# CREDITS.md. Hier auf die diskrete Component-Schnittstelle und immutable State
# umgesetzt (SOC in kWh, ein Schritt = ein Intervall).

"""Batterie-Speicher — Eigenverbrauchs-Dispatch als verschaltbare Komponente.

Echtes Verhalten (kein Platzhalter): lädt aus Bus-Überschuss, entlädt in
Bus-Defizit, hält SOC zwischen ``min_soc`` und ``max_soc``, berücksichtigt
Lade-/Entlade-Wirkungsgrad und die C-Rate als Leistungsgrenze. Die Bilanz-
Konvention folgt :mod:`energietools.components.base`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

from energietools.components.base import (
    KIND_STORAGE,
    Component,
    ComponentStep,
    StepContext,
)


@dataclass(frozen=True)
class Battery(Component):
    """Heimspeicher mit Eigenverbrauchs-Dispatch (immutable; SOC in kWh).

    Konstruktion über :meth:`new` (setzt den Anfangs-SOC auf ``min_soc``). Die
    Standard-Engineering-Parameter (C-Rate, Wirkungsgrade, SOC-Fenster) stammen
    aus der pvtool-Config; sie sind explizite Bausteinparameter, keine versteckten
    Ergebnis-Defaults.
    """

    kind: ClassVar[str] = KIND_STORAGE

    capacity_kwh: float
    soc_kwh: float
    name: str = "battery"
    c_rate: float = 0.5
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    min_soc_pct: float = 5.0
    max_soc_pct: float = 95.0

    @classmethod
    def new(
        cls,
        capacity_kwh: float,
        *,
        name: str = "battery",
        c_rate: float = 0.5,
        charge_efficiency: float = 0.95,
        discharge_efficiency: float = 0.95,
        min_soc_pct: float = 5.0,
        max_soc_pct: float = 95.0,
        initial_soc_kwh: float | None = None,
    ) -> Battery:
        """Erzeugt eine Batterie; Anfangs-SOC = ``min_soc`` (leer am unteren Anschlag)."""
        if capacity_kwh < 0:
            raise ValueError("capacity_kwh darf nicht negativ sein")
        min_soc = capacity_kwh * min_soc_pct / 100.0
        soc = min_soc if initial_soc_kwh is None else float(initial_soc_kwh)
        return cls(
            capacity_kwh=capacity_kwh,
            soc_kwh=soc,
            name=name,
            c_rate=c_rate,
            charge_efficiency=charge_efficiency,
            discharge_efficiency=discharge_efficiency,
            min_soc_pct=min_soc_pct,
            max_soc_pct=max_soc_pct,
        )

    @property
    def min_soc_kwh(self) -> float:
        return self.capacity_kwh * self.min_soc_pct / 100.0

    @property
    def max_soc_kwh(self) -> float:
        return self.capacity_kwh * self.max_soc_pct / 100.0

    def step(self, surplus_kwh: float, ctx: StepContext) -> tuple[ComponentStep, Battery]:
        """Ein Intervall Eigenverbrauchs-Dispatch.

        - ``surplus_kwh >= 0``: lade aus dem Überschuss (Ladeverlust auf dem Weg
          hinein); die Komponente *bezieht* die Roh-kWh vom Bus.
        - ``surplus_kwh < 0``: entlade zur Deckung des Defizits (Entladeverlust auf
          dem Weg hinaus); die Komponente *speist* die gelieferten kWh in den Bus.
        """
        if self.capacity_kwh <= 0:
            return ComponentStep(detail={"soc_kwh": 0.0}), self

        max_charge_interval = self.capacity_kwh * self.c_rate * ctx.dt_hours
        max_discharge_interval = self.capacity_kwh * self.c_rate * ctx.dt_hours

        if surplus_kwh >= 0:
            # In den SOC eingelagerte Energie (bereits wirkungsgrad-bereinigt).
            can_store = min(
                surplus_kwh * self.charge_efficiency,
                self.max_soc_kwh - self.soc_kwh,
                max_charge_interval * self.charge_efficiency,
            )
            can_store = max(can_store, 0.0)
            eff = self.charge_efficiency
            drawn_from_bus = can_store / eff if eff > 0 else 0.0
            new_soc = self.soc_kwh + can_store
            stepres = ComponentStep(consumed_kwh=drawn_from_bus, detail={"soc_kwh": new_soc})
            return stepres, replace(self, soc_kwh=new_soc)

        deficit = -surplus_kwh
        can_discharge = min(
            self.soc_kwh - self.min_soc_kwh,
            deficit / self.discharge_efficiency if self.discharge_efficiency > 0 else 0.0,
            max_discharge_interval,
        )
        can_discharge = max(can_discharge, 0.0)
        delivered = can_discharge * self.discharge_efficiency
        new_soc = self.soc_kwh - can_discharge
        stepres = ComponentStep(produced_kwh=delivered, detail={"soc_kwh": new_soc})
        return stepres, replace(self, soc_kwh=new_soc)
