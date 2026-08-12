# checkin Profil — energietools

cadence: daily
one_liner: Python-Library für den österreichischen Strommarkt (Tarife, Netzkosten) —
  public auf GitHub, released auf PyPI. **Der Rechenkern unter Gridbert:** jede €-Zahl,
  die Gridbert ausgibt, kommt von hier. Kein Dienst, nichts zu deployen.

## health
  - PyPI ≡ Repo: `curl -s https://pypi.org/pypi/energietools/json | python3 -c "import json,sys;print('pypi', json.load(sys.stdin)['info']['version'])"`
    gegen `grep -m1 '^version' pyproject.toml`
    → Weicht die Repo-Version ab, ist ein Release ausstehend ⇒ „prod ≠ live"-Zeile,
      **kein** Auftrag (den Upload macht Ben selbst, sein Token, Version unwiderruflich).
  - Unveröffentlichter Stand: `git status --short` + `git log --oneline origin/main..HEAD`
    → Das Repo ist **public**: jeder Push ist sofort nach außen sichtbar.
  - Testlage: `python3 -m pytest -q 2>&1 | tail -3`
    → Die Offline-Tests müssen grün bleiben; das ist die harte Regel aus dem Gridbert-Kanon.

## kpi
  - PyPI-Version + Repo-Version (siehe health) — die eine Zahl, die „ausgeliefert" bedeutet
  - Testergebnis (passed/failed) aus dem pytest-Lauf
  - Offene inhaltliche Lücken: `rg -c "^\s*- \[ \]" TODO.md docs/HANDOVER.md`

## sources
  - **Gridbert ist der einzige echte Konsument.** Auffälligkeiten im Gridbert-Check-in,
    die eine €-Zahl betreffen (Tarif-Alarm, DISAGREE, Quarantäne), gehören hier
    gegengeprüft — das ist der wichtigste Querbezug dieses Projekts.
  - Es gibt **keine CI für Tests/Lint auf jeden Push** — `.github/workflows/release.yml`
    existiert seit 31.07., läuft aber nur bei Tag-Push (`v*`) oder manuellem Dispatch,
    nicht bei normalen Commits auf `main`. Was nicht lokal läuft, läuft nirgends
    (Ausnahme: der Release-Lauf selbst prüft Tests vor dem PyPI-Upload).

## open_points
  - `rg -n "^\s*- \[ \]" docs/HANDOVER.md` — rollierender Session-Stand (Kanon)
  - `rg -n "^\s*- \[ \]" TODO.md` — bewusst offene **inhaltliche** Lücken, langlebiger
    als das Handover; nicht jeden Tag neu aufzählen, nur Änderungen melden

## vault
area_key:     energietools
backlog_key:  energietools
known_issues: (keine)

## handover
file:         docs/HANDOVER.md
checkin_note: docs/HANDOVER.md → Sektion `## Aus dem globalen Check-in (<Datum>)`,
  direkt vor `## Offene Punkte (nächste Session)`. Wird bei jedem Lauf ersetzt.

## autonomy
  - **Release ist Topf A — der Agent darf taggen und damit veröffentlichen.**
    Freigabe von Ben am 2026-08-08 („kein Problem, ist in Ordnung, wenn das direkt gepusht
    wird"). Sie ersetzt die frühere Regel „Kein PyPI-Release, der Upload ist Bens Schritt";
    die gilt nicht mehr.
    **Wie es hier funktioniert, damit es niemand für Git-Hygiene hält:** Es gibt keinen
    manuellen Upload. `.github/workflows/release.yml` triggert auf Tag-Push und lädt selbst
    auf PyPI. `git push origin v0.8.3` war der Release — zwei Minuten später lag 0.8.3 oben
    (Lauf `31246991011`), ohne dass jemand `twine` aufgerufen hätte. **Wer taggt, released.**
    **Bedingungen, die bleiben:** Tests grün vor dem Tag · `version` in `pyproject.toml` und
    Tag müssen übereinstimmen · Release-Commit im Format `chore(release): vX.Y.Z — <was drin
    ist>` · eine PyPI-Version ist **unwiderruflich**, ein Vertipper in der Nummer lässt sich
    nur durch die nächste Version heilen.
    Wird nur ein neuer Stand für ein anderes Repo gebraucht (typisch gridbert) und kein
    Release, geht das weiterhin ohne Tag: Pin auf den Commit-SHA statt auf `vX.Y.Z`.
  - **Kein Push von Rechenlogik ohne grüne Tests.** Public Repo, auditierbarer Kern:
    ein falscher €-Pfad ist hier sichtbarer als irgendwo sonst.
  - **No-LLM-Math gilt hier an der Quelle:** jede €-Zahl muss aus einer Funktion mit
    nachvollziehbarem Rechenweg kommen, nie aus einer Abschätzung.

## notes
  - **Achtung Vault-Verwechslung:** das MCP `Gridbert_Personal` zeigt auf den
    *Haushalts*-Workspace, nicht auf Bens persönliches Vault (Engram #2). Ein
    `get_page energietools` dort liefert korrekt „no page" — das ist **kein** Hinweis,
    dass die Page fehlt. Für Engram #2 immer `~/.claude/skills/vault-read/vault-read.sh`.
  - `web/` und `apps/simba/` sind eigene Deploy-Ziele und gehören nicht in diesen Check-in.
