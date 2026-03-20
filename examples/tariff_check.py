#!/usr/bin/env python3
"""Example: Compare electricity tariffs for a given postal code."""
from energietools.tools.tariff_compare import compare_tariffs

result = compare_tariffs(
    plz="1060",
    jahresverbrauch_kwh=3200,
    aktueller_lieferant="Wien Energie",
    aktueller_energiepreis=25.0,
    aktuelle_grundgebuehr=3.50,
)

print(f"Aktuell: {result.aktueller_tarif.lieferant} — {result.aktueller_tarif.jahreskosten_eur:.0f} €/Jahr")
print(f"Max Ersparnis: {result.max_ersparnis_eur:.0f} €/Jahr")
print(f"\nTop 3 Fixpreis-Tarife:")
for t in result.beste_fix[:3]:
    print(f"  {t.lieferant} {t.tarif_name}: {t.jahreskosten_eur:.0f} €/Jahr (spart {t.ersparnis_eur:.0f} €)")
