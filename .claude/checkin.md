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
  - Es gibt **keine CI** (`.github/` existiert nicht). Was nicht lokal läuft, läuft nirgends.

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
  - **Kein PyPI-Release.** Der Upload ist Bens Schritt (sein Token, die Version ist danach
    unwiderruflich belegt). Der Agent darf `version` heben und bauen — hochladen nie.
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
