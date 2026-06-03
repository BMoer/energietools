# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Finance-Capability — ROI/NPV/LCOE einer Energieinvestition (auditierbar).

Keine versteckten Defaults: Investition, Ertrag, Nutzungsdauer und Diskontrate
sind Pflicht. Fehlt eine Eingabe oder ist sie unplausibel, wirft die Capability
einen ``CapabilityError`` — keine erfundenen Annahmen. LCOE wird nur berechnet,
wenn die Jahresenergie angegeben ist (sonst ``null``, nicht geschätzt).
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.finance.calculations import lcoe, npv, simple_payback_years
from energietools.capabilities.finance.models import ROIResult


def _require_number(kwargs: dict[str, Any], feld: str, *, positiv: bool = True) -> float:
    wert = kwargs.get(feld)
    if wert is None:
        raise CapabilityError(f"{feld} ist erforderlich (keine erfundenen Annahmen)")
    wert = float(wert)
    if positiv and wert <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return wert


class FinanceCapability(Capability):
    """Investitionskennzahlen ROI/NPV/LCOE mit lückenlosem Rechenweg."""

    name = "finance"
    summary = (
        "Investitionskennzahlen einer Energieinvestition: Amortisation, Kapitalwert (NPV) "
        "mit Degradation und Stromgestehungskosten (LCOE). Standard-Finanzformeln, alle "
        "Annahmen explizit (keine Magic-Numbers). LCOE nur bei angegebener Jahresenergie."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "investition_eur": {"type": "number", "description": "Investitionssumme/CAPEX in EUR"},
            "jaehrlicher_ertrag_eur": {
                "type": "number",
                "description": "Jährlicher Brutto-Ertrag/Ersparnis (Jahr 1)",
            },
            "nutzungsdauer_jahre": {
                "type": "integer",
                "description": "Betrachtete Nutzungsdauer in Jahren",
            },
            "diskontrate": {
                "type": "number",
                "description": "Diskontrate als Dezimalbruch (z.B. 0.04)",
            },
            "betriebskosten_eur_jahr": {
                "type": "number",
                "description": "Jährliche Betriebskosten (optional, Default 0)",
            },
            "degradation_pct_jahr": {
                "type": "number",
                "description": "Jährliche Degradation des Ertrags in % (optional, Default 0)",
            },
            "jahresenergie_kwh": {
                "type": "number",
                "description": "Jahresenergie (Jahr 1) für LCOE (optional)",
            },
        },
        "required": [
            "investition_eur",
            "jaehrlicher_ertrag_eur",
            "nutzungsdauer_jahre",
            "diskontrate",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        investition = _require_number(kwargs, "investition_eur")
        ertrag = _require_number(kwargs, "jaehrlicher_ertrag_eur")
        nutzungsdauer = int(_require_number(kwargs, "nutzungsdauer_jahre"))
        diskontrate = _require_number(kwargs, "diskontrate", positiv=False)

        betriebskosten = float(kwargs.get("betriebskosten_eur_jahr", 0.0) or 0.0)
        degradation = float(kwargs.get("degradation_pct_jahr", 0.0) or 0.0) / 100.0
        jahresenergie = kwargs.get("jahresenergie_kwh")

        netto_nutzen = ertrag - betriebskosten
        payback = simple_payback_years(investition, netto_nutzen)
        kapitalwert = npv(
            total_investment_eur=investition,
            annual_benefit_year1_eur=ertrag,
            lifetime_years=nutzungsdauer,
            discount_rate=diskontrate,
            annual_cost_eur=betriebskosten,
            degradation_rate=degradation,
        )
        lcoe_wert: float | None = None
        if jahresenergie is not None and float(jahresenergie) > 0:
            lcoe_wert = round(
                lcoe(
                    total_investment_eur=investition,
                    annual_cost_eur=betriebskosten,
                    lifetime_years=nutzungsdauer,
                    annual_energy_kwh_year1=float(jahresenergie),
                    discount_rate=diskontrate,
                    degradation_rate=degradation,
                ),
                4,
            )

        result = ROIResult(
            total_investment_eur=round(investition, 2),
            annual_net_benefit_eur=round(netto_nutzen, 2),
            simple_payback_years=round(payback, 2) if payback != float("inf") else payback,
            npv_eur=round(kapitalwert, 2),
            lcoe_eur_kwh=lcoe_wert,
            lifetime_years=nutzungsdauer,
            discount_rate=diskontrate,
            degradation_rate=degradation,
            annahmen={
                "investition_eur": round(investition, 2),
                "jaehrlicher_ertrag_eur": round(ertrag, 2),
                "betriebskosten_eur_jahr": round(betriebskosten, 2),
                "nutzungsdauer_jahre": float(nutzungsdauer),
                "diskontrate": diskontrate,
                "degradation_rate": degradation,
            },
        )
        return result.model_dump()
