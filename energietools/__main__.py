# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""CLI: Capabilities von der Kommandozeile ausführen.

Die CLI wird vollständig aus der Capability-Registry generiert — jede neue
Capability ist sofort aufrufbar, ohne CLI-Code zu ändern.

Usage:
    python -m energietools list
    python -m energietools tariff_catalog --json '{"oekostrom": true}'
    python -m energietools tariff_compare --json '{"verbrauch_kwh": 3200,
        "aktueller_energiepreis_ct_kwh": 25, "aktuelle_grundgebuehr_eur_monat": 6,
        "gebrauchsabgabe_rate": 0.07}'
"""

from __future__ import annotations

import argparse
import json
import sys

from energietools.capabilities.registry import default_registry


def main(argv: list[str] | None = None) -> int:
    registry = default_registry()

    parser = argparse.ArgumentParser(prog="energietools", description="Energie-Capabilities")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Verfügbare Capabilities auflisten")
    for cap in registry.all():
        cap_parser = sub.add_parser(cap.name, help=cap.summary)
        cap_parser.add_argument(
            "--json", default="{}", help="Eingabe-Parameter als JSON-Objekt",
        )

    args = parser.parse_args(argv)

    if args.command == "list":
        for cap in registry.all():
            print(f"  {cap.name:18s} {cap.summary}")
        return 0

    try:
        params = json.loads(args.json)
    except json.JSONDecodeError as exc:
        print(f"Ungültiges JSON in --json: {exc}", file=sys.stderr)
        return 2
    if not isinstance(params, dict):
        print("--json muss ein JSON-Objekt sein", file=sys.stderr)
        return 2

    result = registry.get(args.command).run(**params)
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
