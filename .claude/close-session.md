# close-session Profil — energietools

prod: energietools ist eine **Library**, kein Dienst. „prod" heisst hier zweierlei:
(a) der **öffentliche GitHub-Stand** `BMoer/energietools` auf `main` — das Repo ist
public und der auditierbare Kern von Gridbert, jeder Push ist sofort nach aussen
sichtbar; (b) ein **PyPI-Release**, den es noch nicht gibt (Stand 2026-07-30: 404,
`pyproject` steht auf 0.7.2). Es läuft nichts, was man „deployen" müsste.

## dev_servers
stop_at_close:
  - (keine) — dieses Repo hat keinen eigenen Dev-Server. `web/` (Astro) und
    `apps/simba/` sind eigene Deploy-Ziele; startet eine Session dort etwas,
    beim Abschluss listen und mit Ben klären, nicht blind killen.
keep_alive:
  - (keine bekannt)

## tunnels
  - (keine) — energietools spricht mit keinem Server. Findet sich ein Tunnel,
    gehört er einer anderen Session (gridbert/engram): nur listen, nicht schliessen.

## deploy
mode: manual-only
prod_relevant: alles auf `main` (public Repo). Ein PyPI-Release ist ein bewusster,
  separater Schritt — nie aus close-session heraus.
check: `git status --short` + `git log --oneline origin/main..HEAD` (unpushed?);
  PyPI-Stand via `curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/energietools/json`
  gegen `version` in `pyproject.toml`.
procedure: Release ist manuell und bisher nie gelaufen — es gibt **keine CI**
  (`.github/` existiert nicht). Weicht die PyPI-Version von `pyproject.toml` ab,
  nur als „prod ≠ live"-Zeile ins Handover, nicht selbst publizieren.
health: `pip install git+https://github.com/BMoer/energietools` in einem frischen
  venv, danach `python -c "import energietools"`.

## handover
file: docs/HANDOVER.md

## backlog (Vault)
backlog_key: energietools
area_key:    energietools
  (Engram #2, `os.moerzinger`. **Achtung:** das MCP `Gridbert_Personal` zeigt auf
  den *Haushalts*-Workspace `hh-acc-…`, nicht auf Bens persönliches Vault — ein
  `get_page energietools` dort liefert korrekt „no page". Für Engram #2 nur
  `~/.claude/skills/vault-read/vault-read.sh` bzw. `vault-write.sh` benutzen.)

## gate (optional)
script: (keins) — ersatzweise `python -m pytest -q` vor dem Abschluss, wenn die
  Session Code (nicht nur Doku) angefasst hat.

## notes
  - **Der Tarifkatalog ändert sich täglich.** Ein externer Scraper (proprietär, aus
    gridbert) pusht `chore(data): tariff catalog + netz refresh <datum>` direkt auf
    `main`. Zwei Folgen: (1) vor jedem Push `git pull --rebase`, sonst wird der Push
    abgelehnt; (2) **nie eine harte Tarifzahl** in README, GitHub-Description oder
    Vault schreiben — sie ist am nächsten Tag falsch (121 → 119 innerhalb einer
    Session am 2026-07-30). Stabil sind: **60 Versorger**, **14 Netzbereiche**,
    **2233 PLZ**.
  - Zahlen immer gegen `energietools/data/tariffs/MANIFEST.json` und
    `energietools/data/netz/` prüfen, bevor sie nach aussen gehen — das
    Audit-Versprechen des Repos steht und fällt damit.
  - `TODO.md` ist **kein** Handover, sondern die Liste bewusst offener inhaltlicher
    Lücken (Stand 2026-06-03). Offene Session-Punkte gehören in `docs/HANDOVER.md`.
