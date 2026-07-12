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
from energietools.capabilities.invoice.capability import (
    FinalizeInvoiceCapability,
    ValidateInvoiceFactsCapability,
)
from energietools.capabilities.knowledge.capability import GetKnowledgeCapability
from energietools.capabilities.lastgang.capability import LastgangSignalsCapability
from energietools.capabilities.load_profile.capability import LoadProfileCapability
from energietools.capabilities.netz.capability import (
    GesamtkostenCapability,
    NetzkostenCapability,
    VerfuegbarkeitCapability,
)
from energietools.capabilities.netz.per_kwh_capability import GridFeesCapability
from energietools.capabilities.providers.capability import VersorgerAbdeckungCapability
from energietools.capabilities.scenarios.capability import ScenariosCapability
from energietools.capabilities.tariff_compare.capability import TariffCompareCapability
from energietools.capabilities.tariffs.capability import TariffCatalogCapability
from energietools.capabilities.tools_bridge import register_tool_capabilities


@lru_cache(maxsize=1)
def default_registry() -> CapabilityRegistry:
    """Zentrale Registry aller ausgelieferten Capabilities (gecacht)."""
    registry = CapabilityRegistry()
    # Auditierbarer Kern: Open-Data-Tarifkatalog + Tarifvergleich (B.1-Move:
    # der Vergleichs-Kern lebt seit WP-T hier; Datenquellen via Protocols).
    registry.register(TariffCatalogCapability())
    registry.register(TariffCompareCapability())
    # Rechnungs-Fakten: Validierung (D2.2, Rejection-Semantik) + deterministische
    # Aufbereitung mit Rechenweg (B.4/B.5).
    registry.register(ValidateInvoiceFactsCapability())
    registry.register(FinalizeInvoiceCapability())
    # Wissens-Auslieferung (D7 „Wissens-Auslieferung", Amendment 9): eine kuratierte
    # Wiki-Seite als reinen Text — kein Rechen-Result.
    registry.register(GetKnowledgeCapability())
    # Energiegemeinschafts-Kennzahlen (EEG/BEG).
    registry.register(CommunityMetricsCapability())
    # Netz: regulierte Netzkosten, Gesamtkosten, Verfügbarkeit.
    registry.register(NetzkostenCapability())
    registry.register(GesamtkostenCapability())
    registry.register(VerfuegbarkeitCapability())
    # Versorger-Abdeckung je Netzgebiet (welche Lieferanten sind an der PLZ verfügbar).
    registry.register(VersorgerAbdeckungCapability())
    # Rechenmodule: Netzentgelt je Betreiber/Land (per kWh) + Investitionskennzahlen.
    registry.register(GridFeesCapability())
    registry.register(FinanceCapability())
    # Simulationsbaukasten: Batterie-Größen-Sweep (ersetzt das alte battery_sim).
    registry.register(ScenariosCapability())
    # Wärmepumpe: diskreter Heizkostenvergleich (COP real, Lastgang-Dispatch Platzhalter).
    registry.register(HeatPumpCapability())
    # Lastprofil-Analyse: dedizierte Capability (WP2-S) statt generischer
    # FunctionCapability-Brücke — mappt die in-band-Fehlersemantik auf ok/error.
    registry.register(LoadProfileCapability())
    # Lastgang-Signale: Ursachen-Hypothesen (Heizung/PV/Dauerläufer) + Rückfragen,
    # mit PV-bedingten Netzbezug-Guards gegen Prosumer-False-Positives (L.1).
    registry.register(LastgangSignalsCapability())
    # Bestehende deterministische Analyse-Tools ans Rückgrat hängen.
    register_tool_capabilities(registry)
    return registry
