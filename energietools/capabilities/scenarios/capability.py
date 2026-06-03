# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Scenarios-Capability — Batterie-Größen-Sweep mit Eigenverbrauchs-Dispatch + ROI.

Ersetzt das frühere monolithische ``tools/battery_sim.py``. Läuft den
Eigenverbrauchs-Dispatch (portiert, über die Battery-Komponente) für mehrere
Speichergrößen über die übergebene Produktions-/Verbrauchs-Zeitreihe, bewertet
jede Größe ökonomisch (Netzbezugskosten - Einspeiseerlös) gegen die Baseline
ohne Speicher und rechnet Amortisation/NPV mit dem ``finance``-Modul.

Keine Magic-Numbers: Energiepreis, Einspeisetarif, Speicherkosten, Nutzungsdauer
und Diskontrate sind Pflichteingaben. Die Erlöse sind eine **Schätzung** über den
Eingabezeitraum (auf ein Jahr hochgerechnet), keine Abrechnung — so gekennzeichnet.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.finance.calculations import npv, simple_payback_years
from energietools.capabilities.scenarios.dispatch import DispatchResult, run_self_consumption
from energietools.components.battery import Battery

_HOURS_PER_YEAR = 8760.0
_DEFAULT_SIZES_KWH = (0.0, 5.0, 10.0, 15.0)


def _series_kwh(kwargs: dict[str, Any], feld: str) -> list[float]:
    data = kwargs.get(feld)
    if not isinstance(data, list) or not data:
        raise CapabilityError(f"{feld} muss eine nicht-leere Liste von {{kwh: ...}} sein")
    try:
        return [float(p["kwh"]) for p in data]
    except (KeyError, TypeError, ValueError) as exc:
        raise CapabilityError(f"{feld}: jeder Punkt braucht ein numerisches Feld 'kwh'") from exc


def _require_number(kwargs: dict[str, Any], feld: str, *, positiv: bool = True) -> float:
    wert = kwargs.get(feld)
    if wert is None:
        raise CapabilityError(f"{feld} ist erforderlich (keine erfundenen Annahmen)")
    wert = float(wert)
    if positiv and wert <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return wert


class ScenariosCapability(Capability):
    """Batterie-Größen-Sweep: Eigenverbrauch + Autarkie + Amortisation/NPV je Größe."""

    name = "scenarios"
    summary = (
        "Batterie-Größen-Sweep: Eigenverbrauchs-Dispatch über eine PV-/Verbrauchs-Zeitreihe, "
        "je Größe Eigenverbrauchsquote, Autarkiegrad, Netzbezug/Einspeisung und Amortisation/NPV "
        "(finance). Ersetzt das alte battery_sim; Erlöse sind eine Jahres-Schätzung."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "production_data": {
                "type": "array",
                "description": "PV-Erzeugung je Intervall: [{kwh: float}, ...]",
            },
            "consumption_data": {
                "type": "array",
                "description": "Verbrauch je Intervall: [{kwh: float}, ...] (gleiche Länge)",
            },
            "sizes_kwh": {
                "type": "array",
                "description": "Speichergrößen in kWh (inkl. 0 = Baseline)",
            },
            "energiepreis_ct_kwh": {"type": "number", "description": "Bezugspreis brutto ct/kWh"},
            "einspeisung_ct_kwh": {"type": "number", "description": "Einspeisetarif ct/kWh"},
            "speicher_kosten_eur_pro_kwh": {
                "type": "number",
                "description": "Speicherkosten EUR/kWh",
            },
            "nutzungsdauer_jahre": {"type": "integer", "description": "Nutzungsdauer für NPV"},
            "diskontrate": {
                "type": "number",
                "description": "Diskontrate (Dezimalbruch, z.B. 0.04)",
            },
            "dt_hours": {"type": "number", "description": "Intervalllänge in h (Default 0.25)"},
        },
        "required": [
            "production_data",
            "consumption_data",
            "energiepreis_ct_kwh",
            "einspeisung_ct_kwh",
            "speicher_kosten_eur_pro_kwh",
            "nutzungsdauer_jahre",
            "diskontrate",
        ],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        production = _series_kwh(kwargs, "production_data")
        consumption = _series_kwh(kwargs, "consumption_data")
        if len(production) != len(consumption):
            raise CapabilityError("production_data und consumption_data müssen gleich lang sein")

        energiepreis = _require_number(kwargs, "energiepreis_ct_kwh") / 100.0
        einspeisung = _require_number(kwargs, "einspeisung_ct_kwh", positiv=False) / 100.0
        kosten_pro_kwh = _require_number(kwargs, "speicher_kosten_eur_pro_kwh")
        nutzungsdauer = int(_require_number(kwargs, "nutzungsdauer_jahre"))
        diskontrate = _require_number(kwargs, "diskontrate", positiv=False)
        dt_hours = float(kwargs.get("dt_hours", 0.25) or 0.25)
        sizes = kwargs.get("sizes_kwh") or list(_DEFAULT_SIZES_KWH)

        n = len(production)
        period_hours = n * dt_hours
        annual_factor = _HOURS_PER_YEAR / period_hours if period_hours > 0 else 1.0

        def period_cost_eur(res: DispatchResult) -> float:
            return res.grid_import_kwh * energiepreis - res.grid_feed_in_kwh * einspeisung

        runs = {
            size: run_self_consumption(
                production, consumption, Battery.new(float(size)), dt_hours=dt_hours
            )
            for size in sizes
        }
        baseline = runs.get(0.0) or run_self_consumption(
            production, consumption, Battery.new(0.0), dt_hours=dt_hours
        )
        baseline_cost = period_cost_eur(baseline)

        rows: list[dict[str, Any]] = []
        for size in sizes:
            res = runs[size]
            jahres_ersparnis = (baseline_cost - period_cost_eur(res)) * annual_factor
            invest = float(size) * kosten_pro_kwh
            payback = simple_payback_years(invest, jahres_ersparnis) if size > 0 else float("inf")
            kapitalwert = (
                npv(
                    total_investment_eur=invest,
                    annual_benefit_year1_eur=jahres_ersparnis,
                    lifetime_years=nutzungsdauer,
                    discount_rate=diskontrate,
                )
                if size > 0
                else 0.0
            )
            rows.append(
                {
                    "kapazitaet_kwh": float(size),
                    "eigenverbrauchsquote": res.self_consumption_rate,
                    "autarkiegrad": res.self_sufficiency_rate,
                    "netzbezug_kwh": res.grid_import_kwh,
                    "einspeisung_kwh": res.grid_feed_in_kwh,
                    "vollzyklen": res.cycles,
                    "investition_eur": round(invest, 2),
                    "ersparnis_jahr_eur_schaetzung": round(jahres_ersparnis, 2),
                    "amortisation_jahre": round(payback, 2) if payback != float("inf") else None,
                    "npv_eur": round(kapitalwert, 2),
                }
            )

        bewertbar = [r for r in rows if r["kapazitaet_kwh"] > 0]
        bestes = max(bewertbar, key=lambda r: r["npv_eur"]) if bewertbar else None

        return {
            "szenarien": rows,
            "bestes_szenario": bestes,
            "baseline_kwh": 0.0,
            "annahmen": {
                "energiepreis_ct_kwh": round(energiepreis * 100, 4),
                "einspeisung_ct_kwh": round(einspeisung * 100, 4),
                "speicher_kosten_eur_pro_kwh": kosten_pro_kwh,
                "nutzungsdauer_jahre": nutzungsdauer,
                "diskontrate": diskontrate,
                "dt_hours": dt_hours,
                "intervalle": n,
                "jahres_hochrechnung_faktor": round(annual_factor, 4),
            },
            "hinweis": (
                "Erlöse sind eine Schätzung über den Eingabezeitraum, auf ein Jahr "
                "hochgerechnet (Faktor 8760h / Periodenstunden) — keine Abrechnung."
            ),
        }
