# Netzentgelte

Das Netzentgelt ist der Preis, den ein Haushalt dem Verteilnetzbetreiber (VNB) dafür zahlt, dass der Strom über das Netz an die Verbrauchsstelle kommt. Es ist der zweite der vier Blöcke einer österreichischen Stromrechnung (Energie, Netz, Steuern/Abgaben, USt) und im Gegensatz zum Energiepreis nicht wettbewerblich, sondern bundesweit reguliert: Höhe und Struktur legt die Systemnutzungsentgelte-Verordnung (BGBl. II Nr. 305/2025) je Netzbereich fest. Das Netzentgelt hängt deshalb am Wohnort, nicht am Lieferanten - zwei Nachbarn mit verschiedenen Stromanbietern zahlen dasselbe Netzentgelt.

## Warum reguliert

Das Stromnetz ist ein natürliches Monopol: Niemand baut neben das bestehende Netz ein zweites. Damit ein Monopolist seine Preise nicht frei setzt, gibt die Regulierungsbehörde (E-Control) die zulässigen Entgelte per Verordnung vor. Der Netzbetreiber darf nur diese regulierten Werte verrechnen. Für den Haushalt heißt das: Das Netzentgelt ist ein ortsgebundener Sockel, den man durch Anbieterwechsel nicht senken kann - nur der Energiepreis (Block 1) ist verhandelbar.

## Die zwei regulierten Komponenten

Für einen Haushalt an Niederspannung (NE 7, "nicht gemessene Leistung", also ohne Lastprofilmessung) besteht das reine Netzentgelt aus genau zwei netzbereichsspezifischen Posten:

1. **Netznutzungsentgelt** (§ 5 der Verordnung) - das Entgelt für die Nutzung des Netzes. Es hat zwei Teile:
   - **Arbeitspreis (AP)** in **ct/kWh** - verbrauchsabhängig. Maßgeblich ist der Arbeitspreis rund um die Uhr (Standard-Einfachtarif), **nicht** SNAP (Sommer-Nieder) oder Doppeltarif Tag/Nacht.
   - **Pauschale / Grundpreis** in **EUR/Jahr pro Zählpunkt** - fix, verbrauchsunabhängig. Unter der Novelle 2026 bundesweit einheitlich **54,00 EUR/Jahr** für NE 7 "nicht gemessene Leistung".
2. **Netzverlustentgelt** (§ 6 der Verordnung) - deckt die physikalischen Leitungsverluste, in **ct/kWh**, ebenfalls je Netzbereich. Achtung: Es gibt einen Entnehmer-Wert (Verbraucher) und einen bundesweit uniformen Einspeiser-Wert (0,279 ct/kWh). Für die Haushaltskosten zählt der **Entnehmer**-Wert.

## Was im Netz-Rechenweg zusätzlich mitläuft

Über den beiden reinen Netzkomponenten liegen zwei bundesweit uniforme Abgaben, die auf der Netzrechnung mitlaufen und deshalb im Netz-Rechenweg verrechnet werden (siehe [[steuern/index]] für die vollständige Abgaben-Schicht):

- **EAG-Förderbeitrag** (Erneuerbaren-Ausbau-Gesetz, finanziert den Ökostrom-Ausbau): fällt auf beide verbrauchsabhängigen Komponenten an - auf die Netznutzung (**0,583 ct/kWh**) und auf den Netzverlust (**0,037 ct/kWh**), zusammen **0,620 ct/kWh**. Dazu eine **EAG-Förderpauschale** von **19,02 EUR/Jahr** pro Zählpunkt.
- **Elektrizitätsabgabe** (Stromsteuer des Bundes, ElAbgG): in ct/kWh. Der Regelsatz ist 1,5 ct/kWh; für 2026 ist er für Haushalte temporär auf **0,1 ct/kWh** gesenkt. Diese Senkung ist befristet - läuft sie aus, gilt wieder 1,5 ct/kWh.

Diese Werte sind bundesweit gleich; ortsabhängig sind nur die beiden Netzkomponenten. Die kommunale Gebrauchsabgabe (Landesrecht, pro Gemeinde) gehört zu Block 3 und ist hier nicht enthalten.

## Netzebenen NE 3 bis NE 7

Das Netz ist in sieben Spannungsebenen gegliedert. Je tiefer die Ebene, desto näher am Haushalt und desto höher das Entgelt pro kWh - die Kosten der höheren Ebenen werden nach unten weitergewälzt.

| Netzebene | Spannung | typische Nutzer |
|-----------|----------|-----------------|
| NE 3 | Hochspannung | Großindustrie |
| NE 4 | Umspannung HS auf MS | - |
| NE 5 | Mittelspannung | Industrie, große Gewerbebetriebe |
| NE 6 | Umspannung MS auf NS | PV-Einspeisung von Anlagen, die auf dieser Ebene anschließen |
| **NE 7** | **Niederspannung (400 V)** | **Haushalte, Kleingewerbe** |

Für die Haushalts-Kostenrechnung zählt **NE 7** ("nicht gemessene Leistung"). Strom, der aus einer PV-Anlage ins Netz eingespeist wird, wird typischerweise auf **NE 6** abgerechnet. Größere NE-7-Kunden mit Viertelstundenmessung gelten als "gemessene Leistung" und zahlen zusätzlich einen Leistungspreis (EUR/kW) - das ist nicht das Standard-Haushaltsprofil.

## Die Formel (NE-7-Haushalt, pro Jahr)

```
arbeitspreis_ct = Netznutzung_AP
                + Netzverlust
                + EAG_Foerderbeitrag_Netznutzung   (0,583)
                + EAG_Foerderbeitrag_Netzverlust    (0,037)
                + Elektrizitaetsabgabe_Haushalt     (0,1, 2026)

pauschale_eur   = Netznutzung_Pauschale (54,00) + EAG_Foerderpauschale (19,02)

netto_eur/Jahr  = arbeitspreis_ct * kWh / 100 + pauschale_eur
brutto_eur/Jahr = netto_eur * 1,20
```

Der Arbeitspreis-Term bündelt alle ct/kWh-Posten; die Pauschale-Summe bündelt alle fixen Jahresbeträge. Erst ganz am Ende kommt die Umsatzsteuer als Faktor 1,20 auf den Netto-Betrag. Diese Reihenfolge (netto, dann USt) muss transparent bleiben, damit jede Zahl von Hand nachvollziehbar ist.

## Durchgerechnetes Beispiel - Energienetze Steiermark, 3.500 kWh/Jahr

Werte: Netznutzung-AP 8,82 ct/kWh, Netzverlust 0,336 ct/kWh, EAG-AP 0,583 ct/kWh, EAG-Verlust 0,037 ct/kWh, Elektrizitätsabgabe 0,1 ct/kWh (2026); Pauschalen 54,00 + 19,02 EUR/Jahr; USt 20 %.

Schritt 1 - Arbeitspreis-Summe (alle ct/kWh-Posten):
```
8,82 + 0,336 + 0,583 + 0,037 + 0,1 = 9,876 ct/kWh
```

Schritt 2 - verbrauchsabhängiger Teil (× 3.500 kWh):
```
9,876 * 3.500 / 100 = 345,66 EUR
```

Schritt 3 - Pauschalen (fixe Jahresbeträge):
```
54,00 + 19,02 = 73,02 EUR
```

Schritt 4 - Netto pro Jahr:
```
345,66 + 73,02 = 418,68 EUR
```

Schritt 5 - Brutto (× 1,20):
```
418,68 * 1,20 = 502,42 EUR
```

Ein steirischer Haushalt mit 3.500 kWh zahlt also rund **502,42 EUR/Jahr** allein für Netz plus bundesweite Abgaben (USt inkl.) - bevor der Energiepreis des Lieferanten und eine allfällige Gebrauchsabgabe dazukommen. Ein Haushalt in Kapfenberg zahlt denselben Betrag (gleicher Netzbereich Steiermark); einer in Vorarlberg (AP 4,96) deutlich weniger, einer in Kleinwalsertal (AP 17,73) ein Vielfaches.

> Hinweis: Die konkreten Tarifzahlen sind nicht Teil dieser Seite. Sie stehen in den datierten, gequellten Snapshots unter `energietools/data/netz/` (z. B. `netzkosten.json` je Netzbereich, `abgaben.json` für die bundesweiten Anteile). Diese Seite erklärt die Bedeutung; die Rechen-Capabilities ziehen die aktuellen Werte aus den Snapshots.

## Speicher-Befreiung (§ 16b / § 17 ElWOG)

Strom, der in einen Speicher geladen und später wieder entnommen wird, würde ohne Sonderregel doppelt mit Netzentgelt belastet (einmal beim Laden, einmal bei der Lieferung an den Letztverbraucher). Das ElWOG sieht deshalb vor, dass die **Ladeenergie eines Speichers von Teilen des Netzentgelts befreit** sein kann (§ 16b, § 17). In der Wirtschaftlichkeitsrechnung eines Speichers oder einer Power-to-X-Anlage senkt das die effektiven Netzkosten der eingespeicherten kWh. Die Capability `grid_fees` bildet diese Befreiung über das Flag `storage_exemption` ab.

## Siehe auch

- [[netz/index]] - Übersicht der Netz-Schicht (Netzbereiche, PLZ-Auflösung, Verfügbarkeit)
- [[wirtschaftlichkeit/gesamtkosten]] - wie Netzentgelt + Energiepreis + USt zur echten Brutto-Jahresrechnung werden
- [[steuern/index]] - die Abgaben-Schicht (EAG-Förderbeitrag, Elektrizitätsabgabe, Gebrauchsabgabe) im Detail
- [[glossar]] - Begriffe (Netzebene, AP/SNAP/DT, Entnehmer/Einspeiser, Zählpunkt, VNB)

## Berechnet von

- **`grid_fees`** - Netzentgelt je Betreiber/Land, per kWh und pro Jahr, mit § 16b/§ 17-Speicher-Befreiung. Eingaben: `verbrauch_kwh` (Pflicht), `operator`, `country` (Default "AT"), `storage_exemption`.
  ```
  python -m energietools grid_fees --json '{"verbrauch_kwh": 3500, "operator": "Energienetze Steiermark"}'
  ```
- **`netzkosten`** - regulierte Brutto-Jahres-Netzkosten (NE-7-Haushalt) je PLZ, mit lückenlosem Rechenweg. Eingaben: `plz` und `verbrauch_kwh` (beide Pflicht). Fail-open: unbekannte PLZ -> `netzbetreiber: null`, Kosten 0 (keine erfundenen Werte).
  ```
  python -m energietools netzkosten --json '{"plz": "8010", "verbrauch_kwh": 3500}'
  ```

## Quellen

- **Systemnutzungsentgelte-Verordnung**, BGBl. II Nr. 305/2025 (E-Control, in Kraft 01.01.2026) - autoritative Tarifliste je Netzbereich: NE-7-Arbeitspreis § 5, Netzverlust § 6. RIS: https://www.ris.bka.gv.at/eli/bgbl/II/2025/305
- **Netzbetreiber-Preisblatt Netznutzung Strom 2026** des jeweiligen VNB (z. B. Energienetze Steiermark) - First-Party-Bestätigung der Werte.
- **ElAbgG** (Elektrizitätsabgabegesetz) - Elektrizitätsabgabe inkl. der befristeten 2026-Senkung.
- **EAG** (Erneuerbaren-Ausbau-Gesetz) / ÖMAG - EAG-Förderbeitrag (ct/kWh) und EAG-Förderpauschale (EUR/Jahr).
- **§ 16b / § 17 ElWOG** - Netzentgelt-Befreiung der Speicher-Ladeenergie.
- **Datenquelle:** `energietools/data/netz/` (datierte, gequellte Snapshots: `netzkosten.json`, `abgaben.json`, `plz_netzbereich.json` + MANIFEST). Das Wiki referenziert diese Snapshots, es enthält sie nicht.
- **Provenance / Vertrauens-Anker:** Erhebung und Validierung der Werte siehe `METHODIK.md` (§ 3 Netzkosten); Erklärung der Preis-Zusammensetzung siehe `NETZKOSTEN_UND_GEBUEHREN.md`.

Stand: 2026-06
