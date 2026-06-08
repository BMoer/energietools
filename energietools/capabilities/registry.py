# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Default-Capability-Registry — die Tarif-Fähigkeiten des Toolkits.

``default_registry()`` liefert die zentrale ``CapabilityRegistry`` mit allen
ausgelieferten Capabilities. Neue Fähigkeiten (Rechnungs-Scan, Lastprofil …)
werden hier registriert — danach sind sie automatisch in CLI und Agent
verfügbar.
"""

from __future__ import annotations

from functools import lru_cache

from energietools.capabilities.base import CapabilityRegistry
from energietools.capabilities.community.capability import CommunityMetricsCapability
from energietools.capabilities.finance.capability import FinanceCapability
from energietools.capabilities.heatpump.capability import HeatPumpCapability
from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.netz.per_kwh_capability import GridFeesCapability
from energietools.capabilities.scenarios.capability import ScenariosCapability
from energietools.capabilities.tariffs.capability import TariffCatalogCapability
from energietools.capabilities.tools_bridge import register_tool_capabilities


@lru_cache(maxsize=1)
def default_registry() -> CapabilityRegistry:
    """Zentrale Registry aller ausgelieferten Capabilities (gecacht)."""
    registry = CapabilityRegistry()
    # Auditierbarer Kern: Open-Data-Tarifkatalog (Vergleich lebt im Produkt, S4).
    registry.register(TariffCatalogCapability())
    # Energiegemeinschafts-Kennzahlen (EEG/BEG).
    registry.register(CommunityMetricsCapability())
    # Netz: regulierte Netzkosten, Gesamtkosten, Verfügbarkeit.
    registry.register(NetzkostenCapability())
    registry.register(GesamtkostenCapability())
    registry.register(VerfuegbarkeitCapability())
    # Rechenmodule: Netzentgelt je Betreiber/Land (per kWh) + Investitionskennzahlen.
    registry.register(GridFeesCapability())
    registry.register(FinanceCapability())
    # Simulationsbaukasten: Batterie-Größen-Sweep (ersetzt das alte battery_sim).
    registry.register(ScenariosCapability())
    # Wärmepumpe: diskreter Heizkostenvergleich (COP real, Lastgang-Dispatch Platzhalter).
    registry.register(HeatPumpCapability())
    # Bestehende deterministische Analyse-Tools ans Rückgrat hängen.
    register_tool_capabilities(registry)
    return registry
