# Förderungen

Förderungen sind öffentliche Zuschüsse, die die Wirtschaftlichkeit von Energie-Investitionen verbessern - vor allem **PV, Speicher und Wärmepumpe**. Sie kommen von Bund, Ländern und teils Gemeinden, haben Budgets, Fristen und Voraussetzungen, und ändern sich häufig. Deshalb zählt hier die Aktualität.

## Worum es geht

- **Aktive Programme:** Der Datensatz deckt PV-Anlagen, Batteriespeicher, Heizungstausch, thermische Sanierung, Balkonkraftwerke und weitere Kategorien ab - 10 Bundesförderungen + 35 Landes-/Gemeinde-Förderungen (Bund + alle 9 Bundesländer, inkl. Graz, Linz, Innsbruck, Villach).
- **Woher die Daten kommen:** Ein versionierter Snapshot unter `energietools/data/foerderungen/foerderungen.json` + `MANIFEST.json`. Jeder Eintrag trägt Ebene (Bund/Land), Status (offen/geschlossen/unsicher), Fördersatz mit Rechenweg-Werten, Bedingungen, Zielgruppe, nächstes Antragsfenster und die offizielle Quelle samt URL und Abrufdatum.
- **Aktualität:** Das `MANIFEST.json` trägt `stand_recherche` und `coverage` (Zahl offen/geschlossen/verifiziert je Snapshot). Förderlandschaften veralten schnell - mehrere Bundesprogramme (Kesseltausch, Sauber Heizen für Alle, Sanierungsbonus) sind seit Mitte 2026 budgeterschöpft und für neue Fälle geschlossen, obwohl einzelne Landesrichtlinien formal weiterlaufen.
- **Ehrlichkeit bei Unsicherheit:** Einträge mit `verlaesslichkeit: "unsicher"` (z.B. kolportierte, nicht primärquellenverifizierte Balkonkraftwerk-Beträge) bleiben im Datensatz sichtbar, werden aber von der Capability `foerderungen_check` standardmäßig ausgeblendet (`inkl_unsicher=False`) - nie ungefragt als Fakt ausgespielt.
- **Ohne Gewähr:** Alle Angaben sind kuratiert, aber nicht rechtsverbindlich. **Vor jeder Antragstellung die offizielle Quelle prüfen** - Konditionen und Verfügbarkeit können sich kurzfristig ändern.

## Siehe auch

- [[wirtschaftlichkeit/index]] - wie Förderungen ROI, NPV und Amortisation verbessern
- [[messung/index]] - Smart Meter und Eigenverbrauch als häufige Förder-Voraussetzung
- [[gas/index]] - Wärmepumpe statt Gas (oft förderfähiger Heizungstausch)
- [[markt/index]] - Markt- und Marktrollen-Kontext
- [[glossar]]

## Berechnet von

- Capability `foerderungen_check` - offene (optional auch geschlossene) Förderungen je Bundesland/PLZ, mit Rechenweg-Werten und Quellen
- Tool `energy_monitor` - Förderungen gefiltert nach PLZ/Region, Energie-News und RSS-Feeds
- Die Wirtschaftlichkeit einer geförderten Investition rechnet die Capability `finance` (ROI/NPV/LCOE)

## Quellen

- Daten-Snapshot: `energietools/data/foerderungen/foerderungen.json` + `MANIFEST.json` (`stand_recherche`, `coverage`, `provenance`)
- Jeweils die in den Einträgen verlinkten offiziellen Förderstellen (Bund / Länder / Gemeinden)
- Hinweis aus dem MANIFEST: „Kuratierte Förderdaten, ohne Gewähr. Vor Antragstellung immer die offizielle Quelle prüfen."

Stand: 2026-08
