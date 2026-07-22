---
name: gridbert-lastganganalyse
description: Aus einem Lastgang (15-min-Netzbezug/-Verbrauch, per EDA-Consent) verstehen, was den Verbrauch treibt, und beziffern, welcher Hebel — in der Reihenfolge Tarif vor Verhalten vor Speicher — was bringt.
---

# Lastgang-Analyse

**Version:** 1.1.0 · **Stand:** 2026-07-22 · **Markt:** AT · **Lizenz:** MIT

## Ziel

Aus einem Lastgang (15-min-Netzbezug/-Verbrauch, per EDA-Consent) verstehen, was den Verbrauch treibt, und beziffern, welcher Hebel — in der Reihenfolge Tarif vor Verhalten vor Speicher — was bringt. Erfolg: eine Empfehlung mit auditierbarem Rechenweg (No-LLM-Math) und die beantworteten Rückfragen als persistierte Profil-Fakten.

## Benötigte Daten

- **serie_ref** (Quelle: eda_consent, Pflicht) — Referenz auf die Q15-/Tages-Serie im gridbert-Box-Postgres (WP2-E) — die Rohserie selbst läuft NIE durchs User-LLM (Amendment 4); der Gateway löst serie_ref account-gebunden auf und füttert 'consumption' in die energietools-Capabilities.
- **zp** (Quelle: rechnung, Pflicht) — Zählpunkt aus den Invoice-Fakten der Instanz (kein Abtippen) — schaltet den EDA-Consent (request_data_release) frei.
- **plz** (Quelle: rechnung|frage, Pflicht) — 4-stellig — für exakte Netzkosten/Tarifvergleich in spot_backtest.tarif_ersparnis; ohne PLZ sind €-Zahlen Heuristik.
- **energiepreis_brutto_ct_kwh** (Quelle: rechnung|frage, Optional) — ct/kWh brutto, aktueller Arbeitspreis — für spot_backtest (Vergleichsbasis Fix vs. Spot, Hebel Tarif).
- **aktuelle_grundgebuehr_brutto_eur_monat** (Quelle: rechnung|frage, Optional) — EUR/Monat brutto — für spot_backtest.tarif_ersparnis; fehlt sie, liefert der Block verfuegbar=false + grund (keine stille 0).
- **heizung** (Quelle: rechnung|frage, Optional) — Heizungstyp (elektrisch/Gas/Fernwärme/Pellets) — bestätigt oder widerlegt das electric_heating-Signal, schaltet den WP-Tarif-Hebel frei (f_wp_tarif).
- **pv_status** (Quelle: rechnung|frage, Optional) — PV vorhanden? kWp, Speicher — bestätigt/widerlegt pv_self_consumption; eine bestätigte Einspeisung löst einen zweiten Consent für den Einspeise-Zählpunkt aus (WP2-E (b)).
- **ev_status** (Quelle: rechnung|frage, Optional) — E-Auto/Wallbox vorhanden? Ladeleistung (kW) — Kontext für ein Nachtladen-Muster (Wallbox-Nächte, Ledger-F6/F8).

## Fragen

### f_heizung_likely (Hebel: tarif)
- Frage: Dein Winterverbrauch ist deutlich höher — heizt du mit Strom (Wärmepumpe/Direktheizung) oder nur mehr Beleuchtung/Geräte?
- Nur wenn: electric_heating == likely (winter_summer_ratio >= 2,5, lastgang_signals)
- Ableitung: Setzt asset.heating.type. Bei is_pv=true ersetzt der PV-Guard (Ledger-F24) diesen Text automatisch durch die neutrale Formulierung und stuft das Signal auf 'unknown' zurück — die Frage bleibt inhaltlich offen statt zu behaupten.

### f_heizung_unlikely (Hebel: tarif)
- Frage: Dein Stromverbrauch ist über das Jahr flach — heizt du mit Gas/Fernwärme/Pellets (also nicht elektrisch)?
- Nur wenn: electric_heating == unlikely
- Ableitung: Setzt asset.heating.type (Widerlegung möglich, z. B. bei sehr gut gedämmten Wärmepumpen-Häusern — das Signal bleibt eine Hypothese, keine Behauptung).

### f_pv_signal (Hebel: speicher)
- Frage: Tagsüber sinkt dein Netzbezug auffällig — hast du eine PV-Anlage? Wie viel kWp, und gibt es einen Speicher? Und: hast du eine PV-Einspeisung, für die wir einen eigenen Consent bräuchten?
- Nur wenn: pv_self_consumption == likely (midday_dip_ratio < 0,85 oder gemeldete Einspeisung, lastgang_signals)
- Ableitung: Setzt asset.pv.kwp/asset.battery.kwh — NEU ggü. dem reinen Signal-Port: eine bestätigte PV-Einspeisung löst einen ZWEITEN Consent für den Einspeise-Zählpunkt aus (energy_direction=generation, WP2-E (b)); danach greifen die PV-Guards (basis_label='Netzbezug').

### f_dauerlaeufer (Hebel: verhalten)
- Frage: Nachts läuft konstant einiges an Grundlast durch — gibt es Dauerverbraucher (Pool, Aquarium, Server, alter Kühlschrank, Boiler)?
- Nur wenn: high_continuous_load == likely (night_base_w >= 300 W, lastgang_signals)
- Ableitung: Setzt asset.continuous_loads — night_base_w ist bereits in Watt UND mit Fenster (00:00–04:59) gelabelt (Ledger-F7: Einheit+Fenster nie im Kopf konvertieren).

### f_lastverschiebung (Hebel: verhalten)
- Frage: Dein Tages-Peak liegt zu einer bestimmten Abendstunde — kannst du Wasch-/Spül-/Trockner-Läufe zeitlich verschieben?
- Nur wenn: immer (unabhängig vom Signal-Zustand gestellt, select_rueckfragen)
- Ableitung: Setzt behavior.appliance_timing — Hebel 'Verhalten', unabhängig vom Ausgang der übrigen Signale.

### f_wp_tarif (Hebel: tarif)
- Frage: Läuft dein Heizungs-/Wärmepumpen-Zähler schon auf einem Wärmepumpen-/Heizstromtarif oder auf einem normalen Haushaltstarif? Ist er als unterbrechbar angemeldet (reduziertes Netzentgelt)?
- Nur wenn: asset.heating.type bestätigt elektrisch (aus f_heizung_likely oder Rechnungsdaten) — Hebel-Frage aus Rezept 07
- Ableitung: Größter sicherer Sofort-Hebel bei bestätigter E-Heizung — schaltet den Heizstromtarif-Vergleich frei (Rezept 07 Hebel 1).

### f_pv_eckdaten (Hebel: speicher)
- Frage: Wie groß ist die PV-Anlage genau (kWp), Ausrichtung/Neigung, Inbetriebnahmejahr — und gibt es schon einen Batteriespeicher (kWh)?
- Nur wenn: asset.pv.kwp bestätigt (aus f_pv_signal oder Rechnungsdaten) — Hebel-Frage aus Rezept 07
- Ableitung: Speicher-Dimensionierung/-Wirtschaftlichkeit (Rezept 07 Hebel 3/4) — die Tag/Nacht-Verschiebung dafür braucht zusätzlich Q15-Auflösung (siehe f_q15_optin).

### f_q15_optin (Hebel: datenqualitaet)
- Frage: Dein Smart Meter liefert aktuell nur Tageswerte — aktivierst du den Viertelstundenwerte-Opt-in im Netzbetreiber-Portal? Damit werden Ursachen-Signale, Geräte-Zerlegung und der profilgewichtete Spot-Vergleich möglich, die mit Tageswerten nicht gehen.
- Nur wenn: Consent liefert nur Tageswerte (kein 15-min-Opt-in) — aus list_load_series/get_data_release_status ablesbar
- Ableitung: Granularitäts-Guard (F29 (a)): ohne Q15 verweigern lastgang_signals/trend_attribution/spot_backtest mit Begründung — diese Frage ist die aktive Opt-in-Empfehlung aus dem Tageswerte-Pfad (Rezept 07 Hebel 4/6).

## Signal-Präzedenz (Fakt vor Heuristik)

- **electric_heating** ist Heuristik für `asset.heating.type`
- **pv_self_consumption** ist Heuristik für `asset.pv.kwp`
- **high_continuous_load** ist Heuristik für `asset.continuous_loads`

## Tool-Mapping

### serien_uebersicht — `list_load_series` (extern, aktiv)
- Erster Schritt: welche Serien liegen bereits am Account (ZP maskiert, Richtung, Zeitraum, Coverage, Datenstand) — bevor irgendetwas neu angefordert wird (kein doppelter Consent-Flow).
- Meldet auch die Granularität (Q15 vs. Tageswerte) — Grundlage für den Tageswerte-Pfad-Guard (F29 (a), siehe datenqualitaet_abbruch).

### datenfreigabe_anfordern — `request_data_release` (extern, aktiv)
- Nur falls serien_uebersicht keine aktive Freigabe zeigt. ZP kommt aus den Invoice-Fakten der Instanz (kein Abtippen, WP2-E (b)).
- Kündigt den Portal-Schritt EXAKT an: 'Freigaben→Offen, Provider EP100505, 1 Klick' — nie einen anderen Text erfinden.
- Bei bestätigter PV-Einspeisung (f_pv_signal): zweiter Consent-Aufruf für den Einspeise-Zählpunkt (energy_direction=generation).

### datenfreigabe_status — `get_data_release_status` (extern, aktiv)
- Warte-UX ist Pflicht: CM_CONF-Latenz kann Minuten bis Stunden dauern — ehrlich 'das kann dauern' sagen, statt endlos zu pollen.
- Nach Consent-Aktivierung fordert der ESP die Historie automatisch an — kein zweiter User-Schritt nötig (WP2-E (c)).

### lastprofil_metriken — `load_profile` (energietools, aktiv)
- consumption_data ist die vom Gateway aus serie_ref aufgelöste Serie — läuft NIE als Rohserie durchs User-LLM (Amendment 4).
- Läuft auch auf Tageswerten weiter (Granularitäts-Caveat statt Verweigerung, F29 (a)).

### ursachen_signale — `lastgang_signals` (energietools, aktiv)
- Pflicht-Inputs: consumption
- consumption ist die vom Gateway aufgelöste Serie (s. lastprofil_metriken).
- Verweigert bei Tageswerten (interval_minutes >= 60) mit Begründung — dann aktiv den Q15-Opt-in empfehlen (f_q15_optin, F29 (a)).
- is_pv aus dem Einspeise-Consent/ZP-Suffix setzen — schaltet die PV-Guards (Netzbezug-Label, electric_heating-Herabstufung, Ledger-F3/F14/F24).
- Treibt den signal-getriebenen Rückfragen-Katalog (fragen-Block) — nur die Fragen stellen, deren Signal feuert.
- profil_fakten löst der Gateway aus der kanonischen Profil-Seite auf (get_page) — Fakt schlägt Heuristik deterministisch im Rechenkern; jede Antwort trägt quelle (s. signale-Block, Fakt vor Heuristik).

### mehrjahres_trend — `load_trend` (energietools, aktiv)
- Pflicht-Inputs: consumption
- Kalender-YoY nur bei >=2 vollen Kalenderjahren (Coverage-Guard) — sonst Fenster-YoY; NIE ein Teiljahr gegen ein Volljahr stellen.
- Läuft auch auf Tageswerten weiter (Granularitäts-Caveat, F29 (a)).

### treiber_zerlegung — `trend_attribution` (energietools, aktiv)
- Pflicht-Inputs: consumption
- Nur sinnvoll mit >=2 Jahren Q15-Historie — braucht dieselbe Serie wie mehrjahres_trend.
- Verweigert bei Tageswerten mit Begründung (F29 (a)).
- Ergebnis ist eine Geräte-KLASSE als Hypothese, NIE ein Gerätename (15-min-Grenze, Abnahme-Kriterium 15 — hartes DoD-Gate).

### spot_und_tarifvergleich — `spot_backtest` (energietools, aktiv)
- spot_prices kommt aus der EPEX-Reihe im Box-Postgres (WP-D), nicht vom User-LLM.
- tarif_ersparnis ist NUR verfügbar, wenn plz/energiepreis_brutto_ct_kwh/aktuelle_grundgebuehr_brutto_eur_monat/aktueller_lieferant/jahresverbrauch_kwh vorliegen — sonst verfuegbar=false + grund, NIE eine stille 0.
- Verweigert bei Tageswerten mit Begründung (F29 (a)).
- Hebel-Reihenfolge (ziel): Tarif zuerst prüfen, bevor Verhaltens-/Speicher-Hebel folgen.

### rueckfragen_persistieren — `submit_lastgang_facts` (extern, aktiv)
- Die beantworteten Rückfragen (fragen-Block) werden als Profil-Fakten persistiert — gleiche Rejection-Semantik wie submit_invoice_facts (D2.2).
- Session 2: get_page/search_pages liefert den Fakt ohne erneute Frage (Abnahme-Kriterium 6) — kein neuer Mechanismus, dasselbe ingest→compile_next-Muster (§3.6 Punkt 1).

## Datenqualität & Abbruch

- PV-Guard: is_pv=true (Einspeiser erkannt) -> Metriken NICHT als Verbrauch verkaufen, sondern als Netzbezug labeln (lastgang_signals.basis_label='Netzbezug'); electric_heating wird bei PV zur Rückfrage statt Behauptung herabgestuft (Ledger-F24).
- Coverage-Guard: Teiljahr (<2 volle Kalenderjahre) -> load_trend verweigert die Kalender-YoY (calendar_yoy_verweigert_grund gesetzt) und weicht auf die Fenster-YoY über deckungsgleiche (Monat,Tag,Std,Min)-Slots aus — kein Kalenderjahr-gegen-Teiljahr-Vergleich.
- Mindestdaten: mindestens 1 Tag à 96 Q15-Intervalle — darunter meldet load_profile 'Zu wenig Datenpunkte' und die Analyse bricht ab, statt einen Wert zu erfinden.
- Magnitude+Frequenz an dieselbe Schwelle binden (Ledger-F6): jede Häufigkeits-Aussage (z. B. 'X Nächte über Y kW') nennt die Nächtezahl NUR neben genau der kW-Schwelle, mit der sie berechnet wurde — nie zwei Schwellen im selben Satz mischen (Cross-Citation-Fehler).
- Granularitäts-Guard (F29 (a)): Tageswerte-Serie (kein 15-min-Opt-in, interval_minutes >= 60) -> lastgang_signals/trend_attribution/spot_backtest verweigern mit Begründung + aktiver Q15-Opt-in-Empfehlung (f_q15_optin); load_profile/load_trend laufen weiter, aber mit explizitem Granularitäts-Caveat statt Intraday-Signalen.

## Caveats (MÜSSEN in die Antwort)

- **Trigger `profil_abgleich.anzahl_widersprueche > 0`:** Ein gespeicherter Profil-Fakt widerspricht dem Lastgang-Muster — die Antwort folgt dem gespeicherten Fakt; prüfe, ob sich etwas geändert hat (Fakt veraltet?).
- **Trigger `is_pv == true`:** Die Metriken beschreiben deinen NETZBEZUG, nicht deinen Gesamtverbrauch — bei einer PV-Anlage ist der Mittags-Bezug PV-gedeckt und dadurch niedriger als der reale Verbrauch.
- **Trigger `anzahl_treiber > 0`:** Die Geräte-Zerlegung nennt eine Geräte-KLASSE als Hypothese (z. B. "Kochen", "Elektronik"), NIE ein konkretes Gerät — ein 15-Minuten-Takt kann taktende Einzelgeräte nicht identifizieren, nur andauernde Lastmuster.
- **Trigger `immer`:** Ein Teiljahr oder Halbjahr im Lastgang wird NICHT auf ein volles Jahr hochgerechnet — ohne Saisonalitäts-Korrektur wäre das kein verlässlicher Jahreswert.
- **Trigger `immer`:** Jede Anteils-/Prozent-Zahl (z. B. Grundlast-Anteil, Profilkostenfaktor) trägt ihre Nenner-Definition aus dem Tool-Result — nie ohne diese Definition weiterreichen.
- **Trigger `immer`:** €-Beträge ohne eine bestätigte PLZ sind eine grobe Heuristik (kein hinterlegter Netzbetreiber, keine regionale Tarifprüfung) — sobald die PLZ vorliegt, werden sie exakt.
- **Trigger `immer`:** Die Lastgang-Daten enden am Vortag 23:45 (EDA-Tagesrhythmus, kein Echtzeit-Smart-Meter) — die Analyse ist nie "live", sondern maximal bis gestern Abend aktuell.
- **Trigger `immer`:** Jede Zahl in der Antwort stammt wörtlich aus einem Tool-Result (load_profile/lastgang_signals/load_trend/trend_attribution/ spot_backtest) — nie selbst gerechnet, gerundet oder paraphrasiert (Ledger-F7/F8: kein Cross-Citation-Fehler).

