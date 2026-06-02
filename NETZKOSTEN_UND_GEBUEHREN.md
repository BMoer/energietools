# Netzkosten & Abgaben in Österreich — wie sich der Strompreis zusammensetzt

> **Zweck dieses Dokuments.** Eine vollständige, belegte Erklärung, woraus sich der
> Strompreis eines österreichischen Haushalts zusammensetzt — mit Fokus auf die
> **Netzkosten** und **Abgaben**, ihre regulatorische Grundlage (SNE-V) und ihr
> Zusammenspiel mit dem (wettbewerblichen) Energiepreis. Geschrieben als
> Referenz/Wissensbasis (LLM-Wiki-tauglich): self-contained, mit Quellen, Stand
> **2026** (SNE-V 2018 – Novelle 2026).
>
> Kurzfassung in einem Satz: **Energiepreis wechselst du, Netzkosten zahlst du je
> nach Wohnort, Abgaben legt der Staat fest — und obendrauf 20 % USt.**

---

## 1. Die vier Bausteine einer Stromrechnung

Eine österreichische Haushalts-Stromrechnung besteht aus vier klar trennbaren
Blöcken. Nur **einer** davon ist wettbewerblich.

| Block | Was | Wer setzt ihn fest | Beeinflussbar? |
|------|-----|--------------------|----------------|
| **1. Energiepreis** | Strom-Beschaffung (Arbeitspreis ct/kWh + Grundgebühr) | **Lieferant** (Markt) | **Ja** — Anbieterwechsel |
| **2. Netzkosten** | Nutzung & Verluste des Stromnetzes | **E-Control** (SNE-V), je Netzbereich | Nein — hängt am Wohnort |
| **3. Steuern & Abgaben** | EAG-Förderung, Elektrizitätsabgabe, Gebrauchsabgabe | Bund + Land/Gemeinde | Nein |
| **4. Umsatzsteuer** | 20 % auf die Summe (netto → brutto) | Bund | Nein |

**Faustregel der Anteile** (Haushalt, je nach Netzbereich/Verbrauch): Energie ~40–50 %,
Netzkosten ~25–35 %, Steuern & Abgaben ~20–30 %. Der Anbieterwechsel wirkt **nur auf
Block 1**; Block 2–4 sind für eine gegebene Adresse fix. Genau deshalb trennt eine
saubere Vergleichslogik Energie- von Netzkosten: Ersparnis entsteht in Block 1, Block 2
ist ein **ortsabhängiger Sockel**.

---

## 2. Block 2 — Netzkosten (reguliert)

Die Netzkosten sind das Entgelt dafür, dass der Strom über das Netz zu dir kommt. Sie
sind **reguliert** (kein Wettbewerb) und werden von der **Regulierungskommission der
E-Control** in der **Systemnutzungsentgelte-Verordnung (SNE-V)** festgelegt — pro
**Netzbereich** und pro **Netzebene**.

### 2.1 Netzebenen (NE 1–7)

Das Netz ist in sieben Spannungsebenen gegliedert; je tiefer die Ebene, desto näher am
Haushalt und desto höher das Entgelt pro kWh (die Kosten der höheren Ebenen werden nach
unten weitergewälzt).

| Netzebene | Spannung | typische Nutzer |
|-----------|----------|-----------------|
| NE 1 | Höchstspannung (Übertragungsnetz) | Großindustrie, Netzkopplung |
| NE 3 | Hochspannung | Großindustrie |
| NE 4 | Umspannung HS→MS | — |
| NE 5 | Mittelspannung | Industrie, große Gewerbebetriebe |
| NE 6 | Umspannung MS→NS | — |
| **NE 7** | **Niederspannung (400 V)** | **Haushalte, Kleingewerbe** |

**Haushalte hängen an NE 7**, und zwar als **„nicht gemessene Leistung"** (ohne
Lastprofilmessung). Das ist die für Gridbert relevante Zeile. (Größere NE-7-Kunden mit
Viertelstundenmessung sind „gemessene Leistung" und zahlen zusätzlich einen
Leistungspreis €/kW.)

### 2.2 Die zwei Netzkosten-Komponenten

Für einen NE-7-Haushalt bestehen die reinen Netzkosten aus genau zwei regulierten
Posten (beide **netzbereichsspezifisch**):

1. **Netznutzungsentgelt** (SNE-V § 5) — die Nutzung des Netzes:
   - **Arbeitspreis (AP)** in **ct/kWh** — verbrauchsabhängig.
   - **Grundpreis / Pauschale** in **€/Jahr pro Zählpunkt** — fix. Für NE 7 „nicht
     gemessene Leistung" ist die Pauschale unter Novelle 2026 **bundesweit einheitlich
     54,00 €/Jahr** (früher je VNB unterschiedlich, z. B. 24/43,80/48/49,20).
2. **Netzverlustentgelt** (SNE-V § 6) — deckt die physikalischen Leitungsverluste,
   in **ct/kWh**, ebenfalls je Netzbereich.

> **Tarif-Varianten beim Arbeitspreis** (wichtig, um die richtige Zahl zu erwischen):
> - **AP** = Arbeitspreis rund um die Uhr (Standard-Einfachtarif). **Das ist der
>   Haushaltswert.**
> - **SNAP** = Sommer-Nieder-Arbeitspreis (nur für ¼-h-gemessene NE 7 ohne
>   Energiegemeinschaft, Apr–Sep 10–16 Uhr). **Nicht** der Standard-Haushalt.
> - **DTAP / DNAP** = Doppeltarif Tag/Nacht.
>
> **Verluste — Entnehmer vs. Einspeiser:** Das Netzverlustentgelt hat einen Wert für
> **Entnehmer** (Verbraucher, je Netzbereich) und einen **bundesweit uniformen** Wert
> für **Einspeiser** (**0,279 ct/kWh**). Für die Haushaltskosten zählt der
> **Entnehmer**-Wert — der 0,279-Einspeiserwert ist eine klassische Verwechslungsfalle.

### 2.3 Die SNE-V und die 14 Netzbereiche

Die **SNE-V 2018** wird jährlich novelliert. Maßgeblich für 2026 ist die **Novelle 2026
(BGBl. II Nr. 305/2025)**, in Kraft ab 01.01.2026. Sie ersetzt (§ 5 Abs. 1 Z 6 „lautet:")
die komplette NE-7-Tarifliste und definiert **genau 14 Netzbereiche** mit je eigenem
NE-7-Tarif:

- **9 Bundesländer:** Burgenland, Kärnten, Niederösterreich, Oberösterreich, Salzburg,
  Steiermark, Tirol, Vorarlberg, Wien.
- **4 Stadt-Netzbereiche:** Linz, Graz, Innsbruck, Klagenfurt (eigene Tarife, oft
  deutlich günstiger als das umgebende Land — z. B. Graz 5,17 vs. Steiermark 8,82).
- **1 Sonderfall:** Kleinwalsertal (Gemeinde Mittelberg) — geografisch ans deutsche Netz
  angebunden, mit dem **höchsten** NE-7-Arbeitspreis Österreichs.

**NE-7-Arbeitspreise je Netzbereich (Novelle 2026, „nicht gemessene Leistung", ct/kWh):**

| Netzbereich | AP | Netzverlust | Pauschale €/J |
|---|---|---|---|
| Vorarlberg | 4,96 | 0,393 | 54,00 |
| Graz | 5,17 | 0,658 | 54,00 |
| Linz | 5,57 | 0,487 | 54,00 |
| Oberösterreich | 6,29 | 0,528 | 54,00 |
| Salzburg | 6,59 | 0,357 | 54,00 |
| Tirol | 6,81 | 0,293 | 54,00 |
| Klagenfurt | 6,90 | 0,578 | 54,00 |
| Wien | 6,98 | 0,700 | 54,00 |
| Innsbruck | 8,03 | 0,453 | 54,00 |
| Burgenland | 8,46 | 0,000 | 54,00 |
| Niederösterreich | 8,79 | 0,384 | 54,00 |
| Steiermark | 8,82 | 0,336 | 54,00 |
| Kärnten | 9,67 | 0,368 | 54,00 |
| Kleinwalsertal | 17,73 | 0,401 | 54,00 |

> **Geografische Spreizung:** Der NE-7-Arbeitspreis variiert vom günstigsten
> (Vorarlberg 4,96) zum teuersten Land (Kärnten 9,67) um fast Faktor 2 — und in
> Kleinwalsertal (17,73) um **Faktor 3,6**. Wo du wohnst, entscheidet über die
> Netzkosten; wechseln kannst du sie nicht.

### 2.4 Wichtiger Befund: kleine Stadtwerke haben *keine* eigenen Tarife mehr

Österreich hat **~119 Verteilnetzbetreiber (VNB)** als juristische Einheiten — aber unter
Novelle 2026 nur **14 NE-7-Tarife**. Die ~105 kleinen Stadtwerke/EVU (Kapfenberg,
Kufstein, Feldkirch, Bruck/Mur, Mürzzuschlag, …) **billen den Tarif ihres Netzbereichs**,
keinen eigenen.

Empirisch bestätigt an drei Preisblättern 2026:

| Stadtwerk | eigenes Preisblatt 2026 (AP/Verlust/Pauschale) | = Netzbereich |
|---|---|---|
| Stadtwerke Kufstein | 6,81 / 0,293 / 54 | = Tirol |
| Stadtwerke Kapfenberg | 8,82 / 0,336 / 54 | = Steiermark |
| Stadtwerke Feldkirch | 4,96 / 0,393 / 54 | = Vorarlberg |

Historisch (bis Novelle **2025**) hatten einzelne Stadtwerke **eigene**, oft höhere
Tarife — z. B. Kapfenberg 9,13 / 0,444 / 48. Die **Novelle 2026 hat diese konsolidiert**.
Die **§ 13-Tabellen** der SNE-V (Zahler/Empfänger) sind **Ausgleichszahlungen zwischen
Betreibern desselben Netzbereichs** — sie gleichen unterschiedliche Kostenstrukturen aus,
damit am Ende **alle Kunden eines Netzbereichs denselben Tarif** zahlen. Sie sind **kein**
Kundentarif.

**Praktische Folge:** Für die Kostenrechnung genügen die 14 Netzbereiche. Der konkrete
Betreibername (z. B. „Stadtwerke Kapfenberg") ist nur eine **Attribution** — derselbe
Tarif, anderer Name.

---

## 3. Block 3 — Steuern & Abgaben

Über den reinen Netzkosten liegen zwei Schichten: **bundesweit uniforme** Abgaben
(gesetzlich/verordnet) und die **Gebrauchsabgabe** (Landesrecht, pro Gemeinde).

### 3.1 Bundesweit uniforme Abgaben (überall gleich)

| Abgabe | Wert 2026 | Bezug | Grundlage |
|--------|-----------|-------|-----------|
| **EAG-Förderbeitrag** (Netznutzungs-Anteil) | **0,583 ct/kWh** | × kWh | EAG / ÖMAG |
| **EAG-Förderbeitrag** (Netzverlust-Anteil) | **0,037 ct/kWh** | × kWh | EAG / ÖMAG |
| **EAG-Förderpauschale** | **19,02 €/Jahr** | je Zählpunkt | EAG / ÖMAG |
| **Elektrizitätsabgabe (Haushalt)** | **0,10 ct/kWh** | × kWh | ElAbgG (2026-Senkung) |

- **EAG-Förderbeitrag** (Erneuerbaren-Ausbau-Gesetz): finanziert den Ökostrom-Ausbau.
  Er fällt auf **beide** verbrauchsabhängigen Komponenten an — auf die Netznutzung
  (0,583) und auf den Netzverlust (0,037) — in Summe **0,620 ct/kWh**. Auf
  VNB-Preisblättern oft als eine Zeile „EAG Förderbeitrag 0,620 ct/kWh" ausgewiesen.
- **EAG-Förderpauschale:** fixer Jahresbetrag pro Zählpunkt (19,02 €/Jahr).
- **Elektrizitätsabgabe** (ElAbgG): **Regelsatz 1,5 ct/kWh**. Für 2026 **temporär
  gesenkt** (Energiekrisen-Entlastung): **Haushalte 0,10 ct/kWh**, **Unternehmen
  0,82 ct/kWh**. ⚠️ Diese Senkung ist **befristet** — läuft sie aus, gilt wieder
  1,5 ct/kWh (kein stiller Default auf den niedrigen Wert annehmen).

> Diese Werte werden jährlich per Verordnung neu festgesetzt; die hier genannten gelten
> für 2026.

### 3.2 Gebrauchsabgabe (Landesrecht, pro Gemeinde)

Die **Gebrauchsabgabe** ist eine kommunale Abgabe für die Nutzung des öffentlichen Guts
(Leitungen im Gemeindegebiet). **Satz und Bemessungsbasis variieren je Gemeinde/Land:**

| Gemeinde / Land | Satz | Status |
|-----------------|------|--------|
| **Wien** | **7 %** (ab 01.03.2026, vorher 6 %) | verifiziert |
| Burgenland (Land) | **0 %** (keine Abgabe) | verifiziert |
| Vorarlberg (Land) | **0 %** (keine Abgabe) | verifiziert |
| Graz / Linz / Klagenfurt / Salzburg / Innsbruck | offen | TODO |
| übrige Gemeinden | i. d. R. 0 % | TODO |

> **Vorsicht bei der Basis.** Quellen definieren die Bemessungsgrundlage unterschiedlich
> („% des Netz-Netto" vs. „% der Energiekosten"); Caps variieren (Salzburg max 6 %,
> Tirol/OÖ max 3 % vom Bruttoumsatz). Solange Satz **und** Basis nicht je Gemeinde belegt
> sind, ist die Gebrauchsabgabe **kein** belastbarer, user-sichtbarer Posten — lieber 0
> ansetzen als eine erfundene Quote.

---

## 4. Block 4 — Umsatzsteuer

Auf die **Summe** aus Energie + Netzkosten + Abgaben kommen **20 % USt**. In der
Netzkosten-Rechnung gilt: **brutto = netto × 1,20**.

---

## 5. Die Gesamtformel (NE-7-Haushalt, pro Jahr)

Die **Netzkosten inkl. bundesweiter Abgaben** (ohne Energiepreis, ohne Gebrauchsabgabe):

```
arbeitspreis_ct = Netznutzung_AP
                + Netzverlust
                + EAG_Förderbeitrag_Netznutzung   (0,583)
                + EAG_Förderbeitrag_Netzverlust    (0,037)
                + Elektrizitätsabgabe_Haushalt     (0,10, 2026)

pauschale_eur   = Netznutzung_Pauschale (54,00) + EAG_Förderpauschale (19,02)

netto_eur/Jahr  = arbeitspreis_ct × kWh / 100 + pauschale_eur
brutto_eur/Jahr = netto_eur × 1,20
```

Der **gesamte** Jahresbetrag der Rechnung ergibt sich dann als:

```
Gesamt = Netzkosten_brutto + Energiepreis_brutto(Lieferant) + Gebrauchsabgabe(Gemeinde)
```

### Rechenbeispiel — Netzbereich Steiermark, 3.500 kWh

```
arbeitspreis_ct = 8,82 + 0,336 + 0,583 + 0,037 + 0,10 = 9,876 ct/kWh
verbrauchsteil  = 9,876 × 3.500 / 100                 = 345,66 €
pauschale       = 54,00 + 19,02                        =  73,02 €
netto/Jahr      = 345,66 + 73,02                       = 418,68 €
brutto/Jahr     = 418,68 × 1,20                         = 502,42 €
```

→ Ein steirischer Haushalt mit 3.500 kWh zahlt **502,42 €/Jahr** allein für Netz +
bundesweite Abgaben (USt inkl.) — **bevor** der Energiepreis des Lieferanten und eine
allfällige Gebrauchsabgabe dazukommen. Ein Haushalt in Kapfenberg zahlt **denselben**
Betrag (gleicher Netzbereich); einer in Vorarlberg (AP 4,96) deutlich weniger, einer in
Kleinwalsertal (AP 17,73) ein Vielfaches.

---

## 6. Zusammenspiel mit den Gesamtkosten — warum die Trennung zählt

- **Netzkosten sind ein ortsgebundener Sockel.** Sie hängen ausschließlich am
  Netzbereich (= an der PLZ/Gemeinde), nicht am Lieferanten. Zwei Nachbarn mit
  unterschiedlichen Stromanbietern zahlen **dieselben** Netzkosten.
- **Der Anbieterwechsel betrifft nur Block 1 (Energie).** Ein Tarifvergleich, der
  Netzkosten in den „Preis" mischt, vergleicht Äpfel mit Birnen: Die Netzkosten sind für
  alle Angebote an einer Adresse identisch. Korrekt ist: Energiepreise vergleichen,
  Netzkosten als konstanten Kontext daneben ausweisen.
- **Abgaben sind größtenteils uniform** (Bund) — bis auf die kommunale Gebrauchsabgabe.
- **Der Rechenweg muss transparent bleiben** (netto → Abgaben → USt → brutto), damit
  jede Zahl von Hand oder durch einen Prüfer nachvollziehbar ist.

**Mentales Modell:**

```
Stromrechnung (Haushalt, brutto)
├── Energie   ── Lieferant, Markt        ──► wechselbar (Block 1)
├── Netz      ── E-Control / SNE-V       ──► fix je Netzbereich (Block 2)
│   ├── Netznutzung (AP ct/kWh + 54 €/J)
│   └── Netzverlust (ct/kWh)
├── Abgaben   ── Bund + Gemeinde         ──► fix (Block 3)
│   ├── EAG-Förderbeitrag (0,620 ct/kWh) + Förderpauschale (19,02 €/J)
│   ├── Elektrizitätsabgabe (0,10 ct/kWh, 2026)
│   └── Gebrauchsabgabe (Gemeinde, z. B. Wien 7 %)
└── USt 20 %  ── Bund                    ──► × 1,20
```

---

## 7. Häufige Stolpersteine (Lessons learned)

1. **AP, nicht SNAP/DT.** Für den Standard-Haushalt zählt der Arbeitspreis rund um die
   Uhr — nicht der Sommer-Nieder- (SNAP) oder Doppeltarif-Wert.
2. **Entnehmer-Verlust, nicht Einspeiser.** 0,279 ct/kWh ist der bundesweite
   **Einspeiser**-Verlust — nicht der Haushaltswert.
3. **„nicht gemessene Leistung"** ist die Haushaltszeile; „gemessene Leistung" hat einen
   zusätzlichen Leistungspreis (€/kW) für größere Abnehmer.
4. **Pauschale 54 €/Jahr** ist unter Novelle 2026 bundesweit einheitlich — ältere
   abweichende Werte (24/43,80/48/49,20) sind überholt.
5. **Kleine VNB = Netzbereich-Tarif** (kein eigener Tarif unter Novelle 2026). Der
   reale Betreibername ist Attribution, nicht ein anderer Preis.
6. **Elektrizitätsabgabe 0,10 ct/kWh ist befristet** (2026). Regelsatz 1,5 ct/kWh.
7. **Gebrauchsabgabe nur ansetzen, wenn Satz UND Basis belegt sind.**
8. **Keine E-Control-Rechner-API als Quelle.** Primärquelle sind die VNB-Preisblätter,
   cross-gecheckt gegen die SNE-V. Ein Rechner darf höchstens prüfen, nie liefern.

---

## 8. Glossar

- **SNE-V** — Systemnutzungsentgelte-Verordnung (E-Control); legt die Netzkosten fest.
- **Netzbereich** — regulatorische Tarifzone; 14 davon unter Novelle 2026.
- **Netzebene (NE 1–7)** — Spannungsebene; Haushalt = NE 7 (Niederspannung).
- **VNB** — Verteilnetzbetreiber (Strom). ~119 in Österreich.
- **Netznutzungsentgelt** — Entgelt für die Netznutzung (AP ct/kWh + Pauschale €/J).
- **Netzverlustentgelt** — Entgelt für physikalische Leitungsverluste (ct/kWh).
- **AP / SNAP / DTAP / DNAP** — Arbeitspreis / Sommer-Nieder- / Doppeltarif-Tag- /
  Doppeltarif-Nacht-Arbeitspreis.
- **Entnehmer / Einspeiser** — Verbraucher / Erzeuger (Einspeisung ins Netz).
- **EAG** — Erneuerbaren-Ausbau-Gesetz; Förderbeitrag (ct/kWh) + Förderpauschale (€/J).
- **Elektrizitätsabgabe** — Stromsteuer des Bundes (ElAbgG).
- **Gebrauchsabgabe** — kommunale Abgabe (Landesrecht), pro Gemeinde verschieden.
- **Zählpunkt** — eindeutige Kennung der Verbrauchsstelle (Pauschalen je Zählpunkt).
- **§ 13-Ausgleichszahlungen** — Zahlungen zwischen VNB desselben Netzbereichs; kein
  Kundentarif.

---

## 9. Quellen

- **SNE-V 2018 – Novelle 2026**, BGBl. II Nr. 305/2025 (Verordnung der
  Regulierungskommission der E-Control), in Kraft 01.01.2026 — autoritative Tarifliste
  aller 14 Netzbereiche (NE-7-Arbeitspreis § 5, Netzverlust § 6, Ausgleich § 13).
- **VNB-Preisblätter Netznutzung Strom 2026** (first-party Bestätigung), u. a.:
  Stadtwerke Kapfenberg, Stadtwerke Kufstein, Stadtwerke Feldkirch, Energieversorgung
  Kleinwalsertal (EVK).
- **EAG** (Erneuerbaren-Ausbau-Gesetz) / ÖMAG — Förderbeitrag & Förderpauschale 2026.
- **ElAbgG** (Elektrizitätsabgabegesetz) — Elektrizitätsabgabe inkl. 2026-Senkung.
- Methodik der Datenerhebung & -prüfung: siehe [`METHODIK.md`](METHODIK.md) (§ 3 Netzkosten).

*Stand: 2026-06-02. Werte gelten für das Tarifjahr 2026 und werden mit jeder
SNE-V-Novelle bzw. Abgaben-Verordnung neu festgesetzt.*
