# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Optimierer über ein verschaltetes System — konfigurierbare Zielfunktion.

Drei Zielfunktionen sind **lauffähig** (sie bewerten ein gegebenes System):

- ``economic`` — jährliche Stromkosten (Netzbezug × (Energiepreis + Netzentgelt)
  − Einspeisung × Einspeisetarif). Das Netzentgelt kommt aus der auditierten
  per-kWh-Schicht des ``netz``-Pakets (Capability ``grid_fees``; kein Magic-Default).
- ``self_consumption`` — Eigenverbrauchsquote (maximieren).
- ``autarky`` — Autarkiegrad/Selbstversorgung (maximieren).

Der **Löser** (Suche über Komponenten-Größen nach dem Optimum einer Zielfunktion)
ist bewusst ein **PLATZHALTER**: nicht-triviale Zielfunktionen brauchen einen
echten Solver (CVXPY/Pyomo), dessen Wahl in TODO.md offen ist. Bewerten kann man
schon jetzt; suchen noch nicht.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from energietools.components.base import StepContext
from energietools.system.system import EnergySystem, SystemResult

OBJECTIVE_ECONOMIC = "economic"
OBJECTIVE_SELF_CONSUMPTION = "self_consumption"
OBJECTIVE_AUTARKY = "autarky"

_OBJECTIVES = frozenset({OBJECTIVE_ECONOMIC, OBJECTIVE_SELF_CONSUMPTION, OBJECTIVE_AUTARKY})


@dataclass(frozen=True)
class EconomicPrices:
    """Preise für die ökonomische Zielfunktion (explizit, keine Magic-Defaults).

    Alle in EUR/kWh. Das Netzentgelt wird NICHT hier gesetzt, sondern aus dem
    ``netz``-Paket (Capability ``grid_fees``) für ``operator``/``country`` bezogen
    (auditierbar, gequellt).
    """

    energy_price_eur_kwh: float
    feed_in_tariff_eur_kwh: float
    operator: str | None = None
    country: str = "AT"
    storage_exemption: bool = False


@dataclass(frozen=True)
class ObjectiveValue:
    """Ergebnis einer Zielfunktions-Bewertung."""

    objective: str
    value: float
    maximize: bool
    detail: dict[str, float]


def _grid_fee_eur_kwh(prices: EconomicPrices) -> float:
    """Brutto-Netzentgelt EUR/kWh aus dem auditierten netz-Snapshot (per-kWh)."""
    from energietools.capabilities.base import CapabilityError
    from energietools.capabilities.netz import consumption_fee_ct_kwh

    fee_ct = consumption_fee_ct_kwh(prices.operator, prices.country, brutto=True)
    if fee_ct is None:
        raise CapabilityError(
            f"Netzentgelt für Operator '{prices.operator}'/Land '{prices.country}' "
            "nicht auflösbar — kein stiller Default."
        )
    return fee_ct / 100.0


def evaluate(
    system: EnergySystem,
    objective: str,
    consumption_kwh: Sequence[float],
    contexts: Sequence[StepContext] | None = None,
    prices: EconomicPrices | None = None,
) -> ObjectiveValue:
    """Bewertet ein gegebenes System gegen eine Zielfunktion (lauffähig).

    Für ``economic`` müssen ``prices`` gesetzt sein. Höhere Werte sind besser bei
    ``self_consumption``/``autarky`` (maximieren), niedrigere bei ``economic``
    (Kosten minimieren).
    """
    if objective not in _OBJECTIVES:
        raise ValueError(f"Unbekannte Zielfunktion '{objective}' (erlaubt: {sorted(_OBJECTIVES)})")

    result: SystemResult = system.run(consumption_kwh, contexts)

    if objective == OBJECTIVE_SELF_CONSUMPTION:
        return ObjectiveValue(
            objective=objective,
            value=result.self_consumption_rate,
            maximize=True,
            detail={"self_consumption_rate": result.self_consumption_rate},
        )

    if objective == OBJECTIVE_AUTARKY:
        return ObjectiveValue(
            objective=objective,
            value=result.self_sufficiency_rate,
            maximize=True,
            detail={"self_sufficiency_rate": result.self_sufficiency_rate},
        )

    # economic
    if prices is None:
        raise ValueError("Die ökonomische Zielfunktion braucht 'prices' (EconomicPrices)")
    grid_fee = _grid_fee_eur_kwh(prices)
    import_cost = result.total_grid_import_kwh * (prices.energy_price_eur_kwh + grid_fee)
    feed_in_revenue = result.total_grid_feed_in_kwh * prices.feed_in_tariff_eur_kwh
    annual_cost = import_cost - feed_in_revenue
    return ObjectiveValue(
        objective=objective,
        value=round(annual_cost, 2),
        maximize=False,
        detail={
            "grid_import_kwh": result.total_grid_import_kwh,
            "grid_feed_in_kwh": result.total_grid_feed_in_kwh,
            "grid_fee_eur_kwh": round(grid_fee, 4),
            "import_cost_eur": round(import_cost, 2),
            "feed_in_revenue_eur": round(feed_in_revenue, 2),
            "annual_cost_eur": round(annual_cost, 2),
        },
    )


def optimize(*args: object, **kwargs: object) -> object:
    """PLATZHALTER: Sucht die System-Konfiguration (z.B. Speichergröße), die eine
    Zielfunktion optimiert. Nicht-triviale Zielfunktionen brauchen einen echten
    Löser (CVXPY/Pyomo); die Wahl ist offen. Bewerten via :func:`evaluate` geht
    schon, suchen noch nicht. Siehe TODO.md.
    """
    raise NotImplementedError(
        "PLATZHALTER: Optimierer-Löser noch nicht implementiert (Solver-Wahl CVXPY/Pyomo "
        "offen, siehe TODO.md). Einzelne Konfigurationen lassen sich mit evaluate() bewerten."
    )
