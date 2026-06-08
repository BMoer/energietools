# Steuern & Abgaben

Über Energiepreis und Netzkosten liegen die staatlich festgelegten Abgaben - **Block 3** der Stromrechnung. Sie sind nicht beeinflussbar: teils bundesweit uniform (Gesetz/Verordnung), teils gemeindespezifisch (Landesrecht). Obendrauf kommt die Umsatzsteuer als Block 4.

## Worum es geht

- **Elektrizitätsabgabe (ElAbgG):** Stromsteuer des Bundes. Regelsatz 1,5 ct/kWh, für 2026 temporär auf **0,10 ct/kWh** (Haushalt) gesenkt. Achtung: Die Senkung ist befristet - läuft sie aus, gilt wieder 1,5 ct/kWh.
- **EAG-Förderbeitrag (bundesweit):** Finanziert den Ökostrom-Ausbau (EAG / ÖMAG). Fällt verbrauchsabhängig an (Netznutzungs- + Netzverlust-Anteil, in Summe ~0,620 ct/kWh) plus eine fixe Förderpauschale je Zählpunkt (€/Jahr). Überall in Österreich gleich.
- **Gebrauchsabgabe (gemeindespezifisch):** Kommunale Abgabe für die Nutzung des öffentlichen Guts (Leitungen im Gemeindegebiet). Satz und Bemessungsbasis variieren je Gemeinde (z. B. Wien 7 %; Burgenland und Vorarlberg 0 %). Wird nur angesetzt, wenn Satz **und** Basis belegt sind - sonst rate=0.
- **Umsatzsteuer (Block 4):** 20 % auf die Summe aus Energie + Netz + Abgaben (netto → brutto: × 1,20).

## Siehe auch

- [[netz/index]] - die verbrauchsabhängigen Netz-Komponenten, auf die der EAG-Beitrag aufsetzt
- [[markt/index]] - der wettbewerbliche Energiepreis darunter
- [[wirtschaftlichkeit/index]] - Steuern/Abgaben als Block 3 der Gesamtkosten
- [[tarife/index]] - wie Gebrauchsabgabe und USt in den Tarifvergleich einfließen
- [[glossar]]

## Berechnet von

- Capability `gesamtkosten` - bezieht Elektrizitätsabgabe, EAG-Beitrag, Gebrauchsabgabe und USt in die Jahresrechnung ein (voller Rechenweg)

## Quellen

- ElAbgG (Elektrizitätsabgabegesetz) - inkl. temporärer 2026-Senkung
- EAG (Erneuerbaren-Ausbau-Gesetz) / ÖMAG - Förderbeitrag & Förderpauschale 2026
- Landes-/Gemeinde-Gebrauchsabgabegesetze - Satz und Basis je Gemeinde
- Daten-Snapshot: `energietools/data/netz/abgaben.json`
- Wissens-Referenz: [`NETZKOSTEN_UND_GEBUEHREN.md`](../../NETZKOSTEN_UND_GEBUEHREN.md) (Abschnitt 3)
- Erhebung & Validierung: [`METHODIK.md`](../../METHODIK.md)

Stand: 2026-06
