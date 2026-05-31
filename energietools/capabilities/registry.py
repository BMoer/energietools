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
from energietools.capabilities.tariffs.capability import (
    TariffCatalogCapability,
    TariffCompareCapability,
)


@lru_cache(maxsize=1)
def default_registry() -> CapabilityRegistry:
    """Zentrale Registry aller ausgelieferten Capabilities (gecacht)."""
    registry = CapabilityRegistry()
    registry.register(TariffCatalogCapability())
    registry.register(TariffCompareCapability())
    return registry
