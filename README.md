# energietools — Open-Source Toolkit für den österreichischen Energiemarkt

## What is this?

`energietools` is an open-source Python toolkit for analyzing and optimizing energy consumption in Austria. It provides deterministic tools for tariff comparison, load profile analysis, battery/PV simulation, smart meter data access, and more — all powered by official Austrian data sources (E-Control API, PVGIS, ENTSO-E).

The toolkit also includes a lightweight agent framework with multi-provider LLM support (Claude, OpenAI, Ollama) so you can build conversational energy assistants without depending on heavy frameworks like LangChain.

## Installation

```bash
# Core package
pip install energietools

# All optional dependencies
pip install energietools[all]

# Specific extras
pip install energietools[llm]       # Claude / Anthropic
pip install energietools[openai]    # OpenAI GPT
pip install energietools[analysis]  # FDA anomaly detection, spot prices
pip install energietools[pdf]       # PDF invoice parsing, document generation
pip install energietools[search]    # Web search via DuckDuckGo
pip install energietools[excel]     # Excel file support
pip install energietools[ollama]    # Local LLM via Ollama
```

## Quick Start

```python
from energietools.tools.tariff_compare import compare_tariffs

# Compare electricity tariffs for a household in Vienna
result = compare_tariffs(
    zip_code="1060",
    annual_kwh=3200,
    grid_operator="Wiener Netze",
)

for tariff in result.tariffs[:5]:
    print(f"{tariff.provider}: {tariff.annual_cost_brutto:.2f} € / Jahr")
```

## Available Tools

| Tool | Description |
|------|-------------|
| `tariff_compare` | Compare electricity tariffs via E-Control API |
| `gas_compare` | Compare gas tariffs via E-Control API |
| `load_profile` | Analyze smart meter load profiles (FDA anomaly detection, heatmaps) |
| `spot_analysis` | Spot tariff analysis using ENTSO-E day-ahead prices |
| `battery_sim` | Home battery storage simulation (2/5/10/15 kWh scenarios) |
| `pv_sim` | PV and balcony power station simulation using PVGIS |
| `beg_advisor` | Evaluate Bürgerenergiegemeinschaft (BEG) membership options |
| `invoice_parser` | OCR electricity bill parsing (Claude Vision or Ollama) |
| `smartmeter` | Smart meter data access (7 Austrian grid operators) |
| `energy_monitor` | Energy news, Förderungen catalog, RSS feeds |
| `web_search` | DuckDuckGo web search for energy topics |
| `switching` | Generate Vollmacht PDF for provider switching |

## Agent Framework

Build a conversational energy assistant in a few lines:

```python
from energietools.agent.registry import ToolRegistry
from energietools.agent.loop import EnergiAgent
from energietools.llm import create_provider
from energietools.tools.tariff_compare import compare_tariffs

# Register tools
registry = ToolRegistry()
registry.register(
    name="compare_tariffs",
    description="Vergleiche Stromtarife für eine österreichische Postleitzahl",
    input_schema={
        "type": "object",
        "properties": {
            "zip_code": {"type": "string"},
            "annual_kwh": {"type": "number"},
        },
        "required": ["zip_code", "annual_kwh"],
    },
    handler=compare_tariffs,
)

# Create LLM provider (Claude, OpenAI, or Ollama)
provider = create_provider("claude", api_key="sk-ant-...", model="claude-haiku-4-5-20251001")

# Run the agent
agent = EnergiAgent(
    registry=registry,
    provider=provider,
    system_prompt_builder=lambda: "Du bist ein österreichischer Energieberater.",
    max_tokens=4096,
)

result = agent.run("Vergleiche Tarife für PLZ 1060 mit 3200 kWh Jahresverbrauch")
print(result)
```

## License

MIT — see [LICENSE](LICENSE).
