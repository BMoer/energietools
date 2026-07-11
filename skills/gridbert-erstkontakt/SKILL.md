---
name: gridbert-erstkontakt
description: Orientierung beim ersten Kontakt nach dem Connect ("was kann Gridbert?"): was Gridbert kann, was es zum Haushalt schon weiß, und was der beste nächste Schritt ist.
---

# Erstkontakt

**Version:** 1.0.0 · **Stand:** 2026-07-11 · **Markt:** AT · **Lizenz:** MIT

## Ziel

Orientierung beim ersten Kontakt nach dem Connect ("was kann Gridbert?"): was Gridbert kann, was es zum Haushalt schon weiß, und was der beste nächste Schritt ist. Erfolg: der User kennt die drei Tool-Familien (Vault/Wissen, Rechnen, Rechnungs-Einstieg) und hat einen konkreten Einstieg — in der Regel die Empfehlung, die Stromrechnung hochzuladen.

## Benötigte Daten

Keine — dieser Prozess stellt bewusst keine Pflichtdaten voraus.

## Fragen

Keine — dieser Prozess stellt keine strukturierten Rückfragen.

## Tool-Mapping

### instanz_uebersicht — `search_pages` (extern, aktiv)
- Erst prüfen, was zum Haushalt schon in der Instanz liegt, bevor nach bereits bekannten Daten gefragt wird (kein Verhör).

### instanz_detail — `get_page` (extern, aktiv)
- Bei einem Treffer aus instanz_uebersicht die konkrete Seite laden, damit die Antwort auf echten Fakten aufbaut, nicht auf Vermutung.

### wissen_auf_nachfrage — `get_knowledge` (energietools, aktiv)
- Pflicht-Inputs: thema
- Nur auf konkrete Nachfrage aufrufen (z. B. 'wie setzen sich Stromkosten in Österreich zusammen'), nicht ungefragt in jede Antwort drücken (Kontext-Ballast vermeiden, D7 Wissens-Auslieferung).
- thema wird vom User-LLM aus der Nutzerfrage abgeleitet (siehe get_knowledge.input_schema.thema.enum) — deshalb kein Eintrag in benoetigte_daten, die bewusst leer bleiben.

### rechnung_einstieg — `submit_invoice_facts` (extern, aktiv)
- Standard-Einstiegsempfehlung: die Stromrechnung im Chat hochladen lassen und in den rechnungsanalyse-Prozess übergeben (Amendment 9 Kern-Use-Case).
- Folgeprozess: rechnungsanalyse.yaml übernimmt ab hier (Fragen, Tool-Mapping, Caveats).

### ausblick_tarifwechsel — `tariff_compare` (energietools, ausblick)
- Erst relevant, sobald Rechnungsdaten vorliegen (rechnungsanalyse-Prozess) — hier nur als Ausblick nennen, nicht aufrufen.

### ausblick_wechselinfo — `get_switch_info` (extern, ausblick)
- Reine Information zu Anbieterwechsel-Schritten/Fristen — keine Wechsel-Durchführung (Beschluss 16). Nur als Ausblick nennen.

## Datenqualität & Abbruch

Keine besonderen Abbruchregeln über die Tool-eigene Validierung hinaus.

## Caveats (MÜSSEN in die Antwort)

- **Trigger `immer`:** Die Stromrechnung im Chat hochladen ist der beste nächste Schritt — erst damit kann Gridbert konkrete Zahlen liefern.
- **Trigger `immer`:** Ehrliche Grenze: Gridbert kann (noch) keine Lastgang-/Smart-Meter-Analysen (folgt in einer späteren Ausbaustufe) und führt keinen Anbieterwechsel durch — das entscheidet und erledigt der Haushalt selbst.
- **Trigger `anfrage.ausserhalb_katalog == true`:** Diese Anfrage liegt außerhalb dessen, was Gridbert heute kann — bitte capability_gap aufrufen und dem User ehrlich sagen, dass es das (noch) nicht gibt, statt zu raten.

