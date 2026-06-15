# Simba deployen → `simba.energietools.at`

Simba ist eine FastAPI-App (Rechenkern auf `energietools`, Live-Connectoren über
vendored `pvtool`). Sie läuft als **eigener Container** und wird per **Subdomain**
an energietools.at gehängt. Der Build-Context ist immer der **Repo-Root** (das
Dockerfile installiert `energietools/` aus dem Monorepo).

## Lokal testen (Docker)

```bash
cd apps/simba
docker compose up --build           # → http://localhost:8000
curl -s localhost:8000/api/health   # {"status":"ok","engine":"energietools",...}
```

## Variante A — Fly.io (empfohlen)

```bash
# aus dem Repo-Root:
fly launch --no-deploy --copy-config --name simba-energietools   # einmalig, App anlegen
fly deploy --config apps/simba/fly.toml --dockerfile apps/simba/backend/Dockerfile .

# Solis-Credentials als Secret (nie ins Image):
fly secrets set SOLIS_KEY_ID=… SOLIS_KEY_SECRET=… SOLIS_SN_EAST=… SOLIS_SN_WEST=… SOLIS_SN_EPM=…

# Subdomain anhängen:
fly certs add simba.energietools.at
```

`fly certs add` zeigt die nötigen DNS-Records. Beim Registrar setzen:
**CNAME `simba` → `<app>.fly.dev`** (Fly nennt den genauen Wert; bei manchen
Providern zusätzlich ein `_acme-challenge`-TXT-Record für das Zertifikat).

`fly.toml` hat `min_machines_running = 1` → **kein Cold-Start** (user-facing).

## Variante B — Render

`render.yaml` liegt bei. In Render: **New → Blueprint** auf dieses Repo, dann unter
**Settings → Custom Domains** `simba.energietools.at` hinzufügen und
**CNAME `simba` → `<service>.onrender.com`** setzen. Plan `starter` (nicht Free) →
kein Cold-Start. Solis-Secrets als Environment Variables setzen.

## Nach dem Deploy — Smoke-Test (von der echten Origin)

```bash
curl -s https://simba.energietools.at/api/health
curl -s "https://simba.energietools.at/api/grid-operators" | head -c 200
# Frontend: https://simba.energietools.at  → mit "Sample"-Daten simulieren
```

Die Galerie-Karte (`web/src/content/tools/simba.md`) zeigt bereits auf
`https://simba.energietools.at` (`hosting: external`) — sobald die Subdomain steht,
ist „Tool öffnen" live.

## Was läuft / was hybrid ist

- **Auf energietools (Kern):** `/api/simulate` (alle Strategien), ROI, `/grid-fees`,
  `/grid-operators`, Balancing-Summary, `/health`.
- **Hybrid über vendored pvtool (lazy):** Live-Connectoren (aWATTar, ENTSO-E, Solis,
  PVGIS-Stundenserie) + volle Wärmepumpen-Summary. Im Image enthalten, daher in
  Produktion verfügbar (Solis braucht die Secrets oben).
