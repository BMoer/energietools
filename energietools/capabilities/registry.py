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
from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    TarifvergleichInklNetzCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.tariffs.advice import TariffAdviceCapability
from energietools.capabilities.tariffs.capability import (
    TariffCatalogCapability,
    TariffCompareCapability,
)
from energietools.capabilities.tools_bridge import register_tool_capabilities


@lru_cache(maxsize=1)
def default_registry() -> CapabilityRegistry:
    """Zentrale Registry aller ausgelieferten Capabilities (gecacht)."""
    registry = CapabilityRegistry()
    # Auditierbarer Kern: Open-Data-Tarife + Rechnungs-Zusammenführung.
    registry.register(TariffCatalogCapability())
    registry.register(TariffCompareCapability())
    registry.register(TariffAdviceCapability())
    # Energiegemeinschafts-Kennzahlen (EEG/BEG).
    registry.register(CommunityMetricsCapability())
    # Netz: regulierte Netzkosten, Gesamtkosten, Verfügbarkeit, Tarifvergleich inkl. Netz.
    registry.register(NetzkostenCapability())
    registry.register(GesamtkostenCapability())
    registry.register(VerfuegbarkeitCapability())
    registry.register(TarifvergleichInklNetzCapability())
    # Bestehende deterministische Analyse-Tools ans Rückgrat hängen.
    register_tool_capabilities(registry)
    return registry
