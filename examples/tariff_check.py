#!/usr/bin/env python3
"""Example: Compare an electricity tariff against the Open-Data catalog.

No network, no external tariff API — the comparison runs entirely against the bundled
first-party tariff catalog and is fully auditable (every tariff carries a
Rechenweg).
"""
from energietools.capabilities.tariffs import compare_against_catalog

result = compare_against_catalog(
    verbrauch_kwh=3200,
    aktueller_lieferant="Wien Energie",
    aktueller_energiepreis_ct_kwh=25.0,   # brutto, von der Rechnung
    aktuelle_grundgebuehr_eur_monat=3.50,  # brutto
    gebrauchsabgabe_rate=0.07,             # Wien
    plz="1060",
)

print(f"Aktuell: {result.aktueller_tarif.lieferant} — {result.aktueller_tarif.jahreskosten_eur:.0f} €/Jahr")
print(f"Max Ersparnis: {result.max_ersparnis_eur:.0f} €/Jahr")
print("\nTop 3 Fixpreis-Tarife:")
for t in result.beste_fix[:3]:
    print(f"  {t.lieferant} {t.tarif_name}: {t.jahreskosten_eur:.0f} €/Jahr (spart {t.ersparnis_eur:.0f} €)")

# Audit: print the full Rechenweg of the cheapest tariff
best = result.beste_fix[0]
print(f"\nRechenweg {best.lieferant} — {best.tarif_name}:")
for k, v in best.rechenweg.model_dump().items():
    print(f"  {k}: {v}")
