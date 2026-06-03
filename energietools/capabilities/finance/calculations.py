# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Reine Finanzformeln (Standard-Lehrbuch, clean-room) — ohne Daten, ohne Netzwerk.

Diese Funktionen sind deterministisch und nebenwirkungsfrei; sie werden sowohl von
der ``finance``-Capability als auch von der Kostenzielfunktion des Optimierers
genutzt. Konventionen:

- Beträge in EUR, Raten als Dezimalbruch (``0.04`` = 4 %), Energie in kWh.
- ``simple_payback_years``/``lcoe`` geben ``inf`` zurück, wenn keine sinnvolle
  Kennzahl existiert (statt 0 oder Crash) — der Aufrufer sieht „amortisiert nie“.
- NPV: Investition fällt in Jahr 0 an (nicht abgezinst); Erträge/Kosten ab Jahr 1.
  Degradation mindert den Ertrag linear-geometrisch ``(1 - d)^(y-1)`` (Jahr 1 voll).
- LCOE diskontiert **Kosten und Energie** (korrekte Lehrbuch-Definition), nicht nur
  die Kosten — bewusste Abweichung von Implementierungen, die die Energie nominal
  lassen.
"""

from __future__ import annotations

from math import inf


def capex(
    *,
    capacity_kwh: float,
    cost_eur_per_kwh: float,
    power_kw: float = 0.0,
    cost_eur_per_kw: float = 0.0,
    fixed_eur: float = 0.0,
) -> float:
    """Investitionssumme = Kapazitätskosten + Leistungskosten + Fixkosten."""
    return capacity_kwh * cost_eur_per_kwh + power_kw * cost_eur_per_kw + fixed_eur


def simple_payback_years(total_investment_eur: float, annual_net_benefit_eur: float) -> float:
    """Einfache (statische) Amortisationsdauer in Jahren.

    ``inf``, wenn der jährliche Netto-Nutzen ≤ 0 ist (keine Amortisation).
    """
    if annual_net_benefit_eur <= 0:
        return inf
    return total_investment_eur / annual_net_benefit_eur


def npv(
    *,
    total_investment_eur: float,
    annual_benefit_year1_eur: float,
    lifetime_years: int,
    discount_rate: float,
    annual_cost_eur: float = 0.0,
    degradation_rate: float = 0.0,
) -> float:
    """Kapitalwert über die Nutzungsdauer.

    ``NPV = -I + Σ_{y=1..L} [ benefit·(1-d)^(y-1) - cost ] / (1+r)^y``
    """
    if lifetime_years <= 0:
        return -total_investment_eur
    total = -total_investment_eur
    for year in range(1, int(lifetime_years) + 1):
        benefit_y = annual_benefit_year1_eur * (1.0 - degradation_rate) ** (year - 1)
        total += (benefit_y - annual_cost_eur) / (1.0 + discount_rate) ** year
    return total


def lcoe(
    *,
    total_investment_eur: float,
    annual_cost_eur: float,
    lifetime_years: int,
    annual_energy_kwh_year1: float,
    discount_rate: float = 0.0,
    degradation_rate: float = 0.0,
) -> float:
    """Stromgestehungskosten (EUR/kWh) — diskontierte Lebenszykluskosten je diskontierter kWh.

    ``LCOE = ( I + Σ cost/(1+r)^y ) / Σ ( energy·(1-d)^(y-1) / (1+r)^y )``

    ``inf``, wenn keine Energie über die Lebensdauer abgegeben wird.
    """
    if lifetime_years <= 0 or annual_energy_kwh_year1 <= 0:
        return inf
    cost_pv = total_investment_eur
    energy_pv = 0.0
    for year in range(1, int(lifetime_years) + 1):
        discount = (1.0 + discount_rate) ** year
        cost_pv += annual_cost_eur / discount
        energy_pv += annual_energy_kwh_year1 * (1.0 - degradation_rate) ** (year - 1) / discount
    if energy_pv <= 0:
        return inf
    return cost_pv / energy_pv
