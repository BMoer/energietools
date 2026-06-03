# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""GridFees-Capability — Netzentgelte je Betreiber/Land, per-kWh (offline, auditierbar).

Operator- und länderparametrisiert (Default Österreich). Anders als die
``netz``-Capability (regulierte **Jahres**-Haushaltskosten je PLZ) liefert
``grid_fees`` das **marginale Netzentgelt pro kWh** — die Größe, die der
Dispatch/Optimierer und die Spot-Analyse als Kostenanteil brauchen — plus die
Speicher-Befreiung (kein Netzentgelt auf Ladeenergie, §16b/§17 ElWOG).

**Single Source of Truth:** die österreichischen Zahlen kommen aus demselben
auditierten Snapshot ``data/netz/`` wie die ``netz``-Capability (keine
Wert-Duplikate, kein Drift). Eine spätere DE/CH-Erweiterung füllt die
``country``-Dimension; bis dahin liefert ``country != "AT"`` fail-open ``None``.
"""

from __future__ import annotations

from energietools.capabilities.grid_fees.capability import GridFeesCapability
from energietools.capabilities.grid_fees.resolve import (
    DEFAULT_OPERATOR_AT,
    charging_fee_ct_kwh,
    consumption_fee_ct_kwh,
    default_network_fee_ct_kwh,
    network_fee_ct_kwh,
    resolve_operator,
    total_fee_breakdown,
)

__all__ = [
    "DEFAULT_OPERATOR_AT",
    "GridFeesCapability",
    "charging_fee_ct_kwh",
    "consumption_fee_ct_kwh",
    "default_network_fee_ct_kwh",
    "network_fee_ct_kwh",
    "resolve_operator",
    "total_fee_breakdown",
]
