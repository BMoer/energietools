# energietools — Open-Source Toolkit für den österreichischen Energiemarkt

## What is this?

`energietools` is the open-source, **auditable** core of the Austrian energy market: the business logic anyone should be able to reproduce — tariff data, invoice scanning, and the comparison that joins them. Every number it produces carries a transparent `Rechenweg` (netto → discount → Gebrauchsabgabe → USt → brutto), so a result can be re-derived by hand or by an external auditor.

At its heart is a versioned **Open-Data tariff catalog** (`energietools/data/tariffs/`) — a normalized, first-party snapshot of Austrian electricity tariffs (net list prices). Tariff comparison runs entirely offline against this catalog — no external tariff API, no live lookups.

The toolkit is organized around a **capability spine** (`energietools/capabilities/`): each capability has one shape (`run(**kwargs) -> CapabilityResult`) and self-registers into both a CLI and a lightweight multi-provider agent framework (Claude, OpenAI, Mistral).

## Installation

```bash
# Core package
pip install energietools

# All optional dependencies
pip install energietools[all]

# Specific extras
pip install energietools[llm]       # Claude / Anthropic
pip install energietools[openai]    # OpenAI GPT
pip install energietools[mistral]   # Mistral (via the OpenAI-compatible SDK)
pip install energietools[analysis]  # FDA anomaly detection, spot prices
pip install energietools[pdf]       # PDF invoice parsing, document generation
pip install energietools[search]    # Web search via DuckDuckGo
pip install energietools[excel]     # Excel file support
pip install energietools[ollama]    # Local LLM (invoice_parser fallback only)
```

## Quick Start

```python
from energietools.capabilities.tariffs import compare_against_catalog

# Compare your current tariff against the Open-Data catalog — offline, auditable.
result = compare_against_catalog(
    verbrauch_kwh=3200,
    aktueller_lieferant="Wien Energie",
    aktueller_energiepreis_ct_kwh=25.0,    # brutto, from your invoice
    aktuelle_grundgebuehr_eur_monat=6.0,    # brutto
    gebrauchsabgabe_rate=0.07,              # Vienna
    plz="1060",
)

print(f"Max Ersparnis: {result.max_ersparnis_eur:.0f} € / Jahr")
for t in result.beste_fix[:5]:
    print(f"{t.lieferant} {t.tarif_name}: {t.jahreskosten_eur:.0f} € / Jahr")

# Every tariff carries a full Rechenweg you can audit:
print(result.beste_fix[0].rechenweg.model_dump())
```

### CLI

```bash
python -m energietools list
python -m energietools tariff_catalog --json '{"oekostrom": true}'
python -m energietools tariff_compare --json '{"verbrauch_kwh": 3200,
  "aktueller_energiepreis_ct_kwh": 25, "aktuelle_grundgebuehr_eur_monat": 6,
  "gebrauchsabgabe_rate": 0.07}'
```

## Capabilities

The auditable core, on the capability spine (`energietools/capabilities/`):

Every capability has one shape — `run(**kwargs) -> CapabilityResult` — and self-registers into the CLI and agent. List them with `python -m energietools list`.

| Capability | Description |
|------------|-------------|
| `tariff_catalog` | Query the Open-Data catalog of Austrian electricity tariffs (net list prices), filter by type / Ökostrom / provider / contract lock-in |
| `tariff_compare` | Compare a current tariff (invoice prices) against the catalog — offline, with a full `Rechenweg` per tariff |
| `tariff_advice` | Join scanned invoice data with the catalog into one auditable comparison (the invoice → comparison pillar) |
| `community_metrics` | Energy-community metrics (SSR/self-sufficiency, SCR/self-consumption, Reststrom, Überschuss) from generation+consumption series |
| `netzkosten` | Regulated gross yearly network costs (NE7 household) for a PLZ, from the Open-Data Netzbereiche — VNB, amount and a full Rechenweg (fail-open on unknown PLZ) |
| `gesamtkosten` | Full gross yearly household costs: energy (Arbeitspreis + Grundgebühr) + Gebrauchsabgabe + 20 % USt + regulated network costs, with a full Rechenweg |
| `netz_verfuegbar` | Check whether a tariff with a given service area ('AT', a Bundesland or a list) is available at a PLZ (fail-open on unknown PLZ) |
| `tarifvergleich_inkl_netz` | Compare a current tariff (invoice prices) against the catalog and auto-add the regulated network costs + Gebrauchsabgabe from the PLZ |
| `battery_sim`, `pv_sim`, `beg_advisor`, `spot_analysis`, `load_profile`, `energy_monitor`, `web_search` | Existing deterministic tools, bridged onto the spine via `FunctionCapability` (lazy-imported) |

The catalog (`energietools/data/tariffs/catalog.json` + `MANIFEST.json`) is a versioned, first-party snapshot. Provenance and license are in the MANIFEST. The scrapers that produce it are **not** part of this repo (they stay proprietary); only the resulting data is published here.

## Available Tools

> The remaining `tools/` not yet on the spine:

| Tool | Description |
|------|-------------|
| `smartmeter` | Smart meter data access — needs live credentials (kept off the JSON-callable spine). Currently Wiener Netze implemented; Netz NÖ is a stub (further operators in progress) |
| `switching` | Generate Vollmacht PDF for provider switching (file side-effect, kept off the spine) |
| `invoice_parser` | OCR electricity-bill parsing (Claude Vision, with Ollama fallback) — feeds `tariff_advice` |
| `load_profile` | Analyze smart meter load profiles (FDA anomaly detection, heatmaps) |
| `spot_analysis` | Spot tariff analysis using ENTSO-E day-ahead prices |
| `battery_sim` | Home battery storage simulation (2/5/10/15 kWh scenarios) |
| `pv_sim` | PV and balcony power station simulation using PVGIS |
| `beg_advisor` | Evaluate Bürgerenergiegemeinschaft (BEG) membership options |
| `energy_monitor` | Energy news, Förderungen catalog, RSS feeds |
| `web_search` | DuckDuckGo web search for energy topics |

## Agent Framework

Build a conversational energy assistant in a few lines:

```python
from energietools.agent.registry import ToolRegistry
from energietools.agent.loop import EnergiAgent
from energietools.llm import create_provider
from energietools.capabilities.tariffs import compare_against_catalog

# Register tools
registry = ToolRegistry()
registry.register(
    name="compare_against_catalog",
    description="Vergleiche einen aktuellen Stromtarif gegen den Open-Data-Katalog",
    input_schema={
        "type": "object",
        "properties": {
            "verbrauch_kwh": {"type": "number"},
            "aktueller_lieferant": {"type": "string"},
            "aktueller_energiepreis_ct_kwh": {"type": "number"},
            "aktuelle_grundgebuehr_eur_monat": {"type": "number"},
            "gebrauchsabgabe_rate": {"type": "number"},
            "plz": {"type": "string"},
        },
        "required": [
            "verbrauch_kwh",
            "aktueller_lieferant",
            "aktueller_energiepreis_ct_kwh",
            "aktuelle_grundgebuehr_eur_monat",
        ],
    },
    handler=compare_against_catalog,
)

# Create LLM provider (Claude, OpenAI, or Mistral).
# Mistral talks to its OpenAI-compatible API via the openai SDK, so
# `pip install energietools[mistral]` and `[openai]` share the same dependency.
provider = create_provider("claude", api_key="sk-ant-...", model="claude-haiku-4-5-20251001")

# Run the agent
agent = EnergiAgent(
    registry,
    provider,
    system_prompt_builder=lambda: "Du bist ein österreichischer Energieberater.",
    max_tokens=4096,
)

result = agent.run("Vergleiche meinen Tarif (Wien Energie, 3200 kWh/Jahr, "
                   "25 ct/kWh brutto, 6 €/Monat, PLZ 1060) gegen den Katalog.")
print(result)
```

## Roadmap

The repo is on the capability spine.

- **Done (Phase 1):** capability spine, Open-Data tariff catalog, auditable offline `tariff_compare` (no external tariff API).
- **Done (Phase 2):** `tariff_advice` (invoice → catalog comparison, the auditable pillar); `community_metrics` (EEG/BEG SSR/SCR/Reststrom/Überschuss); existing deterministic tools bridged onto the spine via `FunctionCapability`.
- **Next:** spine adapters for `smartmeter`/`switching` (credentials / file side-effects); deeper EEG analysis (temporal, EPEX correlation, AT extrapolation).

The boundary: the **auditable business logic** (tariff data, invoice scanning, comparison) is open here; the machinery that produces the data (scrapers, hosting, UI) stays proprietary.

## Documentation

- **[METHODIK.md](METHODIK.md)** — how the data (tariffs + network costs) is collected & validated: First-Party + statutory sources, the cross-check against the federal tariff regulation (BGBl. II Nr. 305/2025, no external calculator), the 14 NE7-Netzbereiche, the attribution layer, fail-open discipline, and a reviewer checklist.
- **[NETZKOSTEN_UND_GEBUEHREN.md](NETZKOSTEN_UND_GEBUEHREN.md)** — knowledge reference (LLM-wiki source): how an Austrian household electricity price is composed — network costs, levies, taxes, and how they interact with the competitive energy price — with the full Rechenweg and a worked example.

## License

MIT — see [LICENSE](LICENSE).

The bundled tariff **data** (`energietools/data/tariffs/`) is licensed **MIT**, same as the code (see the `license` field in `MANIFEST.json`).
