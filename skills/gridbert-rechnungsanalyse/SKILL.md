---
name: gridbert-rechnungsanalyse
description: Aus einer im Chat hochgeladenen Stromrechnung die Ist-Kosten verstehen und beziffern, ob ein Tarifwechsel lohnt.
---

# Rechnungsanalyse

**Version:** 1.0.0 · **Stand:** 2026-07-11 · **Markt:** AT · **Lizenz:** MIT

## Ziel

Aus einer im Chat hochgeladenen Stromrechnung die Ist-Kosten verstehen und beziffern, ob ein Tarifwechsel lohnt. Erfolg: validierte Rechnungsfakten mit Rechenweg (jahreskosten_brutto_eur) und — sofern gewünscht — ein Tarifvergleich mit auditierbarem Rechenweg je Alternative.

## Benötigte Daten

- **energieart** (Quelle: rechnung, Pflicht)
- **lieferant** (Quelle: rechnung, Pflicht)
- **zeitraum_von** (Quelle: rechnung, Pflicht)
- **zeitraum_bis** (Quelle: rechnung, Pflicht)
- **verbrauch_kwh** (Quelle: rechnung, Pflicht)
- **plz** (Quelle: rechnung|frage, Pflicht)
- **quellen_anker** (Quelle: rechnung, Pflicht) — wörtliches Zitat je Pflichtfeld (D2.2 Quellen-Anker) — nie ohne Zitat übernehmen
- **arbeitspreis** (Quelle: rechnung, Optional) — ct/kWh + ist_netto (D2.2 PreisCtKwh) — Faktor-100-Fehler vermeiden
- **grundgebuehr** (Quelle: rechnung, Optional) — EUR + zeitraum (monat|jahr) + ist_netto (D2.2 Grundgebuehr)
- **jahresverbrauch_kwh** (Quelle: rechnung, Pflicht) — für tariff_compare; entspricht verbrauch_kwh bzw. der Hochrechnung aus finalize_invoice
- **aktueller_lieferant** (Quelle: rechnung, Pflicht) — für tariff_compare; entspricht lieferant
- **aktueller_energiepreis_brutto_ct_kwh** (Quelle: rechnung, Pflicht) — ct/kWh brutto, für tariff_compare — aus dem finalize_invoice-Rechenweg (effektiver Arbeitspreis) ableiten, nicht 1:1 von der Rechnung übernehmen
- **aktuelle_grundgebuehr_brutto_eur_monat** (Quelle: rechnung, Pflicht) — EUR/Monat brutto, für tariff_compare
- **nb_key** (Quelle: rechnung|instanz, Optional) — VNB-Schlüssel, falls aus der Rechnung ablesbar — erzwingt nb_key in tariff_compare statt PLZ-Auflösung

## Fragen

### f1_zieltarif (Hebel: tarif)
- Frage: Ist dir Planbarkeit (Fixpreis) wichtiger, oder die Chance auf einen günstigeren Schnitt (Spot/Floater)?
- Ableitung: Unscharfe Antworten in eine Tarifpräferenz überführen (Playbook-Regel); ohne Antwort default: Fixtarif-Vergleich.

### f2_rabatt (Hebel: tarif)
- Frage: Ich sehe auf deiner Rechnung einen Neukundenrabatt/Gratistage — der gilt meist nur im ersten Jahr. Soll ich zum Vergleich den rabattierten Preis oder den Listenpreis ansetzen?
- Nur wenn: Rechnung enthält einen Neukundenrabatt oder Gratistage
- Ableitung: Year-1-Bias vermeiden: einmalige Rabatte NICHT in die laufenden Kosten einrechnen — Listenpreis ansetzen (Playbook Abschnitt 1).

## Tool-Mapping

### rechnung_erfassen — `validate_invoice_facts` (energietools, aktiv)
- Pflicht-Inputs: energieart, lieferant, zeitraum_von, zeitraum_bis, verbrauch_kwh, plz, quellen_anker
- Werte wörtlich von der Rechnung übernehmen, nie umrechnen — ist_netto-Flag explizit setzen (keine Default-Annahme, D2.2).
- Bei Ablehnung: strukturierte Rückfrage aus dem Result stellen, nicht eigenmächtig heilen oder auf 0 koerzieren.

### rechnung_abschliessen — `finalize_invoice` (energietools, aktiv)
- Pflicht-Inputs: energieart, lieferant, zeitraum_von, zeitraum_bis, verbrauch_kwh, plz, quellen_anker
- jahreskosten_brutto_eur ist die Hauptmetrik der Antwort; Rechenweg und warnings referenzieren, nicht verschweigen.

### vergleich — `tariff_compare` (energietools, aktiv)
- Pflicht-Inputs: plz, jahresverbrauch_kwh, aktueller_lieferant, aktueller_energiepreis_brutto_ct_kwh, aktuelle_grundgebuehr_brutto_eur_monat
- versorger_abdeckung ist Pflichtfilter + Pflicht-Output-Block (im tariff_compare-Result bereits enthalten) — kein Landesversorger außerhalb seines Bundeslandes als Bestpreis.
- VNB aus der Rechnung erzwingt nb_key, wenn bekannt (statt PLZ-Auflösung).
- Ranking nach Jahr-2-Kosten (Listenpreis), nicht Jahr-1 — Rabatt-Bias vermeiden (siehe f2_rabatt).

## Datenqualität & Abbruch

- Rabatt/Gratistage sind einmalig -> Listenpreis ansetzen (Year-1-Bias vermeiden), nicht den rabattierten Preis.
- 0 verfügbare Alternativen im Katalog -> Abbruch mit Meldung, keine Empfehlung (kein erfundener Vergleich).
- validate_invoice_facts/finalize_invoice lehnt ab (Rejection) -> nichts wurde gespeichert; strukturierte Rückfrage laut Result stellen, nicht eigenmächtig heilen.

## Caveats (MÜSSEN in die Antwort)

- **Trigger `immer`:** Alle verglichenen Tarife sind Netto-Listenpreise (ohne befristete Rabatte), tagesaktueller Katalogstand laut tariff_compare-Result.
- **Trigger `abdeckung.im_katalog_fehlend > 0`:** Für deine Region gibt es Anbieter, die (noch) nicht im Katalog stehen — der Vergleich ist insofern unvollständig.
- **Trigger `invoice.rejected == true`:** Die Rechnungsangaben konnten nicht validiert werden — bitte die genannten Felder korrigieren, bevor ein Vergleich möglich ist.

