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
  - `data/foerderungen/foerderungen.json` + `MANIFEST.json` (§7),
    `data/beratung/beratungsstellen.json` + `MANIFEST.json` (§8),
    `data/energiegemeinschaften/{fakten,verzeichnis,beg_providers}.json` + `MANIFEST.json` (§9),
    `data/marktdaten/solar_speicher.json` + `MANIFEST.json` (§10)
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
6. `data/foerderungen/MANIFEST.json` öffnen → `coverage.gesamt == 45` und
   `len(foerderungen.json) == 45` bestätigen (Manifest-Konsistenz); einen Eintrag mit
   `verlaesslichkeit: "unsicher"` wählen und bestätigen, dass ihn
   `FoerderungenCheckCapability().run(bundesland=...)` **ohne** `inkl_unsicher=True`
   nicht zurückgibt.
7. `FoerderungenCheckCapability().run(bundesland="Nirgendwo")` aufrufen → bestätigen,
   dass eine strukturierte `CapabilityRejection` (kein Absturz, kein stilles
   Leer-Ergebnis) mit einer Bundesland-Rückfrage kommt.
8. `data/energiegemeinschaften/fakten.json → rechtsformen.beg.netzentgelt_reduktion.prozent`
   öffnen → bestätigen, dass er `null` ist (nicht geschätzt) und
   `elwg_aenderung.teil_inkrafttreten_2.datum == "2026-12-31"` (nicht der pauschale,
   in der Praxis irreführende 1.10.2026-Termin) trägt.

---

## 6. Förderungen

### 6.1 Erhebung

- **Quellen (First-Party/statutarisch):** Bundes- und Landes-Förderstellen-Websites
  (`umweltfoerderung.at`, `eag-abwicklungsstelle.at`, Landes-Wohnbauförderungs-Seiten,
  Gemeinde-Förderseiten), ergänzt um RIS-Gesetzestexte (z. B. UStG § 28 Abs. 62) und
  amtliche Transparenzdatenbank-Einträge (`data.gv.at`) für Programm-Laufzeiten.
- **Erhebungsdatum:** manuelle Recherche, Stand `2026-07-31`, **dreifach verifiziert**
  (jede Aussage gegen die Primärquelle gegengelesen, bei Diskrepanz die vom Dokument
  selbst als korrekt bestätigte Fassung übernommen — z. B. Kärnten-Speicherbudget
  "40 Mio. € 2026" vs. der im Dokument präzisierten Erkenntnis, dass das der
  2025er-Auszahlungsbetrag war).
- **Snapshot:** `data/foerderungen/foerderungen.json` (45 Einträge: 10 Bund, 35 Land/
  Gemeinde) + `data/foerderungen/MANIFEST.json` (`coverage` zählt offen/geschlossen/
  verifiziert/unsicher). Ersetzt den alten kuratierten Katalog (Stand 2026-03-05,
  17 Einträge) vollständig — 3 Einträge (`bund-kesseltausch`, `bund-sanierungsbonus`,
  `wien-speicher`) tragen zusätzlich historische Sätze aus dem alten Katalog, klar
  als solche markiert (`foerderhoehe.text` nennt Stand + Grund), weil die neue
  Recherche selbst "nicht beziffert" vermerkt UND das jeweilige Programm ohnehin
  geschlossen ist (kein Aktualitäts-Risiko für Nutzer:innen).

### 6.2 Validierung

- **"Bund vor Land"-Kopplung explizit geprüft.** Mehrere Landesförderungen (Kärnten,
  Salzburg, Burgenland, NÖ, Vorarlberg) setzen eine laufende/bewilligte
  Bundesförderung voraus. Da der Bund seit 10.07.2026 keine Neuregistrierungen mehr
  annimmt (Kesseltausch, Sauber Heizen für Alle), ist das im `status_detail` jedes
  betroffenen Eintrags **explizit** vermerkt — die Landesrichtlinie selbst gilt
  formal weiter, ist aber für neue Fälle faktisch blockiert.
- **Kolportierte Beträge nie stillschweigend als Fakt.** Balkonkraftwerk-Förderungen
  ohne Primärquelle (Steiermark, Burgenland, Innsbruck) wurden trotzdem als Eintrag
  angelegt (nicht verworfen) — aber mit `verlaesslichkeit: "unsicher"` +
  `unsicher_grund`, damit ein im Umlauf befindlicher, potenziell falscher Betrag
  aktiv richtiggestellt statt stillschweigend bestätigt wird.
- **Widerlegte Behauptungen werden verworfen, nicht als unsicher geführt.** Ein
  "unsicher" markierter Wert ist offen, nicht bestätigt/widerlegt; ein im Rechercheprozess
  selbst **widerlegter** Wert (z. B. Steiermark Ökofonds-PV, NÖ Balkonkraftwerk "300 €"
  als Watt/Euro-Verwechslung) wird gar nicht erst als Eintrag angelegt.

### 6.3 Nachvollziehbarkeit (Quelle + Rechenweg)

Jeder Eintrag trägt `quellen[]` (URL + Abrufdatum + Typ primär/sekundär),
`status`/`status_detail` (inkl. Budget-Ausschöpfungsgrad, wo bekannt) und
`naechstes_fenster` (ISO-Datumsspanne, z. B. der EAG-Call `2026-10-08/2026-10-22`).
`foerderhoehe.werte[]` hält jeden Fördersatz einzeln mit Bezeichnung — kein
zusammengefasster Durchschnittswert. Die Capability `foerderungen_check` liefert
diese Struktur unverändert weiter (kein Rechenweg nötig, da keine Rechnung
stattfindet — reine Faktenauslieferung mit Quelle).

---

## 7. Energieberatung

### 7.1 Erhebung

- **Quellen:** die 9 Landes-/Träger-Websites selbst, gegengelesen an zwei
  bundesweiten Übersichten (`klimaaktiv.at/private/zukunftsfittes-haus/
  energieberatungsstellen`, `oesterreich.gv.at`), die beide unabhängig alle
  9 Bundesländer bestätigen.
- **Snapshot:** `data/beratung/beratungsstellen.json` (9 Einträge, eine je
  Bundesland) + `MANIFEST.json`. Stand `2026-07-31`.

### 7.2 Validierung

- **Kosten-Aussage ("kostenlos") nur bei belastbarer Quelle.** Alle 9 Einträge sind
  `kosten: "kostenlos"`; wo die Quelle das Prinzip zwar bestätigt, aber den
  Umfang nicht quantifiziert (Vorarlberg: "Energiesprechstunde in den meisten
  Gemeinden"), ist der Eintrag `verlaesslichkeit: "unsicher"` mit Begründung —
  das Energietelefon selbst ist gesichert kostenlos, die Reichweite der
  gemeindeseitig finanzierten Vor-Ort-Sprechstunde nicht.

### 7.3 Nachvollziehbarkeit

Jeder Eintrag trägt `traeger` (Trägerorganisation), `url` und `quellen[]`. Die
Capability `beratungsstellen` löst `bundesland` optional aus `plz` über die
bestehende netz-PLZ-Logik auf (`capabilities/netz/resolve.py::plz_info`) — keine
eigene, zweite PLZ-Zuordnung.

---

## 8. Energiegemeinschaften

### 8.1 Erhebung

- **Quellen (statutarisch):** RIS (ElWG BGBl. I Nr. 91/2025, ElWOG 2010 § 16c,
  SNE-V 2018 § 5 Abs. 1a), die amtliche Koordinierungsstelle
  `energiegemeinschaften.gv.at` und der E-Control EAG-Monitoringbericht 2025
  (Marktstand-Tabellen 40–43, per `pdftotext` direkt aus dem PDF geprüft).
- **Snapshot:** `data/energiegemeinschaften/fakten.json` (4 Rechtsformen: GEA,
  EEG lokal, EEG regional, BEG — je mit Netzentgelt-Reduktion + Rechtsquelle;
  ElWG-Änderung; Marktstand zum Stichtag 30.06.2025; 6 Beitrittsschritte),
  `verzeichnis.json` (seit 03.08.2026 **befüllt**: 136 BEG-Einträge aus der
  amtlichen Landkarte, nächtlich nachgezogen — siehe 8.2; Provenance, Coverage
  und Disclaimer des Verzeichnisses stehen in `verzeichnis.MANIFEST.json`) und
  `beg_providers.json` (3 bundesweit beitretbare BEG-Anbieter, 1:1 migriert aus
  dem alten `energietools/data/beg_providers.json`).

### 8.2 Validierung

- **Der ElWG-Zweistufigkeits-Fallstrick ist explizit im Datensatz abgebildet.**
  Die Koordinierungsstelle behauptet pauschal "ab 1.10.2026 gelten die neuen
  Bestimmungen zur Gänze" — das gilt laut Gesetzestext **nicht** für die
  Netzentgelt-Bestimmung § 128 ElWG selbst, die laut § 188 Abs. 5 ElWG erst am
  **31.12.2026** in Kraft tritt (3 Monate später als die Definitionen). Das steht
  in `fakten.json → elwg_aenderung.teil_inkrafttreten_2.wichtiger_hinweis` **wörtlich**,
  damit ein künftiges Feature nicht 3 Monate zu früh einen noch nicht bestehenden
  BEG-Netzentgelt-Vorteil kommuniziert.
- **BEG-Netzentgelt-Reduktion ist `unsicher`, nicht erfunden.** Der künftige
  Prozentsatz steht noch nicht fest (Verordnung nach § 135 Abs. 1/2 ElWG
  ausständig) — `rechtsformen.beg.netzentgelt_reduktion.prozent = null`,
  `verlaesslichkeit: "unsicher"` mit Begründung. Kein geschätzter Platzhalterwert.
- **Widersprüchliche Marktzahlen dokumentiert, nicht aufgelöst.**
  `marktstand.unbestaetigte_zahlen[]` hält drei einander widersprechende
  Sekundärquellen-Zahlenreihen (inkl. einer als "WIDERLEGT/unplausibel"
  bewerteten) neben der amtlichen E-Control-Zahl — sichtbar, nicht stillschweigend
  verworfen oder gemittelt.
- **Verzeichnis unvollständig statt erfunden — und die Lücke steht dabei.** Es
  existiert kein vollständiges, offiziell abrufbares Verzeichnis aller
  österreichischen Energiegemeinschaften (die amtliche Landkarte ist BEG-only,
  deckt EEG — die zahlenmäßig größte Kategorie — gar nicht ab, und erreicht nur
  ~18 % Abdeckungsgrad der 737 BEG). `verzeichnis.json` enthält deshalb genau
  das, was die Landkarte hergibt, mit dieser Einschränkung wörtlich im
  `verzeichnis.MANIFEST.json` — nicht mehr. Kontaktdaten sind bewusst **nicht**
  exportiert (die Nutzungsbedingung der Koordinierungsstelle untersagt
  Werbenutzung). Befüllt wird nächtlich aus
  `gridbert/scrapers/eeg_verzeichnis.py` über den `publish`-Job von
  `tariff-refresh.yml`; schlägt der Abruf fehl oder liefert er null Einträge,
  bleibt der letzte gute Stand stehen statt durch eine leere Liste ersetzt zu
  werden.

### 8.3 Nachvollziehbarkeit

Jede Rechtsform trägt `netzentgelt_reduktion` (Prozentsatz + Rechtsquelle +
Gültigkeit) und `quellen[]`. Die Capability `energiegemeinschaften_info` liefert
Rechtsformen bundesweit (kein `bundesland`-Filter nötig) und grenzt nur die
(aktuell leeren) Verzeichnis-Einträge auf ein Bundesland ein.

---

## 9. Solar/Speicher-Marktdaten

### 9.1 Erhebung

- **Quellen:** Anbieter-Websites, Handelsplattformen mit AT-Angebot
  (`geizhals.at`, `voltaik.shop`, `tink.at`), Branchenverband PV Austria
  (Speicherpreis-Referenz) und das amtliche Regelwerk TOR Stromerzeugungsanlagen
  Typ A (E-Control) für die 800-W-Balkonkraftwerk-Regel.
- **Snapshot:** `data/marktdaten/solar_speicher.json` (Vermittler, Energieversorger-
  PV-Pakete, Hersteller/Händler mit Preisbeispielen, Speicherpreis-Referenz,
  Balkonkraftwerk-Regeln, Ausschluss-Liste) + `MANIFEST.json`. Stand `2026-07-31`.

### 9.2 Validierung

- **Rein informativ — bewusst keine Empfehlungs-/Ranking-/Provisionslogik.** Der
  Datensatz enthält keine Bewertung "bester Anbieter"; jeder Eintrag trägt seine
  Rolle (Vermittler/Hersteller/ausgeschlossen) und Belege, keine Reihung.
  Konsequenterweise gibt es (anders als bei Förderungen/Beratung/
  Energiegemeinschaften) **keine eigene Capability** für dieses Package — nur den
  Loader (`capabilities/marktdaten/data.py`).
- **Risiken transparent statt verschwiegen.** Bekannte Partner-Risiken sind explizit
  vermerkt (z. B. Otovo-Finanzkrise 2024 als eigenes Feld `risiko_hinweis_2024`,
  EET-Insolvenz mit Geschäftszahl + fünf unabhängigen Quellen belegt).
- **Ausschluss-Liste statt Verschweigen.** Anbieter ohne belastbaren AT-Marktbezug
  (1KOMMA5°, Enpal) oder mit erloschener Präsenz (EET, daheim.solar) sind explizit
  mit Begründung als `ausgeschlossen[]` geführt — nicht einfach weggelassen.

### 9.3 Nachvollziehbarkeit

Jeder Eintrag trägt `quellen[]`; Preisbeispiele sind als Stichtags-Snapshots
einzelner Händler markiert, nicht als Marktdurchschnitt (`speicherpreis_referenz`
unterscheidet explizit reine Speicherhardware vs. Komplettpaket-Preise, die nicht
direkt vergleichbar sind).

---

## 10. Fakt vor Heuristik (Lastgang-Signale)

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
