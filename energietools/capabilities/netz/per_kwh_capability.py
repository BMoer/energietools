# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""GridFees-Capability — Netzentgelt je Betreiber/Land, per-kWh und pro Jahr.

Auditierbar: jede Zahl trägt ihren Rechenweg und die Quelle des zugrunde
liegenden Preisblatts. Fail-open: unbekannter Operator / nicht befülltes Land →
``operator: null``, Kosten 0, leerer Rechenweg (keine erfundenen Werte).

Seit S0 unter dem ``netz``-Paket beheimatet (per-kWh-Sicht auf die netz-Engine);
der öffentliche Capability-Name ``"grid_fees"`` bleibt unverändert.
"""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.netz.per_kwh import (
    _ap_netto_ct_kwh,
    resolve_operator,
    total_fee_breakdown,
)

_UST = 1.20


def _require_positive(kwargs: dict[str, Any], feld: str) -> float:
    wert = kwargs.get(feld)
    if wert is None or float(wert) <= 0:
        raise CapabilityError(f"{feld} muss > 0 sein")
    return float(wert)


class GridFeesCapability(Capability):
    """Netzentgelt eines Betreibers: per-kWh-Aufschlüsselung + Brutto-Jahresbetrag."""

    name = "grid_fees"
    summary = (
        "Netzentgelt je Netzbetreiber/Land (Default Österreich), per kWh und pro Jahr, "
        "mit lückenlosem Rechenweg und Speicher-Befreiung (§16b/§17 ElWOG). Quelle aus dem "
        "auditierten data/netz-Snapshot. Fail-open: unbekannter Betreiber → null, Kosten 0."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "verbrauch_kwh": {"type": "number", "description": "Jahresverbrauch/Bezug in kWh"},
            "operator": {
                "type": "string",
                "description": "Betreiber-Key oder -Name; leer = Default-Betreiber des Landes",
            },
            "country": {"type": "string", "description": "Ländercode, Default 'AT'"},
            "storage_exemption": {
                "type": "boolean",
                "description": "True = Netzentgelt-Befreiung der Ladeenergie (§16b/§17 ElWOG)",
            },
        },
        "required": ["verbrauch_kwh"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        verbrauch = _require_positive(kwargs, "verbrauch_kwh")
        operator = kwargs.get("operator") or None
        country = str(kwargs.get("country", "AT")).strip() or "AT"
        storage_exemption = bool(kwargs.get("storage_exemption", False))

        tarif = resolve_operator(operator, country)
        breakdown = total_fee_breakdown(operator, country, storage_exemption)
        if tarif is None or breakdown is None:
            # Fail-open: kein eindeutiger Betreiber → keine Kosten erfunden.
            return {
                "operator": None,
                "country": country.upper(),
                "grid_fee_eur_jahr_brutto": 0.0,
                "rechenweg": {"komponenten": {}},
                "gueltig_ab": "",
                "quelle": "",
            }

        ap_netto_ct = _ap_netto_ct_kwh(tarif)
        netto_eur = ap_netto_ct * verbrauch / 100.0 + tarif.netznutzung_pauschale_eur_jahr
        netto_eur += breakdown["eag_foerderpauschale_eur_jahr"]
        brutto_eur = round(netto_eur * _UST, 2)
        return {
            "operator": tarif.name,
            "country": country.upper(),
            "verbrauch_kwh": verbrauch,
            "grid_fee_ct_kwh_netto": breakdown["komponenten_ct_kwh"]["summe_netto"],
            "grid_fee_ct_kwh_brutto": breakdown["komponenten_ct_kwh"]["summe_brutto"],
            "grid_fee_eur_jahr_brutto": brutto_eur,
            "storage_exemption": storage_exemption,
            "rechenweg": {
                "komponenten": breakdown["komponenten_ct_kwh"],
                "arbeitspreis_netto_ct_kwh": round(ap_netto_ct, 4),
                "netznutzung_pauschale_eur_jahr": tarif.netznutzung_pauschale_eur_jahr,
                "eag_foerderpauschale_eur_jahr": breakdown["eag_foerderpauschale_eur_jahr"],
                "netto_eur_jahr": round(netto_eur, 2),
                "ust_faktor": _UST,
                "brutto_eur_jahr": brutto_eur,
            },
            "gueltig_ab": tarif.gueltig_ab,
            "quelle": tarif.quelle,
        }
