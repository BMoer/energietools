# Netz & Netzentgelte

Das Netzentgelt ist der Preis dafür, dass der Strom über die Leitungen zu dir kommt. Es ist **reguliert** (kein Wettbewerb), in der bundesweiten Systemnutzungsentgelte-Verordnung festgelegt und hängt allein an deinem **Netzbereich**, also an deiner Adresse - nicht am Lieferanten.

## Worum es geht

- **Netzebenen (NE 1-7):** Das Netz ist in sieben Spannungsebenen gegliedert. Haushalte hängen an **NE 7** (Niederspannung, 400 V) als „nicht gemessene Leistung". Je tiefer die Ebene, desto höher das Entgelt pro kWh - die Kosten höherer Ebenen werden nach unten weitergewälzt.
- **Zwei Komponenten:** Netznutzungsentgelt (Arbeitspreis ct/kWh + Pauschale, 2026 bundesweit einheitlich 54,00 €/Jahr pro Zählpunkt) und Netzverlustentgelt (ct/kWh, deckt physikalische Leitungsverluste).
- **Regulierte Kosten:** Festgelegt in der **Systemnutzungsentgelte-Verordnung (BGBl. II Nr. 305/2025)**, jährlich novelliert. Kein Verhandeln, kein Wechseln.
- **14 Netzbereiche:** 9 Bundesländer + 4 Stadt-Netzbereiche (Linz, Graz, Innsbruck, Klagenfurt) + Sonderfall Kleinwalsertal. Der NE-7-Arbeitspreis spreizt vom günstigsten (Vorarlberg) zum teuersten Land (Kärnten) um fast Faktor 2.
- **Kleine Stadtwerke = Netzbereich-Tarif:** Die ~119 VNB billen unter Novelle 2026 nur noch die 14 Netzbereich-Tarife. Der konkrete Betreibername ist Attribution, kein eigener Preis.

Die konkrete Tarif-Tabelle, alle 14 Netzbereiche und der vollständige Rechenweg stehen in der eigenen Seite: **[[netz/netzentgelte]]**.

## Siehe auch

- [[netz/netzentgelte]] - die 14 Netzbereiche, NE-7-Arbeitspreise und Rechenweg im Detail
- [[markt/index]] - warum Netzbetreiber und Lieferant getrennte Rollen sind
- [[steuern/index]] - die Abgaben, die auf die verbrauchsabhängigen Komponenten aufsetzen
- [[wirtschaftlichkeit/index]] - Netz als Block 2 der Gesamtkosten
- [[gas/index]] - das eigene Netzentgelt-System für Gas
- [[glossar]]

## Berechnet von

- Capability `netzkosten` - regulierte brutto-Jahres-Netzkosten (NE-7-Haushalt) je PLZ
- Capability `grid_fees` - Netzentgelt je Betreiber/Land, per kWh (inkl. §16b-Speicherbefreiung)
- Capability `netz_verfuegbar` - prüft, ob ein Tarif an einer PLZ verfügbar ist

Aufruf z. B.: `python -m energietools netzkosten --json '{"plz": "8010", "verbrauch_kwh": 3500}'`

## Quellen

- Systemnutzungsentgelte-Verordnung, BGBl. II Nr. 305/2025 (E-Control), in Kraft 01.01.2026
- VNB-Preisblätter Netznutzung Strom 2026 (First-Party-Bestätigung)
- Daten-Snapshot: `energietools/data/netz/` (netzkosten.json, plz_netzbereich.json + MANIFEST)
- Wissens-Referenz Preis-Zusammensetzung: [`NETZKOSTEN_UND_GEBUEHREN.md`](../../../NETZKOSTEN_UND_GEBUEHREN.md)
- Erhebung & Validierung: [`METHODIK.md`](../../../METHODIK.md)

Stand: 2026-06
