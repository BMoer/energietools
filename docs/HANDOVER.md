# HANDOVER — energietools

> Rollierender Stand für die nächste Session. **Stand: 2026-08-11.**
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
- **PyPI-Release 0.8.5** (Stand 2026-08-11, verifiziert per `pypi.org/pypi/energietools/json`
  gegen `pyproject.toml` — beide 0.8.5). Zwei weitere Releases am **10.08. abends,
  außerhalb des Check-in-Flows** (Ben direkt, Commits `74f3bdb`/`e6e4588`, 18:37/18:47,
  kein begleitender `docs(handover)`-Commit — deshalb hier erst jetzt nachgetragen):
  **0.8.4** führt `CatalogTariff.zuletzt_bestaetigt` (ISO, additiv/defaulted) plus
  `preis_alter_tage()`/`preis_veraltet` (Schwelle `PREIS_MAX_ALTER_TAGE=14` Tage) ein —
  ein Preis wird bei Überschreitung **gekennzeichnet, nicht ausgeblendet**; **0.8.5**
  macht beide zu `computed_field`s am `Tariff`-Ergebnismodell, damit sie im
  `model_dump` ankommen (der MCP-Gateway legt das Dump einem Sprachmodell vor, das
  sonst selbst rechnen müsste). 15 neue Tests, Motivation laut Commit-Body explizit
  der 11-Tage-404-Fall vom August 2026. **Befund dieses Check-ins, zweifach
  überprüft (erster Stand vor dem 11.08.-Datenrefresh, dann erneut danach — 4
  `chore(data)`-Commits liefen während dieser Session, 04:29–06:37 UTC):** vor dem
  Refresh war `zuletzt_bestaetigt` katalogweit 0/119 befüllt. **Nach dem Refresh
  (aktueller Stand, `origin/main`): 117/119 befüllt** — gridberts Scraper-Stack hat
  das neue Feld also bereits am selben Tag angeschlossen. Die **exakt 2 Ausnahmen
  sind beide `energie_graz`-Einträge** (`zuletzt_bestaetigt: ""`), und zwar bereits
  im allerersten Refresh dieser Session (04:29 UTC) — kein Zufall, sondern Abbild
  des Scrape-Fehlers: ein Preis, der nie bestätigt werden konnte, bekommt nie ein
  Bestätigungsdatum. **Das deckt aber eine Lücke im Mechanismus auf, keine
  Bestätigung, dass er greift:** `preis_veraltet` ist laut Code (`models.py`)
  bei leerem `zuletzt_bestaetigt` bewusst `False` („nie gemessen" ≠ „veraltet",
  Begründung im Commit: sonst wären alle Alt-Snapshots ohne das Feld fälschlich
  markiert). Für `energie_graz` bedeutet das: der Tarif mit dem greifbar
  schlechtesten Bestätigungsstand im ganzen Katalog (6.+ Nacht in Folge
  ungeprüft, Preisblatt 2024-06-12 statt 2026-01-28) zeigt **denselben
  `preis_veraltet=False`** wie ein heute frisch bestätigter Tarif — die
  14-Tage-Regel läuft nur für Tarife an, die *einmal* bestätigt wurden und dann
  veralten, nicht für einen, der *nie* bestätigt wird. Das ist eine bewusste
  Designentscheidung von Ben (Commit-Body von `74f3bdb`), keine Codeänderung von
  hier aus — aber ein konkreter Punkt, den er kennen sollte, weil er am
  einzigen aktuell betroffenen Fall sichtbar wird [siehe `fuer_ben`].

## prod ≠ live

- (nichts offen — PyPI 0.8.5 ≡ `pyproject.toml` 0.8.5, verifiziert 11.08.; 0.8.4/0.8.5
  liefen am 10.08. abends außerhalb des Check-in-Flows, s. „Was live/fertig")
- Randnotiz: Es gibt **keine CI für Tests/Lint** (kein Workflow prüft Pushes) —
  nur der Release selbst ist automatisiert. `.github/workflows/release.yml`
  triggert auf `git push origin vX.Y.Z` und lädt via Trusted Publishing (OIDC,
  kein Token) direkt auf PyPI hoch — kein manuelles `twine upload` mehr nötig.
  Tests/Daten-Refresh laufen weiterhin ausserhalb dieses Repos.

## Aus dem globalen Check-in (2026-08-11)

- Gridbert hat die Energie-Graz-Entscheidung mit Rückmeldetermin Mi 12.08. und heute live erneut bestätigt, dass das Preisblatt beim Anbieter unverändert auf 12.06.2024 steht → sobald Ben stilllegt, ist der Schnitt hier eine reine Datenänderung, kein Code [Quelle: Check-in gridbert 11.08.]
- Die `preis_veraltet`-Lücke (nie bestätigte Preise gelten nicht als veraltet) ist damit kein theoretischer Fall mehr, sondern hat mit energie_graz einen konkreten Belegfall im Live-Katalog [Quelle: Check-in gridbert 11.08.]

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
- [x] **ruff-Lint aufräumen (Rest) — abgeschlossen 2026-08-10.** Der Lauf meldete 148 Befunde, davon 120
      `E501`. Die 28 echten Regelverstöße (15× `I001`, 4× `F841`, 4× `UP017`, 2× `F401`, 2× `UP006`,
      1× `UP035`) lagen **ausnahmslos in `apps/simba/vendor/pvtool/`**, also in eingebundenem
      Fremdcode. Ein `--fix`-Lauf hätte dort 19 Dateien umformatiert und beim nächsten
      Upstream-Abgleich nur Konflikte erzeugt; die Änderung wurde deshalb zurückgenommen
      (`git checkout -- apps/simba/vendor/`, Arbeitsverzeichnis danach sauber) und stattdessen
      `extend-exclude = ["apps/simba/vendor"]` in `pyproject.toml` gesetzt. Ergebnis: 148 → 89
      Befunde, **alle verbleibenden sind `E501`**, kein einziger echter Regelverstoß im eigenen
      Code. 707 Tests grün vor und nach der Änderung. Ursprünglicher Punkt: 07.08. (Topf A, dieser Lauf): 07.08. (Topf A, dieser Lauf): die 7 verbleibenden
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
- [x] **Worktrees aufgeräumt (2026-08-10): einer entfernt, zwei bleiben bewusst.** `/private/tmp/gridbert-e2e/wt/energietools` war als `prunable` markiert (Zielverzeichnis existierte nicht mehr) und wurde per `git worktree prune` entfernt. Die anderen beiden (`~/.claude/jobs/e7963402/tmp/et-v061` auf `fix/v061-load-trend-meta` und `~/Projekte/energietools-sim-fixes` auf `sim-fixes`) existieren weiterhin auf der Platte, gehören anderen Arbeitssträngen und wurden nicht angefasst. Ursprünglicher Punkt: **Drei Worktrees offen** — weiterhin vorhanden (per `git worktree list` erneut
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
- [ ] **`preis_veraltet` markiert `energie_graz` nicht, obwohl das genau der Fall
      ist, für den es gebaut wurde — Design-Frage an Ben, keine Codeänderung von
      hier aus.** `zuletzt_bestaetigt` ist seit 11.08. (während dieser Session,
      gridbert-seitig nachgezogen) katalogweit 117/119 befüllt; die **einzigen 2
      leeren Einträge sind `energie_graz`** (nie erfolgreich bestätigt). Weil der
      Code ein leeres Datum als „nie gemessen" statt „veraltet" wertet
      (`models.py`, bewusste Entscheidung in `74f3bdb`), bleibt `preis_veraltet`
      für `energie_graz` `False` — identisch zu einem heute frisch bestätigten
      Tarif. Empfehlung für eine mögliche spätere Änderung: ein nie bestätigter
      Preis ist mindestens so verdächtig wie ein 15 Tage alter — eine dritte
      Ausprägung (`nie_bestaetigt`/„unbekannt-verdächtig") oder ein Alter ab dem
      Katalog-`stand` statt ab `zuletzt_bestaetigt` würde die Lücke schließen.
      Nicht selbst umgesetzt, weil das eine sehr frische, im Commit-Body
      begründete Design-Entscheidung überschreiben würde.
- [ ] **EAG-Monitoringbericht (e-control.at) — Versionsstand unbestätigt.**
      Quellen-Wächter meldete die Quelle 11.08. als „geändert"; ein WebFetch gegen
      `e-control.at/eag-monitoringbericht` lieferte nur die Navigationsseite, kein
      Datum/keine PDF-URL — weder bestätigt noch widerlegt, dass eine neuere Ausgabe
      die hier hinterlegten Zahlen (Stand 30.06.2025, `fakten.json`/
      `verzeichnis.MANIFEST.json`) überholt hat. Braucht bei Gelegenheit einen
      gezielteren Abgleich (Direktlink zum aktuellen PDF suchen statt der Nav-Seite).

## Session-Log (letzte 3)

- **2026-08-11** — Tages-Check-in (Projektmodus). Beim ersten Health-Check
  (14:10 Ortszeit) lag lokal noch kein `git fetch` seit 10.08. vor — Befund „nichts
  offen" war dadurch **schon veraltet, bevor er geschrieben war**: 4 externe
  `chore(data)`-Refreshs waren bereits 04:29–06:37 UTC gelaufen. Beim
  Push-Versuch der eigenen Doku-Änderung von GitHub zurückgewiesen
  (`! [rejected] … fetch first`) — Fehler bemerkt, `git fetch` + `pull --rebase`
  nachgeholt, alle Befunde unten sind **gegen den Stand nach dem Rebase**
  verifiziert (722 Tests erneut grün danach). PyPI ≡ Repo bei **0.8.5**
  (verifiziert) — **überholt seit 10.08. abends**: Ben hatte außerhalb des
  Check-in-Flows selbst 0.8.4 und 0.8.5 getaggt/gepusht (`74f3bdb`/`e6e4588`,
  Preisfrische-Feature `zuletzt_bestaetigt`/`preis_veraltet`), ohne begleitenden
  Handover-Eintrag — hier nachgetragen (s. „Was live/fertig"). 722 Tests grün
  (vorher 707 laut letztem Handover-Stand — Differenz sind die 15 neuen Tests aus
  0.8.4). Gegen die drei heutigen Gridbert-Signale geprüft: **Tarif-Alarm**
  (`energie_graz`, 4× FEHLER 1) — Katalog unverändert 2 valide Einträge,
  `gueltig_ab` weiterhin leer; neu geprüft, ob Stilllegen eine Codeänderung
  bräuchte — **nein**, `catalog.py` filtert bereits generisch über `gueltig_bis`,
  kein Provider ist im Code hartverdrahtet, reine Datenfrage. **Kernbefund:**
  gridberts Scraper-Stack hat `zuletzt_bestaetigt` noch während dieser Session
  angeschlossen (0/119 → 117/119 befüllt); die 2 verbleibenden Lücken sind exakt
  `energie_graz` — aber `preis_veraltet` bleibt für beide `False`, weil „nie
  bestätigt" im Code nicht als „veraltet" zählt. Der Mechanismus markiert damit
  aktuell nicht den Fall, für den er gebaut wurde — als Design-Frage an Ben
  dokumentiert, nicht selbst geändert.
  **Netzbetreiber-Nachfolge** (Netz OÖ + Energie AG: KARLSTROM-Netz → AT003000, heute
  erstmals mit Altcode `AT003470` benannt) — `AT003470` und `KARLSTROM` weiterhin 0
  Treffer im Repo, alle 14 `netzkosten.json`-Einträge einzeln gegengeprüft, keine
  Karlstrom-Altlast neben `netz_ooe`. Kein Handlungsbedarf. **Quellen-Wächter** (5
  Fehler bei 72, vorher 4; 1 geänderte Quelle `[eeg] e-control.at
  EAG-Monitoringbericht`) — Quelle wird in `fakten.json`
  (`quelle_primaer`+`quellen[]`) und `verzeichnis.MANIFEST.json` referenziert
  (Stand 30.06.2025/Abrufdatum 2026-07-31); WebFetch-Gegenprobe auf die e-control-Seite
  war nicht schlüssig (nur Navigationsseite, kein PDF-Datum) — als offener Punkt
  vermerkt, kein bestätigter Fehler. Ein `docs(handover)`-Commit gepusht (auf die 4
  externen `chore(data)`-Refreshs rebast, danach erneut 722 Tests grün) — keine
  Rechenlogik geändert, keine Katalog-Daten angefasst.
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
  (siehe vorherige Sessions im Git-Verlauf dieser Datei für 2026-08-08 und älter.)
