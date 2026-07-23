# METHODIK — Erhebung & Validierung der energietools-Daten

> Ziel dieses Dokuments: Jede Zahl, die `energietools` für einen User produziert, soll
> **nachvollziehbar** (mit Quelle und Rechenweg) und **verlässlich** (gegen eine zweite
> unabhängige First-Party-Quelle validiert) sein. Ein externer Reviewer muss die
> Erhebung und die Validierung allein anhand der versionierten Snapshots in
> `energietools/data/` reproduzieren können.

---

## 1. Grundprinzip

`energietools` rechnet ausschließlich gegen **First-Party- und statutarische Quellen** —
und vollständig **offline** gegen versionierte Daten-Snapshots. Konkret heißt das:

- **Energiepreise** kommen direkt von den Anbietern (deren Websites + offizielle
  Preisblatt-PDFs nach ElWOG/EAG), nicht von einem Dritten.
- **Netzkosten** kommen aus den offiziellen Netzbetreiber-Preisblättern, cross-validiert
  gegen die **Systemnutzungsentgelte-Verordnung** (BGBl. II Nr. 305/2025).
- **Abgaben/Steuern** kommen direkt aus den **Verordnungen und Gesetzen**
  (EAG-Förderbeitrags-/-pauschale-Verordnung, Elektrizitätsabgabegesetz,
  Landes-/Gemeinde-Gebrauchsabgabegesetze).

**Keine fremde Rechner-API.** Das ist eine bewusste,
harte Grenze: Wir spiegeln nicht das Ergebnis eines fremden Tarifrechners, sondern erheben die
Eingangsgrößen selbst aus erster Hand und rechnen sie mit einem offen dokumentierten,
auditierbaren Rechenweg zusammen. Damit ist jedes Ergebnis von Hand oder durch einen
Auditor unabhängig re-derivierbar — ohne Abhängigkeit von einer fremden, nicht prüfbaren
Black Box.

Jede einzelne Zahl trägt zwei Dinge mit sich:

1. eine **Quelle** (Anbieter-URL bzw. Preisblatt-/Verordnungs-Fundstelle), und
2. einen **Rechenweg** (die Schritte von der erhobenen Rohgröße zum ausgewiesenen Wert).

Die Erhebungs-Maschinerie (Scraper) ist proprietär und nicht Teil dieses Repos; **die
Ergebnis-Daten** sind hier MIT-lizenziert publiziert und offline prüfbar.

---

## 2. Tarife (Energiepreise)

### 2.1 Erhebung

- **Quellen (First-Party):** die Anbieter-Websites selbst **und** die offiziellen
  Preisblatt-PDFs, die nach ElWOG/EAG zu veröffentlichen sind. Pro Tarif werden damit
  **zwei voneinander unabhängige First-Party-Quellen** herangezogen.
- **Preisbasis:** **Netto-Listenpreise** (`price_basis: "netto_listenpreis"` im MANIFEST).
  Netzkosten und PLZ-abhängige Abgaben sind bewusst **nicht** im Tarif enthalten — sie
  werden erst zur Vergleichszeit aus der Netz-Schicht (§3) ergänzt. So bleibt jede Schicht
  einzeln prüfbar.
- **Frequenz:** täglich aktualisiert; der Stand steht in
  `data/tariffs/MANIFEST.json → generated_at`.
- **Aktueller Stand:** `tariff_count: 131` Tarife, `provider_coverage: 65/65 ok`
  (65 = erfasste Anbieter-Quellen; im Katalog vertretene Lieferanten distinct = 57),
  `failed: []`.

Pro Tarif werden u. a. erhoben: `energiepreis_ct_kwh`, `grundgebuehr_eur_monat`,
`tariftyp` (Fixpreis/Floater/…), `spot_aufschlag_ct`/`spot_index` (bei Spot-Tarifen),
`neukundenrabatt_ct_kwh`/`neukundenrabatt_eur`, `preisgarantie_monate`, `hat_bindung`,
`ist_oekostrom` sowie der `wechsel_link` (die First-Party-Anbieter-URL als Quelle).

### 2.2 Validierung (drei Gates)

Ein Tarif wird nur veröffentlicht, wenn er alle drei Gates passiert:

- **(a) Website ↔ Preisblatt-Abgleich.** Der von der Website gescrapte Preis muss mit dem
  Preisblatt-PDF desselben Anbieters übereinstimmen. Zwei unabhängige First-Party-Quellen
  müssen denselben Wert ergeben. Diskrepanz → kein Publish, manuelle Klärung.
- **(b) Change-Diff-Gate (Quarantäne statt Veröffentlichung).** Zwischen zwei
  Tages-Snapshots wird jeder Tarif gegen den Vortag diff'd. Ein **Preissprung > 30 %**
  (Energiepreis oder Grundgebühr) gilt als Auffälligkeit und schickt den Tarif in
  **Quarantäne** — der alte, geprüfte Wert bleibt online, der neue wird erst nach Sichtung
  freigegeben. So schlägt kein Scrape-Fehler und keine fehlinterpretierte Aktion still in
  ein User-Ergebnis durch.
- **(c) Plausibilitäts-Anker je Scraper.** Jeder anbieterspezifische Scraper hat feste
  Anker (z. B. erwartete Größenordnung von Energiepreis und Grundgebühr, Pflichtfelder,
  Einheiten). Verletzt ein Scrape die Anker, gilt der Lauf für diesen Anbieter als
  fehlgeschlagen (`failed[]`) — es wird kein halbgarer Datensatz publiziert.

### 2.3 Nachvollziehbarkeit (Quelle + Rechenweg)

Jeder Tarif trägt seine **Quelle** als Anbieter-URL (`wechsel_link`). Der **Rechenweg** vom
Netto-Listenpreis zum Brutto-Jahresbetrag ist offen und deterministisch
(`capabilities/tariffs/compare.py → kosten_rechenweg`), in genau dieser Reihenfolge
**netto → Rabatt → Gebrauchsabgabe → USt → brutto**:

```
netto_energie      = verbrauch_kwh * netto_ep_ct / 100
netto_grund        = grundgebuehr_netto_eur_monat * 12
netto_gesamt       = netto_energie + netto_grund
rabatt_netto       = verbrauch_kwh * neukundenrabatt_ct_kwh / 100
netto_nach_rabatt  = max(0, netto_gesamt − rabatt_netto)
gebrauchsabgabe    = netto_nach_rabatt * gebrauchsabgabe_rate
netto_inkl_gab     = netto_nach_rabatt + gebrauchsabgabe
ust                = netto_inkl_gab * 0,20
brutto             = netto_inkl_gab * 1,20 − neukundenrabatt_pauschal_eur
```

Jeder Zwischenschritt (`netto_energie_eur`, `netto_nach_rabatt_eur`,
`gebrauchsabgabe_eur`, `ust_eur`, `brutto_jahreskosten_eur`, …) wird im Ergebnis
mitgeführt und ist damit Zeile für Zeile von Hand prüfbar.

---

## 3. Netzkosten & Nebenkosten

### 3.1 Erhebung

- **Profil:** `NE7 Haushalt, ohne Leistungsmessung, Niederspannung` — das
  Standard-Haushaltsprofil. Genau dieses Profil ist im MANIFEST festgehalten, damit klar
  ist, welche Tarifstufe verglichen wird.
- **Netzkosten je Netzbereich:** aus den **offiziellen Netzbetreiber-Preisblättern**
  (`data/netz/netzkosten.json`). Pro Netzbereich werden erhoben:
  `netznutzung_arbeitspreis_ct_kwh`, `netznutzung_pauschale_eur_jahr` und
  `netzverlust_ct_kwh`, jeweils mit `gueltig_ab` und `quelle` (Preisblatt-URL des
  Netzbetreibers, ersatzweise die Verordnungs-Fundstelle, wo kein direkter
  Preisblatt-Link vorliegt). Jeder
  Eintrag trägt zusätzlich `gemeinden` (Inklusionsliste der Stadt-/Enklaven-VNB), damit
  der Resolver inklusion-first auflösen kann.
- **Genau 14 NE7-Netzbereiche.** Die Novelle 2026 ersetzt (§ 5 Abs. 1 Z 6 „lautet:") die
  NE7-Tarifliste vollständig durch **14 Netzbereiche**: 9 Bundesländer + 4 Stadt-
  Netzbereiche (Linz, Graz, Innsbruck, Klagenfurt) + Kleinwalsertal. Das ist die
  **vollständige** Liste — jeder der ~119 VNB billt einen dieser 14 Tarife.
- **Attributions-VNB** (`data/netz/vnb_attribution.json`): kleine Stadtwerke (z. B.
  Stadtwerke Kapfenberg) tragen einen **realen Namen** + `tarif_referenz` auf ihren
  Netzbereich-VNB — Tarif via Referenz, **kein Wert-Duplikat**. So zeigt der Resolver den
  tatsächlichen Betreiber, ohne einen zweiten Tarif zu führen.
- **Autoritative Gesamttabelle:** die **Systemnutzungsentgelte-Verordnung (BGBl. II
  Nr. 305/2025)** dient als verordnungsseitige Gesamttabelle der Systemnutzungsentgelte,
  gegen die jeder einzelne Preisblatt-Wert gegengeprüft wird.
- **Föderale Konstanten:** EAG-Förderbeitrag (Arbeits- und Verlust-Anteil),
  EAG-Förderpauschale und Elektrizitätsabgabe (Haushalt) kommen **direkt aus den
  Verordnungen** (`data/netz/abgaben.json → federal`). Diese Größen sind **bundesweit
  uniform** und werden daher **zentral** gepflegt, nicht je Netzbereich dupliziert.

### 3.2 Validierung

- **Preisblatt ↔ Verordnung Cross-Check, je Netzbereich.** Für jeden erfassten VNB
  wird der Preisblatt-Wert **exakt gegen die Verordnung** (BGBl. II Nr. 305/2025)
  bestätigt. Stimmt Preisblatt und Verordnung nicht überein, wird der Netzbereich **nicht**
  als `ok` gezählt. Aktueller Stand: **alle 14 Netzbereiche** sind so bestätigt
  (`netzbereich_coverage.ok = 14`) → **vollständige NE7-Kosten-Abdeckung**.
- **Adversariale Doppel-Lesung.** Jeder NE7-Wert wird zweifach unabhängig aus dem
  (gerenderten) Tabellen-PDF gelesen und gegen die Verordnungs-Zeile abgeglichen. Die
  typischen Fallen werden explizit ausgeschlossen: **AP** (rund um die Uhr), nicht
  SNAP/DTAP/DNAP; **Entnehmer-Verlust**, nicht der bundesweite Einspeiserwert
  0,279 ct/kWh; Zeile **„nicht gemessene Leistung"**, nicht „gemessene Leistung".
- **Long-Tail-Befund (Novelle 2026):** Die ~105 kleinen Stadtwerke haben **keinen eigenen
  NE7-Tarif** mehr — empirisch an 3 Preisblättern 2026 bestätigt (Stadtwerke Kufstein =
  Bereich Tirol, Kapfenberg = Steiermark, Feldkirch = Vorarlberg). Bis Novelle 2025
  bestehende Eigen-Tarife (z. B. Kapfenberg 9,13) wurden konsolidiert. Sie werden daher
  **nicht** als eigene Netzbereiche geführt, sondern als Attributions-VNB (realer Name,
  Tarif via Referenz).
- **Föderale Konstanten** stammen direkt aus den Verordnungen und sind damit selbst die
  autoritative Quelle — sie sind nicht aus Sekundärquellen abgeleitet.

### 3.3 Gebrauchsabgabe (landes-/gemeindespezifisch)

- **Basis:** der **Energie-Netto** (`abgaben.json → gebrauchsabgabe.basis = "energie_netto"`),
  konsistent mit dem Rechenweg in §2.3.
- **Ehrlichkeitsregel:** nur **verifizierte** Sätze werden angewandt. Aktuell verifiziert:
  **Wien 7 % ab 01.03.2026** (Wiener Gebrauchsabgabegesetz). Wo kein Landes-Gebrauchs­abgabe­gesetz
  existiert (z. B. Burgenland, Vorarlberg) bzw. wo kein Satz verifiziert ist, gilt
  **`rate = 0`** — **nicht erfunden, nicht geschätzt**, sondern ehrlich null.
- Jede Regel trägt ihre `quelle` (Gesetzes-Fundstelle) mit.

### 3.4 Nachvollziehbarkeit (Quelle + Rechenweg)

Jeder Netzbereich in `netzkosten.json` trägt:

- **`quelle`** — die Preisblatt-URL des Netzbetreibers; wo kein direkter Preisblatt-Link
  vorliegt, ersatzweise die Verordnungs-Fundstelle (BGBl. II Nr. 305/2025),
- **`gueltig_ab`** — ab wann der Wert gilt (z. B. Energienetze Steiermark `2026-04-01`),
- und über das MANIFEST den **Verweis auf die Verordnungs-BGBl-Nummer** (BGBl. II
  Nr. 305/2025) als verordnungsseitigen Cross-Check.

Beispiel (verifizierbar in `netzkosten.json`):

```
Wiener Netze GmbH — Wien
  netznutzung_arbeitspreis_ct_kwh : 6,98
  netznutzung_pauschale_eur_jahr  : 54,0
  netzverlust_ct_kwh              : 0,70
  gueltig_ab                      : 2026-01-01
  quelle                          : wienernetze.at/.../netznutzungs-und-netzverlustentgelt_2026
```

Damit ist die Netzkosten-Komponente eines Vergleichsergebnisses Schritt für Schritt auf
ein offizielles Preisblatt **und** auf die Verordnung zurückführbar.

---

## 4. Ehrlichkeit & Grenzen

- **Coverage-Ledger.** Der Stand steht explizit im MANIFEST: `netzbereich_coverage = 14`
  von 14 NE7-Netzbereichen der Novelle 2026 → **vollständige Kosten-Abdeckung**: jede
  österreichische Gemeinde löst auf einen korrekten NE7-Tarif auf. Die ~105 kleinen
  Stadtwerke sind **keine** eigenen Netzbereiche (sie billen den Tarif ihres
  Netzbereichs); sie werden als Attributions-VNB (realer Name) geführt — derzeit eine
  erste Charge (Kapfenberg/Kufstein/Feldkirch), additiv erweiterbar ohne Kostenwirkung.
- **Fail-open bei Unbekanntem.** Ist eine PLZ bzw. ein Netzbereich nicht erfasst, werden
  **keine Netzkosten geschätzt oder erfunden** — es wird keine Zahl behauptet, die wir
  nicht aus einem Preisblatt belegen können. Der `disclaimer` im MANIFEST sagt das
  wörtlich: „Unbekannte PLZ/Netzbereiche werden NICHT geschätzt (fail-open)."
- **„No silent caps."** Es gibt keine stillen Deckelungen, Default-Pauschalen oder
  geratenen Ersatzwerte, die ein Ergebnis heimlich „glätten". Fehlt eine Grundlage, ist
  das im Ergebnis sichtbar — nicht weginterpoliert.
- **Disclaimer (Tarife):** Netto-Listenpreise, ohne Gewähr; Netzkosten und PLZ-abhängige
  Abgaben werden erst zur Vergleichszeit ergänzt.
- **Disclaimer (Netz):** regulierte Netzkosten + Abgaben, ohne Gewähr; der Stand jedes
  Werts steht in dessen `gueltig_ab`.

---

## 5. Reproduzierbarkeit

Die Methodik ist nicht nur beschrieben, sondern **ausführbar prüfbar**:

- **Versionierte Snapshots.** Alle Daten liegen versioniert im Repo:
  - `data/tariffs/catalog.json` + `data/tariffs/MANIFEST.json`
  - `data/netz/netzkosten.json` (14 Tarif-Netzbereiche, mit `gemeinden`),
    `data/netz/vnb_attribution.json` (Attributions-VNB), `data/netz/abgaben.json`,
    `data/netz/plz_netzbereich.json` + `data/netz/MANIFEST.json`
- **Inhaltliche Erklärung.** Wie sich der Strompreis aus Netzkosten + Abgaben + Energie +
  USt zusammensetzt (Hintergrund, Formel, Rechenbeispiel) steht in
  [`NETZKOSTEN_UND_GEBUEHREN.md`](NETZKOSTEN_UND_GEBUEHREN.md).
- **MANIFEST je Schicht.** Jedes MANIFEST trägt: `generated_at` (Stand),
  `coverage`/`provider_coverage`/`netzbereich_coverage`, `provenance` (Quellenbeschreibung),
  `license: MIT` sowie eine `provenance`-Beschreibung der Quellen (First-Party-Preisblätter + Verordnungen).
- **Offline rechenbar.** Jede Capability (`tariff_catalog`, `tariff_compare`,
  `tariff_advice`, …) ist **vollständig offline** gegen diese Snapshots rechenbar — keine
  Live-Lookups, keine externe Tarif-API. Ein Reviewer kann denselben Snapshot nehmen, den
  Rechenweg aus §2.3 anwenden und auf denselben Brutto-Jahresbetrag kommen.
- **Audit-Pfad.** Ergebnis → Rechenweg-Schritte → erhobene Rohgröße → `quelle`-URL
  (Anbieter-Preisblatt bzw. Netzbetreiber-Preisblatt) → verordnungsseitiger Cross-Check
  (Verordnung BGBl. II Nr. 305/2025; EAG-/Elektrizitätsabgabe-Verordnungen). Dieser Pfad ist für
  jede einzelne Zahl geschlossen.

---

### Reviewer-Checkliste (5 Minuten)

1. `data/tariffs/MANIFEST.json` öffnen → `generated_at`, `price_basis = netto_listenpreis`,
   `provider_coverage 65/65` (65 = erfasste Anbieter-Quellen; distinct `lieferant` im
   Katalog = 57, siehe `note`), `provenance` nennt die eigene Erhebung aus
   Anbieter-Websites + Preisblatt-PDFs.
2. Einen Tarif in `catalog.json` wählen → `wechsel_link` (Quelle) öffnen, Energiepreis &
   Grundgebühr gegen die Anbieter-Seite halten.
3. Rechenweg aus §2.3 von Hand auf diesen Tarif anwenden → Brutto-Jahreskosten
   reproduzieren.
4. Einen Netzbereich in `netzkosten.json` wählen → `quelle` öffnen (Preisblatt-URL des
   Netzbetreibers, ersatzweise die Verordnungs-Fundstelle), `netznutzung_arbeitspreis_ct_kwh`
   bestätigen, gegen die Verordnung (BGBl. II Nr. 305/2025) gegenprüfen.
5. Eine nicht in `plz_netzbereich.json` gelistete PLZ probieren → bestätigen, dass **keine**
   Netzkosten erfunden werden (fail-open).

---

## 6. Fakt vor Heuristik (Lastgang-Signale)

Dasselbe Nachvollziehbarkeits-Prinzip gilt außerhalb der Tarif-/Netzkosten-Schicht auch
für die Lastgang-Signale (`lastgang_signals`): elektrische Heizung, PV-Eigenverbrauch und
Dauerläufer sind dort **Heuristiken** aus dem Q15-Muster (Winter/Sommer-Verhältnis,
Mittags-Delle, Nacht-Grundlast) — plausibel, aber keine Beweise.

- **Provenienz-Envelope.** Jeder Signal-Wert trägt seine Herkunft mit (`*_quelle`:
  `profil|rechnung|messung|prognose|heuristik`). Kommt ein Wert aus einem vom Nutzer
  bestätigten Profil-Fakt (z. B. `asset.heating.type=gas`), ist `quelle` niemals
  `"heuristik"` — eine Heuristik wird nie als Fakt ausgegeben und ein Fakt nie stillschweigend
  überschrieben.
- **Präzedenz.** Ein gespeicherter Fakt schlägt IMMER die Lastgang-Heuristik
  (`capabilities/lastgang/reconcile.py::PRAEZEDENZ`, deklarative SSOT-Tabelle). Das
  Ergebnis-Feld ist fakt-konsistent gesetzt; die Heuristik verschwindet dabei nicht,
  sondern bleibt als Gegenprobe sichtbar.
- **Gegenprobe.** `profil_abgleich` im Result hält je Feld sowohl den Fakt (`wert`,
  `quelle`, `stand`) als auch die reine Heuristik-Schätzung (`heuristik_schaetzung`,
  `kennzahl`) nebeneinander — inklusive einem Status
  (`konsistent|widerspruch|nicht_pruefbar|kein_fakt`) und, bei Widerspruch, einem
  deterministischen Caveat-Text. So bleibt sichtbar, WARUM eine Antwort vom rohen
  Lastgang-Muster abweicht, statt die Abweichung zu verstecken.
