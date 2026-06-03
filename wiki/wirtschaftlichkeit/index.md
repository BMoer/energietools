# Wirtschaftlichkeit

Wirtschaftlichkeit beantwortet zwei Fragen: Was kostet Strom insgesamt, und lohnt sich eine Investition (PV, Speicher, Wärmepumpe)? Beides setzt auf demselben Fundament auf - der sauberen Zerlegung der Stromkosten in ihre vier Blöcke und auditierbaren Kennzahlen.

## Worum es geht

- **Gesamtkosten - vier Blöcke:** (1) **Energie** (Arbeitspreis + Grundgebühr, wettbewerblich), (2) **Netzkosten** (reguliert, je Netzbereich), (3) **Steuern & Abgaben** (Elektrizitätsabgabe, EAG-Beitrag bundesweit, Gebrauchsabgabe gemeindespezifisch), (4) **USt 20 %**. Nur Block 1 ist beeinflussbar; Block 2-4 sind ein ortsabhängiger Sockel.
- **Investitionskennzahlen:** ROI (Rendite), NPV (Kapitalwert über die Lebensdauer), Amortisation (simple payback) und LCOE (Stromgestehungskosten je kWh) machen eine Anlage vergleichbar - mit Förderungen, Strompreisentwicklung und Eigenverbrauch als Eingangsgrößen.
- **Eigenverbrauch & Autarkie:** Bei PV entscheidet, wie viel des erzeugten Stroms selbst genutzt wird (Eigenverbrauchsquote/SCR) und wie viel des Bedarfs die Anlage deckt (Autarkie/SSR). Beide treiben die Wirtschaftlichkeit stärker als die reine Anlagengröße, weil selbst genutzter Strom den vollen Bezugspreis spart, Einspeisung nur den Marktwert bringt.
- **Warum die Trennung zählt:** Eine Ersparnis im Energieblock ist real; Netz- und Abgabenkosten verschiebt keine Investition - sie reduziert nur die bezogene kWh-Menge.

## Siehe auch

- [[markt/index]], [[netz/index]], [[steuern/index]] - die vier Kostenblöcke im Detail
- [[tarife/index]] - Ersparnis im Energieblock durch Anbieterwechsel
- [[foerderung/index]] - Zuschüsse als Eingangsgröße der Investitionsrechnung
- [[messung/index]] - Lastprofile als Basis für Eigenverbrauch und Autarkie
- [[gas/index]] - Heizkostenvergleich Gas vs. Wärmepumpe
- [[glossar]]

## Berechnet von

- Capability `gesamtkosten` - volle brutto-Jahreskosten (alle vier Blöcke) je PLZ mit Rechenweg
- Capability `finance` - ROI / NPV / LCOE / Amortisation einer Investition
- Capability `community_metrics` - Eigenverbrauchsquote (SCR), Autarkie (SSR), Reststrom, Überschuss

## Quellen

- Daten-Snapshots: `energietools/data/netz/` und `energietools/data/tariffs/`
- Wissens-Referenz Preis-Zusammensetzung: [`NETZKOSTEN_UND_GEBUEHREN.md`](../../NETZKOSTEN_UND_GEBUEHREN.md)
- Erhebung & Validierung: [`METHODIK.md`](../../METHODIK.md)

Stand: 2026-06
