# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Ergebnismodell der Finance-Capability (immutable, auditierbar)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ROIResult(BaseModel):
    """Investitionskennzahlen einer Energieinvestition mit lückenlosem Rechenweg.

    ``simple_payback_years``/``lcoe_eur_kwh`` können ``inf`` sein (amortisiert nie /
    keine Energieabgabe). ``annahmen`` hält alle Eingaben fest, damit jede Zahl
    nachgerechnet werden kann.
    """

    model_config = ConfigDict(frozen=True)

    total_investment_eur: float = Field(description="Investitionssumme (CAPEX) in EUR")
    annual_net_benefit_eur: float = Field(
        description="Jährlicher Netto-Nutzen Jahr 1 (Ertrag - Betriebskosten)"
    )
    simple_payback_years: float = Field(
        description="Einfache Amortisationsdauer (Jahre; inf = nie)"
    )
    npv_eur: float = Field(description="Kapitalwert über die Nutzungsdauer in EUR")
    lcoe_eur_kwh: float | None = Field(
        default=None, description="Stromgestehungskosten EUR/kWh (None, wenn keine Energie-Eingabe)"
    )
    lifetime_years: int = Field(description="Betrachtete Nutzungsdauer in Jahren")
    discount_rate: float = Field(description="Diskontrate (Dezimalbruch)")
    degradation_rate: float = Field(description="Jährliche Degradation des Ertrags (Dezimalbruch)")
    annahmen: dict[str, float] = Field(
        default_factory=dict, description="Alle Eingabe-Annahmen (Audit-Trail)"
    )
