# Gas

Erdgas folgt derselben Logik wie Strom: ein wettbewerblicher Energiepreis, ein reguliertes Netzentgelt, Steuern/Abgaben und USt. Wer mit Gas heizt, vergleicht heute aber zunehmend nicht nur Gasanbieter, sondern Gas gegen die **Wärmepumpe** - einen Heizkostenvergleich über zwei verschiedene Energieträger.

## Worum es geht

- **Erdgaspreis-Komponenten:** Arbeitspreis (ct/kWh) + Grundgebühr beim Lieferanten (wettbewerblich), dazu das regulierte Gas-Netzentgelt, die Erdgasabgabe, der Beitrag zum Förderaufwand und 20 % USt - strukturell analog zu den vier Stromblöcken.
- **Netzentgelt Gas:** Eigenes reguliertes System (Gas-Systemnutzungsentgelte-Verordnung der E-Control), nach Netzebenen und Netzbereichen, getrennt vom Strom-Netzentgelt. Auch hier: ortsabhängig, nicht wechselbar.
- **Gas vs. Wärmepumpe:** Der Vergleich rechnet die Heizarbeit (kWh Wärmebedarf) auf beide Wege um. Gas: Brennstoffpreis ÷ Kesselwirkungsgrad. Wärmepumpe: Strompreis ÷ Jahresarbeitszahl (JAZ). Eine JAZ von 3-4 macht aus 1 kWh Strom 3-4 kWh Wärme - der Hebel, der die Wärmepumpe trotz höherem Strompreis konkurrenzfähig macht.
- **Was den Vergleich kippt:** Strompreis vs. Gaspreis, JAZ der Wärmepumpe, Eigenstrom aus PV (senkt den effektiven Strompreis) und Förderungen für den Heizungstausch.

## Siehe auch

- [[netz/index]] - das Strom-Netzentgelt-System (Gas analog, eigene Verordnung)
- [[tarife/index]] - wettbewerblicher Energiepreis (Strom wie Gas)
- [[steuern/index]] - Abgaben und USt (Erdgasabgabe statt Elektrizitätsabgabe)
- [[wirtschaftlichkeit/index]] - Heizkostenvergleich, ROI eines Heizungstauschs
- [[foerderung/index]] - Förderungen für Wärmepumpe und Heizungstausch
- [[glossar]]

## Berechnet von

- Wirtschaftlichkeit des Wechsels (Gas → Wärmepumpe): Capability `finance` (ROI/NPV/LCOE)
- Förderkontext: Tool `energy_monitor` (Förderungen-Katalog)

## Quellen

- Gas-Systemnutzungsentgelte-Verordnung (E-Control) - reguliertes Gas-Netzentgelt
- Erdgasabgabegesetz (ErdgasAbgG) - Erdgasabgabe
- Förderdaten: `energietools/data/foerderungen.json` (Kategorie Heizung)
- Preis-Zusammensetzung (Strom, analog für Gas): [`NETZKOSTEN_UND_GEBUEHREN.md`](../../../NETZKOSTEN_UND_GEBUEHREN.md)

Stand: 2026-06
