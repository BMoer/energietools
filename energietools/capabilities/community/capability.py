# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Community-Capability — EEG/BEG-Kennzahlen als auditierbare Fähigkeit."""

from __future__ import annotations

from typing import Any

from energietools.capabilities.base import Capability, CapabilityError
from energietools.capabilities.community.metrics import community_metrics


class CommunityMetricsCapability(Capability):
    """SSR/SCR/Reststrom/Überschuss einer Energiegemeinschaft berechnen."""

    name = "community_metrics"
    summary = (
        "Berechne Energiegemeinschafts-Kennzahlen (Autarkiegrad/SSR, "
        "Eigenverbrauchsquote/SCR, intern gedeckt, Reststrom, Überschuss) aus "
        "gleich langen Erzeugungs- und Verbrauchsreihen (kWh pro Zeitschlitz)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "erzeugung_kwh": {"type": "array", "items": {"type": "number"}},
            "verbrauch_kwh": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["erzeugung_kwh", "verbrauch_kwh"],
    }

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        gen = kwargs.get("erzeugung_kwh")
        cons = kwargs.get("verbrauch_kwh")
        if not isinstance(gen, list) or not isinstance(cons, list):
            raise CapabilityError("erzeugung_kwh und verbrauch_kwh müssen Listen sein")
        return community_metrics([float(g) for g in gen], [float(c) for c in cons]).model_dump()
