# Wie sich der Strompreis in Österreich zusammensetzt

Eine österreichische Haushalts-Stromrechnung besteht aus **vier klar trennbaren Blöcken**. Nur **einer** davon ist wettbewerblich - alle anderen sind ein ortsabhängiger bzw. gesetzlicher Sockel, den ein Anbieterwechsel nicht bewegt. Diese Seite ist der Überblick; Details stehen auf den verlinkten Konzeptseiten.

## Die vier Blöcke im Überblick

| Block | Was | Wer setzt ihn fest | Beeinflussbar? |
|---|---|---|---|
| **1. Energiepreis** | Arbeitspreis (ct/kWh) + Grundgebühr (€/Monat) | **Lieferant** (Markt) | **Ja** - Anbieterwechsel |
| **2. Netzkosten** | Netznutzung + Netzverlust | Bundesweite Systemnutzungsentgelte-Verordnung, je Netzbereich | Nein - hängt am Wohnort |
| **3. Steuern & Abgaben** | EAG-Förderbeitrag, Elektrizitätsabgabe, Gebrauchsabgabe | Bund + Land/Gemeinde | Nein |
| **4. Umsatzsteuer** | 20 % auf die Summe (netto → brutto) | Bund | Nein |

**Faustregel der Anteile** (Haushalt, je nach Netzbereich/Verbrauch): Energie ~40-50 %, Netzkosten ~25-35 %, Steuern & Abgaben ~20-30 %. Der Anbieterwechsel wirkt **nur auf Block 1**; Block 2-4 sind für eine gegebene Adresse fix.

## Block 1 - Energiepreis (wettbewerblich)

Der Lieferant verkauft die Energie im Wettbewerb: Arbeitspreis (ct/kWh, verbrauchsabhängig) + Grundgebühr (€/Monat, fix). Fixtarife garantieren den Preis für eine Laufzeit; Spot-/Floater-Tarife reichen den schwankenden Großhandelspreis weiter. Das ist der einzige Block, den ein Anbieterwechsel bewegt. Details: [[tarife/index]], [[markt/index]].

## Block 2 - Netzkosten (reguliert)

Das Entgelt dafür, dass der Strom über das Netz zum Haushalt kommt - kein Wettbewerb, sondern bundesweit per Systemnutzungsentgelte-Verordnung (BGBl. II Nr. 305/2025) je Netzbereich festgelegt. Besteht aus Netznutzungsentgelt (Arbeitspreis ct/kWh + Pauschale €/Jahr) und Netzverlustentgelt (ct/kWh). Zwei Nachbarn mit unterschiedlichen Lieferanten zahlen dieselben Netzkosten. Details inkl. Rechenweg und Beispiel: [[netz/netzentgelte]], [[netz/index]].

## Block 3 - Steuern & Abgaben

Über Energiepreis und Netzkosten liegen die staatlich festgelegten Abgaben: Elektrizitätsabgabe (Stromsteuer des Bundes, ElAbgG), EAG-Förderbeitrag (finanziert den Ökostrom-Ausbau, bundesweit uniform) und die kommunale Gebrauchsabgabe (Landesrecht, je Gemeinde verschieden - z. B. Wien, viele andere Gemeinden 0 %). Details: [[steuern/index]].

## Block 4 - Umsatzsteuer

20 % auf die Summe aus Energie + Netz + Abgaben (netto → brutto: × 1,20). Bundesweit einheitlich.

## Warum die Trennung zählt

Ein Tarifvergleich, der Netzkosten in den "Preis" mischt, vergleicht Äpfel mit Birnen: Netzkosten und Abgaben sind für alle Angebote an einer Adresse identisch. Korrekt ist: Energiepreise vergleichen, Netzkosten/Abgaben als konstanten, ortsabhängigen Kontext daneben ausweisen. Genau das leistet ein auditierbarer Gesamtkosten-Vergleich. Details: [[wirtschaftlichkeit/index]].

## Siehe auch

- [[markt/index]] - Lieferant vs. Netzbetreiber, Marktrollen, Bilanzgruppen
- [[netz/netzentgelte]] - Netzkosten im Detail, mit vollständig durchgerechnetem Beispiel
- [[steuern/index]] - Elektrizitätsabgabe, EAG-Förderbeitrag, Gebrauchsabgabe im Detail
- [[wirtschaftlichkeit/index]] - wie die vier Blöcke zur Gesamtjahresrechnung werden
- [[glossar]] - Begriffe von Arbeitspreis bis Zählpunkt

## Berechnet von

- Capability `gesamtkosten` - volle brutto-Jahreskosten (alle vier Blöcke) je PLZ mit Rechenweg
- Capability `netzkosten` / `grid_fees` - Block 2 allein, je PLZ bzw. Netzbetreiber
- Capability `tariff_compare` - Block 1 gegen den Open-Data-Katalog, Blöcke 2-4 als Kontext daneben

## Quellen

- Preis-Zusammensetzung im Detail (Rechenweg, Beispiel, Stolpersteine): [`NETZKOSTEN_UND_GEBUEHREN.md`](../../NETZKOSTEN_UND_GEBUEHREN.md)
- Systemnutzungsentgelte-Verordnung, BGBl. II Nr. 305/2025 (E-Control)
- ElAbgG (Elektrizitätsabgabegesetz), EAG (Erneuerbaren-Ausbau-Gesetz) / ÖMAG
- Erhebung & Validierung: [`METHODIK.md`](../../METHODIK.md)

Stand: 2026-06
