#!/usr/bin/env python3
"""Example: Standalone energy agent wired from the capability registry.

Every capability (tariff_catalog, tariff_compare, …) is registered into the
agent's tool registry in one call — add a capability and the agent gains it
for free.
"""
import os

from energietools.agent.capability_tools import register_capabilities
from energietools.agent.loop import GridbertAgent
from energietools.agent.registry import ToolRegistry
from energietools.llm import create_provider

# Wire all capabilities into the agent's tool registry
registry = register_capabilities(ToolRegistry())

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
result = agent.run(
    "Vergleiche meinen Tarif (3200 kWh/Jahr, 25 ct/kWh brutto, 3.50 €/Monat "
    "Grundgebühr, Wien mit 7% Gebrauchsabgabe) gegen den Katalog."
)
print(result)
