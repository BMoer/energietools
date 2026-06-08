# Förderungen

Förderungen sind öffentliche Zuschüsse, die die Wirtschaftlichkeit von Energie-Investitionen verbessern - vor allem **PV, Speicher und Wärmepumpe**. Sie kommen von Bund, Ländern und teils Gemeinden, haben Budgets, Fristen und Voraussetzungen, und ändern sich häufig. Deshalb zählt hier die Aktualität.

## Worum es geht

- **Aktive Programme:** Der kuratierte Katalog deckt unter anderem PV-Anlagen, Batteriespeicher, Wärmepumpen, thermische Sanierung und Entlastungsmaßnahmen ab - bundesweit und je Bundesland.
- **Woher die Daten kommen:** Ein versionierter Snapshot unter `energietools/data/foerderungen.json`. Jeder Eintrag trägt Betrag, Zielgruppe, Bundesland, Gültigkeit (gueltig_ab / gueltig_bis), Status, Voraussetzungen und die offizielle Quelle samt URL.
- **Aktualität:** Der Snapshot trägt ein `_meta`-Feld mit `stand` und `naechste_pruefung`. Förderlandschaften veralten schnell - Budgets sind oft ausgeschöpft, bevor das Jahr endet.
- **Ohne Gewähr:** Alle Angaben sind kuratiert, aber nicht rechtsverbindlich. **Vor jeder Antragstellung die offizielle Quelle prüfen** - Konditionen und Verfügbarkeit können sich kurzfristig ändern.

## Siehe auch

- [[wirtschaftlichkeit/index]] - wie Förderungen ROI, NPV und Amortisation verbessern
- [[messung/index]] - Smart Meter und Eigenverbrauch als häufige Förder-Voraussetzung
- [[gas/index]] - Wärmepumpe statt Gas (oft förderfähiger Heizungstausch)
- [[markt/index]] - Markt- und Marktrollen-Kontext
- [[glossar]]

## Berechnet von

- Tool `energy_monitor` - Förderungen-Katalog, Energie-News und RSS-Feeds
- Die Wirtschaftlichkeit einer geförderten Investition rechnet die Capability `finance` (ROI/NPV/LCOE)

## Quellen

- Daten-Snapshot: `energietools/data/foerderungen.json` (kuratierter Katalog, `_meta.stand` und `_meta.naechste_pruefung`)
- Jeweils die in den Einträgen verlinkten offiziellen Förderstellen (Bund / Länder / Gemeinden)
- Hinweis aus dem Snapshot: „Alle Angaben ohne Gewähr. Vor Antragstellung immer die offizielle Quelle prüfen."

Stand: 2026-06
