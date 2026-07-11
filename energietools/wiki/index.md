# energietools Wiki

Das Wiki ist die WISSEN-Schicht von energietools. Es erklärt, was die Dinge im österreichischen Energiemarkt bedeuten, in welchem rechtlichen und wirtschaftlichen Zusammenhang sie stehen und wie die einzelnen Konzepte zusammenhängen. Es ist eine kuratierte Wissensbasis, kein Daten-Dump.

energietools besteht aus vier Schichten: WISSEN (dieses Wiki), DATEN (datierte, gequellte Snapshots unter `energietools/data/`), RECHNEN (Capabilities und der Baukasten aus `components`, `system`, `optimizer`) und PROZESSE (`energietools/prozesse/` - Gesprächsleitfäden für einen konkreten Anwendungsfall wie eine Rechnungsanalyse, D7). Das Wiki erklärt Bedeutung; die konkreten, tagesaktuellen Zahlen leben in den Daten-Snapshots, auf die das Wiki nur verweist; die Prozesse orchestrieren Wissen (per `get_knowledge`) und Rechnen (Capabilities) zu einem Gesprächsleitfaden.

## Was ist dieses Wiki

Eine Sammlung von Markdown-Seiten, ein Konzept pro Seite, jede Seite selbst-enthalten. Es ist kein Server und keine Datenbank: Ein Agent zeigt auf diesen Ordner, liest die Seiten und nutzt sie, um Begriffe einzuordnen und die richtige Capability auszuwählen. Wo eine Seite über konkrete Werte spricht, beschreibt sie die Bedeutung der Werte (zum Beispiel "Netznutzungsentgelt hängt von der Netzebene ab"), nicht die aktuelle Zahl selbst. Die Zahl kommt aus dem referenzierten Snapshot und trägt dort ihren eigenen Stand und ihre Quelle.

## Navigation

- [[stromkosten-zusammensetzung]] - Überblick: wie sich eine österreichische Stromrechnung aus Energiepreis, Netzkosten, Steuern/Abgaben und USt zusammensetzt (die vier Blöcke, Einstiegspunkt für `get_knowledge`).
- [[markt]] - der österreichische Strommarkt: Wettbewerb beim Energiepreis, regulierte Netzseite, Marktrollen und wie sich der Endpreis zusammensetzt.
- [[netz]] - Netzkosten und Netzentgelte: regulierte Durchleitungsentgelte je Netzebene und Netzbetreiber, Rechtsgrundlage Systemnutzungsentgelte-Verordnung.
- [[tarife]] - Stromtarife: Arbeitspreis, Grundgebühr, Tariftypen, Katalog und Vergleich der wettbewerblichen Energiekomponente.
- [[steuern]] - Steuern und Abgaben: Elektrizitätsabgabe, EAG-Förderbeitrag, Gebrauchsabgabe und Umsatzsteuer auf Strom.
- [[foerderung]] - Förderungen: Investitions- und Einspeisemodelle für PV, Speicher und Energiegemeinschaften.
- [[messung]] - Messung und Zählung: Smart Meter, Lastprofile, Viertelstundenwerte als Grundlage jeder Abrechnung und Optimierung.
- [[wirtschaftlichkeit]] - Wirtschaftlichkeit: ROI, NPV und LCOE für Investitionsentscheidungen rund um PV und Speicher.
- [[gas]] - Erdgas: Preisbestandteile, Netz und Abgaben im Gasbereich, parallel zum Strommarkt.

## Glossar

- [[glossar]] - kompakte Begriffsdefinitionen quer durch alle Kategorien, von Arbeitspreis bis Viertelstundenwert.

## Vertrauen & Herkunft

Jede gerechnete Zahl in energietools trägt einen nachvollziehbaren Rechenweg und eine Quelle. Zwei Dokumente im Repo-Root sind die Vertrauens-Anker:

- [METHODIK.md](../../METHODIK.md) beschreibt den Prozess: wie Daten erhoben, geprüft und validiert werden, bevor sie in einen Snapshot eingehen.
- [NETZKOSTEN_UND_GEBUEHREN.md](../../NETZKOSTEN_UND_GEBUEHREN.md) ist die Wissens-Referenz zur Preis-Zusammensetzung: wie sich der österreichische Strompreis aus Energie, Netzkosten, Steuern/Abgaben und Umsatzsteuer zusammensetzt.

Die Daten-Snapshots liegen unter `energietools/data/` (Tarifkatalog, Netzkosten, Abgaben, PLZ-Netzbereichs-Zuordnung, Förderungen), jeweils mit MANIFEST und Stand. Das Wiki referenziert diese Snapshots, enthält sie aber nicht.

Stand: 2026-06
