# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Brücke: Capabilities → Agent-ToolRegistry.

Registriert alle Capabilities einer ``CapabilityRegistry`` als Agent-Tools.
Damit ist jede neue Capability ohne zusätzlichen Code im Agent verfügbar —
das Rückgrat trägt Agent **und** CLI aus einer Quelle.
"""

from __future__ import annotations

from energietools.agent.registry import ToolRegistry
from energietools.capabilities.base import CapabilityRegistry
from energietools.capabilities.registry import default_registry


def register_capabilities(
    tool_registry: ToolRegistry,
    capabilities: CapabilityRegistry | None = None,
) -> ToolRegistry:
    """Registriert alle Capabilities als Agent-Tools. Gibt die Registry zurück."""
    capabilities = capabilities or default_registry()
    for cap in capabilities.all():
        tool_registry.register(
            name=cap.name,
            description=cap.summary,
            input_schema=cap.input_schema,
            handler=cap.run,  # gibt CapabilityResult zurück → ToolRegistry serialisiert es
        )
    return tool_registry
