# Tarife

Ein Stromtarif ist der **wettbewerbliche Teil** der Rechnung - der Preis, den dein Lieferant für die Energie verlangt. Er besteht aus einem **Arbeitspreis** (ct/kWh, verbrauchsabhängig) und einer **Grundgebühr** (€/Monat, fix). Das ist der einzige Block, den du durch einen Anbieterwechsel bewegst.

## Worum es geht

- **Fix vs. Spot/Floater:** Fixtarife garantieren den Arbeitspreis für eine Laufzeit (Planungssicherheit). Spot-/Floater-Tarife reichen den schwankenden Großhandelspreis weiter (Chance auf günstige Stunden, aber Preisrisiko) - sinnvoll vor allem mit steuerbarem Verbrauch oder Smart Meter.
- **Zwei Preiskomponenten:** Arbeitspreis × Verbrauch + Grundgebühr × 12. Ein günstiger Arbeitspreis mit hoher Grundgebühr kann bei kleinem Verbrauch teurer sein als umgekehrt - deshalb zählt immer der Jahresbetrag, nicht der ct/kWh-Wert allein.
- **Vergleich ist auditierbar:** energietools vergleicht gegen einen versionierten **Open-Data-Tarifkatalog** (`energietools/data/tariffs/`), vollständig offline, ohne fremde Rechner-API. Jeder verglichene Tarif trägt einen vollständigen Rechenweg (netto → Rabatt → Gebrauchsabgabe → USt → brutto).
- **Saubere Trennung:** Ein korrekter Vergleich vergleicht nur Block 1 (Energie). Netzkosten und Abgaben sind für alle Angebote an einer Adresse identisch - sie gehören als konstanter Kontext daneben, nicht in den „Preis".

## Siehe auch

- [[markt/index]] - Lieferant, Spot/Großhandel und die Marktrollen
- [[netz/index]] - der ortsfeste Netz-Sockel, der nicht im Tarif liegt
- [[steuern/index]] - Abgaben und USt, die auf den Energiepreis aufsetzen
- [[messung/index]] - Smart Meter als Voraussetzung sinnvoller Spot-Tarife
- [[wirtschaftlichkeit/index]] - Energie als Block 1 der Gesamtkosten
- [[glossar]]

## Berechnet von

- Capability `tariff_catalog` - Open-Data-Katalog abfragen (filtern nach Typ / Ökostrom / Anbieter)
- Capability `tariff_compare` - aktuellen Tarif gegen den Katalog vergleichen (offline, voller Rechenweg)
- Capability `tariff_advice` - Rechnungsdaten + Katalog zu einem auditierbaren Vergleich verbinden
- Capability `tarifvergleich_inkl_netz` - Vergleich plus automatisch ergänzte Netzkosten je PLZ

Aufruf z. B.: `python -m energietools tariff_compare --json '{"verbrauch_kwh": 3200, "aktueller_energiepreis_ct_kwh": 25, "aktuelle_grundgebuehr_eur_monat": 6, "gebrauchsabgabe_rate": 0.07}'`

## Quellen

- Daten-Snapshot: `energietools/data/tariffs/` (catalog.json + MANIFEST.json mit Provenance/Lizenz)
- ElWOG / EAG - Preisblatt-Pflicht der Lieferanten (Primärquelle der Preise)
- Erhebung & Validierung: [`METHODIK.md`](../../../METHODIK.md)
- Preis-Zusammensetzung: [`NETZKOSTEN_UND_GEBUEHREN.md`](../../../NETZKOSTEN_UND_GEBUEHREN.md)

Stand: 2026-06
