#!/usr/bin/env python3
"""Example: Standalone energy agent with tariff comparison tool."""
import os
from energietools.agent.registry import ToolRegistry
from energietools.agent.loop import GridbertAgent
from energietools.llm import create_provider
from energietools.tools.tariff_compare import compare_tariffs

# Build a minimal tool registry
registry = ToolRegistry()
registry.register(
    name="compare_tariffs",
    description="Vergleiche Stromtarife über den E-Control Tarifkalkulator.",
    input_schema={
        "type": "object",
        "properties": {
            "plz": {"type": "string"},
            "jahresverbrauch_kwh": {"type": "number"},
            "aktueller_lieferant": {"type": "string"},
            "aktueller_energiepreis": {"type": "number"},
            "aktuelle_grundgebuehr": {"type": "number"},
        },
        "required": ["plz", "jahresverbrauch_kwh", "aktueller_lieferant", "aktueller_energiepreis", "aktuelle_grundgebuehr"],
    },
    handler=compare_tariffs,
)

# Create LLM provider (needs ANTHROPIC_API_KEY env var)
provider = create_provider(
    "claude",
    api_key=os.environ["ANTHROPIC_API_KEY"],
    model="claude-haiku-4-5-20251001",
)

# Create agent
agent = GridbertAgent(
    registry,
    provider,
    system_prompt_builder=lambda: "Du bist ein hilfreicher Energieberater für Österreich.",
    max_tokens=4096,
)

# Run
result = agent.run("Vergleiche Tarife für PLZ 1060, 3200 kWh, aktuell Wien Energie mit 25 ct/kWh und 3.50 €/Monat Grundgebühr.")
print(result)
