# HANDOVER — energietools

> Rollierender Stand für die nächste Session. **Stand: 2026-08-10.**
> Ergänzt [TODO.md](../TODO.md) (bewusst offene inhaltliche Lücken, Stand 2026-06-03).
> Dieses File hält den *Session-Stand*, TODO.md die *inhaltlichen Entscheidungen*.

## Was live / fertig

- **GitHub-Repo-Metadaten gesetzt** (SEO/GEO, 2026-07-30): Description, Website
  (`https://www.gridbert.at`) und 9 Topics (`energy`, `electricity`, `austria`,
  `tariff-comparison`, `grid-fees`, `energy-community`, `mcp`, `python`,
  `open-data`). Live auf `BMoer/energietools`.
- **Englischer Einstiegsabsatz im README** (`8e5677d`, `7728a9e`): positioniert die
  Library für Suche und KI-Antworten, verlinkt Gridbert. Steht vor dem bestehenden
  deutschen Text, der unverändert blieb.

- **PyPI-Release 0.8.3** (Stand 2026-08-09, verifiziert per `pypi.org/pypi/energietools/json`
  gegen `pyproject.toml` — beide 0.8.3). Fünf Releases seit dem 0.7.4-Ersteintrag
  (30.07.): **0.7.5** (31.07., Anomalie-Schwelle Lastgang + geteilte PLZ sichtbar),
  **0.8.0** (01.08., Förderungen/Beratung/Energiegemeinschaften/Marktdaten),
  **0.8.1** (03.08., EEG-Verzeichnis 0 → 136 Einträge), **0.8.2** (03.08.,
  `NetzkostenCapability` löst geteilte PLZ über `nb_key`/Gemeinde auf), **0.8.3**
  (08.08., Kindberg-Attribution + Förderquelle `pvbaustria.at`) — die ersten vier
  manuell hochgeladen, **0.8.3 zum ersten Mal automatisch** über
  `.github/workflows/release.yml` (Tag-Push löst Trusted-Publishing-Upload aus,
  kein Token mehr nötig, s. Offene Punkte 08.08.). Kein PyPI-Eintrag ist eigenständig
  auf Aktualität geprüft worden — nur der Versions-Gleichstand.

## prod ≠ live

- (nichts offen — PyPI 0.8.3 ≡ `pyproject.toml` 0.8.3, verifiziert 09.08. + erneut 10.08.)
- Randnotiz: Es gibt **keine CI für Tests/Lint** (kein Workflow prüft Pushes) —
  nur der Release selbst ist automatisiert. `.github/workflows/release.yml`
  triggert auf `git push origin vX.Y.Z` und lädt via Trusted Publishing (OIDC,
  kein Token) direkt auf PyPI hoch — kein manuelles `twine upload` mehr nötig.
  Tests/Daten-Refresh laufen weiterhin ausserhalb dieses Repos.

## Aus dem globalen Check-in (2026-08-10)

- **Tarif-Daten-Alarm 10.08. 04:47 UTC (FEHLER 2, vorher 1):** Volltext (Gmail) geprüft.
  `energie_graz` (Graz Klassik) — **6. Nacht in Folge seit 05.08.**, heute mit konkreterer
  Diagnose als bisher: „Preisblatt ist veraltet (gültig ab 2024-06-12, erwartet ab
  2026-01-28)" statt der früheren 404. Bereits als Arbeitsauftrag dokumentiert
  [bekannt: gridbert-scraper-known-issues, Alarm-Abschnitt 05.08.]. energietools-Katalog
  unverändert: 2 valide Einträge, `gueltig_ab` strukturell leer über 119/119 (unverändert
  seit 05.08.) — kein energietools-seitiger Defekt, identischer Befund wie 05.–09.08.
  **Neu und Ursache der Verdopplung:** `redgas_gas` — „Preisblatt kein gültiges PDF"
  (`redgas.at/php/preisblatt_tcpdf.php`). Geprüft: das ist der **Gas**-Scraper des
  Lieferanten redgas (nicht der Strom-Tarif `redgas` aus `catalog.json`, Zeile 1829, der
  unberührt bleibt). Gas-Tarifvergleich ist laut `TODO.md` bewusst noch nicht in
  energietools (E-Control-Client-Migration offen, Scraper bleiben in gridbert) → außerhalb
  des Scopes dieser Library, kein hiesiger Katalogeintrag betroffen [neu].
- **Quellen-Wächter 10.08. 05:58 UTC (4 Fehler, vorher 2, 0 geändert/neu):** Volltext
  (Gmail) geprüft — alle 4 Fehler sind Timeouts auf **ris.bka.gv.at**. 1 davon ist der seit
  07./08.08. bekannte EEG-Verweis (Gesetzesnummer 20010107, referenziert in
  `energiegemeinschaften/fakten.json` Zeile 44/74). **3 sind neu** und zeigen auf
  Gesetzesnummer 20012195 / 20005371 / 10004873 — per `grep` gegen
  `data/foerderungen/foerderungen.json` verifiziert: alle drei sind dort korrekt als
  Primärquelle referenziert (`bund-eag-invest-pv-speicher`, `bund-energiemanagement-
  flexibilisierung`, `bund-pv-nullsteuersatz`, Abrufdatum 2026-08-01) — kein Link-Rot,
  keine falsche Domain. **Live-Gegenprobe von hier (10.08., ~11:10):** `curl` gegen
  `ris.bka.gv.at` timet zweimal aus (sowohl die neue als auch die bekannte
  Gesetzesnummer-URL, 15s), während `transparenzportal.gv.at` (der 2. Fehler vom 09.08.)
  jetzt wieder normal antwortet (302, 0,5s). Befund: **RIS-seitige Störung/Latenz beim
  Bund**, nicht 3 neu kaputte Quellen und nicht dieselbe alte Quelle wiederholt — die
  Fehlerzahl hat sich verdoppelt, weil ein weiterer RIS-Endpoint zusätzlich zum bekannten
  betroffen ist. Kein energietools-Handlungsbedarf, keine Korrektur an den Quellen nötig
  [neu].
- **Netzbetreiber-IDs (Salzburg Netz / Energie AG KARLSTROM → AT003000):** geprüft, ob
  diese Library numerische VNB-ID-Codes (E-Control-Schema `AT0xxxxx`) führt — **tut sie
  nicht**. `vnb_attribution.json` und `netzkosten.json` nutzen lesbare Keys
  (`netz_ooe`, `ewerk_kindberg`, …), kein `AT0xxxxx`-Feld irgendwo im Repo
  (`grep -rE "AT[0-9]{6}"` → 0 Treffer). Laut Vault (`eda-ccm-prozess`, Stand 31.07.) ist
  `AT003000` = Netz Oberösterreich GmbH; der passende lesbare Key `netz_ooe` ist bereits
  korrekt in `netzkosten.json` vorhanden. `KARLSTROM` kommt in keiner lokalen Datei vor
  (`grep -rliE karlstrom` → 0 Treffer) — es gibt hier nichts Falsches, weil das
  AT0xxxxx-Schema zur EDA/CCM-Marktprozessebene gehört (gridbert-seitig), nicht zum
  Tarif-/Netzkosten-Datenmodell von energietools. Kein Handlungsbedarf hier [neu].

## Offene Punkte (nächste Session)

- [x] **0.8.3 ist auf PyPI — automatisch, nicht von Hand (Korrektur derselben Session).**
      Beim Check-in 08.08. wurde v0.8.3 getaggt und gepusht. **Der Tag-Push hat
      `.github/workflows/release.yml` ausgelöst**, der Workflow hat um 07:48 UTC gebaut und um
      07:50:35 auf PyPI hochgeladen (Lauf `31246991011`, success). Die ursprüngliche Notiz
      ("PyPI-Upload steht aus, Bens Token") war damit von Anfang an falsch und ist ersetzt.
      **Verifiziert:** frisches venv, `pip install energietools==0.8.3` → Version 0.8.3,
      `vnb_attribution.json` mit 4 Einträgen, `ewerk_kindberg` enthalten.
      **Von Ben am 08.08. nachträglich freigegeben** („kein Problem, ist in Ordnung, wenn das
      direkt gepusht wird"). Das Check-in-Profil trägt jetzt **Release = Topf A** statt der
      alten Regel „Kein PyPI-Release, der Upload ist Bens Schritt".
      **Was man trotzdem wissen muss:** Einen Tag `vX.Y.Z` zu pushen IST hier der Release —
      kein manueller Zwischenschritt, kein Abbruch möglich, PyPI-Versionen sind nicht
      überschreibbar. Tests grün und Versionsnummer geprüft, bevor der Tag rausgeht.
- [ ] **ruff-Lint aufräumen (Rest).** 07.08. (Topf A, dieser Lauf): die 7 verbleibenden
      Nicht-E501-Regeln aus dem 06.08.-Fund behoben — `UP042` (`(str, Enum)` →
      `enum.StrEnum` in `capabilities/lastgang/signals.py` + `models/report.py`,
      `requires-python >=3.11` deckt das), `I001`/`E702` (verwaister Mid-File-Reimport
      `import re as _re_module` in `tools/invoice_parser.py` entfernt, `import re` an
      den Kopf, 24 Aufrufstellen umbenannt; Semikolon-Statement in
      `tools/energy_monitor.py::_check_price_alert` aufgeteilt). 707 Tests vorher/nachher
      grün, Commit `c95ffff`, gepusht. In-Scope-Rest (`energietools/`+`tests/`+`examples/`,
      ohne `apps/simba/` — eigenes Deploy-Ziel, s. Notes): 60 → 53 → **55** (10.08.,
      Konsistenzcheck, +2 seit 09.08.), ausschließlich noch **E501 Line-too-long**
      (manuelles Umbrechen, kein Auto-Fix) — braucht weiter eine eigene Session, bewusst
      auf die Woche 17.–20.08. verschoben, keine CI die das fängt.
- [ ] **Restliche SEO/GEO-Punkte umsetzen.** Erledigt ist nur Punkt 1 des Plans
      („GitHub energietools"). Die Punkte 2 ff. liegen bei Ben und wurden in dieser
      Session nicht genannt.
- [x] **PyPI-Release automatisieren? — beantwortet, war zum Zeitpunkt dieser Frage
      bereits erledigt.** Dieser Punkt stammt aus einer Session vor dem 08.08. und
      ist durch den Fund oben ("0.8.3 ist auf PyPI — automatisch") überholt:
      `.github/workflows/release.yml` existiert seit 31.07. und automatisiert den
      Release bereits (Tag-Push → Trusted-Publishing-Upload). Weiterhin zu
      pflegen bleibt nur `version` in `pyproject.toml` (`__version__` liest sie
      seit 0.7.3 aus den Paket-Metadaten) plus Tag und Release-Commit passend dazu.
- [ ] **Drei Worktrees offen** — weiterhin vorhanden (per `git worktree list` erneut
      geprüft, 09.08.), nicht angefasst, gehören anderen Arbeitssträngen:
      `~/.claude/jobs/e7963402/tmp/et-v061` (`fix/v061-load-trend-meta`),
      `~/Projekte/energietools-sim-fixes` (`sim-fixes`) und
      `/private/tmp/gridbert-e2e/wt/energietools` (detached HEAD, `f4ff253`) —
      vermutlich Rest eines E2E-Testlaufs, nicht angefasst (gehört nicht diesem
      Check-in).
- [ ] **best connect + spotty — KI-Rechnungsanalyse (Ben, Mi 12.08. 13:00).** Rechen-
      Grundlage (Invoice-Parser + Tarifvergleich + rechnungsanalyse-Prozess) existiert
      bereits produktiv; sobald das Rechnungsformat/Scope-Briefing vorliegt, eine
      Passungsprüfung fahren (Topf B — Priorität/Zusage liegt bei Ben).

## Session-Log (letzte 3)

- **2026-08-10** — Morgen-Check-in (Projektmodus, Teil des globalen Fan-outs): externen
  `chore(data)`-Refresh vom 10.08. gepullt/rebased (`77a3c00`, 04:48 UTC — lag beim ersten
  Health-Check noch nicht im lokalen Fetch, per `git fetch`+`rebase` nachgezogen) — 3
  Preis-Updates (`spot_aufschlag_ct` 2×, `energiepreis_ct_kwh` 1×) + Energiegemeinschaften-
  Verzeichnis-Datumsbumps; Tarif-Katalog weiterhin 119 Einträge, `energie_graz` unverändert
  2 valide Einträge. PyPI ≡ Repo bei **0.8.3** (erneut verifiziert), 707 Tests grün (vor
  und nach dem Rebase), `git status` sauber. Gegen die
  beiden heutigen Gridbert-Alarme geprüft (Volltext, Gmail):
  **Tarif-Daten-Alarm** (FEHLER 2, vorher 1) — `energie_graz` unverändert (6. Nacht
  in Folge seit 05.08., bekannt: `gridbert-scraper-known-issues`), Katalog weiterhin
  2 valide Einträge, `gueltig_ab` strukturell leer über 119/119. Der zweite Fehler ist
  **neu und anders**: `redgas_gas` (Gas-Preisblatt kein gültiges PDF) — das ist der
  Gas-Scraper des Lieferanten redgas, nicht der hier geführte Strom-Tarif `redgas`;
  Gas ist laut `TODO.md` bewusst noch nicht in energietools → außerhalb des Scopes,
  kein Katalogeintrag betroffen.
  **Quellen-Wächter** (4 Fehler, vorher 2, 0 geändert/neu) — alle 4 sind
  `ris.bka.gv.at`-Timeouts: 1 bekannt (EEG Gesetzesnummer 20010107), 3 neu
  (Gesetzesnummer 20012195/20005371/10004873, per grep gegen `foerderungen.json`
  als korrekt referenzierte Primärquellen verifiziert — kein Link-Rot). Live-Gegenprobe
  von hier: `ris.bka.gv.at` timet gerade selbst zweimal aus (15s), während
  `transparenzportal.gv.at` (gestriger 2. Fehler) wieder normal antwortet (302,
  0,5s) — RIS-seitige Störung beim Bund, kein energietools-Handlungsbedarf.
  **Netzbetreiber-IDs geprüft** (Salzburg Netz / Energie AG KARLSTROM→AT003000 aus
  dem globalen Kontext): energietools führt keine `AT0xxxxx`-Codes, nur lesbare Keys;
  `netz_ooe` (= AT003000 laut Vault `eda-ccm-prozess`) ist bereits korrekt vorhanden,
  `KARLSTROM` kommt nirgends vor — das Thema liegt auf der EDA/CCM-Ebene (gridbert),
  nicht im Datenmodell dieser Library. ruff-Lint (Konsistenzcheck, In-Scope ohne
  `apps/simba/`): 53 → **55**, weiterhin ausschließlich E501, weiter auf 17.–20.08.
  verschoben. Drei Worktrees unverändert (`git worktree list`). Nur Doku-Commit gepusht
  (der Daten-Refresh kam bereits gepusht vom externen Workflow) — keine Rechenlogik
  geändert.
- **2026-08-09** — Morgen-Check-in (Projektmodus, Teil des globalen Fan-outs):
  externen `chore(data)`-Refresh vom 09.08. gepullt (`3f12b52`, 04:26 UTC,
  `3513644..3f12b52`, `git pull --ff-only`) — nur Energiegemeinschaften-Verzeichnis
  (272 Zeilen, ausschließlich `stand`-Datumsbumps 08.08.→09.08., kein inhaltlicher
  Diff) + Netz-/Tarif-MANIFEST; Tarif-Katalog selbst unverändert (119 Einträge,
  kein Preis-Update). PyPI ≡ Repo bei **0.8.3** (bestätigt, s. „Was live/fertig"),
  707 Tests grün (vor und nach dem Pull). Gegen den heutigen Gridbert-Tarif-Alarm
  geprüft (`energie_graz FEHLER 1`, **fünfte** Nacht in Folge seit 05.08.): Katalog
  weiterhin unverändert 119 Einträge, `energie_graz` weiterhin 2 valide Einträge
  (Graz StromFlex, Graz StromKlassik), `gueltig_ab` strukturell leer über alle
  119/119 Einträge (unverändert seit 05.08.) — Staleness-Prüfung bleibt vollständig
  Gridbert-seitig, kein energietools-seitiger Defekt (identischer Befund wie
  05.–08.08.). **Quellen-Wächter** (70/72 erreichbar, 2 Fehler, 5 geändert/neu)
  im Volltext geprüft (Gmail): die 2 Fehler sind reine Timeouts auf
  `transparenzportal.gv.at` (CSV-Bericht) und `ris.bka.gv.at` (Gesetzesnummer
  20010107, EEG) — kein Content-Diff, beide Quellen lokal bereits korrekt
  referenziert (`data/energiegemeinschaften/fakten.json` Zeile 44/74 zeigt exakt
  auf `Gesetzesnummer=20010107`). Die 5 geänderten/neuen Quellen sind durchweg
  Re-Beobachtungen bereits korrekter lokaler Stände (`pvbaustria.at/eag-investzuschuss`
  + `pvbaustria.at/pv-speicher` **neu beobachtet** — der Wächter zeigt jetzt zum
  ersten Mal auf die am 07.08. hier korrigierte Domain, der am 08.08. vermutete
  Deploy-Rückstand auf der Gridbert-Box ist damit behoben; 3× RIS-Gesetzesnummern
  unverändert). Kein energietools-Handlungsbedarf. ruff-Lint unverändert bei 53
  Fehlern (nur noch E501, absichtlich auf die Woche 17.–20.08. verschoben). Drei
  Worktrees unverändert (`git worktree list`: `et-v061`, `energietools-sim-fixes`,
  `gridbert-e2e/wt/energietools`). **Doku-Korrektur (Topf A):** „Was live/fertig"
  und „prod ≠ live" trugen noch 0.8.2 und den überholten Satz „nächster Release
  ist wieder manuell" — beide auf 0.8.3 und den seit 08.08. bekannten
  Trusted-Publishing-Mechanismus (`.github/workflows/release.yml`, Tag-Push
  löst automatisch aus) korrigiert; der Offene-Punkt „PyPI-Release automatisieren?"
  war dadurch bereits beantwortet und als `[x]` markiert. Kein Push nötig — nur
  Daten-Pull + Doku, keine Rechenlogik geändert.
- **2026-08-08** — Morgen-Check-in (Projektmodus, Teil des globalen Fan-outs):
  externen `chore(data)`-Refresh vom 08.08. gepullt (`b673b3a`, `2cf5421..b673b3a`,
  `git pull --ff-only`) — Energiegemeinschaften-Verzeichnis, Netz-MANIFEST und
  Tarif-Katalog aktualisiert (1 Preis-Update: `V-Strom-SPOT-H-KW4925`
  15.5739→16.4936 ct/kWh). PyPI ≡ Repo weiterhin bei 0.8.2, 707 Tests grün
  (vor und nach dem Pull). Gegen den heutigen Gridbert-Tarif-Alarm geprüft
  (`energie_graz FEHLER 1`, identischer Wortlaut wie 06./07.08. — **vierte**
  Nacht in Folge): Katalog unverändert 119 Einträge, `energie_graz` weiterhin
  2 valide Einträge (Graz StromFlex, Graz StromKlassik), `gueltig_ab`
  strukturell leer über alle 119/119 Einträge (unverändert seit 05.08.) —
  Staleness-Prüfung bleibt vollständig Gridbert-seitig, kein energietools-
  seitiger Defekt. **Quellen-Wächter** (72/72 erreichbar, 7 geändert, erneut
  u.a. `[foerderung-bund] pvaustria.at/eag-investzuschuss`) geprüft: lokale
  Quelle ist seit `7d8af3e` (07.08.) bereits auf `pvbaustria.at` korrigiert;
  per `curl -IL` + WebFetch gegen die Live-Seite erneut abgeglichen —
  Fördersätze (150/140/130/120 €/kWp, 150 €/kWh Speicher) und alle drei
  Call-Termine 2026 weiterhin inhaltlich identisch zum lokalen Stand,
  `pvaustria.at` liefert weiterhin nur den 301-Redirect auf `pvbaustria.at`.
  Der wiederholte „geändert"-Flag betrifft damit vermutlich die Quellenliste
  des Wächters selbst (zeigt noch auf die alte Domain) — kein energietools-
  Handlungsbedarf. ruff-Lint unverändert bei 53 Fehlern (nur noch E501,
  absichtlich auf die Woche 17.–20.08. verschoben). Drei Worktrees unverändert
  (`git worktree list`: `et-v061`, `energietools-sim-fixes`,
  `gridbert-e2e/wt/energietools`). Kein Push nötig — nur Daten-Pull, keine
  Rechenlogik geändert.
  (siehe vorherige Sessions im Git-Verlauf dieser Datei für 2026-08-07 und älter.)
