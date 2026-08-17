# HANDOVER — energietools

> Rollierender Stand für die nächste Session. **Stand: 2026-08-17.**
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
- **PyPI-Release 0.8.6** (Stand 2026-08-12, verifiziert per `pypi.org/pypi/energietools/json`
  gegen `pyproject.toml` — beide 0.8.6). **0.8.6 liegt korrekt und vollständig auf PyPI**
  (Wheel + sdist, hochgeladen 11.08. 17:59 UTC, Lauf `31520153666`, `success`). Der
  Commit, dessen Build tatsächlich hochgeladen wurde, ist `9111161` (feat: centgenaue
  Nachrechnung). **Root Cause des GitHub-Actions-Alarms ("Release to PyPI – v0.8.6
  (abf803e) failed", 11.08. 18:33 UTC):** Nach dem erfolgreichen Release wurde ein
  weiterer, rein kosmetischer Commit (`abf803e`, Zeilenlänge/Formatierung in
  `nachrechnung.py` + HANDOVER-Kürzung, **kein Logikunterschied** — per
  `git diff 9111161 abf803e` geprüft) auf den **bereits vergebenen Tag `v0.8.6`
  umgehängt** und erneut gepusht (Lauf `31523124901`, Tag-Push auf denselben Namen,
  18:31 UTC). Das hat den Release-Workflow ein zweites Mal ausgelöst, der Build/Test-Job
  lief grün ("Succeeded in 1 minute and 49...", daher die widersprüchliche
  Benachrichtigung), aber der Upload-Job scheiterte mit `400 Bad Request: File already
  exists ('energietools-0.8.6-py3-none-any.whl', ...)` — PyPI verweigert das erwartungs-
  gemäß, weil Version 0.8.6 schon vorhanden war (unwiderrufliche Versionen, s. `autonomy`).
  **Kein Schaden, keine falsche Version live.** Einzige Nebenwirkung: der Git-Tag `v0.8.6`
  zeigt jetzt auf `abf803e`, nicht auf den tatsächlich hochgeladenen Commit `9111161` —
  ein Provenance-Versatz ohne Funktionsunterschied (Diff ist ausschließlich Formatierung).
  **Nicht selbst repariert:** den Tag zurückzuhängen würde erneut `push --tags` und damit
  erneut den Release-Workflow auslösen — das ist laut Grenzen dieser Session explizit
  nicht erlaubt und wäre ohnehin wirkungslos (PyPI nimmt 0.8.6 so oder so nicht zweimal).
  Empfehlung an Ben s. `fuer_ben`. **Gridbert ist von diesem Vorfall nicht betroffen:**
  `gridbert/pyproject.toml` pinnt `energietools @ git+https://github.com/BMoer/energietools@v0.8.6`
  — das zieht direkt vom Git-Tag, nicht von PyPI, und der Tag zeigt auf funktional
  identischen Code.

## prod ≠ live

- (nichts offen — PyPI 0.8.6 ≡ `pyproject.toml` 0.8.6, erneut verifiziert 17.08.;
  s. „Was live/fertig" für den Doppel-Tag-Vorfall bei 0.8.6, der PyPI nicht betrifft)
- Randnotiz: Es gibt **keine CI für Tests/Lint** (kein Workflow prüft Pushes) —
  nur der Release selbst ist automatisiert. `.github/workflows/release.yml`
  triggert auf `git push origin vX.Y.Z` und lädt via Trusted Publishing (OIDC,
  kein Token) direkt auf PyPI hoch — kein manuelles `twine upload` mehr nötig.
  Tests/Daten-Refresh laufen weiterhin ausserhalb dieses Repos.

## Aus dem globalen Check-in (2026-08-17)

- Der heutige STMK-Förderdatenfix (Commit c7b1e37) erreicht Gridbert nicht automatisch: Gridbert pinnt den Git-Tag v0.8.6 → entweder auf den neuen Commit re-pinnen oder einen neuen Tag setzen, sonst rechnet Gridbert weiter mit dem 20.07.-Stand [Quelle: Projekt-Check-in 17.08.]
- Falls best connect/spotty heute Nachmittag zum Angebot Rechnungsanalyse zusagt, liegt die Rechen-Grundlage (Invoice-Parser und Tarifvergleich) in diesem Repo, nicht in Gridbert → Format und Briefing kommen dann von Ben [Quelle: Mails 13./14.08.]
- Bens letztes Arbeitsfenster dieser Woche endet Donnerstag 20.08. abends; Fr–So ist er privat weg, Mo 24.08. ganztägig beim Voith-Workshop [Quelle: Kalender beide Konten]

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
- [x] **"Release to PyPI – v0.8.6 (abf803e) failed" — geklärt, kein Release-Defekt
      (Topf A, dieser Lauf 12.08.).** `gh run view --log-failed` auf Lauf `31523124901`:
      `400 Bad Request: File already exists ('energietools-0.8.6-py3-none-any.whl', ...)`.
      Ursache: Tag `v0.8.6` wurde nach dem bereits erfolgreichen Release (Lauf
      `31520153666`, Commit `9111161`, 17:59 UTC) auf einen späteren, rein
      kosmetischen Commit (`abf803e`) umgehängt und erneut gepusht — PyPI lehnt das
      korrekt ab, Versionen sind unwiderruflich. PyPI 0.8.6 ≡ `pyproject.toml` 0.8.6
      (verifiziert per JSON-API), Tests 740/740 grün, `git status`/unpushed sauber.
      Gridbert prüft: pinnt Git-Tag `v0.8.6`, nicht PyPI → unbetroffen. **Empfehlung
      für Ben s. `fuer_ben`/unten** — nicht selbst umgesetzt, weil jede Aktion am Tag
      (zurückhängen) den Release-Workflow erneut auslösen würde (Grenze dieser Session).
- [ ] **Tag-Hygiene nach Release — Empfehlung, keine Codeänderung.** Ein Tag sollte
      nach einem erfolgreichen PyPI-Upload nicht mehr bewegt werden, auch nicht für
      rein kosmetische Nachbesserungen — PyPI nimmt die Version ohnehin nicht zweimal
      an, das Ergebnis ist nur ein verwirrender roter Actions-Lauf plus ein Tag, der
      nicht mehr exakt den hochgeladenen Commit trifft (aktuell `v0.8.6` → `abf803e`,
      hochgeladen wurde `9111161`; funktional identisch, geprüft per Diff). Für den
      nächsten Nachbesserungs-Fall: entweder vor dem ersten Tag-Push warten, bis der
      Commit final ist, oder eine neue Patch-Version ziehen statt den Tag zu bewegen.
      Optional (nicht umgesetzt, Workflow-Änderung liegt bei Ben): ein Preflight-Check
      in `release.yml`, der die Zielversion vorab gegen die PyPI-JSON-API prüft und bei
      Kollision mit einer klaren Meldung abbricht, statt den vollen Build/Test-Lauf
      (~2 Min) durchzuziehen und erst beim Upload mit einem rohen 400 zu scheitern.
- [x] **EAG-Monitoringbericht (e-control.at) — geklärt, keine neuere Ausgabe
      (Topf A, dieser Lauf 13.08.).** Direktlink zum PDF gefunden (statt Nav-Seite):
      `e-control.at/documents/1785851/1811582/E-Control-EAG-Monitoringbericht-2025-FINAL...pdf`.
      Deckblatt: „EAG-Monitoringbericht 2025 | Berichtsjahr 2024" — das ist die
      **aktuellste verfügbare Ausgabe** (Publikationsseite `e-control.at/eag-monitoringbericht`
      listet keine neuere). Kapitel 9 (Energiegemeinschaften, S. 87–89) trägt
      **„Quelle: E-Control; Stand: Juli 2025"** mit Tabellen bis zum Stichtag
      **30.06.2025** — exakt der Stand, der hier in
      `energietools/data/energiegemeinschaften/MANIFEST.json` als
      `marktstand_stichtag: "2025-06-30"` hinterlegt ist. Die Zahlen sind also
      nicht überholt, sondern bereits der aktuelle Stand; der Quellen-Wächter-Alarm
      vom 11.08. war ein technischer Seiten-Diff, keine neue Berichtsausgabe.
      Kein Datenrefresh nötig, keine Codeänderung.

- [x] **STMK-Heizungstausch-Förderstand aktualisiert (Topf A, dieser Lauf 17.08.,
      löst den 13.08.-Fund ab).** Gridbert hatte am 13.08. gemeldet, dass unser
      Modell „45 % ausgeschöpft (Stand 20.07.)" zeigt, während die Landesseite
      am 10.08. „noch 41 % verfügbar" (= 59 % ausgeschöpft) nannte. Per WebFetch
      gegen `wohnbau.steiermark.at/cms/beitrag/13000784/183599709` erneut
      bestätigt: die Live-Anzeige steht **weiterhin** auf „41 % verfügbar,
      Stand 10.08.2026" (seit einer Woche unverändert) — unser Katalogeintrag war
      also ca. 3 Wochen veraltet. `energietools/data/foerderungen/foerderungen.json`
      (`stmk-heizungstausch`) korrigiert: `status_detail` trägt jetzt den
      10.08.-Stand, `quellen[0].abrufdatum` auf 2026-08-17 gesetzt. Kein Test hing
      an dem alten Text (`grep` vorher leer), 740 Tests grün vor und nach der
      Änderung. Diff minimal (2 Zeilen) — ein erster Versuch mit `json.dump`
      hätte die ganze Datei auf 2-Space-Einrückung reformatiert (1747
      Zeilen Diff statt 2), wurde verworfen und durch einen gezielten
      String-Edit ersetzt. **Kein Release nötig** (reine Datenkorrektur, wie
      bei den externen `chore(data)`-Refreshs auch ohne Versionsbump) — Gridbert
      pinnt aber Git-Tag `v0.8.6`, bekommt den korrigierten Wert also nur über
      ein Re-Pin auf den neuen Commit oder einen neuen Tag (s. `global`/`fuer_ben`
      im Check-in-Bericht).
- [x] **Externe Daten-Refreshs 14.–17.08. nachgeholt — waren 4 Commits im
      Rückstand.** `git status`/`git log origin/main..HEAD` zeigten zunächst
      „sauber", aber `git diff HEAD origin/main` deckte 4 ungepullte
      `chore(data)`-Commits auf (14., 15., 16., 17.08. — Tarif-Katalog, Netz-
      und EEG-Verzeichnis). Kein Merge-Konflikt möglich, da diese Commits nur
      Datendateien anfassen, die diese Session nicht bearbeitet hat (geprüft per
      `git diff --name-only`). `git pull --ff-only` nachgeholt, 740 Tests
      danach erneut grün. Katalog jetzt: 119 Tarife, weiterhin nur die 2
      `energie_graz`-Einträge mit leerem `zuletzt_bestaetigt` (bekanntes Muster
      seit 11.08., kein neuer Befund). **`naturkraft`** (3 nächtliche FEHLER-2-
      Meldungen 14.–16.08. laut globalem Kontext) zeigt keine Datenlücke: alle
      4 Einträge zuletzt am 17.08. 03:56 UTC erfolgreich bestätigt — die
      Scrape-Fehler haben sich nicht in fehlenden/veralteten Katalogdaten
      niedergeschlagen.
- [x] **Uncommitteter Rest im Arbeitsverzeichnis eingesammelt.** `docs/HANDOVER.md`
      trug seit dem globalen Check-in vom 13.08. eine lokal geänderte, nie
      committete „Aus dem globalen Check-in"-Sektion (STMK-Fund + Bens
      Abwesenheit) — 4 Tage lang uncommitted im Arbeitsverzeichnis. Inhaltlich
      korrekt (deckt sich mit `handoff.sh read energietools`), deshalb nicht
      verworfen, sondern zusammen mit den Änderungen dieser Session committet.
      Für künftige Läufe: `git status --short` ist Teil der Health-Checks, aber
      ein sauberer `git log origin/main..HEAD` sagt nichts über uncommittete
      Änderungen im Working Tree — beide Prüfungen bleiben nötig.

## Session-Log (letzte 3)

- **2026-08-17** — Tages-Check-in (Projektmodus). PyPI ≡ Repo bei **0.8.6**
  (erneut verifiziert), 740 Tests grün. Ruff in-scope unverändert **55**
  (ausschließlich E501). **4 externe `chore(data)`-Refreshs (14.–17.08.)
  nachgeholt** (waren nicht gepullt, s. „Offene Punkte") — Katalog danach
  119 Einträge, `naturkraft` (Gridbert-Alarm 14.–16.08.) zuletzt 17.08. 03:56
  UTC bestätigt, keine Datenlücke; `energie_graz` weiterhin die einzigen 2
  unbestätigten Einträge (unverändertes bekanntes Muster). **STMK-Heizungstausch-
  Förderstand korrigiert** (Topf A) — Live-Seite bestätigt weiterhin „41 %
  verfügbar, Stand 10.08.", unser Katalog stand auf dem alten 20.07.-Wert;
  jetzt nachgezogen. Ein 4 Tage alter uncommitteter Rest in `docs/HANDOVER.md`
  (aus dem globalen Lauf 13.08.) eingesammelt und mit committet. `git status`
  nach diesem Lauf: nur die beiden Doku-/Datendateien dieser Session, kein
  Rechenlogik-Push. Quellen-Wächter/Gridbert-Kontext (72/72 erreichbar, 4
  geänderte Quellen inkl. Bundesförderungen RIS/umweltfoerderung.at/bmwet.gv.at)
  nicht einzeln nachgeprüft — keine der 4 genannten Quellen betrifft einen
  hier bereits bekannten offenen Punkt; als Rückstand vermerkt, falls ein
  künftiger Lauf gezielt nachschauen will.
- **2026-08-13** — Tages-Check-in (Projektmodus). Externen `chore(data)`-Refresh
  vom 13.08. gepullt (`3bb117e`, ff-only) — Tarif-Katalog + Netz-MANIFEST +
  Energiegemeinschaften-Verzeichnis, 119 Tarif-Einträge unverändert,
  `energie_graz` weiterhin 2 valide Einträge mit leerem `zuletzt_bestaetigt`
  (117/119 katalogweit befüllt, unverändert seit 11.08.). 740 Tests grün vor und
  nach dem Pull. PyPI ≡ Repo bei **0.8.6** (erneut verifiziert). GitHub-Actions-
  Alarm vom 11.08. erneut geprüft (`gh run list --workflow=release.yml`): kein
  neuer Vorfall, weiterhin nur der eine historische Doppel-Tag-Fehl-Lauf.
  **EAG-Monitoringbericht-Punkt abschließend geklärt (Topf A):** Direktlink zum
  PDF gefunden statt Nav-Seite — aktuellste Ausgabe ist „EAG-Monitoringbericht
  2025 (Berichtsjahr 2024)", Energiegemeinschaften-Kapitel „Stand: Juli 2025" mit
  Stichtag 30.06.2025, deckt sich exakt mit dem hier hinterlegten
  `marktstand_stichtag`. Keine neuere Ausgabe verfügbar, keine überholten Zahlen,
  Quellen-Wächter-Alarm war ein technischer Seiten-Diff (s. „Offene Punkte").
  **Ruff-Kleinfund behoben (Topf A):** In-Scope-Lint stieg 55 → 56 durch eine
  echte Regelverletzung (`I001`, doppelte Leerzeile nach dem Import-Block in
  `energietools/capabilities/tariffs/models.py:13`, Nebenwirkung des
  0.8.4-Feature-Commits `74f3bdb`) — per `ruff check --fix` behoben (Whitespace-
  only, kein Logikunterschied), zurück auf 55, ausschließlich `E501`. 740 Tests
  vorher/nachher grün. Worktrees: `git worktree list` zeigt weiterhin nur die
  zwei bewusst belassenen (`et-v061`, `energietools-sim-fixes`); der am 10.08.
  geprunte dritte taucht nicht wieder auf. TODO.md unverändert (20 offene
  Punkte). Ein `docs(handover)`-Commit vorgesehen plus der Ruff-Fix — keine
  Rechenlogik geändert, keine Katalog-Daten von hier aus angefasst (nur der
  externe Refresh gepullt).
- **2026-08-12** — Tages-Check-in (Projektmodus). Leitpunkt war der GitHub-Actions-
  Alarm "Release to PyPI – v0.8.6 (abf803e) failed" (11.08. 18:33 UTC). Root Cause
  per `gh run list`/`gh run view --log-failed` (Lauf `31523124901`) geklärt: Tag
  `v0.8.6` wurde nach dem bereits erfolgreichen Release (Lauf `31520153666`, Commit
  `9111161`, 17:59 UTC, Wheel+sdist erfolgreich hochgeladen) auf den späteren,
  rein kosmetischen Commit `abf803e` umgehängt und erneut gepusht — PyPI lehnte den
  zweiten Upload korrekt mit `400 File already exists` ab. PyPI 0.8.6 ≡
  `pyproject.toml` 0.8.6 (JSON-API verifiziert), 740 Tests grün, `git status` sauber,
  nichts unpushed. `git diff 9111161 abf803e` bestätigt: nur Zeilenumbrüche/Formatierung,
  keine Logikänderung — kein funktionaler Unterschied zwischen getaggtem und tatsächlich
  veröffentlichtem Commit. Gridbert-Pin geprüft (`gridbert/pyproject.toml`): zieht
  `energietools @ git+…@v0.8.6` direkt vom Git-Tag, nicht von PyPI → vom Vorfall nicht
  betroffen. Kein Code-/Datenfehler in energietools; Empfehlung zur Tag-Hygiene für Ben
  dokumentiert (s. „Offene Punkte"), Tag selbst nicht angefasst (jede Aktion daran hätte
  den Release-Workflow erneut ausgelöst — Grenze dieser Session). Zwei Doku-Korrekturen
  gemacht: `.claude/checkin.md` („keine CI, `.github/` existiert nicht" war seit 31.07.
  stale — `release.yml` existiert, läuft aber nur bei Tag-Push, nicht bei jedem Commit)
  und dieses HANDOVER (0.8.6-Stand + Vorfall nachgetragen). TODO.md unverändert (20
  offene Punkte, keine Änderung signalisiert). Nur Doku-Commit vorgesehen — keine
  Rechenlogik, keine Katalog-Daten, kein Tag/Workflow angefasst.
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
